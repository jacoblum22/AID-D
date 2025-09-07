"""
Test script for the Validator + Executor system (Step 4).

This demonstrates the complete pipeline:
- Schema validation
- Effect atom generation and application
- Standardized ToolResult envelope
- Logging system
"""

import sys
import os
import json
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.validator import validate_and_execute
from router.effects import get_registered_effects, apply_effects


@pytest.fixture
def demo_state():
    """Create a demo game state for testing."""

    # Create zones
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard with a guard post.",
            adjacent_zones=["threshold", "main_hall"],
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold to the manor.",
            adjacent_zones=["courtyard", "main_hall"],
        ),
        "main_hall": Zone(
            id="main_hall",
            name="Main Hall",
            description="A grand hall with tapestries.",
            adjacent_zones=["courtyard", "threshold"],
        ),
    }

    # Create entities
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            visible_actors=["npc.guard.01"],
            has_weapon=True,
            inventory=["rope", "healing_potion"],
        ),
        "npc.guard.01": NPC(
            id="npc.guard.01",
            name="Sleepy Guard",
            type="npc",
            current_zone="courtyard",
            visible_actors=["pc.arin"],
            has_weapon=True,
        ),
    }

    return GameState(
        entities=entities, zones=zones, current_actor="pc.arin", pending_action=None
    )


def test_effect_atoms_registration():
    """Test that effect atom system is properly registered."""
    registered_effects = get_registered_effects()

    # Check that we have the expected effect types
    expected_effects = ["hp", "position", "clock", "mark"]
    for effect_type in expected_effects:
        assert (
            effect_type in registered_effects
        ), f"Effect type '{effect_type}' not registered"


def test_hp_effect(demo_state):
    """Test HP effect atom."""
    initial_hp = demo_state.actors["pc.arin"].hp.current

    apply_effects(demo_state, [{"type": "hp", "target": "pc.arin", "delta": -5}])

    final_hp = demo_state.actors["pc.arin"].hp.current
    assert (
        final_hp == initial_hp - 5
    ), f"HP should decrease by 5: {initial_hp} -> {final_hp}"


def test_position_effect(demo_state):
    """Test position effect atom."""
    initial_zone = demo_state.actors["pc.arin"].current_zone
    assert initial_zone == "courtyard"

    apply_effects(
        demo_state, [{"type": "position", "target": "pc.arin", "to": "threshold"}]
    )

    final_zone = demo_state.actors["pc.arin"].current_zone
    assert (
        final_zone == "threshold"
    ), f"Position should change to threshold: {final_zone}"


def test_clock_effect(demo_state):
    """Test clock effect atom."""
    apply_effects(demo_state, [{"type": "clock", "id": "scene.alarm", "delta": 2}])

    assert hasattr(
        demo_state, "clocks"
    ), "State should have clocks attribute after clock effect"
    assert "scene.alarm" in demo_state.clocks, "scene.alarm clock should exist"
    assert demo_state.clocks["scene.alarm"]["value"] == 2, "Clock should have value 2"


def test_successful_ask_roll(demo_state):
    """Test successful ask_roll execution."""
    utterance = Utterance(text="I sneak past the guard", actor_id="pc.arin")

    result = validate_and_execute(
        "ask_roll",
        {
            "actor": "pc.arin",
            "action": "sneak",
            "target": "npc.guard.01",
            "zone_target": "threshold",
            "dc_hint": 12,
            "style": 1,
            "domain": "d6",
        },
        demo_state,
        utterance,
        seed=12345,  # Fixed seed for consistent results
    )

    assert result.ok is True, f"ask_roll should succeed: {result.error_message}"
    assert result.tool_id == "ask_roll"
    assert "outcome" in result.facts
    assert "total" in result.facts
    assert "dc" in result.facts
    assert isinstance(result.effects, list)


def test_move_execution(demo_state):
    """Test move tool execution."""
    utterance = Utterance(text="I run to the main hall", actor_id="pc.arin")

    result = validate_and_execute(
        "move",
        {"actor": "pc.arin", "to": "main_hall", "movement_style": "fast"},
        demo_state,
        utterance,
        seed=54321,
    )

    assert result.ok is True, f"move should succeed: {result.error_message}"
    assert result.tool_id == "move"
    assert "destination" in result.facts
    assert result.facts["destination"] == "main_hall"
    assert len(result.effects) >= 1  # Should have at least position effect


def test_attack_execution(demo_state):
    """Test attack tool execution."""
    utterance = Utterance(text="I attack the guard", actor_id="pc.arin")

    result = validate_and_execute(
        "attack",
        {"actor": "pc.arin", "target": "npc.guard.01", "weapon": "sword"},
        demo_state,
        utterance,
        seed=99999,
    )

    assert result.ok is True, f"attack should succeed: {result.error_message}"
    assert result.tool_id == "attack"
    assert "hit" in result.facts
    assert "damage" in result.facts
    assert isinstance(result.facts["hit"], bool)
    assert isinstance(result.facts["damage"], int)


def test_use_item_execution(demo_state):
    """Test use_item tool execution."""
    utterance = Utterance(text="I drink my healing potion", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item": "healing_potion", "target": "pc.arin"},
        demo_state,
        utterance,
        seed=11111,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"
    assert result.tool_id == "use_item"
    assert "item_used" in result.facts
    assert result.facts["item_used"] == "healing_potion"


def test_get_info_execution(demo_state):
    """Test get_info tool execution."""
    utterance = Utterance(text="What do I see here?", actor_id="pc.arin")

    result = validate_and_execute(
        "get_info",
        {"query": "What do I see?", "scope": "current_zone"},
        demo_state,
        utterance,
        seed=22222,
    )

    assert result.ok is True, f"get_info should succeed: {result.error_message}"
    assert result.tool_id == "get_info"
    # Should contain zone information
    expected_keys = [
        "zone_name",
        "zone_description",
        "visible_actors",
        "adjacent_zones",
    ]
    for key in expected_keys:
        assert key in result.facts, f"get_info should return {key}"


def test_schema_validation_failure(demo_state):
    """Test that schema validation properly fails and provides fallback."""
    utterance = Utterance(text="I do something", actor_id="pc.arin")

    result = validate_and_execute(
        "ask_roll",
        {
            "actor": "pc.arin",
            "style": "invalid_type",  # Should be int, not string
            # Missing required fields
        },
        demo_state,
        utterance,
        seed=33333,
    )

    assert result.ok is False, "Schema validation should fail"
    assert result.tool_id == "ask_clarifying", "Should fallback to ask_clarifying"
    assert result.error_message is not None, "Should have error message"
    assert (
        "Schema validation failed" in result.error_message
    ), "Should mention schema validation failure"


def test_invalid_tool_id(demo_state):
    """Test handling of invalid tool IDs."""
    utterance = Utterance(text="I do something", actor_id="pc.arin")

    result = validate_and_execute(
        "nonexistent_tool", {"actor": "pc.arin"}, demo_state, utterance, seed=44444
    )

    assert result.ok is False, "Invalid tool should fail"
    assert result.tool_id == "ask_clarifying", "Should fallback to ask_clarifying"
    assert result.error_message is not None, "Should have error message"
    assert "Unknown tool" in result.error_message, "Should mention unknown tool"


def test_tool_result_structure():
    """Test that ToolResult has the expected structure."""
    from router.validator import ToolResult

    result = ToolResult(
        ok=True,
        tool_id="test_tool",
        args={"test": "value"},
        facts={"result": "success"},
        effects=[{"type": "test", "value": 1}],
        narration_hint={"summary": "Test action"},
    )

    # Test to_dict conversion
    result_dict = result.to_dict()

    expected_keys = [
        "ok",
        "tool_id",
        "args",
        "facts",
        "effects",
        "narration_hint",
        "error_message",
    ]
    for key in expected_keys:
        assert key in result_dict, f"ToolResult should have {key} in dict conversion"

    assert result_dict["ok"] is True
    assert result_dict["tool_id"] == "test_tool"
    assert result_dict["error_message"] is None


def test_state_modifications_persist(demo_state):
    """Test that effect atoms properly modify game state persistently."""
    # Track initial state
    initial_hp = demo_state.actors["pc.arin"].hp.current
    initial_zone = demo_state.actors["pc.arin"].current_zone

    assert initial_zone == "courtyard"

    # Execute attack action first (while in same zone as guard)
    utterance = Utterance(text="I attack then move to threshold", actor_id="pc.arin")
    result = validate_and_execute(
        "attack",
        {"actor": "pc.arin", "target": "npc.guard.01", "weapon": "sword"},
        demo_state,
        utterance,
        54321,
    )

    assert result.ok is True, f"Attack should succeed: {result.error_message}"
    # Check if damage was applied (if hit)
    if result.facts["hit"] and result.facts["damage"] > 0:
        guard_hp = getattr(demo_state.actors["npc.guard.01"], "hp", None)
        if guard_hp:
            assert guard_hp.current < guard_hp.max, "Guard should take damage if hit"

    # Execute move action after attack (utterance mentions "threshold" for precondition)
    result = validate_and_execute(
        "move",
        {"actor": "pc.arin", "to": "threshold"},
        demo_state,
        utterance,  # This utterance text mentions "threshold"
        12345,
    )

    assert result.ok is True, f"Move should succeed: {result.error_message}"
    assert (
        demo_state.actors["pc.arin"].current_zone == "threshold"
    ), "Move should update state"


def test_zone_target_validation(demo_state):
    """Test that zone_target validation works properly."""
    utterance = Utterance(text="I sneak somewhere impossible", actor_id="pc.arin")

    # Try to move to a zone that's not adjacent
    result = validate_and_execute(
        "ask_roll",
        {
            "actor": "pc.arin",
            "action": "sneak",
            "zone_target": "impossible_zone",  # Not adjacent to courtyard
            "style": 1,
            "domain": "d6",
        },
        demo_state,
        utterance,
        seed=77777,
    )

    assert result.ok is False, "Should fail for invalid zone target"
    assert result.tool_id == "ask_clarifying", "Should ask for clarification"


def test_fixed_critical_failure_delta():
    """Test that critical failure now has worse consequences than regular failure."""
    # This tests the fix we made to line 433
    from router.validator import Validator

    validator = Validator()

    # Create mock state for testing effect generation
    demo_state = GameState(
        entities={}, zones={}, current_actor=None, pending_action=None
    )

    # Test regular failure effects
    fail_effects = validator._generate_ask_roll_effects(
        "fail", "sneak", "pc.arin", None, "threshold", demo_state
    )

    # Test critical failure effects
    crit_fail_effects = validator._generate_ask_roll_effects(
        "crit_fail", "sneak", "pc.arin", None, "threshold", demo_state
    )

    # Both should have alarm clock effects
    fail_alarm = next((e for e in fail_effects if e.get("id") == "scene.alarm"), None)
    crit_fail_alarm = next(
        (e for e in crit_fail_effects if e.get("id") == "scene.alarm"), None
    )

    assert fail_alarm is not None, "Regular failure should have alarm effect"
    assert crit_fail_alarm is not None, "Critical failure should have alarm effect"

    # Critical failure should have higher delta than regular failure
    assert (
        crit_fail_alarm["delta"] > fail_alarm["delta"]
    ), f"Critical failure delta ({crit_fail_alarm['delta']}) should be greater than regular failure delta ({fail_alarm['delta']})"

    # Specifically test the fix: should be 3 vs 2
    assert fail_alarm["delta"] == 2, "Regular failure should have delta=2"
    assert crit_fail_alarm["delta"] == 3, "Critical failure should have delta=3"


if __name__ == "__main__":
    # Run pytest when script is executed directly
    pytest.main([__file__, "-v"])
