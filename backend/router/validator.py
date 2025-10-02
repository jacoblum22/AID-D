"""
Validator + Executor system (Step 4).

Handles:
- Schema validation with Pydantic
- Precondition checking
- Tool execution with standardized ToolResult
- Logging of all operations
"""

import json
import time
import uuid
import random
import logging
import os
from typing import Dict, Any, List, Optional, Union, cast
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass

from .game_state import GameState, Utterance, PC, NPC
from .tool_catalog import TOOL_CATALOG, get_tool_by_id
from .effects import apply_effects


# Set up logging
# TODO: Move logging configuration to application entry point to avoid conflicts
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standardized result envelope for all tool executions."""

    ok: bool
    tool_id: str
    args: Dict[str, Any]
    facts: Dict[str, Any]
    effects: List[Dict[str, Any]]
    narration_hint: Dict[str, Any]
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON logging."""
        return {
            "ok": self.ok,
            "tool_id": self.tool_id,
            "args": self.args,
            "facts": self.facts,
            "effects": self.effects,
            "narration_hint": self.narration_hint,
            "error_message": self.error_message,
        }


class Validator:
    """Handles validation pipeline: schema → preconditions → sanitization."""

    def __init__(self):
        self.turn_counter = 0
        self.social_outcomes = self._load_social_outcomes()

    def _load_social_outcomes(self) -> Dict[str, Any]:
        """Load social outcomes configuration from JSON file."""
        try:
            # Look for social_outcomes.json in parent directory of backend
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(os.path.dirname(current_dir))
            outcomes_path = os.path.join(parent_dir, "social_outcomes.json")

            with open(outcomes_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(
                "social_outcomes.json not found, using fallback hardcoded outcomes"
            )
            return self._get_fallback_outcomes()
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing social_outcomes.json: {e}")
            return self._get_fallback_outcomes()

    def _get_fallback_outcomes(self) -> Dict[str, Any]:
        """Fallback hardcoded outcomes if JSON file not available."""
        return {
            "intents": {
                "persuade": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [{"type": "mark", "tag": "favor", "value": 1}]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "persuade",
                                    "delta": 1,
                                    "max": 3,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "intimidate": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [{"type": "mark", "tag": "fear", "value": 1}]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "fear",
                                    "delta": 1,
                                    "max": 4,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "deceive": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [
                                {"type": "mark", "tag": "deception", "value": 1}
                            ]
                        },
                        "success": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "lie",
                                    "delta": 1,
                                    "max": 2,
                                }
                            ]
                        },
                        "partial": {"effects": [{"type": "guard", "delta": 1}]},
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "charm": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [{"type": "mark", "tag": "charm", "value": 1}]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "charm",
                                    "delta": 1,
                                    "max": 3,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "comfort": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [{"type": "mark", "tag": "comfort", "value": 1}]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "comfort",
                                    "delta": 1,
                                    "max": 3,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "request": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [{"type": "mark", "tag": "favor", "value": 1}]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "request",
                                    "delta": 1,
                                    "max": 3,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
                "distract": {
                    "outcomes": {
                        "crit_success": {
                            "effects": [
                                {"type": "mark", "tag": "distraction", "value": 1}
                            ]
                        },
                        "success": {
                            "effects": [{"type": "guard", "delta": -1, "min_value": 0}]
                        },
                        "partial": {
                            "effects": [
                                {
                                    "type": "clock",
                                    "id_suffix": "distraction",
                                    "delta": 1,
                                    "max": 3,
                                }
                            ]
                        },
                        "fail": {"effects": [{"type": "guard", "delta": 1}]},
                    }
                },
            }
        }

    def advance_turn(self, state: GameState) -> None:
        """
        Advance to the next turn and reset clarification counter.

        This should be called by the game engine when turns advance.
        """
        # Advance turn logic first (if needed for turn order)
        if state.scene.turn_order:
            state.scene.turn_index = (state.scene.turn_index + 1) % len(
                state.scene.turn_order
            )

            # Update current actor if turn order exists
            if state.scene.turn_index == 0:
                state.scene.round += 1

            state.current_actor = state.scene.turn_order[state.scene.turn_index]

        # Reset clarification counter for new turn
        state.scene.choice_count_this_turn = 0

        # Clear expired pending choices (check against the now-updated round)
        if (
            state.scene.pending_choice
            and state.scene.round
            > state.scene.pending_choice.get("expires_round", float("inf"))
        ):
            expired_choice_id = state.scene.pending_choice.get("id")
            logger.info(
                f"Clearing expired pending choice {expired_choice_id} at round {state.scene.round}"
            )
            state.scene.pending_choice = None

    def maybe_consume_pending_choice(
        self, state: GameState, utterance: Utterance
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        Check if there's a pending choice and if user input matches one of the options.

        Returns:
            tuple of (tool_id, args) if a choice was consumed, None otherwise
        """
        # Check if there's a pending choice
        pc = state.scene.pending_choice
        if not pc:
            return None

        # Check if choice has expired
        if state.scene.round > pc.get("expires_round", float("inf")):
            # Log the expiration for debugging
            logger.info(
                f"Pending choice {pc.get('id')} expired at round {state.scene.round}"
            )

            # Store expiration info before clearing
            expired_info = {
                "pending_choice_id": pc.get("id"),
                "expired": True,
                "reason": "turn_timeout",
                "expired_at_round": state.scene.round,
                "original_expires_round": pc.get("expires_round"),
            }

            # Clear expired choice
            state.scene.pending_choice = None

            # Could optionally return the expiration info for logging/debugging
            # For now, just return None to proceed with normal planning
            return None

        # Try to match user input to one of the options
        user_text = utterance.text.lower().strip()
        matched_option = None

        # Check for exact ID match first (e.g., "A", "B", "C")
        for option in pc["options"]:
            if user_text == option["id"].lower():
                matched_option = option
                break

        # If no ID match, try to match labels (fuzzy matching)
        if not matched_option:
            for option in pc["options"]:
                label_lower = option["label"].lower()
                # Simple fuzzy matching - check if key words from label appear in user text
                label_words = label_lower.split()
                if any(word in user_text for word in label_words if len(word) > 2):
                    matched_option = option
                    break

        # If no match found, return None (let normal planning proceed)
        if not matched_option:
            return None

        # Build the tool call arguments
        tool_id = matched_option["tool_id"]

        # Get base args from the tool's suggest_args if available
        from .tool_catalog import get_tool_by_id

        tool = get_tool_by_id(tool_id)
        base_args = {}
        if tool and tool.suggest_args:
            try:
                base_args = tool.suggest_args(state, utterance)
            except Exception as e:
                logger.warning(f"Error getting base args for {tool_id}: {e}")

        # Merge in the args_patch from the option
        args_patch = matched_option.get("args_patch", {})
        final_args = {**base_args, **args_patch}

        # Clear the pending choice since it was consumed
        state.scene.pending_choice = None

        # Log the choice consumption with replay metadata
        choice_metadata = {
            "pending_choice_id": pc["id"],
            "user_input": user_text,
            "matched_option": {
                "id": matched_option["id"],
                "label": matched_option["label"],
                "tool_id": matched_option["tool_id"],
            },
            "all_options_shown": [
                {"id": opt["id"], "label": opt["label"], "tool_id": opt["tool_id"]}
                for opt in pc["options"]
            ],
            "final_tool_call": {"tool_id": tool_id, "args": final_args},
        }

        logger.info(f"Consumed pending choice: {json.dumps(choice_metadata)}")

        return (tool_id, final_args)

    def process_turn_with_pending_choice_check(
        self,
        tool_id: str,
        raw_args: Dict[str, Any],
        state: GameState,
        utterance: Utterance,
        seed: Optional[int] = None,
    ) -> ToolResult:
        """
        Process a turn with automatic pending choice consumption.

        If a pending choice exists and matches the user input, execute that instead.
        Otherwise, proceed with the normal tool execution pipeline.
        """
        # First check if there's a pending choice that matches user input
        pending_choice_result = self.maybe_consume_pending_choice(state, utterance)

        if pending_choice_result:
            # User input matched a pending choice option
            consumed_tool_id, consumed_args = pending_choice_result
            return self.validate_and_execute(
                consumed_tool_id, consumed_args, state, utterance, seed
            )
        else:
            # No pending choice match, proceed with normal tool execution
            return self.validate_and_execute(tool_id, raw_args, state, utterance, seed)

    def validate_and_execute(
        self,
        tool_id: str,
        raw_args: Dict[str, Any],
        state: GameState,
        utterance: Utterance,
        seed: Optional[int] = None,
    ) -> ToolResult:
        """
        Run full validation pipeline and execute tool.

        Pipeline:
        1. Schema validation
        2. Non-destructive sanitization
        3. Precondition checking
        4. Tool execution
        5. Logging
        """

        # Generate turn ID and seed
        self.turn_counter += 1
        turn_id = f"t_{self.turn_counter:04d}"
        if seed is None:
            seed = int(time.time() * 1000) % 10000

        # Start logging
        log_entry = {
            "ts": int(time.time()),
            "turn_id": turn_id,
            "player_text": utterance.text,
            "seed": seed,
            "planner": {"tool": tool_id, "args_raw": raw_args},
        }

        try:
            # Step 1: Get tool definition
            tool = get_tool_by_id(tool_id)
            if not tool:
                return self._create_error_result(
                    tool_id, raw_args, f"Unknown tool: {tool_id}", log_entry
                )

            # Step 2: Schema validation
            schema_ok = False  # Initialize before try block
            try:
                validated_args = tool.args_schema(**raw_args)
                schema_ok = True
                sanitized_args = validated_args.dict()
            except ValidationError as e:
                return self._create_error_result(
                    tool_id, raw_args, f"Schema validation failed: {e}", log_entry
                )

            # Step 3: Non-destructive sanitization
            sanitized_args = self._sanitize_args(sanitized_args)

            # Step 4: Precondition check
            try:
                precond_ok = tool.precond(state, utterance)
            except Exception as e:
                precond_ok = False
                return self._create_error_result(
                    tool_id, raw_args, f"Precondition check failed: {e}", log_entry
                )

            if not precond_ok:
                return self._create_error_result(
                    tool_id, raw_args, "Preconditions not satisfied", log_entry
                )

            # Update log with validation results
            log_entry["validation"] = {
                "schema_ok": schema_ok,
                "preconds_ok": precond_ok,
            }

            # Step 5: Execute tool
            result = self._execute_tool(tool_id, sanitized_args, state, utterance, seed)

            # Step 6: Apply effects to state
            if result.ok and result.effects:
                try:
                    apply_effects(state, result.effects)
                except Exception as e:
                    return self._create_error_result(
                        tool_id,
                        sanitized_args,
                        f"Effect application failed: {e}",
                        log_entry,
                    )

            # Final logging
            log_entry["result"] = result.to_dict()
            log_entry["state"] = self._get_state_summary(state)

            logger.info(json.dumps(log_entry))

            return result

        except Exception as e:
            return self._create_error_result(
                tool_id, raw_args, f"Unexpected error: {e}", log_entry
            )

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Non-destructive sanitization without guessing intent."""
        sanitized = args.copy()

        # Trim strings
        for key, value in sanitized.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()

        # Lowercase domain
        if "domain" in sanitized and isinstance(sanitized["domain"], str):
            sanitized["domain"] = sanitized["domain"].lower()

        # Clamp style values
        if "style" in sanitized and isinstance(sanitized["style"], (int, float)):
            sanitized["style"] = max(0, min(3, int(sanitized["style"])))

        # Clamp DC hints
        if "dc_hint" in sanitized and isinstance(sanitized["dc_hint"], (int, float)):
            sanitized["dc_hint"] = max(5, min(25, int(sanitized["dc_hint"])))

        return sanitized

    def _execute_tool(
        self,
        tool_id: str,
        args: Dict[str, Any],
        state: GameState,
        utterance: Utterance,
        seed: int,
    ) -> ToolResult:
        """Execute the specified tool with validated arguments."""

        # Route to appropriate executor
        if tool_id == "ask_roll":
            return self._execute_ask_roll(args, state, utterance, seed)
        elif tool_id == "move":
            return self._execute_move(args, state, utterance, seed)
        elif tool_id == "talk":
            return self._execute_talk(args, state, utterance, seed)
        elif tool_id == "attack":
            return self._execute_attack(args, state, utterance, seed)
        elif tool_id == "use_item":
            return self._execute_use_item(args, state, utterance, seed)
        elif tool_id == "get_info":
            return self._execute_get_info(args, state, utterance, seed)
        elif tool_id == "narrate_only":
            return self._execute_narrate_only(args, state, utterance, seed)
        elif tool_id == "apply_effects":
            return self._execute_apply_effects(args, state, utterance, seed)
        elif tool_id == "ask_clarifying":
            return self._execute_ask_clarifying(args, state, utterance, seed)
        else:
            return ToolResult(
                ok=False,
                tool_id=tool_id,
                args=args,
                facts={},
                effects=[],
                narration_hint={},
                error_message=f"No executor implemented for tool: {tool_id}",
            )

    def _execute_ask_roll(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute ask_roll tool - Style+Domain dice mechanics."""
        random.seed(seed)

        # Extract arguments
        actor = args.get("actor")
        action = args.get("action", "custom")
        target = args.get("target")
        zone_target = args.get("zone_target")
        style = args.get("style", 1)
        domain = args.get("domain", "d6")
        dc_hint = args.get("dc_hint", 12)
        adv_style_delta = args.get("adv_style_delta", 0)

        # Validate zone_target is adjacent to current zone if provided
        if zone_target and actor:
            current_actor = state.actors.get(actor)
            if current_actor:
                current_zone = state.zones.get(current_actor.current_zone)
                if (
                    current_zone
                    and zone_target != current_actor.current_zone
                    and zone_target not in current_zone.adjacent_zones
                ):
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"You can't reach {zone_target} from here. Where would you like to go instead?"
                        },
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": "Asked for clarification due to invalid target zone",
                            "tone_tags": ["helpful"],
                            "salient_entities": [],
                        },
                        error_message=f"Zone target '{zone_target}' is not adjacent to current zone '{current_actor.current_zone}'",
                    )

        # Derive DC from scene tags if dc_hint wasn't provided
        if dc_hint == 12:  # Default value, derive from scene
            dc = self._derive_dc(action, state.scene)
        else:
            dc = dc_hint

        # Apply advantage/disadvantage to style dice count
        effective_style = max(0, min(3, style + adv_style_delta))

        # Roll dice: d20 + sum(effective_style × domain dice)
        d20_roll = random.randint(1, 20)

        # Parse domain die size with defensive error handling
        try:
            if not domain.startswith("d") or not domain[1:].isdigit():
                raise ValueError(f"Invalid domain format: {domain}")
            domain_size = int(domain[1:])  # "d6" -> 6
        except (ValueError, IndexError) as e:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"I don't understand the dice format '{domain}'. Please use format like 'd6' or 'd20'."
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to invalid dice format",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Invalid domain format: {domain}",
            )
        style_dice = [random.randint(1, domain_size) for _ in range(effective_style)]
        style_sum = sum(style_dice)
        total = d20_roll + style_sum

        # Calculate margin and determine outcome
        margin = total - dc
        if d20_roll == 20 or margin >= 5:
            outcome = "crit_success"
        elif margin >= 0:
            outcome = "success"
        elif margin >= -3:
            outcome = "partial"
        else:
            outcome = "fail"

        # Generate effects based on outcome and action
        effects = self._generate_ask_roll_effects(
            outcome, action, actor, target, zone_target, state
        )

        # Create detailed narration hint
        narration_hint = {
            "summary": f"{action.capitalize()} {self._outcome_to_text(outcome)}",
            "dice": {
                "d20": d20_roll,
                "style": style_dice,
                "style_sum": style_sum,
                "total": total,
                "dc": dc,
                "margin": margin,
                "effective_style": effective_style,
            },
            "outcome": outcome,
            "tone_tags": self._get_tone_tags(outcome, action),
            "salient_entities": [actor] + ([target] if target else []),
        }

        return ToolResult(
            ok=True,
            tool_id="ask_roll",
            args=args,
            facts={
                "outcome": outcome,
                "margin": margin,
                "total": total,
                "dc": dc,
                "style_dice": style_dice,
            },
            effects=effects,
            narration_hint=narration_hint,
        )

    def _derive_dc(self, action: str, scene) -> int:
        """Derive DC from scene tags based on action type."""
        base_dc = scene.base_dc

        # DC adjustment tables
        SNEAK_ADJUST = {
            ("alert", "sleepy"): -2,
            ("alert", "wary"): +2,
            ("alert", "alarmed"): +3,
            ("lighting", "bright"): +2,
            ("lighting", "dim"): -1,
            ("noise", "loud"): -1,
            ("noise", "quiet"): +1,
            ("cover", "good"): -2,
            ("cover", "none"): +2,
        }

        PERSUADE_ADJUST = {
            ("alert", "sleepy"): -1,
            ("alert", "wary"): +1,
            ("alert", "alarmed"): +2,
        }

        # Choose adjustment table based on action
        if action == "sneak":
            adjust_table = SNEAK_ADJUST
        elif action == "persuade":
            adjust_table = PERSUADE_ADJUST
        else:
            adjust_table = {}  # No adjustments for other actions

        # Apply adjustments
        adjusted_dc = base_dc
        for tag_key, tag_value in scene.tags.items():
            adjustment = adjust_table.get((tag_key, tag_value), 0)
            adjusted_dc += adjustment

        # Clamp to reasonable range
        return max(8, min(20, adjusted_dc))

    def _generate_ask_roll_effects(
        self,
        outcome: str,
        action: str,
        actor: Optional[str],
        target: Optional[str],
        zone_target: Optional[str],
        state: GameState,
    ) -> List[Dict[str, Any]]:
        """Generate effect atoms based on ask_roll outcome."""
        effects = []

        if not actor:  # Safety check
            return effects

        if outcome == "crit_success":
            # Apply intended effect + bonus
            if action == "sneak" and zone_target:
                effects.append({"type": "position", "target": actor, "to": zone_target})
                # Reduce alarm clock if it exists
                effects.append({"type": "clock", "id": "scene.alarm", "delta": -1})
            elif action == "persuade" and target:
                effects.append(
                    {
                        "type": "mark",
                        "target": target,
                        "style_bonus": 2,
                        "consumes": True,
                    }
                )

        elif outcome == "success":
            # Apply intended effect
            if action == "sneak" and zone_target:
                effects.append({"type": "position", "target": actor, "to": zone_target})
            elif action == "persuade" and target:
                effects.append(
                    {
                        "type": "mark",
                        "target": target,
                        "style_bonus": 1,
                        "consumes": True,
                    }
                )
            elif action == "athletics" and zone_target:
                effects.append({"type": "position", "target": actor, "to": zone_target})

        elif outcome == "partial":
            # No position change, minor consequence
            effects.append({"type": "clock", "id": "scene.alarm", "delta": 1})

        elif outcome in ["fail", "crit_fail"]:
            # Failure consequences
            effects.append(
                {
                    "type": "clock",
                    "id": "scene.alarm",
                    "delta": 3 if outcome == "crit_fail" else 2,
                }
            )

        return effects

    def _outcome_to_text(self, outcome: str) -> str:
        """Convert outcome to readable text."""
        return {
            "crit_success": "succeeded brilliantly",
            "success": "succeeded",
            "partial": "partially succeeded",
            "fail": "failed",
            "crit_fail": "failed catastrophically",
        }.get(outcome, "had an uncertain outcome")

    def _get_tone_tags(self, outcome: str, action: str) -> List[str]:
        """Get appropriate tone tags for narration."""
        base_tags = [action]

        if outcome in ["crit_success", "success"]:
            base_tags.extend(["confident", "smooth"])
        elif outcome == "partial":
            base_tags.extend(["tense", "close"])
        else:
            base_tags.extend(["tense", "risky"])

        return base_tags

    def _execute_move(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute move tool - comprehensive zone transitions with validation."""
        actor = args.get("actor")
        to_zone = args.get("to")
        method = args.get("method", "walk")
        cost = args.get("cost")

        # Validation: Actor exists and can act
        if not actor or actor not in state.entities:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "Who should move? I don't see that character."},
                facts={},
                effects=[],
                narration_hint={},
            )

        actor_entity = state.entities[actor]
        if actor_entity.type not in ("pc", "npc"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "That entity cannot move."},
                facts={},
                effects=[],
                narration_hint={},
            )

        # Check if actor can act (alive) - only check HP for PC/NPC entities
        if actor_entity.type in ("pc", "npc"):
            # Type cast for proper type checking
            from .game_state import PC, NPC

            living_entity = cast(Union[PC, NPC], actor_entity)

            if hasattr(living_entity, "hp") and living_entity.hp.current <= 0:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": f"{living_entity.name} is unconscious and cannot move."
                    },
                    facts={
                        "cause": "actor_state",
                        "actor_state": "unconscious",
                        "actor": actor,
                    },
                    effects=[],
                    narration_hint={},
                )

        current_zone_id = actor_entity.current_zone
        current_zone = state.zones.get(current_zone_id)

        if not current_zone:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "Something is wrong with the current location."},
                facts={},
                effects=[],
                narration_hint={},
            )

        # Validation: Target zone exists
        if not to_zone or to_zone not in state.zones:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": f"I don't know where '{to_zone}' is."},
                facts={},
                effects=[],
                narration_hint={},
            )

        target_zone = state.zones[to_zone]

        # Validation: Same-zone move
        if to_zone == current_zone_id:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"You're already in {current_zone.name}. Where would you like to go?"
                },
                facts={"cause": "same_zone", "current_zone": current_zone_id},
                effects=[],
                narration_hint={},
            )

        # Validation: Target zone is adjacent
        if to_zone not in current_zone.adjacent_zones:
            valid_exits = [
                state.zones[zone_id].name
                for zone_id in current_zone.adjacent_zones
                if zone_id in state.zones
            ]
            exits_text = ", ".join(valid_exits) if valid_exits else "nowhere"
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"You can't move there from {current_zone.name}. Valid exits: {exits_text}."
                },
                facts={"cause": "invalid", "valid_exits": valid_exits},
                effects=[],
                narration_hint={},
            )

        # Validation: Path not blocked
        blocked_exits = getattr(current_zone, "blocked_exits", [])
        if to_zone in blocked_exits:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": f"The path to {target_zone.name} is blocked."},
                facts={"cause": "blocked", "destination": to_zone},
                effects=[],
                narration_hint={},
            )

        # Special handling for sneak method
        if method == "sneak":
            # For now, we'll handle sneak as a simple move with a tag
            # In the future, this could defer to ask_roll for stealth checks
            # Return ask_roll deferred result if scene has high alert level
            if hasattr(state, "scene") and hasattr(state.scene, "tags"):
                alert_level = state.scene.tags.get("alert_level", 0)
                if isinstance(alert_level, int) and alert_level > 1:
                    return ToolResult(
                        ok=False,
                        tool_id="ask_roll",
                        args={
                            "actor": actor,
                            "action": "sneak",
                            "zone_target": to_zone,
                            "style": 1,
                            "domain": "d6",
                            "dc_hint": 10 + alert_level,
                            "context": f"Moving stealthily to {target_zone.name}",
                        },
                        facts={},
                        effects=[],
                        narration_hint={},
                    )

        # Generate effects
        effects = []

        # Always emit position effect
        effects.append(
            {
                "type": "position",
                "target": actor,
                "from": current_zone_id,
                "to": to_zone,
                "source": actor,
                "cause": "move",
            }
        )

        # Method-specific effects
        facts = {
            "from_zone": current_zone_id,
            "to_zone": to_zone,
            "destination": to_zone,  # For test compatibility
            "method": method,
            "actor": actor,
            "cost": cost,  # Track cost even if not enforced
        }

        tone_tags = ["transition", "movement"]

        if method == "run":
            # Add noise tag/clock effect for running
            effects.append(
                {
                    "type": "tag",
                    "target": "scene",
                    "add": {"noise": "loud"},
                    "source": actor,
                    "cause": "running",
                }
            )
            # Generate generic noise event for subsystems
            effects.append(
                {
                    "type": "noise",
                    "zone": to_zone,
                    "intensity": "loud",
                    "source": actor,
                    "cause": "running",
                }
            )
            # Advance alarm clock if it exists
            if "alarm" in state.clocks:
                effects.append(
                    {
                        "type": "clock",
                        "id": "alarm",  # Use "id" not "target" for clock effects
                        "delta": 1,
                        "source": actor,
                        "cause": "noisy_movement",
                    }
                )
            tone_tags.append("urgent")
            facts["noise_generated"] = True

        elif method == "sneak":
            # Add sneak intent tag (not result - that comes from successful rolls)
            effects.append(
                {
                    "type": "tag",
                    "target": actor,
                    "add": {"sneak_intent": True},
                    "source": actor,
                    "cause": "stealth_movement",
                }
            )
            tone_tags.append("stealthy")
            facts["sneak_intent"] = True

        # Generate narration hint
        method_verb = {"walk": "walks", "run": "runs", "sneak": "sneaks"}.get(
            method, "moves"
        )

        # Build zone names mapping for narrator
        zone_names = {
            current_zone_id: current_zone.name,
            to_zone: target_zone.name,
        }

        narration_hint = {
            "summary": f"{actor_entity.name} {method_verb} from {current_zone.name} to {target_zone.name}.",
            "movement": {
                "from": current_zone_id,
                "to": to_zone,
                "method": method,
                "movement_verb": method_verb,
                "from_name": current_zone.name,
                "to_name": target_zone.name,
            },
            "tone_tags": tone_tags,
            "salient_entities": [actor],
            "mentioned_zones": [current_zone_id, to_zone],
            "zone_names": zone_names,
            "camera": "tracking",
        }

        return ToolResult(
            ok=True,
            tool_id="move",
            args=args,
            facts=facts,
            effects=effects,
            narration_hint=narration_hint,
        )

    def _execute_talk(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute talk tool - social interactions with Style+Domain mechanics."""
        import random

        random.seed(seed)

        # Extract arguments - handle both single target and multiple targets
        actor = args.get("actor")
        target_input = args.get("target")

        # Normalize target to list for consistent processing
        if isinstance(target_input, str):
            targets = [target_input]
        elif isinstance(target_input, list):
            targets = target_input
        else:
            targets = []

        # Check for empty targets early to prevent IndexError
        if not targets:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": "Who are you trying to talk to?",
                    "reason": "no_target",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look around first",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing target",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message="No target specified for talk action",
            )

        intent = args.get("intent", "persuade")
        style = args.get("style", 1)
        domain = args.get("domain", "d6")
        dc_hint = args.get("dc_hint", 12)
        adv_style_delta = args.get("adv_style_delta", 0)
        topic = args.get("topic")

        # Validate entities exist
        if actor not in state.entities:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"Actor '{actor}' not found. Who is trying to talk?",
                    "reason": "invalid_target",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look around first",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing actor",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' not found",
            )

        # Validate all targets exist
        missing_targets = [t for t in targets if t not in state.entities]
        if missing_targets:
            target_list = ", ".join(missing_targets)
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"Target(s) '{target_list}' not found. Who are you trying to talk to?",
                    "reason": "invalid_target",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look around first",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing target(s)",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Target(s) '{target_list}' not found",
            )

        # Get primary target for DC calculation (first in list)
        primary_target = targets[0]
        target_entities = [state.entities[t] for t in targets]

        actor_entity = state.entities[actor]
        primary_target_entity = target_entities[0]

        # Validate actor is a creature that can talk
        if actor_entity.type not in ("pc", "npc"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"Only characters can talk to others.",
                    "reason": "invalid_target",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look for someone else",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to non-character actor",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' is not a character",
            )

        # Type cast for safe access to actor attributes
        actor_creature = cast(Union[PC, NPC], actor_entity)

        # Validate actor can act (has positive HP)
        if actor_creature.hp.current <= 0:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"{actor_creature.name} is unconscious and cannot talk.",
                    "reason": "not_your_turn",
                    "options": [
                        {
                            "id": "A",
                            "label": "Get more information",
                            "tool_id": "get_info",
                            "args_patch": {
                                "query": "current situation",
                                "scope": "current_zone",
                            },
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to unconscious actor",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' is unconscious",
            )

        # Validate target is social_receptive (PC/NPC entities are by default)
        if primary_target_entity.type not in ("pc", "npc"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"You can't have a meaningful conversation with {primary_target_entity.name}.",
                    "reason": "invalid_target",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look for someone else to talk to",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to non-social target",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Target '{primary_target}' is not social_receptive",
            )

        # Type cast for safe access to target attributes
        target_creature = cast(Union[PC, NPC], primary_target_entity)

        # Validate target is visible (in same zone) - check primary target
        if primary_target not in actor_creature.visible_actors:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"You can't see {target_creature.name} to talk to them.",
                    "reason": "not_adjacent",
                    "options": [
                        {
                            "id": "A",
                            "label": "Look around for targets",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to invisible target",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Target '{primary_target}' is not visible to speaker '{actor}'",
            )

        # Calculate effective style
        effective_style = max(0, min(3, style + adv_style_delta))

        # Parse domain die size
        try:
            if not domain.startswith("d") or not domain[1:].isdigit():
                raise ValueError(f"Invalid domain format: {domain}")
            domain_size = int(domain[1:])  # "d6" -> 6
        except (ValueError, IndexError):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"I don't understand the dice format '{domain}'. Please use format like 'd6' or 'd8'.",
                    "reason": "missing_arg",
                    "options": [
                        {
                            "id": "A",
                            "label": "Try something else",
                            "tool_id": "narrate_only",
                            "args_patch": {"topic": "look around"},
                        }
                    ],
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to invalid dice format",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Invalid domain format: {domain}",
            )

        # Roll dice: d20 + sum(effective_style × domain dice)
        d20_roll = random.randint(1, 20)
        style_dice = [random.randint(1, domain_size) for _ in range(effective_style)]
        style_sum = sum(style_dice)
        total = d20_roll + style_sum

        # Calculate margin and determine outcome
        margin = total - dc_hint
        if d20_roll == 20 or margin >= 5:
            outcome = "crit_success"
        elif margin >= 0:
            outcome = "success"
        elif margin >= -3:
            outcome = "partial"
        else:
            outcome = "fail"

        # Generate effects based on intent and outcome - apply to all targets
        effects = []
        for target_id in targets:
            target_effects = self._generate_talk_effects(
                intent, outcome, actor, target_id, state
            )
            effects.extend(target_effects)

        # Create detailed narration hint
        actor_name = actor_creature.name

        # Handle multiple targets in narration
        if len(targets) == 1:
            target_name = target_creature.name
            summary = f"{actor_name} tries to {intent} {target_name}"
        else:
            target_names = [state.entities[t].name for t in targets]
            if len(target_names) == 2:
                target_list = f"{target_names[0]} and {target_names[1]}"
            else:
                target_list = ", ".join(target_names[:-1]) + f", and {target_names[-1]}"
            summary = f"{actor_name} tries to {intent} {target_list}"

        if topic:
            summary += f" about {topic}"

        # Calculate audience disposition before/after for narration enrichment
        audience_disposition_before = {}
        audience_disposition_after = {}
        effects_summary = []

        for target_id in targets:
            target_entity = state.entities.get(target_id)
            if target_entity and target_entity.type in ("pc", "npc"):
                target_creature = cast(Union[PC, NPC], target_entity)

                # Record disposition before
                disposition_before = {
                    "guard": target_creature.guard,
                    "marks": getattr(target_creature, "marks", {}),
                    "attitude": "neutral",  # Could be enhanced with more sophisticated calculation
                }
                audience_disposition_before[target_id] = disposition_before

                # Calculate disposition after effects (simulate application)
                simulated_guard = target_creature.guard
                simulated_marks = getattr(target_creature, "marks", {}).copy()

                # Simulate effect application to predict disposition after
                target_effects = self._generate_talk_effects(
                    intent, outcome, actor, target_id, state
                )
                for effect in target_effects:
                    if effect["type"] == "guard":
                        simulated_guard = effect["value"]
                        effects_summary.append(
                            f"{target_entity.name}: guard {target_creature.guard} → {simulated_guard}"
                        )
                    elif effect["type"] == "mark":
                        tag = effect["tag"]
                        source = effect["source"]
                        mark_key = f"{source}.{tag}"
                        simulated_marks[mark_key] = {
                            "tag": tag,
                            "source": source,
                            "value": effect.get("value", 1),
                        }
                        effects_summary.append(
                            f"{target_entity.name}: gained {tag} mark"
                        )
                    elif effect["type"] == "clock":
                        clock_id = effect["id"]
                        delta = effect["delta"]
                        effects_summary.append(f"Clock {clock_id}: +{delta}")

                # Record disposition after
                disposition_after = {
                    "guard": simulated_guard,
                    "marks": simulated_marks,
                    "attitude": (
                        "positive"
                        if simulated_guard < target_creature.guard
                        else (
                            "negative"
                            if simulated_guard > target_creature.guard
                            else "neutral"
                        )
                    ),
                }
                audience_disposition_after[target_id] = disposition_after

        narration_hint = {
            "summary": summary,
            "dice": {
                "d20": d20_roll,
                "style": style_dice,
                "style_sum": style_sum,
                "total": total,
                "dc": dc_hint,
                "margin": margin,
                "effective_style": effective_style,
            },
            "outcome": outcome,
            "tone_tags": ["social", intent]
            + (["critical"] if outcome == "crit_success" else []),
            "mentioned_entities": [actor] + targets,
            "intent": intent,
            "topic": topic,
            "sentences_max": 3,
            # Enhanced narration context
            "audience_disposition_before": audience_disposition_before,
            "audience_disposition_after": audience_disposition_after,
            "effects_summary": effects_summary,
        }

        return ToolResult(
            ok=True,
            tool_id="talk",
            args=args,
            facts={
                "outcome": outcome,
                "margin": margin,
                "total": total,
                "dc": dc_hint,
                "intent": intent,
                "topic": topic,
            },
            effects=effects,
            narration_hint=narration_hint,
        )

    def _generate_talk_effects(
        self, intent: str, outcome: str, actor: str, target: str, state: GameState
    ) -> List[Dict[str, Any]]:
        """Generate effects based on talk intent and outcome using data-driven approach."""
        effects = []

        # Get target entity to check current guard value
        target_entity = state.entities.get(target)
        current_guard = 0
        if target_entity and target_entity.type in ("pc", "npc"):
            target_creature = cast(Union[PC, NPC], target_entity)
            current_guard = target_creature.guard

        # Look up intent and outcome in social outcomes configuration
        intent_config = self.social_outcomes.get("intents", {}).get(intent)
        if not intent_config:
            logger.warning(f"Unknown intent '{intent}', using fallback")
            return []

        outcome_config = intent_config.get("outcomes", {}).get(outcome)
        if not outcome_config:
            logger.warning(
                f"Unknown outcome '{outcome}' for intent '{intent}', using fallback"
            )
            return []

        # Process each effect template from configuration
        for effect_template in outcome_config.get("effects", []):
            effect = effect_template.copy()

            # Add standard fields
            effect["target"] = target
            effect["source"] = actor
            effect["cause"] = intent

            # Handle special effect type processing
            if effect["type"] == "guard":
                # Calculate new guard value with deltas
                delta = effect.get("delta", 0)
                min_value = effect.get("min_value", 0)
                new_guard = max(min_value, current_guard + delta)
                effect["value"] = new_guard

            elif effect["type"] == "clock":
                # Build full clock ID from suffix
                if "id_suffix" in effect:
                    effect["id"] = f"{target}.{effect['id_suffix']}"
                    del effect["id_suffix"]

            elif effect["type"] == "mark":
                # Mark effects are already properly structured
                pass

            effects.append(effect)

        return effects

    def _execute_attack(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute attack tool - combat mechanics with Style+Domain rolling."""
        import random

        random.seed(seed)

        # Extract arguments
        actor = args.get("actor")
        target = args.get("target")
        style = args.get("style", 1)
        domain = args.get("domain", "d6")
        dc_hint = args.get("dc_hint", 12)
        adv_style_delta = args.get("adv_style_delta", 0)
        weapon = args.get("weapon", "basic_melee")
        damage_expr = args.get("damage_expr", "1d6")
        consume_mark = args.get("consume_mark", True)

        # Validate entities exist
        if actor not in state.entities:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "I can't find the attacker. Who is attacking?"},
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing attacker",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' not found in entities",
            )

        if target not in state.entities:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "I can't find the target. Who are you attacking?"},
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing target",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Target '{target}' not found in entities",
            )

        attacker = state.entities[actor]
        target_entity = state.entities[target]

        # Validate target is attackable (has HP)
        if target_entity.type not in ("pc", "npc"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": "You can't attack that. Try attacking a living creature instead."
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to invalid target type",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Target '{target}' is not attackable (type: {target_entity.type})",
            )

        # Validate visibility
        if attacker.type in ("pc", "npc") and hasattr(attacker, "visible_actors"):
            attacker_creature = cast(Union[PC, NPC], attacker)
            if target not in attacker_creature.visible_actors:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={"question": "You can't see your target. Look around first."},
                    facts={},
                    effects=[],
                    narration_hint={
                        "summary": "Asked for clarification due to invisible target",
                        "tone_tags": ["helpful"],
                        "salient_entities": [],
                    },
                    error_message=f"Target '{target}' is not visible to attacker '{actor}'",
                )

        # Check if target has mark and calculate effective style
        target_has_mark = False
        if target_entity.type in ("pc", "npc"):
            target_creature = cast(Union[PC, NPC], target_entity)
            target_has_mark = (
                hasattr(target_creature, "style_bonus")
                and target_creature.style_bonus > 0
            )

        effective_style = max(0, min(3, style + adv_style_delta))

        # Add mark bonus if consuming mark
        mark_consumed = False
        if consume_mark and target_has_mark:
            effective_style = min(3, effective_style + 1)  # Cap at 3
            mark_consumed = True

        # Parse domain die size
        try:
            if not domain.startswith("d") or not domain[1:].isdigit():
                raise ValueError(f"Invalid domain format: {domain}")
            domain_size = int(domain[1:])  # "d6" -> 6
        except (ValueError, IndexError):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"I don't understand the dice format '{domain}'. Please use format like 'd6' or 'd8'."
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to invalid dice format",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Invalid domain format: {domain}",
            )

        # Roll attack: d20 + sum(effective_style × domain dice)
        d20_roll = random.randint(1, 20)
        style_dice = [random.randint(1, domain_size) for _ in range(effective_style)]
        style_sum = sum(style_dice)
        total = d20_roll + style_sum

        # Calculate margin and determine outcome
        margin = total - dc_hint
        if d20_roll == 20 or margin >= 5:
            outcome = "crit_success"
        elif margin >= 0:
            outcome = "success"
        elif margin >= -3:
            outcome = "partial"
        else:
            outcome = "fail"

        # Calculate damage based on outcome
        damage = 0
        raw_damage = 0
        damage_dice = []

        if outcome != "fail":
            # Parse damage expression and roll dice
            damage_dice, raw_damage = self._roll_damage(
                damage_expr, outcome == "crit_success", random
            )

            # Handle partial success (half damage)
            if outcome == "partial":
                damage = raw_damage // 2
            else:
                damage = raw_damage

        # Generate effects
        effects = []

        # Apply damage if any
        if damage > 0:
            effects.append(
                {
                    "type": "hp",
                    "target": target,
                    "delta": -damage,
                    "source": actor,
                    "cause": "attack",
                }
            )

        # Remove mark if consumed
        if mark_consumed:
            effects.append(
                {
                    "type": "mark",
                    "target": target,
                    "remove": True,
                    "source": actor,
                    "cause": "attack",
                }
            )

        # Create detailed narration hint
        narration_hint = {
            "summary": self._get_attack_summary(
                outcome,
                weapon,
                damage,
                attacker.name if hasattr(attacker, "name") else actor,
            ),
            "dice": {
                "d20": d20_roll,
                "style": style_dice,
                "style_sum": style_sum,
                "total": total,
                "dc": dc_hint,
                "margin": margin,
                "effective_style": effective_style,
                "damage_dice": damage_dice,
            },
            "outcome": outcome,
            "raw_damage": raw_damage,
            "applied_damage": damage,
            "mark_consumed": mark_consumed,
            "tone_tags": ["violent", "tense"]
            + (["critical"] if outcome == "crit_success" else []),
            "salient_entities": [actor, target],
        }

        return ToolResult(
            ok=True,
            tool_id="attack",
            args=args,
            facts={
                "outcome": outcome,
                "margin": margin,
                "total": total,
                "dc": dc_hint,
                "raw_damage": raw_damage,
                "applied_damage": damage,
                "mark_consumed": mark_consumed,
                "weapon": weapon,
            },
            effects=effects,
            narration_hint=narration_hint,
        )

    def _roll_damage(self, damage_expr: str, is_crit: bool, random_module) -> tuple:
        """Roll damage dice based on expression and critical hit status."""
        damage_dice = []
        total_damage = 0

        try:
            # Parse damage expression (e.g., "1d6", "1d6+1", "2d4")
            if "+" in damage_expr:
                dice_part, bonus_part = damage_expr.split("+", 1)
                bonus = int(bonus_part.strip())
            else:
                dice_part = damage_expr.strip()
                bonus = 0

            # Parse dice part (e.g., "1d6" -> count=1, size=6)
            if "d" not in dice_part:
                raise ValueError(f"Invalid damage expression: {damage_expr}")

            count_str, size_str = dice_part.split("d", 1)
            dice_count = int(count_str.strip())
            dice_size = int(size_str.strip())

            # Roll base damage
            for _ in range(dice_count):
                roll = random_module.randint(1, dice_size)
                damage_dice.append({"type": "base", "value": roll})
                total_damage += roll

            # Add bonus
            total_damage += bonus

            # Critical success: add extra damage (1d6 bonus)
            if is_crit:
                crit_roll = random_module.randint(1, 6)
                damage_dice.append({"type": "crit", "value": crit_roll})
                total_damage += crit_roll

        except (ValueError, IndexError) as e:
            # Fallback to simple 1d6 if parsing fails
            roll = random_module.randint(1, 6)
            damage_dice = [{"type": "base", "value": roll}]
            total_damage = roll
            if is_crit:
                crit_roll = random_module.randint(1, 6)
                damage_dice.append({"type": "crit", "value": crit_roll})
                total_damage += crit_roll

        return damage_dice, total_damage

    def _get_attack_summary(
        self, outcome: str, weapon: str, damage: int, attacker_name: str
    ) -> str:
        """Generate attack summary text based on outcome."""
        weapon_text = weapon if weapon != "basic_melee" else "weapon"

        if outcome == "crit_success":
            return f"{attacker_name}'s {weapon_text} strikes true, dealing {damage} devastating damage"
        elif outcome == "success":
            return f"{attacker_name} hits with {weapon_text} for {damage} damage"
        elif outcome == "partial":
            # damage parameter is already halved by caller (line 711)
            return (
                f"{attacker_name}'s {weapon_text} grazes the target for {damage} damage"
            )
        else:  # fail
            return f"{attacker_name}'s {weapon_text} misses completely"

    def _execute_use_item(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute use_item tool."""
        actor = args.get("actor")
        item = args.get("item")
        target = args.get("target", actor)

        # Simple item effects
        effects = []
        if item and "potion" in item.lower():
            effects.append({"type": "hp", "target": target, "delta": 5})
        elif item and "rope" in item.lower():
            effects.append(
                {"type": "mark", "target": actor, "style_bonus": 1, "consumes": True}
            )

        narration_hint = {
            "summary": f"Used {item}",
            "item": {"id": item, "target": target},
            "tone_tags": ["resourceful"],
            "salient_entities": [actor],
        }

        return ToolResult(
            ok=True,
            tool_id="use_item",
            args=args,
            facts={"item_used": item},
            effects=effects,
            narration_hint=narration_hint,
        )

    def _execute_get_info(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute get_info tool."""
        query = args.get("query", "")
        scope = args.get("scope", "current_zone")

        # Generate info based on scope
        info = {}
        if scope == "current_zone" and state.current_actor:
            current_actor = state.actors.get(state.current_actor)
            if current_actor and hasattr(current_actor, "visible_actors"):
                pc_or_npc = cast(Union[PC, NPC], current_actor)
                current_zone = state.zones.get(current_actor.current_zone)
                if current_zone:
                    info = {
                        "zone_name": current_zone.name,
                        "zone_description": current_zone.description,
                        "visible_actors": [
                            state.actors[aid].name
                            for aid in pc_or_npc.visible_actors
                            if aid in state.actors
                        ],
                        "adjacent_zones": [
                            state.zones[zid].name
                            for zid in current_zone.adjacent_zones
                            if zid in state.zones
                        ],
                    }

        return ToolResult(
            ok=True,
            tool_id="get_info",
            args=args,
            facts=info,
            effects=[],
            narration_hint={
                "summary": "Gathered information",
                "tone_tags": ["observant"],
                "salient_entities": (
                    [state.current_actor] if state.current_actor else []
                ),
            },
        )

    def _execute_narrate_only(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute narrate_only tool - Pure narration for flavor moves or observation."""

        # Extract arguments
        actor_id = args.get("actor") or state.current_actor
        topic = args.get("topic") or "look around"

        # Determine POV and current zone
        pov_actor = state.actors.get(actor_id) if actor_id else None
        current_zone_id = (
            pov_actor.current_zone
            if pov_actor and hasattr(pov_actor, "current_zone")
            else None
        )
        current_zone = state.zones.get(current_zone_id) if current_zone_id else None
        # Gather visible entities (only in same zone with visibility != hidden)
        visible_entities = []
        if current_zone_id:
            for entity_id, entity in state.actors.items():
                if (
                    entity_id != actor_id
                    and hasattr(entity, "current_zone")
                    and entity.current_zone == current_zone_id
                    and getattr(entity, "visibility", "visible") == "visible"
                ):
                    visible_entities.append(entity_id)

        # Get salient features from zone (limit to top 2-3)
        salient_features = []
        if current_zone:
            zone_features = getattr(current_zone, "features", [])
            salient_features = zone_features[:3] if zone_features else []

            # Add zone description as a feature if it exists
            if hasattr(current_zone, "description") and current_zone.description:
                salient_features.insert(0, current_zone.description)

        # Get scene tags for tone/lighting/atmosphere
        scene_tags = {}
        if state.scene:
            scene_tags = getattr(state.scene, "tags", {})

        # Create facts dict
        facts = {
            "pov": actor_id,
            "zone": current_zone_id,
            "zone_name": current_zone.name if current_zone else "Unknown Location",
            "visible_entities": visible_entities,
            "salient_features": salient_features,
            "scene_tags": scene_tags,
            "topic": topic,
        }

        # Generate summary based on topic and facts
        summary = self._generate_narration_summary(
            topic, facts, current_zone, visible_entities, scene_tags, state
        )

        # Determine tone tags from scene and topic
        tone_tags = self._get_narration_tone_tags(topic, scene_tags)

        # Determine sensory focus based on topic
        sensory = self._topic_to_senses(topic)

        # Determine camera angle based on topic
        camera = self._topic_to_camera(topic)

        # Create narration hint
        narration_hint = {
            "summary": summary,
            "tone_tags": tone_tags,
            "salient_entities": visible_entities,
            "sensory": sensory,
            "camera": camera,
            "sentences_max": 4 if topic == "recap" else 3,
        }

        return ToolResult(
            ok=True,
            tool_id="narrate_only",
            args=args,
            facts=facts,
            effects=[],  # narrate_only never changes state
            narration_hint=narration_hint,
        )

    def _generate_narration_summary(
        self,
        topic: str,
        facts: dict,
        current_zone,
        visible_entities: list,
        scene_tags: dict,
        state: GameState,
    ) -> str:
        """Generate narration summary based on topic and facts."""
        zone_name = facts.get("zone_name", "an unknown location")

        # Handle None topic
        if not topic:
            topic = "look around"

        if topic == "look around":
            if visible_entities:
                entity_names = []
                for entity_id in visible_entities[:2]:  # Limit to first 2 entities
                    entity = state.actors.get(entity_id)
                    if entity and hasattr(entity, "name"):
                        entity_names.append(entity.name)
                    else:
                        entity_names.append("a figure")

                entities_text = " and ".join(entity_names) if entity_names else ""
                if entities_text:
                    return f"You survey {zone_name}. {entities_text} can be seen here."
                else:
                    return f"You survey {zone_name}."
            else:
                return f"You survey {zone_name}. The area appears quiet."

        elif topic == "listen":
            if scene_tags.get("noise") == "loud":
                return f"You listen carefully. Loud sounds echo through {zone_name}."
            elif scene_tags.get("noise") == "quiet":
                return f"You listen carefully. {zone_name} is eerily quiet."
            else:
                return f"You listen carefully to the sounds of {zone_name}."

        elif topic == "smell":
            if any("grain" in str(v).lower() for v in scene_tags.values()):
                return f"You breathe in deeply. The scent of grain fills the air in {zone_name}."
            else:
                return f"You breathe in deeply, taking in the scents of {zone_name}."

        elif topic == "recap":
            return f"You pause to consider your situation in {zone_name}."

        elif topic == "establishing":
            return f"You gather yourself in {zone_name}."

        elif topic.startswith("zoom_in:"):
            entity_id = topic.split(":", 1)[1]
            return f"You focus your attention on the nearby presence."

        elif topic.startswith("zoom_in:"):
            entity_id = topic.split(":", 1)[1]
            return f"You focus your attention on the nearby presence."

        else:
            return f"You observe {zone_name}."

    def _get_narration_tone_tags(self, topic: str, scene_tags: dict) -> list:
        """Get appropriate tone tags for narration based on topic and scene."""
        base_tags = ["atmospheric"]

        # Handle None topic
        if not topic:
            topic = "look around"

        # Add scene-based tags
        if scene_tags.get("lighting") == "dim":
            base_tags.append("moody")
        if scene_tags.get("alert") == "sleepy":
            base_tags.append("quiet")
        if scene_tags.get("noise") == "loud":
            base_tags.append("tense")

        # Add topic-based tags
        if topic == "recap":
            base_tags.append("reflective")
        elif topic in ["listen", "smell"]:
            base_tags.append("sensory")
        elif topic == "establishing":
            base_tags.append("introspective")

        return base_tags

    def _topic_to_senses(self, topic: str) -> list:
        """Map topic to relevant senses."""
        if not topic:
            topic = "look around"

        if topic == "listen":
            return ["sound"]
        elif topic == "smell":
            return ["smell"]
        elif topic.startswith("zoom_in"):
            return ["sight", "sound"]
        else:
            return ["sight"]

    def _topic_to_camera(self, topic: str) -> str:
        """Map topic to camera angle/distance."""
        if not topic:
            topic = "look around"

        if topic == "look around":
            return "over-shoulder"
        elif topic == "establishing":
            return "wide"
        elif topic.startswith("zoom_in"):
            return "close-up"
        elif topic == "recap":
            return "wide"
        else:
            return "over-shoulder"

    def _execute_apply_effects(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute apply_effects tool."""
        effects = args.get("effects", [])

        return ToolResult(
            ok=True,
            tool_id="apply_effects",
            args=args,
            facts={"effects_applied": len(effects)},
            effects=effects,
            narration_hint={
                "summary": f"Applied {len(effects)} effects",
                "tone_tags": ["mechanical"],
                "salient_entities": [],
            },
        )

    def _execute_ask_clarifying(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute ask_clarifying tool - creates a pending choice for later resolution."""

        # Check if we've exceeded max clarifications per turn
        if state.scene.choice_count_this_turn >= 3:
            # Clear any pending choice and fall back to narrate_only
            state.scene.pending_choice = None

            return ToolResult(
                ok=True,
                tool_id="narrate_only",
                args={"topic": "hesitation", "actor": state.current_actor},
                facts={
                    "clarification_limit_reached": True,
                    "max_clarifications": 3,
                    "fallback_reason": "You hesitate, unsure what to do next.",
                },
                effects=[],
                narration_hint={
                    "summary": "You hesitate, unsure what to do next.",
                    "tone_tags": ["neutral", "reflective"],
                    "sentences_max": 1,
                    "salient_entities": (
                        [state.current_actor] if state.current_actor else []
                    ),
                },
            )

        # Extract arguments with validation
        question = args.get("question", "What would you like to do?")
        options_raw = args.get("options", [])
        reason = args.get("reason", "ambiguous_intent")
        actor = args.get("actor") or state.current_actor
        context_note = args.get("context_note")
        expires_in_turns = args.get("expires_in_turns", 1)

        # Validate we have proper options
        if not options_raw or len(options_raw) < 2:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args=args,
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Failed to create clarifying question - need at least 2 options",
                    "tone_tags": ["error"],
                    "salient_entities": [],
                },
                error_message="ask_clarifying requires at least 2 options",
            )

        # Validate option ids are unique
        option_ids = [opt.get("id") for opt in options_raw]
        if len(set(option_ids)) != len(option_ids):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args=args,
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Failed to create clarifying question - option IDs must be unique",
                    "tone_tags": ["error"],
                    "salient_entities": [],
                },
                error_message="Option IDs must be unique",
            )

        # Validate tool_ids are recognized
        valid_tool_ids = {
            "ask_roll",
            "move",
            "attack",
            "talk",
            "use_item",
            "get_info",
            "narrate_only",
            "apply_effects",
        }
        for opt in options_raw:
            if opt.get("tool_id") not in valid_tool_ids:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args=args,
                    facts={},
                    effects=[],
                    narration_hint={
                        "summary": f"Failed to create clarifying question - invalid tool_id: {opt.get('tool_id')}",
                        "tone_tags": ["error"],
                        "salient_entities": [],
                    },
                    error_message=f"Invalid tool_id: {opt.get('tool_id')}",
                )

        # Increment clarification counter
        state.scene.choice_count_this_turn += 1

        # Generate unique pending choice ID
        pc_id = f"pc_{uuid.uuid4().hex[:6]}"
        expires_round = state.scene.round + expires_in_turns

        # Create pending choice structure
        pending_choice = {
            "id": pc_id,
            "actor": actor,
            "question": question,
            "options": options_raw,
            "reason": reason,
            "expires_round": expires_round,
            "created_turn": state.scene.choice_count_this_turn,
        }

        if context_note:
            pending_choice["context_note"] = context_note

        # Store pending choice in scene state
        state.scene.pending_choice = pending_choice

        # Create a user-friendly options summary for narration
        options_text = " or ".join(
            [f"({opt['id']}) {opt['label']}" for opt in options_raw]
        )
        interactive_summary = f"{question} {options_text}"

        # Create options summary for cleaner presentation
        options_summary = [f"{opt['id']}: {opt['label']}" for opt in options_raw]

        # Create narration hint
        narration_hint = {
            "summary": interactive_summary,
            "options_summary": options_summary,
            "tone_tags": ["interactive", "concise"],
            "sentences_max": 1,
            "salient_entities": [actor] if actor else [],
        }

        # Return facts containing the pending choice metadata
        facts = {
            "pending_choice_id": pc_id,
            "actor": actor,
            "question": question,
            "options": [
                {"id": opt["id"], "label": opt["label"], "tool_id": opt["tool_id"]}
                for opt in options_raw
            ],
            "reason": reason,
            "clarification_number": state.scene.choice_count_this_turn,
            "open_choice": True,  # Options are suggestions, not restrictions
        }

        return ToolResult(
            ok=True,
            tool_id="ask_clarifying",
            args=args,
            facts=facts,
            effects=[],  # No state mutation beyond storing pending_choice
            narration_hint=narration_hint,
        )

    def _create_error_result(
        self,
        tool_id: str,
        args: Dict[str, Any],
        error_msg: str,
        log_entry: Dict[str, Any],
    ) -> ToolResult:
        """Create an error result with ask_clarifying fallback."""
        log_entry["result"] = {"ok": False, "error": error_msg}
        logger.error(json.dumps(log_entry))

        return ToolResult(
            ok=False,
            tool_id="ask_clarifying",
            args={
                "question": "I'm not sure how to do that. Could you try something else?"
            },
            facts={},
            effects=[],
            narration_hint={
                "summary": "Asked for clarification due to error",
                "tone_tags": ["helpful"],
                "salient_entities": [],
            },
            error_message=error_msg,
        )

    def _get_state_summary(self, state: GameState) -> Dict[str, Any]:
        """Get a summary of current state for logging."""
        summary = {}

        if hasattr(state, "turn_flags"):
            summary.update(state.turn_flags)

        if hasattr(state, "clocks"):
            summary["clocks"] = {k: v["value"] for k, v in state.clocks.items()}

        if state.current_actor and state.current_actor in state.actors:
            current_actor = state.actors[state.current_actor]
            summary["current_zone"] = current_actor.current_zone
            if hasattr(current_actor, "visible_actors"):
                pc_or_npc = cast(Union[PC, NPC], current_actor)
                summary["visible_actors"] = len(pc_or_npc.visible_actors)

        return summary


# Global validator instance
validator = Validator()


def validate_and_execute(
    tool_id: str,
    raw_args: Dict[str, Any],
    state: GameState,
    utterance: Utterance,
    seed: Optional[int] = None,
) -> ToolResult:
    """Convenience function for validation and execution."""
    return validator.validate_and_execute(tool_id, raw_args, state, utterance, seed)
