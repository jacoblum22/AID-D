"""
Tool Catalog system for AI D&D - Step 1 Implementation

Each tool has:
- id: unique identifier
- desc: human-readable description
- precond: function that checks if tool is available given state and utterance
- suggest_args: optional function to provide default arguments
- schema: JSON schema for argument validation
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
    weapon: Optional[str] = None
    zone: Optional[str] = None


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
    """Arguments for narrate_only tool (minimal)."""

    scene_description: Optional[str] = None


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
    """attack available when there's a visible enemy and actor has weapon."""
    if not state.current_actor:
        return False

    current_actor = state.actors.get(state.current_actor)
    if (
        not current_actor
        or not hasattr(current_actor, "has_weapon")
        or not current_actor.has_weapon
    ):
        return False

    # Check if there are any visible enemies (NPCs in same zone)
    if hasattr(current_actor, "visible_actors"):
        # Check if any visible actors are actually NPCs (attackable targets)
        for actor_id in current_actor.visible_actors:
            target = state.actors.get(actor_id)
            if target and hasattr(target, "type") and target.type == "npc":
                return True
    return False


def talk_precond(state, utterance) -> bool:
    """talk always available but capped by 'already talked this turn' flag."""
    if not state.current_actor:
        return True  # Default to available

    current_actor = state.actors.get(state.current_actor)
    return not (current_actor and current_actor.has_talked_this_turn)


def use_item_precond(state, utterance) -> bool:
    """use_item available when actor has items in inventory."""
    if not state.current_actor:
        return False

    current_actor = state.actors.get(state.current_actor)
    return current_actor and len(current_actor.inventory) > 0


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
        "hide": ("hide", 10),
        "persuade": ("persuade", 13),
        "intimidate": ("intimidate", 14),
        "search": ("search", 11),
        "climb": ("climb", 12),
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
        suggest_args=lambda state, utterance: {},
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
        suggest_args=lambda state, utterance: {
            "actor": state.current_actor,
            "target": (
                state.actors[state.current_actor].visible_actors[0]
                if state.current_actor
                and state.actors.get(state.current_actor)
                and hasattr(state.actors[state.current_actor], "visible_actors")
                and state.actors[state.current_actor].visible_actors
                else None
            ),
        },
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
        suggest_args=lambda state, utterance: {
            "actor": state.current_actor,
            "item": (
                state.actors[state.current_actor].inventory[0]
                if state.current_actor
                and state.actors.get(state.current_actor)
                and state.actors[state.current_actor].inventory
                else None
            ),
        },
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
