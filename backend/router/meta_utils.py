"""
Meta utility helpers for the AID&D game system.

Convenience functions for working with meta fields on game objects,
providing easy access to visibility controls and metadata management.
"""

from typing import Union, Literal, Optional
from .game_state import BaseEntity, Zone, Clock, Scene, GameState


def reveal_to(
    obj: Union[BaseEntity, Zone, Clock, Scene],
    actor_id: str,
    game_state: Optional[GameState] = None,
) -> None:
    """
    Add an actor to the known_by set of an object's meta data.

    Args:
        obj: The game object to reveal (entity, zone, clock, or scene)
        actor_id: The ID of the actor who should now know about this object
        game_state: Optional GameState to invalidate cache for
    """
    obj.meta.known_by.add(actor_id)
    entity_id = getattr(obj, "id", None)
    obj.meta.touch(game_state, entity_id)


def set_visibility(
    obj: Union[BaseEntity, Zone, Clock, Scene],
    level: Literal["public", "hidden", "gm_only"],
    game_state: Optional[GameState] = None,
) -> None:
    """
    Set the visibility level of a game object.

    Args:
        obj: The game object to modify
        level: The new visibility level
        game_state: Optional GameState to invalidate cache for
    """
    obj.meta.visibility = level
    obj.meta.gm_only = level == "gm_only"  # Keep redundant flag in sync
    entity_id = getattr(obj, "id", None)
    obj.meta.touch(game_state, entity_id)


def hide_from(
    obj: Union[BaseEntity, Zone, Clock, Scene],
    actor_id: str,
    game_state: Optional[GameState] = None,
) -> None:
    """
    Remove an actor from the known_by set of an object's meta data.

    Args:
        obj: The game object to hide
        actor_id: The ID of the actor who should no longer know about this object
        game_state: Optional GameState to invalidate cache for
    """
    obj.meta.known_by.discard(actor_id)
    entity_id = getattr(obj, "id", None)
    obj.meta.touch(game_state, entity_id)


def is_known_by(obj: Union[BaseEntity, Zone, Clock, Scene], actor_id: str) -> bool:
    """
    Check if an actor knows about a specific game object.

    Args:
        obj: The game object to check
        actor_id: The ID of the actor to check

    Returns:
        True if the actor knows about the object
    """
    return actor_id in obj.meta.known_by


def set_gm_note(
    obj: Union[BaseEntity, Zone, Clock, Scene],
    note: str,
    game_state: Optional[GameState] = None,
) -> None:
    """
    Set a GM-only note to an object's meta data (replaces existing note).

    Args:
        obj: The game object to annotate
        note: The note to set (replaces existing)
        game_state: Optional GameState to invalidate cache for
    """
    obj.meta.notes = note
    entity_id = getattr(obj, "id", None)
    obj.meta.touch(game_state, entity_id)


def clear_gm_note(
    obj: Union[BaseEntity, Zone, Clock, Scene], game_state: Optional[GameState] = None
) -> None:
    """
    Clear the GM note from an object's meta data.

    Args:
        obj: The game object to clear the note from
        game_state: Optional GameState to invalidate cache for
    """
    obj.meta.notes = None
    entity_id = getattr(obj, "id", None)
    obj.meta.touch(game_state, entity_id)
