# AID&D Dice System Design: d20 + Domain + Style

**Version**: 2.0 (Proposed)  
**Date**: November 6, 2025  
**Status**: Design Phase

---

## Overview

A d20-based resolution system that combines **5e-style bounded accuracy** with **AI-friendly narrative nuance** through two orthogonal progression axes:
- **Domains** (what you rely on): Determine how many dice you roll
- **Styles** (how you do it): Determine the size of those dice

This system maintains familiar D&D mechanics while providing rich flavor and clear margin bands for storytelling.

---

## Core Mechanics

### The Roll Formula

```
Total = d20 + Domain Dice + Flat Modifiers
```

**Where**:
- **d20**: Base randomness (bounded accuracy backbone)
- **Domain Dice**: Roll N dice of size D, where:
  - N = number of dice (determined by Domain rating)
  - D = die size (determined by Style rating)
- **Flat Modifiers**: Small bonuses (+0 to +3 typical)

**Success**: `Total ≥ DC`

### Example Roll

**Lira attempts a Physical + Graceful vault, DC 18**

- Domain: Physical 2 → Roll 2 dice
- Style: Graceful d10 → Each die is a d10
- Flats: +0

**Roll**: `d20 + 2d10 + 0`
- d20: 12
- d10: 7, 5
- **Total**: 12 + 7 + 5 = **24**
- **Result**: Success, margin = 24 - 18 = **6** (Clean success)

---

## Domain System

**Domains** represent what fundamental capability you're drawing upon.

### Four Domains

| Domain | Description |
|--------|-------------|
| **Physical** | Bodily capability: strength, agility, endurance, coordination |
| **Mental** | Intellectual power: logic, memory, knowledge, creativity |
| **Social** | Interpersonal effectiveness: charm, persuasion, leadership, manipulation |
| **Insight** | Perception & intuition: awareness, wisdom, reading people, gut feelings |

### Domain Rating → Number of Dice

| Rating | Dice | Description |
|--------|------|-------------|
| **1** | 1 die | Basic competence |
| **2** | 2 dice | Trained professional |
| **3** | 3 dice | Master-level expertise |
| **4** | 4 dice | Mythic/legendary (rare) |

**Progression Philosophy**: Domain upgrades are **rare and impactful**. Most PCs end campaigns at 2-3; reaching 4 is mythic-tier.

**Mechanical Impact**: Adding a Domain die increases mean by ~`(StyleDie + 1) / 2` and significantly increases variance (bigger, swingier results).

---

## Style System

**Styles** represent how you approach a task - your method and flavor.

### Seven Styles

| Style | Die Size | Description |
|-------|----------|-------------|
| **Forceful** | 0 → d4 → d6 → d8* | Direct, powerful, overwhelming |
| **Subtle** | 0 → d4 → d6 → d8* | Sneaky, hidden, misdirected |
| **Precise** | 0 → d4 → d6 → d8* | Accurate, calculated, controlled |
| **Clever** | 0 → d4 → d6 → d8* | Inventive, lateral, unconventional |
| **Resilient** | 0 → d4 → d6 → d8* | Enduring, steady, unshakeable |
| **Graceful** | 0 → d4 → d6 → d8* | Elegant, flowing, artistic |
| **Chaotic** | 0 → d4 → d6 → d8* | Wild, unpredictable, erratic |

**d8 marked with `*`** = Only ONE style can reach d8 (your signature style)

### Style Rating → Die Size

| Rating | Die Size | Progression |
|--------|----------|-------------|
| **0** | 0 | Untrained (no dice) |
| **1** | d4 | Novice |
| **2** | d6 | Practiced |
| **3** | d8 | Signature (ONE style only) |

**Progression Philosophy**: 
- New characters start with **all 0s**
- Most styles cap at **d6** (practiced/competent)
- Only **one signature style** reaches **d8** (expert)
- Experienced characters have mostly d6s with one d8

**Mechanical Impact**: Each die-size step adds ~+1 per Domain die - noticeable but smaller than adding a whole Domain die.

---

## DC Ladder

Fixed difficulty targets for consistent challenge scaling:

| DC | Difficulty | Description |
|----|------------|-------------|
| **8** | Easy | Routine tasks, minimal risk |
| **10** | Routine | Standard professional work |
| **12** | Tricky | Requires skill and focus |
| **15** | Hard | Challenging even for experts |
| **18** | Expert | Top-tier professional capability |
| **20** | Heroic | Extraordinary feats |
| **25** | Epic | Legendary accomplishments |
| **30** | Mythic | God-like achievements |

---

## Margin of Success Bands

**Margin** = `Total - DC`

These bands provide narrative hooks without additional mechanics:

| Margin | Band | Narration Guidance |
|--------|------|-------------------|
| **< 0** | Fail | Attempt fails with consequences |
| **0-2** | Mixed | Success with a cost or complication |
| **3-6** | Clean | Straightforward success |
| **7-11** | Strong | Impressive success with style |
| **12+** | Dramatic | Spectacular, memorable achievement |

**Purpose**: Translates numbers into story beats. The GM uses the margin band to flavor the outcome, not as a mechanical effect.

---

## Domain × Style Interpretation Matrix

This table provides **flavor guidance** for combining Domains and Styles:

| **Domain ↓ / Style →** | **Forceful** | **Subtle** | **Precise** | **Clever** | **Resilient** | **Graceful** | **Chaotic** |
|------------------------|--------------|------------|-------------|------------|---------------|--------------|-------------|
| **Physical** | Brawling, breaking, shoving | Stealth, pickpocketing, tailing | Surgery, fine tools, lockpicks | Parkour, jury-rigging gear | Marathon, damage soak, grapples | Martial arts, acrobatics, dance | Berserk rush, improvised weapons |
| **Mental** | Bulldozing logic, hard rhetoric | Deception, traps, misdirection | Calculation, recall, proofs | Lateral ideas, hacks, inventions | Deep focus, long study | Elegant theory, clear exposition | Erratic leaps, wild hypotheses |
| **Social** | Command presence, rallying | Intrigue, rumors, manipulation | Diplomacy, contracts, etiquette | Banter, improv persuasion | Hold the line, poker face | Performance, charm, poise | Stir the crowd, start a riot |
| **Insight** | Willpower, conviction, zeal | Read tells, sense motives | Perception, tracking, awareness | See patterns, trickster wisdom | Resist sway, fearlessness | Flow state, serene clarity | Gut hunch, prophetic guess |

**Usage**: When a player declares an action, the GM (or AI) selects the appropriate Domain+Style combination based on this matrix. This provides consistent, flavorful interpretations.

---

## Opposed Checks

When two characters directly contest each other:

1. **Both roll** using the same mechanics (d20 + Domain dice + flats)
2. **Higher total wins**
3. **Margin** = Winner's total - Loser's total
4. Use margin bands to narrate how decisively the winner succeeded

**Example**: Stealth vs Perception
- **Lira** (Physical 2, Subtle d8): d20 + 2d8 = 18
- **Guard** (Insight 2, Precise d6): d20 + 2d6 = 16
- **Result**: Lira wins by margin 2 (Mixed) → She slips past but makes a soft noise

---

## Progression Philosophy

### Two-Speed Growth System

| Axis | Frequency | Impact | End-Game |
|------|-----------|--------|----------|
| **Domains** | Rare | Impactful (adds whole die) | Most PCs: 2-3 dice, Mythic: 4 dice |
| **Styles** | Common | Steady (~+1 per Domain die) | Most favorites: d8-d10, Capstone: d12 |

**Why This Works**:
- **Domain bumps** feel significant - you're fundamentally better at Physical/Mental/Social/Insight
- **Style bumps** feel flavorful - you're refining your approach (Forceful → Graceful, etc.)
- **Flat bonuses** remain small (+0 to +3) - avoid modifier bloat

**Example Progression**:
- **Level 1**: Physical 1, Graceful d6 → 1d6 + d20
- **Level 5**: Physical 2, Graceful d8 → 2d8 + d20
- **Level 10**: Physical 2, Graceful d10 → 2d10 + d20
- **Level 15**: Physical 3, Graceful d10 → 3d10 + d20
- **Level 20**: Physical 3, Graceful d12 → 3d12 + d20

---

## Statistical Properties

### Mean Values by Configuration

Assuming d20 average = 10.5, no flats:

| Domain | Style d4 | Style d6 | Style d8 | Style d10 | Style d12 |
|--------|----------|----------|----------|-----------|-----------|
| **1 die** | 13.0 | 14.0 | 15.0 | 16.0 | 17.0 |
| **2 dice** | 15.5 | 17.5 | 19.5 | 21.5 | 23.5 |
| **3 dice** | 18.0 | 21.0 | 24.0 | 27.0 | 30.0 |
| **4 dice** | 20.5 | 24.5 | 28.5 | 32.5 | 36.5 |

**Observations**:
- Physical 2 + Graceful d10 averages 21.5 vs DC 18 → comfortable success
- Physical 3 + Graceful d12 averages 30.0 → can attempt Mythic DCs
- Bounded by d20: even gods can roll poorly, novices can get lucky

---

## Comparison to Current System

### Current System (Style + Domain)
- Formula: `XdY + AdB` (e.g., 2d6 + 1d8)
- Style and Domain are **separate dice pools**
- More complex mental math
- Wider variance, less bounded

### Proposed System (d20 + Domain × Style)
- Formula: `d20 + NdD` (e.g., d20 + 2d10)
- Domain determines **number**, Style determines **size**
- Simpler math (sum dice of same size)
- Bounded by d20, familiar to D&D players
- Clearer progression (bump Domain OR Style)

**Why Change?**:
- **Familiarity**: d20 backbone matches 5e expectations
- **Clarity**: One die size per roll, not mixing d6 + d8
- **Bounded Accuracy**: d20 keeps things grounded
- **Easier AI**: Simpler to describe and understand

---

## Open Questions

### For Implementation

1. **Replacing Current System**:
   - Should this completely replace the existing Style+Domain system?
   - Or should both coexist (new system for new content)?

2. **Flat Modifiers**:
   - Where do +0 to +3 flats come from?
   - Equipment bonuses? Circumstantial advantages? Temporary buffs?

3. **Character Stats**:
   - Should Domain and Style ratings be stored in PC.stats?
   - Or passed as parameters each roll?

4. **Tool Integration**:
   - How does this affect existing tools (attack, talk, move, etc.)?
   - Do they need updates to use the new system?

5. **NPC Stats**:
   - How do NPCs define their Domain/Style ratings?
   - Should there be quick templates for common NPCs?

6. **Backwards Compatibility**:
   - Should old saves/characters be migrated?
   - Or is this a clean break for new campaigns?

---

## Implementation Plan (Draft)

### Phase 1: Core Rolling
1. Create new roll function: `roll_d20_domain_style()`
2. Update `ask_roll` tool to support new system
3. Add Domain/Style rating fields to Entity stats
4. Add margin band calculation and narration hints

### Phase 2: Character System
1. Define default Domain/Style ratings for PC
2. Create progression rules and level-up mechanics
3. Add Domain/Style rating display to get_info

### Phase 3: Tool Updates
1. Update attack tool to use new system
2. Update talk tool to use new system
3. Update other tools as needed

### Phase 4: Testing & Refinement
1. Comprehensive unit tests for all configurations
2. Playtesting to validate DC ladder
3. Balance adjustments based on feedback

---

## Next Steps

1. **Review & Approval**: Confirm design matches vision
2. **Answer Open Questions**: Clarify integration details
3. **Implement Core**: Build roll_d20_domain_style() function
4. **Test**: Validate statistical properties and edge cases
5. **Integrate**: Update tools and character systems
6. **Playtest**: Real-world validation

---

## Appendix A: Example Rolls

### Example 1: Lockpicking (Physical + Precise)
- **Character**: Rogue with Physical 2, Precise d8
- **DC**: 15 (Hard)
- **Roll**: d20 (11) + 2d8 (5, 7) = **23**
- **Margin**: 23 - 15 = **8** (Strong success)
- **Narration**: "The tumblers click into place with satisfying precision. The lock opens smoothly."

### Example 2: Persuasion (Social + Graceful)
- **Character**: Bard with Social 3, Graceful d10
- **DC**: 18 (Expert)
- **Roll**: d20 (8) + 3d10 (4, 6, 9) = **27**
- **Margin**: 27 - 18 = **9** (Strong success)
- **Narration**: "Your words flow like poetry. The merchant's stern expression melts into a warm smile."

### Example 3: Spot Hidden Trap (Insight + Precise)
- **Character**: Ranger with Insight 2, Precise d6
- **DC**: 20 (Heroic)
- **Roll**: d20 (14) + 2d6 (3, 5) = **22**
- **Margin**: 22 - 20 = **2** (Mixed success)
- **Narration**: "You catch a glint of wire - the trap! But your foot is already moving..."

### Example 4: Opposed Check (Stealth vs Perception)
- **Lira**: Physical 2, Subtle d8 → d20 (15) + 2d8 (6, 3) = **24**
- **Guard**: Insight 2, Precise d6 → d20 (12) + 2d6 (4, 5) = **21**
- **Winner**: Lira by margin 3 (Clean)
- **Narration**: "You slip past the guard's patrol route with practiced ease."

---

## Appendix B: Statistical Tables

### Probability of Meeting DC by Configuration

*(To be calculated during implementation)*

Example format:
```
Domain 2, Style d10 vs DC 15:
- Probability of success: ~75%
- Average margin on success: +5.2
```

---

## Appendix C: Migration from Old System

*(To be defined if backwards compatibility is required)*

Potential mapping:
- Old System `2d6 + 1d8` → New System Physical 2, Forceful d8?
- Requires statistical equivalence analysis

---

**End of Document**
