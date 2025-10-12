"""
Core data structures for the AI D&D game state and utterances.
"""

import re
import sys
import os
from typing import (
    Dict,
    List,
    Optional,
    Any,
    Union,
    Literal,
    Annotated,
    cast,
    Tuple,
    Callable,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator, PrivateAttr
from enum import Enum

# Add project root to path for models import - more robust approach
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from models.meta import Meta
from models.space import Zone as ZoneModel, Exit


class EffectLogEntry(BaseModel):
    """
    Structured log entry for applied effects with comprehensive audit trail.

    Used for replay, undo functionality, and debugging. Contains complete
    information about an effect application including before/after state,
    dice rolls, and execution details.
    """

    # Core effect information
    effect: Dict[str, Any]  # The applied effect (Effect.model_dump())
    before: Dict[str, Any] = Field(default_factory=dict)  # State before application
    after: Dict[str, Any] = Field(default_factory=dict)  # State after application

    # Execution results
    ok: bool = True  # Whether the effect succeeded
    error: Optional[str] = None  # Error message if failed

    # Context and replay information
    actor: Optional[str] = None  # Who caused this effect
    seed: Optional[int] = None  # For deterministic replay
    rolled: Optional[List[int]] = None  # Raw dice roll results
    dice_log: Optional[List[Dict[str, Any]]] = None  # Detailed dice information

    # Impact analysis
    impact_level: Optional[int] = None  # Magnitude of change (0-10+)
    resolved_delta: Optional[Union[int, float]] = (
        None  # Final delta value after dice resolution
    )

    # Timestamps and metadata
    timestamp: Optional[str] = None  # When the effect was applied
    round_applied: Optional[int] = None  # Game round when applied
    meta: Dict[str, Any] = Field(default_factory=dict)  # Additional metadata


class PendingEffect(BaseModel):
    """
    Timed or conditional effect waiting to be applied.

    Represents an effect scheduled for future execution. Forms part of a FIFO queue
    where effects are added via append() and processed in chronological order.

    Queue Operations:
    - Add: pending_effects.append(new_effect)
    - Process: Iterate through list, apply triggered effects, rebuild list without them
    - The list should maintain chronological order (earliest trigger_round first)
    """

    # The effect to apply when triggered
    effect: Dict[str, Any]  # Effect.model_dump() - the effect to apply

    # Timing information
    trigger_round: int  # Game round when this effect should activate
    scheduled_at: int  # Game round when this was scheduled

    # Context information
    actor: Optional[str] = None  # Who scheduled this effect
    seed: Optional[int] = None  # For deterministic replay

    # Unique identifier
    id: str  # Unique identifier for this pending effect

    # Optional metadata
    condition: Optional[str] = None  # Additional condition to check before applying
    source: Optional[str] = None  # What caused this effect to be scheduled
    meta: Dict[str, Any] = Field(default_factory=dict)  # Additional metadata


class Zone(ZoneModel):
    """
    Backwards-compatible Zone wrapper extending models/space.Zone.

    Provides legacy adjacent_zones and blocked_exits properties for compatibility
    while using the new Exit-based model internally.
    """

    def __init__(
        self,
        id: str,
        name: str,
        description: Optional[str] = None,
        adjacent_zones: Optional[List[str]] = None,
        blocked_exits: Optional[List[str]] = None,
        exits: Optional[List[Union[dict, Exit]]] = None,
        tags: Optional[Union[set, List[str]]] = None,
        meta: Optional[Meta] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize Zone with backward compatibility for legacy parameters.

        Args:
            id: Zone ID
            name: Zone name
            description: Zone description
            adjacent_zones: Legacy parameter - list of connected zone IDs
            blocked_exits: Legacy parameter - list of blocked zone IDs
            exits: New parameter - list of Exit objects or dicts
            tags: Set of zone tags
            meta: Zone metadata
            **kwargs: Additional parameters
        """
        # Handle legacy format conversion
        if adjacent_zones is not None and exits is None:
            exits = []
            blocked_set = set(blocked_exits or [])

            # Create exits for all adjacent zones
            for zone_id in adjacent_zones:
                exits.append({"to": zone_id, "blocked": zone_id in blocked_set})

            # Add any blocked-only exits (shouldn't normally happen but be safe)
            for zone_id in blocked_set:
                if zone_id not in adjacent_zones:
                    exits.append({"to": zone_id, "blocked": True})

        # Convert tags to set if it's a list
        if isinstance(tags, list):
            tag_set = set(tags)
        else:
            tag_set = tags or set()

        # Convert exit dicts to Exit objects if needed
        if exits:
            exit_objects = []
            for exit in exits:
                if isinstance(exit, dict):
                    exit_objects.append(Exit(**exit))
                else:
                    exit_objects.append(exit)
        else:
            exit_objects = []

        # Initialize with converted or provided exits
        super().__init__(
            id=id,
            name=name,
            description=description,
            exits=exit_objects,
            tags=tag_set,  # tag_set will be converted to set by validator if needed
            meta=meta or Meta(),
            **kwargs,
        )

    @property
    def adjacent_zones(self) -> List[str]:
        """
        Legacy compatibility property derived from exits.

        Returns:
            List of zone IDs that have unblocked exits
        """
        return [exit.to for exit in self.exits if not exit.blocked]

    @property
    def blocked_exits(self) -> List[str]:
        """
        Legacy compatibility property derived from exits.

        Returns:
            List of zone IDs that have blocked exits
        """
        return [exit.to for exit in self.exits if exit.blocked]

    def model_dump_json_safe(self, mode="save", **kwargs):
        """
        Ensure Zone has model_dump_json_safe method available.

        This method should be inherited from ZoneModel, but we're adding it
        explicitly to handle any inheritance issues.
        """
        # Call the parent class method
        return super().model_dump_json_safe(mode=mode, **kwargs)


class Clock(BaseModel):
    """Represents a game clock/progress tracker."""

    id: str
    name: str
    value: int = 0
    maximum: int = 4
    minimum: int = 0
    source: Optional[str] = None
    created_turn: Optional[int] = None
    last_modified_turn: Optional[int] = None
    last_modified_by: Optional[str] = None
    filled_this_turn: bool = False
    meta: Meta = Field(default_factory=Meta)


class HP(BaseModel):
    """Health points for living entities."""

    current: int
    max: int


class Stats(BaseModel):
    """D&D ability scores."""

    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10


class BaseEntity(BaseModel):
    """Base class for all game entities."""

    model_config = ConfigDict(extra="forbid")  # Strict validation

    id: str
    name: str
    current_zone: str
    tags: Dict[str, Any] = Field(default_factory=dict)  # Support for arbitrary tags
    meta: Meta = Field(default_factory=Meta)

    def model_dump_json_safe(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"] = "full",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Export Entity data with JSON-safe serialization (handles Meta sets).

        Args:
            mode: Export mode for Meta fields (full, save, public, etc.)
            **kwargs: Additional arguments passed to model_dump

        Returns:
            Dictionary with meta.known_by as list instead of set
        """
        data = self.model_dump(**kwargs)
        # Use meta's export method for JSON-safe serialization
        if "meta" in data:
            data["meta"] = self.meta.export(mode=mode)
        return data


class PC(BaseEntity):
    """Player character entity."""

    type: Literal["pc"] = Field(default="pc")
    stats: Stats = Field(default_factory=Stats)
    hp: HP = Field(default_factory=lambda: HP(current=20, max=20))
    visible_actors: List[str] = Field(default_factory=list)
    has_weapon: bool = True
    has_talked_this_turn: bool = False
    inventory: List[str] = Field(default_factory=list)
    conditions: Dict[str, bool] = Field(default_factory=dict)

    # Combat and effect fields
    guard: int = 0
    guard_duration: int = 0
    style_bonus: int = 0
    mark_consumes: bool = True
    marks: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # New flexible marks system


class NPC(BaseEntity):
    """Non-player character entity."""

    type: Literal["npc"] = Field(default="npc")
    stats: Stats = Field(default_factory=Stats)
    hp: HP = Field(default_factory=lambda: HP(current=20, max=20))
    visible_actors: List[str] = Field(default_factory=list)
    has_weapon: bool = True
    has_talked_this_turn: bool = False
    inventory: List[str] = Field(default_factory=list)
    conditions: Dict[str, bool] = Field(default_factory=dict)

    # Combat and effect fields
    guard: int = 0
    guard_duration: int = 0
    style_bonus: int = 0
    mark_consumes: bool = True
    marks: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # New flexible marks system


class ObjectEntity(BaseEntity):
    """Environmental objects like doors, chests, etc."""

    type: Literal["object"]
    description: str = ""
    interactable: bool = True
    locked: bool = False


class ItemEntity(BaseEntity):
    """Items that can be picked up."""

    type: Literal["item"]
    description: str = ""
    weight: float = 1.0
    value: int = 0


# Discriminated union for all entity types
Entity = Annotated[
    Union[PC, NPC, ObjectEntity, ItemEntity], Field(discriminator="type")
]


class Scene(BaseModel):
    """Scene tracking for turn order and environmental conditions."""

    id: str = "default_scene"
    turn_order: List[str] = Field(default_factory=list)
    turn_index: int = 0
    round: int = 1
    base_dc: int = 12
    tags: Dict[str, str] = Field(
        default_factory=lambda: {
            "alert": "normal",  # sleepy | normal | wary | alarmed
            "lighting": "normal",  # dim | normal | bright
            "noise": "normal",  # quiet | normal | loud
            "cover": "some",  # none | some | good
        }
    )
    objective: Dict[str, Any] = Field(default_factory=dict)
    pending_choice: Optional[Dict[str, Any]] = None  # For ask_clarifying tool
    choice_count_this_turn: int = 0  # Max 3 clarifications per turn
    last_effect_log: List[EffectLogEntry] = Field(
        default_factory=list,
        description="Structured log of recently applied effects for replay/undo functionality. "
        "Contains complete audit trail with before/after state, dice rolls, and execution details.",
    )
    last_diff_summary: Optional[str] = (
        None  # Human-readable audit trail of last changes
    )
    pending_effects: List[PendingEffect] = Field(
        default_factory=list,
        description="FIFO queue of timed/conditional effects awaiting execution. "
        "Effects are appended to the end and processed in chronological order. "
        "Use .append() to add new effects and rebuild the list to remove triggered ones. "
        "Maintains chronological ordering by trigger_round.",
    )
    meta: Meta = Field(default_factory=Meta)

    def add_pending_effect(self, pending_effect: PendingEffect) -> None:
        """
        Add a pending effect to the FIFO queue.

        Effects are appended to the end to maintain chronological order.
        The queue should be processed by trigger_round to ensure proper timing.
        """
        self.pending_effects.append(pending_effect)

    def process_pending_effects(self, current_round: int) -> List[PendingEffect]:
        """
        Remove and return all pending effects that should trigger this round.

        This maintains FIFO semantics by processing effects in the order they were added,
        but only returns those whose trigger_round <= current_round.

        Args:
            current_round: The current game round

        Returns:
            List of effects to process (trigger_round <= current_round)
        """
        triggered = []
        remaining = []

        for effect in self.pending_effects:
            if effect.trigger_round <= current_round:
                triggered.append(effect)
            else:
                remaining.append(effect)

        self.pending_effects = remaining
        return triggered

    def add_effect_log(self, log_entry: EffectLogEntry) -> None:
        """
        Add an effect log entry to the audit trail.

        Maintains a record of all applied effects for replay/undo functionality.
        """
        self.last_effect_log.append(log_entry)


class GameState(BaseModel):
    """Core game state representation."""

    entities: Dict[str, Entity]  # Changed from actors to entities
    zones: Dict[str, Zone]
    scene: Scene = Field(default_factory=Scene)
    pending_action: Optional[str] = None
    current_actor: Optional[str] = None
    turn_flags: Dict[str, Any] = Field(default_factory=dict)
    clocks: Dict[str, Union[Clock, Dict[str, Any]]] = Field(
        default_factory=dict
    )  # Support both Clock objects and legacy dict format

    # Redaction caching for performance optimization
    _redaction_cache: Dict[Tuple[Optional[str], str], Dict[str, Any]] = PrivateAttr(
        default_factory=dict
    )

    # Event system for zone graph and other dynamic changes
    _event_listeners: Dict[str, List[Callable]] = PrivateAttr(default_factory=dict)

    # Backward compatibility property
    @property
    def actors(self) -> Dict[str, Union[PC, NPC]]:
        """Get only PC and NPC entities for backward compatibility."""
        filtered = {k: v for k, v in self.entities.items() if v.type in ("pc", "npc")}
        return cast(Dict[str, Union[PC, NPC]], filtered)

    def get_state(
        self,
        pov_id: Optional[str] = None,
        slice: Optional[Dict[str, Any]] = None,
        redact: bool = True,
        use_cache: bool = True,
        role: Literal["player", "narrator", "gm"] = "player",
    ) -> Dict[str, Any]:
        """
        Get the current game state, optionally redacted for a specific point of view.

        Args:
            pov_id: The point-of-view actor ID, or None for GM view
            slice: Optional slice specification for partial state
            redact: Whether to apply redaction based on visibility rules
            use_cache: Whether to use redaction cache for performance
            role: The redaction role determining information access level

        Returns:
            Dictionary representing the game state
        """
        # Import here to avoid circular imports
        from .visibility import redact_entity, redact_zone, redact_clock

        state = {
            "scene": self.scene.model_dump() if not redact else self.scene.model_dump(),
            "zones": {},
            "entities": {},
            "clocks": {},
        }

        # Handle zones
        for zid, zone in self.zones.items():
            if redact:
                state["zones"][zid] = redact_zone(pov_id, zone, self, role)
            else:
                zone_data = zone.model_dump()
                zone_data["is_visible"] = True
                state["zones"][zid] = zone_data

        # Handle entities
        for eid, entity in self.entities.items():
            if redact:
                if use_cache and role == "player":  # Only cache player view for now
                    state["entities"][eid] = self.get_cached_view(pov_id, eid)
                else:
                    state["entities"][eid] = redact_entity(pov_id, entity, self, role)
            else:
                entity_data = entity.model_dump()
                entity_data["is_visible"] = True
                state["entities"][eid] = entity_data

        # Handle clocks
        for cid, clock in self.clocks.items():
            if redact:
                if isinstance(clock, Clock):
                    state["clocks"][cid] = redact_clock(pov_id, clock)
                else:
                    # Legacy dict format - use old redaction logic
                    state["clocks"][cid] = self._redact_legacy_clock(pov_id, cid, clock)
            else:
                if isinstance(clock, Clock):
                    clock_data = clock.model_dump()
                    clock_data["is_visible"] = True
                    state["clocks"][cid] = clock_data
                else:
                    clock_data = clock.copy()
                    clock_data["is_visible"] = True
                    state["clocks"][cid] = clock_data

        # Apply slice filtering if provided
        if slice:
            # Simple slice implementation - can be enhanced later
            if "entities" in slice and isinstance(slice["entities"], list):
                state["entities"] = {
                    k: v for k, v in state["entities"].items() if k in slice["entities"]
                }

        return state

    def list_visible_entities(self, pov_id: str, zone_only: bool = True) -> List[str]:
        """
        List entity IDs visible to the specified point of view.

        Args:
            pov_id: The point-of-view actor ID
            zone_only: If True, only return entities in the same zone as the POV actor

        Returns:
            List of visible entity IDs
        """
        # Import here to avoid circular imports
        from .visibility import can_player_see

        pov = self.entities.get(pov_id)
        if not pov:
            return []

        visible = []
        for eid, entity in self.entities.items():
            if zone_only and getattr(entity, "current_zone", None) != getattr(
                pov, "current_zone", None
            ):
                continue
            if can_player_see(pov_id, entity, self):
                visible.append(eid)

        return visible

    def get_cached_view(self, pov_id: Optional[str], eid: str) -> Dict[str, Any]:
        """
        Get a cached redacted view of an entity, computing it if not cached.

        Args:
            pov_id: The point-of-view actor ID, or None for GM view
            eid: The entity ID to get a redacted view for

        Returns:
            Cached redacted view of the entity
        """
        key = (pov_id, eid)
        if key not in self._redaction_cache:
            # Import here to avoid circular imports
            from .visibility import redact_entity

            entity = self.entities.get(eid)
            if entity:
                self._redaction_cache[key] = redact_entity(pov_id, entity, self)
            else:
                # Return a "not found" redacted view
                self._redaction_cache[key] = {
                    "id": eid,
                    "type": "unknown",
                    "is_visible": False,
                    "name": "Not Found",
                }

        return self._redaction_cache[key]

    def invalidate_cache(self, eid: Optional[str] = None) -> None:
        """
        Invalidate redaction cache entries.

        Args:
            eid: If provided, only invalidate cache for this entity.
                 If None, clear the entire cache.
        """
        if eid:
            # Remove all cache entries for this entity
            self._redaction_cache = {
                k: v for k, v in self._redaction_cache.items() if k[1] != eid
            }
        else:
            # Clear entire cache
            self._redaction_cache.clear()

        # Publish cache invalidation event using deferred import
        try:
            import importlib

            # Try import paths in order of preference (tests use router.events via path modification)
            events_module = None
            for module_path in ["router.events", "backend.router.events"]:
                try:
                    events_module = importlib.import_module(module_path)
                    break
                except ImportError:
                    continue

            if (
                events_module
                and hasattr(events_module, "publish")
                and hasattr(events_module, "EventTypes")
            ):
                events_module.publish(
                    events_module.EventTypes.CACHE_INVALIDATED,
                    {
                        "entity_id": eid,
                        "cache_size_before": len(self._redaction_cache),
                        "full_clear": eid is None,
                    },
                )

        except (ImportError, AttributeError, Exception):
            # Event system not available or failed, continue silently
            pass

    def validate_invariants(self) -> List[str]:
        """
        Validate game state invariants and return list of errors.

        Returns:
            List of error messages for any invariant violations
        """
        errors = []

        # Check Meta field consistency across all objects
        for eid, entity in self.entities.items():
            try:
                # This will trigger the model_validator
                entity.meta.model_validate(entity.meta.model_dump())
            except ValueError as e:
                errors.append(f"Entity {eid}: {str(e)}")

        for zid, zone in self.zones.items():
            try:
                zone.meta.model_validate(zone.meta.model_dump())
            except ValueError as e:
                errors.append(f"Zone {zid}: {str(e)}")

        for cid, clock in self.clocks.items():
            if isinstance(clock, Clock):
                try:
                    clock.meta.model_validate(clock.meta.model_dump())
                except ValueError as e:
                    errors.append(f"Clock {cid}: {str(e)}")

        # Check scene meta if it has one
        if hasattr(self.scene, "meta") and self.scene.meta:
            try:
                self.scene.meta.model_validate(self.scene.meta.model_dump())
            except ValueError as e:
                errors.append(f"Scene {self.scene.id}: {str(e)}")

        return errors

    def export_state(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"] = "full",
        pov_id: Optional[str] = None,
        role: Literal["player", "narrator", "gm"] = "gm",
        include_known_by: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Export game state with different serialization policies for various contexts.

        Args:
            mode: Export mode determining level of detail
                - "full": Complete state (for debugging/GM tools)
                - "public": Public-safe state (for sharing/logs)
                - "minimal": Core state only (for storage efficiency)
                - "save": Persistent state for save files
                - "session": Runtime state for session management
            pov_id: Point of view for redaction (if None, uses role-appropriate view)
            role: Redaction role for information access level
            include_known_by: Override known_by inclusion in meta (None=auto based on mode)

        Returns:
            Dictionary with game state in requested format
        """
        # Determine redaction settings based on mode
        apply_redaction = mode == "public" or (mode == "session" and role != "gm")

        state = {
            "scene": self._export_scene(mode, include_known_by),
            "zones": {},
            "entities": {},
            "clocks": {},
        }

        # Handle zones
        for zid, zone in self.zones.items():
            if apply_redaction:
                from .visibility import redact_zone

                redacted_zone = redact_zone(pov_id, zone, self, role)
                # Apply meta export policy to redacted zone
                if "meta" in redacted_zone:
                    redacted_zone["meta"] = zone.meta.export(mode, include_known_by)
                state["zones"][zid] = redacted_zone
            else:
                zone_data = zone.model_dump_json_safe(mode=mode)
                zone_data["meta"] = zone.meta.export(mode, include_known_by)
                state["zones"][zid] = zone_data

        # Handle entities
        for eid, entity in self.entities.items():
            if apply_redaction:
                from .visibility import redact_entity

                # For public mode, use a real entity ID if pov_id is None
                effective_pov_id = pov_id
                if mode == "public" and pov_id is None:
                    # Find first PC entity as default POV for public exports
                    pc_entities = [
                        e_id
                        for e_id, e in self.entities.items()
                        if getattr(e, "type", None) == "pc"
                    ]
                    effective_pov_id = (
                        pc_entities[0]
                        if pc_entities
                        else list(self.entities.keys())[0] if self.entities else None
                    )

                redacted_entity = redact_entity(effective_pov_id, entity, self, role)

                # For public mode, completely exclude non-visible entities
                if mode == "public" and not redacted_entity.get("is_visible", False):
                    continue

                # Apply meta export policy if entity has meta
                if "meta" in redacted_entity:
                    redacted_entity["meta"] = entity.meta.export(mode, include_known_by)
                state["entities"][eid] = redacted_entity
            else:
                entity_data = entity.model_dump()
                entity_data["meta"] = entity.meta.export(mode, include_known_by)
                state["entities"][eid] = entity_data

        # Handle clocks
        for cid, clock in self.clocks.items():
            if isinstance(clock, Clock):
                if apply_redaction:
                    from .visibility import redact_clock

                    redacted_clock = redact_clock(pov_id, clock)
                    if "meta" in redacted_clock:
                        redacted_clock["meta"] = clock.meta.export(
                            mode, include_known_by
                        )
                    state["clocks"][cid] = redacted_clock
                else:
                    clock_data = clock.model_dump()
                    clock_data["meta"] = clock.meta.export(mode, include_known_by)
                    state["clocks"][cid] = clock_data
            else:
                # Legacy format - preserve as-is
                state["clocks"][cid] = (
                    clock.copy() if isinstance(clock, dict) else clock
                )

        return state

    def _export_scene(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"],
        include_known_by: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Export scene with appropriate meta serialization policy.

        Args:
            mode: Export mode
            include_known_by: Whether to include known_by in meta

        Returns:
            Scene data with exported meta
        """
        scene_data = self.scene.model_dump()

        # Export scene meta if it exists
        if hasattr(self.scene, "meta") and self.scene.meta:
            scene_data["meta"] = self.scene.meta.export(mode, include_known_by)

        return scene_data

    def to_save_format(self, include_runtime_data: bool = False) -> Dict[str, Any]:
        """
        Export game state for save files - persistent data only.

        Args:
            include_runtime_data: Whether to include runtime-only data like known_by

        Returns:
            Dictionary suitable for save files
        """
        return self.export_state(
            mode="save",
            role="gm",  # GM view for complete data
            include_known_by=include_runtime_data,
        )

    def to_session_format(self, pov_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Export game state for session management - includes runtime data.

        Args:
            pov_id: Point of view for redaction

        Returns:
            Dictionary suitable for session management
        """
        return self.export_state(
            mode="session", pov_id=pov_id, role="player" if pov_id else "gm"
        )

    def to_public_format(
        self,
        pov_id: Optional[str] = None,
        role: Literal["player", "narrator", "gm"] = "player",
    ) -> Dict[str, Any]:
        """
        Export game state for public sharing - excludes sensitive data.

        Args:
            pov_id: Point of view for redaction
            role: Redaction role

        Returns:
            Dictionary suitable for public sharing
        """
        return self.export_state(
            mode="public",
            pov_id=pov_id,
            role=role,
            include_known_by=False,  # Never include known_by in public format
        )

    def to_minimal_format(self) -> Dict[str, Any]:
        """
        Export game state in minimal format - core data only.

        Returns:
            Dictionary with minimal data set
        """
        return self.export_state(mode="minimal", role="gm", include_known_by=False)

    def _redact_legacy_clock(
        self, pov_id: Optional[str], clock_id: str, clock_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Redact legacy clock dictionary format for backward compatibility.
        """
        from copy import deepcopy

        # Check clock visibility using existing logic
        meta = clock_data.get("meta", {})
        if meta.get("visibility") == "gm_only":
            return {"id": clock_id, "value": None, "max": None, "is_visible": False}
        if meta.get("visibility") == "hidden":
            if pov_id not in meta.get("known_by", set()):
                return {"id": clock_id, "value": None, "max": None, "is_visible": False}

        # Return visible clock data
        safe_clock = deepcopy(clock_data)
        safe_clock["id"] = clock_id
        safe_clock["is_visible"] = True

        # Strip GM notes
        if "meta" in safe_clock:
            safe_clock["meta"]["notes"] = None

        return safe_clock

    # =============================================================================
    # Event System for Dynamic Zone Changes
    # =============================================================================

    def register_event_listener(self, event_type: str, listener: Callable) -> None:
        """
        Register an event listener for a specific event type.

        Args:
            event_type: Type of event to listen for (e.g., "zone_graph.exit_blocked")
            listener: Function to call when event occurs
        """
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)

    def unregister_event_listener(self, event_type: str, listener: Callable) -> bool:
        """
        Unregister an event listener.

        Args:
            event_type: Type of event to stop listening for
            listener: Function to remove

        Returns:
            True if listener was found and removed
        """
        if event_type in self._event_listeners:
            try:
                self._event_listeners[event_type].remove(listener)
                return True
            except ValueError:
                pass
        return False

    def emit(self, event_type: str, **event_data) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_type: Type of event being emitted
            **event_data: Event-specific data to pass to listeners
        """
        if event_type in self._event_listeners:
            # Iterate over a snapshot to prevent modifications during dispatch from disrupting delivery
            for listener in list(self._event_listeners[event_type]):
                try:
                    listener(event_type=event_type, world=self, **event_data)
                except Exception as e:
                    # Log error but don't break event processing
                    # In a real system you'd use proper logging here
                    print(f"Error in event listener for {event_type}: {e}")

    def get_event_listeners(self, event_type: str) -> List[Callable]:
        """
        Get all listeners for a specific event type.

        Args:
            event_type: Event type to get listeners for

        Returns:
            List of listener functions
        """
        return self._event_listeners.get(event_type, [])


def is_clock_visible_to(
    clock: Union[Clock, Dict[str, Any]], pov_id: Optional[str] = None
) -> bool:
    """Check if a clock is visible to the given actor."""
    # Handle both Clock objects and legacy dict format
    if isinstance(clock, Clock):
        if clock.meta.visibility == "gm_only":
            return False
        if clock.meta.visibility == "hidden":
            # Hidden clocks are only visible to actors who know about them
            return pov_id in clock.meta.known_by if pov_id else False
    else:
        # Legacy dict format
        meta = clock.get("meta", {})
        if meta.get("visibility") == "gm_only":
            return False
        if meta.get("visibility") == "hidden":
            # Hidden clocks are only visible to actors who know about them
            known_by = meta.get("known_by", set())
            return pov_id in known_by if pov_id else False
    return True


class Utterance(BaseModel):
    """Player input with basic analysis."""

    text: str
    actor_id: str
    detected_intent: Optional[str] = None
    actionable_verbs: List[str] = Field(default_factory=list)

    def has_actionable_verb(self) -> bool:
        """Check if utterance contains actionable verbs like move, attack, talk, etc."""
        action_verbs = {
            "move",
            "go",
            "walk",
            "run",
            "sneak",
            "travel",
            "attack",
            "hit",
            "strike",
            "fight",
            "combat",
            "talk",
            "speak",
            "say",
            "tell",
            "ask",
            "whisper",
            "use",
            "cast",
            "drink",
            "activate",
            "throw",
            "look",
            "examine",
            "search",
            "investigate",
        }
        return any(verb in self.text.lower() for verb in action_verbs)


def is_visible_to(entity: BaseEntity, scene: Optional[Scene] = None) -> bool:
    """Check if an entity is visible to the given actor.

    Args:
        entity: The entity being checked
        scene: Current scene for environmental visibility rules

    Returns:
        True if the entity should be visible to the actor
    """
    # GM-only content is never visible unless explicitly in GM mode
    if entity.meta.visibility == "gm_only":
        return False

    # Explicit hidden visibility
    if entity.meta.visibility == "hidden":
        return False

    # Scene-based visibility rules
    if scene and scene.meta.visibility == "gm_only":
        return False

    # Dark lighting rules (future enhancement)
    if scene and scene.tags.get("lighting") == "dark":
        # Future: check for darkvision, light sources, etc.
        pass

    return True


def is_zone_visible_to(zone: "Zone", scene: Optional[Scene] = None) -> bool:
    """Check if a zone is visible to the given actor."""
    # GM-only content is never visible unless explicitly in GM mode
    if zone.meta.visibility == "gm_only":
        return False

    # Explicit hidden visibility
    if zone.meta.visibility == "hidden":
        return False

    # Scene-based visibility rules
    if scene and scene.meta.visibility == "gm_only":
        return False

    return True
