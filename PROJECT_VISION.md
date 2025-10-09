# AID&D Project Vision

## The Big Picture

The AID&D system has two cooperating layers that work together to provide both tactical scene resolution and persistent world narrative:

### Scene Layer (short-term, tactical)
- **What's happening right now** in a specific location: actors, zones, clocks, turn order
- **Deterministic rules** resolve actions; narration describes outcomes
- **Ends with a recap + deltas** that can update the world

### World/Campaign Layer (long-term, narrative)
- **Canon facts** about places, factions, quests, NPC bios, promises/hooks
- **Provides context** to scenes; gets updated by scene results
- **Think**: Scene = "now", World = "always"

## Architecture Flow

```
Player → Router(Planner) → Validator → Executor(tool) → RRE/Effects → AGS(state)
                                                         ↓
                                                Narrator (facts-only)
Scene deltas ────────────────────────────────→ World/KB (campaign facts)
```

## Core Systems

### 1) AGS — Authoritative Game State (single source of truth)

**Goals (what "good" looks like):**

- **Single source of truth**: All game facts (entities, zones, clocks, factions, items, scene data) live here—not in free-form text.
- **Deterministic + auditable**: Seeded RNG, snapshots, diffs, and effect logs enable replay/undo and testing.
- **Modular + extensible**: Adding a new entity type or effect doesn't require rewiring the world.
- **Visibility-safe**: A single perception layer prevents spoilers for players/NPC AIs.
- **LLM-friendly**: Fast, structured queries; compact slices; stable IDs; consistent shapes.

**Data model (Pydantic skeletons):**

Keep core vs meta distinct. Core = in-world facts. Meta = editorial/system fields (gm_only, timestamps, etc.).

```python
# models/meta.py
class Meta(BaseModel):
    gm_only: bool = False
    visibility: Literal["public","hidden","gm_only"] = "public"
    created_at: Optional[str] = None
    last_changed_at: Optional[str] = None
    source: Optional[str] = None        # "manual" | "generator" | "import"
    known_by: Set[str] = Field(default_factory=set)  # actor ids who know about this
    notes: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

# models/common.py
class Stats(BaseModel):
    hp: int = 0
    max_hp: int = 0
    guard: int = 0
    resources: Dict[str, int] = Field(default_factory=dict)  # stamina, mana...

class InventoryEntry(BaseModel):
    item_id: str
    charges: int = 1
    equipped: bool = False

class Inventory(BaseModel):
    items: Dict[str, InventoryEntry] = Field(default_factory=dict)

class Clock(BaseModel):
    id: str
    name: str
    value: int = 0
    maximum: int = 4
    meta: Meta = Field(default_factory=Meta)

class RelationshipEdge(BaseModel):
    id: str                       # e.g., "pc.arin -> npc.guard.01"
    src: str
    dst: str
    kind: Literal["favor","fear","bond","reputation","quest","owed_debt"]
    value: int = 0                # [-3..+3] or 0..N
    meta: Meta = Field(default_factory=Meta)

# models/entities.py
class EntityBase(BaseModel):
    id: str
    name: str
    kind: Literal["pc","npc","object","item"]
    zone: Optional[str] = None
    tags: Set[str] = Field(default_factory=set)     # in-world tags: "stealthed"
    marks: Set[str] = Field(default_factory=set)    # discrete statuses: "fear","favor:guard"
    stats: Stats = Field(default_factory=Stats)
    inventory: Optional[Inventory] = None           # for pc/npc
    meta: Meta = Field(default_factory=Meta)

class PC(EntityBase): kind: Literal["pc"] = "pc"
class NPC(EntityBase): kind: Literal["npc"] = "npc"
class ObjectEntity(EntityBase): kind: Literal["object"] = "object"
class ItemEntity(EntityBase): kind: Literal["item"] = "item"

# models/space.py
class Exit(BaseModel):
    to: str
    blocked: bool = False
    label: Optional[str] = None

class Zone(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    exits: List[Exit] = Field(default_factory=list)
    tags: Set[str] = Field(default_factory=set)   # "dark","noisy","narrow"
    meta: Meta = Field(default_factory=Meta)

# models/scene.py
class Scene(BaseModel):
    id: str
    name: str
    round: int = 1
    turn_order: List[str] = Field(default_factory=list)
    current_actor: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)  # {"lighting":"dim","alert":"sleepy"}
    clocks: Dict[str, Clock] = Field(default_factory=dict)
    pending_choice: Optional[Dict[str, Any]] = None
    last_effect_log: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Meta = Field(default_factory=Meta)

# models/world.py
class World(BaseModel):
    entities: Dict[str, EntityBase] = Field(default_factory=dict)
    zones: Dict[str, Zone] = Field(default_factory=dict)
    relationships: Dict[str, RelationshipEdge] = Field(default_factory=dict)
    scene: Scene
    # Optional long-term/campaign KB references (see KB section)
    meta: Meta = Field(default_factory=Meta)
```

**AGS API (tiny, stable SDK):**

Expose a compact, explicit surface. All tools should go through this.

```python
# ags.py
class AGS:
    def __init__(self, world: World, rng_seed: Optional[int]=None): ...

    # Reads
    def get_state(self, slice: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        """Return structured slices (entities by ids, zone, scene clocks, etc.)."""

    def get_entity(self, eid: str) -> EntityBase | None: ...
    def get_zone(self, zid: str) -> Zone | None: ...
    def list_visible_entities(self, pov: str, zone_only: bool=True) -> List[str]: ...

    # Writes
    def apply_effects(self, effects: List[Effect], actor: Optional[str]=None,
                      transactional: bool=True, seed: Optional[int]=None) -> ApplyResult: ...

    # Snapshots & diffs
    def snapshot(self, note: str="") -> str:
        """Persist a copy; return snapshot_id"""

    def diff_since(self, snapshot_id: str) -> Dict[str, Any]: ...

    # Integrity
    def validate_invariants(self) -> List[str]: ...
```

**Design notes:**

- `get_state(slice=...)` supports projections and limits: e.g., `{"entities":["pc.arin","npc.guard.01"], "zone":"courtyard", "fields":["hp","tags","zone"]}`.
- `apply_effects` delegates to your existing transactional executor (you've built this).
- Snapshots can be JSON file blobs at first; SQLite later (same SDK).

**Perception & redaction (safety layer):**

One function controls information leakage everywhere:

```python
# visibility.py
def can_player_see(pov_id: Optional[str], entity: EntityBase, world: World) -> bool:
    if entity.meta.gm_only or entity.meta.visibility == "gm_only":
        return False
    if entity.kind in {"pc","npc","object"}:
        # strict: same zone
        actor = world.entities.get(pov_id) if pov_id else None
        return bool(actor and entity.zone == actor.zone)
    if entity.kind == "item":
        # hybrid: zone or known_by
        actor = world.entities.get(pov_id) if pov_id else None
        if actor and entity.zone == actor.zone:
            return True
        return pov_id in entity.meta.known_by
    return False
```

Redaction helper returns stable shapes with placeholders:

```python
def redact_entity(pov_id: Optional[str], e: EntityBase) -> Dict[str, Any]:
    vis = can_player_see(pov_id, e, world=None)  # world bound in instance
    base = {"id": e.id, "name": e.name if vis else "Someone", "kind": e.kind, "is_visible": vis}
    if not vis:
        return base  # keep schema stable, hide sensitive fields
    allowed = {"zone","tags","marks","stats","inventory"}
    out = base | {k: getattr(e, k) for k in allowed}
    # optional: redact deep fields (e.g., inventory counts) per policy
    return out
```

Use this in `get_info` and any other read path.

### 2) RRE — Rules/Resolution Engine (deterministic)

**Resolution kernel:** 
```
total = d20 + sum(style_eff × d<domain>)
```
Banded by margin: `crit/success/partial/fail`

**Effect atoms (Phase 1):** hp, position, clock, guard, mark

**Handlers via registry:** adding an effect = add a handler; tools don't change

### 3) World Model / KB (campaign knowledge)

**Knowledge Base (campaign memory)**

Phase 2A we don't need vector search yet; we need canonical cards:

```python
# kb.py
class Card(BaseModel):
    id: str               # "npc.guard.01" or "lore.smugglers_tunnel"
    title: str
    kind: Literal["entity","place","faction","lore","quest"]
    facts: List[str] = [] # short bullet facts
    citations: List[str] = []  # "note#41", "session2.log@t=12:33"
    meta: Meta = Field(default_factory=Meta)

class KB(BaseModel):
    cards: Dict[str, Card] = Field(default_factory=dict)

def lore_snippet(ids: List[str], k: int = 3) -> Dict[str, List[str]]:
    """Return up to k facts per id; use for narrator context."""
```

**How it connects**

- Scene end commits deltas into KB cards (e.g., "Guard owes party a favor.").
- `get_info(topic="rules"/"relationships")` can surface KB summaries.
- Later, add RAG (vector index) with citations, but keep the same `lore_snippet` API.

**Entity cards:** short bios, tags, 1–3 facts for NPCs/places

**Graphs:** relationships (e.g., "Guard works for the Mill Coop")

**Truth levels:**
- `canon` (locked)
- `soft-canon` (retcon-able) 
- `improv` (ephemeral notes)

**Access:** 
- Narrator can request `lore_snippet(ids, k)`
- Scenes can commit world deltas after resolution (e.g., "Guard now owes the party a favor")

**Implementation:**
- **Now**: JSON dictionaries
- **Later**: vector store + citations (RAG) with the same `lore_snippet` API

**Events & reactions (world maintains itself)**

Add a lightweight internal event bus; publish after `apply_effects`.

```python
# events.py
def publish(event: str, payload: Dict[str, Any]): ...
def subscribe(event: str, cb: Callable[[Dict[str, Any]], None]): ...
```

Useful reaction rules (register on subscribe):

- HP <= 0 → add tag `unconscious`; remove `guard`.
- Zone change → recompute visibility caches.
- Add `fear` mark → emit `guard −1`.

This keeps rule logic out of individual tools and inside the world's reactive layer.

**Integrity checks (guardrails)**

Run after each transaction:

- **HP & resources clamped**: `0 ≤ hp ≤ max_hp`
- **Unique location**: an entity appears in zero or one zones (not several lists if you index by zone).
- **Clock bounds**: `0 ≤ value ≤ maximum`
- **Zone exits symmetric** (optional): if you require two-way edges.
- **No gm_only leaks**: assert redaction isn't bypassed in logged/public views.

Return a list of violated invariants; in transactional mode, rollback and record an error tool result.

**Seeding, determinism, and logs**

The AGS holds a session seed; each `apply_effects` call can accept an override to isolate rolls.

Store roll breakdowns in the effect log so replay is exact.

Every ToolResult written to `/logs/*.jsonl` should include:

- `turn_id`, `round`, `actor`, `tool_id`
- `args`, `effects`, `facts`
- `seed`, `dice_rolls`, `narration_hint.summary`

### 4) Narrative Controller (lightweight pacing)

**Tracks:** scene goal, tone knobs, optional beat hint (raise_complication, cooldown, etc.)

**Feeds:** the Planner (as guidance) and the Narrator (as tone tags)

**Implementation:**
- **Now**: a tiny struct + counters
- **Later**: add a Beat Tagger/evaluator, spotlight metrics

## The Router Loop (control plane)

1. **Planner** builds a menu of legal tools (affordances) from preconditions, then picks one and proposes args
2. **Validator** enforces schema + preconditions (auto-repair disabled for v1; invalid ⇒ ask_clarifying)
3. **Executor** runs the chosen tool, producing facts + effects
4. **AGS** applies effects and snapshots
5. **Narrator** renders 1–3 sentences from facts only (currently via templates, later via 4o-mini with validation & fallback)
6. **Logger** writes structured JSON for each stage

**Deterministic seeds** ensure replays.

## Persistence, snapshots, and diffs

**Phase 2A start: JSON**

- `/data/world.json` → full world state (with schema_version).
- `/data/snapshots/{timestamp}.{scene.round}.json`
- `/logs/turn_YYYYMMDD_HHMMSS.jsonl` (append ToolResults, effects, seeds).

**Phase 2A later: SQLite**

- Tables: entities, zones, relationships, clocks, snapshots, effects_log.
- Same SDK; add migrations with schema_version.

**Diffs**

- Use JSON Patch-like diffs or a simple `{path: (before, after)}` representation.
- Keep a `last_diff_summary` string for human audit.

**Relationship & faction model**

Start simple: edges with value in a bounded range.

- Directed edges: persuasion may change `pc → npc` differently than `npc → pc`.

Derived disposition (for narrator/planner):

- `hostile` if value ≤ −2
- `neutral` if −1..+1  
- `ally` if ≥ +2

Add helpers:

```python
def set_relationship(src, dst, kind, delta): ...
def get_disposition(src, dst) -> Literal["hostile","neutral","ally"]: ...
```

**Zone graph & travel**

Zones own exits with blocked flags. Keep helper utilities:

```python
def is_adjacent(z1: str, z2: str, world: World) -> bool: ...
def list_exits(z: str, world: World) -> List[Exit]: ...
def path_exists(z1: str, z2: str, world: World, allow_blocked=False) -> bool: ...
```

This feeds move preconditions and ask_clarifying options.

## Saving & Retrieving Information

### What gets saved
- State snapshots every turn (for undo/replay)
- Turn logs (structured JSON: player text, chosen tool, args, roll, effects, seed)
- Session recap (generated from logs/facts, not memory)
- World deltas when a scene ends (e.g., "alarm was raised at Mill" → KB update)

### How you retrieve
- **For tools**: `get_state(slice=...)` returns only what's relevant (current actor, zone, visible entities, clocks)
- **For narration**: facts + lore_snippet + tone_tags → template (now) or LLM (later)
- **For future scenes**: read KB/campaign to seed scene tags, NPC dispositions, unresolved hooks

## The Tools (current set)

Each tool = schema → preconditions → executor → ToolResult (facts, narration_hint, effects). No state writes except via effects.

### ask_roll
- Use Style+Domain vs derived DC; map outcome band → minimal effects (move, clock changes, etc.)
- **Args**: actor, action, target?, zone_target?, style, domain, dc_hint, adv_style_delta

### attack  
- Style+Domain vs defense-ish DC; on hit, roll damage (e.g., 1d6), consume mark if applicable
- **Effects**: hp (−), optional mark removal

### move (uncontested)
- **Preconditions**: adjacency + scene allows free movement
- **Effect**: position

### talk
- Social check that maps to small riders (guard, mark, or ease_next_check) based on band
- **Effects**: guard/mark/clock (small)

### use_item
- Looks up item script → emits scripted effects; decrements inventory

### get_info
- Read-only; returns compact facts (hp, zone, clocks, visible enemies)

### narrate_only
- Deterministic facts → prose; no effects
- Topic inference (look/listen/smell/recap/zoom_in), POV rules, visibility guard

### apply_effects
- Applies a provided list of effect atoms (rare/manual/system use)

### ask_clarifying
- Short question + ≤3 options when intent/args are ambiguous/illegal

**Preconditions** are evaluated before the model chooses (to prune the menu) and again in the executor (to be safe).

## How "current scenes" vs "larger story" interact

### Scene starts
- Seeds from the world: location tags, known NPC cards, any active quest hooks ("Find the smuggler")

### During play  
- Scene state evolves via effects (clocks, hp, positions)
- Narration uses world snippets for flavor

### Scene end
- Export deltas back to world/KB:
  - NPC disposition changes
  - A rumor unlocked
  - A quest step completed  
  - New location discovered, etc.

### Between scenes
- World/KB becomes the durable memory that the next scene imports
- Deltas can be represented as structured patches (e.g., JSON Patch) with audit trail

## Where the "AI" is now vs later

### Now
- AI is used for planning (tool choice) if you've wired the Planner
- Narration is template-based (deterministic)

### Soon  
- Add an LLM Narrator pass on top of the template summary with strict validation
- Keep template fallback for reliability

### Later
- Small "intentifier" or classifier to pre-tag user utterances
- RAG for KB
- Evaluator bots for pacing & rule compliance

## Observability & Safety

### Logs
- One structured row per stage (planner, validator, executor, narrator) with turn_id, seed, and diffs

### Safety
- Content prefs (lines/veils) enforced on narration output
- narrate_only never reveals hidden entities

### Determinism
- Fixed RNG seed
- Snapshots allow replay of bugs

## Minimal File/Module Layout

```
/engine
  ags.py          # state + snapshots
  rre.py          # Style+Domain roller + banding
  effects.py      # effect registry & handlers

/world
  kb.py           # entity cards, place graph, lore_snippet()
  nc.py           # scene goal, tone, beat hint

/router
  tool_catalog.py # schemas + preconditions + arg hints
  planner.py      # (menu → choice)  [LLM or rules+LLM hybrid]
  validator.py    # schema & precond checks (no auto-repair v1)
  executor.py     # dispatch to tools → effects → AGS
  narrator.py     # templates now; optional LLM polish later

/logs
  turn_*.jsonl

/data
  state.json
  snapshots/
  kb/
```

## Summary

**Yes**: One system focuses on the current scene; another maintains the world/plot.

**Saving**: transactional effects → snapshots each turn, plus logs; scene end writes deltas into the world/KB.

**Retrieval**: tools read slices of state; Narrator fetches small KB snippets; later you can add RAG.

**Tools**: the nine listed above, each with schema, preconditions, executor, and effect atoms; only effects mutate state.

## Phase 2 Development Roadmap: Building the Game Layer

Now that the low-level mechanics exist, it's time to move upward into narrative orchestration and world persistence — the "brains" of the game.

Broadly, there are three major layers left:

### 🗺️ 1. The Authoritative Game State & World Model (AGS + KB)

You already have an AGS schema, but now it needs to become a living world, not just a container.

**🔧 Purpose**

To manage:
- Persistent entities, locations, factions, and relationships
- Scene transitions and world simulation between scenes
- Query & retrieval for AI reasoning (memory, knowledge base)

**🧩 Subsystems to Build**

Break it up like this:

| Subsystem | Description | Core Deliverable |
|-----------|-------------|------------------|
| Entity Manager | CRUD for PCs, NPCs, Items, Zones | Add/modify/delete entities safely via apply_effects |
| Zone Graph | Tracks spatial relationships (adjacent zones, travel costs) | Zone-level metadata, connections, travel logic |
| Faction & Relationship Graph | Handles alliances, enmity, reputation | Add graph-based structure to relationships topic |
| Knowledge Base / Lore Memory (KB) | Vectorized summaries of entities, scenes, notes | Allows LLM to recall past events canonically |
| Persistence System | Snapshot/Load/Save game states | JSON or SQLite backend |
| Visibility & Perception Engine | Determines what actors can perceive | Integrate meta/known_by system fully |

### 🎭 2. The Narrative Controller (NC)

This is the layer that makes your system feel like a GM instead of a physics simulator.

**🔧 Purpose**

Manage beats, stakes, tension, spotlight balance, and scene goals.

**🧩 Subsystems to Build**

Break it down like the tools:

| Subsystem | Description | Core Deliverable |
|-----------|-------------|------------------|
| Scene Manager | Handles scene creation, entry, exit, pacing | start_scene(), end_scene(), transition_scene() |
| Beat Tracker | Recognizes narrative beats (setup → complication → resolution) | Tag each turn or effect with a beat_type |
| Tension & Clock System | Centralized tension/resource manager | Integrate "clocks" into pacing, not just mechanics |
| Spotlight Balancer | Tracks how long each PC has been active | Weight scene framing accordingly |
| Narration Planner | Converts ToolResults into scene-level narration | Combine narration_hints into full prose |
| Tone Controller | Adjusts emotional tone dynamically | "gritty ↔ whimsical", "sandbox ↔ guided" sliders |

Essentially, you'll be building the DM brain that decides what happens next, not just how to resolve it.

### 🏛️ 3. The Director / AI Orchestrator (LLM Integration Layer)

Once the AGS and NC exist, this is the topmost layer that makes it playable.

**🔧 Purpose**

Turn natural language from players into structured game actions (and back again), using your tools.

**🧩 Subsystems to Build**

| Subsystem | Description | Core Deliverable |
|-----------|-------------|------------------|
| Planner / Intent Router | Maps player input → Tool call + args | Reuse your current planner, but train/expand it |
| Narrator | Turns ToolResults → rich prose | Uses your narration hints + AGS facts |
| Memory Retriever | Injects relevant past lore into context | Vector search over KB |
| Safety & Style Filter | Enforces player tone, genre, and safety lines | Hooks into meta + player prefs |
| Dialogue Engine | Allows freeform conversation between PCs/NPCs | Uses talk + narrate_only tools intelligently |
| Evaluation Bot | Scores scene pacing, tension, clarity | Offline evaluator for tuning the AI |

This is the layer where the LLM truly becomes the "Dungeon Master AI."

### 🪜 Recommended Build Order (Phase 2 Roadmap)

Here's how to structure the next development phase — mirroring the "tool-by-tool" approach used in Phase 1.

**Phase 2A: Authoritative Game State Expansion**

**Phase 2A task breakdown (like the tools phase):**

1. **Meta & redaction layer**
   - Add meta to entities/zones/scene/clock.
   - Implement `can_player_see` + `redact_entity`.
   - Tests: hidden/gm_only/known_by behaviors.

2. **Zone graph utilities**
   - `is_adjacent`, `list_exits`, `path_exists`.
   - Tests: adjacency, blocked paths.

3. **Relationships & disposition**
   - Edge model + helpers; derived disposition bins.
   - Tests: edge updates, summaries.

4. **Snapshots & diffs**
   - JSON snapshot/save; `diff_since`.
   - Tests: roundtrip; diff correctness.

5. **Event bus & reactions**
   - Publish after `apply_effects`; add 3–4 core reaction rules.
   - Tests: HP→unconscious, zone change triggers recompute.

6. **Invariants & rollback**
   - Implement `validate_invariants()`, plug into `apply_effects`.
   - Tests: force invariant failure → rollback.

7. **KB cards & lore_snippet**
   - Card model + write API; hook scene end to persist deltas.
   - Tests: snippets returned, citations retained.

8. **Performance/limits**
   - Add projections/limits to `get_state`; stable sorting.
   - Tests: pagination, field projection.

**File/module layout:**
```
/engine
  ags.py                 # AGS class (reads/writes/snapshots)
  visibility.py          # perception + redaction
  effects_exec.py        # your apply_effects registry (already built)
  invariants.py          # post-transaction checks
  events.py              # event bus
  rng.py                 # seeded RNG helpers

/models
  meta.py
  common.py
  entities.py
  space.py
  scene.py
  world.py

/world
  kb.py                  # cards + lore_snippet
  factions.py            # relationship helpers

/persistence
  json_store.py          # save/load world, snapshots, logs
  sqlite_store.py        # later

/tests
  test_visibility.py
  test_snapshots.py
  test_invariants.py
  test_relationships.py
  test_zone_graph.py
```

**How it all fits your current system:**

- Tools keep emitting effects; AGS applies them atomically and reacts.
- `get_info` and the Narrator read through redaction, never touching raw state directly.
- Planner can call `get_info` with compact projections for fast reasoning.
- Scene Manager (next step in Phase 2B) will call `AGS.snapshot()` on transitions and write world deltas into the KB.

**Phase 2B: Narrative Controller**
1. Scene Manager (scene creation, transitions)
2. Beat & Tension Tracker (scene pacing)
3. Spotlight Tracker (character focus balancing)
4. Narration Aggregator (merge hints into story text)
5. Tone Controller (genre/style sliders)

**Phase 2C: LLM Integration Layer**
1. Planner / Intent Router (input → tool call)
2. Narrator / Story Renderer
3. Memory Retriever (RAG) (retrieve world facts)
4. Evaluator Bots (offline) (feedback + reward shaping)