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
    assert "outcome" in result.facts
    assert "applied_damage" in result.facts
    assert result.facts["outcome"] in ["crit_success", "success", "partial", "fail"]
    assert isinstance(result.facts["applied_damage"], int)


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
    if (
        result.facts["outcome"] in ["success", "crit_success", "partial"]
        and result.facts["applied_damage"] > 0
    ):
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


def test_damage_dice_type_consistency():
    """Test that damage_dice uses consistent dictionary format for all entries."""
    from router.validator import Validator
    import random

    validator = Validator()

    # Test regular damage without crit
    damage_dice, total_damage = validator._roll_damage("1d6", False, random)

    # Should have exactly one entry (the base damage roll)
    assert len(damage_dice) == 1, "Regular damage should have one dice entry"

    # Check that it's a dictionary with proper structure
    dice_entry = damage_dice[0]
    assert isinstance(dice_entry, dict), "Damage dice entry should be a dictionary"
    assert "type" in dice_entry, "Damage dice entry should have 'type' field"
    assert "value" in dice_entry, "Damage dice entry should have 'value' field"
    assert dice_entry["type"] == "base", "Regular damage should have type 'base'"
    assert isinstance(dice_entry["value"], int), "Damage value should be an integer"
    assert 1 <= dice_entry["value"] <= 6, "1d6 should roll between 1 and 6"

    # Test critical damage
    damage_dice, total_damage = validator._roll_damage("1d6", True, random)

    # Should have two entries (base damage + crit damage)
    assert len(damage_dice) == 2, "Critical damage should have two dice entries"

    # Check base damage entry
    base_entry = damage_dice[0]
    assert isinstance(base_entry, dict), "Base damage entry should be a dictionary"
    assert base_entry["type"] == "base", "First entry should be base damage"
    assert isinstance(
        base_entry["value"], int
    ), "Base damage value should be an integer"

    # Check crit damage entry
    crit_entry = damage_dice[1]
    assert isinstance(crit_entry, dict), "Crit damage entry should be a dictionary"
    assert crit_entry["type"] == "crit", "Second entry should be crit damage"
    assert isinstance(
        crit_entry["value"], int
    ), "Crit damage value should be an integer"
    assert 1 <= crit_entry["value"] <= 6, "Crit damage should roll 1d6"


def test_partial_damage_no_double_halving():
    """Test that partial damage is not halved twice in attack summary."""
    from router.validator import Validator

    validator = Validator()

    # Test partial outcome with already-halved damage value
    halved_damage = 4  # This represents damage already halved from 8 raw damage
    summary = validator._get_attack_summary(
        "partial", "sword", halved_damage, "TestActor"
    )

    # Should use the damage value as-is, not halve it again
    expected_summary = f"TestActor's sword grazes the target for {halved_damage} damage"
    assert (
        summary == expected_summary
    ), f"Partial damage should not be halved again. Got: {summary}"

    # Compare with success to ensure we're not double-halving
    success_summary = validator._get_attack_summary("success", "sword", 8, "TestActor")
    partial_summary = validator._get_attack_summary(
        "partial", "sword", 4, "TestActor"
    )  # 4 is already halved from 8

    # The damage numbers in the strings should match the passed values
    assert "8 damage" in success_summary, "Success should show full damage"
    assert (
        "4 damage" in partial_summary
    ), "Partial should show halved damage (already halved by caller)"


def test_consistent_field_naming_salient_entities():
    """Test that narration_hint consistently uses 'salient_entities' instead of 'mentioned_entities'."""
    from router.validator import validate_and_execute

    # Test various error conditions that should use salient_entities
    demo_state = GameState(
        entities={}, zones={}, current_actor=None, pending_action=None
    )

    utterance = Utterance(text="I attack someone", actor_id="pc.arin")

    # Test missing actor error
    result = validate_and_execute(
        "attack",
        {"actor": "nonexistent_actor", "target": "some_target"},
        demo_state,
        utterance,
        seed=12345,
    )

    assert result.ok is False, "Should fail with missing actor"
    assert "narration_hint" in result.to_dict(), "Should have narration_hint"
    narration_hint = result.to_dict()["narration_hint"]
    assert "salient_entities" in narration_hint, "Should use 'salient_entities' field"
    assert (
        "mentioned_entities" not in narration_hint
    ), "Should not use 'mentioned_entities' field"

    # Add a target entity to test missing target error
    demo_state.entities["some_target"] = PC(
        id="some_target", name="Target", current_zone="zone1"
    )

    result = validate_and_execute(
        "attack",
        {"actor": "some_target", "target": "nonexistent_target"},
        demo_state,
        utterance,
        seed=12345,
    )

    assert result.ok is False, "Should fail with missing target"
    narration_hint = result.to_dict()["narration_hint"]
    assert "salient_entities" in narration_hint, "Should use 'salient_entities' field"
    assert (
        "mentioned_entities" not in narration_hint
    ), "Should not use 'mentioned_entities' field"


def test_tool_catalog_suggest_attack_args_no_actor():
    """Test that suggest_attack_args returns empty dict when no current actor exists."""
    from router.tool_catalog import suggest_attack_args
    from router.game_state import Utterance

    # Create state with no current_actor
    state = GameState(entities={}, zones={}, current_actor=None, pending_action=None)

    utterance = Utterance(text="I attack", actor_id="pc.test")

    # Should return empty dict instead of None values that would fail validation
    result = suggest_attack_args(state, utterance)

    assert isinstance(result, dict), "Should return a dictionary"
    assert result == {}, "Should return empty dict when no current actor"

    # Verify this doesn't cause Pydantic validation issues
    from router.tool_catalog import AttackArgs

    # If result is empty, AttackArgs validation should handle it gracefully
    # (the calling code would need to handle missing required fields)
    if result:  # Only validate if not empty
        try:
            AttackArgs(**result)
        except Exception as e:
            # Empty dict should not cause issues - this tests that we don't have None values
            assert "None" not in str(e), f"Should not have None validation errors: {e}"


if __name__ == "__main__":
    # Run pytest when script is executed directly
    pytest.main([__file__, "-v"])
