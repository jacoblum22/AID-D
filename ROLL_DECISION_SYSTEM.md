# Roll Decision System Design

**Version**: 1.0  
**Date**: November 6, 2025  
**Status**: Design Phase

---

## Overview

This system determines **when the DM should ask for a dice roll** vs. **when to just narrate the outcome**. It analyzes player input using GPT-5-nano to identify:
- Whether this is player knowledge vs. character action
- If there's uncertainty + stakes
- If this requires mechanical resolution vs. narrative positioning
- Whether the action verbs imply a roll
- If there are real consequences vs. pure flavor

---

## Core Principles

### Roll When:
1. ✅ **Character is acting** (not player asking meta questions)
2. ✅ **Uncertainty exists** (outcome is not guaranteed)
3. ✅ **Stakes matter** (failure has consequences)
4. ✅ **Success not guaranteed** by fictional positioning

### Narrate When:
1. ❌ **Player-level question** (rules, world facts, clarifications)
2. ❌ **Trivial action** (no uncertainty)
3. ❌ **Automatic success** (good positioning makes it certain)
4. ❌ **Impossible action** (no roll needed, just say no)
5. ❌ **Pure flavor** (no mechanical stakes)

---

## Decision Criteria

### 1. Player vs. Character Knowledge/Action

| Type | Example | Response |
|------|---------|----------|
| **Player question (meta)** | "What's the DC for climbing that wall?" | No roll - answer meta question |
| **Player question (rules)** | "How do spell slots work again?" | No roll - explain rules |
| **Player question (world info)** | "What's the name of this city?" | No roll - DM provides info directly |
| **Inventory/Possessions** | "Do I have a map?" | No roll - check inventory or ask DM |
| **Past actions** | "Did I buy supplies before leaving?" | No roll - DM clarifies or player checks notes |
| **Character knowledge (obscure)** | "Do I know the name of this ancient city?" | ROLL (Mental - if knowledge is uncertain/obscure) |
| **Character knowledge (common)** | "Do I know the name of the capital?" | NARRATE (if everyone would know this) |
| **Character knowledge (guaranteed)** | "Do I recognize this crest?" (diplomat) | NARRATE (if background guarantees it) |
| **Character assessment** | "Would I know how hard that wall is to climb?" | ROLL (Physical/Insight to assess) |
| **Character action** | "I climb the wall" | Maybe ROLL (if uncertain + stakes) |

**KEY DISTINCTIONS:**
1. **Inventory/Possessions** ("Do I have...") → **NARRATE** (either you have it or you don't - check inventory or ask DM)
2. **Past events** ("Did I previously...") → **NARRATE** (no retroactive rolls for past actions)
3. **Common knowledge** → **NARRATE** (just tell them)
4. **Obscure knowledge** → **ROLL** (Mental check, use context)

**Examples:**
- "Do I have rope?" → NARRATE ("Check your inventory. Did you buy rope?")
- "Did I bring a map?" → NARRATE ("Did you pack one before leaving?")
- "Do I know the capital city?" → NARRATE (common knowledge)
- "Do I know this ancient ruined city?" → ROLL (obscure historical fact, DC 18)
- "Do I recognize this ship type?" (sailor) → NARRATE (guaranteed by background)
- "Do I recognize this ship type?" (farmer) → ROLL (specialized knowledge, DC 15)

**Rule of thumb**: Player clarifying, checking possessions, or asking about past → Narrate. Character acting or testing uncertain knowledge → Consider roll.

---

### 2. Uncertainty + Stakes

Both must be present for a roll:

| Situation | Uncertainty? | Stakes? | Roll? |
|-----------|-------------|---------|-------|
| Crossing a small stream | No | None | **Narrate** |
| Sneaking past guards | Yes | Yes | **Roll (Stealth)** |
| Picking up a rock | No | None | **Narrate** |
| Scaling a crumbling tower | Yes | Yes | **Roll (Athletics)** |
| Reading a book in a library | No | None | **Narrate** |
| Deciphering an ancient tome | Yes | Yes (time/resources) | **Roll (Mental+Clever)** |

**Rule of thumb**: Uncertainty + Stakes → Roll. Otherwise → Narrate.

---

### 3. Fictional Positioning vs. Mechanical Resolution

| Type | Example | Action |
|------|---------|--------|
| **Narrative exploration** | "I check under the rug" | If it's there, they find it. No roll. |
| **Uncertain discovery** | "I look for hidden compartments" | Uncertain → Roll (Insight+Subtle) |
| **Guaranteed success** | "I open the unlocked door" | Narrate automatically |
| **Risky action** | "I leap across the chasm" | Risk → Roll (Physical+Graceful) |

**Rule of thumb**: Success guaranteed by description → Narrate. Success depends on hidden info/ability → Roll.

---

### 4. Action Verbs (Player Phrasing)

Player phrasing often reveals whether a roll is needed:

| Player says... | Likely needs roll? | Example |
|----------------|-------------------|---------|
| "I **want to try to**..." | ✅ Yes | "I want to try to climb the wall" |
| "I **look for**..." | ✅ Usually | "I look for traps" |
| "I **ask the DM**..." | ❌ No | "What's the capital of this kingdom?" |
| "My character **remembers**..." | ✅ Maybe | "Do I remember the royal family?" (Mental check) |
| "I **say to the NPC**..." | ⚙️ Maybe | "I tell him we mean no harm" (maybe Social roll) |
| "I **attack**..." | ✅ Yes | "I attack the guard" |
| "I **convince**..." | ✅ Yes | "I convince the merchant" |
| "I **sneak**..." | ✅ Yes | "I sneak past the sleeping dog" |

**Keywords that suggest rolls**:
- Verbs of **attempt**: try, attempt, strive
- Verbs of **perception**: search, look for, investigate, notice
- Verbs of **action**: climb, jump, sneak, attack, dodge
- Verbs of **social**: persuade, convince, deceive, intimidate, charm
- Verbs of **recall/knowledge**: "Do I know...", "Do I remember...", "Do I recognize...", "Would I know..." (testing CHARACTER's knowledge)

**Keywords that suggest narration**:
- Meta questions: "What's...", "How does...", "Can you tell me..." (player asking DM for info)
- Automatic actions: "I walk", "I pick up", "I open" (when trivial)
- Scene clarifications: "Is there...", "What does it look like..." (DM describing the scene)

**CRITICAL DISTINCTION** for knowledge:
- "What's the name of X?" → NARRATE (player asking DM to provide info)
- "Do I know the name of X?" → Check uncertainty:
  - If X is **common knowledge** → NARRATE (just tell them "Yes, it's called...")
  - If X is **obscure/specialized** → ROLL (Mental check)
  - If character's **background guarantees** → NARRATE (sailor knows ships, etc.)

**Examples:**
- "Do I know the capital?" → NARRATE (common)
- "Do I know this ancient ruined city?" → ROLL (obscure, DC 18)
- "Do I recognize ship rigging?" (sailor) → NARRATE (guaranteed)
- "Do I recognize ship rigging?" (farmer) → ROLL (specialized, DC 15)

---

### 5. Consequence vs. Flavor

Sometimes an action has **flavor but no mechanical stakes**. In those cases, narrate creatively without a roll.

| Example | Stakes? | Action |
|---------|---------|--------|
| "I balance my dagger on one finger to impress the crowd" | No | Narrate a cool moment |
| "I perform a flip while crossing the room" | No (unless guards/traps) | Narrate it stylishly |
| "I flip a coin to decide" | No | Narrate the result |
| "I juggle torches at the tavern for tips" | Yes (embarrassment/money) | Roll (Physical+Graceful or Social+Chaotic) |

**Rule of thumb**: If failure would just be awkward but not consequential → Narrate. If failure has real consequences → Roll.

---

## LLM Decision Format

The system uses GPT-5-nano to analyze player input and output a decision:

```json
{
  "decision": "roll|narrate",
  "reasoning": "Brief 1-sentence explanation",
  "confidence": "high|medium|low",
  "suggested_action_if_roll": {
    "domain": "physical|mental|social|insight",
    "style": "forceful|subtle|precise|clever|resilient|graceful|chaotic",
    "dc_hint": 8-30
  }
}
```

### Field Specification

| Field | Type | Required | Description | Notes |
|-------|------|----------|-------------|-------|
| `decision` | string | **Required** | Either `"roll"` or `"narrate"` | Must be one of these two values |
| `reasoning` | string | **Required** | Brief 1-sentence explanation of the decision | Always populated |
| `confidence` | string | **Required** | `"high"`, `"medium"`, or `"low"` | Indicates certainty of decision |
| `suggested_action_if_roll` | object | **Optional** | Suggested roll parameters | **Only present when `decision: "roll"`**. Null or omitted when `decision: "narrate"` |
| `suggested_action_if_roll.domain` | string | Required if parent exists | `"physical"`, `"mental"`, `"social"`, or `"insight"` | Always present when `suggested_action_if_roll` exists |
| `suggested_action_if_roll.style` | string | Required if parent exists | One of 7 styles (see below) | Always present when `suggested_action_if_roll` exists |
| `suggested_action_if_roll.dc_hint` | number | Required if parent exists | Integer 8-30 | Always present when `suggested_action_if_roll` exists |

**Styles**: `forceful`, `subtle`, `precise`, `clever`, `resilient`, `graceful`, `chaotic`

### Decision Values:
- **`roll`**: Character is performing uncertain action with stakes
- **`narrate`**: Player question, trivial action, or guaranteed outcome

### Confidence:
- **`high`**: Clear indicators (attack, sneak, persuade keywords)
- **`medium`**: Some uncertainty (could go either way)
- **`low`**: Ambiguous phrasing or edge case

---

## Examples

### Example 1: Clear Roll
**Input**: "I try to sneak past the sleeping guards."

```json
{
  "decision": "roll",
  "reasoning": "Character attempting stealth with failure consequences",
  "confidence": "high",
  "suggested_action_if_roll": {
    "domain": "physical",
    "style": "subtle",
    "dc_hint": 15
  }
}
```

---

### Example 2: Clear Narrate (Player asking for info)
**Input**: "What's the name of the tavern again?"

```json
{
  "decision": "narrate",
  "reasoning": "Player asking DM for world information directly",
  "confidence": "high",
  "suggested_action_if_roll": null
}
```

---

### Example 2b: Character Knowledge Check
**Input**: "Do I know the name of this ancient city the merchant is describing?"

**Context**: "There's a little-known ancient, abandoned city called Thema"

```json
{
  "decision": "roll",
  "reasoning": "Testing character's knowledge of obscure historical information",
  "confidence": "high",
  "suggested_action_if_roll": {
    "domain": "mental",
    "style": "precise",
    "dc_hint": 18
  }
}
```

**Note**: The key difference is **"What's the name?"** (player wants DM to tell them) vs. **"Do I know the name?"** (character's knowledge is uncertain).

---

### Example 3: Edge Case (Context Dependent)
**Input**: "I open the door."

```json
{
  "decision": "narrate",
  "reasoning": "Trivial action unless door is locked or trapped",
  "confidence": "medium",
  "suggested_action_if_roll": null
}
```

**Note**: The DM can override if context changes (e.g., door is actually locked → roll Physical+Forceful to break it).

---

## Implementation Strategy

1. **Pre-process player input** → Send to GPT-5-nano decision model
2. **Get decision + reasoning** → JSON response
3. **If `roll`** → Use suggested Domain/Style/DC and run ask_roll
4. **If `narrate`** → Just narrate the outcome
5. **Log confidence** → Track edge cases for improvement

---

## Integration Points

- **Router**: Before calling tool validation, check if roll is needed
- **Tool Catalog**: Add `should_ask_roll` decision function
- **Narration**: If `narrate`, skip roll and generate narration directly
- **ask_roll**: If `roll`, use suggested Domain/Style/DC (or refine with additional context)

---

## Testing Strategy

Create interactive test script similar to `test_roll_interactive.py`:
- Display player action prompts
- Show LLM decision + reasoning
- Allow manual override
- Track accuracy of decisions
- Test edge cases

---

## Future Enhancements

- **Context awareness**: Use recent actions/scene to inform decisions
- **Player patterns**: Learn individual player's style over time
- **Multi-character**: Handle party actions (some roll, some don't)
- **Partial rolls**: Some characters roll, others auto-succeed based on positioning
