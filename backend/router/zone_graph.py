"""
Zone Graph Utilities - Core graph operations for zone-based movement and pathfinding.

This module provides efficient graph operations for the zone system, including
adjacency checks, pathfinding, and movement validation.
"""

import sys
import os
import heapq
from collections import deque
from typing import Dict, List, Optional, Any, Set, Tuple, Union, TYPE_CHECKING

# Add project root to path for models import
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

if TYPE_CHECKING:
    from models.space import Exit
    from .game_state import GameState, Entity, Zone, PC, NPC

# Import GameState for runtime use in functions
from .game_state import GameState


def get_zone(world: "GameState", zone_id: str) -> "Zone":
    """
    Get a zone by ID with clean error handling.

    Args:
        world: Game state containing zones
        zone_id: Zone ID to retrieve

    Returns:
        Zone object

    Raises:
        ValueError: If zone is not found
    """
    zone = world.zones.get(zone_id)
    if not zone:
        raise ValueError(f"Zone '{zone_id}' not found")
    return zone


def list_exits(
    zone: "Zone",
    world: "GameState",
    include_blocked: bool = False,
    include_conditional: bool = True,
) -> List["Exit"]:
    """
    List usable exits from a zone.

    Args:
        zone: Zone to get exits from
        world: Game state for context
        include_blocked: Whether to include blocked exits
        include_conditional: Whether to include exits with conditions

    Returns:
        List of Exit objects that are currently usable
    """
    exits = []
    for exit in zone.exits:
        # Skip blocked exits unless explicitly requested
        if exit.blocked and not include_blocked:
            continue

        # Skip conditional exits if not requested
        if exit.conditions and not include_conditional:
            continue

        exits.append(exit)

    return exits


def describe_exits(
    zone: "Zone",
    world: "GameState",
    pov_id: Optional[str] = None,
    include_blocked: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get human-readable exit descriptions for a zone.

    Args:
        zone: Zone to describe exits for
        world: Game state for context
        pov_id: Optional point-of-view actor for visibility checks
        include_blocked: Whether to include blocked exits

    Returns:
        List of exit description dictionaries
    """
    exits = list_exits(zone, world, include_blocked=include_blocked)
    descriptions = []

    for exit in exits:
        # Check if target zone is visible
        target_zone = world.zones.get(exit.to)
        if not target_zone or target_zone.meta.gm_only:
            continue

        descriptions.append(
            {
                "to": exit.to,
                "label": exit.get_display_label(dict(world.zones)),
                "direction": exit.direction,
                "blocked": exit.blocked,
                "has_conditions": bool(exit.conditions),
                "target_name": target_zone.name if target_zone else "Unknown",
            }
        )

    return descriptions


def is_adjacent(
    zone_a_id: str, zone_b_id: str, world: "GameState", allow_blocked: bool = False
) -> bool:
    """
    Check if two zones are directly connected.

    Args:
        zone_a_id: Source zone ID
        zone_b_id: Target zone ID
        world: Game state containing zones
        allow_blocked: Whether to consider blocked exits as valid

    Returns:
        True if zones are adjacent
    """
    try:
        zone_a = get_zone(world, zone_a_id)
    except ValueError:
        return False

    for exit in zone_a.exits:
        if exit.to == zone_b_id:
            return allow_blocked or not exit.blocked

    return False


def path_exists(
    start: str,
    goal: str,
    world: "GameState",
    allow_blocked: bool = False,
    max_depth: int = 50,
) -> bool:
    """
    Check if a path exists between two zones using breadth-first search.

    Args:
        start: Starting zone ID
        goal: Goal zone ID
        world: Game state containing zones
        allow_blocked: Whether blocked exits are traversable
        max_depth: Maximum search depth to prevent infinite loops

    Returns:
        True if a path exists
    """
    if start == goal:
        return True

    visited: Set[str] = set()
    queue: deque = deque([(start, 0)])

    while queue:
        current, depth = queue.popleft()

        if depth > max_depth:
            break

        if current in visited:
            continue

        visited.add(current)

        try:
            zone = get_zone(world, current)
        except ValueError:
            continue

        for exit in zone.exits:
            if exit.blocked and not allow_blocked:
                continue

            if exit.to == goal:
                return True

            if exit.to not in visited:
                queue.append((exit.to, depth + 1))

    return False


def find_shortest_path(
    start: str,
    goal: str,
    world: "GameState",
    allow_blocked: bool = False,
    max_depth: int = 50,
) -> Optional[List[str]]:
    """
    Find the shortest path between two zones.

    Args:
        start: Starting zone ID
        goal: Goal zone ID
        world: Game state containing zones
        allow_blocked: Whether blocked exits are traversable
        max_depth: Maximum search depth

    Returns:
        List of zone IDs representing the path, or None if no path exists
    """
    if start == goal:
        return [start]

    visited: Set[str] = set()
    queue: deque = deque([(start, [start], 0)])

    while queue:
        current, path, depth = queue.popleft()

        if depth > max_depth:
            continue

        if current in visited:
            continue

        visited.add(current)

        try:
            zone = get_zone(world, current)
        except ValueError:
            continue

        for exit in zone.exits:
            if exit.blocked and not allow_blocked:
                continue

            if exit.to == goal:
                return path + [exit.to]

            if exit.to not in visited:
                queue.append((exit.to, path + [exit.to], depth + 1))

    return None


def get_adjacent_zones(
    zone_id: str, world: "GameState", include_blocked: bool = False
) -> List[str]:
    """
    Get list of zones adjacent to the given zone.

    Args:
        zone_id: Zone to get neighbors for
        world: Game state containing zones
        include_blocked: Whether to include blocked connections

    Returns:
        List of adjacent zone IDs
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return []

    adjacent = []
    for exit in zone.exits:
        if exit.blocked and not include_blocked:
            continue
        adjacent.append(exit.to)

    return adjacent


def is_exit_usable(
    exit: "Exit", actor: "Entity", world: "GameState"
) -> Tuple[bool, Optional[str]]:
    """
    Check if an exit is usable by a specific actor.

    Args:
        exit: Exit to check
        actor: Actor attempting to use the exit
        world: Game state for context

    Returns:
        Tuple of (is_usable, reason_if_not)
    """
    if exit.blocked:
        return False, "blocked"

    if not exit.conditions:
        return True, None

    # Check each condition
    for condition_type, condition_value in exit.conditions.items():
        if condition_type == "key_required":
            # Check if actor has the required key (only for PC/NPC with inventory)
            actor_inventory = getattr(actor, "inventory", None)
            if actor_inventory:
                # Handle both dict-like and list-like inventory formats
                if isinstance(actor_inventory, dict):
                    items = list(actor_inventory.keys())  # For dict inventory, use keys
                elif isinstance(actor_inventory, list):
                    items = actor_inventory  # For list inventory, use as-is
                elif hasattr(actor_inventory, "items"):
                    items = list(actor_inventory.items())  # For other dict-like objects
                else:
                    items = []  # Fallback for unknown inventory types

                if condition_value not in items:
                    return False, f"requires {condition_value}"
            else:
                return False, f"requires {condition_value}"
        elif condition_type == "level_required":
            # Check actor level (attribute or tag)
            actor_level = getattr(actor, "level", None)
            if actor_level is None:
                # Check tags for level if not found as attribute
                actor_tags = getattr(actor, "tags", {})
                actor_level = actor_tags.get("level", 1)
            required_level = int(condition_value)
            if actor_level < required_level:
                return False, f"requires level {required_level}"
        elif condition_type == "tag_required":
            # Check if actor has required tag
            actor_tags = getattr(actor, "tags", {})
            if condition_value not in actor_tags:
                return False, f"requires {condition_value}"
        elif condition_type == "stat_check":
            # Placeholder for stat-based checks
            return False, f"requires {condition_value} check"
        # Add more condition types as needed

    return True, None


def zone_has_tag(zone: "Zone", tag: str) -> bool:
    """
    Check if a zone has a specific tag.

    Args:
        zone: Zone to check
        tag: Tag to look for

    Returns:
        True if zone has the tag
    """
    return zone.has_tag(tag)


def zone_is_public(zone: "Zone") -> bool:
    """
    Check if a zone is publicly visible.

    Args:
        zone: Zone to check

    Returns:
        True if zone is public
    """
    return zone.meta.visibility == "public"


def set_zone_tag(zone: "Zone", tag: str) -> None:
    """
    Add a tag to a zone and update metadata.

    Args:
        zone: Zone to modify
        tag: Tag to add
    """
    zone.add_tag(tag)


def remove_zone_tag(zone: "Zone", tag: str) -> bool:
    """
    Remove a tag from a zone.

    Args:
        zone: Zone to modify
        tag: Tag to remove

    Returns:
        True if tag was removed
    """
    return zone.remove_tag(tag)


def get_zones_with_tag(world: "GameState", tag: str) -> List["Zone"]:
    """
    Get all zones that have a specific tag.

    Args:
        world: Game state containing zones
        tag: Tag to search for

    Returns:
        List of zones with the tag
    """
    return [zone for zone in world.zones.values() if zone.has_tag(tag)]


def get_reachable_zones(
    start: str, world: "GameState", allow_blocked: bool = False, max_depth: int = 50
) -> Set[str]:
    """
    Get all zones reachable from a starting zone.

    Args:
        start: Starting zone ID
        world: Game state containing zones
        allow_blocked: Whether blocked exits are traversable
        max_depth: Maximum search depth

    Returns:
        Set of reachable zone IDs
    """
    reachable: Set[str] = set()
    visited: Set[str] = set()
    queue: deque = deque([(start, 0)])

    while queue:
        current, depth = queue.popleft()

        if depth > max_depth or current in visited:
            continue

        visited.add(current)
        reachable.add(current)

        try:
            zone = get_zone(world, current)
        except ValueError:
            continue

        for exit in zone.exits:
            if exit.blocked and not allow_blocked:
                continue
            if exit.to not in visited:
                queue.append((exit.to, depth + 1))

    return reachable


def validate_zone_graph(world: "GameState") -> List[str]:
    """
    Validate the zone graph for common issues.

    Args:
        world: Game state to validate

    Returns:
        List of validation error messages
    """
    errors = []

    for zone_id, zone in world.zones.items():
        # Check for exits to non-existent zones
        for exit in zone.exits:
            if exit.to not in world.zones:
                errors.append(f"Zone {zone_id} has exit to non-existent zone {exit.to}")

        # Check for duplicate exits to same zone
        exit_targets = [exit.to for exit in zone.exits]
        duplicates = set(
            [target for target in exit_targets if exit_targets.count(target) > 1]
        )
        for duplicate in duplicates:
            errors.append(f"Zone {zone_id} has multiple exits to zone {duplicate}")

    return errors


# =============================================================================
# Zone Discovery & Memory Tracking
# =============================================================================


def reveal_adjacent_zones(
    actor_id: str, current_zone: "Zone", world: "GameState"
) -> List[str]:
    """
    Reveal adjacent zones to an actor and mark them as discovered.

    This function should be called when an actor enters a zone or uses get_info("zone").
    It automatically discovers all adjacent zones that are visible to the actor.
    Blocked exits are not revealed unless the actor can see the destination somehow.

    Args:
        actor_id: Actor ID who is discovering zones
        current_zone: The zone the actor is currently in
        world: Game state containing zones

    Returns:
        List of newly discovered zone IDs
    """
    newly_discovered = []

    for exit in current_zone.exits:
        # Skip blocked exits - they shouldn't be automatically revealed
        if exit.blocked:
            continue

        target_zone = world.zones.get(exit.to)
        if not target_zone:
            continue

        # Only reveal zones that are not GM-only
        if target_zone.meta.gm_only:
            continue

        # Mark as discovered if not already discovered
        if target_zone.discover_by(actor_id):
            newly_discovered.append(target_zone.id)

    return newly_discovered


def discover_zone(actor_id: str, zone_id: str, world: "GameState") -> bool:
    """
    Mark a specific zone as discovered by an actor.

    Args:
        actor_id: Actor ID who discovered the zone
        zone_id: Zone ID to mark as discovered
        world: Game state containing zones

    Returns:
        True if this was a new discovery, False if already discovered or zone not found
    """
    zone = world.zones.get(zone_id)
    if not zone:
        return False

    return zone.discover_by(actor_id)


def is_zone_discovered(actor_id: str, zone_id: str, world: "GameState") -> bool:
    """
    Check if a zone has been discovered by an actor.

    Args:
        actor_id: Actor ID to check
        zone_id: Zone ID to check
        world: Game state containing zones

    Returns:
        True if the zone has been discovered by this actor
    """
    zone = world.zones.get(zone_id)
    if not zone:
        return False

    return zone.is_discovered_by(actor_id)


def get_discovered_zones(actor_id: str, world: "GameState") -> List["Zone"]:
    """
    Get all zones discovered by an actor.

    Args:
        actor_id: Actor ID to get discoveries for
        world: Game state containing zones

    Returns:
        List of Zone objects discovered by the actor
    """
    return [zone for zone in world.zones.values() if zone.is_discovered_by(actor_id)]


def get_undiscovered_adjacent_zones(
    actor_id: str, zone_id: str, world: "GameState"
) -> List[str]:
    """
    Get adjacent zones that haven't been discovered yet by an actor.

    Args:
        actor_id: Actor ID to check discoveries for
        zone_id: Current zone ID
        world: Game state containing zones

    Returns:
        List of undiscovered adjacent zone IDs
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return []

    undiscovered = []
    for exit in zone.exits:
        target_zone = world.zones.get(exit.to)
        if (
            target_zone
            and not target_zone.is_discovered_by(actor_id)
            and not target_zone.meta.gm_only
        ):
            undiscovered.append(exit.to)

    return undiscovered


def get_zone_discovery_map(actor_id: str, world: "GameState") -> Dict[str, str]:
    """
    Get a discovery status map for all zones from an actor's perspective.

    Args:
        actor_id: Actor ID to generate map for
        world: Game state containing zones

    Returns:
        Dictionary mapping zone IDs to discovery status ("discovered", "undiscovered", "hidden")
    """
    discovery_map = {}

    for zone_id, zone in world.zones.items():
        if zone.meta.gm_only:
            discovery_map[zone_id] = "hidden"
        elif zone.is_discovered_by(actor_id):
            discovery_map[zone_id] = "discovered"
        else:
            discovery_map[zone_id] = "undiscovered"

    return discovery_map


# =============================================================================
# Zone Graph Events - Dynamic Environment System
# =============================================================================


def block_exit(
    zone_id: str,
    target_id: str,
    world: "GameState",
    cause: Optional[str] = None,
    reason: Optional[str] = None,
    emit_event: bool = True,
) -> bool:
    """
    Block an exit between zones and optionally emit an event.

    Args:
        zone_id: ID of zone containing the exit
        target_id: ID of target zone to block access to
        world: Game state containing zones
        cause: Reason for blocking (e.g., "combat", "trap", "magic")
        reason: Human-readable reason (e.g., "The door slams shut!")
        emit_event: Whether to emit zone_graph.exit_blocked event

    Returns:
        True if exit was found and blocked, False otherwise
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return False

    exit_found = False
    for exit in zone.exits:
        if exit.to == target_id:
            if not exit.blocked:  # Only change if not already blocked
                exit.blocked = True
                zone.meta.touch()
                exit_found = True

                if emit_event:
                    world.emit(
                        "zone_graph.exit_blocked",
                        from_zone=zone_id,
                        to_zone=target_id,
                        cause=cause,
                        reason=reason,
                        exit=exit.model_dump(),
                    )
                break

    return exit_found


def unblock_exit(
    zone_id: str,
    target_id: str,
    world: "GameState",
    cause: Optional[str] = None,
    reason: Optional[str] = None,
    emit_event: bool = True,
) -> bool:
    """
    Unblock an exit between zones and optionally emit an event.

    Args:
        zone_id: ID of zone containing the exit
        target_id: ID of target zone to unblock access to
        world: Game state containing zones
        cause: Reason for unblocking (e.g., "key_used", "spell", "time")
        reason: Human-readable reason (e.g., "The door creaks open!")
        emit_event: Whether to emit zone_graph.exit_unblocked event

    Returns:
        True if exit was found and unblocked, False otherwise
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return False

    exit_found = False
    for exit in zone.exits:
        if exit.to == target_id:
            if exit.blocked:  # Only change if currently blocked
                exit.blocked = False
                zone.meta.touch()
                exit_found = True

                if emit_event:
                    world.emit(
                        "zone_graph.exit_unblocked",
                        from_zone=zone_id,
                        to_zone=target_id,
                        cause=cause,
                        reason=reason,
                        exit=exit.model_dump(),
                    )
                break

    return exit_found


def toggle_exit(
    zone_id: str,
    target_id: str,
    world: "GameState",
    cause: Optional[str] = None,
    emit_event: bool = True,
) -> Optional[bool]:
    """
    Toggle the blocked status of an exit.

    Args:
        zone_id: ID of zone containing the exit
        target_id: ID of target zone
        world: Game state containing zones
        cause: Reason for toggle (e.g., "lever", "button", "spell")
        emit_event: Whether to emit events

    Returns:
        True if now blocked, False if now unblocked, None if exit not found
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return None

    for exit in zone.exits:
        if exit.to == target_id:
            if exit.blocked:
                unblock_exit(zone_id, target_id, world, cause, emit_event=emit_event)
                return False
            else:
                block_exit(zone_id, target_id, world, cause, emit_event=emit_event)
                return True

    return None


def create_exit(
    zone_id: str,
    target_id: str,
    world: "GameState",
    direction: Optional[str] = None,
    label: Optional[str] = None,
    blocked: bool = False,
    conditions: Optional[Dict[str, str]] = None,
    cause: Optional[str] = None,
    emit_event: bool = True,
) -> bool:
    """
    Create a new exit between zones and optionally emit an event.

    Args:
        zone_id: ID of zone to add exit to
        target_id: ID of target zone
        world: Game state containing zones
        direction: Optional direction (e.g., "north", "up")
        label: Optional label (e.g., "Hidden Door")
        blocked: Whether exit starts blocked
        conditions: Optional travel conditions
        cause: Reason for creation (e.g., "magic", "explosion", "construction")
        emit_event: Whether to emit zone_graph.exit_created event

    Returns:
        True if exit was created, False if zone not found or exit already exists
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return False

    # Check if exit already exists
    if any(exit.to == target_id for exit in zone.exits):
        return False

    # Create new exit
    exit = zone.add_exit(
        to=target_id,
        direction=direction,
        label=label,
        blocked=blocked,
        conditions=conditions,
    )

    if emit_event:
        world.emit(
            "zone_graph.exit_created",
            from_zone=zone_id,
            to_zone=target_id,
            direction=direction,
            label=label,
            blocked=blocked,
            conditions=conditions,
            cause=cause,
            exit=exit.model_dump(),
        )

    return True


def destroy_exit(
    zone_id: str,
    target_id: str,
    world: "GameState",
    cause: Optional[str] = None,
    reason: Optional[str] = None,
    emit_event: bool = True,
) -> bool:
    """
    Permanently destroy an exit between zones and optionally emit an event.

    Args:
        zone_id: ID of zone containing the exit
        target_id: ID of target zone
        world: Game state containing zones
        cause: Reason for destruction (e.g., "collapse", "explosion", "magic")
        reason: Human-readable reason (e.g., "The tunnel collapses!")
        emit_event: Whether to emit zone_graph.exit_destroyed event

    Returns:
        True if exit was found and destroyed, False otherwise
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return False

    # Find and store exit data before removal
    exit_data = None
    for exit in zone.exits:
        if exit.to == target_id:
            exit_data = exit.model_dump()
            break

    if exit_data:
        # Remove the exit
        if zone.remove_exit(target_id):
            if emit_event:
                world.emit(
                    "zone_graph.exit_destroyed",
                    from_zone=zone_id,
                    to_zone=target_id,
                    cause=cause,
                    reason=reason,
                    exit=exit_data,
                )
            return True

    return False


def set_exit_conditions(
    zone_id: str,
    target_id: str,
    conditions: Optional[Dict[str, str]],
    world: "GameState",
    cause: Optional[str] = None,
    emit_event: bool = True,
) -> bool:
    """
    Set or clear conditions on an exit.

    Args:
        zone_id: ID of zone containing the exit
        target_id: ID of target zone
        conditions: New conditions dict (None to clear)
        world: Game state containing zones
        cause: Reason for change (e.g., "puzzle_solved", "key_found")
        emit_event: Whether to emit zone_graph.exit_conditions_changed event

    Returns:
        True if exit was found and modified, False otherwise
    """
    try:
        zone = get_zone(world, zone_id)
    except ValueError:
        return False

    for exit in zone.exits:
        if exit.to == target_id:
            old_conditions = exit.conditions
            exit.conditions = conditions
            zone.meta.touch()

            if emit_event:
                world.emit(
                    "zone_graph.exit_conditions_changed",
                    from_zone=zone_id,
                    to_zone=target_id,
                    old_conditions=old_conditions,
                    new_conditions=conditions,
                    cause=cause,
                    exit=exit.model_dump(),
                )
            return True

    return False


def get_zone_graph_events() -> List[str]:
    """
    Get list of all zone graph event types.

    Returns:
        List of event type strings
    """
    return [
        "zone_graph.exit_blocked",
        "zone_graph.exit_unblocked",
        "zone_graph.exit_created",
        "zone_graph.exit_destroyed",
        "zone_graph.exit_conditions_changed",
    ]


# =============================================================================
# Cost-Based Pathfinding with Terrain Support
# =============================================================================


def find_lowest_cost_path(
    start: str,
    goal: str,
    world: "GameState",
    actor: Optional["Entity"] = None,
    terrain_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
    allow_blocked: bool = False,
    max_cost: float = float("inf"),
) -> Optional[Tuple[List[str], float]]:
    """
    Find the lowest-cost path between two zones using Dijkstra's algorithm.

    Args:
        start: Starting zone ID
        goal: Goal zone ID
        world: Game state containing zones
        actor: Optional actor for personalized costs
        terrain_modifiers: Optional terrain cost modifiers
        allow_blocked: Whether blocked exits are traversable
        max_cost: Maximum acceptable total cost

    Returns:
        Tuple of (path_as_zone_list, total_cost) or None if no path exists
    """
    if start == goal:
        return ([start], 0.0)

    # Priority queue: (cost, zone_id, path)
    pq = [(0.0, start, [start])]
    visited = set()

    while pq:
        current_cost, current_zone, path = heapq.heappop(pq)

        if current_cost > max_cost:
            continue

        if current_zone in visited:
            continue

        visited.add(current_zone)

        if current_zone == goal:
            return (path, current_cost)

        try:
            zone = get_zone(world, current_zone)
        except ValueError:
            continue

        for exit in zone.exits:
            if exit.blocked and not allow_blocked:
                continue

            if exit.to in visited:
                continue

            # Calculate movement cost for this exit
            exit_cost = exit.get_movement_cost(actor, terrain_modifiers)
            new_cost = current_cost + exit_cost

            if new_cost <= max_cost:
                heapq.heappush(pq, (new_cost, exit.to, path + [exit.to]))

    return None


def find_multiple_paths(
    start: str,
    goal: str,
    world: "GameState",
    actor: Optional["Entity"] = None,
    terrain_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
    allow_blocked: bool = False,
    max_paths: int = 3,
    cost_tolerance: float = 1.5,
) -> List[Tuple[List[str], float]]:
    """
    Find multiple paths between zones, sorted by cost.

    Args:
        start: Starting zone ID
        goal: Goal zone ID
        world: Game state containing zones
        actor: Optional actor for personalized costs
        terrain_modifiers: Optional terrain cost modifiers
        allow_blocked: Whether blocked exits are traversable
        max_paths: Maximum number of paths to return
        cost_tolerance: Maximum cost multiplier from optimal path

    Returns:
        List of (path, cost) tuples sorted by cost
    """
    if start == goal:
        return [([start], 0.0)]

    paths = []
    visited_paths = set()

    # Find the optimal path first
    optimal_result = find_lowest_cost_path(
        start, goal, world, actor, terrain_modifiers, allow_blocked
    )

    if not optimal_result:
        return []

    optimal_path, optimal_cost = optimal_result
    max_acceptable_cost = optimal_cost * cost_tolerance
    paths.append((optimal_path, optimal_cost))
    visited_paths.add(tuple(optimal_path))

    # Use modified Dijkstra to find alternative paths
    # Priority queue: (cost, zone_id, path, blocked_edges)
    pq = [(0.0, start, [start], set())]

    while pq and len(paths) < max_paths:
        current_cost, current_zone, path, blocked_edges = heapq.heappop(pq)

        if current_cost > max_acceptable_cost:
            continue

        if current_zone == goal:
            path_tuple = tuple(path)
            if path_tuple not in visited_paths:
                paths.append((path, current_cost))
                visited_paths.add(path_tuple)
                continue

        try:
            zone = get_zone(world, current_zone)
        except ValueError:
            continue

        for exit in zone.exits:
            edge = (current_zone, exit.to)

            if edge in blocked_edges:
                continue

            if exit.blocked and not allow_blocked:
                continue

            if exit.to in path:  # Avoid cycles
                continue

            exit_cost = exit.get_movement_cost(actor, terrain_modifiers)
            new_cost = current_cost + exit_cost

            if new_cost <= max_acceptable_cost:
                heapq.heappush(pq, (new_cost, exit.to, path + [exit.to], blocked_edges))

                # Also add a version that blocks this edge to force alternative routes
                if len(paths) < max_paths:
                    new_blocked = blocked_edges.copy()
                    new_blocked.add(edge)
                    heapq.heappush(pq, (current_cost, current_zone, path, new_blocked))

    return sorted(paths, key=lambda x: x[1])


def calculate_path_cost(
    path: List[str],
    world: "GameState",
    actor: Optional["Entity"] = None,
    terrain_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
) -> float:
    """
    Calculate the total cost of a given path.

    Args:
        path: List of zone IDs representing the path
        world: Game state containing zones
        actor: Optional actor for personalized costs
        terrain_modifiers: Optional terrain cost modifiers

    Returns:
        Total path cost
    """
    if len(path) < 2:
        return 0.0

    total_cost = 0.0

    for i in range(len(path) - 1):
        current_zone_id = path[i]
        next_zone_id = path[i + 1]

        try:
            zone = get_zone(world, current_zone_id)
        except ValueError:
            return float("inf")  # Invalid path

        # Find the exit to the next zone
        exit_found = False
        for exit in zone.exits:
            if exit.to == next_zone_id:
                total_cost += exit.get_movement_cost(actor, terrain_modifiers)
                exit_found = True
                break

        if not exit_found:
            return float("inf")  # Invalid path

    return total_cost


def get_reachable_zones_with_cost(
    start: str,
    world: "GameState",
    actor: Optional["Entity"] = None,
    terrain_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
    max_cost: float = 10.0,
    allow_blocked: bool = False,
) -> Dict[str, float]:
    """
    Get all zones reachable within a given cost budget.

    Args:
        start: Starting zone ID
        world: Game state containing zones
        actor: Optional actor for personalized costs
        terrain_modifiers: Optional terrain cost modifiers
        max_cost: Maximum total cost to consider
        allow_blocked: Whether blocked exits are traversable

    Returns:
        Dictionary mapping zone IDs to minimum cost to reach them
    """
    if start not in world.zones:
        return {}

    # Priority queue: (cost, zone_id)
    pq = [(0.0, start)]
    costs = {start: 0.0}

    while pq:
        current_cost, current_zone = heapq.heappop(pq)

        if current_cost > costs.get(current_zone, float("inf")):
            continue  # Already found a better path

        try:
            zone = get_zone(world, current_zone)
        except ValueError:
            continue

        for exit in zone.exits:
            if exit.blocked and not allow_blocked:
                continue

            exit_cost = exit.get_movement_cost(actor, terrain_modifiers)
            new_cost = current_cost + exit_cost

            if new_cost <= max_cost and new_cost < costs.get(exit.to, float("inf")):
                costs[exit.to] = new_cost
                heapq.heappush(pq, (new_cost, exit.to))

    return costs


def get_terrain_modifiers_template() -> Dict[str, Dict[str, float]]:
    """
    Get a template for terrain modifiers that can be customized per game.

    Returns:
        Dictionary template for terrain cost modifiers
    """
    return {
        "stairs": {
            "climbing": 0.5,  # Good at climbing
            "heavy_armor": 2.0,  # Slow in heavy armor
        },
        "mud": {
            "light_step": 0.7,  # Light on feet
            "heavy_armor": 2.5,  # Very slow in heavy armor
        },
        "fire": {
            "fire_resistance": 0.5,  # Resistant to fire
            "ice_attuned": 3.0,  # Vulnerable to fire
        },
        "water": {
            "swimming": 0.3,  # Good swimmer
            "heavy_armor": 10.0,  # Nearly impossible in heavy armor
        },
        "ice": {
            "ice_walking": 0.5,  # Stable on ice
            "clumsy": 2.0,  # Prone to slipping
        },
        "thorns": {
            "nature_walk": 0.6,  # Used to natural terrain
            "thick_skin": 0.8,  # Less damage from thorns
        },
        "sand": {
            "desert_travel": 0.7,  # Used to desert
            "heavy_armor": 1.8,  # Difficult in armor
        },
        "rubble": {
            "sure_footed": 0.7,  # Good balance
            "heavy_armor": 1.5,  # Awkward in armor
        },
        "swamp": {
            "swamp_walker": 0.5,  # At home in swamps
            "disease_prone": 1.5,  # Slower due to caution
        },
        "lava": {
            "fire_immunity": 0.2,  # Immune to fire
            "ice_attuned": 50.0,  # Extremely vulnerable
        },
    }


# =============================================================================
# Zone Hierarchies & Regional Grouping
# =============================================================================


def zones_in_region(region: str, world: "GameState") -> List["Zone"]:
    """
    Get all zones belonging to a specific region.

    Args:
        region: Region name to search for
        world: Game state containing zones

    Returns:
        List of Zone objects in the specified region
    """
    return [zone for zone in world.zones.values() if zone.is_in_region(region)]


def get_all_regions(world: "GameState") -> List[str]:
    """
    Get a list of all unique regions defined in the world.

    Args:
        world: Game state containing zones

    Returns:
        Sorted list of unique region names (excludes None/unassigned zones)
    """
    regions = set()
    for zone in world.zones.values():
        if zone.region:
            regions.add(zone.region)
    return sorted(list(regions))


def get_region_summary(world: "GameState") -> Dict[str, Dict[str, Any]]:
    """
    Get a comprehensive summary of all regions and their zones.

    Args:
        world: Game state containing zones

    Returns:
        Dictionary mapping region names to summary information
    """
    summary = {}

    # Get all regions including unassigned
    regions = get_all_regions(world)
    regions.append("Unassigned")  # Add unassigned category

    for region in regions:
        if region == "Unassigned":
            zones = [zone for zone in world.zones.values() if not zone.region]
        else:
            zones = zones_in_region(region, world)

        # Calculate region statistics
        zone_count = len(zones)
        zone_ids = [zone.id for zone in zones]

        # Count exits within region vs external
        internal_exits = 0
        external_exits = 0
        for zone in zones:
            for exit in zone.exits:
                target_zone = world.zones.get(exit.to)
                if target_zone and target_zone.is_in_region(region):
                    internal_exits += 1
                elif target_zone:  # External zone exists
                    external_exits += 1

        # Collect unique tags across region
        region_tags = set()
        for zone in zones:
            region_tags.update(zone.tags)

        summary[region] = {
            "zone_count": zone_count,
            "zone_ids": sorted(zone_ids),
            "internal_exits": internal_exits,
            "external_exits": external_exits,
            "common_tags": sorted(list(region_tags)),
            "zones": zones,  # Include full zone objects for detailed access
        }

    return summary


def find_inter_region_connections(
    world: "GameState",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Find all connections between different regions.

    Args:
        world: Game state containing zones

    Returns:
        Dictionary mapping region pairs to connection details
    """
    connections = {}

    for zone in world.zones.values():
        source_region = zone.region or "Unassigned"

        for exit in zone.exits:
            target_zone = world.zones.get(exit.to)
            if not target_zone:
                continue

            target_region = target_zone.region or "Unassigned"

            # Only track inter-region connections
            if source_region != target_region:
                # Create bidirectional key (smaller region first for consistency)
                regions = sorted([source_region, target_region])
                key = f"{regions[0]} <-> {regions[1]}"

                if key not in connections:
                    connections[key] = []

                connection_info = {
                    "from_zone": zone.id,
                    "to_zone": target_zone.id,
                    "from_region": source_region,
                    "to_region": target_region,
                    "exit_direction": exit.direction,
                    "exit_label": exit.label,
                    "cost": exit.cost,
                    "terrain": exit.terrain,
                    "blocked": exit.blocked,
                }
                connections[key].append(connection_info)

    return connections


def set_zone_regions(
    zone_region_mapping: Dict[str, str], world: "GameState"
) -> Dict[str, bool]:
    """
    Bulk assign regions to multiple zones.

    Args:
        zone_region_mapping: Dictionary mapping zone IDs to region names
        world: Game state containing zones

    Returns:
        Dictionary mapping zone IDs to success status
    """
    results = {}

    for zone_id, region in zone_region_mapping.items():
        if zone_id in world.zones:
            world.zones[zone_id].set_region(region)
            results[zone_id] = True
        else:
            results[zone_id] = False

    return results


def find_zones_by_region_pattern(pattern: str, world: "GameState") -> List["Zone"]:
    """
    Find zones whose region matches a pattern (supports wildcards).

    Args:
        pattern: Pattern to match (supports * and ? wildcards)
        world: Game state containing zones

    Returns:
        List of zones with regions matching the pattern
    """
    import fnmatch

    matching_zones = []
    for zone in world.zones.values():
        if zone.region and fnmatch.fnmatch(zone.region, pattern):
            matching_zones.append(zone)

    return matching_zones


def get_region_connectivity_score(region: str, world: "GameState") -> float:
    """
    Calculate a connectivity score for a region based on internal vs external connections.

    Args:
        region: Region name to analyze
        world: Game state containing zones

    Returns:
        Connectivity score (0.0 = isolated, 1.0 = fully internal, >1.0 = hub region)
    """
    zones = zones_in_region(region, world)
    if not zones:
        return 0.0

    internal_exits = 0
    external_exits = 0

    for zone in zones:
        for exit in zone.exits:
            target_zone = world.zones.get(exit.to)
            if target_zone:
                if target_zone.is_in_region(region):
                    internal_exits += 1
                else:
                    external_exits += 1

    total_exits = internal_exits + external_exits
    if total_exits == 0:
        return 0.0  # No connections

    # Score calculation:
    # - 0.0 = no connections
    # - 0.5 = equal internal/external
    # - 1.0 = all internal connections
    # - >1.0 = high external connectivity (hub)
    if internal_exits == 0:
        return external_exits / len(zones)  # Hub score
    else:
        return internal_exits / total_exits


def suggest_region_assignments(
    world: "GameState", similarity_threshold: float = 0.7
) -> Dict[str, List[str]]:
    """
    Suggest region assignments for unassigned zones based on tags and connectivity.

    Args:
        world: Game state containing zones
        similarity_threshold: Minimum similarity score for suggestions

    Returns:
        Dictionary mapping suggested region names to lists of zone IDs
    """
    unassigned_zones = [zone for zone in world.zones.values() if not zone.region]
    if not unassigned_zones:
        return {}

    existing_regions = get_all_regions(world)
    suggestions = {}

    for unassigned_zone in unassigned_zones:
        best_region = None
        best_score = 0.0

        # Check similarity to existing regions
        for region in existing_regions:
            region_zones = zones_in_region(region, world)
            if not region_zones:
                continue

            # Calculate tag similarity
            region_tags = set()
            for rz in region_zones:
                region_tags.update(rz.tags)

            if region_tags and unassigned_zone.tags:
                common_tags = len(region_tags.intersection(unassigned_zone.tags))
                total_tags = len(region_tags.union(unassigned_zone.tags))
                tag_similarity = common_tags / total_tags if total_tags > 0 else 0.0
            else:
                tag_similarity = 0.0

            # Check connectivity to region
            connectivity_score = 0.0
            for exit in unassigned_zone.exits:
                target_zone = world.zones.get(exit.to)
                if target_zone and target_zone.is_in_region(region):
                    connectivity_score += 1.0

            # Normalize connectivity by zone's total exits
            if unassigned_zone.exits:
                connectivity_score /= len(unassigned_zone.exits)

            # Combined score (weighted average)
            combined_score = (tag_similarity * 0.6) + (connectivity_score * 0.4)

            if combined_score > best_score and combined_score >= similarity_threshold:
                best_score = combined_score
                best_region = region

        if best_region:
            if best_region not in suggestions:
                suggestions[best_region] = []
            suggestions[best_region].append(unassigned_zone.id)

    return suggestions


# =============================================================================
# Exit Auto-Mirroring Utility
# =============================================================================


def ensure_bidirectional_links(
    world: "GameState", dry_run: bool = False
) -> Dict[str, Any]:
    """
    Automatically generate reciprocal exits for bidirectional zones.

    This function analyzes the zone graph and creates missing reverse exits
    to ensure bidirectional connectivity where expected.

    Args:
        world: Game state containing zones
        dry_run: If True, only report what would be changed without modifying

    Returns:
        Dictionary with analysis results and changes made/proposed
    """
    results = {
        "analyzed_exits": 0,
        "missing_reciprocals": [],
        "created_exits": [],
        "skipped_exits": [],
        "errors": [],
    }

    for zone_id, zone in world.zones.items():
        for exit in zone.exits:
            results["analyzed_exits"] += 1
            target_zone_id = exit.to

            # Check if target zone exists
            if target_zone_id not in world.zones:
                results["errors"].append(
                    {
                        "type": "missing_target_zone",
                        "from_zone": zone_id,
                        "to_zone": target_zone_id,
                        "message": f"Exit from {zone_id} points to non-existent zone {target_zone_id}",
                    }
                )
                continue

            target_zone = world.zones[target_zone_id]

            # Check if reciprocal exit already exists
            has_reciprocal = any(
                target_exit.to == zone_id for target_exit in target_zone.exits
            )

            if not has_reciprocal:
                # Determine reciprocal direction
                reciprocal_direction = _get_reciprocal_direction(exit.direction)

                missing_info = {
                    "from_zone": zone_id,
                    "to_zone": target_zone_id,
                    "original_exit": {
                        "direction": exit.direction,
                        "label": exit.label,
                        "cost": exit.cost,
                        "terrain": exit.terrain,
                        "blocked": exit.blocked,
                    },
                    "proposed_reciprocal": {
                        "direction": reciprocal_direction,
                        "label": _generate_reciprocal_label(
                            exit.label, reciprocal_direction
                        ),
                        "cost": exit.cost,  # Same cost for reciprocal
                        "terrain": exit.terrain,  # Same terrain
                        "blocked": exit.blocked,  # Same blocked status
                    },
                }

                results["missing_reciprocals"].append(missing_info)

                if not dry_run:
                    # Create the reciprocal exit
                    try:
                        reciprocal_exit = target_zone.add_exit(
                            to=zone_id,
                            direction=reciprocal_direction,
                            label=missing_info["proposed_reciprocal"]["label"],
                            cost=exit.cost,
                            terrain=exit.terrain,
                            blocked=exit.blocked,
                            conditions=(
                                exit.conditions.copy() if exit.conditions else None
                            ),
                        )

                        results["created_exits"].append(
                            {
                                "zone": target_zone_id,
                                "exit": {
                                    "to": zone_id,
                                    "direction": reciprocal_direction,
                                    "label": reciprocal_exit.label,
                                    "cost": reciprocal_exit.cost,
                                    "terrain": reciprocal_exit.terrain,
                                },
                            }
                        )

                    except Exception as e:
                        results["errors"].append(
                            {
                                "type": "creation_error",
                                "from_zone": target_zone_id,
                                "to_zone": zone_id,
                                "message": f"Failed to create reciprocal exit: {str(e)}",
                            }
                        )

    return results


def _get_reciprocal_direction(direction: Optional[str]) -> Optional[str]:
    """
    Get the reciprocal direction for a given direction.

    Args:
        direction: Original direction (e.g., "north", "up")

    Returns:
        Reciprocal direction (e.g., "south", "down") or None
    """
    if not direction:
        return None

    direction_map = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
        "northeast": "southwest",
        "northwest": "southeast",
        "southeast": "northwest",
        "southwest": "northeast",
        "in": "out",
        "out": "in",
        "forward": "back",
        "back": "forward",
    }

    return direction_map.get(direction.lower())


def _generate_reciprocal_label(
    original_label: Optional[str], reciprocal_direction: Optional[str]
) -> Optional[str]:
    """
    Generate an appropriate label for a reciprocal exit.

    Args:
        original_label: Label from the original exit
        reciprocal_direction: Direction of the reciprocal exit

    Returns:
        Appropriate label for the reciprocal exit
    """
    if not original_label:
        return reciprocal_direction

    # Try to detect and replace directional terms in the label
    label_direction_map = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
        "upstairs": "downstairs",
        "downstairs": "upstairs",
        "entrance": "exit",
        "exit": "entrance",
    }

    lower_label = original_label.lower()
    for original_dir, reciprocal_dir in label_direction_map.items():
        if original_dir in lower_label:
            return original_label.lower().replace(original_dir, reciprocal_dir).title()

    # If no direction found in label, use the reciprocal direction
    return reciprocal_direction


def validate_bidirectional_consistency(world: "GameState") -> Dict[str, Any]:
    """
    Validate that bidirectional exits have consistent properties.

    Args:
        world: Game state containing zones

    Returns:
        Dictionary with validation results and inconsistencies found
    """
    results = {
        "total_bidirectional_pairs": 0,
        "consistent_pairs": 0,
        "inconsistent_pairs": [],
        "cost_mismatches": [],
        "terrain_mismatches": [],
        "blocked_mismatches": [],
    }

    analyzed_pairs = set()

    for zone_id, zone in world.zones.items():
        for exit in zone.exits:
            target_zone_id = exit.to

            # Skip if target zone doesn't exist
            if target_zone_id not in world.zones:
                continue

            # Create a consistent pair identifier (smaller ID first)
            pair_id = tuple(sorted([zone_id, target_zone_id]))
            if pair_id in analyzed_pairs:
                continue
            analyzed_pairs.add(pair_id)

            target_zone = world.zones[target_zone_id]

            # Find reciprocal exit
            reciprocal_exit = None
            for target_exit in target_zone.exits:
                if target_exit.to == zone_id:
                    reciprocal_exit = target_exit
                    break

            if reciprocal_exit:
                results["total_bidirectional_pairs"] += 1

                # Check for inconsistencies
                inconsistencies = []

                if exit.cost != reciprocal_exit.cost:
                    inconsistencies.append("cost")
                    results["cost_mismatches"].append(
                        {
                            "zone_a": zone_id,
                            "zone_b": target_zone_id,
                            "cost_a_to_b": exit.cost,
                            "cost_b_to_a": reciprocal_exit.cost,
                        }
                    )

                if exit.terrain != reciprocal_exit.terrain:
                    inconsistencies.append("terrain")
                    results["terrain_mismatches"].append(
                        {
                            "zone_a": zone_id,
                            "zone_b": target_zone_id,
                            "terrain_a_to_b": exit.terrain,
                            "terrain_b_to_a": reciprocal_exit.terrain,
                        }
                    )

                if exit.blocked != reciprocal_exit.blocked:
                    inconsistencies.append("blocked_status")
                    results["blocked_mismatches"].append(
                        {
                            "zone_a": zone_id,
                            "zone_b": target_zone_id,
                            "blocked_a_to_b": exit.blocked,
                            "blocked_b_to_a": reciprocal_exit.blocked,
                        }
                    )

                if inconsistencies:
                    results["inconsistent_pairs"].append(
                        {
                            "zone_a": zone_id,
                            "zone_b": target_zone_id,
                            "inconsistencies": inconsistencies,
                        }
                    )
                else:
                    results["consistent_pairs"] += 1

    return results


def fix_bidirectional_inconsistencies(
    world: "GameState", strategy: str = "prefer_lower_cost", dry_run: bool = False
) -> Dict[str, Any]:
    """
    Fix inconsistencies in bidirectional exits.

    Args:
        world: Game state containing zones
        strategy: Strategy for resolving conflicts ("prefer_lower_cost", "prefer_higher_cost", "average")
        dry_run: If True, only report what would be changed

    Returns:
        Dictionary with fixes applied or proposed
    """
    validation_results = validate_bidirectional_consistency(world)

    results = {
        "strategy_used": strategy,
        "cost_fixes": [],
        "terrain_fixes": [],
        "blocked_fixes": [],
        "errors": [],
    }

    # Fix cost mismatches
    for mismatch in validation_results["cost_mismatches"]:
        zone_a_id = mismatch["zone_a"]
        zone_b_id = mismatch["zone_b"]
        cost_a_to_b = mismatch["cost_a_to_b"]
        cost_b_to_a = mismatch["cost_b_to_a"]

        # Determine target cost based on strategy
        if strategy == "prefer_lower_cost":
            target_cost = min(cost_a_to_b, cost_b_to_a)
        elif strategy == "prefer_higher_cost":
            target_cost = max(cost_a_to_b, cost_b_to_a)
        elif strategy == "average":
            target_cost = (cost_a_to_b + cost_b_to_a) / 2
        else:
            results["errors"].append(f"Unknown strategy: {strategy}")
            continue

        fix_info = {
            "zone_a": zone_a_id,
            "zone_b": zone_b_id,
            "old_cost_a_to_b": cost_a_to_b,
            "old_cost_b_to_a": cost_b_to_a,
            "new_cost": target_cost,
        }

        if not dry_run:
            # Apply the fix
            zone_a = world.zones[zone_a_id]
            zone_b = world.zones[zone_b_id]

            # Update exit from A to B
            for exit in zone_a.exits:
                if exit.to == zone_b_id:
                    exit.cost = target_cost
                    break

            # Update exit from B to A
            for exit in zone_b.exits:
                if exit.to == zone_a_id:
                    exit.cost = target_cost
                    break

        results["cost_fixes"].append(fix_info)

    # Fix terrain mismatches (prefer non-None terrain)
    for mismatch in validation_results["terrain_mismatches"]:
        zone_a_id = mismatch["zone_a"]
        zone_b_id = mismatch["zone_b"]
        terrain_a_to_b = mismatch["terrain_a_to_b"]
        terrain_b_to_a = mismatch["terrain_b_to_a"]

        # Prefer non-None terrain
        target_terrain = (
            terrain_a_to_b if terrain_a_to_b is not None else terrain_b_to_a
        )

        fix_info = {
            "zone_a": zone_a_id,
            "zone_b": zone_b_id,
            "old_terrain_a_to_b": terrain_a_to_b,
            "old_terrain_b_to_a": terrain_b_to_a,
            "new_terrain": target_terrain,
        }

        if not dry_run:
            # Apply the fix
            zone_a = world.zones[zone_a_id]
            zone_b = world.zones[zone_b_id]

            # Update both exits
            for exit in zone_a.exits:
                if exit.to == zone_b_id:
                    exit.terrain = target_terrain
                    break

            for exit in zone_b.exits:
                if exit.to == zone_a_id:
                    exit.terrain = target_terrain
                    break

        results["terrain_fixes"].append(fix_info)

    # Fix blocked status mismatches (prefer unblocked)
    for mismatch in validation_results["blocked_mismatches"]:
        zone_a_id = mismatch["zone_a"]
        zone_b_id = mismatch["zone_b"]
        blocked_a_to_b = mismatch["blocked_a_to_b"]
        blocked_b_to_a = mismatch["blocked_b_to_a"]

        # Prefer unblocked (False)
        target_blocked = (
            blocked_a_to_b and blocked_b_to_a
        )  # Only blocked if both are blocked

        fix_info = {
            "zone_a": zone_a_id,
            "zone_b": zone_b_id,
            "old_blocked_a_to_b": blocked_a_to_b,
            "old_blocked_b_to_a": blocked_b_to_a,
            "new_blocked": target_blocked,
        }

        if not dry_run:
            # Apply the fix
            zone_a = world.zones[zone_a_id]
            zone_b = world.zones[zone_b_id]

            # Update both exits
            for exit in zone_a.exits:
                if exit.to == zone_b_id:
                    exit.blocked = target_blocked
                    break

            for exit in zone_b.exits:
                if exit.to == zone_a_id:
                    exit.blocked = target_blocked
                    break

        results["blocked_fixes"].append(fix_info)

    return results


# =============================================================================
# Graph Analysis & Visualization Tools
# =============================================================================


def export_zone_graph(
    world: "GameState",
    format: str = "json",
    include_meta: bool = True,
    include_discovery: bool = False,
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> str:
    """
    Export the zone graph in various formats for analysis and visualization.

    Args:
        world: Game state containing zones
        format: Export format ("json", "graphviz", "mermaid", "cytoscape")
        include_meta: Whether to include metadata fields
        include_discovery: Whether to include discovery information
        actor_perspective: If provided, filter to actor's discovered zones only
        regions_only: If provided, only export zones from these regions

    Returns:
        Formatted graph representation as string
    """
    if format == "json":
        return _export_json(
            world, include_meta, include_discovery, actor_perspective, regions_only
        )
    elif format == "graphviz":
        return _export_graphviz(
            world, include_meta, include_discovery, actor_perspective, regions_only
        )
    elif format == "mermaid":
        return _export_mermaid(
            world, include_meta, include_discovery, actor_perspective, regions_only
        )
    elif format == "cytoscape":
        return _export_cytoscape(
            world, include_meta, include_discovery, actor_perspective, regions_only
        )
    else:
        raise ValueError(f"Unsupported export format: {format}")


def _filter_zones(
    world: "GameState",
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> Dict[str, "Zone"]:
    """Filter zones based on perspective and region constraints."""
    zones = dict(world.zones)

    # Filter by actor discovery
    if actor_perspective:
        zones = {
            zone_id: zone
            for zone_id, zone in zones.items()
            if zone.is_discovered_by(actor_perspective)
        }

    # Filter by regions
    if regions_only:
        zones = {
            zone_id: zone
            for zone_id, zone in zones.items()
            if zone.region in regions_only
        }

    return zones


def _export_json(
    world: "GameState",
    include_meta: bool = True,
    include_discovery: bool = False,
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> str:
    """Export zone graph as structured JSON."""
    import json

    zones = _filter_zones(world, actor_perspective, regions_only)

    graph_data = {
        "metadata": {
            "format": "zone_graph_json",
            "version": "1.0",
            "exported_at": None,  # Could add timestamp if needed
            "total_zones": len(zones),
            "actor_perspective": actor_perspective,
            "regions_filter": regions_only,
        },
        "zones": {},
        "edges": [],
        "regions": {},
        "statistics": {},
    }

    # Export zones
    for zone_id, zone in zones.items():
        zone_data = {
            "id": zone.id,
            "name": zone.name,
            "description": zone.description,
            "region": zone.region,
            "tags": sorted(list(zone.tags)),
        }

        if include_meta and zone.meta:
            zone_data["meta"] = {
                "visibility": zone.meta.visibility,
                "created_at": zone.meta.created_at,
                "last_changed_at": zone.meta.last_changed_at,
            }

        if include_discovery:
            zone_data["discovered_by"] = sorted(list(zone.discovered_by))

        graph_data["zones"][zone_id] = zone_data

    # Export edges (exits)
    for zone_id, zone in zones.items():
        for exit in zone.exits:
            # Only include edges to zones that are in our filtered set
            if exit.to in zones:
                edge_data = {
                    "from": zone_id,
                    "to": exit.to,
                    "direction": exit.direction,
                    "label": exit.label,
                    "cost": exit.cost,
                    "terrain": exit.terrain,
                    "blocked": exit.blocked,
                    "conditions": exit.conditions,
                }
                graph_data["edges"].append(edge_data)

    # Export region summaries
    if any(zone.region for zone in zones.values()):
        region_summary = get_region_summary(world)
        for region_name, region_info in region_summary.items():
            # Filter to zones in our export set
            region_zones = [zid for zid in region_info["zone_ids"] if zid in zones]
            if region_zones:
                graph_data["regions"][region_name] = {
                    "zone_count": len(region_zones),
                    "zone_ids": region_zones,
                    "common_tags": region_info["common_tags"],
                }

    # Calculate statistics
    total_exits = len(graph_data["edges"])
    bidirectional_pairs = 0
    unidirectional_exits = 0

    # Analyze bidirectionality
    exit_pairs = set()
    for edge in graph_data["edges"]:
        pair = tuple(sorted([edge["from"], edge["to"]]))
        if pair in exit_pairs:
            bidirectional_pairs += 1
        else:
            exit_pairs.add(pair)
            unidirectional_exits += 1

    graph_data["statistics"] = {
        "total_zones": len(zones),
        "total_exits": total_exits,
        "bidirectional_pairs": bidirectional_pairs,
        "unidirectional_exits": unidirectional_exits,
        "average_exits_per_zone": total_exits / len(zones) if zones else 0,
        "regions_count": len(graph_data["regions"]),
    }

    return json.dumps(graph_data, indent=2, default=str)


def _export_graphviz(
    world: "GameState",
    include_meta: bool = True,
    include_discovery: bool = False,
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> str:
    """Export zone graph as Graphviz DOT format."""
    zones = _filter_zones(world, actor_perspective, regions_only)

    lines = ["digraph zone_graph {"]
    lines.append("  rankdir=TB;")
    lines.append("  node [shape=box, style=rounded];")
    lines.append("")

    # Group zones by region for better layout
    regions = {}
    unassigned = []

    for zone_id, zone in zones.items():
        if zone.region:
            if zone.region not in regions:
                regions[zone.region] = []
            regions[zone.region].append((zone_id, zone))
        else:
            unassigned.append((zone_id, zone))

    # Create subgraphs for regions
    for region_name, region_zones in regions.items():
        lines.append(f"  subgraph cluster_{region_name.replace(' ', '_')} {{")
        lines.append(f'    label="{region_name}";')
        lines.append("    style=dashed;")
        lines.append("    color=blue;")

        for zone_id, zone in region_zones:
            node_attrs = _get_graphviz_node_attrs(
                zone, include_meta, include_discovery, actor_perspective
            )
            lines.append(f'    "{zone_id}" [{node_attrs}];')

        lines.append("  }")
        lines.append("")

    # Add unassigned zones
    if unassigned:
        lines.append("  // Unassigned zones")
        for zone_id, zone in unassigned:
            node_attrs = _get_graphviz_node_attrs(
                zone, include_meta, include_discovery, actor_perspective
            )
            lines.append(f'  "{zone_id}" [{node_attrs}];')
        lines.append("")

    # Add edges
    lines.append("  // Exits")
    for zone_id, zone in zones.items():
        for exit in zone.exits:
            if exit.to in zones:  # Only include edges to zones in our set
                edge_attrs = _get_graphviz_edge_attrs(exit)
                lines.append(f'  "{zone_id}" -> "{exit.to}" [{edge_attrs}];')

    lines.append("}")
    return "\n".join(lines)


def _get_graphviz_node_attrs(
    zone: "Zone",
    include_meta: bool,
    include_discovery: bool,
    actor_perspective: Optional[str],
) -> str:
    """Generate Graphviz node attributes for a zone."""
    label_parts = [zone.name]

    if zone.tags:
        tag_str = ", ".join(sorted(zone.tags))
        label_parts.append(f"Tags: {tag_str}")

    if include_discovery and actor_perspective:
        discovery_status = zone.get_discovery_status(actor_perspective)
        label_parts.append(f"Discovery: {discovery_status}")

    label = "\\n".join(label_parts)

    # Choose node color based on region or tags
    color = "lightblue"
    if zone.region:
        region_colors = {
            "forest": "lightgreen",
            "mountain": "lightgray",
            "town": "lightyellow",
            "dungeon": "lightcoral",
            "underground": "lightsteelblue",
        }
        color = region_colors.get(zone.region.lower(), "lightblue")

    attrs = [f'label="{label}"', f'fillcolor="{color}"', "style=filled"]

    return ", ".join(attrs)


def _get_graphviz_edge_attrs(exit: "Exit") -> str:
    """Generate Graphviz edge attributes for an exit."""
    attrs = []

    # Label with direction and cost
    label_parts = []
    if exit.direction:
        label_parts.append(exit.direction)
    if exit.cost != 1.0:
        label_parts.append(f"cost: {exit.cost}")
    if exit.terrain:
        label_parts.append(f"terrain: {exit.terrain}")

    if label_parts:
        attrs.append(f'label="{", ".join(label_parts)}"')

    # Style based on properties
    if exit.blocked:
        attrs.extend(["color=red", "style=dashed"])
    elif exit.terrain:
        terrain_colors = {
            "mud": "brown",
            "water": "blue",
            "fire": "red",
            "ice": "cyan",
            "stairs": "gray",
        }
        color = terrain_colors.get(exit.terrain, "black")
        attrs.append(f"color={color}")

    return ", ".join(attrs) if attrs else ""


def _export_mermaid(
    world: "GameState",
    include_meta: bool = True,
    include_discovery: bool = False,
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> str:
    """Export zone graph as Mermaid diagram format."""
    zones = _filter_zones(world, actor_perspective, regions_only)

    lines = ["graph TD"]

    # Add nodes with styling
    for zone_id, zone in zones.items():
        # Create safe node ID for Mermaid
        safe_id = zone_id.replace(".", "_").replace("-", "_")
        node_label = zone.name

        if zone.tags:
            node_label += f"<br/>Tags: {', '.join(sorted(zone.tags))}"

        # Choose node shape and style based on properties
        if zone.region:
            lines.append(f"  {safe_id}[{node_label}]")
            # Add region styling
            region_class = zone.region.replace(" ", "_").lower()
            lines.append(f"  class {safe_id} {region_class}")
        else:
            lines.append(f"  {safe_id}({node_label})")

    lines.append("")

    # Add edges
    for zone_id, zone in zones.items():
        safe_from_id = zone_id.replace(".", "_").replace("-", "_")

        for exit in zone.exits:
            if exit.to in zones:
                safe_to_id = exit.to.replace(".", "_").replace("-", "_")

                # Create edge label
                edge_label = ""
                if exit.direction:
                    edge_label = exit.direction
                if exit.cost != 1.0:
                    edge_label += f" (${exit.cost})"

                # Choose arrow style
                arrow = "-->"
                if exit.blocked:
                    arrow = "-.->|blocked|"
                elif edge_label:
                    arrow = f"-->|{edge_label}|"

                lines.append(f"  {safe_from_id} {arrow} {safe_to_id}")

    lines.append("")

    # Add region styling
    region_styles = [
        "classDef forest fill:#e1f5fe",
        "classDef mountain fill:#f3e5f5",
        "classDef town fill:#fff3e0",
        "classDef dungeon fill:#ffebee",
        "classDef underground fill:#e8f5e8",
    ]
    lines.extend(region_styles)

    return "\n".join(lines)


def _export_cytoscape(
    world: "GameState",
    include_meta: bool = True,
    include_discovery: bool = False,
    actor_perspective: Optional[str] = None,
    regions_only: Optional[List[str]] = None,
) -> str:
    """Export zone graph as Cytoscape.js JSON format."""
    import json

    zones = _filter_zones(world, actor_perspective, regions_only)

    elements = {"nodes": [], "edges": []}

    # Add nodes
    for zone_id, zone in zones.items():
        node_data = {
            "id": zone_id,
            "name": zone.name,
            "region": zone.region,
            "tags": list(zone.tags),
        }

        if include_discovery and actor_perspective:
            node_data["discovered"] = zone.is_discovered_by(actor_perspective)

        elements["nodes"].append({"data": node_data})

    # Add edges
    for zone_id, zone in zones.items():
        for exit in zone.exits:
            if exit.to in zones:
                edge_data = {
                    "id": f"{zone_id}_{exit.to}",
                    "source": zone_id,
                    "target": exit.to,
                    "direction": exit.direction,
                    "cost": exit.cost,
                    "terrain": exit.terrain,
                    "blocked": exit.blocked,
                }

                elements["edges"].append({"data": edge_data})

    return json.dumps(elements, indent=2)


def analyze_zone_graph_structure(world: "GameState") -> Dict[str, Any]:
    """
    Perform comprehensive structural analysis of the zone graph.

    Args:
        world: Game state containing zones

    Returns:
        Dictionary with detailed structural analysis
    """
    analysis = {
        "basic_stats": {},
        "connectivity": {},
        "regions": {},
        "discovery": {},
        "pathfinding": {},
        "issues": [],
    }

    zones = world.zones
    total_zones = len(zones)

    if total_zones == 0:
        analysis["basic_stats"] = {"total_zones": 0, "empty_graph": True}
        return analysis

    # Basic statistics
    total_exits = sum(len(zone.exits) for zone in zones.values())
    analysis["basic_stats"] = {
        "total_zones": total_zones,
        "total_exits": total_exits,
        "average_exits_per_zone": total_exits / total_zones,
        "max_exits_per_zone": max(len(zone.exits) for zone in zones.values()),
        "min_exits_per_zone": min(len(zone.exits) for zone in zones.values()),
    }

    # Connectivity analysis
    connectivity_analysis = validate_bidirectional_consistency(world)
    analysis["connectivity"] = {
        "bidirectional_pairs": connectivity_analysis["total_bidirectional_pairs"],
        "consistent_pairs": connectivity_analysis["consistent_pairs"],
        "inconsistent_pairs": len(connectivity_analysis["inconsistent_pairs"]),
        "connectivity_ratio": connectivity_analysis["consistent_pairs"]
        / max(1, connectivity_analysis["total_bidirectional_pairs"]),
    }

    # Check for isolated zones
    reachable_zones = get_reachable_zones(
        "start" if "start" in zones else list(zones.keys())[0], world
    )
    isolated_zones = [zone_id for zone_id in zones if zone_id not in reachable_zones]

    analysis["connectivity"]["isolated_zones"] = isolated_zones
    analysis["connectivity"]["reachability_ratio"] = len(reachable_zones) / total_zones

    # Regional analysis
    region_summary = get_region_summary(world)
    analysis["regions"] = {
        "total_regions": len([r for r in region_summary.keys() if r != "Unassigned"]),
        "unassigned_zones": region_summary.get("Unassigned", {}).get("zone_count", 0),
        "average_zones_per_region": 0,
        "region_connectivity": {},
    }

    if analysis["regions"]["total_regions"] > 0:
        assigned_zones = total_zones - analysis["regions"]["unassigned_zones"]
        analysis["regions"]["average_zones_per_region"] = (
            assigned_zones / analysis["regions"]["total_regions"]
        )

        # Calculate region connectivity scores
        for region in region_summary:
            if region != "Unassigned":
                score = get_region_connectivity_score(region, world)
                analysis["regions"]["region_connectivity"][region] = score

    # Discovery analysis
    all_discovered_by = set()
    for zone in zones.values():
        all_discovered_by.update(zone.discovered_by)

    discovery_stats = {}
    for actor_id in all_discovered_by:
        discovered_count = sum(
            1 for zone in zones.values() if zone.is_discovered_by(actor_id)
        )
        discovery_stats[actor_id] = {
            "discovered_zones": discovered_count,
            "discovery_ratio": discovered_count / total_zones,
        }

    analysis["discovery"] = {
        "actors_with_discoveries": len(all_discovered_by),
        "per_actor_stats": discovery_stats,
    }

    # Pathfinding analysis
    # Test shortest path lengths between random zone pairs
    zone_ids = list(zones.keys())
    if len(zone_ids) >= 2:
        sample_paths = []
        for i in range(min(10, len(zone_ids))):  # Sample up to 10 paths
            start = zone_ids[i]
            end = zone_ids[(i + len(zone_ids) // 2) % len(zone_ids)]

            path = find_shortest_path(start, end, world)
            if path:
                sample_paths.append(len(path) - 1)  # Path length (edges)

        if sample_paths:
            analysis["pathfinding"] = {
                "average_path_length": sum(sample_paths) / len(sample_paths),
                "max_sampled_path_length": max(sample_paths),
                "min_sampled_path_length": min(sample_paths),
            }
        else:
            analysis["pathfinding"] = {"disconnected_graph": True}

    # Identify potential issues
    issues = []

    # Dead ends (zones with no exits)
    dead_ends = [zone_id for zone_id, zone in zones.items() if len(zone.exits) == 0]
    if dead_ends:
        issues.append(
            {
                "type": "dead_ends",
                "description": f"Found {len(dead_ends)} zones with no exits",
                "zones": dead_ends,
            }
        )

    # Highly connected nodes (potential bottlenecks)
    high_degree_threshold = total_exits / total_zones * 3  # 3x average
    bottlenecks = [
        zone_id
        for zone_id, zone in zones.items()
        if len(zone.exits) > high_degree_threshold
    ]
    if bottlenecks:
        issues.append(
            {
                "type": "potential_bottlenecks",
                "description": f"Found {len(bottlenecks)} highly connected zones",
                "zones": bottlenecks,
            }
        )

    # Broken exits (pointing to non-existent zones)
    broken_exits = []
    for zone_id, zone in zones.items():
        for exit in zone.exits:
            if exit.to not in zones:
                broken_exits.append({"from": zone_id, "to": exit.to})

    if broken_exits:
        issues.append(
            {
                "type": "broken_exits",
                "description": f"Found {len(broken_exits)} exits pointing to non-existent zones",
                "exits": broken_exits,
            }
        )

    analysis["issues"] = issues

    return analysis


def generate_zone_graph_report(world: "GameState") -> str:
    """
    Generate a comprehensive human-readable report about the zone graph.

    Args:
        world: Game state containing zones

    Returns:
        Formatted text report
    """
    analysis = analyze_zone_graph_structure(world)

    lines = ["ZONE GRAPH ANALYSIS REPORT", "=" * 40, ""]

    # Basic Statistics
    lines.append("BASIC STATISTICS:")
    basic = analysis["basic_stats"]
    if basic.get("empty_graph"):
        lines.append("  - Graph is empty (no zones)")
        return "\n".join(lines)

    lines.extend(
        [
            f"  - Total Zones: {basic['total_zones']}",
            f"  - Total Exits: {basic['total_exits']}",
            f"  - Average Exits per Zone: {basic['average_exits_per_zone']:.2f}",
            f"  - Max Exits per Zone: {basic['max_exits_per_zone']}",
            f"  - Min Exits per Zone: {basic['min_exits_per_zone']}",
            "",
        ]
    )

    # Connectivity
    lines.append("CONNECTIVITY:")
    conn = analysis["connectivity"]
    lines.extend(
        [
            f"  - Bidirectional Pairs: {conn['bidirectional_pairs']}",
            f"  - Consistent Pairs: {conn['consistent_pairs']}",
            f"  - Inconsistent Pairs: {conn['inconsistent_pairs']}",
            f"  - Consistency Ratio: {conn['connectivity_ratio']:.2%}",
            f"  - Reachability Ratio: {conn['reachability_ratio']:.2%}",
        ]
    )

    if conn.get("isolated_zones"):
        lines.append(f"  - Isolated Zones: {', '.join(conn['isolated_zones'])}")

    lines.append("")

    # Regions
    lines.append("REGIONAL ORGANIZATION:")
    regions = analysis["regions"]
    lines.extend(
        [
            f"  - Total Regions: {regions['total_regions']}",
            f"  - Unassigned Zones: {regions['unassigned_zones']}",
        ]
    )

    if regions["total_regions"] > 0:
        lines.append(
            f"  - Average Zones per Region: {regions['average_zones_per_region']:.1f}"
        )

        # Top connected regions
        region_scores = regions["region_connectivity"]
        if region_scores:
            top_regions = sorted(
                region_scores.items(), key=lambda x: x[1], reverse=True
            )[:3]
            lines.append("  - Most Connected Regions:")
            for region, score in top_regions:
                lines.append(f"    * {region}: {score:.2f}")

    lines.append("")

    # Discovery
    lines.append("DISCOVERY TRACKING:")
    discovery = analysis["discovery"]
    lines.append(f"  - Actors with Discoveries: {discovery['actors_with_discoveries']}")

    if discovery["per_actor_stats"]:
        lines.append("  - Discovery Progress:")
        for actor_id, stats in discovery["per_actor_stats"].items():
            lines.append(
                f"    * {actor_id}: {stats['discovered_zones']} zones ({stats['discovery_ratio']:.1%})"
            )

    lines.append("")

    # Issues
    lines.append("IDENTIFIED ISSUES:")
    issues = analysis["issues"]
    if not issues:
        lines.append("  - No issues found!")
    else:
        for issue in issues:
            lines.append(
                f"  - {issue['type'].replace('_', ' ').title()}: {issue['description']}"
            )

    lines.append("")

    # Pathfinding
    if "pathfinding" in analysis and not analysis["pathfinding"].get(
        "disconnected_graph"
    ):
        pathfinding = analysis["pathfinding"]
        lines.extend(
            [
                "PATHFINDING METRICS:",
                f"  - Average Path Length: {pathfinding['average_path_length']:.1f} hops",
                f"  - Path Length Range: {pathfinding['min_sampled_path_length']}-{pathfinding['max_sampled_path_length']} hops",
                "",
            ]
        )

    lines.append("End of Report")
    return "\n".join(lines)


# =============================================================================
# Enhanced Meta Layer Exit Redaction
# =============================================================================


def redact_exit(
    exit: "Exit", actor_id: str, world: "GameState", redaction_level: str = "partial"
) -> Optional["Exit"]:
    """
    Apply fine-grained redaction to an exit based on actor knowledge and discovery.

    Args:
        exit: The exit to potentially redact
        actor_id: ID of the actor requesting to see the exit
        world: Game state for context
        redaction_level: Level of redaction ("none", "partial", "full", "smart")

    Returns:
        Redacted exit or None if fully hidden
    """
    if redaction_level == "none":
        return exit

    if redaction_level == "full":
        return None

    # Get actor's knowledge and discovery status
    actor_knowledge = _get_actor_knowledge(actor_id, world)
    source_zone = _get_zone_containing_exit(exit, world)
    target_zone = world.zones.get(exit.to)

    # Smart redaction based on discovery and knowledge
    if redaction_level == "smart":
        return _apply_smart_redaction(
            exit, actor_id, actor_knowledge, source_zone, target_zone, world
        )

    # Partial redaction
    elif redaction_level == "partial":
        return _apply_partial_redaction(
            exit, actor_id, actor_knowledge, source_zone, target_zone, world
        )

    else:
        raise ValueError(f"Unknown redaction level: {redaction_level}")


def _get_actor_knowledge(actor_id: str, world: "GameState") -> Dict[str, Any]:
    """Get actor's knowledge and discovery state."""
    knowledge = {
        "discovered_zones": set(),
        "known_exits": set(),
        "has_mapping_skill": False,
        "has_detection_skill": False,
        "knowledge_level": "basic",
    }

    # Collect discovered zones
    for zone_id, zone in world.zones.items():
        if zone.is_discovered_by(actor_id):
            knowledge["discovered_zones"].add(zone_id)

    # Check for special knowledge skills (from actor entity if exists)
    actor_entity = world.entities.get(actor_id)
    if actor_entity:
        # Check tags for special skills
        if hasattr(actor_entity, "tags") and actor_entity.tags:
            tags = actor_entity.tags
            if "mapping" in tags or "cartographer" in tags:
                knowledge["has_mapping_skill"] = True
            if "detection" in tags or "scout" in tags:
                knowledge["has_detection_skill"] = True

        # Determine knowledge level based on stats (if PC or NPC)
        if hasattr(actor_entity, "type") and hasattr(actor_entity, "stats"):
            entity_type = getattr(actor_entity, "type", None)
            if entity_type in ("pc", "npc"):
                # Type narrow to PC/NPC to access stats safely
                from .game_state import PC, NPC

                if isinstance(actor_entity, (PC, NPC)):
                    stats = actor_entity.stats
                    if stats.intelligence > 15:
                        knowledge["knowledge_level"] = "high"
                    elif stats.wisdom > 15:
                        knowledge["knowledge_level"] = "wise"

    return knowledge


def _get_zone_containing_exit(exit: "Exit", world: "GameState") -> Optional["Zone"]:
    """Find the zone that contains this exit."""
    for zone in world.zones.values():
        if exit in zone.exits:
            return zone
    return None


def _apply_smart_redaction(
    exit: "Exit",
    actor_id: str,
    actor_knowledge: Dict[str, Any],
    source_zone: Optional["Zone"],
    target_zone: Optional["Zone"],
    world: "GameState",
) -> Optional["Exit"]:
    """Apply intelligent redaction based on comprehensive context."""
    from copy import deepcopy

    # If target zone doesn't exist, hide completely
    if not target_zone:
        return None

    # Check if actor is currently in the source zone
    actor_entity = world.entities.get(actor_id)
    actor_in_source_zone = (
        actor_entity
        and hasattr(actor_entity, "current_zone")
        and source_zone
        and actor_entity.current_zone == source_zone.id
    )

    # If actor hasn't discovered the source zone AND is not currently there, hide the exit
    if (
        source_zone
        and source_zone.id not in actor_knowledge["discovered_zones"]
        and not actor_in_source_zone
    ):
        return None

    # Base visibility on target zone discovery
    target_discovered = target_zone.id in actor_knowledge["discovered_zones"]

    # Create redacted copy
    redacted_exit = deepcopy(exit)

    if target_discovered:
        # If target is discovered, show full details
        return redacted_exit

    # Target not discovered - apply smart partial redaction

    # Always hide specific terrain details if not discovered
    if not target_discovered:
        redacted_exit.terrain = None
        redacted_exit.cost = 1.0  # Default cost

    # Hide detailed conditions unless actor has detection skills or conditions are obvious
    if not actor_knowledge["has_detection_skill"] and redacted_exit.conditions:
        # Keep basic conditions but hide complex ones
        simplified_conditions = {}
        for key, value in redacted_exit.conditions.items():
            # Keep common, obvious conditions
            if key in ["requires_key", "requires", "needs", "blocked_by"]:
                simplified_conditions[key] = value  # Keep the condition
            elif key in ["requires_perception", "requires_skill"]:
                simplified_conditions[key] = "special ability"  # Vague requirement
        redacted_exit.conditions = (
            simplified_conditions if simplified_conditions else None
        )

    # Adjust label based on knowledge level
    if redacted_exit.label:
        if not target_discovered:
            if actor_knowledge["knowledge_level"] == "high":
                redacted_exit.label = (
                    f"To {redacted_exit.label.split(' ')[0]}..."  # Partial info
                )
            else:
                redacted_exit.label = "To unknown area"

    # Direction is usually observable
    # But hide precise direction if actor lacks mapping skills and area isn't discovered
    if not actor_knowledge["has_mapping_skill"] and not target_discovered:
        if redacted_exit.direction in [
            "northeast",
            "northwest",
            "southeast",
            "southwest",
        ]:
            # Simplify diagonal directions
            if "north" in redacted_exit.direction:
                redacted_exit.direction = "north"
            elif "south" in redacted_exit.direction:
                redacted_exit.direction = "south"
            else:
                redacted_exit.direction = "away"

    # Hide blocked status if it's a secret or actor can't detect it
    if redacted_exit.blocked and not actor_knowledge["has_detection_skill"]:
        if not target_discovered:
            redacted_exit.blocked = False  # Appear open until attempted

    return redacted_exit


def _apply_partial_redaction(
    exit: "Exit",
    actor_id: str,
    actor_knowledge: Dict[str, Any],
    source_zone: Optional["Zone"],
    target_zone: Optional["Zone"],
    world: "GameState",
) -> Optional["Exit"]:
    """Apply standard partial redaction."""
    from copy import deepcopy

    # Check if actor is currently in the source zone
    actor_entity = world.entities.get(actor_id)
    actor_in_source_zone = (
        actor_entity
        and hasattr(actor_entity, "current_zone")
        and source_zone
        and actor_entity.current_zone == source_zone.id
    )

    # If actor hasn't discovered the source zone AND is not currently there, hide the exit
    if (
        source_zone
        and source_zone.id not in actor_knowledge["discovered_zones"]
        and not actor_in_source_zone
    ):
        return None

    # Create redacted copy
    redacted_exit = deepcopy(exit)

    # If target zone exists and is discovered, show full details
    if target_zone and target_zone.id in actor_knowledge["discovered_zones"]:
        return redacted_exit

    # Apply partial redaction for undiscovered targets

    # Hide terrain and cost details
    redacted_exit.terrain = None
    redacted_exit.cost = 1.0

    # Simplify or hide detailed conditions - keep obvious ones
    if redacted_exit.conditions:
        simplified_conditions = {}
        for key, value in redacted_exit.conditions.items():
            # Keep obvious conditions that a player would notice
            if key in ["requires_key", "blocked_by", "locked", "needs"]:
                simplified_conditions[key] = value
            elif key in ["requires_perception", "requires_skill"]:
                simplified_conditions[key] = "special ability"  # Vague requirement
        redacted_exit.conditions = (
            simplified_conditions if simplified_conditions else None
        )

    # Generalize the label
    if redacted_exit.label:
        if (
            "secret" in redacted_exit.label.lower()
            or "hidden" in redacted_exit.label.lower()
        ):
            redacted_exit.label = None  # Hide secret passages completely
        else:
            redacted_exit.label = "To unexplored area"

    # Keep direction and basic properties
    return redacted_exit


def get_redacted_exits(
    zone: "Zone", actor_id: str, world: "GameState", redaction_level: str = "smart"
) -> List["Exit"]:
    """
    Get a list of exits from a zone with appropriate redaction applied.

    Args:
        zone: Zone to get exits from
        actor_id: ID of the actor requesting exits
        world: Game state for context
        redaction_level: Level of redaction to apply

    Returns:
        List of redacted exits (some may be filtered out entirely)
    """
    redacted_exits = []

    for exit in zone.exits:
        redacted_exit = redact_exit(exit, actor_id, world, redaction_level)
        if redacted_exit is not None:
            redacted_exits.append(redacted_exit)

    return redacted_exits


def analyze_exit_visibility(
    world: "GameState", actor_id: str, redaction_level: str = "smart"
) -> Dict[str, Any]:
    """
    Analyze exit visibility across the entire world for an actor.

    Args:
        world: Game state containing zones
        actor_id: ID of the actor to analyze visibility for
        redaction_level: Level of redaction to apply

    Returns:
        Dictionary with visibility analysis
    """
    analysis = {
        "actor_id": actor_id,
        "redaction_level": redaction_level,
        "total_exits": 0,
        "visible_exits": 0,
        "partially_redacted": 0,
        "fully_hidden": 0,
        "zone_visibility": {},
        "discovery_progress": {},
    }

    actor_knowledge = _get_actor_knowledge(actor_id, world)

    for zone_id, zone in world.zones.items():
        zone_analysis = {
            "zone_discovered": zone_id in actor_knowledge["discovered_zones"],
            "total_exits": len(zone.exits),
            "visible_exits": 0,
            "redacted_exits": 0,
            "hidden_exits": 0,
        }

        for exit in zone.exits:
            analysis["total_exits"] += 1

            original_exit = exit
            redacted_exit = redact_exit(exit, actor_id, world, redaction_level)

            if redacted_exit is None:
                # Fully hidden
                analysis["fully_hidden"] += 1
                zone_analysis["hidden_exits"] += 1
            elif _exit_is_modified(original_exit, redacted_exit):
                # Partially redacted
                analysis["partially_redacted"] += 1
                analysis["visible_exits"] += 1
                zone_analysis["visible_exits"] += 1
                zone_analysis["redacted_exits"] += 1
            else:
                # Fully visible
                analysis["visible_exits"] += 1
                zone_analysis["visible_exits"] += 1

        analysis["zone_visibility"][zone_id] = zone_analysis

    # Calculate discovery progress
    total_zones = len(world.zones)
    discovered_zones = len(actor_knowledge["discovered_zones"])

    analysis["discovery_progress"] = {
        "total_zones": total_zones,
        "discovered_zones": discovered_zones,
        "discovery_ratio": discovered_zones / total_zones if total_zones > 0 else 0,
        "visibility_ratio": (
            analysis["visible_exits"] / analysis["total_exits"]
            if analysis["total_exits"] > 0
            else 0
        ),
    }

    return analysis


def _exit_is_modified(original: "Exit", redacted: "Exit") -> bool:
    """Check if an exit has been modified during redaction."""
    if original is None and redacted is None:
        return False
    if original is None or redacted is None:
        return True

    # Compare key properties
    return (
        original.label != redacted.label
        or original.terrain != redacted.terrain
        or original.cost != redacted.cost
        or original.conditions != redacted.conditions
        or original.blocked != redacted.blocked
    )


def create_redacted_world_view(
    world: "GameState",
    actor_id: str,
    redaction_level: str = "smart",
    include_undiscovered_zones: bool = False,
) -> "GameState":
    """
    Create a redacted view of the world from an actor's perspective.

    Args:
        world: Original game state
        actor_id: ID of the actor to create view for
        redaction_level: Level of redaction to apply
        include_undiscovered_zones: Whether to include zones the actor hasn't discovered

    Returns:
        New GameState with redacted information
    """
    from copy import deepcopy

    # Create new world state
    redacted_world = GameState(
        zones={},
        entities=deepcopy(world.entities),  # Copy entities as-is
        scene=deepcopy(world.scene),  # Copy scene as-is
    )

    actor_knowledge = _get_actor_knowledge(actor_id, world)

    for zone_id, original_zone in world.zones.items():
        # Check if zone should be included
        zone_discovered = zone_id in actor_knowledge["discovered_zones"]

        if not zone_discovered and not include_undiscovered_zones:
            continue

        # Create redacted zone copy
        redacted_zone = deepcopy(original_zone)

        # Apply exit redaction
        redacted_exits = []
        for exit in original_zone.exits:
            redacted_exit = redact_exit(exit, actor_id, world, redaction_level)
            if redacted_exit is not None:
                redacted_exits.append(redacted_exit)

        redacted_zone.exits = redacted_exits

        # Apply zone-level redaction if not discovered
        if not zone_discovered:
            # Hide detailed zone information
            redacted_zone.description = "An unexplored area."
            redacted_zone.tags = set()  # Hide tags

            # Apply zone meta redaction
            if redacted_zone.meta:
                redacted_zone.meta.visibility = "hidden"

        redacted_world.zones[zone_id] = redacted_zone

    return redacted_world


def get_redaction_suggestions(world: "GameState", actor_id: str) -> Dict[str, Any]:
    """
    Suggest redaction strategies based on actor knowledge and world structure.

    Args:
        world: Game state to analyze
        actor_id: Actor to analyze redaction for

    Returns:
        Dictionary with redaction suggestions and recommendations
    """
    suggestions = {
        "recommended_level": "smart",
        "reasoning": [],
        "specific_suggestions": [],
        "knowledge_assessment": {},
        "discovery_recommendations": [],
    }

    actor_knowledge = _get_actor_knowledge(actor_id, world)

    # Assess actor's knowledge level
    suggestions["knowledge_assessment"] = {
        "discovery_ratio": len(actor_knowledge["discovered_zones"]) / len(world.zones),
        "has_special_skills": actor_knowledge["has_mapping_skill"]
        or actor_knowledge["has_detection_skill"],
        "knowledge_level": actor_knowledge["knowledge_level"],
    }

    discovery_ratio = suggestions["knowledge_assessment"]["discovery_ratio"]

    # Recommend redaction level based on discovery progress
    if discovery_ratio < 0.2:
        suggestions["recommended_level"] = "partial"
        suggestions["reasoning"].append(
            "Low discovery ratio suggests conservative redaction"
        )
    elif discovery_ratio > 0.7:
        suggestions["recommended_level"] = "none"
        suggestions["reasoning"].append("High discovery ratio allows minimal redaction")
    else:
        suggestions["recommended_level"] = "smart"
        suggestions["reasoning"].append(
            "Moderate discovery ratio benefits from smart redaction"
        )

    # Special skill considerations
    if actor_knowledge["has_mapping_skill"]:
        suggestions["reasoning"].append(
            "Mapping skills allow for more directional information"
        )
    if actor_knowledge["has_detection_skill"]:
        suggestions["reasoning"].append(
            "Detection skills reveal hidden obstacles and conditions"
        )

    # Analyze specific zones for redaction suggestions
    for zone_id, zone in world.zones.items():
        if zone_id not in actor_knowledge["discovered_zones"]:
            # Count exits pointing to this undiscovered zone
            incoming_exits = []
            for other_zone_id, other_zone in world.zones.items():
                if other_zone_id in actor_knowledge["discovered_zones"]:
                    for exit in other_zone.exits:
                        if exit.to == zone_id:
                            incoming_exits.append((other_zone_id, exit))

            if incoming_exits:
                suggestions["specific_suggestions"].append(
                    {
                        "type": "exit_redaction",
                        "target_zone": zone_id,
                        "incoming_exits": len(incoming_exits),
                        "suggestion": f"Redact {len(incoming_exits)} exits pointing to undiscovered zone {zone_id}",
                    }
                )

    # Discovery recommendations
    discovered_count = len(actor_knowledge["discovered_zones"])
    total_count = len(world.zones)

    if discovered_count < total_count * 0.5:
        suggestions["discovery_recommendations"].append(
            "Consider revealing adjacent zones to improve navigation context"
        )

    if actor_knowledge["knowledge_level"] == "high" and discovery_ratio < 0.8:
        suggestions["discovery_recommendations"].append(
            "High intelligence actor could benefit from more zone revelations"
        )

    return suggestions


def create_bidirectional_exit(
    zone_a_id: str,
    zone_b_id: str,
    world: "GameState",
    direction_a_to_b: Optional[str] = None,
    direction_b_to_a: Optional[str] = None,
    label_a_to_b: Optional[str] = None,
    label_b_to_a: Optional[str] = None,
    cost: float = 1.0,
    terrain: Optional[str] = None,
    blocked: bool = False,
    conditions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create a bidirectional exit between two zones.

    Args:
        zone_a_id: First zone ID
        zone_b_id: Second zone ID
        world: Game state containing zones
        direction_a_to_b: Direction from A to B
        direction_b_to_a: Direction from B to A (auto-calculated if None)
        label_a_to_b: Label for exit from A to B
        label_b_to_a: Label for exit from B to A (auto-calculated if None)
        cost: Movement cost for both directions
        terrain: Terrain type for both directions
        blocked: Blocked status for both directions
        conditions: Travel conditions for both directions

    Returns:
        Dictionary with creation results
    """
    results = {"success": False, "created_exits": [], "errors": []}

    # Validate zones exist
    if zone_a_id not in world.zones:
        results["errors"].append(
            {
                "type": "missing_source_zone",
                "from_zone": zone_a_id,
                "message": f"Zone {zone_a_id} does not exist",
            }
        )
        return results

    if zone_b_id not in world.zones:
        results["errors"].append(
            {
                "type": "missing_target_zone",
                "to_zone": zone_b_id,
                "message": f"Zone {zone_b_id} does not exist",
            }
        )
        return results

    # Auto-calculate reciprocal direction if not provided
    if direction_b_to_a is None and direction_a_to_b is not None:
        direction_b_to_a = _get_reciprocal_direction(direction_a_to_b)

    # Auto-calculate reciprocal label if not provided
    if label_b_to_a is None:
        label_b_to_a = _generate_reciprocal_label(label_a_to_b, direction_b_to_a)

    try:
        # Create exit from A to B
        zone_a = world.zones[zone_a_id]
        exit_a_to_b = zone_a.add_exit(
            to=zone_b_id,
            direction=direction_a_to_b,
            label=label_a_to_b,
            cost=cost,
            terrain=terrain,
            blocked=blocked,
            conditions=conditions.copy() if conditions else None,
        )

        results["created_exits"].append(
            {
                "from": zone_a_id,
                "to": zone_b_id,
                "direction": direction_a_to_b,
                "label": label_a_to_b,
            }
        )

        # Create exit from B to A
        zone_b = world.zones[zone_b_id]
        exit_b_to_a = zone_b.add_exit(
            to=zone_a_id,
            direction=direction_b_to_a,
            label=label_b_to_a,
            cost=cost,
            terrain=terrain,
            blocked=blocked,
            conditions=conditions.copy() if conditions else None,
        )

        results["created_exits"].append(
            {
                "from": zone_b_id,
                "to": zone_a_id,
                "direction": direction_b_to_a,
                "label": label_b_to_a,
            }
        )

        results["success"] = True

    except Exception as e:
        results["errors"].append(f"Failed to create bidirectional exit: {str(e)}")

    return results
