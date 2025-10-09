"""
Tests for the Auto-Reveal System - Visibility Events & Auto-Reveal functionality.

Tests automatic discovery mechanics when actors enter zones, ensuring exploration
feels alive and reduces manual bookkeeping.
"""

import pytest
from typing import Dict, cast
from backend.router.game_state import GameState, PC, NPC, Zone, Scene, HP, Meta, Entity
from backend.router.auto_reveal import (
    auto_reveal_on_zone_entry,
    auto_reveal_zone_entities,
    check_mutual_discovery,
    get_discoverable_entities,
    trigger_exploration_events,
)
from backend.router.effects import apply_position


class TestAutoRevealBasics:
    """Test basic auto-reveal functionality."""

    @pytest.fixture
    def basic_exploration_state(self):
        """Create a game state for testing basic exploration."""
        entities: Dict[str, Entity] = {
            "pc.explorer": PC(
                id="pc.explorer",
                name="Explorer",
                current_zone="start_zone",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public"),
            ),
            "npc.guard": NPC(
                id="npc.guard",
                name="Guard",
                current_zone="treasure_room",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="public"),
            ),
            "npc.hidden_scout": NPC(
                id="npc.hidden_scout",
                name="Hidden Scout",
                current_zone="treasure_room",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="hidden", known_by=set()),
            ),
        }

        zones = {
            "start_zone": Zone(
                id="start_zone",
                name="Starting Area",
                description="A simple starting location",
                adjacent_zones=["treasure_room"],
            ),
            "treasure_room": Zone(
                id="treasure_room",
                name="Treasure Room",
                description="A room filled with treasure",
                adjacent_zones=["start_zone"],
            ),
        }

        return GameState(entities=entities, zones=zones, scene=Scene())

    def test_auto_reveal_public_entities(self, basic_exploration_state):
        """Test that public entities are auto-revealed when entering a zone."""
        result = auto_reveal_on_zone_entry(
            basic_exploration_state, "pc.explorer", "treasure_room"
        )

        # Should discover the public guard
        assert "npc.guard" in result["discovered"]
        assert len(result["discovered"]) == 1

        # Hidden entities should not be auto-revealed
        assert "npc.hidden_scout" not in result["discovered"]

        # Verify the guard now knows about the explorer
        guard = basic_exploration_state.entities["npc.guard"]
        assert "pc.explorer" in guard.meta.known_by

    def test_auto_reveal_hidden_entities_with_knowledge(self, basic_exploration_state):
        """Test that hidden entities are revealed if already known."""
        # Make the hidden scout known to the explorer
        scout = basic_exploration_state.entities["npc.hidden_scout"]
        updated_meta = scout.meta.model_copy(deep=True)
        updated_meta.known_by.add("pc.explorer")
        updated_scout = scout.model_copy(update={"meta": updated_meta})
        basic_exploration_state.entities["npc.hidden_scout"] = updated_scout

        result = auto_reveal_on_zone_entry(
            basic_exploration_state, "pc.explorer", "treasure_room"
        )

        # Should discover public guard and recognize known hidden scout
        assert "npc.guard" in result["discovered"]
        assert "npc.hidden_scout" in result["already_known"]

    def test_auto_reveal_zone_entities(self, basic_exploration_state):
        """Test revealing all appropriate entities in a zone."""
        revealed = auto_reveal_zone_entities(
            basic_exploration_state, "treasure_room", "pc.explorer"
        )

        # Should reveal only the public guard
        assert revealed == ["npc.guard"]

        # Verify the guard knows about the explorer
        guard = basic_exploration_state.entities["npc.guard"]
        assert "pc.explorer" in guard.meta.known_by

    def test_mutual_discovery(self, basic_exploration_state):
        """Test mutual discovery between two actors."""
        # Move the explorer to the treasure room first
        explorer = basic_exploration_state.entities["pc.explorer"]
        updated_explorer = explorer.model_copy(update={"current_zone": "treasure_room"})
        basic_exploration_state.entities["pc.explorer"] = updated_explorer

        result = check_mutual_discovery(
            basic_exploration_state, "pc.explorer", "npc.guard"
        )

        # Both should discover each other
        assert result["actor1_discovers_actor2"] == True
        assert result["actor2_discovers_actor1"] == True


class TestPositionEffectIntegration:
    """Test integration with position effects from the move tool."""

    @pytest.fixture
    def movement_test_state(self):
        """Create a state for testing movement integration."""
        entities: Dict[str, Entity] = {
            "pc.traveler": PC(
                id="pc.traveler",
                name="Traveler",
                current_zone="forest",
                hp=HP(current=18, max=18),
                meta=Meta(visibility="public"),
            ),
            "npc.wolf": NPC(
                id="npc.wolf",
                name="Forest Wolf",
                current_zone="clearing",
                hp=HP(current=14, max=14),
                meta=Meta(visibility="public"),
            ),
        }

        zones = {
            "forest": Zone(
                id="forest",
                name="Dark Forest",
                description="A dense, dark forest",
                adjacent_zones=["clearing"],
            ),
            "clearing": Zone(
                id="clearing",
                name="Forest Clearing",
                description="A sunny clearing in the forest",
                adjacent_zones=["forest"],
            ),
        }

        return GameState(entities=entities, zones=zones, scene=Scene())

    def test_position_effect_triggers_auto_reveal(self, movement_test_state):
        """Test that position effects automatically trigger revelations."""
        # Apply position effect (simulating move tool)
        position_effect = {
            "type": "position",
            "target": "pc.traveler",
            "from": "forest",
            "to": "clearing",
        }

        apply_position(movement_test_state, position_effect)

        # Verify traveler moved
        traveler = movement_test_state.entities["pc.traveler"]
        assert traveler.current_zone == "clearing"

        # Verify auto-reveal occurred - public wolf should be discovered
        wolf = movement_test_state.entities["npc.wolf"]
        assert "pc.traveler" in wolf.meta.known_by

    def test_position_effect_updates_visibility(self, movement_test_state):
        """Test that position effects update visible_actors correctly."""
        # Apply position effect
        position_effect = {
            "type": "position",
            "target": "pc.traveler",
            "from": "forest",
            "to": "clearing",
        }

        apply_position(movement_test_state, position_effect)

        # Check that visible_actors is updated for entities in the clearing
        traveler = movement_test_state.entities["pc.traveler"]
        wolf = movement_test_state.entities["npc.wolf"]

        # Both entities should see each other
        assert "npc.wolf" in traveler.visible_actors
        assert "pc.traveler" in wolf.visible_actors


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_auto_reveal_nonexistent_actor(self):
        """Test auto-reveal with nonexistent actor."""
        state = GameState(entities={}, zones={}, scene=Scene())

        result = auto_reveal_on_zone_entry(state, "nonexistent", "zone")

        assert result["discovered"] == []
        assert result["already_known"] == []
        assert result["events"] == []

    def test_auto_reveal_nonexistent_zone(self):
        """Test auto-reveal with nonexistent zone."""
        entities: Dict[str, Entity] = {
            "pc.test": PC(
                id="pc.test",
                name="Test PC",
                current_zone="real_zone",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public"),
            )
        }

        state = GameState(entities=entities, zones={}, scene=Scene())

        result = auto_reveal_on_zone_entry(state, "pc.test", "fake_zone")

        # Should handle gracefully
        assert result["discovered"] == []

    def test_mutual_discovery_same_actor(self):
        """Test mutual discovery with same actor (should be safe)."""
        entities: Dict[str, Entity] = {
            "pc.test": PC(
                id="pc.test",
                name="Test PC",
                current_zone="zone",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public"),
            )
        }

        state = GameState(entities=entities, zones={}, scene=Scene())

        result = check_mutual_discovery(state, "pc.test", "pc.test")

        assert result["actor1_discovers_actor2"] == False
        assert result["actor2_discovers_actor1"] == False


class TestExplorationEvents:
    """Test exploration event triggering functionality."""

    def test_trigger_exploration_events(self):
        """Test triggering comprehensive exploration events."""
        entities: Dict[str, Entity] = {
            "pc.adventurer": PC(
                id="pc.adventurer",
                name="Adventurer",
                current_zone="entrance",
                hp=HP(current=25, max=25),
                meta=Meta(visibility="public"),
            ),
            "npc.librarian": NPC(
                id="npc.librarian",
                name="Librarian",
                current_zone="library",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="public"),
            ),
        }

        zones = {
            "entrance": Zone(
                id="entrance",
                name="Grand Entrance",
                description="A grand entrance hall",
                adjacent_zones=["library"],
            ),
            "library": Zone(
                id="library",
                name="Ancient Library",
                description="An ancient library filled with books",
                adjacent_zones=["entrance"],
            ),
        }

        state = GameState(entities=entities, zones=zones, scene=Scene())

        result = trigger_exploration_events(
            state, "pc.adventurer", "entrance", "library"
        )

        # Should have reveal results
        assert "reveal_results" in result
        reveal_results = result["reveal_results"]

        # Should discover the librarian
        assert "npc.librarian" in reveal_results["discovered"]

    def test_get_discoverable_entities(self):
        """Test getting list of discoverable entities."""
        entities: Dict[str, Entity] = {
            "pc.observer": PC(
                id="pc.observer",
                name="Observer",
                current_zone="library",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="public"),
            ),
            "npc.librarian": NPC(
                id="npc.librarian",
                name="Librarian",
                current_zone="library",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="public"),
            ),
            "npc.distant": NPC(
                id="npc.distant",
                name="Distant NPC",
                current_zone="other_zone",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public"),
            ),
        }

        zones = {
            "library": Zone(
                id="library", name="Library", description="A library", adjacent_zones=[]
            ),
            "other_zone": Zone(
                id="other_zone",
                name="Other Zone",
                description="A different zone",
                adjacent_zones=[],
            ),
        }

        state = GameState(entities=entities, zones=zones, scene=Scene())

        discoverable = get_discoverable_entities(state, "pc.observer", "library")

        # Should find the librarian as discoverable, but not the distant NPC
        assert "npc.librarian" in discoverable
        assert "npc.distant" not in discoverable

    def test_event_publishing_resilience(self):
        """Test that auto-reveal works even if event publishing fails."""
        entities: Dict[str, Entity] = {
            "pc.explorer": PC(
                id="pc.explorer",
                name="Explorer",
                current_zone="zone1",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="public"),
            ),
            "npc.discovered": NPC(
                id="npc.discovered",
                name="To Be Discovered",
                current_zone="zone2",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public"),
            ),
        }

        zones = {
            "zone1": Zone(
                id="zone1", name="Zone 1", description="First zone", adjacent_zones=[]
            ),
            "zone2": Zone(
                id="zone2", name="Zone 2", description="Second zone", adjacent_zones=[]
            ),
        }

        state = GameState(entities=entities, zones=zones, scene=Scene())

        # This should work even if event bus is not available
        result = auto_reveal_on_zone_entry(state, "pc.explorer", "zone2")

        # Core functionality should work regardless of event publishing
        assert "npc.discovered" in result["discovered"]

        # Verify meta was updated
        discovered = state.entities["npc.discovered"]
        assert "pc.explorer" in discovered.meta.known_by
