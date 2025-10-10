"""
Test suite for Cost-Based Pathfinding with Terrain Support.

This module tests the enhanced pathfinding system including terrain costs,
Dijkstra's algorithm, multiple path finding, and actor-specific modifiers.
"""

import pytest
from typing import Dict, Any, List, Tuple
import sys
import os

# Add project root to path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import GameState, Zone, PC, Scene, HP, Entity
from backend.router.zone_graph import (
    find_lowest_cost_path,
    find_multiple_paths,
    calculate_path_cost,
    get_reachable_zones_with_cost,
    get_terrain_modifiers_template,
)
from models.space import Exit
from models.meta import Meta


class TestExitCostCalculation:
    """Test Exit model cost calculation methods."""

    def test_basic_cost_calculation(self):
        """Test basic movement cost without modifiers."""
        # Default cost
        exit = Exit(to="target", cost=1.0)
        assert exit.get_movement_cost() == 1.0

        # Custom cost
        exit = Exit(to="target", cost=2.5)
        assert exit.get_movement_cost() == 2.5

        # Minimum cost enforcement
        exit = Exit(to="target", cost=0.0)
        assert exit.get_movement_cost() == 0.1

    def test_terrain_cost_modifiers(self):
        """Test terrain-based cost modifiers."""
        # Setup terrain modifiers
        terrain_mods = {
            "mud": {
                "light_step": 0.5,
                "heavy_armor": 2.0,
            },
            "stairs": {
                "climbing": 0.5,
            },
        }

        # Create mock actor with tags
        class MockActor:
            def __init__(self, tags):
                self.tags = tags

        # Test mud terrain with light step
        exit = Exit(to="target", cost=2.0, terrain="mud")
        actor = MockActor({"light_step": True})
        cost = exit.get_movement_cost(actor, terrain_mods)
        assert cost == 1.0  # 2.0 * 0.5

        # Test mud terrain with heavy armor
        actor = MockActor({"heavy_armor": True})
        cost = exit.get_movement_cost(actor, terrain_mods)
        assert cost == 4.0  # 2.0 * 2.0

        # Test stairs with climbing ability
        exit = Exit(to="target", cost=1.0, terrain="stairs")
        actor = MockActor({"climbing": True})
        cost = exit.get_movement_cost(actor, terrain_mods)
        assert cost == 0.5  # 1.0 * 0.5

        # Test unknown terrain - no modifier
        exit = Exit(to="target", cost=1.0, terrain="unknown")
        actor = MockActor({"light_step": True})
        cost = exit.get_movement_cost(actor, terrain_mods)
        assert cost == 1.0  # No modifier applied

        # Test no terrain - no modifier
        exit = Exit(to="target", cost=1.0, terrain=None)
        actor = MockActor({"light_step": True})
        cost = exit.get_movement_cost(actor, terrain_mods)
        assert cost == 1.0  # No modifier applied

    def test_terrain_descriptions(self):
        """Test terrain description generation."""
        exit = Exit(to="target", terrain="mud")
        assert exit.get_terrain_description() == "muddy ground"

        exit = Exit(to="target", terrain="stairs")
        assert exit.get_terrain_description() == "steep stairs"

        exit = Exit(to="target", terrain="unknown_terrain")
        assert exit.get_terrain_description() == "unknown_terrain terrain"

        exit = Exit(to="target", terrain=None)
        assert exit.get_terrain_description() == ""


class TestCostBasedPathfinding:
    """Test cost-based pathfinding algorithms."""

    @pytest.fixture
    def cost_world(self):
        """Create a world for testing cost-based pathfinding."""
        zones = {
            "start": Zone(id="start", name="Start"),
            "mud_path": Zone(id="mud_path", name="Muddy Path"),
            "stairs": Zone(id="stairs", name="Steep Stairs"),
            "goal": Zone(id="goal", name="Goal"),
            "alternative": Zone(id="alternative", name="Alternative"),
        }

        # Set up cost-based exits
        # Route 1: start -> mud_path -> goal (cost: 1.0 + 3.0 = 4.0)
        zones["start"].add_exit("mud_path", cost=1.0, terrain="normal")
        zones["mud_path"].add_exit("goal", cost=3.0, terrain="mud")

        # Route 2: start -> stairs -> goal (cost: 2.0 + 1.5 = 3.5)
        zones["start"].add_exit("stairs", cost=2.0, terrain="stairs")
        zones["stairs"].add_exit("goal", cost=1.5, terrain="normal")

        # Route 3: start -> alternative -> goal (cost: 1.0 + 1.0 = 2.0 - cheapest)
        zones["start"].add_exit("alternative", cost=1.0, terrain="normal")
        zones["alternative"].add_exit("goal", cost=1.0, terrain="normal")

        # Add reverse exits for bidirectional movement
        zones["mud_path"].add_exit("start", cost=1.0, terrain="normal")
        zones["stairs"].add_exit("start", cost=2.0, terrain="stairs")
        zones["alternative"].add_exit("start", cost=1.0, terrain="normal")
        zones["goal"].add_exit("mud_path", cost=3.0, terrain="mud")
        zones["goal"].add_exit("stairs", cost=1.5, terrain="normal")
        zones["goal"].add_exit("alternative", cost=1.0, terrain="normal")

        entities: Dict[str, Entity] = {
            "pc.climber": PC(
                id="pc.climber",
                name="Climber",
                type="pc",
                current_zone="start",
                hp=HP(current=20, max=20),
                tags={"climbing": True},  # Good at climbing
            ),
            "pc.heavy": PC(
                id="pc.heavy",
                name="Heavy Warrior",
                type="pc",
                current_zone="start",
                hp=HP(current=30, max=30),
                tags={"heavy_armor": True},  # Slow in mud
            ),
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    @pytest.fixture
    def terrain_modifiers(self):
        """Terrain modifier configuration for testing."""
        return {
            "mud": {
                "light_step": 0.5,
                "heavy_armor": 2.0,
            },
            "stairs": {
                "climbing": 0.5,
                "heavy_armor": 1.5,
            },
        }

    def test_find_lowest_cost_path_basic(self, cost_world):
        """Test basic lowest cost path finding without modifiers."""
        # Should find alternative route (cost 2.0)
        result = find_lowest_cost_path("start", "goal", cost_world)
        assert result is not None
        path, cost = result
        assert path == ["start", "alternative", "goal"]
        assert cost == 2.0

    def test_find_lowest_cost_path_with_actor_modifiers(
        self, cost_world, terrain_modifiers
    ):
        """Test pathfinding with actor-specific terrain modifiers."""
        climber = cost_world.entities["pc.climber"]
        heavy = cost_world.entities["pc.heavy"]

        # Climber should prefer stairs route due to climbing ability
        result = find_lowest_cost_path(
            "start", "goal", cost_world, climber, terrain_modifiers
        )
        assert result is not None
        path, cost = result
        # Alternative route still cheapest: 1.0 + 1.0 = 2.0
        # Stairs route with climbing: 2.0 + (1.5 * 0.5) = 2.75
        assert path == ["start", "alternative", "goal"]
        assert cost == 2.0

        # Heavy warrior should definitely avoid mud
        result = find_lowest_cost_path(
            "start", "goal", cost_world, heavy, terrain_modifiers
        )
        assert result is not None
        path, cost = result
        # Alternative route: 1.0 + 1.0 = 2.0 (still cheapest)
        # Mud route with heavy armor: 1.0 + (3.0 * 2.0) = 7.0
        # Stairs route with heavy armor: 2.0 * 1.5 + 1.5 = 4.5
        assert path == ["start", "alternative", "goal"]
        assert cost == 2.0

    def test_find_lowest_cost_path_no_path(self, cost_world):
        """Test pathfinding when no path exists."""
        # Add isolated zone
        cost_world.zones["isolated"] = Zone(id="isolated", name="Isolated")

        result = find_lowest_cost_path("start", "isolated", cost_world)
        assert result is None

    def test_find_lowest_cost_path_max_cost_limit(self, cost_world):
        """Test pathfinding with cost limits."""
        # Set very low cost limit
        result = find_lowest_cost_path("start", "goal", cost_world, max_cost=1.5)
        assert result is None  # No path under cost limit

        # Set reasonable cost limit
        result = find_lowest_cost_path("start", "goal", cost_world, max_cost=5.0)
        assert result is not None
        path, cost = result
        assert cost <= 5.0

    def test_find_multiple_paths(self, cost_world):
        """Test finding multiple paths sorted by cost."""
        paths = find_multiple_paths("start", "goal", cost_world, max_paths=3)

        assert len(paths) >= 1  # Should find at least 1 path

        # Paths should be sorted by cost
        for i in range(len(paths) - 1):
            assert paths[i][1] <= paths[i + 1][1]

        # Should include the optimal path
        optimal_path, optimal_cost = paths[0]
        assert optimal_path == ["start", "alternative", "goal"]
        assert optimal_cost == 2.0

        # If multiple paths found, verify they're different
        if len(paths) > 1:
            assert paths[0][0] != paths[1][0]  # Different paths

    def test_calculate_path_cost(self, cost_world, terrain_modifiers):
        """Test path cost calculation."""
        # Basic path cost
        path = ["start", "alternative", "goal"]
        cost = calculate_path_cost(path, cost_world)
        assert cost == 2.0

        # Path cost with actor modifiers
        heavy = cost_world.entities["pc.heavy"]
        path = ["start", "mud_path", "goal"]
        cost = calculate_path_cost(path, cost_world, heavy, terrain_modifiers)
        assert cost == 7.0  # 1.0 + (3.0 * 2.0) = 7.0

        # Invalid path
        invalid_path = ["start", "nonexistent", "goal"]
        cost = calculate_path_cost(invalid_path, cost_world)
        assert cost == float("inf")

        # Single zone path
        single_path = ["start"]
        cost = calculate_path_cost(single_path, cost_world)
        assert cost == 0.0

    def test_get_reachable_zones_with_cost(self, cost_world, terrain_modifiers):
        """Test getting reachable zones within cost budget."""
        # Basic reachability
        reachable = get_reachable_zones_with_cost("start", cost_world, max_cost=2.0)

        assert "start" in reachable
        assert reachable["start"] == 0.0
        assert "alternative" in reachable
        assert reachable["alternative"] == 1.0
        # Goal should be reachable via alternative
        assert "goal" in reachable
        assert reachable["goal"] == 2.0

        # Test with actor modifiers
        heavy = cost_world.entities["pc.heavy"]
        reachable = get_reachable_zones_with_cost(
            "start", cost_world, heavy, terrain_modifiers, max_cost=5.0
        )

        # Heavy warrior should still reach goal via alternative route
        assert "goal" in reachable
        assert reachable["goal"] == 2.0

        # But mud_path should be more expensive
        if "mud_path" in reachable:
            assert (
                reachable["mud_path"] == 1.0
            )  # Getting to mud_path is still normal cost


class TestTerrainModifiersTemplate:
    """Test terrain modifiers template functionality."""

    def test_get_terrain_modifiers_template(self):
        """Test that terrain modifiers template is complete and valid."""
        template = get_terrain_modifiers_template()

        # Check that common terrain types are included
        expected_terrains = [
            "stairs",
            "mud",
            "fire",
            "water",
            "ice",
            "thorns",
            "sand",
            "rubble",
            "swamp",
            "lava",
        ]

        for terrain in expected_terrains:
            assert terrain in template
            assert isinstance(template[terrain], dict)
            assert len(template[terrain]) > 0

        # Check that modifiers are reasonable
        for terrain, modifiers in template.items():
            for modifier_name, multiplier in modifiers.items():
                assert isinstance(multiplier, (int, float))
                assert multiplier > 0  # Costs should be positive
                assert multiplier <= 50.0  # Reasonable upper bound


class TestCostPathfindingIntegration:
    """Test integration of cost-based pathfinding with other systems."""

    def test_pathfinding_with_blocked_exits(self):
        """Test that blocked exits are properly handled in cost pathfinding."""
        zones = {
            "start": Zone(id="start", name="Start"),
            "middle": Zone(id="middle", name="Middle"),
            "goal": Zone(id="goal", name="Goal"),
        }

        # Create path with blocked exit
        zones["start"].add_exit("middle", cost=1.0)
        zones["middle"].add_exit("goal", cost=1.0, blocked=True)  # Blocked!
        zones["start"].add_exit("goal", cost=5.0)  # Expensive direct route

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Should take expensive direct route
        result = find_lowest_cost_path("start", "goal", world)
        assert result is not None
        path, cost = result
        assert path == ["start", "goal"]
        assert cost == 5.0

        # With allow_blocked, should take cheaper blocked route
        result = find_lowest_cost_path("start", "goal", world, allow_blocked=True)
        assert result is not None
        path, cost = result
        assert path == ["start", "middle", "goal"]
        assert cost == 2.0

    def test_pathfinding_with_discovery_system(self):
        """Test that cost pathfinding works with discovery tracking."""
        zones = {
            "start": Zone(id="start", name="Start"),
            "secret": Zone(id="secret", name="Secret Room"),
            "goal": Zone(id="goal", name="Goal"),
        }

        # Create exits
        zones["start"].add_exit("secret", cost=1.0)
        zones["secret"].add_exit("goal", cost=1.0)
        zones["start"].add_exit("goal", cost=10.0)  # Expensive direct

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Path should prefer secret room route
        result = find_lowest_cost_path("start", "goal", world)
        assert result is not None
        path, cost = result
        assert path == ["start", "secret", "goal"]
        assert cost == 2.0

        # Discovery tracking should work with found path
        from backend.router.zone_graph import discover_zone

        assert discover_zone("pc.test", "secret", world)
        assert discover_zone("pc.test", "goal", world)


if __name__ == "__main__":
    pytest.main([__file__])
