"""
Visibility and redaction layer for the AID&D game system.

This module centralizes all visibility logic and provides safe, consistent
redaction of game state to prevent information leaks while maintaining
stable JSON schemas for downstream consumers.
"""

from typing import Optional, Dict, Any, List, Union, Literal
from copy import deepcopy

# Import will work since game_state.py is in the same directory
from .game_state import BaseEntity, Zone, Clock, GameState

# Define redaction roles for different AI contexts
RedactionRole = Literal["player", "narrator", "gm"]


def can_player_see(pov_id: Optional[str], entity: BaseEntity, world: GameState) -> bool:
    """
    Pure visibility check. Does NOT cause discovery.
    
    Returns True only if the POV already knows the entity or it is public/visible 
    in current conditions. Hidden entities remain invisible until an explicit 
    reveal event.

    Args:
        pov_id: The point-of-view actor ID, or None for GM view
        entity: The entity being checked for visibility
        world: The game state containing all entities and zones

    Returns:
        True if the entity should be visible to the POV actor
    """
    # GM view sees everything
    if pov_id is None:
        return True

    # GM-only content is never visible to players
    if entity.meta.gm_only or entity.meta.visibility == "gm_only":
        return False

    # Hidden entities are only visible to those who know about them
    if entity.meta.visibility == "hidden":
        return pov_id in entity.meta.known_by

    # Get the POV actor
    actor = world.entities.get(pov_id)
    if not actor:
        return False

    # Basic spatial rule - same zone visibility
    if getattr(entity, "current_zone", None) == getattr(actor, "current_zone", None):
        return True

    # Allow global knowledge of some items/locations if known
    if (
        hasattr(entity, "__dict__")
        and entity.__dict__.get("type") == "item"
        and pov_id in entity.meta.known_by
    ):
        return True

    return False


def redact_entity(
    pov_id: Optional[str],
    entity: BaseEntity,
    world: GameState,
    role: RedactionRole = "player",
) -> Dict[str, Any]:
    """
    Return a safe, schema-consistent public view of an entity.

    Args:
        pov_id: The point-of-view actor ID, or None for GM view
        entity: The entity to redact
        world: The game state containing all entities and zones
        role: The redaction role determining information access level

    Returns:
        Dictionary representation of the entity, redacted for the role and POV actor
    """
    # GM role sees everything unredacted
    if role == "gm":
        result = entity.model_dump()
        result["is_visible"] = True
        return result

    # Check basic visibility
    visible = can_player_see(pov_id, entity, world)

    # Always include basic structure for schema consistency
    base = {
        "id": entity.id,
        "type": getattr(entity, "type", "unknown"),
        "is_visible": visible,
    }

    if not visible:
        # For narrator role, check if entity should be partially visible
        if role == "narrator" and entity.meta.visibility == "hidden":
            # Narrator can see basic info about hidden entities but not details
            narrator_view = base.copy()
            narrator_view.update(
                {
                    "name": entity.name,  # Narrator knows the name
                    "current_zone": entity.current_zone,  # And location
                    "tags": getattr(entity, "tags", {}),  # And tags for context
                    "meta": {
                        "visibility": entity.meta.visibility,  # Narrator sees visibility state
                        "created_at": entity.meta.created_at,
                        "last_changed_at": entity.meta.last_changed_at,
                        "source": entity.meta.source,
                        "notes": None,  # But not GM notes
                        "extra": entity.meta.extra,
                    },
                }
            )

            # Add redacted type-specific fields to maintain schema consistency
            if hasattr(entity, "hp"):
                narrator_view["hp"] = {"current": -1, "max": -1}
            if hasattr(entity, "stats"):
                narrator_view["stats"] = {
                    "strength": -1,
                    "dexterity": -1,
                    "constitution": -1,
                    "intelligence": -1,
                    "wisdom": -1,
                    "charisma": -1,
                }
            if hasattr(entity, "inventory"):
                narrator_view["inventory"] = []
            if hasattr(entity, "visible_actors"):
                narrator_view["visible_actors"] = []
            if hasattr(entity, "marks"):
                narrator_view["marks"] = {
                    "hidden_mark_count": len(getattr(entity, "marks", {}))
                }
            if hasattr(entity, "guard"):
                narrator_view["guard"] = None

            return narrator_view
        # Keep same shape but replace sensitive values
        redacted = base.copy()
        redacted.update(
            {
                "name": "Unknown",
                "current_zone": None,
                "tags": {},
                "meta": {
                    "visibility": "hidden",
                    "created_at": None,
                    "last_changed_at": None,
                    "source": None,
                    "notes": None,
                    "extra": {},
                },
            }
        )

        # Add type-specific redacted fields to maintain schema consistency
        if hasattr(entity, "hp"):
            redacted["hp"] = {"current": None, "max": None}
        if hasattr(entity, "stats"):
            redacted["stats"] = {
                "strength": None,
                "dexterity": None,
                "constitution": None,
                "intelligence": None,
                "wisdom": None,
                "charisma": None,
            }
        if hasattr(entity, "inventory"):
            redacted["inventory"] = []
        if hasattr(entity, "visible_actors"):
            redacted["visible_actors"] = []
        if hasattr(entity, "marks"):
            redacted["marks"] = {}
        if hasattr(entity, "guard"):
            redacted["guard"] = None

        return redacted

    # Fully visible copy - apply role-based policies
    safe = deepcopy(entity.model_dump())
    safe["is_visible"] = True

    # Apply role-based redaction policies
    if role == "player":
        # Player view: hide GM notes completely
        if "meta" in safe:
            safe["meta"]["notes"] = None

    elif role == "narrator":
        # Narrator view: can see meta info but not GM notes
        if "meta" in safe:
            safe["meta"]["notes"] = None  # Still hide GM notes
            # Narrator keeps visibility settings for context

    return safe


def redact_zone(
    pov_id: Optional[str], zone: Zone, world: GameState, role: RedactionRole = "player"
) -> Dict[str, Any]:
    """
    Return a safe, schema-consistent public view of a zone.

    Args:
        pov_id: The point-of-view actor ID, or None for GM view
        zone: The zone to redact
        world: The game state containing all entities and zones
        role: The redaction role determining information access level

    Returns:
        Dictionary representation of the zone, redacted for the role and POV actor
    """
    # GM role sees everything
    if role == "gm":
        result = zone.model_dump()
        result["is_visible"] = True
        return result

    # Check zone visibility
    vis = zone.meta.visibility != "gm_only"
    if not vis:
        return {
            "id": zone.id,
            "name": "Unknown Area",
            "description": "You cannot see this area.",
            "adjacent_zones": [],
            "blocked_exits": [],
            "entities": [],
            "is_visible": False,
        }

    # Get visible entities in this zone
    visible_entities = []
    for eid, entity in world.entities.items():
        if getattr(entity, "current_zone", None) == zone.id and can_player_see(
            pov_id, entity, world
        ):
            visible_entities.append(eid)

    # Return redacted zone info
    zone_data = zone.model_dump()
    zone_data["entities"] = visible_entities
    zone_data["is_visible"] = True

    # Strip GM notes
    if "meta" in zone_data:
        zone_data["meta"]["notes"] = None

    return zone_data


def redact_clock(
    pov_id: Optional[str], clock: Union[Clock, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Return a safe, schema-consistent public view of a clock.

    Args:
        pov_id: The point-of-view actor ID, or None for GM view
        clock: The Clock object or dictionary to redact

    Returns:
        Dictionary representation of the clock, redacted for the POV actor
    """
    # Handle both Clock objects and legacy dict format
    if isinstance(clock, dict):
        # Legacy format - use existing logic
        meta = clock.get("meta", {})
        if meta.get("visibility") == "gm_only":
            return {
                "id": clock.get("id", "unknown"),
                "name": "Unknown Progress",
                "value": None,
                "maximum": None,
                "is_visible": False,
            }
        if meta.get("visibility") == "hidden":
            if pov_id not in meta.get("known_by", set()):
                return {
                    "id": clock.get("id", "unknown"),
                    "name": "Unknown Progress",
                    "value": None,
                    "maximum": None,
                    "is_visible": False,
                }

        # Return visible clock data
        safe_clock = deepcopy(clock)
        safe_clock["is_visible"] = True

        # Strip GM notes
        if "meta" in safe_clock:
            safe_clock["meta"]["notes"] = None

        return safe_clock

    # New Clock object format
    # Check clock visibility
    if clock.meta.visibility == "gm_only":
        return {
            "id": clock.id,
            "name": "Unknown Progress",
            "value": None,
            "maximum": None,
            "is_visible": False,
        }
    if clock.meta.visibility == "hidden":
        if pov_id not in clock.meta.known_by:
            return {
                "id": clock.id,
                "name": "Unknown Progress",
                "value": None,
                "maximum": None,
                "is_visible": False,
            }

    # Return visible clock data
    safe_clock = clock.model_dump()
    safe_clock["is_visible"] = True

    # Strip GM notes
    if "meta" in safe_clock:
        safe_clock["meta"]["notes"] = None

    return safe_clock
