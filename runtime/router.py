"""
Runtime router for processing game turns.

This module handles the execution pipeline:
1. Take player command and current world state
2. Use planner to select appropriate tool
3. Execute tool via validator
4. Generate rich narration via LLM
5. Apply effects to world state
6. Return result for display

Integrates all the existing AID&D systems into a cohesive game loop.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List

from backend.router.game_state import GameState, Utterance
from backend.router.planner import get_plan, get_action_sequence, initialize_planner
from backend.router.staged_planner import get_staged_plan, initialize_staged_planner
from backend.router.validator import Validator, ToolResult
from backend.router.effects import apply_effects
from backend.router.outcome_resolver import resolve_outcome
from narration.generator import generate_narration, initialize_generator
import config


# Set up logging
logger = logging.getLogger(__name__)


class TurnResult:
    """Result of processing a game turn."""

    def __init__(
        self,
        success: bool,
        narration: str,
        tool_result: Optional[ToolResult] = None,
        tool_results: Optional[List[ToolResult]] = None,  # For action sequences
        error_message: Optional[str] = None,
        is_compound: bool = False,  # True if this was a compound action
    ):
        self.success = success
        self.narration = narration
        self.tool_result = tool_result  # For backward compatibility (single action)
        self.tool_results = tool_results or []  # For action sequences
        self.error_message = error_message
        self.is_compound = is_compound


class GameRouter:
    """Coordinates the game execution pipeline."""

    def __init__(self, use_staged_planner: bool = True):
        """Initialize the router with necessary components."""
        self.validator = Validator()
        self.use_staged_planner = use_staged_planner
        self._initialized = False

    def initialize(self) -> None:
        """Initialize LLM-based components."""
        if self._initialized:
            return

        try:
            # Initialize planner(s)
            if self.use_staged_planner:
                initialize_staged_planner(config.OPENAI_API_KEY, config.OPENAI_MODEL)
                logger.info("Initialized staged planner (3-stage architecture)")
            else:
                initialize_planner(config.OPENAI_API_KEY, config.OPENAI_MODEL)
                logger.info("Initialized monolithic planner (legacy)")

            # Initialize narration generator
            initialize_generator(config.OPENAI_API_KEY, config.OPENAI_MODEL)

            self._initialized = True
            logger.info("Game router initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize game router: {e}")
            raise RuntimeError(f"Router initialization failed: {e}")

    def process_turn(
        self,
        world: GameState,
        player_input: str,
        actor_id: Optional[str] = None,
        debug: bool = False,
    ) -> TurnResult:
        """
        Process a complete game turn, supporting both single actions and action sequences.

        Args:
            world: Current game state
            player_input: Raw player command text
            actor_id: Actor taking the action (defaults to current_actor)
            debug: Enable debug output

        Returns:
            TurnResult with narration and updated state
        """
        if not self._initialized:
            self.initialize()

        try:
            # Determine acting character
            if not actor_id:
                actor_id = world.current_actor

            if not actor_id:
                return TurnResult(
                    success=False,
                    narration="No active character found.",
                    error_message="Missing current_actor in game state",
                )

            # Create utterance object
            utterance = Utterance(text=player_input, actor_id=actor_id)

            if debug:
                logger.info(f"Processing turn for {actor_id}: '{player_input}'")

            # Step 1: Plan using appropriate planner
            if self.use_staged_planner:
                # Use 3-stage architecture
                staged_result = get_staged_plan(world, utterance, debug=debug)

                if not staged_result.success:
                    return TurnResult(
                        success=False,
                        narration="I'm not sure what you want to do. Could you clarify?",
                        error_message=staged_result.error_message,
                    )

                # Convert staged result to action sequence format
                action_sequence_data = []
                for tool_call in staged_result.tool_calls:
                    action_sequence_data.append(
                        {"tool": tool_call["tool"], "args": tool_call["args"]}
                    )

                is_compound = len(action_sequence_data) > 1

                if debug:
                    if is_compound:
                        logger.info(
                            f"Staged planner: compound action with {len(action_sequence_data)} steps"
                        )
                    else:
                        logger.info(
                            f"Staged planner: single action: {action_sequence_data[0]['tool']}"
                        )

            else:
                # Use legacy monolithic planner
                action_sequence = get_action_sequence(world, utterance, debug=debug)

                if not action_sequence.success:
                    return TurnResult(
                        success=False,
                        narration="I'm not sure what you want to do. Could you clarify?",
                        error_message=action_sequence.error_message,
                    )

                action_sequence_data = action_sequence.actions
                is_compound = action_sequence.is_compound

                if debug:
                    if is_compound:
                        logger.info(
                            f"Legacy planner: compound action with {len(action_sequence_data)} steps"
                        )
                    else:
                        logger.info(
                            f"Legacy planner: single action: {action_sequence_data[0]['tool']}"
                        )

            # Step 2: Execute action sequence
            all_tool_results = []
            all_narrations = []
            overall_success = True

            for i, action in enumerate(action_sequence_data):
                tool_id = action["tool"]
                args = action["args"]

                if debug:
                    logger.info(
                        f"Executing step {i+1}/{len(action_sequence_data)}: {tool_id}"
                    )

                # Execute this action
                tool_result = self.validator.validate_and_execute(
                    tool_id, args, world, utterance
                )

                # Apply outcome resolution to add consequences
                if tool_result.ok:
                    tool_result = resolve_outcome(tool_result, world)

                all_tool_results.append(tool_result)

                # Handle roll progression display if needed
                if (
                    tool_result.ok
                    and tool_result.narration_hint
                    and tool_result.narration_hint.get("roll_progression")
                ):

                    roll_narration = self._generate_roll_progression(tool_result)
                    all_narrations.append(roll_narration)
                else:
                    # Step 3: Generate narration for this action
                    step_narration = self._generate_narration(
                        tool_result, world, actor_id, debug
                    )
                    all_narrations.append(step_narration)

                if not tool_result.ok:
                    overall_success = False
                    if debug:
                        logger.warning(
                            f"Step {i+1} failed: {tool_result.error_message}"
                        )
                    # For failed steps, still try to continue if possible
                    # (unless it's a critical failure)
                    if tool_id in ["move", "attack"]:
                        # Critical actions - stop sequence on failure
                        break

                # Step 4: Apply effects immediately (each step sees previous step's results)
                if tool_result.ok and tool_result.effects:
                    try:
                        apply_effects(world, tool_result.effects)
                        if debug:
                            logger.info(
                                f"Applied {len(tool_result.effects)} effects from step {i+1}"
                            )
                    except Exception as e:
                        logger.error(f"Effect application failed for step {i+1}: {e}")
                        overall_success = False
                        all_narrations.append(f"Something went wrong with {tool_id}.")
                        break

            # Step 5: Combine narrations
            if len(all_narrations) == 1:
                combined_narration = all_narrations[0]
            else:
                # For multiple actions, combine with logical flow
                combined_narration = " ".join(all_narrations)

            # Step 6: Update turn counter
            if hasattr(world.scene, "round"):
                # Increment turn within round
                if hasattr(world.scene, "turn_index") and hasattr(
                    world.scene, "turn_order"
                ):
                    if world.scene.turn_order:
                        world.scene.turn_index = (world.scene.turn_index + 1) % len(
                            world.scene.turn_order
                        )
                        # If we've cycled through all actors, increment round
                        if world.scene.turn_index == 0:
                            world.scene.round += 1
                else:
                    # Simple round increment for single-player
                    world.scene.round += 1

            return TurnResult(
                success=overall_success,
                narration=combined_narration,
                tool_result=(
                    all_tool_results[0] if all_tool_results else None
                ),  # Backward compatibility
                tool_results=all_tool_results,
                error_message=None if overall_success else "One or more actions failed",
                is_compound=is_compound,
            )

        except Exception as e:
            logger.error(f"Turn processing failed: {e}")
            return TurnResult(
                success=False,
                narration="Something went wrong. Please try again.",
                error_message=str(e),
            )

    def _generate_roll_progression(self, tool_result: ToolResult) -> str:
        """Generate dramatic roll progression narration with consequences."""
        roll_setup = tool_result.narration_hint.get("roll_setup", {})
        dice = tool_result.narration_hint.get("dice", {})
        outcome = tool_result.narration_hint.get("outcome", "unknown")
        consequence = tool_result.narration_hint.get("consequence", "")

        # Build progression narrative
        progression_parts = []

        # Setup: What we're rolling and why
        if roll_setup.get("description"):
            progression_parts.append(f"{roll_setup['description']}.")

        # Pre-roll: Show what we're about to roll
        style_count = roll_setup.get("style_dice_count", 0)
        domain = roll_setup.get("domain", "d6")
        dc = roll_setup.get("dc", 10)

        if style_count > 0:
            dice_desc = f"d20 + {style_count}{domain}"
        else:
            dice_desc = "d20"

        progression_parts.append(f"Rolling {dice_desc} vs DC {dc}...")

        # Results: Show the actual rolls
        d20 = dice.get("d20", 0)
        style_dice = dice.get("style", [])
        total = dice.get("total", 0)

        if style_dice:
            style_text = " + ".join(map(str, style_dice))
            progression_parts.append(f"Rolled: {d20} + [{style_text}] = {total}")
        else:
            progression_parts.append(f"Rolled: {total}")

        # Outcome: Success or failure with margin
        margin = dice.get("margin", 0)
        if outcome == "crit_success":
            result_text = f"Critical Success! (beat DC by {margin})"
        elif outcome == "success":
            result_text = f"Success! (beat DC by {margin})"
        elif outcome == "partial":
            result_text = f"Partial success (missed DC by {abs(margin)})"
        else:
            result_text = f"Failure (missed DC by {abs(margin)})"

        progression_parts.append(result_text)

        # Add consequence if available
        if consequence:
            progression_parts.append(consequence)

        return " ".join(progression_parts)

    def _generate_narration(
        self,
        tool_result: ToolResult,
        world: GameState,
        actor_id: str,
        debug: bool = False,
    ) -> str:
        """Generate appropriate narration for the tool result."""

        # Tools that should use LLM narration for rich prose
        llm_narration_tools = {
            "narrate_only",  # Replace deterministic templates
            "attack",  # Combat flavor
            "move",  # Transition prose
            "talk",  # Dialogue narration
            "use_item",  # Magical/item flavor
        }

        # Use LLM narration for selected tools
        if tool_result.tool_id in llm_narration_tools:
            try:
                narration = generate_narration(tool_result, world, actor_id)
                if debug:
                    logger.info(f"Generated LLM narration for {tool_result.tool_id}")
                return narration
            except Exception as e:
                logger.error(f"LLM narration failed for {tool_result.tool_id}: {e}")
                # Fallback to original summary

        # For other tools, use the original narration hint
        if tool_result.narration_hint and isinstance(tool_result.narration_hint, dict):
            return tool_result.narration_hint.get("summary", "Something happens.")
        else:
            return "Something happens."


# Global router instance
_router_instance: Optional[GameRouter] = None


def get_router(use_staged_planner: bool = True) -> GameRouter:
    """Get the global game router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = GameRouter(use_staged_planner=use_staged_planner)
    return _router_instance


def process_turn(
    world: GameState,
    player_input: str,
    actor_id: Optional[str] = None,
    debug: bool = False,
    use_staged_planner: bool = True,
) -> TurnResult:
    """
    Convenience function to process a turn using the global router.

    Args:
        world: Current game state
        player_input: Raw player command text
        actor_id: Actor taking the action (defaults to current_actor)
        debug: Enable debug output
        use_staged_planner: Use 3-stage architecture (True) or legacy monolithic (False)

    Returns:
        TurnResult with narration and effects applied
    """
    router = get_router(use_staged_planner=use_staged_planner)
    return router.process_turn(world, player_input, actor_id, debug)
