"""
Core data structures for the AI D&D game state and utterances.
"""

import re
from typing import Dict, List, Optional, Any, Union, Literal, Annotated, cast
from pydantic import BaseModel, ConfigDict, Field, model_validator
from enum import Enum


class Meta(BaseModel):
    """Metadata for system-level management (not gameplay state)."""

    created_at: Optional[str] = None  # ISO timestamp
    last_changed_at: Optional[str] = None
    visibility: Literal["public", "hidden", "gm_only"] = "public"
    source: Optional[str] = None  # e.g., "manual", "generator", "import"
    notes: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class Zone(BaseModel):
    """Represents a game zone/location."""

    id: str
    name: str
    description: str
    adjacent_zones: List[str]
    blocked_exits: List[str] = Field(
        default_factory=list
    )  # Optional list of blocked adjacent zones
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
    meta: Meta = Field(default_factory=Meta)


class GameState(BaseModel):
    """Core game state representation."""

    entities: Dict[str, Entity]  # Changed from actors to entities
    zones: Dict[str, Zone]
    scene: Scene = Field(default_factory=Scene)
    pending_action: Optional[str] = None
    current_actor: Optional[str] = None
    turn_flags: Dict[str, Any] = Field(default_factory=dict)
    clocks: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # Enhanced with meta support

    # Backward compatibility property
    @property
    def actors(self) -> Dict[str, Union[PC, NPC]]:
        """Get only PC and NPC entities for backward compatibility."""
        filtered = {k: v for k, v in self.entities.items() if v.type in ("pc", "npc")}
        return cast(Dict[str, Union[PC, NPC]], filtered)


def is_clock_visible_to(clock_data: Dict[str, Any]) -> bool:
    """Check if a clock is visible to the given actor."""
    # Check for meta.visibility in clock data
    meta = clock_data.get("meta", {})
    if meta.get("visibility") == "gm_only":
        return False
    if meta.get("visibility") == "hidden":
        return False
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
