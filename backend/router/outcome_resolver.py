"""
Outcome Resolution Engine (ORE) - Bridges mechanics and storytelling.

This module takes raw mechanical outcomes (success/fail) and enriches them with
fictional consequences and secondary effects, transforming bare dice results
into compelling narrative moments.

Architecture:
1. Detect domain & outcome band from ToolResult
2. Look up consequences in YAML tables
3. Apply secondary effects via apply_effects
4. Enrich narration hints with consequences
5. Return enhanced ToolResult for rich storytelling
"""

import yaml
import os
import random
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .game_state import GameState
from .validator import ToolResult
from .effects import apply_effects

logger = logging.getLogger(__name__)


@dataclass
class OutcomeConsequence:
    """A consequence derived from a mechanical outcome."""

    description: str
    effects: List[Dict[str, Any]]
    tone_tags: List[str]


class OutcomeResolver:
    """Resolves mechanical outcomes into fictional consequences."""

    def __init__(self):
        """Initialize with outcome tables loaded from YAML files."""
        self.outcome_tables = {}
        self._load_outcome_tables()

    def _load_outcome_tables(self) -> None:
        """Load all outcome tables from YAML files."""
        tables_dir = os.path.join(os.path.dirname(__file__), "outcome_tables")

        if not os.path.exists(tables_dir):
            logger.warning(f"Outcome tables directory not found: {tables_dir}")
            return

        for filename in os.listdir(tables_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                table_name = filename.rsplit(".", 1)[
                    0
                ]  # Remove extension, handle multiple dots
                filepath = os.path.join(tables_dir, filename)

                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        table_data = yaml.safe_load(f)
                        self.outcome_tables[table_name] = table_data
                        logger.info(f"Loaded outcome table: {table_name}")
                except Exception as e:
                    logger.error(f"Failed to load outcome table {filename}: {e}")

    def resolve_outcome(self, result: ToolResult, state: GameState) -> ToolResult:
        """
        Enrich a ToolResult with consequences and secondary effects.

        Args:
            result: The raw tool result from execution
            state: Current game state for context

        Returns:
            Enhanced ToolResult with consequences added
        """
        # Skip if no narration hint or already processed
        if not result.narration_hint or result.narration_hint.get(
            "consequences_resolved"
        ):
            return result

        # Detect domain and outcome
        domain = self._detect_domain(result)
        outcome = result.narration_hint.get("outcome")

        logger.debug(
            f"ORE processing - tool: {result.tool_id}, domain: {domain}, outcome: {outcome}"
        )

        if not domain or not outcome:
            logger.debug(
                f"Cannot resolve outcome - domain: {domain}, outcome: {outcome}"
            )
            return result

        # Look up consequences
        consequence = self._lookup_consequence(domain, outcome, result, state)

        if not consequence:
            logger.debug(f"No consequence found for {domain}.{outcome}")
            return result

        # Apply secondary effects
        processed_effects = self._process_effects(consequence.effects, result, state)

        # Add to existing effects list
        if processed_effects:
            if not hasattr(result, "effects") or result.effects is None:
                result.effects = []
            result.effects.extend(processed_effects)

        # Enrich narration hint
        result.narration_hint["consequence"] = consequence.description

        # Defensive check for tone_tags existence
        if "tone_tags" not in result.narration_hint:
            result.narration_hint["tone_tags"] = []
        result.narration_hint["tone_tags"].extend(consequence.tone_tags)

        result.narration_hint["consequences_resolved"] = True

        logger.debug(f"Resolved {domain}.{outcome}: {consequence.description}")

        return result

    def _detect_domain(self, result: ToolResult) -> Optional[str]:
        """Detect the outcome domain from tool result."""
        tool_id = result.tool_id
        action = result.args.get("action", "")

        # Map tool types and actions to domains
        if tool_id == "ask_roll":
            if action == "sneak":
                return "stealth_outcomes"
            elif action in ["persuade", "intimidate", "deceive"]:
                return "social_outcomes"
            elif action in ["athletics", "shove"]:
                return "combat_outcomes"
        elif tool_id == "attack":
            return "combat_outcomes"
        elif tool_id == "talk":
            return "social_outcomes"
        elif tool_id == "move" and result.args.get("method") == "sneak":
            return "stealth_outcomes"

        return None

    def _lookup_consequence(
        self, domain: str, outcome: str, result: ToolResult, state: GameState
    ) -> Optional[OutcomeConsequence]:
        """Look up consequence from outcome tables."""

        if domain not in self.outcome_tables:
            logger.debug(f"Domain {domain} not found in tables")
            return None

        table = self.outcome_tables[domain]
        domain_key = domain.split("_")[0]  # "stealth_outcomes" -> "stealth"

        logger.debug(f"Looking for {domain_key} in table keys: {list(table.keys())}")

        if domain_key not in table:
            logger.debug(f"Domain key {domain_key} not found in table")
            return None

        outcome_data = table[domain_key].get(outcome)
        logger.debug(
            f"Looking for outcome {outcome} in {domain_key}, found: {outcome_data is not None}"
        )

        if not outcome_data:
            return None

        # Pick random variant if multiple options
        if isinstance(outcome_data, list):
            if not outcome_data:  # Defensive check for empty list
                logger.warning(f"Empty outcome list for {domain_key}.{outcome}")
                return None
            chosen = random.choice(outcome_data)
        else:
            chosen = outcome_data

        logger.debug(
            f"Selected consequence: {chosen.get('description', 'No description')}"
        )

        return OutcomeConsequence(
            description=chosen.get("description", "Something happens."),
            effects=chosen.get("effects", []),
            tone_tags=chosen.get("tone_tags", []),
        )

    def _process_effects(
        self, effects: List[Dict[str, Any]], result: ToolResult, state: GameState
    ) -> List[Dict[str, Any]]:
        """Process effect templates, substituting placeholders."""
        processed = []

        for effect in effects:
            # Deep copy to avoid modifying template
            processed_effect = self._substitute_placeholders(effect, result, state)
            processed.append(processed_effect)

        return processed

    def _substitute_placeholders(
        self, effect: Dict[str, Any], result: ToolResult, state: GameState
    ) -> Dict[str, Any]:
        """Substitute placeholder tokens like {actor}, {target} with actual IDs."""
        processed = {}

        for key, value in effect.items():
            if isinstance(value, str):
                # Replace common placeholders
                actor_id = result.args.get("actor", "")
                target_id = result.args.get("target", "")
                value = value.replace("{actor}", actor_id or "")
                value = value.replace("{target}", target_id or "")
                # Get current zone from actor
                current_zone = ""
                if actor_id and actor_id in state.entities:
                    actor = state.entities[actor_id]
                    if hasattr(actor, "current_zone"):
                        current_zone = actor.current_zone
                value = value.replace("{zone}", current_zone)
            elif isinstance(value, dict):
                value = self._substitute_placeholders(value, result, state)
            elif isinstance(value, list):
                value = [
                    (
                        self._substitute_placeholders(item, result, state)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]

            processed[key] = value

        return processed


# Global resolver instance
_resolver_instance: Optional[OutcomeResolver] = None


def get_resolver() -> OutcomeResolver:
    """Get the global outcome resolver instance."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = OutcomeResolver()
    return _resolver_instance


def resolve_outcome(result: ToolResult, state: GameState) -> ToolResult:
    """Convenience function to resolve outcomes using the global resolver."""
    resolver = get_resolver()
    return resolver.resolve_outcome(result, state)
