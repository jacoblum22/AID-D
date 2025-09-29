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

**What it stores (separate but linked):**
- `scene`: id, tags (lighting/alert/noise), clocks, zones, turn order, current actor
- `entities`: PCs/NPCs/items/objects (discriminated union)
- `locations`: zone graph + features
- `campaign`: durable world facts and quest state (future: or store in KB)

**How you use it:**
- Read slices for routing and narration (never dump the whole world)
- Apply effects transactionally
- Create snapshots each turn for undo/replay

**Tiny SDK surface (stable):**
```python
get_state(slice: list[str] | None) -> dict
apply_effects(effects: list[EffectAtom]) -> None
advance_clock(clock_id: str, delta: int) -> int
snapshot(note: str) -> str
```

**Persistence (now → later):**
- **Now**: JSON files + ring-buffer snapshots (cheap, testable)
- **Later**: SQLite/Postgres behind the same SDK

### 2) RRE — Rules/Resolution Engine (deterministic)

**Resolution kernel:** 
```
total = d20 + sum(style_eff × d<domain>)
```
Banded by margin: `crit/success/partial/fail`

**Effect atoms (Phase 1):** hp, position, clock, guard, mark

**Handlers via registry:** adding an effect = add a handler; tools don't change

### 3) World Model / KB (campaign knowledge)

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