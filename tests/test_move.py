"""
Test script for the Move tool.

This tests the comprehensive move mechanics including zone transitions,
movement methods (walk/run/sneak), validation, and effect generation.
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, HP, Utterance, Scene
from router.validator import validate_and_execute


@pytest.fixture
def move_state():
    """Create a game state set up for move testing."""

    # Create zones with adjacency
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard.",
            adjacent_zones=["hall", "armory"],
        ),
        "hall": Zone(
            id="hall",
            name="Great Hall",
            description="A large hall with tapestries.",
            adjacent_zones=["courtyard", "kitchen"],
        ),
        "kitchen": Zone(
            id="kitchen",
            name="Kitchen",
            description="A busy kitchen.",
            adjacent_zones=["hall"],
        ),
        "armory": Zone(
            id="armory",
            name="Armory",
            description="Weapons and armor storage.",
            adjacent_zones=["courtyard"],
        ),
        "barracks": Zone(
            id="barracks",
            name="Barracks",
            description="Sleeping quarters.",
            adjacent_zones=["distant_tower"],  # Not connected to main area
        ),
        "distant_tower": Zone(
            id="distant_tower",
            name="Distant Tower",
            description="A far tower.",
            adjacent_zones=["barracks"],
        ),
    }

    # Create entities
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["npc.guard"],
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=15, max=20),
            visible_actors=["pc.arin"],
        ),
        "npc.unconscious": NPC(
            id="npc.unconscious",
            name="Unconscious Guard",
            type="npc",
            current_zone="hall",
            hp=HP(current=0, max=20),  # Unconscious
            visible_actors=[],
        ),
    }

    # Create scene with basic tags
    scene = Scene(
        turn_order=["pc.arin", "npc.guard"],
        turn_index=0,
        round=1,
        tags={"lighting": "normal", "noise": "quiet"},
    )

    return GameState(
        entities=entities,
        zones=zones,
        scene=scene,
        current_actor="pc.arin",
        clocks={"alarm": {"value": 0, "min": 0, "max": 10}},
        pending_action=None,
    )


class TestMoveBasics:
    """Test basic move functionality."""

    def test_valid_move_walk(self, move_state):
        """Test a basic successful move (walk)."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "walk",
        }

        utterance = Utterance(text="I walk to the hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.tool_id == "move"
        assert result.facts["from_zone"] == "courtyard"
        assert result.facts["to_zone"] == "hall"
        assert result.facts["method"] == "walk"
        assert result.facts["actor"] == "pc.arin"

        # Should have position effect
        position_effects = [e for e in result.effects if e["type"] == "position"]
        assert len(position_effects) == 1
        assert position_effects[0]["target"] == "pc.arin"
        assert position_effects[0]["to"] == "hall"
        assert position_effects[0]["source"] == "pc.arin"
        assert position_effects[0]["cause"] == "move"

    def test_valid_move_run(self, move_state):
        """Test running movement with noise generation."""
        args = {
            "actor": "pc.arin",
            "to": "armory",
            "method": "run",
        }

        utterance = Utterance(text="I run to the armory", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["method"] == "run"
        assert result.facts["noise_generated"] == True

        # Should have position effect
        position_effects = [e for e in result.effects if e["type"] == "position"]
        assert len(position_effects) == 1

        # Should have noise tag effect
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        assert len(tag_effects) == 1
        assert tag_effects[0]["target"] == "scene"
        assert "noise" in tag_effects[0]["add"]
        assert tag_effects[0]["add"]["noise"] == "loud"

        # Should advance alarm clock
        clock_effects = [e for e in result.effects if e["type"] == "clock"]
        assert len(clock_effects) == 1
        assert clock_effects[0]["id"] == "alarm"  # Clock effects use "id" not "target"
        assert clock_effects[0]["delta"] == 1

        # Check narration tone
        assert "urgent" in result.narration_hint["tone_tags"]

    def test_valid_move_sneak(self, move_state):
        """Test sneaking movement with stealth tag."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "sneak",
        }

        utterance = Utterance(text="I sneak to the hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["method"] == "sneak"
        assert (
            result.facts["sneak_intent"] == True
        )  # Changed from "sneaking" to "sneak_intent"

        # Should have position effect
        position_effects = [e for e in result.effects if e["type"] == "position"]
        assert len(position_effects) == 1

        # Should have sneak intent tag effect
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        assert len(tag_effects) == 1
        assert tag_effects[0]["target"] == "pc.arin"
        assert (
            tag_effects[0]["add"]["sneak_intent"] == True
        )  # Changed from "sneaking" to "sneak_intent"

        # Check narration tone
        assert "stealthy" in result.narration_hint["tone_tags"]

    def test_multi_zone_path(self, move_state):
        """Test that each move is only one zone at a time."""
        # Try to move from courtyard to kitchen (must go through hall)
        args = {
            "actor": "pc.arin",
            "to": "kitchen",
            "method": "walk",
        }

        utterance = Utterance(text="I walk to the kitchen", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        # Should fail because kitchen is not adjacent to courtyard
        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "Great Hall, Armory" in result.args["question"]  # Valid exits


class TestMoveValidation:
    """Test move validation and error handling."""

    def test_invalid_actor(self, move_state):
        """Test move with non-existent actor."""
        args = {
            "actor": "nonexistent.actor",
            "to": "hall",
            "method": "walk",
        }

        utterance = Utterance(text="I move", actor_id="nonexistent.actor")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "don't see that character" in result.args["question"].lower()

    def test_unconscious_actor(self, move_state):
        """Test move with unconscious actor."""
        args = {
            "actor": "npc.unconscious",
            "to": "kitchen",
            "method": "walk",
        }

        utterance = Utterance(
            text="unconscious guard moves", actor_id="npc.unconscious"
        )
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "unconscious" in result.args["question"].lower()

    def test_invalid_target_zone(self, move_state):
        """Test move to non-existent zone."""
        args = {
            "actor": "pc.arin",
            "to": "nonexistent_zone",
            "method": "walk",
        }

        utterance = Utterance(text="I go to nowhere", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "don't know where" in result.args["question"].lower()

    def test_non_adjacent_zone(self, move_state):
        """Test move to non-adjacent zone."""
        args = {
            "actor": "pc.arin",
            "to": "barracks",  # Not adjacent to courtyard
            "method": "walk",
        }

        utterance = Utterance(text="I walk to barracks", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "can't move there" in result.args["question"].lower()
        assert "Valid exits:" in result.args["question"]


class TestMoveNarration:
    """Test move narration and hints."""

    def test_narration_hint_structure(self, move_state):
        """Test that narration hints have proper structure."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "walk",
        }

        utterance = Utterance(text="I walk to the hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        hint = result.narration_hint

        # Check required fields
        assert "summary" in hint
        assert "movement" in hint
        assert "tone_tags" in hint
        assert "salient_entities" in hint
        assert "mentioned_zones" in hint
        assert "camera" in hint

        # Check movement details
        movement = hint["movement"]
        assert movement["from"] == "courtyard"
        assert movement["to"] == "hall"
        assert movement["method"] == "walk"
        assert movement["from_name"] == "Courtyard"
        assert movement["to_name"] == "Great Hall"

        # Check entities and zones mentioned
        assert "pc.arin" in hint["salient_entities"]
        assert "courtyard" in hint["mentioned_zones"]
        assert "hall" in hint["mentioned_zones"]
        assert hint["camera"] == "tracking"

    def test_method_specific_narration(self, move_state):
        """Test that different movement methods generate appropriate narration."""
        methods = [
            ("walk", "walks", ["transition", "movement"]),
            ("run", "runs", ["transition", "movement", "urgent"]),
            ("sneak", "sneaks", ["transition", "movement", "stealthy"]),
        ]

        for method, verb, expected_tags in methods:
            # Reset actor to courtyard before each test iteration
            move_state.entities["pc.arin"].current_zone = "courtyard"

            args = {
                "actor": "pc.arin",
                "to": "armory",  # Move to adjacent zone (armory is adjacent to courtyard)
                "method": method,
            }

            utterance = Utterance(text=f"I {method} to the armory", actor_id="pc.arin")
            result = validate_and_execute("move", args, move_state, utterance, seed=42)

            assert result.ok == True
            summary = result.narration_hint["summary"]
            tone_tags = result.narration_hint["tone_tags"]

            # Summary should use the correct verb
            assert verb in summary.lower()
            assert "courtyard" in summary.lower()
            assert "armory" in summary.lower()

            # Tone tags should match expectations
            for tag in expected_tags:
                assert tag in tone_tags


class TestMoveEffects:
    """Test move effect generation."""

    def test_position_effect_details(self, move_state):
        """Test position effect contains all required fields."""
        args = {
            "actor": "pc.arin",
            "to": "armory",
            "method": "walk",
        }

        utterance = Utterance(text="I walk to armory", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        position_effects = [e for e in result.effects if e["type"] == "position"]
        assert len(position_effects) == 1

        effect = position_effects[0]
        assert effect["type"] == "position"
        assert effect["target"] == "pc.arin"
        assert effect["to"] == "armory"
        assert effect["source"] == "pc.arin"
        assert effect["cause"] == "move"

    def test_run_generates_noise_and_clock_effects(self, move_state):
        """Test that running generates both noise tags and clock effects."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "run",
        }

        utterance = Utterance(text="I run to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True

        # Check tag effect for noise
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        assert len(tag_effects) == 1
        tag_effect = tag_effects[0]
        assert tag_effect["target"] == "scene"
        assert tag_effect["add"]["noise"] == "loud"
        assert tag_effect["source"] == "pc.arin"
        assert tag_effect["cause"] == "running"

        # Check clock effect for alarm
        clock_effects = [e for e in result.effects if e["type"] == "clock"]
        assert len(clock_effects) == 1
        clock_effect = clock_effects[0]
        assert clock_effect["id"] == "alarm"  # Clock effects use "id" not "target"
        assert clock_effect["delta"] == 1
        assert clock_effect["source"] == "pc.arin"
        assert clock_effect["cause"] == "noisy_movement"

    def test_sneak_generates_stealth_tag(self, move_state):
        """Test that sneaking generates stealth tag effect."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "sneak",
        }

        utterance = Utterance(text="I sneak to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True

        # Check tag effect for sneak intent
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        assert len(tag_effects) == 1
        tag_effect = tag_effects[0]
        assert tag_effect["target"] == "pc.arin"
        assert (
            tag_effect["add"]["sneak_intent"] == True
        )  # Changed from "sneaking" to "sneak_intent"
        assert tag_effect["source"] == "pc.arin"
        assert tag_effect["cause"] == "stealth_movement"


class TestMoveToolCatalogIntegration:
    """Test integration with tool catalog (preconditions, suggestions)."""

    def test_move_precondition_valid_zone(self, move_state):
        """Test that move precondition works for valid moves."""
        from router.tool_catalog import move_precond

        # Test valid move mention
        utterance = Utterance(text="I want to go to the hall", actor_id="pc.arin")
        assert move_precond(move_state, utterance) == True

        # Test by zone name
        utterance = Utterance(text="I head to the Great Hall", actor_id="pc.arin")
        assert move_precond(move_state, utterance) == True

    def test_move_precondition_invalid_zone(self, move_state):
        """Test that move precondition checks game state, not intent."""
        from router.tool_catalog import move_precond

        # Valid game state should return True regardless of zone mentioned
        utterance = Utterance(text="I go to the barracks", actor_id="pc.arin")
        assert move_precond(move_state, utterance) == True  # Game state is valid

        # Invalid utterance but valid game state should still return True
        utterance = Utterance(text="I just stand here", actor_id="pc.arin")
        assert move_precond(move_state, utterance) == True  # Game state check only

    def test_move_precondition_unconscious_actor(self, move_state):
        """Test that unconscious actors can pass preconditions but fail during execution."""
        from router.tool_catalog import move_precond

        # Set current actor to unconscious - should pass precondition now
        move_state.current_actor = "npc.unconscious"
        utterance = Utterance(text="I go to the kitchen", actor_id="npc.unconscious")

        # Precondition should pass (HP check moved to execution logic)
        assert move_precond(move_state, utterance) == True

        # But execution should fail with better error message
        args = {"actor": "npc.unconscious", "to": "kitchen", "method": "walk"}
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "unconscious" in result.args["question"].lower()

    def test_suggest_move_args_method_detection(self, move_state):
        """Test that argument suggestion detects movement methods."""
        from router.tool_catalog import suggest_move_args

        # Test walk detection (default)
        utterance = Utterance(text="I walk to the hall", actor_id="pc.arin")
        args = suggest_move_args(move_state, utterance)
        assert args["method"] == "walk"
        assert args["to"] == "hall"

        # Test run detection
        utterance = Utterance(text="I run quickly to the armory", actor_id="pc.arin")
        args = suggest_move_args(move_state, utterance)
        assert args["method"] == "run"
        assert args["to"] == "armory"

        # Test sneak detection
        utterance = Utterance(text="I sneak quietly to the hall", actor_id="pc.arin")
        args = suggest_move_args(move_state, utterance)
        assert args["method"] == "sneak"
        assert args["to"] == "hall"


class TestMoveEdgeCases:
    """Test edge cases and future enhancements."""

    def test_move_to_same_zone(self, move_state):
        """Test that moving to the same zone is prevented."""
        args = {
            "actor": "pc.arin",
            "to": "courtyard",  # Same as current zone
            "method": "walk",
        }

        utterance = Utterance(text="I stay in courtyard", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        # Should fail because courtyard is not in its own adjacent_zones
        assert result.ok == False
        assert result.tool_id == "ask_clarifying"

    def test_empty_zone_name_handling(self, move_state):
        """Test handling of empty or None zone names."""
        args = {
            "actor": "pc.arin",
            "to": "",  # Empty zone name
            "method": "walk",
        }

        utterance = Utterance(text="I go nowhere", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "don't know where" in result.args["question"].lower()

    def test_cost_parameter_ignored(self, move_state):
        """Test that cost parameter is accepted but ignored for now."""
        args = {
            "actor": "pc.arin",
            "to": "hall",
            "method": "walk",
            "cost": 5,  # Future enhancement
        }

        utterance = Utterance(text="I walk to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        # Should succeed despite cost parameter
        assert result.ok == True
        assert result.facts["to_zone"] == "hall"


# Enhanced Move Tool Tests (Additional Features)
class TestMoveEnhancements:
    """Test the enhanced move tool features."""

    def test_same_zone_move_rejected(self, move_state):
        """Test that moving to the same zone is rejected."""
        args = {"actor": "pc.arin", "to": "courtyard", "method": "walk"}
        utterance = Utterance(text="I stay here", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "already in" in result.args["question"].lower()
        assert result.facts["cause"] == "same_zone"
        assert result.facts["current_zone"] == "courtyard"

    def test_blocked_exits_validation(self, move_state):
        """Test that blocked exits are properly rejected."""
        # Add blocked_exits to courtyard zone
        move_state.zones["courtyard"].blocked_exits = ["hall"]

        args = {"actor": "pc.arin", "to": "hall", "method": "walk"}
        utterance = Utterance(text="I go to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "blocked" in result.args["question"].lower()
        assert result.facts["cause"] == "blocked"
        assert result.facts["destination"] == "hall"

    def test_cost_tracking_in_facts(self, move_state):
        """Test that cost is tracked in facts even when not enforced."""
        # First test: courtyard to hall
        args = {"actor": "pc.arin", "to": "hall", "method": "walk", "cost": 2}
        utterance = Utterance(text="I walk to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["cost"] == 2

        # Second test: now actor is in hall, move to kitchen (adjacent to hall)
        args = {"actor": "pc.arin", "to": "kitchen", "method": "walk", "cost": None}
        utterance = Utterance(text="I walk to kitchen", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)
        assert result.ok == True
        assert result.facts["cost"] is None

    def test_position_effect_includes_from_and_to(self, move_state):
        """Test that position effects include both from and to fields."""
        args = {"actor": "pc.arin", "to": "hall", "method": "walk"}
        utterance = Utterance(text="I walk to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True

        # Find the position effect
        position_effect = next(e for e in result.effects if e["type"] == "position")
        assert position_effect["from"] == "courtyard"
        assert position_effect["to"] == "hall"
        assert position_effect["target"] == "pc.arin"

    def test_sneak_intent_vs_result(self, move_state):
        """Test that sneak method sets intent, not result."""
        args = {"actor": "pc.arin", "to": "hall", "method": "sneak"}
        utterance = Utterance(text="I sneak to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["sneak_intent"] == True
        assert "sneaking" not in result.facts  # Should not claim success

        # Find the tag effect
        tag_effect = next(
            e for e in result.effects if e["type"] == "tag" and e["target"] == "pc.arin"
        )
        assert "sneak_intent" in tag_effect["add"]
        assert tag_effect["add"]["sneak_intent"] == True

    def test_run_method_generates_noise_effect(self, move_state):
        """Test that running generates both scene tag and noise effect."""
        args = {"actor": "pc.arin", "to": "hall", "method": "run"}
        utterance = Utterance(text="I run to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["noise_generated"] == True

        # Find the scene noise tag effect
        scene_tag_effect = next(
            e for e in result.effects if e["type"] == "tag" and e["target"] == "scene"
        )
        assert scene_tag_effect["add"]["noise"] == "loud"

        # Find the generic noise effect
        noise_effect = next(e for e in result.effects if e["type"] == "noise")
        assert noise_effect["zone"] == "hall"
        assert noise_effect["intensity"] == "loud"
        assert noise_effect["source"] == "pc.arin"

    def test_narration_hints_enhanced(self, move_state):
        """Test enhanced narration hints with movement_verb and zone_names."""
        args = {"actor": "pc.arin", "to": "hall", "method": "sneak"}
        utterance = Utterance(text="I sneak to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == True

        narration = result.narration_hint
        assert narration["movement"]["movement_verb"] == "sneaks"
        assert narration["zone_names"]["courtyard"] == "Courtyard"
        assert narration["zone_names"]["hall"] == "Great Hall"
        assert "stealthy" in narration["tone_tags"]

    def test_unconscious_actor_metadata(self, move_state):
        """Test that unconscious actors get proper error metadata."""
        # Make actor unconscious
        move_state.entities["pc.arin"].hp.current = 0

        args = {"actor": "pc.arin", "to": "hall", "method": "walk"}
        utterance = Utterance(text="I walk to hall", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "unconscious" in result.args["question"].lower()
        assert result.facts["cause"] == "actor_state"
        assert result.facts["actor_state"] == "unconscious"
        assert result.facts["actor"] == "pc.arin"

    def test_invalid_destination_metadata(self, move_state):
        """Test that invalid destinations include helpful metadata."""
        args = {"actor": "pc.arin", "to": "invalid_zone", "method": "walk"}
        utterance = Utterance(text="I go somewhere", actor_id="pc.arin")
        result = validate_and_execute("move", args, move_state, utterance, seed=42)

        assert result.ok == False
        # Check if facts are provided (depends on validation level)
        if result.facts:
            assert result.facts["cause"] == "invalid"
            assert "valid_exits" in result.facts
        # At minimum, should have helpful error message
        assert (
            "don't know where" in result.args["question"].lower()
            or "invalid" in result.args["question"].lower()
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
