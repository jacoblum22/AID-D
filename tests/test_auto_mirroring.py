"""
Test suite for Exit Auto-Mirroring Utility.

This module tests the bidirectional exit generation system including
automatic reciprocal creation, consistency validation, and error fixing.
"""

import pytest
from typing import Dict, Any, List
import sys
import os

# Add project root to path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import GameState, Zone, PC, Scene, HP, Entity
from backend.router.zone_graph import (
    ensure_bidirectional_links,
    validate_bidirectional_consistency,
    fix_bidirectional_inconsistencies,
    create_bidirectional_exit,
    _get_reciprocal_direction,
    _generate_reciprocal_label,
)
from models.space import Exit
from models.meta import Meta


class TestReciprocalDirections:
    """Test reciprocal direction calculation."""

    def test_get_reciprocal_direction_basic(self):
        """Test basic directional opposites."""
        assert _get_reciprocal_direction("north") == "south"
        assert _get_reciprocal_direction("south") == "north"
        assert _get_reciprocal_direction("east") == "west"
        assert _get_reciprocal_direction("west") == "east"
        assert _get_reciprocal_direction("up") == "down"
        assert _get_reciprocal_direction("down") == "up"

    def test_get_reciprocal_direction_advanced(self):
        """Test advanced directional opposites."""
        assert _get_reciprocal_direction("northeast") == "southwest"
        assert _get_reciprocal_direction("northwest") == "southeast"
        assert _get_reciprocal_direction("southeast") == "northwest"
        assert _get_reciprocal_direction("southwest") == "northeast"
        assert _get_reciprocal_direction("in") == "out"
        assert _get_reciprocal_direction("out") == "in"
        assert _get_reciprocal_direction("forward") == "back"
        assert _get_reciprocal_direction("back") == "forward"

    def test_get_reciprocal_direction_edge_cases(self):
        """Test edge cases for reciprocal directions."""
        assert _get_reciprocal_direction(None) is None
        assert _get_reciprocal_direction("") is None
        assert _get_reciprocal_direction("unknown_direction") is None

        # Test case insensitivity
        assert _get_reciprocal_direction("NORTH") == "south"
        assert _get_reciprocal_direction("North") == "south"

    def test_generate_reciprocal_label(self):
        """Test reciprocal label generation."""
        # No original label
        assert _generate_reciprocal_label(None, "south") == "south"
        assert _generate_reciprocal_label("", "south") == "south"

        # Direction in label
        assert _generate_reciprocal_label("North Gate", "south") == "South Gate"
        assert _generate_reciprocal_label("Upstairs", "down") == "Downstairs"
        assert _generate_reciprocal_label("Main Entrance", "out") == "Main Exit"

        # No direction in label
        assert _generate_reciprocal_label("Secret Door", "west") == "west"
        assert _generate_reciprocal_label("Ancient Portal", None) is None


class TestEnsureBidirectionalLinks:
    """Test automatic bidirectional link creation."""

    @pytest.fixture
    def unidirectional_world(self):
        """Create a world with missing reciprocal exits."""
        zones = {
            "hall": Zone(id="hall", name="Great Hall"),
            "kitchen": Zone(id="kitchen", name="Kitchen"),
            "library": Zone(id="library", name="Library"),
            "garden": Zone(id="garden", name="Garden"),
            "missing": Zone(
                id="missing", name="Missing Target"
            ),  # Target for broken exit
        }

        # Create some unidirectional exits
        zones["hall"].add_exit(
            "kitchen", direction="north", label="To Kitchen", cost=1.0
        )
        zones["hall"].add_exit(
            "library", direction="east", label="To Library", cost=2.0, terrain="stairs"
        )
        zones["garden"].add_exit(
            "hall", direction="north", label="To Hall"
        )  # This one has reciprocal
        zones["hall"].add_exit(
            "garden", direction="south", label="To Garden"
        )  # Reciprocal exists

        # Create exit to non-existent zone for testing error handling
        zones["hall"].add_exit("nonexistent", direction="west", label="Broken Exit")

        return GameState(zones=zones, entities={}, scene=Scene())

    def test_ensure_bidirectional_links_dry_run(self, unidirectional_world):
        """Test dry run analysis without making changes."""
        results = ensure_bidirectional_links(unidirectional_world, dry_run=True)

        # Should analyze all exits
        assert (
            results["analyzed_exits"] == 5
        )  # hall->kitchen, hall->library, garden->hall, hall->garden, hall->nonexistent

        # Should find missing reciprocals
        assert len(results["missing_reciprocals"]) == 2  # kitchen->hall, library->hall

        # Should not create any exits in dry run
        assert len(results["created_exits"]) == 0

        # Should report error for broken exit
        assert len(results["errors"]) == 1
        assert results["errors"][0]["type"] == "missing_target_zone"
        assert results["errors"][0]["to_zone"] == "nonexistent"

    def test_ensure_bidirectional_links_create(self, unidirectional_world):
        """Test actual reciprocal exit creation."""
        results = ensure_bidirectional_links(unidirectional_world, dry_run=False)

        # Should create reciprocal exits
        assert len(results["created_exits"]) == 2

        # Verify kitchen now has exit back to hall
        kitchen_exits = [
            exit.to for exit in unidirectional_world.zones["kitchen"].exits
        ]
        assert "hall" in kitchen_exits

        # Verify library now has exit back to hall
        library_exits = [
            exit.to for exit in unidirectional_world.zones["library"].exits
        ]
        assert "hall" in library_exits

        # Check that reciprocal direction was calculated correctly
        kitchen_to_hall = None
        for exit in unidirectional_world.zones["kitchen"].exits:
            if exit.to == "hall":
                kitchen_to_hall = exit
                break

        assert kitchen_to_hall is not None
        assert kitchen_to_hall.direction == "south"  # Reciprocal of "north"
        assert kitchen_to_hall.cost == 1.0  # Same cost as original

    def test_ensure_bidirectional_links_preserves_properties(
        self, unidirectional_world
    ):
        """Test that reciprocal exits inherit correct properties."""
        # Create exit with specific properties
        hall = unidirectional_world.zones["hall"]
        hall.add_exit(
            "missing",
            direction="up",
            cost=3.0,
            terrain="rope",
            blocked=True,
            conditions={"requires": "climbing_gear"},
        )

        results = ensure_bidirectional_links(unidirectional_world, dry_run=False)

        # Find the created reciprocal exit
        missing_to_hall = None
        for exit in unidirectional_world.zones["missing"].exits:
            if exit.to == "hall":
                missing_to_hall = exit
                break

        assert missing_to_hall is not None
        assert missing_to_hall.direction == "down"  # Reciprocal of "up"
        assert missing_to_hall.cost == 3.0
        assert missing_to_hall.terrain == "rope"
        assert missing_to_hall.blocked is True
        assert missing_to_hall.conditions == {"requires": "climbing_gear"}


class TestBidirectionalValidation:
    """Test bidirectional consistency validation."""

    @pytest.fixture
    def inconsistent_world(self):
        """Create a world with inconsistent bidirectional exits."""
        zones = {
            "a": Zone(id="a", name="Zone A"),
            "b": Zone(id="b", name="Zone B"),
            "c": Zone(id="c", name="Zone C"),
            "d": Zone(id="d", name="Zone D"),
        }

        # Consistent bidirectional pair
        zones["a"].add_exit("b", cost=2.0, terrain="grass", blocked=False)
        zones["b"].add_exit("a", cost=2.0, terrain="grass", blocked=False)

        # Inconsistent cost
        zones["a"].add_exit("c", cost=1.0, terrain="stone", blocked=False)
        zones["c"].add_exit("a", cost=3.0, terrain="stone", blocked=False)

        # Inconsistent terrain and blocked status
        zones["b"].add_exit("d", cost=1.0, terrain="mud", blocked=True)
        zones["d"].add_exit("b", cost=1.0, terrain="sand", blocked=False)

        return GameState(zones=zones, entities={}, scene=Scene())

    def test_validate_bidirectional_consistency(self, inconsistent_world):
        """Test consistency validation reporting."""
        results = validate_bidirectional_consistency(inconsistent_world)

        assert results["total_bidirectional_pairs"] == 3
        assert results["consistent_pairs"] == 1  # Only a<->b is consistent
        assert len(results["inconsistent_pairs"]) == 2  # a<->c and b<->d

        # Check cost mismatches
        assert len(results["cost_mismatches"]) == 1
        cost_mismatch = results["cost_mismatches"][0]
        assert set([cost_mismatch["zone_a"], cost_mismatch["zone_b"]]) == {"a", "c"}

        # Check terrain mismatches
        assert len(results["terrain_mismatches"]) == 1
        terrain_mismatch = results["terrain_mismatches"][0]
        assert set([terrain_mismatch["zone_a"], terrain_mismatch["zone_b"]]) == {
            "b",
            "d",
        }

        # Check blocked status mismatches
        assert len(results["blocked_mismatches"]) == 1
        blocked_mismatch = results["blocked_mismatches"][0]
        assert set([blocked_mismatch["zone_a"], blocked_mismatch["zone_b"]]) == {
            "b",
            "d",
        }

    def test_fix_bidirectional_inconsistencies_prefer_lower_cost(
        self, inconsistent_world
    ):
        """Test fixing inconsistencies with prefer_lower_cost strategy."""
        results = fix_bidirectional_inconsistencies(
            inconsistent_world, strategy="prefer_lower_cost", dry_run=False
        )

        assert len(results["cost_fixes"]) == 1

        # Verify costs were fixed to lower value
        a_to_c_cost = None
        c_to_a_cost = None

        for exit in inconsistent_world.zones["a"].exits:
            if exit.to == "c":
                a_to_c_cost = exit.cost

        for exit in inconsistent_world.zones["c"].exits:
            if exit.to == "a":
                c_to_a_cost = exit.cost

        assert a_to_c_cost == 1.0  # Lower of 1.0 and 3.0
        assert c_to_a_cost == 1.0

    def test_fix_bidirectional_inconsistencies_average(self, inconsistent_world):
        """Test fixing inconsistencies with average strategy."""
        results = fix_bidirectional_inconsistencies(
            inconsistent_world, strategy="average", dry_run=False
        )

        # Verify costs were fixed to average value
        a_to_c_cost = None
        c_to_a_cost = None

        for exit in inconsistent_world.zones["a"].exits:
            if exit.to == "c":
                a_to_c_cost = exit.cost

        for exit in inconsistent_world.zones["c"].exits:
            if exit.to == "a":
                c_to_a_cost = exit.cost

        expected_average = (1.0 + 3.0) / 2
        assert a_to_c_cost == expected_average
        assert c_to_a_cost == expected_average


class TestCreateBidirectionalExit:
    """Test bidirectional exit creation utility."""

    @pytest.fixture
    def empty_world(self):
        """Create an empty world for testing."""
        zones = {
            "start": Zone(id="start", name="Starting Zone"),
            "end": Zone(id="end", name="Ending Zone"),
        }
        return GameState(zones=zones, entities={}, scene=Scene())

    def test_create_bidirectional_exit_basic(self, empty_world):
        """Test basic bidirectional exit creation."""
        results = create_bidirectional_exit(
            "start",
            "end",
            empty_world,
            direction_a_to_b="north",
            label_a_to_b="To End Zone",
            cost=2.0,
            terrain="grass",
        )

        assert results["success"] is True
        assert len(results["created_exits"]) == 2
        assert len(results["errors"]) == 0

        # Verify start->end exit
        start_exits = [
            exit for exit in empty_world.zones["start"].exits if exit.to == "end"
        ]
        assert len(start_exits) == 1
        start_exit = start_exits[0]
        assert start_exit.direction == "north"
        assert start_exit.label == "To End Zone"
        assert start_exit.cost == 2.0
        assert start_exit.terrain == "grass"

        # Verify end->start exit (reciprocal)
        end_exits = [
            exit for exit in empty_world.zones["end"].exits if exit.to == "start"
        ]
        assert len(end_exits) == 1
        end_exit = end_exits[0]
        assert end_exit.direction == "south"  # Reciprocal of north
        assert end_exit.cost == 2.0
        assert end_exit.terrain == "grass"

    def test_create_bidirectional_exit_auto_labels(self, empty_world):
        """Test automatic label generation."""
        results = create_bidirectional_exit(
            "start",
            "end",
            empty_world,
            direction_a_to_b="up",
            label_a_to_b="Upstairs to End",
        )

        assert results["success"] is True

        # Check that reciprocal label was generated
        end_exit = None
        for exit in empty_world.zones["end"].exits:
            if exit.to == "start":
                end_exit = exit
                break

        assert end_exit is not None
        assert end_exit.label == "Downstairs To End"  # Auto-generated reciprocal

    def test_create_bidirectional_exit_errors(self, empty_world):
        """Test error handling in bidirectional exit creation."""
        # Test non-existent zone
        results = create_bidirectional_exit(
            "start", "nonexistent", empty_world, direction_a_to_b="north"
        )

        assert results["success"] is False
        assert len(results["errors"]) == 1
        assert results["errors"][0]["type"] == "missing_target_zone"
        assert results["errors"][0]["to_zone"] == "nonexistent"


class TestAutoMirroringIntegration:
    """Test integration of auto-mirroring with other zone graph features."""

    def test_auto_mirroring_with_discovery(self):
        """Test that auto-mirroring works with discovery tracking."""
        zones = {
            "town": Zone(id="town", name="Town Square"),
            "forest": Zone(id="forest", name="Forest Entrance"),
        }

        # Create unidirectional exit
        zones["town"].add_exit("forest", direction="east")

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Ensure bidirectional links
        results = ensure_bidirectional_links(world, dry_run=False)
        assert len(results["created_exits"]) == 1  # Should create one reciprocal exit

        # Test discovery on both zones
        zones["town"].discover_by("pc.explorer")
        zones["forest"].discover_by("pc.explorer")

        assert zones["town"].is_discovered_by("pc.explorer")
        assert zones["forest"].is_discovered_by("pc.explorer")

    def test_auto_mirroring_with_events(self):
        """Test that auto-mirroring works with zone graph events."""
        zones = {
            "castle": Zone(id="castle", name="Castle Gate"),
            "courtyard": Zone(id="courtyard", name="Courtyard"),
        }

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Create bidirectional exit
        create_bidirectional_exit(
            "castle", "courtyard", world, direction_a_to_b="north", blocked=False
        )

        # Test blocking exit using events
        from backend.router.zone_graph import block_exit

        block_exit(
            "castle",
            "courtyard",
            world,
            cause="siege",
            reason="Gates sealed during siege!",
        )

        # Both directions should be blocked
        castle_exit = None
        for exit in zones["castle"].exits:
            if exit.to == "courtyard":
                castle_exit = exit
                break

        assert castle_exit is not None
        assert castle_exit.blocked is True

    def test_auto_mirroring_with_pathfinding(self):
        """Test that auto-mirroring works with cost-based pathfinding."""
        zones = {
            "start": Zone(id="start", name="Start"),
            "middle": Zone(id="middle", name="Middle"),
            "goal": Zone(id="goal", name="Goal"),
        }

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Create bidirectional exits with costs
        create_bidirectional_exit("start", "middle", world, cost=2.0)
        create_bidirectional_exit("middle", "goal", world, cost=1.0)

        # Test pathfinding uses reciprocal exits
        from backend.router.zone_graph import find_lowest_cost_path

        # Forward path
        result = find_lowest_cost_path("start", "goal", world)
        assert result is not None
        path, cost = result
        assert path == ["start", "middle", "goal"]
        assert cost == 3.0

        # Reverse path (using reciprocal exits)
        result = find_lowest_cost_path("goal", "start", world)
        assert result is not None
        path, cost = result
        assert path == ["goal", "middle", "start"]
        assert cost == 3.0


if __name__ == "__main__":
    pytest.main([__file__])
