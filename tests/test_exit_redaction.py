"""
Test suite for enhanced exit redaction functionality.

Tests fine-grained exit visibility control, discovery-based redaction,
knowledge-based filtering, and partial information display.
"""

import pytest
from backend.router.game_state import GameState, Zone, PC, NPC, HP, Scene
from backend.router.zone_graph import (
    redact_exit,
    get_redacted_exits,
    create_redacted_world_view,
    get_redaction_suggestions,
)


class TestExitRedaction:
    """Test exit redaction functionality."""

    @pytest.fixture
    def redaction_world(self):
        """Create a world for testing exit redaction."""
        zones = {}

        # Create zones
        library = Zone(
            id="library",
            name="Ancient Library",
            description="A dusty library filled with ancient tomes",
            tags={"knowledge", "quiet", "indoor"},
        )

        secret_passage = Zone(
            id="secret_passage",
            name="Hidden Passage",
            description="A secret passage behind the bookshelf",
            tags={"hidden", "secret", "narrow"},
        )

        treasure_room = Zone(
            id="treasure_room",
            name="Treasure Chamber",
            description="A room filled with golden treasures",
            tags={"treasure", "valuable", "protected"},
        )

        dungeon = Zone(
            id="dungeon",
            name="Dark Dungeon",
            description="A damp, dark dungeon cell",
            tags={"prison", "dark", "dangerous"},
        )

        # Add zones to dictionary
        zones["library"] = library
        zones["secret_passage"] = secret_passage
        zones["treasure_room"] = treasure_room
        zones["dungeon"] = dungeon

        # Create exits with various properties
        library.add_exit(
            to="secret_passage",
            direction="north",
            label="Hidden Door",
            cost=3.0,
            terrain="stone",
            blocked=False,
            conditions={"requires_perception": "15"},
        )

        library.add_exit(
            to="dungeon",
            direction="east",
            label="Dungeon Stairs",
            cost=2.0,
            terrain="stone",
            blocked=False,
        )

        secret_passage.add_exit(
            to="treasure_room",
            direction="west",
            label="Treasure Door",
            cost=1.0,
            terrain="marble",
            blocked=True,
            conditions={"requires_key": "golden_key"},
        )

        secret_passage.add_exit(
            to="library",
            direction="south",
            label="Back to Library",
            cost=1.0,
            terrain="stone",
        )

        # Create actors with different capabilities
        scholar = PC(
            id="scholar",
            name="Wise Scholar",
            type="pc",
            current_zone="library",
            hp=HP(current=20, max=20),
        )

        rogue = PC(
            id="rogue",
            name="Sneaky Rogue",
            type="pc",
            current_zone="library",
            hp=HP(current=20, max=20),
        )

        guard = NPC(
            id="guard",
            name="Simple Guard",
            type="npc",
            current_zone="library",
            hp=HP(current=30, max=30),
        )

        # Create entities dictionary
        entities = {"scholar": scholar, "rogue": rogue, "guard": guard}

        # Create world
        world = GameState(entities=entities, zones=zones, scene=Scene())

        # Set some discovery states
        library.discovered_by.add("scholar")
        library.discovered_by.add("rogue")
        library.discovered_by.add(
            "guard"
        )  # Guard can see exits from where they're standing
        secret_passage.discovered_by.add("rogue")  # Only rogue found the secret

        return world

    def test_basic_exit_redaction(self, redaction_world):
        """Test basic exit redaction functionality."""
        library = redaction_world.zones["library"]
        hidden_exit = library.exits[0]  # north exit

        # Redact for scholar (high intelligence)
        redacted = redact_exit(hidden_exit, "scholar", redaction_world)

        # Scholar should see the exit (not None)
        assert redacted is not None
        assert redacted.direction == "north"
        assert redacted.to == "secret_passage"  # Destination should be preserved
        # Label might be redacted depending on discovery status

    def test_knowledge_based_redaction(self, redaction_world):
        """Test redaction based on actor knowledge/stats."""
        library = redaction_world.zones["library"]
        hidden_exit = library.exits[0]  # north exit

        # Test with different actors
        scholar_view = redact_exit(hidden_exit, "scholar", redaction_world)
        guard_view = redact_exit(hidden_exit, "guard", redaction_world)

        # Both should see the exit but scholar might see more details
        assert scholar_view is not None
        assert guard_view is not None
        assert scholar_view.direction == "north"
        assert guard_view.direction == "north"

    def test_discovery_based_redaction(self, redaction_world):
        """Test redaction based on discovery status."""
        secret_passage = redaction_world.zones["secret_passage"]

        # Get exits from zones not yet discovered by scholar
        treasure_exit = secret_passage.exits[0]  # west exit

        # Scholar hasn't discovered secret passage yet, so this might be redacted
        scholar_view = redact_exit(treasure_exit, "scholar", redaction_world)

        # Rogue has discovered the passage
        rogue_view = redact_exit(treasure_exit, "rogue", redaction_world)

        # Should see more since they discovered the zone
        assert rogue_view is not None
        assert rogue_view.direction == "west"

    def test_conditional_exit_redaction(self, redaction_world):
        """Test redaction of exits with conditions."""
        secret_passage = redaction_world.zones["secret_passage"]
        treasure_exit = secret_passage.exits[0]  # west exit with key requirement

        # Exit with key requirement
        redacted = redact_exit(treasure_exit, "rogue", redaction_world)
        assert redacted is not None
        assert redacted.blocked is True
        assert redacted.conditions is not None
        assert "requires_key" in redacted.conditions

    def test_get_redacted_exits(self, redaction_world):
        """Test getting all redacted exits for an actor."""
        library = redaction_world.zones["library"]

        # Get redacted exits for scholar
        redacted_exits = get_redacted_exits(library, "scholar", redaction_world)

        assert len(redacted_exits) == 2  # north and east exits
        # Check that exits are properly redacted
        for exit_obj in redacted_exits:
            assert hasattr(exit_obj, "direction")
            assert hasattr(exit_obj, "to")

    def test_create_redacted_world_view(self, redaction_world):
        """Test creating a complete redacted world view."""
        # Create redacted view for scholar
        scholar_view = create_redacted_world_view(redaction_world, "scholar")

        # Should include discovered zones
        assert "library" in scholar_view.zones

        # Should not include undiscovered zones
        assert "secret_passage" not in scholar_view.zones

        # Check that exits are properly redacted
        library_view = scholar_view.zones["library"]
        assert hasattr(library_view, "exits")

        # Create view for rogue (who discovered secret passage)
        rogue_view = create_redacted_world_view(redaction_world, "rogue")

        # Should include secret passage for rogue
        assert "secret_passage" in rogue_view.zones

    def test_redaction_suggestions(self, redaction_world):
        """Test getting redaction suggestions."""
        suggestions = get_redaction_suggestions(redaction_world, "scholar")

        # Should provide suggestions for improving redaction
        assert isinstance(suggestions, dict)

    def test_redaction_with_stats(self, redaction_world):
        """Test that redaction considers actor stats appropriately."""
        library = redaction_world.zones["library"]
        hidden_exit = library.exits[0]  # north exit with perception requirement

        # Scholar has high intelligence but moderate wisdom
        scholar_view = redact_exit(hidden_exit, "scholar", redaction_world)

        # Rogue has high wisdom (better perception)
        rogue_view = redact_exit(hidden_exit, "rogue", redaction_world)

        # Both should see the exit but may see different levels of detail
        assert scholar_view is not None
        assert rogue_view is not None
        assert scholar_view.direction == "north"
        assert rogue_view.direction == "north"

    def test_redaction_error_handling(self, redaction_world):
        """Test redaction error handling."""
        library = redaction_world.zones["library"]
        normal_exit = library.exits[1]  # east exit

        # Test with non-existent actor
        redacted = redact_exit(normal_exit, "nonexistent", redaction_world)

        # Non-existent actors should get no access since they haven't discovered anything
        # and aren't in the zone
        assert redacted is None, "Non-existent actors should not see exits"

        # Test with empty string actor
        redacted = redact_exit(normal_exit, "", redaction_world)
        # Empty actor should also get no access
        assert redacted is None, "Empty actor ID should not see exits"

    def test_redaction_preserves_core_info(self, redaction_world):
        """Test that redaction always preserves core exit information."""
        library = redaction_world.zones["library"]

        for exit_obj in library.exits:
            redacted = redact_exit(exit_obj, "guard", redaction_world)  # Low stats

            # Core info should always be preserved for actors in the zone
            assert (
                redacted is not None
            ), f"Exit {exit_obj.direction} should not be completely hidden for actor in zone"
            assert hasattr(redacted, "direction")
            assert hasattr(redacted, "to")
            assert redacted.direction == exit_obj.direction
            assert redacted.to == exit_obj.to
