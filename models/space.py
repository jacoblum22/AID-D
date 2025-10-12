"""
Enhanced Zone and Exit models for sophisticated zone graph functionality.

This module provides rich zone modeling with directional exits, conditional travel,
and metadata support for the AI D&D system.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Set, Any, Literal
from .meta import Meta


class Exit(BaseModel):
    """
    Represents a directional exit from one zone to another.

    Supports conditional travel, directional labeling, cost-based pathfinding,
    and rich metadata.
    """

    to: str  # target zone id
    label: Optional[str] = None  # e.g. "north door", "ladder up"
    direction: Optional[str] = None  # "north", "south", "up", "down", etc.
    blocked: bool = False  # currently blocked?
    lock_id: Optional[str] = None  # optional puzzle/door id
    conditions: Optional[Dict[str, str]] = None  # e.g. {"key_required": "brass_key"}
    cost: float = 1.0  # movement cost for pathfinding (1.0 = normal)
    terrain: Optional[str] = None  # "stairs", "mud", "fire", "water", etc.
    meta: Meta = Field(default_factory=Meta)

    def model_dump_json_safe(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"] = "save",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Export Exit data with JSON-safe serialization (handles Meta sets).

        Args:
            mode: Export mode for Meta fields
            **kwargs: Additional arguments passed to model_dump

        Returns:
            Dictionary with meta.known_by as list instead of set
        """
        data = self.model_dump(**kwargs)
        # Use meta's export method for JSON-safe serialization
        if "meta" in data:
            data["meta"] = self.meta.export(mode=mode)
        return data

    def get_display_label(self, world_zones: Optional[Dict[str, "Zone"]] = None) -> str:
        """
        Get a human-readable label for this exit.

        Args:
            world_zones: Optional zone lookup for fallback naming

        Returns:
            Human-readable exit label
        """
        if self.label:
            return self.label
        elif self.direction:
            return self.direction
        elif world_zones and self.to in world_zones:
            return f"Exit to {world_zones[self.to].name}"
        else:
            return f"Exit to {self.to}"

    def get_movement_cost(
        self,
        actor: Optional[Any] = None,
        terrain_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> float:
        """
        Calculate the movement cost for this exit, considering terrain and actor modifiers.

        Args:
            actor: Optional actor entity for personalized costs
            terrain_modifiers: Optional terrain modifier table
                               Format: {"terrain_type": {"actor_property": multiplier}}

        Returns:
            Final movement cost (base_cost * terrain_modifier)
        """
        final_cost = self.cost

        # Apply terrain modifiers if terrain and modifiers are specified
        if self.terrain and terrain_modifiers and self.terrain in terrain_modifiers:
            terrain_mods = terrain_modifiers[self.terrain]

            if actor:
                # Check actor for relevant properties/tags
                actor_tags = getattr(actor, "tags", {})

                # Apply modifiers based on actor properties
                for property_name, multiplier in terrain_mods.items():
                    if property_name in actor_tags:
                        final_cost *= multiplier
                        break  # Apply first matching modifier
                    elif hasattr(actor, property_name):
                        # Check for boolean properties like "flying", "swimming", etc.
                        if getattr(actor, property_name):
                            final_cost *= multiplier
                            break

        return max(0.1, final_cost)  # Minimum cost to prevent infinite loops

    def get_terrain_description(self) -> str:
        """
        Get a human-readable description of the terrain.

        Returns:
            Terrain description or empty string if no terrain
        """
        if not self.terrain:
            return ""

        terrain_descriptions = {
            "stairs": "steep stairs",
            "mud": "muddy ground",
            "fire": "flames",
            "water": "deep water",
            "ice": "slippery ice",
            "thorns": "thorny undergrowth",
            "sand": "shifting sand",
            "rubble": "broken rubble",
            "swamp": "swampy marsh",
            "lava": "molten lava",
        }

        return terrain_descriptions.get(self.terrain, f"{self.terrain} terrain")


class Zone(BaseModel):
    """
    Represents a game zone/location with rich exit modeling.

    Zones are graph nodes connected by directional Exit edges, supporting
    conditional travel, blocking, and sophisticated movement mechanics.
    """

    id: str
    name: str
    description: Optional[str] = None
    exits: List[Exit] = Field(default_factory=list)
    tags: Set[str] = Field(default_factory=set)  # "dark", "noisy", "safe", etc.
    discovered_by: Set[str] = Field(
        default_factory=set
    )  # actor IDs who have discovered this zone
    region: Optional[str] = None  # regional grouping for macro-level organization
    meta: Meta = Field(default_factory=Meta)

    @field_validator("tags", mode="before")
    @classmethod
    def convert_tags_to_set(cls, v):
        """Convert tags from list to set if needed for backward compatibility."""
        if isinstance(v, list):
            return set(v)
        return v

    @field_validator("discovered_by", mode="before")
    @classmethod
    def convert_discovered_by_to_set(cls, v):
        """Convert discovered_by from list to set if needed for backward compatibility."""
        if isinstance(v, list):
            return set(v)
        return v

    # Backwards compatibility with existing code
    @property
    def adjacent_zones(self) -> List[str]:
        """
        Legacy compatibility property for existing code.

        Returns:
            List of zone IDs that have unblocked exits
        """
        return [exit.to for exit in self.exits if not exit.blocked]

    @property
    def blocked_exits(self) -> List[str]:
        """
        Legacy compatibility property for existing code.

        Returns:
            List of zone IDs that have blocked exits
        """
        return [exit.to for exit in self.exits if exit.blocked]

    def add_exit(
        self,
        to: str,
        label: Optional[str] = None,
        direction: Optional[str] = None,
        blocked: bool = False,
        conditions: Optional[Dict[str, str]] = None,
        lock_id: Optional[str] = None,
        cost: float = 1.0,
        terrain: Optional[str] = None,
        region: Optional[str] = None,
    ) -> "Exit":
        """
        Add a new exit to this zone.

        Args:
            to: Target zone ID
            label: Optional human-readable label
            direction: Optional directional indicator
            blocked: Whether the exit is initially blocked
            conditions: Optional travel conditions
            lock_id: Optional lock/puzzle ID
            cost: Movement cost for pathfinding
            terrain: Optional terrain type
            region: Optional region override for this zone

        Returns:
            The created Exit object
        """
        # Set region if provided
        if region is not None:
            self.set_region(region)

        exit = Exit(
            to=to,
            label=label,
            direction=direction,
            blocked=blocked,
            conditions=conditions,
            lock_id=lock_id,
            cost=cost,
            terrain=terrain,
        )
        self.exits.append(exit)

        # Touch meta to update timestamp for change detection
        self.meta.touch()

        return exit

    def remove_exit(self, to: str) -> bool:
        """
        Remove an exit to the specified zone.

        Args:
            to: Target zone ID to remove exit for

        Returns:
            True if an exit was removed, False if not found
        """
        original_count = len(self.exits)
        self.exits = [exit for exit in self.exits if exit.to != to]

        # Touch meta only if an exit was actually removed
        if len(self.exits) < original_count:
            self.meta.touch()

        return len(self.exits) < original_count

    def get_exit(self, to: str) -> Optional[Exit]:
        """
        Get the exit to a specific zone.

        Args:
            to: Target zone ID

        Returns:
            Exit object if found, None otherwise
        """
        for exit in self.exits:
            if exit.to == to:
                return exit
        return None

    def get_exits_by_direction(self, direction: str) -> List[Exit]:
        """
        Get all exits in a specific direction.

        Args:
            direction: Direction to search for

        Returns:
            List of exits in that direction
        """
        return [exit for exit in self.exits if exit.direction == direction]

    def has_tag(self, tag: str) -> bool:
        """
        Check if zone has a specific tag.

        Args:
            tag: Tag to check for

        Returns:
            True if zone has the tag
        """
        return tag in self.tags

    def add_tag(self, tag: str) -> None:
        """
        Add a tag to this zone.

        Args:
            tag: Tag to add
        """
        self.tags.add(tag)
        self.meta.touch()

    def remove_tag(self, tag: str) -> bool:
        """
        Remove a tag from this zone.

        Args:
            tag: Tag to remove

        Returns:
            True if tag was removed, False if not found
        """
        if tag in self.tags:
            self.tags.remove(tag)
            self.meta.touch()
            return True
        return False

    def is_discovered_by(self, actor_id: str) -> bool:
        """
        Check if this zone has been discovered by an actor.

        Args:
            actor_id: Actor ID to check

        Returns:
            True if the zone has been discovered by this actor
        """
        return actor_id in self.discovered_by

    def discover_by(self, actor_id: str) -> bool:
        """
        Mark this zone as discovered by an actor.

        Args:
            actor_id: Actor ID who discovered the zone

        Returns:
            True if this was a new discovery, False if already discovered
        """
        if actor_id not in self.discovered_by:
            self.discovered_by.add(actor_id)
            self.meta.touch()
            return True
        return False

    def forget_discovery(self, actor_id: str) -> bool:
        """
        Remove discovery status for an actor (for memory loss effects, etc.).

        Args:
            actor_id: Actor ID to remove discovery for

        Returns:
            True if discovery was removed, False if not found
        """
        if actor_id in self.discovered_by:
            self.discovered_by.remove(actor_id)
            self.meta.touch()
            return True
        return False

    def get_discovery_status(self, actor_id: str) -> str:
        """
        Get human-readable discovery status for an actor.

        Args:
            actor_id: Actor ID to check

        Returns:
            "discovered", "undiscovered"
        """
        return "discovered" if self.is_discovered_by(actor_id) else "undiscovered"

    def set_region(self, region: Optional[str]) -> None:
        """
        Set the regional grouping for this zone.

        Args:
            region: Region name or None to remove region assignment
        """
        if self.region != region:
            self.region = region
            self.meta.touch()

    def is_in_region(self, region: str) -> bool:
        """
        Check if this zone belongs to a specific region.

        Args:
            region: Region name to check

        Returns:
            True if zone is in the specified region
        """
        return self.region == region

    def get_region_display_name(self) -> str:
        """
        Get a human-readable region name.

        Returns:
            Region name or "Unassigned" if no region set
        """
        return self.region if self.region else "Unassigned"

    def model_dump_json_safe(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"] = "save",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Export Zone data with JSON-safe serialization (sets converted to lists).

        Args:
            mode: Export mode for Meta fields
            **kwargs: Additional arguments passed to model_dump

        Returns:
            Dictionary with tags as list instead of set and exits with JSON-safe meta
        """
        data = self.model_dump(**kwargs)
        # Convert tags set to sorted list for JSON compatibility
        if "tags" in data and isinstance(data["tags"], (set, list)):
            data["tags"] = sorted(list(data["tags"]))

        # Convert discovered_by set to sorted list for JSON compatibility
        if "discovered_by" in data and isinstance(data["discovered_by"], (set, list)):
            data["discovered_by"] = sorted(list(data["discovered_by"]))

        # Handle exits - use each exit's JSON-safe serialization
        if "exits" in data and self.exits:
            data["exits"] = [
                exit.model_dump_json_safe(mode=mode) for exit in self.exits
            ]

        # Use meta's export method for JSON-safe serialization
        if "meta" in data:
            data["meta"] = self.meta.export(mode=mode)

        return data


# Backwards compatibility function for zone creation
def create_zone_from_legacy(
    id: str,
    name: str,
    description: str = "",
    adjacent_zones: Optional[List[str]] = None,
    blocked_exits: Optional[List[str]] = None,
    **kwargs,
) -> Zone:
    """
    Create a Zone from legacy adjacent_zones format.

    Args:
        id: Zone ID
        name: Zone name
        description: Zone description
        adjacent_zones: List of connected zone IDs
        blocked_exits: List of blocked zone IDs
        **kwargs: Additional zone properties

    Returns:
        Zone object with exits created from legacy format
    """
    zone = Zone(id=id, name=name, description=description, **kwargs)

    # Convert adjacent_zones to Exit objects only if no explicit exits were provided
    if adjacent_zones and "exits" not in kwargs:
        blocked_set = set(blocked_exits or [])
        for zone_id in adjacent_zones:
            zone.add_exit(to=zone_id, blocked=zone_id in blocked_set)

    return zone
