"""
Planner Prompt (Step 3) - LLM-based tool selection from constrained menu.

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


class Planner:
    """LLM-based planner that selects tools from constrained menus."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 500,
        temperature: float = 0.1,
    ):
        """Initialize the planner with OpenAI configuration."""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

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
    def _call_llm_with_retry(self, user_prompt: str) -> str:
        """Call OpenAI API with retry logic."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Force JSON response
            )

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
            chosen_candidate = next(c for c in candidates if c.id == chosen_tool)

            # Merge LLM args with suggested args (LLM args take precedence)
            final_args = chosen_candidate.args_hint.copy()
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


def initialize_planner(api_key: str, model: str = "gpt-4o-mini") -> None:
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
