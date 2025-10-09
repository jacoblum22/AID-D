"""
Effect atoms system - modular, extensible game state changes.

Effect atoms are the only way the game engine modifies state.
Tools output effect atoms, and the engine applies them atomically.
"""

from typing import Dict, Any, List, Callable, Union, cast
from dataclasses import dataclass

from .game_state import GameState, PC, NPC, Entity


# Effect registry for extensibility
EFFECT_REGISTRY: Dict[str, Callable[[GameState, Dict[str, Any]], None]] = {}


def effect(tag: str):
    """Decorator to register effect handlers."""

    def wrap(fn: Callable[[GameState, Dict[str, Any]], None]):
        EFFECT_REGISTRY[tag] = fn
        return fn

    return wrap


@effect("hp")
def apply_hp(state: GameState, e: Dict[str, Any]) -> None:
    """Apply HP change to a living entity."""
    target_id = e["target"]
    delta = e["delta"]

    # Fail fast on unknown HP target
    if target_id not in state.entities:
        raise ValueError(f"HP effect target not found: {target_id}")

    entity: Entity = state.entities[target_id]

    # Type-safe check for living entities
    if entity.type not in ("pc", "npc"):
        raise ValueError(f"hp effect on non-creature: {entity.type}")

    # Type cast for static analysis
    living_entity: Union[PC, NPC] = cast(Union[PC, NPC], entity)

    # Calculate new HP with both lower and upper bounds clamped
    new_hp = max(0, min(living_entity.hp.max, living_entity.hp.current + delta))

    # Create new HP object and update entity
    from .game_state import HP

    new_hp_obj = HP(current=new_hp, max=living_entity.hp.max)
    updated_entity = living_entity.model_copy(update={"hp": new_hp_obj})
    state.entities[target_id] = updated_entity


@effect("position")
def apply_position(state: GameState, e: Dict[str, Any]) -> None:
    """Change an entity's position/zone."""
    target_id = e["target"]
    to_zone = e["to"]
    from_zone = e.get("from")

    if target_id in state.entities and to_zone in state.zones:
        entity: Entity = state.entities[target_id]
        old_zone = getattr(entity, "current_zone", None)

        # Update position using Pydantic's copy mechanism
        updated_entity = entity.model_copy(update={"current_zone": to_zone})
        state.entities[target_id] = updated_entity

        # Update visibility for all actors
        _update_visibility(state)

        # Trigger auto-reveal for exploration
        if entity.type in ("pc", "npc") and old_zone != to_zone:
            from .auto_reveal import trigger_exploration_events

            try:
                trigger_exploration_events(state, target_id, old_zone, to_zone)
            except Exception as ex:
                # Auto-reveal is optional - core movement should work even if it fails
                import sys

                print(
                    f"Warning: Auto-reveal failed during movement: {ex}",
                    file=sys.stderr,
                )


@effect("clock")
def apply_clock(state: GameState, e: Dict[str, Any]) -> None:
    """Update a clock value with enhanced tracking.

    Enhanced format supports:
    {"type":"clock","id":"npc.guard.persuade","delta":1,"max":3,"source":"pc.arin"}
    """
    clock_id = e["id"]
    delta = e["delta"]
    source = e.get("source", "unknown")
    max_value = e.get("max", 10)  # Default max for backwards compatibility

    # Initialize this clock if not present with enhanced structure
    if clock_id not in state.clocks:
        state.clocks[clock_id] = {
            "value": 0,
            "min": 0,
            "max": max_value,
            "source": source,
            "created_turn": state.scene.round,
            "last_modified_turn": state.scene.round,
            "last_modified_by": source,
        }

    clock = state.clocks[clock_id]

    # Handle Clock objects vs legacy dicts
    if not isinstance(clock, dict):
        # Convert Clock object to dict for legacy processing
        clock_dict = clock.model_dump()
        clock_dict["min"] = 0  # Set default min for legacy compatibility
        # Update the state with the dict version
        state.clocks[clock_id] = clock_dict
        clock = clock_dict

    # Migrate legacy clocks to enhanced structure if needed
    if "min" not in clock:
        clock["min"] = 0
    if "max" not in clock:
        clock["max"] = max_value
    if "source" not in clock:
        clock["source"] = source
    if "created_turn" not in clock:
        clock["created_turn"] = state.scene.round
    if "last_modified_turn" not in clock:
        clock["last_modified_turn"] = state.scene.round
    if "last_modified_by" not in clock:
        clock["last_modified_by"] = source

    # Capture current state before any modifications for filled detection
    old_value = clock["value"]
    old_max = clock["max"]

    # Update max if provided (allows for dynamic adjustment)
    if "max" in e:
        clock["max"] = max_value

    # Update tracking metadata
    clock["last_modified_turn"] = state.scene.round
    clock["last_modified_by"] = source

    # Apply delta
    clock["value"] += delta

    # Clamp to min/max
    clock["value"] = max(clock["min"], min(clock["max"], clock["value"]))

    # Track if clock reached max (filled the bar) this turn
    # Use old_max for consistent filled detection regardless of dynamic max changes
    was_filled_before = old_value >= old_max
    is_filled_now = clock["value"] >= clock["max"]

    if not was_filled_before and is_filled_now:
        # Clock was just filled this turn
        clock["filled_this_turn"] = True
        clock["filled_by"] = source
    elif was_filled_before and not is_filled_now:
        # Clock was reset/reduced from filled state
        clock.pop("filled_this_turn", None)
        clock.pop("filled_by", None)
    # If clock was already filled and stays filled, preserve existing filled_this_turn status


@effect("guard")
def apply_guard(state: GameState, e: Dict[str, Any]) -> None:
    """Apply guard/protection status to a living entity."""
    target_id = e["target"]
    guard_value = e["value"]
    duration = e.get("duration", 1)

    if target_id in state.entities:
        entity: Entity = state.entities[target_id]

        # Type-safe check for living entities
        if entity.type not in ("pc", "npc"):
            raise ValueError(f"guard effect on non-creature: {entity.type}")

        # Type cast for static analysis
        living_entity: Union[PC, NPC] = cast(Union[PC, NPC], entity)

        # Update using Pydantic's copy mechanism
        updated_entity = living_entity.model_copy(
            update={"guard": guard_value, "guard_duration": duration}
        )
        state.entities[target_id] = updated_entity


@effect("mark")
def apply_mark(state: GameState, e: Dict[str, Any]) -> None:
    """Apply a mark/bonus to a living entity or remove marks.

    Supports both legacy format (style_bonus) and new flexible format (tag-based).
    New format: {"type":"mark","target":"npc.guard","tag":"favor","source":"pc.arin"}
    """
    target_id = e["target"]

    if target_id in state.entities:
        entity: Entity = state.entities[target_id]

        # Type-safe check for living entities
        if entity.type not in ("pc", "npc"):
            raise ValueError(f"mark effect on non-creature: {entity.type}")

        # Type cast for static analysis
        living_entity: Union[PC, NPC] = cast(Union[PC, NPC], entity)

        # Check if this is a removal operation
        if e.get("remove", False):
            if e.get("tag"):
                # New format: Remove specific tag-based mark
                source = e.get("source")
                if not source:
                    raise ValueError(
                        "Tag-based mark removal requires 'source' to be specified"
                    )

                current_marks = getattr(living_entity, "marks", {}).copy()
                mark_key = f"{source}.{e['tag']}"
                current_marks.pop(mark_key, None)
                updated_entity = living_entity.model_copy(
                    update={"marks": current_marks}
                )
            else:
                # Legacy: Remove all marks by setting style_bonus to 0
                updated_entity = living_entity.model_copy(
                    update={"style_bonus": 0, "mark_consumes": True}
                )
        else:
            # Check for new flexible format vs legacy format
            if "tag" in e:
                # New flexible format
                tag = e["tag"]
                source = e.get("source", "unknown")
                mark_key = f"{source}.{tag}"

                # Get current marks (initialize if not present)
                current_marks = getattr(living_entity, "marks", {}).copy()

                # Add new mark with metadata
                current_marks[mark_key] = {
                    "tag": tag,
                    "source": source,
                    "value": e.get("value", 1),  # Default mark strength
                    "consumes": e.get("consumes", True),
                    "created_turn": state.scene.round,
                }

                updated_entity = living_entity.model_copy(
                    update={"marks": current_marks}
                )
            else:
                # Legacy format for backwards compatibility
                style_bonus = e["style_bonus"]
                consumes = e.get("consumes", True)

                updated_entity = living_entity.model_copy(
                    update={
                        "style_bonus": living_entity.style_bonus + style_bonus,
                        "mark_consumes": consumes,
                    }
                )

        state.entities[target_id] = updated_entity


def _update_visibility(state: GameState) -> None:
    """Update visibility between all actors based on current positions."""
    # Get all living entities (PC and NPC)
    living_entities = {
        k: v for k, v in state.entities.items() if v.type in ("pc", "npc")
    }

    # Update visibility for each living entity
    for entity_id, entity in living_entities.items():
        visible_actors = []

        # Find other entities in the same zone
        for other_id, other_entity in living_entities.items():
            if (
                entity_id != other_id
                and entity.current_zone == other_entity.current_zone
            ):
                visible_actors.append(other_id)

        # Update visibility using Pydantic's copy mechanism
        updated_entity = entity.model_copy(update={"visible_actors": visible_actors})
        state.entities[entity_id] = updated_entity


def apply_effects(state: GameState, effects: List[Dict[str, Any]]) -> GameState:
    """
    Apply a list of effect atoms to the game state.

    Args:
        state: Current game state
        effects: List of effect atom dictionaries

    Returns:
        Modified game state

    Raises:
        ValueError: If an unknown effect type is encountered or type mismatch
    """
    for effect_atom in effects:
        effect_type = effect_atom.get("type")
        if not effect_type:
            raise ValueError(f"Effect missing 'type' field: {effect_atom}")

        handler = EFFECT_REGISTRY.get(effect_type)
        if not handler:
            raise ValueError(f"Unknown effect type: {effect_type}")

        handler(state, effect_atom)

    return state


@effect("tag")
def apply_tag(state: GameState, e: Dict[str, Any]) -> None:
    """Apply tag changes to scene or entities."""
    target_id = e["target"]

    if target_id == "scene":
        # Modify scene tags
        if "add" in e:
            if isinstance(e["add"], dict):
                # Add multiple tags
                for key, value in e["add"].items():
                    state.scene.tags[key] = str(value)
            else:
                raise ValueError("tag effect 'add' must be a dict")

        if "remove" in e:
            if isinstance(e["remove"], list):
                # Remove multiple tags
                for key in e["remove"]:
                    state.scene.tags.pop(key, None)
            elif isinstance(e["remove"], str):
                # Remove single tag
                state.scene.tags.pop(e["remove"], None)
            else:
                raise ValueError("tag effect 'remove' must be a string or list")

    else:
        # Modify entity tags
        if target_id not in state.entities:
            raise ValueError(f"Tag effect target not found: {target_id}")

        entity = state.entities[target_id]

        # Get current tags (will be empty dict by default from BaseEntity)
        current_tags = entity.tags.copy()

        if "add" in e:
            if isinstance(e["add"], dict):
                for key, value in e["add"].items():
                    current_tags[key] = value
            else:
                raise ValueError("tag effect 'add' must be a dict")

        if "remove" in e:
            if isinstance(e["remove"], list):
                for key in e["remove"]:
                    current_tags.pop(key, None)
            elif isinstance(e["remove"], str):
                current_tags.pop(e["remove"], None)
            else:
                raise ValueError("tag effect 'remove' must be a string or list")

        # Update entity using Pydantic's copy mechanism
        updated_entity = entity.model_copy(update={"tags": current_tags})
        state.entities[target_id] = updated_entity


@effect("noise")
def apply_noise(state: GameState, e: Dict[str, Any]) -> None:
    """Apply noise effect for subsystem integration.

    This is a passive effect that doesn't modify game state directly,
    but allows other subsystems to subscribe to noise events.
    """
    # For now, this is a no-op effect that just validates structure
    required_fields = ["zone", "intensity", "source"]
    for field in required_fields:
        if field not in e:
            raise ValueError(f"noise effect missing required field: {field}")

    # Validate intensity values
    valid_intensities = ["quiet", "normal", "loud", "very_loud"]
    if e["intensity"] not in valid_intensities:
        raise ValueError(f"noise effect intensity must be one of: {valid_intensities}")

    # In the future, this could:
    # - Update zone noise levels
    # - Trigger NPC awareness systems
    # - Log events for replay systems
    # - Advance detection clocks


@effect("inventory")
def apply_inventory(state: GameState, e: Dict[str, Any]) -> None:
    """Apply inventory changes to an entity."""
    target_id = e["target"]
    item_id = e.get("item")
    delta = e.get("delta", 0)

    if target_id not in state.entities:
        raise ValueError(f"Inventory effect target not found: {target_id}")

    entity = state.entities[target_id]

    # Type-safe check for entities with inventory
    if entity.type not in ("pc", "npc"):
        raise ValueError(f"inventory effect on non-creature: {entity.type}")

    # Type cast for static analysis
    creature = cast(Union[PC, NPC], entity)

    if not hasattr(creature, "inventory"):
        raise ValueError(f"Entity {target_id} does not have inventory")

    current_inventory = creature.inventory.copy()

    if item_id:
        if delta > 0:
            # Add items
            for _ in range(delta):
                current_inventory.append(item_id)
        elif delta < 0:
            # Remove items
            items_to_remove = abs(delta)
            for _ in range(items_to_remove):
                if item_id in current_inventory:
                    current_inventory.remove(item_id)
                else:
                    break

    # Update entity using Pydantic's copy mechanism
    updated_entity = creature.model_copy(update={"inventory": current_inventory})
    state.entities[target_id] = updated_entity


def get_registered_effects() -> List[str]:
    """Get list of all registered effect types."""
    return list(EFFECT_REGISTRY.keys())
