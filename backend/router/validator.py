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
import hashlib
import ast
import operator
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union, cast, Callable
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass

from .game_state import (
    GameState,
    Utterance,
    PC,
    NPC,
    ObjectEntity,
    ItemEntity,
    PendingEffect,
    EffectLogEntry,
    is_visible_to,
    is_zone_visible_to,
    is_clock_visible_to,
)
from .zone_graph import (
    is_adjacent,
    describe_exits,
    is_exit_usable,
    get_zone as get_zone_graph,
)
from .tool_catalog import TOOL_CATALOG, get_tool_by_id, Effect
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
        self.item_registry = self._load_item_registry()

    def _load_item_registry(self) -> Dict[str, Any]:
        """Load item registry from JSON file with fallback to hardcoded items."""
        try:
            # Look for items.json in parent directory of backend
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(os.path.dirname(current_dir))
            items_path = os.path.join(parent_dir, "items.json")

            with open(items_path, "r") as f:
                registry = json.load(f)
                logger.info(f"Loaded {len(registry)} items from items.json")
                return registry
        except FileNotFoundError:
            logger.warning(
                "items.json not found, using fallback hardcoded item registry"
            )
            return self._get_fallback_item_registry()
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing items.json: {e}")
            return self._get_fallback_item_registry()

    def _get_fallback_item_registry(self) -> Dict[str, Any]:
        """Fallback hardcoded item registry if JSON file not available."""
        return {
            "healing_potion": {
                "id": "healing_potion",
                "name": "Healing Potion",
                "description": "Restores health when drunk.",
                "tags": ["consumable", "healing", "magical"],
                "usage_methods": ["consume"],
                "charges": 1,
                "effects": [{"type": "hp", "delta": "2d4+2"}],
            },
            "poison_vial": {
                "id": "poison_vial",
                "name": "Poison Vial",
                "description": "Deals poison damage to target.",
                "tags": ["consumable", "poison", "dangerous"],
                "usage_methods": ["consume"],
                "charges": 1,
                "effects": [{"type": "hp", "delta": "-1d6"}],
            },
            "rope": {
                "id": "rope",
                "name": "Rope",
                "description": "Provides advantage on climbing checks.",
                "tags": ["consumable", "mundane", "tool"],
                "usage_methods": ["consume"],
                "charges": 1,
                "effects": [{"type": "mark", "tag": "climbing_advantage"}],
            },
        }

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
                sanitized_args = validated_args.model_dump()
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
        ignore_adjacency = args.get(
            "ignore_adjacency", False
        )  # For special movement tools

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

        # Validation: Check if exit exists first, then check usability
        target_exit = (
            current_zone.get_exit(to_zone)
            if hasattr(current_zone, "get_exit")
            else None
        )

        if target_exit:
            # Exit exists, check if it's usable
            is_usable, reason = is_exit_usable(target_exit, actor_entity, state)
            if not is_usable:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={"question": f"The path to {target_zone.name} is {reason}."},
                    facts={
                        "cause": "blocked",
                        "destination": to_zone,
                        "reason": reason,
                    },
                    effects=[],
                    narration_hint={},
                )
        else:
            # No exit exists - check if this should be considered invalid adjacency
            if not ignore_adjacency:
                # Helper function to get zone properties from both Zone objects and dict-backed zones
                def get_zone_property(zone, prop_name, default):
                    """Get property from Zone object (attribute) or dict-backed zone (key)."""
                    if hasattr(zone, prop_name):
                        # Zone object - use attribute access
                        return getattr(zone, prop_name, default)
                    elif isinstance(zone, dict):
                        # Dict-backed zone - use key access
                        return zone.get(prop_name, default)
                    else:
                        return default

                # Check legacy blocked_exits for backwards compatibility
                blocked_exits = get_zone_property(current_zone, "blocked_exits", [])
                if to_zone in blocked_exits:
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"The path to {target_zone.name} is blocked."
                        },
                        facts={"cause": "blocked", "destination": to_zone},
                        effects=[],
                        narration_hint={},
                    )

                # Check legacy adjacent_zones for backwards compatibility
                adjacent_zones = get_zone_property(
                    current_zone, "adjacent_zones", set()
                )
                if to_zone in adjacent_zones:
                    # Legacy adjacency allows the move - proceed without exit-specific messaging
                    pass  # Continue to movement execution below
                else:
                    # No exit exists and not in adjacent_zones - show valid exits
                    valid_exit_descriptions = describe_exits(current_zone, state)
                    valid_exits = [
                        desc["target_name"] for desc in valid_exit_descriptions
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

        # Validate ALL targets are social creatures and visible to actor
        for i, (target_id, target_entity) in enumerate(zip(targets, target_entities)):
            # Check if target is a social creature (pc or npc)
            if target_entity.type not in ("pc", "npc"):
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": f"You can't have a meaningful conversation with {target_entity.name}.",
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
                    error_message=f"Target '{target_id}' is not social_receptive",
                )

            # Check if target is visible to actor
            if target_id not in actor_creature.visible_actors:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": f"You can't see {target_entity.name} to talk to them.",
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
                    error_message=f"Target '{target_id}' is not visible to speaker '{actor}'",
                )

        # Type cast for safe access to target attributes
        target_creature = cast(Union[PC, NPC], primary_target_entity)

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
        attack_mode = args.get("attack_mode", "normal")  # New: scroll vs normal attacks

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

        # Special handling for scroll attacks - they never completely fail
        if attack_mode == "scroll" and outcome == "fail":
            outcome = "partial"  # Scrolls always deal at least half damage
            logger.debug(f"Scroll attack upgraded from fail to partial for {weapon}")

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
        """Execute use_item tool - comprehensive item usage system."""
        import random

        random.seed(seed)

        # Extract arguments
        actor = args.get("actor")
        item_id = args.get("item_id")
        target = args.get("target")
        if target is None:
            target = actor  # Default target is actor if not specified
        method = args.get("method", "consume")
        charges = args.get("charges", 1)

        # Ensure target is never None for type safety
        if target is None:
            target = "unknown"

        # Validate actor exists and can act
        if not actor or actor not in state.entities:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": "Who should use the item? I don't see that character."
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

        actor_entity = state.entities[actor]
        if actor_entity.type not in ("pc", "npc"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": "Only characters can use items."},
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

        # Check if actor can act (has positive HP)
        if actor_creature.hp.current <= 0:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"{actor_creature.name} is unconscious and cannot use items."
                },
                facts={
                    "cause": "actor_state",
                    "actor_state": "unconscious",
                    "actor": actor,
                },
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to unconscious actor",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' is unconscious",
            )

        # Check if actor has inventory
        if not hasattr(actor_creature, "inventory"):
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": f"{actor_creature.name} doesn't have an inventory."},
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to missing inventory",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Actor '{actor}' has no inventory",
            )

        # Check if actor has the item
        if item_id not in actor_creature.inventory:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"You don't have '{item_id}'. What item would you like to use?"
                },
                facts={
                    "cause": "item_not_found",
                    "item_id": item_id,
                    "available_items": actor_creature.inventory,
                },
                effects=[],
                narration_hint={
                    "summary": f"Asked for clarification due to missing item '{item_id}'",
                    "tone_tags": ["helpful"],
                    "salient_entities": [actor],
                },
                error_message=f"Item '{item_id}' not in inventory",
            )

        # Get item definition from registry (needed for validation)
        item_definition = self._get_item_definition(item_id)

        # Validate target if specified and different from actor
        target_entity = None
        if target and target != actor:
            # Check if this item delegates to move tool (needs zone, not entity)
            delegation_tool = item_definition.get("delegation", {}).get("tool")

            if delegation_tool == "move":
                # For move tool delegation, validate that target is a zone instead
                if target not in state.zones:
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"I can't find the zone '{target}'. Where do you want to go?"
                        },
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": "Asked for clarification due to missing zone",
                            "tone_tags": ["helpful"],
                            "salient_entities": [],
                        },
                        error_message=f"Zone '{target}' not found",
                    )
                # Skip entity validation for move delegation
            else:
                # Standard entity validation for other tools
                if target not in state.entities:
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"I can't find '{target}'. Who should be the target?"
                        },
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": "Asked for clarification due to missing target",
                            "tone_tags": ["helpful"],
                            "salient_entities": [],
                        },
                        error_message=f"Target '{target}' not found",
                    )

                target_entity = state.entities[target]

        # Enhanced target validation with item-specific checks (only for entity targets)
        if target_entity:
            item_tags = item_definition.get("tags", [])

            # Check if target is valid for the item type
            if method in ("consume", "activate") and target_entity.type not in (
                "pc",
                "npc",
            ):
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": "You can't use that item on this target. Choose a different target."
                    },
                    facts={},
                    effects=[],
                    narration_hint={
                        "summary": "Asked for clarification due to invalid target type",
                        "tone_tags": ["helpful"],
                        "salient_entities": [],
                    },
                    error_message=f"Target '{target}' is not a valid target for item usage",
                )

            # Check for dangerous item usage on allies
            if "dangerous" in item_tags or "poison" in item_tags:
                # Warn if using dangerous items on potential allies
                if target_entity.type == "pc":
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"This item could harm {target_entity.name}. Are you sure you want to use it on them?",
                            "options": [
                                {
                                    "id": "A",
                                    "label": "Yes, use it anyway",
                                    "tool_id": "use_item",
                                    "args_patch": args,  # Pass through original args
                                },
                                {
                                    "id": "B",
                                    "label": "No, cancel",
                                    "tool_id": "narrate_only",
                                    "args_patch": {"topic": "hesitation"},
                                },
                            ],
                        },
                        facts={
                            "dangerous_item_warning": True,
                            "target_type": target_entity.type,
                            "item_tags": item_tags,
                        },
                        effects=[],
                        narration_hint={
                            "summary": "Warning about dangerous item usage",
                            "tone_tags": ["warning", "dangerous"],
                            "salient_entities": [actor, target],
                        },
                        error_message=f"Dangerous item usage warning for '{item_id}' on '{target}'",
                    )

            # Check visibility for targeted usage
            if actor in state.entities and state.entities[actor].type in ("pc", "npc"):
                actor_creature_check = cast(Union[PC, NPC], state.entities[actor])
                if (
                    hasattr(actor_creature_check, "visible_actors")
                    and target not in actor_creature_check.visible_actors
                ):
                    return ToolResult(
                        ok=False,
                        tool_id="ask_clarifying",
                        args={
                            "question": f"You can't see {target_entity.name} to use the item on them."
                        },
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": "Asked for clarification due to invisible target",
                            "tone_tags": ["helpful"],
                            "salient_entities": [],
                        },
                        error_message=f"Target '{target}' is not visible to actor '{actor}'",
                    )

        # Validate method compatibility using tags and usage_methods
        usage_methods = item_definition.get(
            "usage_methods", [item_definition.get("method", "consume")]
        )
        if method not in usage_methods:
            # Enhanced misuse detection with context-aware suggestions
            item_tags = item_definition.get("tags", [])
            suggestions = []
            warnings = []

            # Tag-based method suggestions
            if "consumable" in item_tags:
                suggestions.append("consume")
            if "equipable" in item_tags or "weapon" in item_tags:
                suggestions.append("equip")
            if "reusable" in item_tags or "illumination" in item_tags:
                suggestions.append("activate")
            if "magical" in item_tags and "scroll" in item_tags:
                suggestions.append("read")

            # Generate warnings for dangerous misuse
            if "cursed" in item_tags and method == "equip":
                warnings.append(
                    "Warning: This item is cursed and may have negative effects when equipped!"
                )
            if "dangerous" in item_tags and target and target != actor:
                warnings.append("Warning: This item could harm the target!")
            if "area_effect" in item_definition and not target:
                warnings.append(
                    "Warning: This item affects a large area - specify a target!"
                )

            suggested_methods = (
                ", ".join(suggestions) if suggestions else ", ".join(usage_methods)
            )

            warning_text = " ".join(warnings) if warnings else ""
            question_text = f"This item should be used with method '{suggested_methods}', not '{method}'. Try again?"
            if warning_text:
                question_text = f"{warning_text} {question_text}"

            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={"question": question_text},
                facts={
                    "cause": "method_mismatch",
                    "expected_methods": usage_methods,
                    "provided_method": method,
                    "item_tags": item_tags,
                    "warnings": warnings,
                    "misuse_detected": True,
                },
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to method mismatch",
                    "tone_tags": ["helpful", "warning"] if warnings else ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Method mismatch: expected {usage_methods}, got '{method}'",
            )

        # Check if item has enough charges
        item_charges = item_definition.get("charges", 1)
        # Handle unlimited use items (-1 charges)
        if item_charges != -1 and charges > item_charges:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"This item only has {item_charges} charges, but you're trying to use {charges}. Use fewer charges?"
                },
                facts={
                    "cause": "insufficient_charges",
                    "available_charges": item_charges,
                    "requested_charges": charges,
                },
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification due to insufficient charges",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message=f"Insufficient charges: has {item_charges}, requested {charges}",
            )

        # Execute item usage based on method
        effects = []

        # Capture inventory state before usage for enhanced logging
        inventory_before = actor_creature.inventory.copy()

        facts = {
            "item_id": item_id,
            "item_name": item_definition.get("name", item_id),
            "method": method,
            "charges_used": charges,
            "target": target,
            "item_tags": item_definition.get("tags", []),
            "inventory_before": inventory_before,
        }

        # Enhanced logging for replay - capture more granular details
        dice_rolls_log = []
        item_usage_metadata = {
            "item_id": item_id,
            "method": method,
            "charges_used": charges,
            "target": target,
            "seed": seed,
            "timestamp": int(time.time()),
            "dice_rolls": dice_rolls_log,  # Will be populated during effect resolution
        }

        # Check for delegation first
        delegation_result = None
        if "delegation" in item_definition:
            logger.debug(
                f"Executing delegation for item {item_id} to {item_definition['delegation'].get('tool')}"
            )
            delegation_result = self._execute_item_delegation(
                item_definition, target, actor, state, utterance, seed
            )

            # Check if delegation failed - surface the error instead of continuing
            if delegation_result and not delegation_result.ok:
                return delegation_result  # Return the delegated tool's error directly

            if delegation_result and delegation_result.ok:
                # Add delegation results to effects
                effects.extend(delegation_result.effects)
                facts.update(delegation_result.facts)
                # Update metadata
                item_usage_metadata["delegation"] = {
                    "tool": item_definition["delegation"]["tool"],
                    "delegated_result": delegation_result.to_dict(),
                }

        if method == "consume":
            # Apply item effects (if not delegated successfully) and remove from inventory
            if not (delegation_result and delegation_result.ok):
                item_effects = self._resolve_item_effects_with_logging(
                    item_definition, target, actor, random, dice_rolls_log
                )
                effects.extend(item_effects)

            # Remove item from inventory
            effects.append(
                {
                    "type": "inventory",
                    "target": actor,
                    "item": item_id,
                    "delta": -1,
                    "source": actor,
                    "cause": "item_consumed",
                }
            )

        elif method == "activate":
            # Apply effects without consuming (if not delegated successfully)
            if not (delegation_result and delegation_result.ok):
                item_effects = self._resolve_item_effects_with_logging(
                    item_definition, target, actor, random, dice_rolls_log
                )
                effects.extend(item_effects)

            # Add activation tag to actor
            effects.append(
                {
                    "type": "tag",
                    "target": actor,
                    "add": {f"{item_id}_active": True},
                    "source": actor,
                    "cause": "item_activated",
                }
            )

            # Activate method does NOT consume the item

        elif method == "equip":
            # Move item to equipped slot (simplified - would need equipment system)
            effects.append(
                {
                    "type": "tag",
                    "target": actor,
                    "add": {f"equipped_{item_id}": True},
                    "source": actor,
                    "cause": "item_equipped",
                }
            )

            # Apply passive effects from item (if not delegated successfully)
            if not (delegation_result and delegation_result.ok):
                item_effects = self._resolve_item_effects_with_logging(
                    item_definition, actor, actor, random, dice_rolls_log
                )
                effects.extend(item_effects)

            # Equipment is NOT consumed - it stays in inventory but is now equipped

        elif method == "read":
            # Apply standard item effects first (if not delegated successfully)
            if not (delegation_result and delegation_result.ok):
                item_effects = self._resolve_item_effects_with_logging(
                    item_definition, target, actor, random, dice_rolls_log
                )
                effects.extend(item_effects)

            # Remove item from inventory (scrolls are typically consumed when read)
            effects.append(
                {
                    "type": "inventory",
                    "target": actor,
                    "item": item_id,
                    "delta": -1,
                    "source": actor,
                    "cause": "item_read",
                }
            )

            # Create knowledge or advance clocks based on item
            if "knowledge" in item_definition:
                # Add lore/knowledge to scene
                effects.append(
                    {
                        "type": "tag",
                        "target": "scene",
                        "add": {"revealed_info": item_definition["knowledge"]},
                        "source": actor,
                        "cause": "item_read",
                    }
                )

            if "clock_effect" in item_definition:
                clock_effect = item_definition["clock_effect"]
                effects.append(
                    {
                        "type": "clock",
                        "id": clock_effect["id"],
                        "delta": clock_effect["delta"],
                        "max": clock_effect.get("max", 10),
                        "source": actor,
                        "cause": "item_read",
                    }
                )

        # Store enhanced logging metadata
        item_usage_metadata["effects_generated"] = len(effects)
        item_usage_metadata["inventory_before"] = inventory_before

        # Create detailed narration hint
        item_name = item_definition.get("name", item_id)
        actor_name = actor_creature.name
        item_tags = item_definition.get("tags", [])
        charges_remaining = (
            item_definition.get("charges", 1) - charges
            if item_definition.get("charges", 1) != -1
            else -1
        )

        # Capture inventory state after usage for comparison - maintain working list
        inventory_after = inventory_before.copy()  # Start with original inventory

        for effect in effects:
            if effect.get("type") == "inventory" and effect.get("target") == actor:
                item = effect.get("item")
                delta = effect.get("delta", 0)

                if item and delta != 0:
                    if delta < 0:
                        # Remove specified number of items (not all copies)
                        items_to_remove = abs(delta)
                        while items_to_remove > 0 and item in inventory_after:
                            inventory_after.remove(item)
                            items_to_remove -= 1
                    else:
                        # Add items
                        for _ in range(delta):
                            inventory_after.append(item)

        # Complete the enhanced logging metadata
        item_usage_metadata["inventory_after"] = inventory_after
        item_usage_metadata["charges_remaining"] = charges_remaining

        # Update facts with post-usage information
        facts.update(
            {
                "inventory_after": inventory_after,
                "charges_remaining": charges_remaining,
                "item_consumed": (
                    item_id not in inventory_after
                    if item_id in inventory_before
                    else False
                ),
                "item_usage_metadata": item_usage_metadata,  # Enhanced logging
            }
        )

        # Check for delegation result summary override
        summary_override = None
        if delegation_result and delegation_result.narration_hint:
            summary_override = delegation_result.narration_hint.get("summary")

        if summary_override:
            summary = summary_override
        elif target and target != actor:
            target_entity = state.entities[target]
            target_name = getattr(target_entity, "name", target)
            if method == "consume":
                summary = f"{actor_name} uses {item_name} on {target_name}"
            else:
                summary = f"{actor_name} {method}s {item_name} on {target_name}"
        else:
            if method == "consume":
                summary = f"{actor_name} uses {item_name}"
            else:
                summary = f"{actor_name} {method}s {item_name}"

        # Add effect summary to narration
        effects_summary = []
        for effect in effects:
            if effect["type"] == "hp":
                delta = effect["delta"]
                if delta > 0:
                    effects_summary.append(f"heals {delta} HP")
                else:
                    effects_summary.append(f"deals {abs(delta)} damage")
            elif effect["type"] == "inventory":
                if effect["delta"] < 0:
                    effects_summary.append("item consumed")
            elif effect["type"] == "guard":
                effects_summary.append(f"guard becomes {effect['value']}")
            elif effect["type"] == "mark":
                tag = effect.get("tag", "bonus")
                effects_summary.append(f"gains {tag} mark")
            elif effect["type"] == "delegation":
                effects_summary.append(f"triggers {effect['tool']} effect")

        # Enhanced narration hint with rich metadata
        narration_hint = {
            "summary": summary,
            "tone_tags": ["item", method]
            + (
                [
                    tag
                    for tag in item_tags
                    if tag
                    in ["magical", "cursed", "healing", "poison", "fire", "social"]
                ]
            ),
            "mentioned_entities": [actor]
            + ([target] if target and target != actor else []),
            "mentioned_items": [item_id],
            "effects_summary": effects_summary,
            "sentences_max": 3 if delegation_result else 2,
            "item": {
                "id": item_id,
                "name": item_name,
                "method": method,
                "target": target,
                "tags": item_tags,
                "charges_remaining": charges_remaining,
                "consumed": (
                    item_id not in inventory_after
                    if item_id in inventory_before
                    else False
                ),
                "delegation": delegation_result is not None,
            },
            "inventory": {
                "before": inventory_before,
                "after": inventory_after,
                "changed": inventory_before != inventory_after,
            },
            "enhanced_logging": item_usage_metadata,  # For replay and debugging
        }

        # Override narration hint if delegation provided one
        if delegation_result and delegation_result.narration_hint:
            delegation_hint = delegation_result.narration_hint
            # Merge delegation narration with item narration
            narration_hint.update(
                {
                    "summary": delegation_hint.get("summary", summary),
                    "tone_tags": list(
                        set(
                            narration_hint["tone_tags"]
                            + delegation_hint.get("tone_tags", [])
                        )
                    ),
                    "delegation_details": delegation_hint,
                }
            )

        return ToolResult(
            ok=True,
            tool_id="use_item",
            args=args,
            facts=facts,
            effects=effects,
            narration_hint=narration_hint,
        )

    def _get_item_definition(self, item_id: str) -> Dict[str, Any]:
        """Get item definition from registry or return default definition."""
        # Try to get from loaded registry first
        if item_id in self.item_registry:
            return self.item_registry[item_id]

        # Fallback to legacy hardcoded registry for backward compatibility
        LEGACY_ITEM_REGISTRY = {
            "healing_potion": {
                "id": "healing_potion",
                "name": "Healing Potion",
                "method": "consume",
                "effects": [{"type": "hp", "delta": "2d4+2"}],
                "charges": 1,
                "description": "Restores health when drunk.",
            },
            "poison_vial": {
                "id": "poison_vial",
                "name": "Poison Vial",
                "method": "consume",
                "effects": [{"type": "hp", "delta": "-1d6"}],
                "charges": 1,
                "description": "Deals poison damage to target.",
            },
            "lantern": {
                "id": "lantern",
                "name": "Lantern",
                "method": "activate",
                "effects": [
                    {"type": "tag", "target": "scene", "add": {"lighting": "bright"}}
                ],
                "charges": 10,
                "description": "Provides bright light when activated.",
            },
            "rope": {
                "id": "rope",
                "name": "Rope",
                "method": "consume",
                "effects": [{"type": "mark", "tag": "climbing_advantage"}],
                "charges": 1,
                "description": "Provides advantage on climbing checks.",
            },
            "scroll_fireball": {
                "id": "scroll_fireball",
                "name": "Scroll of Fireball",
                "method": "read",
                "effects": [{"type": "hp", "delta": "-3d6"}],
                "charges": 1,
                "description": "Unleashes a magical fireball when read.",
            },
            "sword": {
                "id": "sword",
                "name": "Sword",
                "method": "equip",
                "effects": [{"type": "guard", "delta": 1}],
                "charges": -1,  # -1 means unlimited uses
                "description": "A sharp blade for combat.",
            },
        }

        if item_id in LEGACY_ITEM_REGISTRY:
            return LEGACY_ITEM_REGISTRY[item_id]

        # Final fallback for completely unknown items
        return {
            "id": item_id,
            "name": item_id.replace("_", " ").title(),
            "method": "consume",
            "usage_methods": ["consume"],
            "tags": ["unknown", "mundane"],
            "effects": [],
            "charges": 1,
            "description": f"A {item_id.replace('_', ' ')}.",
        }

    def _resolve_item_effects(
        self, item_definition: Dict[str, Any], target: str, source: str, random_module
    ) -> List[Dict[str, Any]]:
        """Resolve item effects, including dice rolling for damage/healing and delegation."""
        effects = []

        # Check for delegation first - if item delegates to another tool, handle that
        if "delegation" in item_definition:
            delegation_effects = self._handle_item_delegation(
                item_definition, target, source, random_module
            )
            effects.extend(delegation_effects)
        else:
            # Handle standard item effects
            for effect_template in item_definition.get("effects", []):
                effect = effect_template.copy()

                # Add standard fields - ensure target is never None
                effect_target = effect.get("target")
                if effect_target is None or effect_target == "":
                    effect["target"] = target
                else:
                    effect["target"] = effect_target

                effect["source"] = source
                effect["cause"] = "item_effect"

                # Handle dice expressions in deltas
                if "delta" in effect and isinstance(effect["delta"], str):
                    delta_expr = effect["delta"]
                    if any(char in delta_expr for char in "d+-"):
                        # Parse and roll dice expression
                        rolled_value = self._roll_dice_expression(
                            delta_expr, random_module
                        )
                        effect["delta"] = rolled_value

                # Handle special effect types
                if effect["type"] == "mark":
                    # Ensure mark has proper structure
                    if "tag" not in effect:
                        effect["tag"] = "item_bonus"
                    effect["value"] = effect.get("value", 1)
                    effect["consumes"] = effect.get("consumes", True)

                elif effect["type"] == "guard":
                    # For guard effects, use value instead of delta for absolute setting
                    if "delta" in effect and "value" not in effect:
                        # Convert delta to absolute value (simplified)
                        current_guard = (
                            0  # Would need to get from target entity in real system
                        )
                        effect["value"] = max(0, current_guard + effect["delta"])
                        del effect["delta"]
                    elif "value" not in effect:
                        effect["value"] = 1  # Default guard value

                elif effect["type"] == "tag":
                    # Ensure tag effects have proper structure
                    if "add" not in effect and "remove" not in effect:
                        effect["add"] = {"item_effect": True}

                effects.append(effect)

        # Handle cursed effects for cursed items
        if (
            "cursed" in item_definition.get("tags", [])
            and "curse_effects" in item_definition
        ):
            curse_effects = self._resolve_curse_effects(
                item_definition, target, source, random_module
            )
            effects.extend(curse_effects)

        # Handle area effects for multi-target items
        if "area_effect" in item_definition:
            area_effects = self._resolve_area_effects(
                item_definition, target, source, random_module, effects
            )
            effects.extend(area_effects)

        return effects

    def _resolve_item_effects_with_logging(
        self,
        item_definition: Dict[str, Any],
        target: str,
        source: str,
        random_module,
        dice_log: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Resolve item effects with enhanced dice roll logging for replay."""
        effects = []

        # Check for delegation first - if item delegates to another tool, handle that
        if "delegation" in item_definition:
            delegation_effects = self._handle_item_delegation(
                item_definition, target, source, random_module
            )
            effects.extend(delegation_effects)
        else:
            # Handle standard item effects
            for effect_template in item_definition.get("effects", []):
                effect = effect_template.copy()

                # Add standard fields - ensure target is never None
                effect_target = effect.get("target")
                if effect_target is None or effect_target == "":
                    effect["target"] = target
                else:
                    effect["target"] = effect_target

                effect["source"] = source
                effect["cause"] = "item_effect"

                # Handle dice expressions in deltas with detailed logging
                if "delta" in effect and isinstance(effect["delta"], str):
                    delta_expr = effect["delta"]
                    if any(char in delta_expr for char in "d+-"):
                        # Parse and roll dice expression with detailed logging
                        rolled_value = self._roll_dice_expression_with_details(
                            delta_expr, random_module, dice_log
                        )
                        effect["delta"] = rolled_value

                # Handle special effect types
                if effect["type"] == "mark":
                    # Ensure mark has proper structure
                    if "tag" not in effect:
                        effect["tag"] = "item_bonus"
                    effect["value"] = effect.get("value", 1)
                    effect["consumes"] = effect.get("consumes", True)

                elif effect["type"] == "guard":
                    # For guard effects, use value instead of delta for absolute setting
                    if "delta" in effect and "value" not in effect:
                        # Convert delta to absolute value (simplified)
                        current_guard = (
                            0  # Would need to get from target entity in real system
                        )
                        effect["value"] = max(0, current_guard + effect["delta"])
                        del effect["delta"]
                    elif "value" not in effect:
                        effect["value"] = 1  # Default guard value

                elif effect["type"] == "tag":
                    # Ensure tag effects have proper structure
                    if "add" not in effect and "remove" not in effect:
                        effect["add"] = {"item_effect": True}

                effects.append(effect)

        # Handle cursed effects for cursed items
        if (
            "cursed" in item_definition.get("tags", [])
            and "curse_effects" in item_definition
        ):
            curse_effects = self._resolve_curse_effects(
                item_definition, target, source, random_module
            )
            effects.extend(curse_effects)

        # Handle area effects for multi-target items
        if "area_effect" in item_definition:
            area_effects = self._resolve_area_effects(
                item_definition, target, source, random_module, effects
            )
            effects.extend(area_effects)

        return effects

    def _handle_item_delegation(
        self, item_definition: Dict[str, Any], target: str, source: str, random_module
    ) -> List[Dict[str, Any]]:
        """Handle delegation to other tools for complex items like scroll_fireball."""
        delegation_config = item_definition.get("delegation", {})
        target_tool = delegation_config.get("tool")
        args_override = delegation_config.get("args_override", {})
        effect_duration = delegation_config.get("effect_duration")

        if not target_tool:
            logger.warning(
                f"Item delegation missing target tool: {item_definition.get('id')}"
            )
            return []

        # Get current state from the context - this is a bit tricky since we're inside use_item
        # For now, we'll create a synthetic delegation effect that can be processed later
        delegation_effect = {
            "type": "delegation",
            "target": target,
            "source": source,
            "cause": "item_delegation",
            "tool": target_tool,
            "args_override": args_override,
            "item_id": item_definition.get("id"),
            "item_name": item_definition.get("name"),
        }

        if effect_duration:
            delegation_effect["effect_duration"] = effect_duration

        # For items like scroll_fireball that delegate to attack, we need special handling
        if target_tool == "attack":
            delegation_effect["delegation_type"] = "combat"
            # Add area effect info if present
            if "area_effect" in item_definition:
                delegation_effect["area_effect"] = item_definition["area_effect"]

        elif target_tool == "talk":
            delegation_effect["delegation_type"] = "social"
            # For social delegation like potion_persuasion

        elif target_tool == "move":
            delegation_effect["delegation_type"] = "movement"
            # For movement delegation like grappling_hook

        return [delegation_effect]

    def _resolve_curse_effects(
        self, item_definition: Dict[str, Any], target: str, source: str, random_module
    ) -> List[Dict[str, Any]]:
        """Resolve curse effects for cursed items like cursed_ring."""
        curse_effects = []

        for effect_template in item_definition.get("curse_effects", []):
            effect = effect_template.copy()

            # Add standard fields
            effect["target"] = target
            effect["source"] = source
            effect["cause"] = "curse_effect"

            # Handle dice expressions in deltas (simplified version for curse effects)
            if "delta" in effect and isinstance(effect["delta"], str):
                delta_expr = effect["delta"]
                if any(char in delta_expr for char in "d+-"):
                    rolled_value = self._roll_dice_expression(delta_expr, random_module)
                    effect["delta"] = rolled_value

            # Mark as a curse effect for special handling
            effect["is_curse"] = True

            curse_effects.append(effect)

        return curse_effects

    def _resolve_area_effects(
        self,
        item_definition: Dict[str, Any],
        target: str,
        source: str,
        random_module,
        base_effects: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Resolve area effects for items that affect multiple targets."""
        area_config = item_definition.get("area_effect", {})
        area_type = area_config.get("type", "zone")
        radius = area_config.get("radius", 1)

        area_effects = []

        if area_type == "zone":
            # Apply effects to all entities in the same zone as target
            # For now, create a special area effect that will be processed by the effects system
            area_effect = {
                "type": "area_effect",
                "target": target,
                "source": source,
                "cause": "item_area_effect",
                "area_type": area_type,
                "radius": radius,
                "base_effects": base_effects,  # Effects to apply to each target
                "item_id": item_definition.get("id"),
            }
            area_effects.append(area_effect)

        return area_effects

    def _execute_item_delegation(
        self,
        item_definition: Dict[str, Any],
        target: str,
        source: str,
        state: GameState,
        utterance: Utterance,
        seed: int,
    ) -> Optional[ToolResult]:
        """Execute delegation to another tool for complex items."""
        delegation_config = item_definition.get("delegation", {})
        target_tool = delegation_config.get("tool")
        args_override = delegation_config.get("args_override", {})
        effect_duration = delegation_config.get("effect_duration")

        if not target_tool:
            logger.warning(
                f"Item delegation missing target tool: {item_definition.get('id')}"
            )
            return None

        # Build arguments for the delegated tool
        delegated_args = {}

        # Get base arguments from the tool's suggest_args
        from .tool_catalog import get_tool_by_id

        tool = get_tool_by_id(target_tool)
        if tool and tool.suggest_args:
            try:
                delegated_args = tool.suggest_args(state, utterance)
            except Exception as e:
                logger.warning(
                    f"Error getting base args for delegated tool {target_tool}: {e}"
                )

        # Override with delegation-specific arguments
        delegated_args.update(args_override)

        # Ensure actor and target are set correctly
        delegated_args["actor"] = source
        if target and target != source:
            # Parameter mapping for different tools
            if target_tool == "move":
                # Move tool expects "to" parameter, not "target"
                delegated_args["to"] = target
            else:
                # Other tools expect "target" parameter
                delegated_args["target"] = target

        # Add item context for narration
        delegated_args["_item_context"] = {
            "item_id": item_definition.get("id"),
            "item_name": item_definition.get("name"),
            "method": "delegation",
        }

        # Execute the delegated tool
        try:
            result = self._execute_tool(
                target_tool, delegated_args, state, utterance, seed
            )
            logger.debug(
                f"Delegation to {target_tool} completed with {len(result.effects)} effects"
            )

            # Enhance narration to mention the item
            if result.ok and result.narration_hint:
                item_name = item_definition.get("name", item_definition.get("id"))
                original_summary = result.narration_hint.get("summary", "")

                # Modify summary to include item usage
                if target_tool == "attack":
                    result.narration_hint["summary"] = (
                        f"Using {item_name}, {original_summary.lower()}"
                    )
                elif target_tool == "talk":
                    result.narration_hint["summary"] = (
                        f"Enhanced by {item_name}, {original_summary.lower()}"
                    )
                elif target_tool == "move":
                    result.narration_hint["summary"] = (
                        f"Using {item_name}, {original_summary.lower()}"
                    )

                # Add item tags to tone_tags
                item_tags = item_definition.get("tags", [])
                tone_tags = result.narration_hint.get("tone_tags", [])
                tone_tags.extend(
                    [
                        tag
                        for tag in item_tags
                        if tag in ["magical", "fire", "social", "traversal"]
                    ]
                )
                result.narration_hint["tone_tags"] = tone_tags

                # Add item to mentioned items
                result.narration_hint["mentioned_items"] = [item_definition.get("id")]

            return result

        except Exception as e:
            logger.error(f"Error executing delegated tool {target_tool}: {e}")
            return None

    def _roll_dice_expression(self, expr: str, random_module) -> int:
        """Roll a dice expression like '2d4+2' or '-1d6' with enhanced logging."""
        try:
            # Handle negative expressions
            negative = expr.startswith("-")
            if negative:
                expr = expr[1:]

            # Split by + or -
            total = 0
            parts = []
            current_part = ""

            for char in expr:
                if char in "+-":
                    if current_part:
                        parts.append(current_part)
                        current_part = ""
                    if char == "-":
                        current_part = "-"
                else:
                    current_part += char

            if current_part:
                parts.append(current_part)

            # Enhanced logging: capture individual rolls
            roll_details = {
                "expression": expr,
                "negative": negative,
                "parts": [],
                "individual_rolls": [],
                "total": 0,
            }

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                part_negative = part.startswith("-")
                if part_negative:
                    part = part[1:]

                part_detail = {
                    "part": part,
                    "negative": part_negative,
                    "type": "dice" if "d" in part else "constant",
                    "rolls": [],
                    "subtotal": 0,
                }

                if "d" in part:
                    # Roll dice
                    count_str, size_str = part.split("d", 1)
                    count = int(count_str) if count_str else 1
                    size = int(size_str)

                    for _ in range(count):
                        roll = random_module.randint(1, size)
                        part_detail["rolls"].append(roll)
                        roll_details["individual_rolls"].append(
                            {"die_size": size, "result": roll}
                        )
                        part_subtotal = roll
                        part_detail["subtotal"] += part_subtotal
                        total += -part_subtotal if part_negative else part_subtotal
                else:
                    # Add constant
                    constant = int(part)
                    part_detail["subtotal"] = constant
                    total += -constant if part_negative else constant

                roll_details["parts"].append(part_detail)

            final_total = -total if negative else total
            roll_details["total"] = final_total

            # Store roll details for enhanced logging (would need to be captured by caller)
            # For now, just return the total but this structure enables detailed replay
            return final_total

        except (ValueError, IndexError):
            # Fallback to simple value
            return -1 if negative else 1

    def _roll_dice_expression_with_details(
        self, expr: str, random_module, dice_log: List[Dict[str, Any]]
    ) -> int:
        """Roll dice expression and capture detailed results for replay."""
        try:
            # Handle negative expressions
            negative = expr.startswith("-")
            if negative:
                expr = expr[1:]

            # Split by + or -
            total = 0
            parts = []
            current_part = ""

            for char in expr:
                if char in "+-":
                    if current_part:
                        parts.append(current_part)
                        current_part = ""
                    if char == "-":
                        current_part = "-"
                else:
                    current_part += char

            if current_part:
                parts.append(current_part)

            # Enhanced logging: capture individual rolls
            roll_entry = {
                "expression": f"{'-' if negative else ''}{expr}",
                "timestamp": int(time.time() * 1000),
                "parts": [],
                "individual_rolls": [],
                "total": 0,
            }

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                part_negative = part.startswith("-")
                if part_negative:
                    part = part[1:]

                part_detail = {
                    "part": f"{'-' if part_negative else ''}{part}",
                    "type": "dice" if "d" in part else "constant",
                    "rolls": [],
                    "subtotal": 0,
                }

                if "d" in part:
                    # Roll dice with detailed logging
                    count_str, size_str = part.split("d", 1)
                    count = int(count_str) if count_str else 1
                    size = int(size_str)

                    for _ in range(count):
                        roll = random_module.randint(1, size)
                        part_detail["rolls"].append(roll)
                        roll_entry["individual_rolls"].append(
                            {
                                "die_size": size,
                                "result": roll,
                                "part_index": len(roll_entry["parts"]),
                            }
                        )
                        part_subtotal = roll
                        part_detail["subtotal"] += part_subtotal
                        total += -part_subtotal if part_negative else part_subtotal
                else:
                    # Add constant
                    constant = int(part)
                    part_detail["subtotal"] = constant
                    total += -constant if part_negative else constant

                roll_entry["parts"].append(part_detail)

            final_total = -total if negative else total
            roll_entry["total"] = final_total

            # Add to dice log for replay
            dice_log.append(roll_entry)

            return final_total

        except (ValueError, IndexError):
            # Fallback to simple value with logging
            fallback_entry = {
                "expression": expr,
                "timestamp": int(time.time() * 1000),
                "fallback": True,
                "total": -1 if negative else 1,
            }
            dice_log.append(fallback_entry)
            return -1 if negative else 1

    def _execute_get_info(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute get_info tool - retrieve structured facts from game state."""

        # Extract arguments with defaults
        actor = args.get("actor", state.current_actor)
        target = (
            args.get("target") or actor
        )  # Default to actor if target is None or missing
        topic = args.get("topic", "status")
        detail_level = args.get("detail_level", "brief")

        # Validate context - must have at least one valid context
        if not actor and not target:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": "Who or what would you like to get information about?",
                    "reason": "missing_arg",
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": "Asked for clarification - no valid context provided",
                    "tone_tags": ["helpful"],
                    "salient_entities": [],
                },
                error_message="No valid actor or target provided",
            )

        # Validate target exists if specified
        if target and target not in state.entities and target not in state.zones:
            return ToolResult(
                ok=False,
                tool_id="ask_clarifying",
                args={
                    "question": f"I don't see '{target}' here. What would you like to check instead?",
                    "reason": "invalid_target",
                },
                facts={},
                effects=[],
                narration_hint={
                    "summary": f"Asked for clarification - '{target}' not found",
                    "tone_tags": ["helpful"],
                    "salient_entities": [actor] if actor else [],
                },
                error_message=f"Target '{target}' not found in game state",
            )

        # Validate target visibility if it's an entity
        if target and target in state.entities:
            entity = state.entities[target]
            # Check scene-level visibility (Meta system)
            if not is_visible_to(entity, state.scene):
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": f"I don't see '{target}' here. What would you like to check instead?",
                        "reason": "invalid_target",
                    },
                    facts={},
                    effects=[],
                    narration_hint={
                        "summary": f"Asked for clarification - '{target}' not visible",
                        "tone_tags": ["helpful"],
                        "salient_entities": [actor] if actor else [],
                    },
                    error_message=f"Target '{target}' not visible to actor",
                )

            # Check actor POV visibility (visible_actors list) - only for PC/NPC targets
            if (
                actor
                and actor in state.entities
                and target != actor
                and entity.type in ("pc", "npc")
            ):
                requesting_actor = state.entities[actor]
                # Only PC and NPC entities have visible_actors list
                if requesting_actor.type in ("pc", "npc"):
                    # Safe to cast since we checked the type
                    from .game_state import PC, NPC

                    actor_with_vision = cast(Union[PC, NPC], requesting_actor)
                    if target not in actor_with_vision.visible_actors:
                        return ToolResult(
                            ok=False,
                            tool_id="ask_clarifying",
                            args={
                                "question": f"I don't see '{target}' here. What would you like to check instead?",
                                "reason": "invalid_target",
                            },
                            facts={},
                            effects=[],
                            narration_hint={
                                "summary": f"Asked for clarification - '{target}' not in actor's view",
                                "tone_tags": ["helpful"],
                                "salient_entities": [actor],
                            },
                            error_message=f"Target '{target}' not visible to actor '{actor}'",
                        )

            # For objects (not items), check zone-based visibility
            elif entity.type == "object" and actor and actor in state.entities:
                requesting_actor = state.entities[actor]
                if hasattr(requesting_actor, "current_zone") and hasattr(
                    entity, "current_zone"
                ):
                    if requesting_actor.current_zone != entity.current_zone:
                        return ToolResult(
                            ok=False,
                            tool_id="ask_clarifying",
                            args={
                                "question": f"I don't see '{target}' here. What would you like to check instead?",
                                "reason": "invalid_target",
                            },
                            facts={},
                            effects=[],
                            narration_hint={
                                "summary": f"Asked for clarification - '{target}' object not in current zone",
                                "tone_tags": ["helpful"],
                                "salient_entities": [actor],
                            },
                            error_message=f"Object '{target}' not in same zone as actor '{actor}'",
                        )

        # Generate facts based on topic
        facts = {}
        narration_summary = ""

        try:
            # Extract parameters
            limit = args.get("limit")
            offset = args.get("offset", 0)
            fields = args.get("fields")
            use_refs = args.get("use_refs", False)

            # Generate query metadata
            query_metadata = self._generate_query_metadata(state)

            if topic == "status":
                facts, narration_summary = self._get_status_info(
                    target, state, detail_level, fields
                )
            elif topic == "inventory":
                facts, narration_summary = self._get_inventory_info(
                    target, state, detail_level, limit, offset, fields
                )
            elif topic == "zone":
                facts, narration_summary = self._get_zone_info(
                    target, state, detail_level, limit, offset, fields
                )
            elif topic == "scene":
                facts, narration_summary = self._get_scene_info(
                    state, detail_level, fields
                )
            elif topic == "effects":
                facts, narration_summary = self._get_effects_info(
                    target, state, detail_level, fields
                )
            elif topic == "clocks":
                facts, narration_summary = self._get_clocks_info(
                    state, detail_level, limit, offset, fields
                )
            elif topic == "relationships":
                facts, narration_summary = self._get_relationships_info(
                    target, state, detail_level, limit, offset, fields
                )
            elif topic == "rules":
                facts, narration_summary = self._get_rules_info(
                    state, detail_level, fields
                )
            else:
                return ToolResult(
                    ok=False,
                    tool_id="ask_clarifying",
                    args={
                        "question": f"I don't know how to get information about '{topic}'. What would you like to know instead?",
                        "reason": "unknown_topic",
                    },
                    facts={},
                    effects=[],
                    narration_hint={
                        "summary": f"Asked for clarification - unknown topic '{topic}'",
                        "tone_tags": ["helpful"],
                        "salient_entities": [actor] if actor else [],
                    },
                    error_message=f"Unknown topic: {topic}",
                )

            # Add query metadata to facts
            facts["_metadata"] = query_metadata

            # Transform to refs structure if requested
            if use_refs:
                refs = self._build_refs_structure(facts, state)
                thin_facts = self._convert_facts_to_thin_format(facts)
                facts = {"facts": thin_facts, "refs": refs}

        except Exception as e:
            return ToolResult(
                ok=False,
                tool_id="get_info",
                args=args,
                facts={},
                effects=[],
                narration_hint={},
                error_message=f"Error gathering {topic} information: {str(e)}",
            )

        return ToolResult(
            ok=True,
            tool_id="get_info",
            args=args,
            facts=facts,
            effects=[],  # Read-only tool, no effects
            narration_hint={
                "summary": narration_summary,
                "tone_tags": ["informative", "status"],
                "sentences_max": 2 if detail_level == "brief" else 4,
                "salient_entities": [target] if target else [],
            },
        )

    # Helper methods for size control
    def _filter_fields(
        self, data: Dict[str, Any], fields: Optional[List[str]]
    ) -> Dict[str, Any]:
        """Filter dictionary to only include specified fields (preserves _metadata)."""
        if fields is None:
            return data

        # Always preserve metadata
        filtered = {key: value for key, value in data.items() if key in fields}
        if "_metadata" in data:
            filtered["_metadata"] = data["_metadata"]
        return filtered

    def _apply_pagination(
        self, items: List[Any], limit: Optional[int], offset: int
    ) -> tuple[List[Any], Dict[str, Any]]:
        """Apply pagination to a list and return pagination metadata."""
        total_count = len(items)

        # Apply offset
        if offset >= total_count:
            paginated_items = []
        else:
            paginated_items = items[offset:]

        # Apply limit
        if limit is not None and limit > 0:
            paginated_items = paginated_items[:limit]

        # Create pagination metadata
        pagination = {
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "returned_count": len(paginated_items),
            "has_more": offset + len(paginated_items) < total_count,
        }

        return paginated_items, pagination

    def _generate_query_metadata(self, state: GameState) -> Dict[str, Any]:
        """Generate query metadata for audit and replay support."""
        # Generate a deterministic snapshot ID based on key state elements
        state_fingerprint = f"r{state.scene.round}_t{state.scene.turn_index}_{len(state.entities)}_{len(state.clocks)}"
        # Use deterministic hash function for consistent snapshot IDs across sessions
        snapshot_hash = hashlib.md5(state_fingerprint.encode("utf-8")).hexdigest()
        snapshot_id = f"snap_{snapshot_hash[:8]}"

        return {
            "schema_version": "1.0.0",
            "query_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "round": state.scene.round,
            "turn_id": f"r{state.scene.round}_t{state.scene.turn_index}",
            "turn_index": state.scene.turn_index,
            "snapshot_id": snapshot_id,
            "current_actor": state.current_actor,
            "scene_id": state.scene.id,
            "game_state_summary": {
                "entity_count": len(state.entities),
                "clock_count": len(state.clocks),
                "pending_action": state.pending_action,
            },
        }

    def _build_refs_structure(
        self, facts: Dict[str, Any], state: GameState
    ) -> Dict[str, Any]:
        """Transform facts into refs structure, extracting entity/zone/clock details into refs."""
        refs = {"entities": {}, "zones": {}, "clocks": {}, "relationships": {}}

        # Find and extract entity references
        entity_ids = set()

        # Collect entity IDs from various fact patterns
        if "entity_id" in facts:
            entity_ids.add(facts["entity_id"])
        if "entities" in facts and isinstance(facts["entities"], list):
            entity_ids.update(facts["entities"])
        if "entity_details" in facts and isinstance(facts["entity_details"], dict):
            entity_ids.update(facts["entity_details"].keys())

        # Build entity refs
        for entity_id in entity_ids:
            if entity_id in state.entities:
                entity = state.entities[entity_id]
                refs["entities"][entity_id] = {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "current_zone": entity.current_zone,
                }

                # Add type-specific fields
                if entity.type in ("pc", "npc"):
                    living_entity = cast(Union[PC, NPC], entity)
                    refs["entities"][entity_id].update(
                        {
                            "hp": living_entity.hp.current,
                            "max_hp": living_entity.hp.max,
                            "marks": list(getattr(living_entity, "marks", {}).keys()),
                            "inventory": getattr(living_entity, "inventory", []),
                        }
                    )
                elif entity.type == "object":
                    object_entity = cast(ObjectEntity, entity)
                    refs["entities"][entity_id][
                        "interactable"
                    ] = object_entity.interactable

        # Find and extract zone references
        zone_ids = set()
        if "zone_id" in facts:
            zone_ids.add(facts["zone_id"])
        if "adjacent_zones" in facts and isinstance(facts["adjacent_zones"], list):
            zone_ids.update(facts["adjacent_zones"])

        # Add current zone of referenced entities
        for entity_id in entity_ids:
            if entity_id in state.entities:
                zone_ids.add(state.entities[entity_id].current_zone)

        # Build zone refs
        for zone_id in zone_ids:
            if zone_id in state.zones:
                zone = state.zones[zone_id]
                refs["zones"][zone_id] = {
                    "id": zone.id,
                    "name": zone.name,
                    "description": zone.description,
                    "adjacent_zones": zone.adjacent_zones,
                }

        # Find and extract clock references
        clock_ids = set()
        if "active_clocks" in facts and isinstance(facts["active_clocks"], dict):
            for clock_id in facts["active_clocks"].keys():
                if not clock_id.startswith("[hidden"):  # Skip hidden placeholders
                    clock_ids.add(clock_id)

        # Build clock refs
        for clock_id in clock_ids:
            if clock_id in state.clocks:
                clock_data = state.clocks[clock_id]
                # Handle both Clock objects and dictionary formats
                from .game_state import Clock

                if isinstance(clock_data, Clock):
                    refs["clocks"][clock_id] = {
                        "id": clock_id,
                        "value": clock_data.value,
                        "max": clock_data.maximum,
                        "min": clock_data.minimum,
                        "source": clock_data.source or "unknown",
                    }
                else:
                    refs["clocks"][clock_id] = {
                        "id": clock_id,
                        "value": clock_data["value"],
                        # Handle both legacy (maximum/minimum) and modern (max/min) key styles
                        "max": clock_data.get("max", clock_data.get("maximum", 10)),
                        "min": clock_data.get("min", clock_data.get("minimum", 0)),
                        "source": clock_data.get("source", "unknown"),
                    }

        # Find and extract relationship references
        if "relationships" in facts and isinstance(facts["relationships"], dict):
            refs["relationships"] = facts["relationships"].copy()

        # Remove empty refs sections
        refs = {k: v for k, v in refs.items() if v}

        return refs

    def _convert_facts_to_thin_format(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Convert detailed facts to thin ID-based format for refs structure."""
        thin_facts = facts.copy()

        # Convert entity_details to entity_ids
        if "entity_details" in thin_facts:
            thin_facts["entity_ids"] = list(thin_facts["entity_details"].keys())
            del thin_facts["entity_details"]

        # Convert active_clocks to clock_ids (excluding hidden placeholders)
        if "active_clocks" in thin_facts:
            clock_ids = [
                cid
                for cid in thin_facts["active_clocks"].keys()
                if not cid.startswith("[hidden")
            ]
            if clock_ids:
                thin_facts["clock_ids"] = clock_ids
            del thin_facts["active_clocks"]

        # Convert item_details to item_ids
        if "item_details" in thin_facts:
            thin_facts["item_ids"] = list(thin_facts["item_details"].keys())
            del thin_facts["item_details"]

        # Convert relationship details to source_ids
        if "relationships" in thin_facts and isinstance(
            thin_facts["relationships"], dict
        ):
            source_ids = list(thin_facts["relationships"].keys())
            if source_ids:
                thin_facts["relationship_source_ids"] = source_ids
            del thin_facts["relationships"]

        return thin_facts

    def _get_status_info(
        self,
        target: str,
        state: GameState,
        detail_level: str,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get status information about an entity with perception filtering."""
        if target not in state.entities:
            raise ValueError(f"Entity {target} not found")

        entity = state.entities[target]
        # Note: Visibility is checked at the main execution level

        facts: Dict[str, Any] = {
            "topic": "status",
            "entity_id": target,
            "entity_type": entity.type,
            "id": entity.id,  # Include ID for consistency
            "name": entity.name,
            "position": entity.current_zone,
        }

        # Add HP for living entities
        if entity.type in ("pc", "npc"):
            living_entity = cast(Union[PC, NPC], entity)
            facts["hp"] = living_entity.hp.current
            facts["max_hp"] = living_entity.hp.max
            facts["guard"] = getattr(living_entity, "guard", 0)

            # Add marks in new format (sorted)
            marks = getattr(living_entity, "marks", {})
            if marks:
                facts["marks"] = sorted(marks.keys())
            else:
                facts["marks"] = []

            # Add tags if any (sorted)
            if entity.tags:
                facts["tags"] = sorted(entity.tags.keys())
            else:
                facts["tags"] = []

            if detail_level == "full":
                facts["stats"] = {
                    "strength": living_entity.stats.strength,
                    "dexterity": living_entity.stats.dexterity,
                    "constitution": living_entity.stats.constitution,
                    "intelligence": living_entity.stats.intelligence,
                    "wisdom": living_entity.stats.wisdom,
                    "charisma": living_entity.stats.charisma,
                }
                facts["conditions"] = getattr(living_entity, "conditions", {})

        elif entity.type == "object":
            obj_entity = cast(ObjectEntity, entity)
            facts["interactable"] = obj_entity.interactable
            facts["locked"] = getattr(obj_entity, "locked", False)
            if detail_level == "full":
                facts["description"] = getattr(obj_entity, "description", "")

        elif entity.type == "item":
            item_entity = cast(ItemEntity, entity)
            facts["weight"] = item_entity.weight
            facts["value"] = item_entity.value
            if detail_level == "full":
                facts["description"] = getattr(item_entity, "description", "")

        # Generate summary
        if entity.type in ("pc", "npc"):
            living_entity = cast(Union[PC, NPC], entity)
            summary = f"{entity.name} is at {facts['hp']}/{facts['max_hp']} HP in {entity.current_zone}"
            if facts["tags"]:
                summary += f" with tags: {', '.join(facts['tags'])}"
        else:
            summary = f"{entity.name} is a {entity.type} in {entity.current_zone}"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_inventory_info(
        self,
        target: str,
        state: GameState,
        detail_level: str,
        limit: Optional[int] = None,
        offset: int = 0,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get inventory information with deterministic ordering."""
        if target not in state.entities:
            raise ValueError(f"Entity {target} not found")

        entity = state.entities[target]

        if entity.type not in ("pc", "npc"):
            raise ValueError(f"Entity {target} does not have inventory")

        living_entity = cast(Union[PC, NPC], entity)
        inventory = getattr(living_entity, "inventory", [])

        # Sort inventory for deterministic ordering
        sorted_inventory = sorted(inventory)

        # Apply pagination
        paginated_inventory, pagination = self._apply_pagination(
            sorted_inventory, limit, offset
        )

        facts: Dict[str, Any] = {
            "topic": "inventory",
            "entity_id": target,
            "items": paginated_inventory,
            "item_count": len(paginated_inventory),
        }

        # Add pagination metadata if pagination was applied
        if limit is not None or offset > 0:
            facts["pagination"] = pagination

        if detail_level == "full" and paginated_inventory:
            # Try to get item details from the item registry with ID+name format
            item_details = {}
            unique_items = sorted(
                set(paginated_inventory)
            )  # Sort unique items from paginated list
            for item_id in unique_items:
                count = paginated_inventory.count(item_id)
                item_info = self.item_registry.get(item_id, {})
                item_details[item_id] = {
                    "id": item_id,  # Include ID for consistency
                    "count": count,
                    "name": item_info.get("name", item_id),
                    "description": item_info.get("description", ""),
                }
            facts["item_details"] = item_details

        if paginated_inventory:
            unique_items = sorted(set(paginated_inventory))
            if limit is not None and pagination["has_more"]:
                summary = f"{entity.name} carries {pagination['total_count']} total items (showing {len(paginated_inventory)}): {', '.join(unique_items)}"
            else:
                summary = f"{entity.name} carries {len(paginated_inventory)} items: {', '.join(unique_items)}"
        else:
            if limit is not None and pagination["total_count"] > 0:
                summary = f"{entity.name} carries {pagination['total_count']} items (none in this page)"
            else:
                summary = f"{entity.name} carries no items"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_zone_info(
        self,
        target: str,
        state: GameState,
        detail_level: str,
        limit: Optional[int] = None,
        offset: int = 0,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get zone information with perception filtering."""
        # If target is an entity, get their zone; if target is a zone ID, use that
        if target in state.zones:
            zone_id = target
        elif target in state.entities:
            zone_id = state.entities[target].current_zone
        else:
            raise ValueError(f"Cannot determine zone for target {target}")

        if zone_id not in state.zones:
            raise ValueError(f"Zone {zone_id} not found")

        zone = state.zones[zone_id]

        # Check if zone itself is visible
        if not is_zone_visible_to(zone, state.scene):
            # Return redacted info instead of failing
            facts: Dict[str, Any] = {
                "topic": "zone",
                "zone_id": zone_id,
                "name": "[hidden]",
                "entities": [],
                "entity_count": 0,
                "adjacent_zones": [],
                "blocked_exits": [],
            }
            return facts, f"Zone information is hidden"

        # Get entities in this zone with visibility filtering
        all_entities_in_zone = [
            entity_id
            for entity_id, entity in state.entities.items()
            if entity.current_zone == zone_id
        ]

        # Filter visible entities and sort deterministically
        visible_entities = [
            entity_id
            for entity_id in all_entities_in_zone
            if is_visible_to(state.entities[entity_id], state.scene)
        ]

        # Sort entities by (type, name, id) for consistency
        def entity_sort_key(entity_id: str):
            entity = state.entities[entity_id]
            return (entity.type, entity.name.lower(), entity.id)

        visible_entities.sort(key=entity_sort_key)

        # Apply pagination to entities
        paginated_entities, pagination = self._apply_pagination(
            visible_entities, limit, offset
        )

        facts: Dict[str, Any] = {
            "topic": "zone",
            "zone_id": zone_id,
            "name": zone.name,
            "entities": paginated_entities,
            "entity_count": len(paginated_entities),
            "adjacent_zones": sorted(zone.adjacent_zones),  # Sort for consistency
            "blocked_exits": sorted(
                getattr(zone, "blocked_exits", [])
            ),  # Sort for consistency
        }

        # Add pagination metadata if pagination was applied
        if limit is not None or offset > 0:
            facts["pagination"] = pagination

        if detail_level == "full":
            facts["description"] = zone.description
            # Add entity details for visible entities only, with ID+name format
            entity_details = {}
            for entity_id in paginated_entities:  # Use paginated list
                entity = state.entities[entity_id]
                entity_details[entity_id] = {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                }
            facts["entity_details"] = entity_details

        if paginated_entities:
            entity_names = [state.entities[eid].name for eid in paginated_entities]
            if limit is not None and pagination["has_more"]:
                hidden_count = len(all_entities_in_zone) - len(visible_entities)
                summary = f"{zone.name} contains {pagination['total_count']} visible entities (showing {len(paginated_entities)}): {', '.join(entity_names)}"
                if hidden_count > 0:
                    summary += f" (+{hidden_count} hidden)"
            else:
                hidden_count = len(all_entities_in_zone) - len(visible_entities)
                summary = f"{zone.name} contains {len(paginated_entities)} visible entities: {', '.join(entity_names)}"
                if hidden_count > 0:
                    summary += f" (+{hidden_count} hidden)"
        else:
            if limit is not None and pagination["total_count"] > 0:
                summary = f"{zone.name} contains {pagination['total_count']} visible entities (none in this page)"
            else:
                summary = f"{zone.name} appears empty"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_scene_info(
        self, state: GameState, detail_level: str, fields: Optional[List[str]] = None
    ) -> tuple[Dict[str, Any], str]:
        """Get scene information."""
        scene = state.scene

        facts: Dict[str, Any] = {
            "topic": "scene",
            "scene_id": scene.id,
            "round": scene.round,
            "turn_index": scene.turn_index,
            "base_dc": scene.base_dc,
            "tags": scene.tags.copy(),
        }

        if detail_level == "full":
            facts["turn_order"] = scene.turn_order
            facts["objective"] = scene.objective
            facts["pending_choice"] = scene.pending_choice
            facts["choice_count_this_turn"] = scene.choice_count_this_turn

        summary = f"Round {scene.round}, scene is {scene.tags.get('alert', 'normal')} alert with {scene.tags.get('lighting', 'normal')} lighting"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_effects_info(
        self,
        target: str,
        state: GameState,
        detail_level: str,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get effects information about an entity."""
        if target not in state.entities:
            raise ValueError(f"Entity {target} not found")

        entity = state.entities[target]

        facts: Dict[str, Any] = {
            "topic": "effects",
            "entity_id": target,
            "active_effects": [],
        }

        # Check for various effects
        if entity.type in ("pc", "npc"):
            living_entity = cast(Union[PC, NPC], entity)

            # Guard effects
            if getattr(living_entity, "guard", 0) > 0:
                guard_duration = getattr(living_entity, "guard_duration", 0)
                facts["active_effects"].append(
                    {
                        "type": "guard",
                        "value": living_entity.guard,
                        "duration": guard_duration,
                    }
                )

            # Mark effects
            marks = getattr(living_entity, "marks", {})
            for mark_key, mark_data in marks.items():
                facts["active_effects"].append(
                    {
                        "type": "mark",
                        "key": mark_key,
                        "tag": mark_data.get("tag", "unknown"),
                        "source": mark_data.get("source", "unknown"),
                        "value": mark_data.get("value", 1),
                    }
                )

            # Tag effects
            if entity.tags:
                for tag_key, tag_value in entity.tags.items():
                    facts["active_effects"].append(
                        {"type": "tag", "key": tag_key, "value": tag_value}
                    )

        effect_count = len(facts["active_effects"])
        if effect_count > 0:
            summary = f"{entity.name} has {effect_count} active effects"
        else:
            summary = f"{entity.name} has no active effects"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_clocks_info(
        self,
        state: GameState,
        detail_level: str,
        limit: Optional[int] = None,
        offset: int = 0,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get clocks information with visibility filtering."""
        facts: Dict[str, Any] = {
            "topic": "clocks",
            "active_clocks": {},
            "clock_count": 0,  # Will be updated after filtering
        }

        # Sort clocks by ID for deterministic ordering
        sorted_clock_ids = sorted(state.clocks.keys())

        # Apply pagination to clock IDs
        paginated_clock_ids, pagination = self._apply_pagination(
            sorted_clock_ids, limit, offset
        )

        visible_clocks = {}
        hidden_clock_count = 0

        for clock_id in paginated_clock_ids:
            clock_data = state.clocks[clock_id]
            if is_clock_visible_to(clock_data):
                # Handle both Clock objects and dictionary formats
                from .game_state import Clock

                if isinstance(clock_data, Clock):
                    clock_info = {
                        "id": clock_id,  # Include ID for consistency
                        "value": clock_data.value,
                        "max": clock_data.maximum,
                        "min": clock_data.minimum,
                    }

                    if detail_level == "full":
                        clock_info.update(
                            {
                                "source": clock_data.source or "unknown",
                                "created_turn": clock_data.created_turn or 0,
                                "last_modified_turn": clock_data.last_modified_turn
                                or 0,
                                "last_modified_by": clock_data.last_modified_by
                                or "unknown",
                                "filled_this_turn": clock_data.filled_this_turn,
                            }
                        )
                else:
                    clock_info = {
                        "id": clock_id,  # Include ID for consistency
                        "value": clock_data["value"],
                        # Handle both legacy (maximum/minimum) and modern (max/min) key styles
                        "max": clock_data.get("max", clock_data.get("maximum", 10)),
                        "min": clock_data.get("min", clock_data.get("minimum", 0)),
                    }

                    if detail_level == "full":
                        clock_info.update(
                            {
                                "source": clock_data.get("source", "unknown"),
                                "created_turn": clock_data.get("created_turn", 0),
                                "last_modified_turn": clock_data.get(
                                    "last_modified_turn", 0
                                ),
                                "last_modified_by": clock_data.get(
                                    "last_modified_by", "unknown"
                                ),
                                "filled_this_turn": clock_data.get(
                                    "filled_this_turn", False
                                ),
                            }
                        )

                visible_clocks[clock_id] = clock_info
            else:
                hidden_clock_count += 1

        # Add redacted placeholders for hidden clocks (deterministic naming)
        for i in range(hidden_clock_count):
            visible_clocks[f"[hidden_clock_{i+1}]"] = {
                "id": f"[hidden_clock_{i+1}]",
                "value": "[hidden]",
                "max": "[hidden]",
                "min": "[hidden]",
            }

        facts: Dict[str, Any] = {
            "topic": "clocks",
            "active_clocks": visible_clocks,
            "clock_count": len(visible_clocks) - hidden_clock_count,
        }

        # Add pagination metadata if pagination was applied
        if limit is not None or offset > 0:
            facts["pagination"] = pagination

        total_clocks = len(state.clocks)
        visible_count = len(visible_clocks) - hidden_clock_count

        if visible_count > 0:
            if limit is not None and pagination["has_more"]:
                summary = f"{visible_count} visible clocks (showing {len(paginated_clock_ids)})"
            else:
                summary = f"{visible_count} visible clocks are running"
            if hidden_clock_count > 0:
                summary += f" (+{hidden_clock_count} hidden)"
        else:
            if limit is not None and pagination["total_count"] > 0:
                summary = f"No visible clocks in this page ({pagination['total_count']} total)"
            else:
                summary = "No visible clocks" + (
                    f" ({hidden_clock_count} hidden)" if hidden_clock_count > 0 else ""
                )

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_relationships_info(
        self,
        target: str,
        state: GameState,
        detail_level: str,
        limit: Optional[int] = None,
        offset: int = 0,
        fields: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Get relationships and marks information with deterministic ordering."""
        if target not in state.entities:
            raise ValueError(f"Entity {target} not found")

        entity = state.entities[target]

        facts: Dict[str, Any] = {
            "topic": "relationships",
            "entity_id": target,
            "relationships": {},
        }

        if entity.type in ("pc", "npc"):
            living_entity = cast(Union[PC, NPC], entity)
            marks = getattr(living_entity, "marks", {})

            # Group marks by source to show relationships, sort sources for consistency
            for mark_key, mark_data in marks.items():
                source = mark_data.get("source", "unknown")
                tag = mark_data.get("tag", "unknown")

                if source not in facts["relationships"]:
                    facts["relationships"][source] = []

                relationship = {"tag": tag, "value": mark_data.get("value", 1)}

                if detail_level == "full":
                    relationship.update(
                        {
                            "created_turn": mark_data.get("created_turn", 0),
                            "consumes": mark_data.get("consumes", True),
                        }
                    )

                facts["relationships"][source].append(relationship)

            # Sort relationships within each source by tag name for consistency
            for source in facts["relationships"]:
                facts["relationships"][source].sort(key=lambda r: r["tag"])

        # Apply pagination to relationships if requested
        if limit is not None or offset > 0:
            all_relationships = []
            for source in sorted(facts["relationships"].keys()):
                for rel in facts["relationships"][source]:
                    all_relationships.append((source, rel))

            paginated_relationships, pagination = self._apply_pagination(
                all_relationships, limit, offset
            )

            # Rebuild relationships dict from paginated results
            paginated_relationships_dict = {}
            for source, rel in paginated_relationships:
                if source not in paginated_relationships_dict:
                    paginated_relationships_dict[source] = []
                paginated_relationships_dict[source].append(rel)

            facts["relationships"] = paginated_relationships_dict
            facts["pagination"] = pagination

        relationship_count = len(facts["relationships"])
        if relationship_count > 0:
            # Sort sources for deterministic output
            sources = sorted(facts["relationships"].keys())
            if (
                limit is not None
                and "pagination" in facts
                and facts["pagination"]["has_more"]
            ):
                summary = f"{entity.name} has relationships with {facts['pagination']['total_count']} total entities (showing {relationship_count}): {', '.join(sources)}"
            else:
                summary = f"{entity.name} has relationships with {relationship_count} entities: {', '.join(sources)}"
        else:
            if (
                limit is not None
                and "pagination" in facts
                and facts["pagination"]["total_count"] > 0
            ):
                summary = f"{entity.name} has {facts['pagination']['total_count']} relationships (none in this page)"
            else:
                summary = f"{entity.name} has no recorded relationships"

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

    def _get_rules_info(
        self, state: GameState, detail_level: str, fields: Optional[List[str]] = None
    ) -> tuple[Dict[str, Any], str]:
        """Get rules and mechanics information."""
        facts: Dict[str, Any] = {
            "topic": "rules",
            "base_dc": state.scene.base_dc,
            "current_round": state.scene.round,
        }

        if detail_level == "full":
            facts.update(
                {
                    "dc_ranges": {
                        "trivial": "5-8",
                        "easy": "9-11",
                        "moderate": "12-14",
                        "hard": "15-17",
                        "extreme": "18-20",
                    },
                    "outcomes": {
                        "crit_success": "Natural 20 or margin >= 5",
                        "success": "Margin >= 0",
                        "partial": "Margin >= -3",
                        "fail": "Margin < -3",
                    },
                    "style_domains": {
                        "d4": "Careful/precise actions",
                        "d6": "Balanced approach",
                        "d8": "Bold/risky actions",
                    },
                    "scene_tags": state.scene.tags.copy(),
                }
            )

        summary = (
            f"Base DC is {state.scene.base_dc}, currently round {state.scene.round}"
        )

        # Apply field filtering
        facts = self._filter_fields(facts, fields)

        return facts, summary

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

    # Effect Type Registry System
    EFFECT_REGISTRY = {
        "hp": "_apply_hp_effect",
        "guard": "_apply_guard_effect",
        "position": "_apply_position_effect",
        "mark": "_apply_mark_effect",
        "inventory": "_apply_inventory_effect",
        "clock": "_apply_clock_effect",
        "tag": "_apply_tag_effect",
        "resource": "_apply_resource_effect",
        "meta": "_apply_meta_effect",
    }

    # Reaction rules for cascading effects
    REACTION_RULES = {
        # HP-based reactions
        "hp_zero": {
            "trigger": {"type": "hp", "condition": "after.hp.current <= 0"},
            "effects": [{"type": "tag", "add": "unconscious", "source": "hp_reaction"}],
        },
        "hp_critical": {
            "trigger": {
                "type": "hp",
                "condition": "after.hp.current <= 3 and after.hp.current > 0 and before.hp.current > 3",
            },
            "effects": [{"type": "tag", "add": "bloodied", "source": "hp_reaction"}],
        },
        # Mark-based reactions
        "fear_guard_penalty": {
            "trigger": {"type": "mark", "condition": "effect.add == 'fear'"},
            "effects": [{"type": "guard", "delta": -1, "source": "fear_reaction"}],
        },
        "confidence_guard_bonus": {
            "trigger": {"type": "mark", "condition": "effect.add == 'confidence'"},
            "effects": [{"type": "guard", "delta": 1, "source": "confidence_reaction"}],
        },
        # Position-based reactions
        "zone_visibility_update": {
            "trigger": {
                "type": "position",
                "condition": "True",
            },  # Always trigger on position change
            "effects": [],  # Handled specially - visibility updates are automatic
        },
    }

    def _dispatch_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch effect to appropriate handler using registry."""
        handler_name = self.EFFECT_REGISTRY.get(effect.type)
        if handler_name is None:
            # Unknown effect types are skipped gracefully for plugin extensibility
            return self._create_enhanced_log_entry(
                effect=effect,
                before={},
                after={},
                ok=True,  # Changed to True so unknown effects don't fail transactions
                error=f"Unknown effect type: {effect.type} (skipped)",
                actor=actor,
                seed=seed,
                state=state,
            )

        handler = getattr(self, handler_name, None)
        if handler is None:
            return self._create_enhanced_log_entry(
                effect=effect,
                before={},
                after={},
                ok=False,
                error=f"Handler {handler_name} not found for effect type: {effect.type}",
                actor=actor,
                seed=seed,
                state=state,
            )

        return handler(effect, state, actor, seed)

    def register_effect_handler(
        self, effect_type: str, handler_method_name: str
    ) -> None:
        """Register a new effect type handler for plugin extensibility."""
        self.EFFECT_REGISTRY[effect_type] = handler_method_name

    def get_registered_effect_types(self) -> List[str]:
        """Get list of all registered effect types."""
        return list(self.EFFECT_REGISTRY.keys())

    # Apply Effects Tool Helper Functions
    def _create_enhanced_log_entry(
        self,
        effect: Effect,
        before: Dict[str, Any],
        after: Dict[str, Any],
        ok: bool = True,
        error: Optional[str] = None,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
        rolled: Optional[List[int]] = None,
        state: Optional[GameState] = None,
        dice_log: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create enhanced log entry with all replay and audit fields."""
        # Calculate impact level (magnitude of change) from actual results
        impact_level = 0
        resolved_delta = 0

        # Try to get resolved delta from dice log or before/after values
        if dice_log and len(dice_log) > 0:
            # Use the resolved dice total
            resolved_delta = dice_log[0].get("total", 0)
            impact_level = abs(resolved_delta)
        elif effect.delta is not None:
            # Try to resolve delta - handle both numbers and dice expressions
            try:
                if isinstance(effect.delta, str) and any(
                    char in str(effect.delta) for char in "d+-"
                ):
                    # Dice expression - estimate impact from before/after if available
                    if "hp" in before and "hp" in after:
                        resolved_delta = after["hp"] - before["hp"]
                        impact_level = abs(resolved_delta)
                    elif len(before) == 1 and len(after) == 1:
                        # Single field change
                        before_val = list(before.values())[0]
                        after_val = list(after.values())[0]
                        if isinstance(before_val, (int, float)) and isinstance(
                            after_val, (int, float)
                        ):
                            resolved_delta = after_val - before_val
                            impact_level = abs(resolved_delta)
                else:
                    # Regular number
                    resolved_delta = int(effect.delta)
                    impact_level = abs(resolved_delta)
            except (ValueError, TypeError):
                # Fallback for unparseable values
                impact_level = 1
        elif ok and effect.type in ("position", "mark", "tag"):
            impact_level = 1  # Binary change

        # Generate human-readable summary using resolved delta
        summary = ""
        if ok:
            target_name = effect.target
            if "." in target_name:
                target_name = target_name.split(".")[-1].title()

            if effect.type == "hp":
                if resolved_delta > 0:
                    summary = f"{target_name} healed {resolved_delta} HP"
                elif resolved_delta < 0:
                    summary = f"{target_name} took {abs(resolved_delta)} damage"
                else:
                    summary = f"{target_name} HP unchanged"
            elif effect.type == "guard":
                if resolved_delta > 0:
                    summary = f"{target_name} gained {resolved_delta} guard"
                elif resolved_delta < 0:
                    summary = f"{target_name} lost {abs(resolved_delta)} guard"
                else:
                    summary = f"{target_name} guard unchanged"
            elif effect.type == "position":
                summary = f"{target_name} moved to {effect.to}"
            elif effect.type == "mark":
                if effect.add:
                    summary = f"{target_name} gained {effect.add} mark"
                elif effect.remove:
                    summary = f"{target_name} lost {effect.remove} mark"
            elif effect.type == "inventory":
                item_name = effect.id or "item"
                if resolved_delta > 0:
                    summary = f"{target_name} gained {resolved_delta} {item_name}"
                elif resolved_delta < 0:
                    summary = f"{target_name} lost {abs(resolved_delta)} {item_name}"
                else:
                    summary = f"{target_name} {item_name} unchanged"
            elif effect.type == "clock":
                clock_name = effect.id or "clock"
                if resolved_delta > 0:
                    summary = f"{clock_name} advanced by {resolved_delta}"
                elif resolved_delta < 0:
                    summary = f"{clock_name} decreased by {abs(resolved_delta)}"
                else:
                    summary = f"{clock_name} unchanged"
            elif effect.type == "tag":
                if effect.add:
                    summary = f"{target_name} gained {effect.add} tag"
                elif effect.remove:
                    summary = f"{target_name} lost {effect.remove} tag"
            else:
                summary = f"{target_name} {effect.type} changed"
        else:
            summary = (
                f"Failed to apply {effect.type} effect: {error or 'unknown error'}"
            )

        return {
            "effect": effect.model_dump(),
            "before": before,
            "after": after,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": ok,
            "error": error,
            # Enhanced fields
            "seed": seed,
            "actor": actor or effect.source,
            "round": state.scene.round if state else None,
            "rolled": dice_log or rolled or [],
            "summary": summary,
            "impact_level": impact_level,
        }

    def _validate_effect(self, effect: Effect, state: GameState) -> Optional[str]:
        """Validate a single effect. Returns error message if invalid, None if valid."""
        # Check target exists - allow known non-entity targets and target-less effects
        if effect.target is not None:
            # Allow scene/global targets, entity targets, and special patterns for certain effect types
            if (
                effect.target not in state.entities
                and effect.target not in ("scene", "global")
                and effect.type != "meta"
                and not (effect.type == "clock" and effect.target.startswith("clock."))
            ):
                return f"Entity {effect.target} not found"

        # Type-specific validation
        if effect.type == "hp":
            if effect.target not in state.entities:
                return f"HP effect target not found: {effect.target}"
            entity = state.entities[effect.target]
            if entity.type not in ("pc", "npc"):
                return f"HP effect on non-creature: {entity.type}"
            if effect.delta is None:
                return "HP effect requires delta"

        elif effect.type == "position":
            if effect.to is None:
                return "Position effect requires 'to' field"
            if effect.to not in state.zones:
                return f"Target zone {effect.to} not found"

        elif effect.type == "clock":
            if effect.id is None:
                return "Clock effect requires 'id' field"
            if effect.delta is None:
                return "Clock effect requires delta"

        elif effect.type == "inventory":
            if effect.id is None:
                return "Inventory effect requires 'id' field"
            if effect.delta is None:
                return "Inventory effect requires delta"

        elif effect.type in ("mark", "tag"):
            if effect.add is None and effect.remove is None:
                return f"{effect.type} effect requires either 'add' or 'remove'"

        elif effect.type == "guard":
            if effect.delta is None:
                return "Guard effect requires delta"

        elif effect.type == "resource":
            if effect.id is None:
                return "Resource effect requires 'id' field"
            if effect.delta is None:
                return "Resource effect requires delta"

        return None

    def _create_snapshot(
        self, state: GameState, effects: List[Effect]
    ) -> Dict[str, Any]:
        """Create a snapshot of state before applying effects for rollback."""
        snapshot = {}

        # Snapshot all entities that might be affected
        for effect in effects:
            if effect.target in state.entities:
                entity = state.entities[effect.target]
                snapshot[effect.target] = entity.model_copy(deep=True)

        # Snapshot clocks if any clock effects
        clock_effects = [e for e in effects if e.type == "clock"]
        if clock_effects:
            snapshot["clocks"] = {k: v.copy() for k, v in state.clocks.items()}

        # Snapshot scene-level structures that can be mutated during effect application
        scene_effects = [
            e for e in effects if e.target == "scene" or e.type in ("tag", "timed")
        ]
        if scene_effects:
            # Snapshot scene tags (can be mutated by tag effects)
            if hasattr(state.scene, "tags"):
                snapshot["scene_tags"] = state.scene.tags.copy()

            # Snapshot pending effects (can be mutated by timed effects)
            if hasattr(state.scene, "pending_effects"):
                snapshot["scene_pending_effects"] = [
                    (
                        effect.model_copy()
                        if hasattr(effect, "model_copy")
                        else dict(effect)
                    )
                    for effect in state.scene.pending_effects
                ]

        return snapshot

    def _apply_hp_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply HP effect and return enhanced log entry with dice expression support."""
        import random

        entity = state.entities[effect.target]
        living_entity = cast(Union[PC, NPC], entity)

        old_hp = living_entity.hp.current

        # Handle dice expressions in delta field
        dice_log = []
        if effect.delta is not None:
            if isinstance(effect.delta, str) and any(
                char in str(effect.delta) for char in "d+-"
            ):
                # Delta contains dice expression - roll it
                if seed is not None:
                    random.seed(seed)
                delta = self._roll_dice_expression_with_details(
                    str(effect.delta), random, dice_log
                )
            else:
                # Delta is already a number
                delta = int(effect.delta)
        else:
            delta = 0

        new_hp = max(0, min(living_entity.hp.max, old_hp + delta))

        # Update entity
        from .game_state import HP

        updated_entity = living_entity.model_copy(
            update={"hp": HP(current=new_hp, max=living_entity.hp.max)}
        )
        state.entities[effect.target] = updated_entity

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"hp": old_hp},
            after={"hp": new_hp},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
            dice_log=dice_log,  # Pass dice results for storage
        )

    def _apply_guard_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply guard effect and return enhanced log entry with dice expression support."""
        import random

        entity = state.entities[effect.target]
        living_entity = cast(Union[PC, NPC], entity)

        old_guard = getattr(living_entity, "guard", 0)

        # Handle dice expressions in delta field
        dice_log = []
        if effect.delta is not None:
            if isinstance(effect.delta, str) and any(
                char in str(effect.delta) for char in "d+-"
            ):
                # Delta contains dice expression - roll it
                if seed is not None:
                    random.seed(seed)
                delta = self._roll_dice_expression_with_details(
                    str(effect.delta), random, dice_log
                )
            else:
                # Delta is already a number
                delta = int(effect.delta)
        else:
            delta = 0

        new_guard = old_guard + delta

        # Update entity
        updated_entity = living_entity.model_copy(update={"guard": new_guard})
        state.entities[effect.target] = updated_entity

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"guard": old_guard},
            after={"guard": new_guard},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
            dice_log=dice_log,
        )

    def _apply_position_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply position effect and return enhanced log entry."""
        entity = state.entities[effect.target]
        old_zone = entity.current_zone
        new_zone = effect.to

        # Update entity position
        updated_entity = entity.model_copy(update={"current_zone": new_zone})
        state.entities[effect.target] = updated_entity

        # Update visibility for all actors
        from .effects import _update_visibility

        _update_visibility(state)

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"zone": old_zone},
            after={"zone": new_zone},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
        )

    def _apply_mark_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply mark effect and return enhanced log entry."""
        entity = state.entities[effect.target]
        living_entity = cast(Union[PC, NPC], entity)

        old_marks = getattr(living_entity, "marks", {}).copy()
        new_marks = old_marks.copy()

        if effect.add:
            new_marks[effect.add] = {"source": effect.source or "unknown"}
        if effect.remove and effect.remove in new_marks:
            del new_marks[effect.remove]

        updated_entity = living_entity.model_copy(update={"marks": new_marks})
        state.entities[effect.target] = updated_entity

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"marks": old_marks},
            after={"marks": new_marks},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
        )

    def _apply_inventory_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply inventory effect and return enhanced log entry with dice expression support."""
        import random

        entity = state.entities[effect.target]
        living_entity = cast(Union[PC, NPC], entity)

        old_inventory = living_entity.inventory.copy()
        new_inventory = old_inventory.copy()

        # Handle dice expressions in delta field
        dice_log = []
        if effect.delta is not None:
            if isinstance(effect.delta, str) and any(
                char in str(effect.delta) for char in "d+-"
            ):
                # Delta contains dice expression - roll it
                if seed is not None:
                    random.seed(seed)
                delta = self._roll_dice_expression_with_details(
                    str(effect.delta), random, dice_log
                )
            else:
                # Delta is already a number
                delta = int(effect.delta)
        else:
            delta = 0

        item_id = effect.id

        if item_id is None:
            return self._create_enhanced_log_entry(
                effect=effect,
                before={"inventory": old_inventory},
                after={"inventory": old_inventory},
                ok=False,
                error="Item ID is required for inventory effect",
                actor=actor,
                seed=seed,
                state=state,
                dice_log=dice_log,
            )

        if delta > 0:
            # Add items
            for _ in range(delta):
                new_inventory.append(item_id)
        else:
            # Remove items
            items_to_remove = abs(delta)
            for _ in range(items_to_remove):
                if item_id in new_inventory:
                    new_inventory.remove(item_id)
                else:
                    break

        updated_entity = living_entity.model_copy(update={"inventory": new_inventory})
        state.entities[effect.target] = updated_entity

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"inventory": old_inventory},
            after={"inventory": new_inventory},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
            dice_log=dice_log,
        )

    def _apply_clock_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply clock effect and return enhanced log entry."""
        clock_id = effect.id
        if clock_id is None:
            return self._create_enhanced_log_entry(
                effect=effect,
                before={},
                after={},
                ok=False,
                error="Clock ID is required for clock effect",
                actor=actor,
                seed=seed,
                state=state,
            )

        if clock_id not in state.clocks:
            # Create new clock
            state.clocks[clock_id] = {
                "value": 0,
                "max": 10,
                "source": effect.source or "unknown",
                "created_turn": state.scene.round,
            }

        clock = state.clocks[clock_id]

        # Handle both Clock objects and dictionary formats
        from .game_state import Clock

        if isinstance(clock, Clock):
            # Clock object - use attribute access
            old_value = clock.value
            max_value = clock.maximum
            min_value = clock.minimum
        else:
            # Dictionary format - use dictionary access
            old_value = clock["value"]
            # Handle both legacy (maximum/minimum) and modern (max/min) key styles
            max_value = clock.get("max", clock.get("maximum", 10))
            min_value = clock.get("min", clock.get("minimum", 0))

        # Handle dice expressions in delta field
        dice_log = []
        if effect.delta is not None:
            if isinstance(effect.delta, str) and any(
                char in str(effect.delta) for char in "d+-"
            ):
                # Delta contains dice expression - roll it
                import random

                if seed is not None:
                    random.seed(seed)
                delta = self._roll_dice_expression_with_details(
                    str(effect.delta), random, dice_log
                )
            else:
                # Delta is already a number
                delta = int(effect.delta)
        else:
            delta = 0

        new_value = max(min_value, min(max_value, old_value + delta))

        # Update clock based on its type
        if isinstance(clock, Clock):
            # Clock object - use attribute assignment
            clock.value = new_value
            clock.last_modified_turn = state.scene.round
            clock.last_modified_by = effect.source or "unknown"
        else:
            # Dictionary format - use dictionary assignment
            clock["value"] = new_value
            clock["last_modified_turn"] = state.scene.round
            clock["last_modified_by"] = effect.source or "unknown"

        return self._create_enhanced_log_entry(
            effect=effect,
            before={"value": old_value},
            after={"value": new_value},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
            dice_log=dice_log,
        )

    def _apply_tag_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply tag effect and return enhanced log entry."""
        if effect.target == "scene":
            # Apply to scene
            old_tags = state.scene.tags.copy()
            new_tags = old_tags.copy()

            if effect.add is not None:
                if isinstance(effect.add, dict):
                    # Merge dict payloads - ensure all values are strings
                    for key, value in effect.add.items():
                        new_tags[str(key)] = str(value) if value is not None else "true"
                elif isinstance(effect.add, str):
                    # Handle string payloads
                    new_tags[effect.add] = effect.value or effect.note or "true"
                elif isinstance(effect.add, (list, tuple, set)):
                    # Handle iterable payloads explicitly for type safety
                    for key in effect.add:
                        new_tags[str(key)] = effect.value or effect.note or "true"
                else:
                    # Fallback for other types - convert to string
                    new_tags[str(effect.add)] = effect.value or effect.note or "true"

            if (
                effect.remove
                and isinstance(effect.remove, str)
                and effect.remove in new_tags
            ):
                del new_tags[effect.remove]

            state.scene.tags = new_tags

            return self._create_enhanced_log_entry(
                effect=effect,
                before={"scene_tags": old_tags},
                after={"scene_tags": new_tags},
                ok=True,
                actor=actor,
                seed=seed,
                state=state,
            )
        else:
            # Apply to entity
            entity = state.entities[effect.target]
            old_tags = entity.tags.copy()
            new_tags = old_tags.copy()

            if effect.add is not None:
                if isinstance(effect.add, dict):
                    # Merge dict payloads - ensure all values are strings
                    for key, value in effect.add.items():
                        new_tags[str(key)] = str(value) if value is not None else "true"
                elif isinstance(effect.add, str):
                    # Handle string payloads
                    new_tags[effect.add] = effect.value or effect.note or "true"
                elif isinstance(effect.add, (list, tuple, set)):
                    # Handle iterable payloads explicitly for type safety
                    for key in effect.add:
                        new_tags[str(key)] = effect.value or effect.note or "true"
                else:
                    # Fallback for other types - convert to string
                    new_tags[str(effect.add)] = effect.value or effect.note or "true"

            if (
                effect.remove
                and isinstance(effect.remove, str)
                and effect.remove in new_tags
            ):
                del new_tags[effect.remove]

            updated_entity = entity.model_copy(update={"tags": new_tags})
            state.entities[effect.target] = updated_entity

            return self._create_enhanced_log_entry(
                effect=effect,
                before={"tags": old_tags},
                after={"tags": new_tags},
                ok=True,
                actor=actor,
                seed=seed,
                state=state,
            )

    def _apply_resource_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply resource effect and return enhanced log entry with dice expression support."""
        import random

        entity = state.entities[effect.target]

        resource_id = effect.id
        if resource_id is None:
            return self._create_enhanced_log_entry(
                effect=effect,
                before={},
                after={},
                ok=False,
                error="Resource ID is required for resource effect",
                actor=actor,
                seed=seed,
                state=state,
            )

        # Get or create resources dict
        old_resources = getattr(entity, "resources", {}).copy()
        new_resources = old_resources.copy()

        # Handle dice expressions in delta field
        dice_log = []
        if effect.delta is not None:
            if isinstance(effect.delta, str) and any(
                char in str(effect.delta) for char in "d+-"
            ):
                # Delta contains dice expression - roll it
                if seed is not None:
                    random.seed(seed)
                delta = self._roll_dice_expression_with_details(
                    str(effect.delta), random, dice_log
                )
            else:
                # Delta is already a number
                delta = int(effect.delta)
        else:
            delta = 0

        old_value = old_resources.get(resource_id, 0)
        new_value = max(0, old_value + delta)

        new_resources[resource_id] = new_value

        # For this to work, we'd need to add resources field to entities
        # For now, use tags as a workaround
        updated_entity = entity.model_copy(
            update={"tags": {**entity.tags, f"resource_{resource_id}": str(new_value)}}
        )
        state.entities[effect.target] = updated_entity

        return self._create_enhanced_log_entry(
            effect=effect,
            before={resource_id: old_value},
            after={resource_id: new_value},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
            dice_log=dice_log,
        )

    def _apply_meta_effect(
        self,
        effect: Effect,
        state: GameState,
        actor: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply meta effect and return enhanced log entry."""
        # Meta effects modify metadata - this is a simplified implementation
        return self._create_enhanced_log_entry(
            effect=effect,
            before={},
            after={},
            ok=True,
            actor=actor,
            seed=seed,
            state=state,
        )

    def _rollback_state(self, state: GameState, snapshot: Dict[str, Any]) -> None:
        """Rollback state to snapshot."""
        # Restore entities
        for entity_id, entity_snapshot in snapshot.items():
            if entity_id in ("clocks", "scene_tags", "scene_pending_effects"):
                continue
            if entity_id in state.entities:
                state.entities[entity_id] = entity_snapshot

        # Restore clocks
        if "clocks" in snapshot:
            state.clocks = snapshot["clocks"]

        # Restore scene-level structures
        if "scene_tags" in snapshot:
            state.scene.tags = snapshot["scene_tags"]

        if "scene_pending_effects" in snapshot:
            state.scene.pending_effects = snapshot["scene_pending_effects"]

    def _generate_narration_hint(
        self, logs: List[Dict[str, Any]], actor: Optional[str]
    ) -> Dict[str, Any]:
        """Generate narration hint from effect logs."""
        if not logs:
            return {
                "summary": "No effects applied",
                "tone_tags": ["neutral"],
                "sentences_max": 1,
            }

        # Group effects by target
        targets = {}
        for log in logs:
            effect = log["effect"]
            target = effect["target"]
            if target not in targets:
                targets[target] = []
            targets[target].append(log)

        # Generate summary
        summaries = []
        for target, target_logs in targets.items():
            entity_name = target
            if target in ["scene"]:
                entity_name = "scene"
            elif "." in target:
                # Extract name from ID like "pc.arin" -> "arin"
                entity_name = target.split(".")[-1].title()

            effects_desc = []
            for log in target_logs:
                effect = log["effect"]
                if effect["type"] == "hp":
                    delta = effect.get("delta", 0)
                    # Handle dice expressions that haven't been resolved yet
                    if isinstance(delta, str):
                        # Use log info to determine actual effect
                        if "after" in log and "before" in log:
                            before_hp = log["before"].get("hp", 0)
                            after_hp = log["after"].get("hp", 0)
                            actual_delta = after_hp - before_hp
                            if actual_delta > 0:
                                effects_desc.append(f"healed {actual_delta} HP")
                            elif actual_delta < 0:
                                effects_desc.append(f"took {abs(actual_delta)} damage")
                            else:
                                effects_desc.append("HP unchanged")
                        else:
                            # Fallback - just mention HP effect
                            effects_desc.append("HP affected")
                    else:
                        # Regular integer delta
                        if delta > 0:
                            effects_desc.append(f"healed {delta} HP")
                        else:
                            effects_desc.append(f"took {abs(delta)} damage")
                elif effect["type"] == "position":
                    effects_desc.append(
                        f"moved to {effect.get('to', 'unknown location')}"
                    )
                elif effect["type"] == "mark":
                    if effect.get("add"):
                        effects_desc.append(f"gained {effect['add']} mark")
                    if effect.get("remove"):
                        effects_desc.append(f"lost {effect['remove']} mark")
                else:
                    effects_desc.append(f"{effect['type']} changed")

            if effects_desc:
                summaries.append(f"{entity_name} {' and '.join(effects_desc)}")

        summary = ". ".join(summaries) if summaries else "Effects applied"

        # Determine tone tags
        tone_tags = ["mechanical"]
        if any("damage" in s for s in summaries):
            tone_tags.append("damage")
        if any("healed" in s for s in summaries):
            tone_tags.append("healing")
        if any("moved" in s for s in summaries):
            tone_tags.append("movement")

        return {
            "summary": summary,
            "tone_tags": tone_tags,
            "sentences_max": 2,
            "salient_entities": list(targets.keys()),
        }

    def _generate_audit_trail(
        self, logs: List[Dict[str, Any]], actor: Optional[str], state: GameState
    ) -> str:
        """Generate human-readable audit trail from effect logs."""
        if not logs:
            return "No changes applied"

        # Get current round number
        current_round = getattr(state.scene, "round", 1)

        changes = []
        for log in logs:
            if not log.get("ok", False):
                continue  # Skip failed effects

            effect = log["effect"]
            before = log.get("before", {})
            after = log.get("after", {})

            # Extract entity name from target
            target = effect["target"]
            entity_name = target
            if "." in target:
                entity_name = target.split(".")[-1].title()
            elif target == "scene":
                entity_name = "Scene"

            # Generate change descriptions based on effect type
            if effect["type"] == "hp":
                before_hp = (
                    before.get("hp", {}).get("current", 0)
                    if isinstance(before.get("hp"), dict)
                    else before.get("hp", 0)
                )
                after_hp = (
                    after.get("hp", {}).get("current", 0)
                    if isinstance(after.get("hp"), dict)
                    else after.get("hp", 0)
                )
                if before_hp != after_hp:
                    changes.append(f"{entity_name}.hp: {before_hp} → {after_hp}")

            elif effect["type"] == "position":
                before_zone = before.get("zone", "unknown")
                after_zone = after.get("zone", "unknown")
                if before_zone != after_zone:
                    changes.append(f"{entity_name}.zone: {before_zone} → {after_zone}")

            elif effect["type"] == "guard":
                before_guard = before.get("guard", 0)
                after_guard = after.get("guard", 0)
                if before_guard != after_guard:
                    changes.append(
                        f"{entity_name}.guard: {before_guard} → {after_guard}"
                    )

            elif effect["type"] == "mark":
                # Check if marks actually changed
                before_marks = before.get("marks", {})
                after_marks = after.get("marks", {})

                if effect.get("add"):
                    mark_name = effect["add"]
                    if mark_name in after_marks and mark_name not in before_marks:
                        changes.append(f"{entity_name}.marks: +{mark_name}")

                if effect.get("remove"):
                    mark_name = effect["remove"]
                    if mark_name in before_marks and mark_name not in after_marks:
                        changes.append(f"{entity_name}.marks: -{mark_name}")

            elif effect["type"] == "inventory":
                item_id = effect.get("id", "item")
                delta = effect.get("delta", 0)
                if delta > 0:
                    changes.append(f"{entity_name}.inventory: +{delta} {item_id}")
                elif delta < 0:
                    changes.append(f"{entity_name}.inventory: {delta} {item_id}")

            elif effect["type"] == "clock":
                clock_id = effect.get("id", "clock")
                before_value = before.get("value", 0)
                after_value = after.get("value", 0)
                if before_value != after_value:
                    changes.append(
                        f"{entity_name}.{clock_id}: {before_value} → {after_value}"
                    )

            elif effect["type"] == "tag":
                if effect.get("add"):
                    tag_name = effect["add"]
                    changes.append(f"{entity_name}.tags: +{tag_name}")
                if effect.get("remove"):
                    tag_name = effect["remove"]
                    changes.append(f"{entity_name}.tags: -{tag_name}")

            elif effect["type"] == "resource":
                resource_id = effect.get("id", "resource")
                before_value = before.get("value", 0)
                after_value = after.get("value", 0)
                if before_value != after_value:
                    changes.append(
                        f"{entity_name}.{resource_id}: {before_value} → {after_value}"
                    )

        if not changes:
            return "No visible changes"

        # Format as audit trail
        actor_prefix = f"[{actor}] " if actor else ""
        round_prefix = f"[Round {current_round}] "
        change_list = ", ".join(changes)

        return f"{round_prefix}{actor_prefix}{change_list}"

    def _check_reaction_triggers(self, log_entry: Dict[str, Any]) -> List[Effect]:
        """Check if any reaction rules are triggered by this effect log and return reactive effects."""
        reactive_effects = []

        effect = log_entry["effect"]
        before = log_entry.get("before", {})
        after = log_entry.get("after", {})

        # Only check reactions for successful effects
        if not log_entry.get("ok", False):
            return reactive_effects

        for rule_name, rule in self.REACTION_RULES.items():
            trigger = rule["trigger"]

            # Check if effect type matches
            if trigger["type"] != effect["type"]:
                continue

            # Evaluate condition
            condition = trigger["condition"]
            try:
                # Create evaluation context
                eval_context = {"effect": effect, "before": before, "after": after}

                # Safely evaluate condition
                if self._safe_eval_condition(condition, eval_context):
                    # Create reactive effects
                    for reactive_effect_data in rule["effects"]:
                        # Create Effect object for reactive effect
                        reactive_effect = Effect(
                            type=reactive_effect_data["type"],
                            target=effect["target"],  # Apply to same target by default
                            source=reactive_effect_data.get("source"),
                            delta=reactive_effect_data.get("delta"),
                            add=reactive_effect_data.get("add"),
                            remove=reactive_effect_data.get("remove"),
                            to=reactive_effect_data.get("to"),
                            id=reactive_effect_data.get("id"),
                            cause=f"reaction_{rule_name}",
                            note=f"Triggered by {effect['type']} effect",
                        )
                        reactive_effects.append(reactive_effect)

            except Exception as e:
                # Log but don't fail on reaction evaluation errors
                import logging

                logging.warning(f"Reaction rule {rule_name} evaluation failed: {e}")
                continue

        return reactive_effects

    class SafeExpressionEvaluator:
        """Safe expression evaluator that uses AST parsing to only allow safe operations."""

        # Allowed node types for safe evaluation
        SAFE_NODES = {
            ast.Expression,
            ast.Compare,
            ast.BoolOp,
            ast.UnaryOp,
            ast.BinOp,
            ast.Name,
            ast.Load,
            ast.Attribute,
            ast.Constant,  # ast.Attribute needed for dot notation like target.guard
            ast.And,
            ast.Or,
            ast.Not,
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Mod,
        }

        # Allowed operators
        OPERATORS = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Mod: operator.mod,
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.And: lambda x, y: x and y,
            ast.Or: lambda x, y: x or y,
            ast.Not: operator.not_,
        }

        @classmethod
        def is_safe_node(cls, node):
            """Check if a node type is safe for evaluation."""
            return type(node) in cls.SAFE_NODES

        @classmethod
        def evaluate_safe_expression(
            cls, expression: str, context: Dict[str, Any]
        ) -> bool:
            """Safely evaluate a boolean expression using AST parsing."""
            try:
                # Parse the expression
                tree = ast.parse(expression, mode="eval")

                # Check if all nodes in the tree are safe
                for node in ast.walk(tree):
                    if not cls.is_safe_node(node):
                        raise ValueError(f"Unsafe node type: {type(node).__name__}")

                # Evaluate the expression
                return cls._eval_node(tree.body, context)

            except Exception as e:
                logging.warning(
                    f"Safe expression evaluation failed for '{expression}': {e}"
                )
                return False

        @classmethod
        def _eval_node(cls, node, context: Dict[str, Any]):
            """Recursively evaluate an AST node."""
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.Name):
                # Resolve variable name from context
                return cls._resolve_variable(node.id, context)
            elif isinstance(node, ast.Attribute):
                # Handle attribute access like target.guard or target.hp.current
                obj = cls._eval_node(node.value, context)
                attr_name = node.attr
                if isinstance(obj, dict) and attr_name in obj:
                    return obj[attr_name]
                else:
                    raise ValueError(f"Attribute '{attr_name}' not found in object")
            elif isinstance(node, ast.Load):
                # Load context - this is just used for variable access, no action needed
                return None
            elif isinstance(node, ast.Compare):
                left = cls._eval_node(node.left, context)
                for op, right_node in zip(node.ops, node.comparators):
                    right = cls._eval_node(right_node, context)
                    op_func = cls.OPERATORS.get(type(op))
                    if not op_func:
                        raise ValueError(
                            f"Unsupported comparison operator: {type(op).__name__}"
                        )
                    result = op_func(left, right)
                    if not result:
                        return False
                    left = right  # For chained comparisons
                return True
            elif isinstance(node, ast.BoolOp):
                values = [cls._eval_node(value, context) for value in node.values]
                if isinstance(node.op, ast.And):
                    return all(values)
                elif isinstance(node.op, ast.Or):
                    return any(values)
                else:
                    raise ValueError(
                        f"Unsupported boolean operator: {type(node.op).__name__}"
                    )
            elif isinstance(node, ast.UnaryOp):
                operand = cls._eval_node(node.operand, context)
                if isinstance(node.op, ast.Not):
                    return not operand
                else:
                    raise ValueError(
                        f"Unsupported unary operator: {type(node.op).__name__}"
                    )
            elif isinstance(node, ast.BinOp):
                left = cls._eval_node(node.left, context)
                right = cls._eval_node(node.right, context)
                op_func = cls.OPERATORS.get(type(node.op))
                if not op_func:
                    raise ValueError(
                        f"Unsupported binary operator: {type(node.op).__name__}"
                    )
                return op_func(left, right)
            else:
                raise ValueError(f"Unsupported node type: {type(node).__name__}")

        @classmethod
        def _resolve_variable(cls, var_name: str, context: Dict[str, Any]):
            """Resolve a variable name from the context using dot notation."""
            # Handle direct variable access first (for shorthand variables)
            if var_name in context:
                return context[var_name]

            # Handle dot notation (e.g., target.hp.current)
            if "." in var_name:
                parts = var_name.split(".")
                current = context

                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        raise ValueError(f"Variable '{var_name}' not found in context")

                return current

            # Variable not found
            raise ValueError(f"Variable '{var_name}' not found in context")

    def _safe_eval_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate a reaction condition with limited context using AST parsing."""
        # Handle simple literal boolean values
        if condition == "True":
            return True
        elif condition == "False":
            return False

        # Prepare context for the safe evaluator
        eval_context = {}

        # Handle after.hp.current patterns by flattening nested structures
        if "after" in context:
            after_data = context["after"]
            after_hp = self._safe_get_nested(after_data, "hp.current", None)
            if after_hp is None:
                after_hp = after_data.get("hp", 0)
            eval_context["after"] = {"hp": {"current": after_hp}}

        # Handle before.hp.current patterns
        if "before" in context:
            before_data = context["before"]
            before_hp = self._safe_get_nested(before_data, "hp.current", None)
            if before_hp is None:
                before_hp = before_data.get("hp", 0)
            eval_context["before"] = {"hp": {"current": before_hp}}

        # Handle effect.add patterns
        if "effect" in context:
            effect_data = context["effect"]
            eval_context["effect"] = {"add": effect_data.get("add")}

        # Use the safe expression evaluator
        try:
            return self.SafeExpressionEvaluator.evaluate_safe_expression(
                condition, eval_context
            )
        except Exception as e:
            logging.warning(f"Safe condition evaluation failed for '{condition}': {e}")
            return False

    def _safe_get_nested(
        self, obj: Dict[str, Any], path: str, default: Any = None
    ) -> Any:
        """Safely get nested dictionary values using dot notation."""
        keys = path.split(".")
        current = obj

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def _process_reactive_effects(
        self,
        primary_logs: List[Dict[str, Any]],
        state: GameState,
        actor: Optional[str],
        seed: int,
    ) -> List[Dict[str, Any]]:
        """Process reactive effects triggered by primary effects."""
        reactive_logs = []
        reaction_queue = []

        # Collect all reactive effects from primary effects
        for log_entry in primary_logs:
            reactive_effects = self._check_reaction_triggers(log_entry)
            reaction_queue.extend(reactive_effects)

        # Process reactive effects (with depth limit to prevent infinite loops)
        max_depth = 3
        current_depth = 0

        while reaction_queue and current_depth < max_depth:
            current_depth += 1
            current_batch = reaction_queue.copy()
            reaction_queue.clear()

            for reactive_effect in current_batch:
                try:
                    # Apply reactive effect
                    reactive_log = self._dispatch_effect(
                        reactive_effect, state, f"{actor}_reaction", seed
                    )
                    reactive_logs.append(reactive_log)

                    # Check for second-order reactions
                    if reactive_log.get("ok", False):
                        second_order_effects = self._check_reaction_triggers(
                            reactive_log
                        )
                        reaction_queue.extend(second_order_effects)

                except Exception as e:
                    # Log reactive effect failure but don't fail the transaction
                    reactive_log = self._create_enhanced_log_entry(
                        effect=reactive_effect,
                        before={},
                        after={},
                        ok=False,
                        error=f"Reactive effect failed: {str(e)}",
                        actor=f"{actor}_reaction",
                        seed=seed,
                        state=state,
                    )
                    reactive_logs.append(reactive_log)

        return reactive_logs

    def _evaluate_effect_condition(self, effect: Effect, state: GameState) -> bool:
        """Evaluate whether an effect's condition is met."""
        if not effect.condition:
            return True  # No condition means always apply

        try:
            # Create evaluation context with target entity data
            entity = state.entities.get(effect.target)
            if not entity:
                return False  # Target doesn't exist

            # Build context for condition evaluation - safely access HP for living entities only
            hp_current = 0
            hp_attr = getattr(entity, "hp", None)
            if hp_attr is not None:
                hp_current = getattr(hp_attr, "current", 0)

            context = {
                "target": {
                    "hp": {"current": hp_current},
                    "guard": getattr(entity, "guard", 0),
                    "tags": getattr(entity, "tags", {}),
                    "marks": getattr(entity, "marks", {}),
                },
                "scene": {
                    "round": state.scene.round,
                    "turn_index": state.scene.turn_index,
                },
            }

            # Use similar evaluation logic as reactive effects
            return self._safe_eval_effect_condition(effect.condition, context)

        except Exception as e:
            import logging

            logging.warning(f"Condition evaluation failed for {effect.condition}: {e}")
            return False

    def _safe_eval_effect_condition(
        self, condition: str, context: Dict[str, Any]
    ) -> bool:
        """Safely evaluate an effect condition with target context using AST parsing."""
        # Handle common condition patterns
        if condition == "True":
            return True
        elif condition == "False":
            return False

        # Prepare context for the safe evaluator with both full and shorthand variable names
        eval_context = context.copy()

        # Add shorthand aliases for convenience
        target_data = context.get("target", {})
        if target_data:
            # For shorthand "hp" -> "target.hp.current"
            hp_current = target_data.get("hp", {}).get("current", 0)
            eval_context["hp"] = hp_current

            # For shorthand "guard" -> "target.guard"
            guard_value = target_data.get("guard", 0)
            eval_context["guard"] = guard_value

        # For shorthand "round" -> "scene.round"
        scene_data = context.get("scene", {})
        if scene_data:
            round_value = scene_data.get("round", 1)
            eval_context["round"] = round_value

        # Use the safe expression evaluator
        try:
            return self.SafeExpressionEvaluator.evaluate_safe_expression(
                condition, eval_context
            )
        except Exception as e:
            logging.warning(
                f"Safe effect condition evaluation failed for '{condition}': {e}"
            )
            return False

    def _schedule_timed_effect(
        self, effect: Effect, state: GameState, actor: Optional[str], seed: int
    ) -> None:
        """Schedule a timed effect for future execution."""
        # Calculate when the effect should trigger
        after_rounds = effect.after_rounds or 0
        trigger_round = state.scene.round + after_rounds

        # Create pending effect entry
        pending_effect = PendingEffect(
            effect=effect.model_dump(),
            trigger_round=trigger_round,
            actor=actor,
            seed=seed,
            scheduled_at=state.scene.round,
            id=f"timed_{seed}_{len(state.scene.pending_effects) if hasattr(state.scene, 'pending_effects') else 0}",
        )

        # Add to pending effects queue
        if not hasattr(state.scene, "pending_effects"):
            state.scene.pending_effects = []
        state.scene.pending_effects.append(pending_effect)

    def _process_pending_effects(self, state: GameState) -> List[Dict[str, Any]]:
        """Process any timed effects that should trigger this round."""
        if not hasattr(state.scene, "pending_effects"):
            return []

        current_round = state.scene.round
        triggered_logs = []
        remaining_effects = []

        for pending in state.scene.pending_effects:
            if pending.trigger_round <= current_round:
                # Effect should trigger now
                try:
                    effect_data = pending.effect
                    effect = Effect(**effect_data)
                    actor = pending.actor
                    seed = pending.seed

                    # Apply the timed effect
                    log_entry = self._dispatch_effect(
                        effect, state, f"{actor}_timed", seed
                    )
                    log_entry["timed_effect_id"] = pending.id
                    triggered_logs.append(log_entry)

                except Exception as e:
                    # Log timed effect failure
                    error_log = {
                        "effect": effect_data,
                        "ok": False,
                        "error": f"Timed effect failed: {str(e)}",
                        "actor": f"{pending.actor}_timed",
                        "timed_effect_id": pending.id,
                    }
                    triggered_logs.append(error_log)
            else:
                # Effect not ready yet, keep it in queue
                remaining_effects.append(pending)

        # Update pending effects queue
        state.scene.pending_effects = remaining_effects

        return triggered_logs

    def _execute_apply_effects(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute apply_effects tool with transactional rollback and comprehensive logging."""
        try:
            # Extract and validate arguments
            effects_data = args.get("effects", [])
            actor = args.get("actor")
            transactional = args.get("transactional", True)
            transaction_mode = args.get("transaction_mode", "strict")
            replay_seed = args.get(
                "seed", seed
            )  # For deterministic replay, use args seed or fallback to function seed
            validation_errors = []  # Initialize validation errors list

            # Check if this is a pure empty call or if there are pending timed effects to process
            if not effects_data:
                # Check if there are pending timed effects that could be triggered
                has_pending_effects = (
                    hasattr(state.scene, "pending_effects")
                    and len(state.scene.pending_effects) > 0
                )

                if not has_pending_effects:
                    # Pure empty call with no pending effects - this is an error
                    return ToolResult(
                        ok=False,
                        tool_id="apply_effects",
                        args=args,
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": "No effects to apply",
                            "tone_tags": ["error"],
                            "salient_entities": [],
                        },
                        error_message="No effects provided",
                    )
                # If there are pending effects, continue processing with empty effects list
                effects_data = []

            # Convert dict effects to Effect objects for validation
            effects = []
            for effect_data in effects_data:
                try:
                    if isinstance(effect_data, dict):
                        effect = Effect(**effect_data)
                    else:
                        effect = effect_data  # Already an Effect object
                    effects.append(effect)
                except ValidationError as e:
                    return ToolResult(
                        ok=False,
                        tool_id="apply_effects",
                        args=args,
                        facts={},
                        effects=[],
                        narration_hint={
                            "summary": f"Effect validation failed: {e}",
                            "tone_tags": ["error"],
                            "salient_entities": [],
                        },
                        error_message=f"Effect validation failed: {e}",
                    )

            # Pre-validation phase - handle validation errors based on transaction mode
            validation_errors = []
            for i, effect in enumerate(effects):
                error = self._validate_effect(effect, state)
                if error:
                    validation_errors.append((i, effect, error))

            # Handle validation errors based on transaction mode
            if validation_errors:
                if transaction_mode == "strict":
                    # Strict mode: fail on any validation error
                    first_error = validation_errors[0][2]
                    return ToolResult(
                        ok=False,
                        tool_id="apply_effects",
                        args=args,
                        facts={
                            "applied": 0,
                            "skipped": len(effects),
                            "transaction_mode": transaction_mode,
                            "total_effects": len(effects),
                        },
                        effects=[],
                        narration_hint={
                            "summary": f"Effect validation failed: {first_error}",
                            "tone_tags": ["error"],
                            "salient_entities": [],
                        },
                        error_message=first_error,
                    )
                elif transaction_mode in ["partial", "best_effort"]:
                    # Remove invalid effects, continue with valid ones
                    invalid_indices = {i for i, _, _ in validation_errors}
                    original_effects_count = len(effects)
                    effects = [
                        effect
                        for i, effect in enumerate(effects)
                        if i not in invalid_indices
                    ]

                    # If no valid effects remain and in partial mode, fail
                    if not effects and transaction_mode == "partial":
                        return ToolResult(
                            ok=False,
                            tool_id="apply_effects",
                            args=args,
                            facts={
                                "applied": 0,
                                "skipped": original_effects_count,
                                "transaction_mode": transaction_mode,
                                "total_effects": original_effects_count,
                            },
                            effects=[],
                            narration_hint={
                                "summary": "All effects failed validation",
                                "tone_tags": ["error"],
                                "salient_entities": [],
                            },
                            error_message="All effects failed validation",
                        )

            # Store original total for facts
            original_effects_count = len(args.get("effects", []))

            # Create snapshot for rollback if transactional
            snapshot = None
            if transactional:
                snapshot = self._create_snapshot(state, effects)
            if transactional:
                snapshot = self._create_snapshot(state, effects)

            # Apply effects atomically
            logs = []
            applied_count = 0
            skipped_count = 0
            failed_count = 0  # Track actual failures vs graceful skips
            scheduled_count = 0  # Track effects scheduled for future execution

            # First: Process any pending timed effects that should trigger this round
            timed_effect_logs = self._process_pending_effects(state)
            logs.extend(timed_effect_logs)

            # Process reactive effects for timed effects if any were triggered
            if timed_effect_logs:
                timed_actor = f"{actor or 'unknown'}_timed_reactive"
                reactive_logs_from_timed = self._process_reactive_effects(
                    timed_effect_logs, state, timed_actor, replay_seed
                )
                logs.extend(reactive_logs_from_timed)

            # Count timed effects separately
            timed_applied_count = sum(
                1 for log in timed_effect_logs if log.get("ok", True)
            )

            # Add validation error logs if any effects were skipped due to validation
            if validation_errors:
                for i, effect, error in validation_errors:
                    log_entry = self._create_enhanced_log_entry(
                        effect=effect,
                        before={},
                        after={},
                        ok=False,
                        error=f"Validation failed: {error}",
                        actor=actor,
                        seed=replay_seed,
                        state=state,
                    )
                    logs.append(log_entry)
                    skipped_count += 1
                    failed_count += 1  # Validation failures are real failures

            try:
                for effect in effects:
                    try:
                        # Check if effect has a condition that must be evaluated
                        if effect.condition:
                            if not self._evaluate_effect_condition(effect, state):
                                # Condition not met - skip this effect
                                log_entry = self._create_enhanced_log_entry(
                                    effect=effect,
                                    before={},
                                    after={},
                                    ok=False,
                                    error=f"Condition not met: {effect.condition}",
                                    actor=actor,
                                    seed=replay_seed,
                                    state=state,
                                )
                                logs.append(log_entry)
                                skipped_count += 1
                                continue

                        # Check if effect should be delayed (timed effect)
                        if effect.after_rounds and effect.after_rounds > 0:
                            # Schedule effect for future execution
                            self._schedule_timed_effect(
                                effect, state, actor, replay_seed
                            )

                            # Log that effect was scheduled
                            log_entry = self._create_enhanced_log_entry(
                                effect=effect,
                                before={},
                                after={},
                                ok=True,
                                error=f"Scheduled for +{effect.after_rounds} rounds",
                                actor=actor,
                                seed=replay_seed,
                                state=state,
                            )
                            logs.append(log_entry)
                            scheduled_count += 1  # Count as scheduled, not applied
                            continue

                        # Apply effect immediately using registry dispatch
                        log_entry = self._dispatch_effect(
                            effect, state, actor, replay_seed
                        )

                        logs.append(log_entry)
                        error_msg = log_entry.get("error")
                        if log_entry.get("ok", True) and (
                            error_msg is None
                            or not error_msg.startswith("Unknown effect type")
                        ):
                            applied_count += 1
                        else:
                            skipped_count += 1
                            if error_msg is None or not error_msg.startswith(
                                "Unknown effect type"
                            ):
                                failed_count += (
                                    1  # Only count real failures, not graceful skips
                                )

                    except Exception as e:
                        # Individual effect failed
                        log_entry = self._create_enhanced_log_entry(
                            effect=effect,
                            before={},
                            after={},
                            ok=False,
                            error=str(e),
                            actor=actor,
                            seed=replay_seed,
                            state=state,
                        )
                        logs.append(log_entry)
                        skipped_count += 1
                        failed_count += 1  # Exception failures are real failures

                        # Handle failure based on transaction mode
                        if transactional and transaction_mode == "strict":
                            # Strict mode: any failure causes full rollback
                            if snapshot:
                                self._rollback_state(state, snapshot)
                            return ToolResult(
                                ok=False,
                                tool_id="apply_effects",
                                args=args,
                                facts={
                                    "applied": 0,
                                    "skipped": len(effects),
                                    "transaction_mode": transaction_mode,
                                },
                                effects=[],
                                narration_hint={
                                    "summary": f"Transaction failed: {str(e)}",
                                    "tone_tags": ["error"],
                                    "salient_entities": [],
                                },
                                error_message=f"Transaction failed: {str(e)}",
                            )
                        elif transactional and transaction_mode == "partial":
                            # Partial mode: rollback only failed effect, continue with others
                            # (In this simple implementation, we just continue - no per-effect rollback yet)
                            continue
                        # best_effort mode: log failure and continue without rollback

                # Second pass: Process reactive effects
                reactive_effects_logs = self._process_reactive_effects(
                    logs, state, actor, replay_seed
                )
                logs.extend(reactive_effects_logs)

                # Track reactive effects separately (don't add to primary counts for backward compatibility)
                reactive_applied_count = 0
                reactive_failed_count = 0
                for reactive_log in reactive_effects_logs:
                    if reactive_log.get("ok", True):
                        reactive_applied_count += 1
                    else:
                        reactive_failed_count += 1

                # Store effect logs in state for replay/undo
                if not hasattr(state.scene, "last_effect_log"):
                    state.scene.last_effect_log = []
                state.scene.last_effect_log.extend(logs)

                # Generate and store human-readable audit trail
                audit_trail = self._generate_audit_trail(logs, actor, state)
                state.scene.last_diff_summary = audit_trail

                # Generate narration hint
                narration_hint = self._generate_narration_hint(logs, actor)

                # Collect unique targets for facts
                targets = list(set(effect.target for effect in effects))

                # Determine overall success based on transaction mode
                overall_success = True
                if transaction_mode == "strict" and failed_count > 0:
                    # Strict mode fails only on actual failures, not graceful skips
                    overall_success = False
                elif transaction_mode == "partial" and applied_count == 0:
                    # Partial mode requires at least one effect to succeed
                    overall_success = False
                # best_effort always succeeds if no critical errors occurred

                return ToolResult(
                    ok=overall_success,
                    tool_id="apply_effects",
                    args=args,
                    facts={
                        "applied": applied_count,
                        "skipped": skipped_count,
                        "scheduled": scheduled_count,
                        "targets": targets,
                        "transaction_mode": transaction_mode,
                        "total_effects": original_effects_count,
                        "reactive_applied": reactive_applied_count,
                        "reactive_failed": reactive_failed_count,
                        "timed_applied": timed_applied_count,
                        "pending_effects_count": (
                            len(state.scene.pending_effects)
                            if hasattr(state.scene, "pending_effects")
                            else 0
                        ),
                    },
                    effects=logs,
                    narration_hint=narration_hint,
                )

            except Exception as e:
                # Critical failure during application
                if transactional and snapshot:
                    self._rollback_state(state, snapshot)

                return ToolResult(
                    ok=False,
                    tool_id="apply_effects",
                    args=args,
                    facts={
                        "applied": 0,
                        "skipped": original_effects_count,
                        "transaction_mode": transaction_mode,
                        "total_effects": original_effects_count,
                    },
                    effects=[],
                    narration_hint={
                        "summary": f"Critical failure: {str(e)}",
                        "tone_tags": ["error"],
                        "salient_entities": [],
                    },
                    error_message=f"Critical failure: {str(e)}",
                )

        except Exception as e:
            # Top-level error handling
            return ToolResult(
                ok=False,
                tool_id="apply_effects",
                args=args,
                facts={},
                effects=[],
                narration_hint={
                    "summary": f"Unexpected error: {str(e)}",
                    "tone_tags": ["error"],
                    "salient_entities": [],
                },
                error_message=f"Unexpected error: {str(e)}",
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
            # Handle both Clock objects and dictionary formats
            from .game_state import Clock

            clock_values = {}
            for k, v in state.clocks.items():
                if isinstance(v, Clock):
                    clock_values[k] = v.value
                else:
                    clock_values[k] = v["value"]
            summary["clocks"] = clock_values

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
