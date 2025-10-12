"""
Test suite for Zone Graph utilities and enhanced Zone/Exit models.

This module provides comprehensive testing for the zone graph system including:
- Zone model migration and compatibility
- Zone graph utilities (adjacency, pathfinding, etc.)
- Exit conditions and usability
- Integration with existing systems
"""

import pytest
from typing import Dict, Any
import sys
import os

# Add project root to path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import GameState, Zone, PC, NPC, Scene, HP, Entity
from backend.router.zone_graph import (
    get_zone,
    is_adjacent,
    path_exists,
    find_shortest_path,
    get_adjacent_zones,
    list_exits,
    describe_exits,
    is_exit_usable,
    zone_has_tag,
    zone_is_public,
    set_zone_tag,
    remove_zone_tag,
    get_zones_with_tag,
    get_reachable_zones,
    validate_zone_graph,
)
from models.space import Exit
from models.meta import Meta


class TestZoneMigrationAndCompatibility:
    """Test Zone model migration from legacy format and backward compatibility."""

    def test_zone_from_legacy_format(self):
        """Test Zone creation from legacy adjacent_zones format."""
        legacy_data = {
            "id": "courtyard",
            "name": "Courtyard",
            "description": "A stone courtyard",
            "adjacent_zones": ["hall", "garden"],
            "blocked_exits": ["garden"],
        }

        zone = Zone(**legacy_data)

        # Check that exits were created correctly
        assert len(zone.exits) == 2

        # Find exits by target
        hall_exit = next((ex for ex in zone.exits if ex.to == "hall"), None)
        garden_exit = next((ex for ex in zone.exits if ex.to == "garden"), None)

        assert hall_exit is not None
        assert not hall_exit.blocked

        assert garden_exit is not None
        assert garden_exit.blocked

    def test_zone_backward_compatibility_properties(self):
        """Test that legacy properties still work with new Zone model."""
        # Create zone with new Exit format
        zone = Zone(id="test_zone", name="Test Zone", description="A test zone")
        zone.add_exit("zone_a", blocked=False)
        zone.add_exit("zone_b", blocked=True)
        zone.add_exit("zone_c", blocked=False)

        # Test legacy properties
        assert set(zone.adjacent_zones) == {"zone_a", "zone_c"}
        assert zone.blocked_exits == ["zone_b"]

    def test_zone_exit_manipulation(self):
        """Test Zone exit manipulation methods."""
        zone = Zone(id="test", name="Test Zone")

        # Add exits
        exit1 = zone.add_exit("target1", direction="north", label="North Door")
        assert exit1.to == "target1"
        assert exit1.direction == "north"
        assert exit1.label == "North Door"

        # Get exit
        found_exit = zone.get_exit("target1")
        assert found_exit is not None
        assert found_exit.direction == "north"

        # Remove exit
        assert zone.remove_exit("target1")
        assert zone.get_exit("target1") is None
        assert not zone.remove_exit("nonexistent")

    def test_zone_tag_management(self):
        """Test Zone tag management."""
        zone = Zone(id="test", name="Test Zone")

        # Add tags
        zone.add_tag("dark")
        zone.add_tag("dangerous")
        assert zone.has_tag("dark")
        assert zone.has_tag("dangerous")
        assert not zone.has_tag("safe")

        # Remove tags
        assert zone.remove_tag("dark")
        assert not zone.has_tag("dark")
        assert not zone.remove_tag("nonexistent")


class TestZoneGraphUtilities:
    """Test core zone graph utility functions."""

    @pytest.fixture
    def sample_world(self):
        """Create a sample game world for testing."""
        zones = {
            "courtyard": Zone(
                id="courtyard", name="Courtyard", description="A stone courtyard"
            ),
            "hall": Zone(id="hall", name="Great Hall", description="A grand hall"),
            "garden": Zone(id="garden", name="Garden", description="A peaceful garden"),
            "tower": Zone(id="tower", name="Tower", description="A tall tower"),
        }

        # Set up exits
        zones["courtyard"].add_exit("hall", direction="north")
        zones["courtyard"].add_exit("garden", direction="east", blocked=True)
        zones["hall"].add_exit("courtyard", direction="south")
        zones["hall"].add_exit("tower", direction="up")
        zones["garden"].add_exit("courtyard", direction="west")
        zones["tower"].add_exit("hall", direction="down")

        # Add some tags
        zones["garden"].add_tag("peaceful")
        zones["tower"].add_tag("high")
        zones["tower"].add_tag("dangerous")

        entities: Dict[str, Entity] = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                type="pc",
                current_zone="courtyard",
                hp=HP(current=20, max=20),
            )
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    def test_get_zone(self, sample_world):
        """Test zone retrieval."""
        zone = get_zone(sample_world, "courtyard")
        assert zone.id == "courtyard"
        assert zone.name == "Courtyard"

        with pytest.raises(ValueError, match="Zone 'nonexistent' not found"):
            get_zone(sample_world, "nonexistent")

    def test_is_adjacent_basic(self, sample_world):
        """Test basic adjacency checks."""
        # Direct connection
        assert is_adjacent("courtyard", "hall", sample_world)
        assert is_adjacent("hall", "courtyard", sample_world)

        # No direct connection
        assert not is_adjacent("courtyard", "tower", sample_world)

        # Blocked connection
        assert not is_adjacent("courtyard", "garden", sample_world)
        assert is_adjacent("courtyard", "garden", sample_world, allow_blocked=True)

    def test_path_exists_simple(self, sample_world):
        """Test path existence checks."""
        # Direct path
        assert path_exists("courtyard", "hall", sample_world)

        # Multi-step path
        assert path_exists("courtyard", "tower", sample_world)

        # No path due to blocked exit
        assert not path_exists("courtyard", "garden", sample_world)
        assert path_exists("courtyard", "garden", sample_world, allow_blocked=True)

        # Same zone
        assert path_exists("courtyard", "courtyard", sample_world)

    def test_find_shortest_path(self, sample_world):
        """Test shortest path finding."""
        # Direct path
        path = find_shortest_path("courtyard", "hall", sample_world)
        assert path == ["courtyard", "hall"]

        # Multi-step path
        path = find_shortest_path("courtyard", "tower", sample_world)
        assert path == ["courtyard", "hall", "tower"]

        # No path
        path = find_shortest_path("courtyard", "garden", sample_world)
        assert path is None

        # Same zone
        path = find_shortest_path("courtyard", "courtyard", sample_world)
        assert path == ["courtyard"]

    def test_get_adjacent_zones(self, sample_world):
        """Test getting adjacent zones."""
        adjacent = get_adjacent_zones("courtyard", sample_world)
        assert set(adjacent) == {"hall"}

        adjacent_with_blocked = get_adjacent_zones(
            "courtyard", sample_world, include_blocked=True
        )
        assert set(adjacent_with_blocked) == {"hall", "garden"}

        # Non-existent zone
        adjacent = get_adjacent_zones("nonexistent", sample_world)
        assert adjacent == []

    def test_list_exits(self, sample_world):
        """Test listing exits from a zone."""
        courtyard = get_zone(sample_world, "courtyard")

        # Only unblocked exits
        exits = list_exits(courtyard, sample_world)
        assert len(exits) == 1
        assert exits[0].to == "hall"

        # Include blocked exits
        exits = list_exits(courtyard, sample_world, include_blocked=True)
        assert len(exits) == 2
        exit_targets = {ex.to for ex in exits}
        assert exit_targets == {"hall", "garden"}

    def test_describe_exits(self, sample_world):
        """Test exit descriptions."""
        courtyard = get_zone(sample_world, "courtyard")
        descriptions = describe_exits(courtyard, sample_world)

        assert len(descriptions) == 1
        desc = descriptions[0]
        assert desc["to"] == "hall"
        assert desc["direction"] == "north"
        assert desc["target_name"] == "Great Hall"
        assert not desc["blocked"]

    def test_zone_tag_utilities(self, sample_world):
        """Test zone tag utility functions."""
        tower = get_zone(sample_world, "tower")
        garden = get_zone(sample_world, "garden")

        # Test zone_has_tag
        assert zone_has_tag(tower, "dangerous")
        assert not zone_has_tag(garden, "dangerous")

        # Test get_zones_with_tag
        dangerous_zones = get_zones_with_tag(sample_world, "dangerous")
        assert len(dangerous_zones) == 1
        assert dangerous_zones[0].id == "tower"

        # Test tag manipulation
        set_zone_tag(garden, "magical")
        assert zone_has_tag(garden, "magical")

        assert remove_zone_tag(garden, "magical")
        assert not zone_has_tag(garden, "magical")

    def test_get_reachable_zones(self, sample_world):
        """Test getting all reachable zones."""
        reachable = get_reachable_zones("courtyard", sample_world)
        assert reachable == {"courtyard", "hall", "tower"}

        reachable_with_blocked = get_reachable_zones(
            "courtyard", sample_world, allow_blocked=True
        )
        assert reachable_with_blocked == {"courtyard", "hall", "tower", "garden"}

    def test_validate_zone_graph(self, sample_world):
        """Test zone graph validation."""
        # Valid graph should have no errors
        errors = validate_zone_graph(sample_world)
        assert errors == []

        # Add invalid exit to test validation
        courtyard = get_zone(sample_world, "courtyard")
        courtyard.add_exit("nonexistent_zone")

        errors = validate_zone_graph(sample_world)
        assert len(errors) == 1
        assert "nonexistent_zone" in errors[0]


class TestExitConditions:
    """Test exit conditions and usability checks."""

    @pytest.fixture
    def conditional_world(self):
        """Create a world with conditional exits."""
        zones = {
            "start": Zone(id="start", name="Start", description="Starting area"),
            "locked_room": Zone(
                id="locked_room", name="Locked Room", description="A locked room"
            ),
            "high_level_area": Zone(
                id="high_level_area",
                name="High Level Area",
                description="Dangerous area",
            ),
        }

        # Add exits with conditions
        zones["start"].add_exit(
            "locked_room", label="Iron Door", conditions={"key_required": "iron_key"}
        )
        zones["start"].add_exit(
            "high_level_area",
            label="Dangerous Path",
            conditions={"level_required": "5"},
        )

        entities: Dict[str, Entity] = {
            "pc.hero": PC(
                id="pc.hero",
                name="Hero",
                type="pc",
                current_zone="start",
                hp=HP(current=20, max=20),
                inventory=["iron_key", "health_potion"],  # Hero has the key
                tags={"level": 10},  # High level hero
            ),
            "pc.novice": PC(
                id="pc.novice",
                name="Novice",
                type="pc",
                current_zone="start",
                hp=HP(current=10, max=10),
                inventory=[],  # Novice has no key
                tags={"level": 2},  # Low level novice
            ),
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    def test_exit_usability_with_key(self, conditional_world):
        """Test exit usability with key requirements."""
        start_zone = get_zone(conditional_world, "start")
        locked_exit = start_zone.get_exit("locked_room")
        assert locked_exit is not None  # Ensure exit exists

        hero = conditional_world.entities["pc.hero"]
        novice = conditional_world.entities["pc.novice"]

        # Hero has key, should be usable
        usable, reason = is_exit_usable(locked_exit, hero, conditional_world)
        assert usable
        assert reason is None

        # Novice doesn't have key, should not be usable
        usable, reason = is_exit_usable(locked_exit, novice, conditional_world)
        assert not usable
        assert reason is not None and "iron_key" in reason

    def test_exit_usability_with_level(self, conditional_world):
        """Test exit usability with level requirements."""
        start_zone = get_zone(conditional_world, "start")
        level_exit = start_zone.get_exit("high_level_area")
        assert level_exit is not None  # Ensure exit exists

        hero = conditional_world.entities["pc.hero"]
        novice = conditional_world.entities["pc.novice"]

        # Hero has sufficient level (10 >= 5), should be usable
        usable, reason = is_exit_usable(level_exit, hero, conditional_world)
        assert usable
        assert reason is None

        # Novice has insufficient level (2 < 5), should not be usable
        usable, reason = is_exit_usable(level_exit, novice, conditional_world)
        assert not usable
        assert reason is not None and "level 5" in reason

    def test_exit_usability_blocked(self, conditional_world):
        """Test exit usability with blocked exits."""
        start_zone = get_zone(conditional_world, "start")
        start_zone.add_exit("blocked_area", blocked=True)

        blocked_exit = start_zone.get_exit("blocked_area")
        assert blocked_exit is not None  # Ensure exit exists
        hero = conditional_world.entities["pc.hero"]

        usable, reason = is_exit_usable(blocked_exit, hero, conditional_world)
        assert not usable
        assert reason == "blocked"

    def test_exit_usability_no_conditions(self, conditional_world):
        """Test exit usability with no conditions."""
        start_zone = get_zone(conditional_world, "start")
        start_zone.add_exit("open_area")  # No conditions

        open_exit = start_zone.get_exit("open_area")
        assert open_exit is not None  # Ensure exit exists
        hero = conditional_world.entities["pc.hero"]

        usable, reason = is_exit_usable(open_exit, hero, conditional_world)
        assert usable
        assert reason is None


class TestIntegration:
    """Test integration with existing systems."""

    def test_zone_serialization_roundtrip(self):
        """Test that zones can be serialized and deserialized properly."""
        # Create zone with new format
        zone = Zone(
            id="test_zone",
            name="Test Zone",
            description="A test zone",
            tags={"magical", "dangerous"},
        )
        zone.add_exit("target1", direction="north", label="North Door")
        zone.add_exit(
            "target2", blocked=True, conditions={"key_required": "special_key"}
        )

        # Serialize
        zone_dict = zone.model_dump()

        # Deserialize
        restored_zone = Zone(**zone_dict)

        # Verify everything is preserved
        assert restored_zone.id == "test_zone"
        assert restored_zone.name == "Test Zone"
        assert restored_zone.description == "A test zone"
        assert restored_zone.tags == {"magical", "dangerous"}
        assert len(restored_zone.exits) == 2

        # Check exits
        north_exit = restored_zone.get_exit("target1")
        assert north_exit is not None
        assert north_exit.direction == "north"
        assert north_exit.label == "North Door"
        assert not north_exit.blocked

        blocked_exit = restored_zone.get_exit("target2")
        assert blocked_exit is not None
        assert blocked_exit.blocked
        assert blocked_exit.conditions == {"key_required": "special_key"}

    def test_legacy_compatibility_in_gamestate(self):
        """Test that GameState works with both old and new zone formats."""
        # Create GameState with legacy zone data
        legacy_zone_data = {
            "id": "legacy_zone",
            "name": "Legacy Zone",
            "description": "A zone from legacy format",
            "adjacent_zones": ["zone_a", "zone_b"],
            "blocked_exits": ["zone_b"],
        }

        zone = Zone(**legacy_zone_data)
        game_state = GameState(zones={"legacy_zone": zone}, entities={}, scene=Scene())

        # Test that zone graph utilities work
        assert is_adjacent("legacy_zone", "zone_a", game_state)
        assert not is_adjacent("legacy_zone", "zone_b", game_state)  # blocked
        assert is_adjacent("legacy_zone", "zone_b", game_state, allow_blocked=True)

        adjacent = get_adjacent_zones("legacy_zone", game_state)
        assert adjacent == ["zone_a"]

        adjacent_with_blocked = get_adjacent_zones(
            "legacy_zone", game_state, include_blocked=True
        )
        assert set(adjacent_with_blocked) == {"zone_a", "zone_b"}


if __name__ == "__main__":
    pytest.main([__file__])
