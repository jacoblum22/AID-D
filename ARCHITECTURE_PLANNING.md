# AID&D Architecture Planning & Restructuring

**Date Started**: November 6, 2025  
**Status**: Planning / Discussion Phase

---

## Purpose

This document tracks architectural discussions, potential restructuring decisions, and planning for changes to the AID&D project structure. It serves as a living record of our design decisions and trade-offs.

---

## Current Architecture Overview

### LLM Integration
- **Parser**: Two-tier hybrid system (Tier 1 deterministic, Tier 2 LLM with 4o-mini)
- **Narration**: GPT-5 models (gpt-5-main for fast responses)
- **Situation Manager**: Orchestrates scene framing, question interpretation, composite narration

### Core Systems
- **Tool System**: 9 implemented tools (ask_roll, narrate_only, apply_effects, get_info, move, attack, talk, use_item, ask_clarifying)
- **Game State**: Comprehensive AGS (Authoritative Game State) with Meta/Redaction layer
- **Outcome Resolution**: Data-driven YAML tables mapping outcomes to fictional consequences
- **Persistence**: JSON-based save/load with session state management

### Recent Discoveries
- **Prompt Caching**: OpenAI supports automatic caching for prompts 1024+ tokens
  - Cached input tokens receive a **discounted rate** (pricing varies by model - check OpenAI docs)
  - Cache lasts 5-10 minutes of inactivity (standard)
  - **Extended caching**: Newer models (GPT-5.1+) support 24-hour retention via `prompt_cache_retention` parameter for long-running workflows
  - Works with GPT-4o, GPT-4o-mini, o1, GPT-5 family
  - Static content (system prompts, tools) should be placed first for optimal caching

---

## Potential Changes Under Consideration

### Problem Statement: "Too Deterministic / Checklist Feel"

**User Feedback**:
> "Originally, I was just essentially telling GPT 5 'You're a DM, follow these rules...etc., etc.' It felt very flowy when I talked to it. Now it feels like when I talk to it, it's going off a checklist a bit. 'You're in this place. You see these exits. You see these entities.'"

**Diagnosis**:
The current architecture has become **over-engineered** with multiple layers of constraints:
1. **Staged planner**: Breaks down intent → tool → arguments (very structured)
2. **Tool schemas**: Rigid Pydantic validation
3. **Situation Manager**: Orchestrates in fixed sequences (scene framing, entity detection, etc.)
4. **Narration generator**: Fed highly structured context (explicit sections for entities, exits, tags)
5. **Outcome resolver**: Maps mechanical results to pre-written YAML outcomes

**Result**: The AI feels like it's "reading from a database" rather than "telling a story."

---

### Architecture Philosophy Tension

**Current State**: "Game Engine with AI Narration"
- Deterministic tools are primary
- AI is called to prettify mechanical results
- Structured data flows through rigid pipelines
- Reliable, testable, predictable
- But feels mechanical and templated

**Original State**: "Conversational AI with Game Rules"
- AI was primary, natural language interface
- Game mechanics were constraints, not the interface
- Emergent, creative, flowing
- But potentially unreliable, hard to test

**Question**: How do we get the best of both worlds?

---

### Potential Solution Directions

#### Option 1: "DM-First Architecture"
**Concept**: Let GPT-5 be the primary interface with tools as invisible helpers

**Changes**:
- Player talks directly to AI DM
- AI decides when to call tools (like function calling)
- Tools execute silently, return results to AI
- AI presents everything narratively

**Pros**:
- Natural conversational flow
- AI has full creative control
- Tools still ensure mechanical consistency

**Cons**:
- Less deterministic/predictable
- Harder to debug
- AI might forget to call tools

**Trade-offs**:
- Creativity ↑, Reliability ↓

---

#### Option 2: "Loosen Narration Constraints"
**Concept**: Keep tool architecture but make narration much less structured

**Changes**:
- Remove explicit "describe entities, then exits, then..." instructions
- Feed raw game state instead of pre-categorized data
- Trust GPT-5 to decide what's interesting to describe
- Reduce prescriptive prompts, increase creative freedom

**Pros**:
- Keeps mechanical reliability
- Reduces templated feel
- Easier to implement (just prompt changes)

**Cons**:
- Might miss important information
- Less consistent output format

**Trade-offs**:
- Natural feel ↑, Information completeness ↓

---

#### Option 3: "Hybrid: Mechanics Backend, Creative Frontend"
**Concept**: Strict separation - tools handle mechanics, AI handles all presentation

**Changes**:
- Tools remain deterministic (dice, effects, validation)
- But tool results never shown directly to player
- AI gets tool results + game state, decides how to present
- Player never sees "tool execution" - only story

**Pros**:
- Best of both worlds potentially
- Mechanical consistency + narrative creativity
- Clear separation of concerns

**Cons**:
- More complex architecture
- Requires careful prompt engineering
- AI must understand mechanical results

**Trade-offs**:
- Complexity ↑, Both creativity and reliability ↑

---

#### Option 4: "Simplify SituationManager"
**Concept**: Remove rigid orchestration sequences

**Changes**:
- Stop auto-triggering scene framing sequences
- Remove forced "move → look → act" patterns
- Let AI decide when to gather information
- More emergent behavior, less scripted

**Pros**:
- Less mechanical feel
- More responsive to player intent
- Simpler code

**Cons**:
- Might lose useful patterns
- Less consistent experience

**Trade-offs**:
- Emergent behavior ↑, Predictability ↓

---

## Discussion Notes

### Session 1: [Date]
**Topic**: 

**Key Points**:
- 

**Questions Raised**:
- 

**Decisions Made**:
- 

**Action Items**:
- [ ] 

---

## Design Principles to Consider

- **Modularity**: Keep systems loosely coupled
- **Testability**: Maintain comprehensive test coverage
- **Cost Efficiency**: Optimize API usage and caching
- **Developer Experience**: Clear, maintainable code
- **Player Experience**: Immersive, responsive gameplay
- **Future-Proofing**: Extensible architecture for future features

---

## Architecture Decision Records (ADRs)

### ADR-001: [Decision Title]
**Date**: 
**Status**: Proposed / Accepted / Rejected

**Context**: 

**Decision**: 

**Consequences**: 
- **Positive**: 
- **Negative**: 
- **Neutral**: 

---

## Next Steps

1. [ ] Identify specific areas for potential restructuring
2. [ ] Analyze current pain points or limitations
3. [ ] Evaluate alternative approaches
4. [ ] Make architectural decisions
5. [ ] Create implementation plan
6. [ ] Execute changes with testing

---

## References

- [PROJECT_VISION.md](PROJECT_VISION.md)
- [CURRENT_IMPLEMENTATION.md](CURRENT_IMPLEMENTATION.md)
- OpenAI Prompt Caching Documentation: https://openai.com/index/api-prompt-caching/
