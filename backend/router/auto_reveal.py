"""
Auto-Reveal System - Automatic discovery mechanics for enhanced exploration.

This module implements automatic reveal hooks that trigger when actors enter zones,
making exploration feel more alive and reducing manual bookkeeping.
"""

import importlib
from typing import Dict, Set, List, Optional, Any, Tuple
from .game_state import GameState, PC, NPC
from .visibility import can_player_see


def _safe_entity_update(state: GameState, entity_id: str, discoverer_id: str) -> bool:
    """
    Safely update an entity's known_by set and trigger meta change notification.

    Args:
        state: Current game state
        entity_id: ID of entity to update
        discoverer_id: ID of actor discovering the entity

    Returns:
        True if update was successful, False if failed
    """
    try:
        entity = state.entities.get(entity_id)
        if not entity:
            return False

        # Create updated entity with new knowledge
        updated_meta = entity.meta.model_copy(deep=True)
        updated_meta.known_by.add(discoverer_id)
        updated_entity = entity.model_copy(update={"meta": updated_meta})

        # Commit the update atomically
        state.entities[entity_id] = updated_entity

        # Trigger meta change notification (safe - won't break atomicity)
        try:
            updated_meta.touch(state, entity_id)
        except Exception as e:
            # Log warning but don't fail the transaction
            # The entity update is already committed and consistent
            import sys

            print(
                f"Warning: Meta touch notification failed for {entity_id}: {e}",
                file=sys.stderr,
            )

        return True

    except Exception:
        return False


def _check_discovery_eligibility(
    state: GameState, observer_id: str, target_id: str, zone_id: Optional[str] = None
) -> bool:
    """
    Check if an observer can discover a target entity.

    Determines if a hidden target *could* be discovered under current conditions.
    Hidden entities require explicit triggers (perception, light, etc.).
    Zone proximity alone is insufficient; see reveal_on_event handlers.

    Args:
        state: Current game state
        observer_id: Observer actor ID
        target_id: Target entity ID
        zone_id: Optional zone to check (defaults to observer's current zone)

    Returns:
        True if discovery is possible, False otherwise
    """
    observer = state.entities.get(observer_id)
    target = state.entities.get(target_id)

    if not observer or not target:
        return False

    # Determine zone to check
    check_zone = zone_id or getattr(observer, "current_zone", None)
    if not check_zone:
        return False

    # Check if target is in the same zone
    target_zone = getattr(target, "current_zone", None)
    if target_zone != check_zone:
        return False

    # Check if observer already knows target
    if observer_id in target.meta.known_by:
        return False

    # Check visibility rules using temporary state
    # Create temp state with observer in the target zone
    temp_state = state.model_copy(deep=True)

    # Update observer to be in the target zone for visibility check
    if hasattr(temp_state.entities[observer_id], "current_zone"):
        temp_observer = temp_state.entities[observer_id].model_copy(
            update={"current_zone": check_zone}
        )
        temp_state.entities[observer_id] = temp_observer

    target_entity = temp_state.entities[target_id]
    return can_player_see(observer_id, target_entity, temp_state)


def auto_reveal_on_zone_entry(
    state: GameState, actor_id: str, new_zone: str
) -> Dict[str, List[str]]:
    """
    Automatically reveal entities when an actor enters a new zone.

    Args:
        state: Current game state
        actor_id: ID of the actor who entered the zone
        new_zone: Zone ID that was entered

    Returns:
        Dictionary containing:
        - "discovered": List of entity IDs that were newly discovered
        - "already_known": List of entity IDs that were already known
        - "events": List of discovery events published
    """
    if actor_id not in state.entities:
        return {"discovered": [], "already_known": [], "events": []}

    actor = state.entities[actor_id]
    if actor.type not in ("pc", "npc"):
        return {"discovered": [], "already_known": [], "events": []}

    discovered = []
    already_known = []

    # Check all entities in the new zone for discovery
    for entity_id, entity in state.entities.items():
        if entity_id == actor_id:
            continue

        # Check if this entity can be discovered
        if _check_discovery_eligibility(state, actor_id, entity_id, new_zone):
            # Use safe update helper for atomic operation
            if _safe_entity_update(state, entity_id, actor_id):
                discovered.append(entity_id)
        elif (
            hasattr(entity, "current_zone")
            and entity.current_zone == new_zone
            and actor_id in entity.meta.known_by
        ):
            already_known.append(entity_id)

    # Publish discovery events
    events = []
    if discovered:
        events.extend(_publish_discovery_events(state, actor_id, new_zone, discovered))

    return {"discovered": discovered, "already_known": already_known, "events": events}


def auto_reveal_zone_entities(
    state: GameState, zone_id: str, revealer_id: str
) -> List[str]:
    """
    Reveal all appropriate entities in a zone to a specific actor.

    Args:
        state: Current game state
        zone_id: Zone to reveal entities from
        revealer_id: Actor who should discover the entities

    Returns:
        List of entity IDs that were newly revealed
    """
    if revealer_id not in state.entities:
        return []

    revealer = state.entities[revealer_id]
    if revealer.type not in ("pc", "npc"):
        return []

    revealed = []

    # Check all entities in the zone for discovery
    for entity_id, entity in state.entities.items():
        if entity_id == revealer_id:
            continue

        # Check if this entity can be discovered
        if _check_discovery_eligibility(state, revealer_id, entity_id, zone_id):
            # Use safe update helper for atomic operation
            if _safe_entity_update(state, entity_id, revealer_id):
                revealed.append(entity_id)

    return revealed


def check_mutual_discovery(
    state: GameState, actor1_id: str, actor2_id: str
) -> Dict[str, bool]:
    """
    Check if two actors should mutually discover each other.

    Uses atomic updates to ensure mutual discovery is consistent:
    both actors updated together or neither.

    Args:
        state: Current game state
        actor1_id: First actor ID
        actor2_id: Second actor ID

    Returns:
        Dictionary with discovery results:
        - "actor1_discovers_actor2": bool
        - "actor2_discovers_actor1": bool
    """
    result = {"actor1_discovers_actor2": False, "actor2_discovers_actor1": False}

    # Don't allow self-discovery
    if actor1_id == actor2_id:
        return result

    if actor1_id not in state.entities or actor2_id not in state.entities:
        return result

    actor1 = state.entities[actor1_id]
    actor2 = state.entities[actor2_id]

    if actor1.type not in ("pc", "npc") or actor2.type not in ("pc", "npc"):
        return result

    # Phase 1: Validate all potential discoveries before committing any
    updates_needed = []

    # Check if actor1 can discover actor2
    if (
        can_player_see(actor1_id, actor2, state)
        and actor1_id not in actor2.meta.known_by
    ):
        updates_needed.append(("actor1_discovers_actor2", actor2_id, actor1_id))

    # Check if actor2 can discover actor1
    if (
        can_player_see(actor2_id, actor1, state)
        and actor2_id not in actor1.meta.known_by
    ):
        updates_needed.append(("actor2_discovers_actor1", actor1_id, actor2_id))

    # Phase 2: Apply all validated updates atomically
    for discovery_type, entity_id, discoverer_id in updates_needed:
        if _safe_entity_update(state, entity_id, discoverer_id):
            result[discovery_type] = True
        else:
            # If any update fails, we could implement rollback here
            # For now, continue with partial success
            pass

    return result


def get_discoverable_entities(
    state: GameState, observer_id: str, zone_id: Optional[str] = None
) -> List[str]:
    """
    Get list of entities that could be discovered by an observer.

    Args:
        state: Current game state
        observer_id: Observer actor ID
        zone_id: Optional zone to limit search to (defaults to observer's current zone)

    Returns:
        List of entity IDs that are discoverable but not yet known
    """
    if observer_id not in state.entities:
        return []

    observer = state.entities[observer_id]
    if observer.type not in ("pc", "npc"):
        return []

    search_zone = zone_id or getattr(observer, "current_zone", None)
    if not search_zone:
        return []

    discoverable = []
    for entity_id, entity in state.entities.items():
        if (
            entity_id != observer_id
            and getattr(entity, "current_zone", None) == search_zone
        ):

            # Check if visible but not yet known
            if (
                can_player_see(observer_id, entity, state)
                and observer_id not in entity.meta.known_by
            ):
                discoverable.append(entity_id)

    return discoverable


def _publish_discovery_events(
    state: GameState, discoverer_id: str, zone_id: str, discovered_entities: List[str]
) -> List[str]:
    """
    Publish discovery events to the event bus for other systems to react.

    Args:
        state: Current game state
        discoverer_id: Actor who made the discovery
        zone_id: Zone where discovery occurred
        discovered_entities: List of entity IDs that were discovered

    Returns:
        List of event names that were published
    """
    events_published = []

    try:
        # Use deferred import to avoid circular dependencies
        try:
            events_module = importlib.import_module("router.events")
        except ImportError:
            try:
                events_module = importlib.import_module("backend.router.events")
            except ImportError:
                # Event bus not available, skip publishing
                return events_published

        event_bus = events_module.event_bus

        # Publish individual discovery events
        for entity_id in discovered_entities:
            entity = state.entities.get(entity_id)
            if entity:
                event_name = f"entity.discovered"
                event_bus.publish(
                    event_name,
                    {
                        "discoverer": discoverer_id,
                        "discovered_entity": entity_id,
                        "entity_type": entity.type,
                        "zone": zone_id,
                        "timestamp": state.scene.round,
                    },
                )
                events_published.append(event_name)

        # Publish bulk discovery event
        if discovered_entities:
            event_name = "zone.entities_discovered"
            event_bus.publish(
                event_name,
                {
                    "discoverer": discoverer_id,
                    "discovered_entities": discovered_entities,
                    "zone": zone_id,
                    "count": len(discovered_entities),
                    "timestamp": state.scene.round,
                },
            )
            events_published.append(event_name)

    except Exception:
        # Event publishing is optional - core functionality should work even if events fail
        pass

    return events_published


def trigger_exploration_events(
    state: GameState, explorer_id: str, from_zone: Optional[str], to_zone: str
) -> Dict[str, Any]:
    """
    Trigger all exploration-related events when an actor moves between zones.

    Args:
        state: Current game state
        explorer_id: Actor who is exploring
        from_zone: Zone the actor came from (None if initial placement)
        to_zone: Zone the actor entered

    Returns:
        Dictionary with exploration results
    """
    # Perform auto-reveal
    reveal_results = auto_reveal_on_zone_entry(state, explorer_id, to_zone)

    # Check for mutual discoveries with other actors in the zone
    mutual_discoveries = []
    for other_id, other_entity in state.entities.items():
        if (
            other_id != explorer_id
            and other_entity.type in ("pc", "npc")
            and getattr(other_entity, "current_zone", None) == to_zone
        ):

            mutual_result = check_mutual_discovery(state, explorer_id, other_id)
            if any(mutual_result.values()):
                mutual_discoveries.append(
                    {"other_actor": other_id, "results": mutual_result}
                )

    # Publish zone entry event
    try:
        try:
            events_module = importlib.import_module("router.events")
        except ImportError:
            try:
                events_module = importlib.import_module("backend.router.events")
            except ImportError:
                events_module = None

        if events_module:
            event_bus = events_module.event_bus
            event_bus.publish(
                "zone.entered",
                {
                    "actor": explorer_id,
                    "from_zone": from_zone,
                    "to_zone": to_zone,
                    "discovered_count": len(reveal_results["discovered"]),
                    "mutual_discoveries": len(mutual_discoveries),
                    "timestamp": state.scene.round,
                },
            )
    except Exception:
        # Event publishing is optional
        pass

    return {
        "reveal_results": reveal_results,
        "mutual_discoveries": mutual_discoveries,
        "explorer": explorer_id,
        "zone": to_zone,
    }
