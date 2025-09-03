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
from typing import Dict, Any, List, Optional, Union, cast
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass

from .game_state import GameState, Utterance, PC, NPC
from .tool_catalog import TOOL_CATALOG, get_tool_by_id
from .effects import apply_effects


# Set up logging
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
            try:
                validated_args = tool.args_schema(**raw_args)
                schema_ok = True
                sanitized_args = validated_args.dict()
            except ValidationError as e:
                schema_ok = False
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

            print(f"INFO: {json.dumps(log_entry)}")

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

        # Parse domain die size
        domain_size = int(domain[1:])  # "d6" -> 6
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
                    "delta": 2 if outcome == "crit_fail" else 2,
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
        """Execute move tool - zone transitions."""
        actor = args.get("actor")
        to_zone = args.get("to")
        from_zone = args.get("from_zone")
        movement_style = args.get("movement_style", "normal")

        effects = [{"type": "position", "target": actor, "to": to_zone}]

        # Potential clock effects for movement
        if movement_style == "fast":
            effects.append({"type": "clock", "id": "scene.noise", "delta": 1})

        narration_hint = {
            "summary": f"Moved to {args.get('zone_name', to_zone)}",
            "movement": {"from": from_zone, "to": to_zone, "style": movement_style},
            "tone_tags": ["quiet"] if movement_style == "stealth" else ["active"],
            "salient_entities": [actor],
        }

        return ToolResult(
            ok=True,
            tool_id="move",
            args=args,
            facts={"destination": to_zone, "movement_style": movement_style},
            effects=effects,
            narration_hint=narration_hint,
        )

    def _execute_talk(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute talk tool - social interactions."""
        actor = args.get("actor")
        target = args.get("target")
        message = args.get("message", "")
        tone = args.get("tone", "neutral")

        # Simple social mechanics - could trigger rolls or effects
        effects = []
        facts = {"message_delivered": True, "tone": tone}

        # Set talked flag to prevent multiple talks per turn
        if actor and actor in state.actors:
            actor_entity = state.actors[actor]
            if hasattr(actor_entity, "has_talked_this_turn"):
                # Type cast to ensure we can access the attribute
                pc_or_npc = cast(Union[PC, NPC], actor_entity)
                pc_or_npc.has_talked_this_turn = True

        narration_hint = {
            "summary": f"Spoke to {args.get('target_name', target)}",
            "social": {
                "tone": tone,
                "message": message[:50] + "..." if len(message) > 50 else message,
            },
            "tone_tags": ["social", tone],
            "salient_entities": [actor, target],
        }

        return ToolResult(
            ok=True,
            tool_id="talk",
            args=args,
            facts=facts,
            effects=effects,
            narration_hint=narration_hint,
        )

    def _execute_attack(
        self, args: Dict[str, Any], state: GameState, utterance: Utterance, seed: int
    ) -> ToolResult:
        """Execute attack tool - combat mechanics."""
        import random

        random.seed(seed)

        actor = args.get("actor")
        target = args.get("target")
        weapon = args.get("weapon", "weapon")

        # Simple combat: roll to hit, then damage
        hit_roll = random.randint(1, 20)
        hits = hit_roll >= 10  # Simple AC
        damage = random.randint(1, 8) if hits else 0

        effects = []
        if hits and damage > 0:
            effects.append({"type": "hp", "target": target, "delta": -damage})

        narration_hint = {
            "summary": f"Hit for {damage} damage" if hits else "Missed",
            "dice": {"d20": hit_roll, "damage": damage},
            "outcome": "hit" if hits else "miss",
            "tone_tags": ["combat", "tense"],
            "salient_entities": [actor, target],
        }

        return ToolResult(
            ok=True,
            tool_id="attack",
            args=args,
            facts={"hit": hits, "damage": damage},
            effects=effects,
            narration_hint=narration_hint,
        )

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
        """Execute narrate_only tool."""
        return ToolResult(
            ok=True,
            tool_id="narrate_only",
            args=args,
            facts={"narration_only": True},
            effects=[],
            narration_hint={
                "summary": "Scene narration",
                "tone_tags": ["atmospheric"],
                "salient_entities": [],
            },
        )

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
        """Execute ask_clarifying tool."""
        question = args.get("question", "Could you clarify what you'd like to do?")

        return ToolResult(
            ok=True,
            tool_id="ask_clarifying",
            args=args,
            facts={"question": question},
            effects=[],
            narration_hint={
                "summary": "Asked for clarification",
                "tone_tags": ["helpful"],
                "salient_entities": [],
            },
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
        print(f"ERROR: {json.dumps(log_entry)}")

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
