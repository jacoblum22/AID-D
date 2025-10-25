"""
Planner - LLM-based tool selection from filtered menu.

The Planner takes the affordance filter output and:
1. Formats it into a numbered, deterministic menu
2. Creates structured prompts for LLM consumption
3. Constrains LLM to pick from the menu (no free-form generation)
4. Returns validated JSON with chosen tool and arguments
5. Falls back gracefully on LLM failures
"""

import json
import logging
from typing import Dict, Any, Optional, List, Union, cast
from dataclasses import dataclass

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .game_state import GameState, Utterance, PC, NPC
from .affordances import ToolCandidate, get_tool_candidates
from .tool_catalog import TOOL_CATALOG


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PlannerResult:
    """Result from the Planner."""

    chosen_tool: str
    args: Dict[str, Any]
    confidence: float
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class ActionSequenceResult:
    """Result from the Planner that supports sequential actions."""

    actions: List[Dict[str, Any]]  # List of {"tool": str, "args": Dict[str, Any]}
    confidence: float
    success: bool = True
    error_message: Optional[str] = None
    is_compound: bool = False  # True if this is a multi-action sequence


class Planner:
    """LLM-based planner that selects tools from constrained menus."""

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """Initialize the planner with OpenAI configuration."""
        import config

        self.client = OpenAI(api_key=api_key)
        self.model = model or config.PLANNING_MODEL
        self.max_tokens = max_tokens or config.PLANNING_MAX_TOKENS
        self.temperature = temperature or config.PLANNING_TEMPERATURE

        # System prompt for the planner role
        self.system_prompt = """You are a Planner for an AI D&D game. Your job is to choose exactly one tool from the provided numbered list and return JSON only.

CRITICAL RULES:
- Choose exactly ONE tool from the numbered list
- Return ONLY valid JSON in the specified format
- Use canonical tool IDs exactly as provided
- If player intent is ambiguous, choose "ask_clarifying"
- If the action has no mechanics, choose "narrate_only"
- Do not invent new tools or modify the provided arguments significantly
- Confidence should be 0.0-1.0 based on how well the tool matches player intent

Required JSON format:
{
  "chosen_tool": "tool_id_from_list",
  "args": {
    "key": "value"
  },
  "confidence": 0.85
}"""

        # Generate list of compound-eligible tools (exclude internal-only tools)
        compound_eligible_tools = [
            tool.id
            for tool in TOOL_CATALOG
            if tool.id != "apply_effects"  # Exclude internal-only tools
        ]
        tool_list_str = ", ".join(compound_eligible_tools)

        # System prompt for compound action parsing
        self.compound_system_prompt = f"""You are a Compound Action Parser for an AI D&D game. Your job is to detect if player input contains multiple sequential actions and break them into an ordered list.

DETECTION RULES:
- Look for connecting words: "and", "then", "after", "before", "while"
- Look for sequential verbs: "look around and move", "drink potion then attack"
- Each action should be semantically complete
- Maintain logical order (causality matters)

OUTPUT RULES:
- Return ONLY valid JSON
- If single action: {{"is_compound": false, "actions": [{{"tool": "tool_id", "args": {{...}}}}]}}
- If multiple actions: {{"is_compound": true, "actions": [{{"tool": "tool1", "args": {{...}}}}, {{"tool": "tool2", "args": {{...}}}}]}}
- Use these tool IDs: {tool_list_str}
- Common patterns:
  * "look around" → narrate_only with topic: "look around"
  * "move to X" → move with to: "X"
  * "sneak to X" → move with method: "sneak"
  * "attack X" → attack with target: "X"
  * "talk to X" → talk with target: "X"
  * "use item" → use_item with item_id
  * "drink potion" → use_item with method: "consume"

Required JSON format:
{{
  "is_compound": true/false,
  "actions": [
    {{"tool": "tool_id", "args": {{"key": "value"}}}},
    {{"tool": "tool_id", "args": {{"key": "value"}}}}
  ],
  "confidence": 0.85
}}"""

    def get_plan(
        self, state: GameState, utterance: Utterance, debug: bool = False
    ) -> PlannerResult:
        """
        Get a plan (tool selection) from the LLM based on game state and player input.

        Args:
            state: Current game state
            utterance: Player input
            debug: If True, print the prompt being sent to LLM

        Returns:
            PlannerResult with chosen tool, args, and confidence
        """
        try:
            # Get candidates from affordance filter
            candidates = get_tool_candidates(state, utterance)

            if not candidates:
                # Fallback if no candidates (shouldn't happen due to escape hatches)
                return PlannerResult(
                    chosen_tool="ask_clarifying",
                    args={
                        "question": "I'm not sure what you want to do. Could you clarify?"
                    },
                    confidence=0.1,
                    success=False,
                    error_message="No tool candidates available",
                )

            # Format user prompt with context and tool menu
            user_prompt = self._format_user_prompt(state, utterance, candidates)

            if debug:
                print("\n=== DEBUG: Prompt sent to LLM ===")
                print("SYSTEM PROMPT:")
                print(self.system_prompt)
                print("\nUSER PROMPT:")
                print(user_prompt)
                print("=== END DEBUG ===\n")

            # Call LLM with retry logic
            response = self._call_llm_with_retry(user_prompt)

            if debug:
                print(f"\n=== DEBUG: LLM Response ===")
                print(response)
                print("=== END DEBUG ===\n")

            # Parse and validate response
            return self._parse_llm_response(response, candidates)

        except Exception as e:
            logger.error(f"Error in planner: {e}")
            return self._create_fallback_result(str(e))

    def get_action_sequence(
        self, state: GameState, utterance: Utterance, debug: bool = False
    ) -> ActionSequenceResult:
        """
        Get an action sequence from player input, supporting compound commands.

        Args:
            state: Current game state
            utterance: Player input
            debug: If True, print the prompt being sent to LLM

        Returns:
            ActionSequenceResult with list of actions to execute sequentially
        """
        try:
            # First, check if this looks like a compound command
            if self._is_likely_compound(utterance.text):
                # Use LLM to parse compound command
                compound_result = self._parse_compound_command(utterance, debug)
                if compound_result.success and compound_result.is_compound:
                    return compound_result

            # Fall back to single action planning
            single_result = self.get_plan(state, utterance, debug)

            if single_result.success:
                return ActionSequenceResult(
                    actions=[
                        {"tool": single_result.chosen_tool, "args": single_result.args}
                    ],
                    confidence=single_result.confidence,
                    success=True,
                    is_compound=False,
                )
            else:
                return ActionSequenceResult(
                    actions=[],
                    confidence=0.1,
                    success=False,
                    error_message=single_result.error_message,
                    is_compound=False,
                )

        except Exception as e:
            logger.error(f"Error in action sequence planning: {e}")
            return ActionSequenceResult(
                actions=[],
                confidence=0.1,
                success=False,
                error_message=str(e),
                is_compound=False,
            )

    def _is_likely_compound(self, text: str) -> bool:
        """Quick heuristic check if text might contain compound actions."""
        text_lower = text.lower()
        # Only include the compound connectors that are actually used
        compound_indicators = [
            " and ",
            " then ",
            " after ",
            " before ",
        ]

        # Count potential action verbs
        action_count = 0
        action_verbs = [
            "look",
            "move",
            "go",
            "attack",
            "drink",
            "use",
            "cast",
            "talk",
            "say",
        ]
        for verb in action_verbs:
            if verb in text_lower:
                action_count += 1

        # If multiple action verbs or explicit connecting words
        has_connectors = any(
            indicator in text_lower for indicator in compound_indicators
        )
        return action_count > 1 or has_connectors

    def _parse_compound_command(
        self, utterance: Utterance, debug: bool = False
    ) -> ActionSequenceResult:
        """Use LLM to parse compound command into action sequence."""
        try:
            user_prompt = f'Player says: "{utterance.text}"\n\nBreak this into sequential actions if it contains multiple commands, or return single action if not.'

            if debug:
                print("\n=== DEBUG: Compound parsing prompt ===")
                print("SYSTEM PROMPT:")
                print(self.compound_system_prompt)
                print("\nUSER PROMPT:")
                print(user_prompt)
                print("=== END DEBUG ===\n")

            # Call LLM for compound parsing
            response = self._call_llm_with_retry(user_prompt, use_compound_prompt=True)

            if debug:
                print(f"\n=== DEBUG: Compound LLM Response ===")
                print(response)
                print("=== END DEBUG ===\n")

            # Parse response
            response_data = json.loads(response)

            # Validate and clean up the actions
            raw_actions = response_data.get("actions", [])
            validated_actions = self._validate_compound_actions(raw_actions)

            return ActionSequenceResult(
                actions=validated_actions,
                confidence=response_data.get("confidence", 0.7),
                success=True,
                is_compound=response_data.get("is_compound", False),
            )

        except Exception as e:
            logger.error(f"Compound parsing failed: {e}")
            return ActionSequenceResult(
                actions=[],
                confidence=0.1,
                success=False,
                error_message=str(e),
                is_compound=False,
            )

    def _validate_compound_actions(
        self, actions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and clean up compound actions from LLM."""
        # Get valid tool IDs
        valid_tools = {tool.id for tool in TOOL_CATALOG}

        validated = []
        max_steps = 3  # Cap at 3 steps

        for action in actions[:max_steps]:  # Limit steps
            if not isinstance(action, dict):
                continue

            tool_id = action.get("tool")
            if not tool_id or tool_id not in valid_tools:
                continue  # Filter invalid tool IDs

            args = action.get("args", {})
            if not isinstance(args, dict):
                args = {}  # Default missing/invalid args to empty dict

            # Skip if this exact action already exists (remove duplicates)
            action_key = (tool_id, tuple(sorted(args.items())))
            if any(
                (a.get("tool"), tuple(sorted(a.get("args", {}).items()))) == action_key
                for a in validated
            ):
                continue

            validated.append({"tool": tool_id, "args": args})

        return validated

    def _format_user_prompt(
        self, state: GameState, utterance: Utterance, candidates: List[ToolCandidate]
    ) -> str:
        """Format the user prompt with compact state slice and numbered tool menu."""

        # Compact state slice
        current_actor = (
            state.actors.get(state.current_actor) if state.current_actor else None
        )
        state_info = "Unknown state"

        if current_actor:
            current_zone = state.zones.get(current_actor.current_zone)
            zone_name = current_zone.name if current_zone else "Unknown Zone"

            visible_targets = []
            if hasattr(current_actor, "visible_actors"):
                pc_or_npc = cast(Union[PC, NPC], current_actor)
                for actor_id in pc_or_npc.visible_actors:
                    actor = state.actors.get(actor_id)
                    if actor:
                        visible_targets.append(actor.name)

            state_info = f"Actor: {current_actor.name}, Zone: {zone_name}, Visible: {', '.join(visible_targets) if visible_targets else 'None'}"

        # Numbered tool menu
        tool_menu = []
        for i, candidate in enumerate(candidates, 1):
            args_preview = {}
            # Show key arguments as preview
            if candidate.args_hint:
                # Pick the most important args to show
                important_keys = [
                    "actor",
                    "target",
                    "action",
                    "to",
                    "dc_hint",
                    "message",
                    "question",
                ]
                for key in important_keys:
                    if key in candidate.args_hint:
                        args_preview[key] = candidate.args_hint[key]

            tool_menu.append(f"{i}. {candidate.id}: {candidate.desc}")
            if args_preview:
                tool_menu.append(f"   Suggested args: {args_preview}")

        # Construct full user prompt
        user_prompt = f"""Player input: "{utterance.text}"

Game state: {state_info}

Available tools:
{chr(10).join(tool_menu)}

Choose the most appropriate tool and return JSON only."""

        return user_prompt

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _call_llm_with_retry(
        self, user_prompt: str, use_compound_prompt: bool = False
    ) -> str:
        """Call OpenAI API with retry logic."""
        try:
            # Choose appropriate system prompt
            system_prompt = (
                self.compound_system_prompt
                if use_compound_prompt
                else self.system_prompt
            )

            if self.model.startswith("gpt-5"):
                # Use Responses API for GPT-5 models
                api_params = {
                    "model": self.model,
                    "input": f"{system_prompt}\n\n{user_prompt}",
                    "reasoning": {"effort": "minimal"},  # Fast responses for planning
                    "text": {"verbosity": "low"},  # Concise outputs
                    "max_output_tokens": self.max_tokens,  # Set token limit for Responses API
                }

                response = self.client.responses.create(**api_params)
                content = response.output_text
            else:
                # Use Chat Completions API for non-GPT-5 models
                api_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": self.max_tokens,  # Correct parameter name for Chat Completions
                    "temperature": self.temperature,
                    "response_format": {"type": "json_object"},  # Force JSON response
                }

                response = self.client.chat.completions.create(**api_params)
                content = response.choices[0].message.content
            return content.strip() if content else ""

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def _parse_llm_response(
        self, response_text: str, candidates: List[ToolCandidate]
    ) -> PlannerResult:
        """Parse and validate the LLM's JSON response."""
        try:
            # Parse JSON
            response_data = json.loads(response_text)

            # Validate required fields
            if not all(
                key in response_data for key in ["chosen_tool", "args", "confidence"]
            ):
                raise ValueError("Missing required fields in response")

            chosen_tool = response_data["chosen_tool"]
            args = response_data["args"]
            confidence = float(response_data["confidence"])

            # Validate chosen tool is in candidates
            valid_tool_ids = [c.id for c in candidates]
            if chosen_tool not in valid_tool_ids:
                raise ValueError(
                    f"Invalid tool choice: {chosen_tool}. Valid options: {valid_tool_ids}"
                )

            # Get the candidate to merge with suggested args
            chosen_candidate = next(
                (c for c in candidates if c.id == chosen_tool), None
            )
            if chosen_candidate is None:
                raise ValueError(
                    f"Internal error: chosen tool {chosen_tool} not found in candidates"
                )

            # Merge LLM args with suggested args (LLM args take precedence)
            # Ensure args_hint exists before copying
            if chosen_candidate.args_hint is not None:
                final_args = chosen_candidate.args_hint.copy()
            else:
                final_args = {}
            final_args.update(args)

            # Clamp confidence to valid range
            confidence = max(0.0, min(1.0, confidence))

            return PlannerResult(
                chosen_tool=chosen_tool,
                args=final_args,
                confidence=confidence,
                success=True,
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return self._create_fallback_result(f"Invalid JSON response: {e}")

        except Exception as e:
            logger.error(f"Response validation error: {e}")
            return self._create_fallback_result(f"Response validation failed: {e}")

    def _create_fallback_result(self, error_message: str) -> PlannerResult:
        """Create a fallback result when LLM fails."""
        return PlannerResult(
            chosen_tool="ask_clarifying",
            args={"question": "I'm not sure what you want to do. Could you clarify?"},
            confidence=0.1,
            success=False,
            error_message=error_message,
        )


# Global planner instance (will be configured later)
_planner_instance: Optional[Planner] = None


def initialize_planner(api_key: str, model: Optional[str] = None) -> None:
    """Initialize the global planner instance."""
    global _planner_instance
    _planner_instance = Planner(api_key=api_key, model=model)


def get_plan(
    state: GameState, utterance: Utterance, debug: bool = False
) -> PlannerResult:
    """Convenience function to get a plan using the global planner instance."""
    if _planner_instance is None:
        raise RuntimeError("Planner not initialized. Call initialize_planner() first.")

    return _planner_instance.get_plan(state, utterance, debug)


def get_action_sequence(
    state: GameState, utterance: Utterance, debug: bool = False
) -> ActionSequenceResult:
    """Convenience function to get an action sequence using the global planner instance."""
    if _planner_instance is None:
        raise RuntimeError("Planner not initialized. Call initialize_planner() first.")

    return _planner_instance.get_action_sequence(state, utterance, debug)
