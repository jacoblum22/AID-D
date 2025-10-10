"""
Test suite for Zone Discovery & Memory Tracking features.

This module tests the fog-of-war style discovery system for zones,
including discovery tracking, revelation mechanics, and map generation.
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
    reveal_adjacent_zones,
    discover_zone,
    is_zone_discovered,
    get_discovered_zones,
    get_undiscovered_adjacent_zones,
    get_zone_discovery_map,
)
from models.space import Exit
from models.meta import Meta


class TestZoneDiscoveryBasics:
    """Test basic zone discovery functionality."""

    @pytest.fixture
    def discovery_world(self):
        """Create a world for testing zone discovery."""
        zones = {
            "start": Zone(
                id="start",
                name="Starting Room",
                description="Where the adventure begins",
            ),
            "north_hall": Zone(
                id="north_hall", name="North Hall", description="A long hallway"
            ),
            "secret_room": Zone(
                id="secret_room", name="Secret Room", description="A hidden chamber"
            ),
            "gm_only_zone": Zone(
                id="gm_only_zone",
                name="GM Zone",
                description="Players shouldn't see this",
            ),
        }

        # Set up exits
        zones["start"].add_exit("north_hall", direction="north")
        zones["start"].add_exit("secret_room", direction="hidden", blocked=True)
        zones["north_hall"].add_exit("start", direction="south")
        zones["north_hall"].add_exit("secret_room", direction="east")
        zones["secret_room"].add_exit("north_hall", direction="west")

        # Make one zone GM-only
        zones["gm_only_zone"].meta.gm_only = True

        entities: Dict[str, Entity] = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                type="pc",
                current_zone="start",
                hp=HP(current=20, max=20),
            ),
            "pc.bob": PC(
                id="pc.bob",
                name="Bob",
                type="pc",
                current_zone="start",
                hp=HP(current=20, max=20),
            ),
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    def test_zone_discovery_methods(self, discovery_world):
        """Test Zone model discovery methods."""
        start_zone = discovery_world.zones["start"]

        # Initially undiscovered
        assert not start_zone.is_discovered_by("pc.alice")
        assert start_zone.get_discovery_status("pc.alice") == "undiscovered"

        # Discover the zone
        assert start_zone.discover_by("pc.alice")  # New discovery
        assert not start_zone.discover_by("pc.alice")  # Already discovered
        assert start_zone.is_discovered_by("pc.alice")
        assert start_zone.get_discovery_status("pc.alice") == "discovered"

        # Different actor hasn't discovered it
        assert not start_zone.is_discovered_by("pc.bob")

        # Forget discovery
        assert start_zone.forget_discovery("pc.alice")
        assert not start_zone.is_discovered_by("pc.alice")
        assert not start_zone.forget_discovery("pc.alice")  # Already forgotten

    def test_discover_zone_function(self, discovery_world):
        """Test the discover_zone utility function."""
        # Discover existing zone
        assert discover_zone("pc.alice", "start", discovery_world)  # New discovery
        assert not discover_zone(
            "pc.alice", "start", discovery_world
        )  # Already discovered

        # Try to discover non-existent zone
        assert not discover_zone("pc.alice", "nonexistent", discovery_world)

    def test_is_zone_discovered_function(self, discovery_world):
        """Test the is_zone_discovered utility function."""
        # Initially not discovered
        assert not is_zone_discovered("pc.alice", "start", discovery_world)

        # After discovery
        discover_zone("pc.alice", "start", discovery_world)
        assert is_zone_discovered("pc.alice", "start", discovery_world)

        # Non-existent zone
        assert not is_zone_discovered("pc.alice", "nonexistent", discovery_world)

    def test_reveal_adjacent_zones(self, discovery_world):
        """Test revealing adjacent zones when entering a zone."""
        start_zone = discovery_world.zones["start"]

        # Reveal adjacent zones from start
        newly_discovered = reveal_adjacent_zones(
            "pc.alice", start_zone, discovery_world
        )

        # Should discover north_hall but not secret_room (blocked) or gm_only_zone
        assert "north_hall" in newly_discovered
        assert "secret_room" not in newly_discovered  # exists but should be discovered
        assert "gm_only_zone" not in newly_discovered  # GM only

        # Check that north_hall is now discovered
        assert is_zone_discovered("pc.alice", "north_hall", discovery_world)

        # Second revelation should not discover anything new
        newly_discovered_2 = reveal_adjacent_zones(
            "pc.alice", start_zone, discovery_world
        )
        assert len(newly_discovered_2) == 0

    def test_get_discovered_zones(self, discovery_world):
        """Test getting all discovered zones for an actor."""
        # Initially no zones discovered
        discovered = get_discovered_zones("pc.alice", discovery_world)
        assert len(discovered) == 0

        # Discover some zones
        discover_zone("pc.alice", "start", discovery_world)
        discover_zone("pc.alice", "north_hall", discovery_world)

        discovered = get_discovered_zones("pc.alice", discovery_world)
        assert len(discovered) == 2
        discovered_ids = {zone.id for zone in discovered}
        assert discovered_ids == {"start", "north_hall"}

    def test_get_undiscovered_adjacent_zones(self, discovery_world):
        """Test getting undiscovered adjacent zones."""
        # From start, both north_hall and secret_room should be undiscovered
        undiscovered = get_undiscovered_adjacent_zones(
            "pc.alice", "start", discovery_world
        )
        assert set(undiscovered) == {"north_hall", "secret_room"}

        # Discover north_hall
        discover_zone("pc.alice", "north_hall", discovery_world)

        # Now only secret_room should be undiscovered
        undiscovered = get_undiscovered_adjacent_zones(
            "pc.alice", "start", discovery_world
        )
        assert undiscovered == ["secret_room"]

        # Non-existent zone
        undiscovered = get_undiscovered_adjacent_zones(
            "pc.alice", "nonexistent", discovery_world
        )
        assert undiscovered == []

    def test_get_zone_discovery_map(self, discovery_world):
        """Test generating a discovery map for an actor."""
        # Initially all zones undiscovered except GM-only zones
        discovery_map = get_zone_discovery_map("pc.alice", discovery_world)

        expected = {
            "start": "undiscovered",
            "north_hall": "undiscovered",
            "secret_room": "undiscovered",
            "gm_only_zone": "hidden",
        }
        assert discovery_map == expected

        # Discover some zones
        discover_zone("pc.alice", "start", discovery_world)
        discover_zone("pc.alice", "north_hall", discovery_world)

        discovery_map = get_zone_discovery_map("pc.alice", discovery_world)
        expected = {
            "start": "discovered",
            "north_hall": "discovered",
            "secret_room": "undiscovered",
            "gm_only_zone": "hidden",
        }
        assert discovery_map == expected


class TestZoneDiscoveryIntegration:
    """Test integration of discovery system with existing features."""

    def test_discovery_serialization(self):
        """Test that zones with discovery data serialize properly."""
        # Create zone with discovery data
        zone = Zone(
            id="test_zone",
            name="Test Zone",
            description="A test zone",
            discovered_by={"pc.alice", "pc.bob"},
        )

        # Test serialization
        zone_dict = zone.model_dump()
        assert "discovered_by" in zone_dict
        assert set(zone_dict["discovered_by"]) == {"pc.alice", "pc.bob"}

        # Test JSON-safe serialization
        zone_dict_safe = zone.model_dump_json_safe()
        assert isinstance(zone_dict_safe["discovered_by"], list)
        assert set(zone_dict_safe["discovered_by"]) == {"pc.alice", "pc.bob"}

        # Test deserialization
        restored_zone = Zone(**zone_dict)
        assert restored_zone.discovered_by == {"pc.alice", "pc.bob"}
        assert restored_zone.is_discovered_by("pc.alice")
        assert restored_zone.is_discovered_by("pc.bob")
        assert not restored_zone.is_discovered_by("pc.charlie")

    def test_discovery_backward_compatibility(self):
        """Test that zones without discovery data work correctly."""
        # Create zone without discovered_by field (legacy format)
        zone = Zone(id="legacy_zone", name="Legacy Zone", description="A legacy zone")

        # Should have empty discovered_by set
        assert zone.discovered_by == set()
        assert not zone.is_discovered_by("pc.alice")

        # Discovery should work normally
        assert zone.discover_by("pc.alice")
        assert zone.is_discovered_by("pc.alice")

    def test_discovery_with_legacy_list_format(self):
        """Test that discovery data can be loaded from list format."""
        # Create zone with discovered_by as list (for JSON compatibility)
        zone_data = {
            "id": "test_zone",
            "name": "Test Zone",
            "discovered_by": ["pc.alice", "pc.bob"],  # List instead of set
        }

        zone = Zone(**zone_data)

        # Should convert to set automatically
        assert isinstance(zone.discovered_by, set)
        assert zone.discovered_by == {"pc.alice", "pc.bob"}
        assert zone.is_discovered_by("pc.alice")
        assert zone.is_discovered_by("pc.bob")


class TestZoneDiscoveryEdgeCases:
    """Test edge cases and error conditions for zone discovery."""

    def test_discovery_with_gm_only_zones(self):
        """Test that GM-only zones are handled correctly in discovery."""
        gm_zone = Zone(id="gm_zone", name="GM Zone")
        gm_zone.meta.gm_only = True

        world = GameState(zones={"gm_zone": gm_zone}, entities={}, scene=Scene())

        # Manual discovery should still work (for GM tools)
        assert discover_zone("pc.alice", "gm_zone", world)
        assert is_zone_discovered("pc.alice", "gm_zone", world)

        # But GM zones should be marked as hidden in discovery map
        discovery_map = get_zone_discovery_map("pc.alice", world)
        assert discovery_map["gm_zone"] == "hidden"

    def test_discovery_with_empty_world(self):
        """Test discovery functions with empty world."""
        empty_world = GameState(zones={}, entities={}, scene=Scene())

        assert not discover_zone("pc.alice", "nonexistent", empty_world)
        assert not is_zone_discovered("pc.alice", "nonexistent", empty_world)
        assert get_discovered_zones("pc.alice", empty_world) == []
        assert (
            get_undiscovered_adjacent_zones("pc.alice", "nonexistent", empty_world)
            == []
        )
        assert get_zone_discovery_map("pc.alice", empty_world) == {}


if __name__ == "__main__":
    pytest.main([__file__])
