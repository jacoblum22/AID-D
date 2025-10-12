"""
Test suite for Zone Hierarchies & Regional Grouping.

This module tests the regional organization system including zone grouping,
regional analysis, connectivity scoring, and automated assignment suggestions.
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
    zones_in_region,
    get_all_regions,
    get_region_summary,
    find_inter_region_connections,
    set_zone_regions,
    find_zones_by_region_pattern,
    get_region_connectivity_score,
    suggest_region_assignments,
)
from models.space import Exit
from models.meta import Meta


class TestZoneRegionalMethods:
    """Test Zone model regional functionality."""

    def test_set_region(self):
        """Test setting and changing zone regions."""
        zone = Zone(id="test", name="Test Zone")

        # Initially no region
        assert zone.region is None
        assert zone.get_region_display_name() == "Unassigned"

        # Set region
        zone.set_region("forest")
        assert zone.region == "forest"
        assert zone.get_region_display_name() == "forest"
        assert zone.is_in_region("forest")
        assert not zone.is_in_region("mountain")

        # Change region
        zone.set_region("mountain")
        assert zone.region == "mountain"
        assert zone.is_in_region("mountain")
        assert not zone.is_in_region("forest")

        # Clear region
        zone.set_region(None)
        assert zone.region is None
        assert zone.get_region_display_name() == "Unassigned"

    def test_add_exit_with_region(self):
        """Test adding exits with region parameter."""
        zone = Zone(id="test", name="Test Zone")

        # Add exit with region assignment
        exit = zone.add_exit("target", direction="north", region="forest")
        assert zone.region == "forest"
        assert exit.to == "target"
        assert exit.direction == "north"


class TestRegionalGrouping:
    """Test regional grouping functionality."""

    @pytest.fixture
    def regional_world(self):
        """Create a world with multiple regions for testing."""
        zones = {
            # Forest region
            "forest_entrance": Zone(
                id="forest_entrance", name="Forest Entrance", region="forest"
            ),
            "deep_woods": Zone(id="deep_woods", name="Deep Woods", region="forest"),
            "forest_clearing": Zone(
                id="forest_clearing", name="Forest Clearing", region="forest"
            ),
            # Mountain region
            "mountain_base": Zone(
                id="mountain_base", name="Mountain Base", region="mountain"
            ),
            "mountain_peak": Zone(
                id="mountain_peak", name="Mountain Peak", region="mountain"
            ),
            # Town region
            "town_square": Zone(id="town_square", name="Town Square", region="town"),
            "inn": Zone(id="inn", name="The Prancing Pony", region="town"),
            # Unassigned zones
            "mysterious_cave": Zone(id="mysterious_cave", name="Mysterious Cave"),
            "ancient_ruins": Zone(id="ancient_ruins", name="Ancient Ruins"),
        }

        # Add some tags for testing
        zones["forest_entrance"].add_tag("outdoor")
        zones["deep_woods"].add_tag("outdoor")
        zones["deep_woods"].add_tag("dark")
        zones["forest_clearing"].add_tag("outdoor")
        zones["mountain_base"].add_tag("outdoor")
        zones["mountain_peak"].add_tag("outdoor")
        zones["mountain_peak"].add_tag("cold")
        zones["town_square"].add_tag("safe")
        zones["inn"].add_tag("safe")
        zones["inn"].add_tag("warm")
        zones["mysterious_cave"].add_tag("dark")
        zones["ancient_ruins"].add_tag("mysterious")

        # Set up connections
        # Forest internal connections
        zones["forest_entrance"].add_exit("deep_woods", direction="north")
        zones["deep_woods"].add_exit("forest_entrance", direction="south")
        zones["deep_woods"].add_exit("forest_clearing", direction="east")
        zones["forest_clearing"].add_exit("deep_woods", direction="west")

        # Mountain internal connection
        zones["mountain_base"].add_exit("mountain_peak", direction="up")
        zones["mountain_peak"].add_exit("mountain_base", direction="down")

        # Town internal connection
        zones["town_square"].add_exit("inn", direction="north")
        zones["inn"].add_exit("town_square", direction="south")

        # Inter-region connections
        zones["forest_entrance"].add_exit("town_square", direction="west", cost=2.0)
        zones["town_square"].add_exit("forest_entrance", direction="east", cost=2.0)
        zones["town_square"].add_exit("mountain_base", direction="north", cost=3.0)
        zones["mountain_base"].add_exit("town_square", direction="south", cost=3.0)

        # Connections to unassigned zones
        zones["forest_clearing"].add_exit("mysterious_cave", direction="down")
        zones["mysterious_cave"].add_exit("forest_clearing", direction="up")
        zones["mountain_peak"].add_exit("ancient_ruins", direction="east")
        zones["ancient_ruins"].add_exit("mountain_peak", direction="west")

        entities: Dict[str, Entity] = {
            "pc.explorer": PC(
                id="pc.explorer",
                name="Explorer",
                type="pc",
                current_zone="town_square",
                hp=HP(current=20, max=20),
            )
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    def test_zones_in_region(self, regional_world):
        """Test finding zones in a specific region."""
        forest_zones = zones_in_region("forest", regional_world)
        assert len(forest_zones) == 3
        forest_ids = [zone.id for zone in forest_zones]
        assert "forest_entrance" in forest_ids
        assert "deep_woods" in forest_ids
        assert "forest_clearing" in forest_ids

        mountain_zones = zones_in_region("mountain", regional_world)
        assert len(mountain_zones) == 2
        mountain_ids = [zone.id for zone in mountain_zones]
        assert "mountain_base" in mountain_ids
        assert "mountain_peak" in mountain_ids

        # Non-existent region
        empty_zones = zones_in_region("desert", regional_world)
        assert len(empty_zones) == 0

    def test_get_all_regions(self, regional_world):
        """Test getting list of all regions."""
        regions = get_all_regions(regional_world)
        assert regions == ["forest", "mountain", "town"]  # Sorted

    def test_get_region_summary(self, regional_world):
        """Test comprehensive region summary."""
        summary = get_region_summary(regional_world)

        # Check forest region
        forest_summary = summary["forest"]
        assert forest_summary["zone_count"] == 3
        assert set(forest_summary["zone_ids"]) == {
            "forest_entrance",
            "deep_woods",
            "forest_clearing",
        }
        assert forest_summary["internal_exits"] == 4  # 2 bidirectional connections
        assert (
            forest_summary["external_exits"] == 2
        )  # to town + to cave (outgoing only)
        assert "outdoor" in forest_summary["common_tags"]
        assert "dark" in forest_summary["common_tags"]

        # Check town region
        town_summary = summary["town"]
        assert town_summary["zone_count"] == 2
        assert town_summary["internal_exits"] == 2  # bidirectional town square <-> inn
        assert (
            town_summary["external_exits"] == 2
        )  # to forest + to mountain (outgoing only)

        # Check unassigned zones
        unassigned_summary = summary["Unassigned"]
        assert unassigned_summary["zone_count"] == 2
        assert set(unassigned_summary["zone_ids"]) == {
            "mysterious_cave",
            "ancient_ruins",
        }
        assert (
            unassigned_summary["internal_exits"] == 0
        )  # No connections between unassigned zones
        assert (
            unassigned_summary["external_exits"] == 2
        )  # Each connects back to assigned zones (outgoing only)

    def test_find_inter_region_connections(self, regional_world):
        """Test finding connections between regions."""
        connections = find_inter_region_connections(regional_world)

        # Check forest <-> town connection
        forest_town_key = "forest <-> town"
        assert forest_town_key in connections
        ft_connections = connections[forest_town_key]
        assert len(ft_connections) == 2  # Bidirectional

        # Verify connection details
        connection_zones = [(c["from_zone"], c["to_zone"]) for c in ft_connections]
        assert ("forest_entrance", "town_square") in connection_zones
        assert ("town_square", "forest_entrance") in connection_zones

        # Check mountain <-> town connection
        mountain_town_key = "mountain <-> town"
        assert mountain_town_key in connections

        # Check connections to unassigned zones
        forest_unassigned_key = "Unassigned <-> forest"
        assert forest_unassigned_key in connections

    def test_set_zone_regions(self, regional_world):
        """Test bulk region assignment."""
        mapping = {
            "mysterious_cave": "underground",
            "ancient_ruins": "underground",
            "nonexistent_zone": "underground",
        }

        results = set_zone_regions(mapping, regional_world)

        assert results["mysterious_cave"] is True
        assert results["ancient_ruins"] is True
        assert results["nonexistent_zone"] is False

        # Verify assignments
        assert regional_world.zones["mysterious_cave"].region == "underground"
        assert regional_world.zones["ancient_ruins"].region == "underground"

    def test_find_zones_by_region_pattern(self, regional_world):
        """Test pattern-based region searching."""
        # Exact match
        forest_zones = find_zones_by_region_pattern("forest", regional_world)
        assert len(forest_zones) == 3

        # Wildcard match
        all_zones = find_zones_by_region_pattern("*", regional_world)
        assert len(all_zones) == 7  # All zones with regions

        # Pattern match
        outdoor_regions = find_zones_by_region_pattern(
            "*o*", regional_world
        )  # forest, mountain, town
        assert len(outdoor_regions) == 7

        # No match
        no_match = find_zones_by_region_pattern("desert*", regional_world)
        assert len(no_match) == 0

    def test_get_region_connectivity_score(self, regional_world):
        """Test region connectivity scoring."""
        # Forest region has good internal + external connectivity
        forest_score = get_region_connectivity_score("forest", regional_world)
        assert 0.5 < forest_score < 1.0  # Mixed internal/external

        # Town region is a hub (more external connections)
        town_score = get_region_connectivity_score("town", regional_world)
        assert town_score > 0.0

        # Non-existent region
        none_score = get_region_connectivity_score("desert", regional_world)
        assert none_score == 0.0

    def test_suggest_region_assignments(self, regional_world):
        """Test automated region assignment suggestions."""
        suggestions = suggest_region_assignments(
            regional_world, similarity_threshold=0.3
        )

        # Should have suggestions for unassigned zones
        assert len(suggestions) > 0

        # Check if mysterious_cave is suggested for forest (connected + has 'dark' tag like deep_woods)
        suggested_zones = []
        for region, zone_ids in suggestions.items():
            suggested_zones.extend(zone_ids)

        # At least one unassigned zone should get a suggestion
        unassigned_zones = ["mysterious_cave", "ancient_ruins"]
        has_suggestion = any(zone in suggested_zones for zone in unassigned_zones)
        assert has_suggestion


class TestRegionalGroupingIntegration:
    """Test integration of regional grouping with other zone graph features."""

    def test_regional_grouping_with_discovery(self):
        """Test that regional grouping works with discovery tracking."""
        zones = {
            "start": Zone(id="start", name="Start", region="town"),
            "hidden": Zone(id="hidden", name="Hidden", region="forest"),
        }

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Test region queries
        town_zones = zones_in_region("town", world)
        forest_zones = zones_in_region("forest", world)

        assert len(town_zones) == 1
        assert len(forest_zones) == 1
        assert town_zones[0].id == "start"
        assert forest_zones[0].id == "hidden"

    def test_regional_grouping_with_pathfinding(self):
        """Test that regional grouping works with cost-based pathfinding."""
        zones = {
            "town_a": Zone(id="town_a", name="Town A", region="town"),
            "town_b": Zone(id="town_b", name="Town B", region="town"),
            "forest": Zone(id="forest", name="Forest", region="wilderness"),
        }

        # Set up connections
        zones["town_a"].add_exit("town_b", cost=1.0)
        zones["town_a"].add_exit("forest", cost=5.0)  # Expensive
        zones["forest"].add_exit("town_b", cost=1.0)

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Test pathfinding within region
        from backend.router.zone_graph import find_lowest_cost_path

        result = find_lowest_cost_path("town_a", "town_b", world)
        assert result is not None
        path, cost = result
        assert path == ["town_a", "town_b"]
        assert cost == 1.0

        # Test region analysis
        town_zones = zones_in_region("town", world)
        assert len(town_zones) == 2

    def test_regional_summary_with_events(self):
        """Test that regional summaries work with zone graph events."""
        zones = {
            "gate": Zone(id="gate", name="Gate", region="town"),
            "field": Zone(id="field", name="Field", region="countryside"),
        }

        zones["gate"].add_exit("field", blocked=True)  # Initially blocked

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Check initial summary
        summary = get_region_summary(world)
        town_summary = summary["town"]
        assert town_summary["external_exits"] == 1  # Blocked exit still counts

        # Unblock exit using events
        from backend.router.zone_graph import unblock_exit

        unblock_exit("gate", "field", world, cause="quest_completed")

        # Summary should still show the connection
        summary = get_region_summary(world)
        town_summary = summary["town"]
        assert town_summary["external_exits"] == 1


if __name__ == "__main__":
    pytest.main([__file__])
