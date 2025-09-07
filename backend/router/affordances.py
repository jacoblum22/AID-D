"""
Affordance Filter (Step 2) - Runtime tool filtering and argument enrichment.

This module computes the applicable tool list at runtime by:
1. Filtering tools based on preconditions
2. Always including escape hatches (narrate_only, ask_clarifying)
3. Computing enriched argument hints for each candidate tool
4. Providing context-aware suggestions to reduce hallucination
"""

from typing import List, Dict, Any, Optional, Union, cast
from dataclasses import dataclass

from .game_state import GameState, Utterance, PC, NPC
from .tool_catalog import TOOL_CATALOG, Tool, get_tool_by_id


@dataclass
class ToolCandidate:
    """A tool candidate with enriched argument hints."""

    id: str
    desc: str
    args_hint: Dict[str, Any]
    confidence: float = 1.0  # How confident we are this tool applies


class AffordanceFilter:
    """Computes applicable tools at runtime with enriched argument hints."""

    def __init__(self):
        self.escape_hatch_ids = {"narrate_only", "ask_clarifying"}

    def get_candidates(
        self, state: GameState, utterance: Utterance
    ) -> List[ToolCandidate]:
        """
        Get applicable tool candidates with enriched argument hints.

        Returns:
            List of ToolCandidate objects, always including escape hatches.
        """
        candidates = []

        for tool in TOOL_CATALOG:
            try:
                # Check if tool precondition is satisfied
                is_applicable = tool.precond(state, utterance)

                # Always include escape hatches regardless of preconditions
                if tool.id in self.escape_hatch_ids:
                    is_applicable = True

                if is_applicable:
                    # Get base argument suggestions
                    args_hint = {}
                    if tool.suggest_args:
                        args_hint = tool.suggest_args(state, utterance)

                    # Enrich arguments with context-aware hints
                    enriched_args = self._enrich_arguments(
                        tool, args_hint, state, utterance
                    )

                    # Calculate confidence based on how well the tool matches
                    confidence = self._calculate_confidence(tool, state, utterance)

                    candidate = ToolCandidate(
                        id=tool.id,
                        desc=tool.desc,
                        args_hint=enriched_args,
                        confidence=confidence,
                    )
                    candidates.append(candidate)

            except Exception as e:
                # Log error but don't crash - affordance filtering should be robust
                print(f"Warning: Error processing tool {tool.id}: {e}")
                continue

        # Sort by confidence (highest first)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        return candidates

    def _enrich_arguments(
        self,
        tool: Tool,
        base_args: Dict[str, Any],
        state: GameState,
        utterance: Utterance,
    ) -> Dict[str, Any]:
        """Enrich base arguments with context-aware hints."""
        enriched = base_args.copy()

        # Tool-specific enrichment
        if tool.id == "ask_roll":
            enriched = self._enrich_ask_roll_args(enriched, state, utterance)
        elif tool.id == "move":
            enriched = self._enrich_move_args(enriched, state, utterance)
        elif tool.id == "attack":
            enriched = self._enrich_attack_args(enriched, state, utterance)
        elif tool.id == "talk":
            enriched = self._enrich_talk_args(enriched, state, utterance)
        elif tool.id == "ask_clarifying":
            enriched = self._enrich_clarifying_args(enriched, state, utterance)

        return enriched

    def _enrich_ask_roll_args(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance
    ) -> Dict[str, Any]:
        """Enrich ask_roll arguments with context-aware DC hints."""
        enriched = args.copy()

        # Context-aware DC adjustment
        if "dc_hint" in enriched:
            base_dc = enriched["dc_hint"]

            # Adjust DC based on context
            current_actor = (
                state.actors.get(state.current_actor) if state.current_actor else None
            )
            if current_actor:
                # If targeting a guard, check if they might be sleepy/distracted
                target_id = enriched.get("target")
                if target_id and "guard" in str(target_id).lower():
                    # Example: sleepy guard is easier to sneak past
                    if enriched.get("action") == "sneak":
                        enriched["dc_hint"] = max(8, base_dc - 3)  # Easier DC
                        enriched["dc_reason"] = "sleepy guard"

                # Zone-specific adjustments
                current_zone = state.zones.get(current_actor.current_zone)
                if current_zone and "courtyard" in current_zone.id.lower():
                    # Open areas might be harder for stealth
                    if enriched.get("action") == "sneak":
                        enriched["dc_hint"] = min(18, base_dc + 2)
                        enriched["dc_reason"] = "open courtyard"

        return enriched

    def _enrich_move_args(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance
    ) -> Dict[str, Any]:
        """Enrich move arguments with movement context."""
        enriched = args.copy()

        # Add movement method hints
        text_lower = utterance.text.lower()
        if any(word in text_lower for word in ["sneak", "quietly", "stealth"]):
            enriched["movement_style"] = "stealth"
        elif any(word in text_lower for word in ["run", "quickly", "fast"]):
            enriched["movement_style"] = "fast"
        else:
            enriched["movement_style"] = "normal"

        # Add zone description for context
        if "to" in enriched:
            target_zone = state.zones.get(enriched["to"])
            if target_zone:
                enriched["zone_name"] = target_zone.name
                enriched["zone_desc"] = target_zone.description

        return enriched

    def _enrich_attack_args(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance
    ) -> Dict[str, Any]:
        """Enrich attack arguments with combat context."""
        enriched = args.copy()

        # Suggest weapon based on utterance
        text_lower = utterance.text.lower()
        if "sword" in text_lower:
            enriched["weapon"] = "sword"
        elif "bow" in text_lower or "arrow" in text_lower:
            enriched["weapon"] = "bow"
        elif "dagger" in text_lower:
            enriched["weapon"] = "dagger"

        # Add target information
        if "target" in enriched:
            target_actor = state.actors.get(enriched["target"])
            if target_actor:
                enriched["target_name"] = target_actor.name
                enriched["target_zone"] = target_actor.current_zone

        return enriched

    def _enrich_talk_args(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance
    ) -> Dict[str, Any]:
        """Enrich talk arguments with social context."""
        enriched = args.copy()

        # Extract potential message from utterance
        text = utterance.text
        quote_patterns = ['"', "'", "say ", "tell ", "ask "]

        for pattern in quote_patterns:
            if pattern in text.lower():
                # Try to extract the message part
                if pattern in ['"', "'"]:
                    parts = text.split(pattern)
                    if len(parts) >= 3:
                        enriched["message"] = parts[1]
                else:
                    # For "say X", "tell X", etc.
                    idx = text.lower().find(pattern)
                    if idx >= 0:
                        message_part = text[idx + len(pattern) :].strip()
                        enriched["message"] = message_part
                break

        # Add target relationship context
        if "target" in enriched:
            target_actor = state.actors.get(enriched["target"])
            if target_actor:
                enriched["target_name"] = target_actor.name
                if "guard" in target_actor.name.lower():
                    enriched["relationship"] = "authority_figure"
                elif hasattr(target_actor, "type") and target_actor.type == "npc":
                    enriched["relationship"] = "stranger"

        return enriched

    def _enrich_clarifying_args(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance
    ) -> Dict[str, Any]:
        """Enrich ask_clarifying arguments with context-specific questions."""
        enriched = args.copy()

        # Generate context-appropriate clarifying questions
        text_lower = utterance.text.lower()
        current_actor = (
            state.actors.get(state.current_actor) if state.current_actor else None
        )

        if current_actor:
            visible_actors = []
            if hasattr(current_actor, "visible_actors"):
                pc_or_npc = cast(Union[PC, NPC], current_actor)
                visible_actors = pc_or_npc.visible_actors
            current_zone = state.zones.get(current_actor.current_zone)

            # Ambiguous action clarification
            if any(word in text_lower for word in ["it", "that", "thing", "there"]):
                if visible_actors:
                    enriched["question"] = (
                        f"Do you mean the {state.actors[visible_actors[0]].name}?"
                    )
                elif current_zone:
                    enriched["question"] = (
                        f"What specifically in the {current_zone.name}?"
                    )

            # Movement ambiguity
            elif any(word in text_lower for word in ["go", "move"]) and current_zone:
                # Safely resolve adjacent zone names, filtering out any that don't exist
                adjacent_names = []
                for z_id in current_zone.adjacent_zones:
                    zone = state.zones.get(z_id)
                    if zone is not None:
                        adjacent_names.append(zone.name)
                
                if len(adjacent_names) > 1:
                    enriched["question"] = (
                        f"Where to? You can go to: {', '.join(adjacent_names)}"
                    )

            # Action method ambiguity
            elif (
                any(word in text_lower for word in ["attack", "approach"])
                and visible_actors
            ):
                target_name = state.actors[visible_actors[0]].name
                enriched["question"] = (
                    f"How do you want to approach the {target_name}? Stealthily, directly, or diplomatically?"
                )

        return enriched

    def _calculate_confidence(
        self, tool: Tool, state: GameState, utterance: Utterance
    ) -> float:
        """Calculate confidence score for how well this tool matches the context."""
        base_confidence = 0.5

        # Escape hatches get lower confidence unless specifically needed
        if tool.id in self.escape_hatch_ids:
            return 0.3

        # Boost confidence based on keyword matching
        text_lower = utterance.text.lower()

        confidence_boosters = {
            "ask_roll": ["roll", "check", "try", "attempt", "sneak", "persuade"],
            "move": ["go", "move", "walk", "run", "travel", "enter"],
            "attack": ["attack", "fight", "hit", "strike", "combat", "kill"],
            "talk": ["talk", "say", "tell", "ask", "speak", "whisper"],
            "use_item": ["use", "drink", "cast", "throw", "activate"],
            "get_info": ["look", "examine", "search", "what", "where", "who"],
        }

        if tool.id in confidence_boosters:
            keywords = confidence_boosters[tool.id]
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            base_confidence += matches * 0.2

        # Cap confidence at 1.0
        return min(1.0, base_confidence)


# Global instance for easy access
affordance_filter = AffordanceFilter()


def get_tool_candidates(state: GameState, utterance: Utterance) -> List[ToolCandidate]:
    """Convenience function to get tool candidates."""
    return affordance_filter.get_candidates(state, utterance)
