"""
Tool Catalog system for AI D&D - Step 1 Implementation

Each tool has:
- id: unique identifier
- desc: human-readable description
- precond: function that checks if tool is available given state and utterance
- suggest_args: optional function to provide default arguments
- schema: JSON schema for argument validation

=== TOOL IMPLEMENTATION STATUS ===
✅ FULLY IMPLEMENTED:
- ask_roll: Complete dice mechanics with Style+Domain system, DC derivation,
           effect generation, and comprehensive validation pipeline

🚧 PLACEHOLDER IMPLEMENTATIONS:
- move: Basic zone transitions (minimal implementation)
- attack: Simple combat mechanics (placeholder)
- talk: Basic social interactions (placeholder)
- use_item: Basic item usage (placeholder)
- narrate_only: Scene narration (escape hatch)
- get_info: State querying (basic implementation)
- apply_effects: Direct effect application (utility)
- ask_clarifying: Clarification requests (escape hatch)

The placeholder tools provide basic functionality for testing and integration
but lack the sophisticated mechanics that ask_roll has. They will be enhanced
in future development phases.
"""

from typing import Dict, List, Optional, Any, Callable, Union, Literal, Annotated
from pydantic import BaseModel, Field
import re


class ToolArgs(BaseModel):
    """Base class for all tool arguments."""

    pass


class AskRollArgs(ToolArgs):
    """Arguments for ask_roll tool."""

    actor: str
    action: Literal["sneak", "persuade", "athletics", "shove", "custom"]
    target: Optional[str] = None  # npc or object
    zone_target: Optional[str] = None  # e.g., "threshold"
    style: Annotated[int, Field(ge=0, le=3)] = 1
    domain: Literal["d4", "d6", "d8", "d10"] = "d6"
    dc_hint: Annotated[int, Field(ge=5, le=25)] = 12
    adv_style_delta: Annotated[int, Field(ge=-1, le=1)] = 0
    context: Optional[str] = None


class MoveArgs(ToolArgs):
    """Arguments for move tool."""

    actor: str
    to: str
    from_zone: Optional[str] = None


class AttackArgs(ToolArgs):
    """Arguments for attack tool."""

    actor: str
    target: str
    style: Annotated[int, Field(ge=0, le=3)] = 1
    domain: Literal["d4", "d6", "d8"] = "d6"
    dc_hint: Annotated[int, Field(ge=8, le=22)] = 12  # target's defense / dodge DC
    adv_style_delta: Annotated[int, Field(ge=-1, le=1)] = 0
    weapon: Optional[str] = "basic_melee"
    damage_expr: Literal["1d6", "1d6+1", "2d4"] = "1d6"
    consume_mark: bool = True


class TalkArgs(ToolArgs):
    """Arguments for talk tool."""

    actor: str
    target: str
    message: Optional[str] = None
    tone: str = "neutral"


class UseItemArgs(ToolArgs):
    """Arguments for use_item tool."""

    actor: str
    item: str
    target: Optional[str] = None


class NarrateOnlyArgs(ToolArgs):
    """Arguments for narrate_only tool."""

    actor: Optional[str] = None
    topic: Optional[str] = None  # "look around", "recap", "listen", "smell", etc.


class GetInfoArgs(ToolArgs):
    """Arguments for get_info tool."""

    query: str
    scope: str = "current_zone"  # "current_zone", "actor", "inventory", etc.


class ApplyEffectsArgs(ToolArgs):
    """Arguments for apply_effects tool."""

    effects: List[Dict[str, Any]]


class AskClarifyingArgs(ToolArgs):
    """Arguments for ask_clarifying tool."""

    question: str


class Tool(BaseModel):
    """Core Tool definition with preconditions and argument schema."""

    id: str
    desc: str
    precond: Callable[[Any, Any], bool]  # (state, utterance) -> bool
    suggest_args: Optional[Callable[[Any, Any], Dict[str, Any]]] = None
    args_schema: type[ToolArgs]

    class Config:
        arbitrary_types_allowed = True


# Precondition functions
def ask_roll_precond(state, utterance) -> bool:
    """ask_roll available when there's a pending action or actionable verb."""
    has_pending = state.pending_action is not None
    has_action_verb = utterance.has_actionable_verb()
    return has_pending or has_action_verb


def move_precond(state, utterance) -> bool:
    """move available when target zone is adjacent to current zone."""
    if not state.current_actor:
        return False

    current_actor = state.actors.get(state.current_actor)
    if not current_actor:
        return False

    current_zone = state.zones.get(current_actor.current_zone)
    if not current_zone:
        return False

    # Check if utterance mentions any adjacent zone
    text_lower = utterance.text.lower()
    for zone_id in current_zone.adjacent_zones:
        zone = state.zones.get(zone_id)
        if zone and (zone.name.lower() in text_lower or zone_id.lower() in text_lower):
            return True

    return False


def attack_precond(state, utterance) -> bool:
    """attack available when there's a visible enemy in the same zone."""
    if not state.current_actor:
        return False

    current_actor = state.entities.get(state.current_actor)
    if not current_actor or current_actor.type not in ("pc", "npc"):
        return False

    # Check if actor has positive HP (can't attack if unconscious)
    if hasattr(current_actor, "hp") and current_actor.hp.current <= 0:
        return False

    # Check for visible enemies (PC can attack NPCs, NPCs can attack PCs)
    if hasattr(current_actor, "visible_actors"):
        for actor_id in current_actor.visible_actors:
            target = state.entities.get(actor_id)
            if (
                target
                and target.type in ("pc", "npc")
                and target.type != current_actor.type
            ):
                # Found a valid target of different type with positive HP
                if hasattr(target, "hp") and target.hp.current > 0:
                    return True

    return False


def talk_precond(state, utterance) -> bool:
    """talk available when there's a current actor who hasn't talked this turn."""
    if not state.current_actor:
        return False  # No talk without current actor

    current_actor = state.actors.get(state.current_actor)
    if not current_actor:
        return False

    # Check if actor has already talked this turn
    return not (
        hasattr(current_actor, "has_talked_this_turn")
        and current_actor.has_talked_this_turn
    )


def use_item_precond(state, utterance) -> bool:
    """use_item available when actor has items in inventory."""
    if not state.current_actor:
        return False

    current_actor = state.actors.get(state.current_actor)
    if not current_actor:
        return False

    # Defensive check for inventory attribute
    if not hasattr(current_actor, "inventory"):
        return False

    return len(current_actor.inventory) > 0


def narrate_only_precond(state, utterance) -> bool:
    """narrate_only always available as escape hatch."""
    return True


def get_info_precond(state, utterance) -> bool:
    """get_info always available for querying state."""
    return True


def apply_effects_precond(state, utterance) -> bool:
    """apply_effects typically used internally, rarely from player input."""
    # Could check for admin/GM permissions in future
    return True


def ask_clarifying_precond(state, utterance) -> bool:
    """ask_clarifying always available as escape hatch."""
    return True


# Argument suggestion functions
def suggest_ask_roll_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for ask_roll based on state and utterance."""
    args = {}

    if state.current_actor:
        args["actor"] = state.current_actor

    # Try to detect action from utterance
    action_map = {
        "sneak": ("sneak", 12),
        "hide": ("sneak", 10),  # "hide" maps to "sneak" action
        "persuade": ("persuade", 13),
        "intimidate": ("persuade", 14),  # "intimidate" also maps to "persuade"
        "search": ("athletics", 11),  # "search" maps to "athletics"
        "climb": ("athletics", 12),  # "climb" maps to "athletics"
    }

    text_lower = utterance.text.lower()
    for keyword, (action, dc) in action_map.items():
        if keyword in text_lower:
            args["action"] = action
            args["dc_hint"] = dc
            break

    # Try to detect target
    current_actor = (
        state.actors.get(state.current_actor) if state.current_actor else None
    )
    if (
        current_actor
        and hasattr(current_actor, "visible_actors")
        and current_actor.visible_actors
    ):
        # For now, default to first visible actor
        args["target"] = current_actor.visible_actors[0]

    args.setdefault("style", 1)
    args.setdefault("domain", "d6")

    return args


def suggest_move_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for move based on available adjacent zones."""
    args = {}

    if state.current_actor:
        args["actor"] = state.current_actor
        current_actor = state.actors.get(state.current_actor)

        if current_actor:
            args["from_zone"] = current_actor.current_zone
            current_zone = state.zones.get(current_actor.current_zone)

            if current_zone:
                text_lower = utterance.text.lower()
                # Find which adjacent zone is mentioned
                for zone_id in current_zone.adjacent_zones:
                    zone = state.zones.get(zone_id)
                    if zone and (
                        zone.name.lower() in text_lower or zone_id.lower() in text_lower
                    ):
                        args["to"] = zone_id
                        break

    return args


def suggest_attack_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for attack tool with intelligent defaults."""
    args = {}

    if state.current_actor:
        args["actor"] = state.current_actor
        current_actor = state.entities.get(state.current_actor)

        if current_actor and hasattr(current_actor, "visible_actors"):
            # Find first valid target (different type, positive HP)
            for actor_id in current_actor.visible_actors:
                target = state.entities.get(actor_id)
                if (
                    target
                    and target.type in ("pc", "npc")
                    and target.type != current_actor.type
                    and hasattr(target, "hp")
                    and target.hp.current > 0
                ):
                    args["target"] = actor_id

                    # Try to estimate DC from target's stats if available
                    if hasattr(target, "stats"):
                        # Basic AC calculation: 10 + DEX modifier (simplified)
                        dex_mod = (target.stats.dexterity - 10) // 2
                        base_ac = 10 + dex_mod
                        args["dc_hint"] = max(8, min(22, base_ac))
                    break

        # Set reasonable defaults
        args.setdefault("style", 1)
        args.setdefault("domain", "d6")
        args.setdefault("dc_hint", 12)
        args.setdefault("adv_style_delta", 0)
        args.setdefault("weapon", "basic_melee")
        args.setdefault("damage_expr", "1d6")
        args.setdefault("consume_mark", True)
    else:
        # No current actor - return empty dict to let caller handle missing args
        args = {}

    return args


def suggest_use_item_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for use_item tool with safe actor access."""
    args = {}

    if state.current_actor:
        args["actor"] = state.current_actor
        current_actor = state.actors.get(state.current_actor)

        if (
            current_actor
            and hasattr(current_actor, "inventory")
            and current_actor.inventory
        ):
            args["item"] = current_actor.inventory[0]
        else:
            args["item"] = None
    else:
        args["actor"] = None
        args["item"] = None

    return args


def suggest_talk_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for talk based on visible actors."""
    args = {}

    if state.current_actor:
        args["actor"] = state.current_actor
        current_actor = state.actors.get(state.current_actor)

        if (
            current_actor
            and hasattr(current_actor, "visible_actors")
            and current_actor.visible_actors
        ):
            args["target"] = current_actor.visible_actors[0]

        # Detect tone from utterance
        text_lower = utterance.text.lower()
        if any(word in text_lower for word in ["angry", "shout", "yell"]):
            args["tone"] = "aggressive"
        elif any(word in text_lower for word in ["whisper", "quiet", "soft"]):
            args["tone"] = "calm"
        elif any(word in text_lower for word in ["friendly", "smile", "kind"]):
            args["tone"] = "friendly"
        else:
            args["tone"] = "neutral"

    return args


def suggest_narrate_only_args(state, utterance) -> Dict[str, Any]:
    """Suggest arguments for narrate_only based on topic inference heuristics."""
    args = {}

    # Set actor
    if state.current_actor:
        args["actor"] = state.current_actor

    # Infer topic from utterance using classification/regex
    text_lower = utterance.text.lower().strip()

    # Contains look/see/watch/survey/scan → "look around"
    if any(
        word in text_lower
        for word in ["look", "see", "watch", "survey", "scan", "observe", "examine"]
    ):
        args["topic"] = "look around"

    # Contains listen/hear → "listen"
    elif any(word in text_lower for word in ["listen", "hear", "sound", "noise"]):
        args["topic"] = "listen"

    # Contains smell/scent/odor → "smell"
    elif any(word in text_lower for word in ["smell", "scent", "odor", "sniff"]):
        args["topic"] = "smell"

    # Contains recap/remind/what happened → "recap"
    elif any(
        phrase in text_lower
        for phrase in ["recap", "remind", "what happened", "summary", "so far"]
    ):
        args["topic"] = "recap"

    # Check for zoom_in on specific entity mentions
    elif state.current_actor:
        current_actor = state.actors.get(state.current_actor)
        if current_actor and hasattr(current_actor, "visible_actors"):
            # Look for mentions of visible actor names/IDs in the text
            for actor_id in current_actor.visible_actors:
                actor_obj = state.actors.get(actor_id)
                if actor_obj:
                    # Check if actor name or ID is mentioned
                    if (
                        hasattr(actor_obj, "name")
                        and actor_obj.name.lower() in text_lower
                    ) or actor_id.lower() in text_lower:
                        args["topic"] = f"zoom_in:{actor_id}"
                        break

        # If no entity match found, check if starts with "I" and no actionable verb → "establishing"
        if (
            "topic" not in args
            and text_lower.startswith("i ")
            and not utterance.has_actionable_verb()
        ):
            args["topic"] = "establishing"

    # Fallback: "look around"
    args.setdefault("topic", "look around")

    return args


# Tool catalog definition
TOOL_CATALOG: List[Tool] = [
    Tool(
        id="ask_roll",
        desc="Roll Style+Domain to resolve an action.",
        precond=ask_roll_precond,
        suggest_args=suggest_ask_roll_args,
        args_schema=AskRollArgs,
    ),
    Tool(
        id="narrate_only",
        desc="No mechanics; just narrate the scene.",
        precond=narrate_only_precond,
        suggest_args=suggest_narrate_only_args,
        args_schema=NarrateOnlyArgs,
    ),
    Tool(
        id="apply_effects",
        desc="Apply mechanical effects to game state.",
        precond=apply_effects_precond,
        suggest_args=lambda state, utterance: {"effects": []},
        args_schema=ApplyEffectsArgs,
    ),
    Tool(
        id="get_info",
        desc="Query current game state information.",
        precond=get_info_precond,
        suggest_args=lambda state, utterance: {
            "query": utterance.text,
            "scope": "current_zone",
        },
        args_schema=GetInfoArgs,
    ),
    Tool(
        id="move",
        desc="Change zone without a roll if uncontested.",
        precond=move_precond,
        suggest_args=suggest_move_args,
        args_schema=MoveArgs,
    ),
    Tool(
        id="attack",
        desc="Engage in combat with a visible enemy.",
        precond=attack_precond,
        suggest_args=suggest_attack_args,
        args_schema=AttackArgs,
    ),
    Tool(
        id="talk",
        desc="Say something to influence another character.",
        precond=talk_precond,
        suggest_args=suggest_talk_args,
        args_schema=TalkArgs,
    ),
    Tool(
        id="use_item",
        desc="Use an item from your inventory.",
        precond=use_item_precond,
        suggest_args=suggest_use_item_args,
        args_schema=UseItemArgs,
    ),
    Tool(
        id="ask_clarifying",
        desc="Ask the player a short clarifying question.",
        precond=ask_clarifying_precond,
        suggest_args=lambda state, utterance: {
            "question": "Could you clarify what you'd like to do?"
        },
        args_schema=AskClarifyingArgs,
    ),
]


def get_tool_by_id(tool_id: str) -> Optional[Tool]:
    """Get a tool by its ID."""
    for tool in TOOL_CATALOG:
        if tool.id == tool_id:
            return tool
    return None
