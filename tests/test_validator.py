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
        {"actor": "pc.arin", "item_id": "healing_potion", "target": "pc.arin"},
        demo_state,
        utterance,
        seed=11111,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"
    assert result.tool_id == "use_item"
    assert "item_id" in result.facts
    assert result.facts["item_id"] == "healing_potion"


def test_use_item_healing_potion(demo_state):
    """Test using a healing potion increases HP and consumes item."""
    # First, reduce PC's HP so healing can have an effect
    from router.game_state import HP

    damaged_hp = HP(current=10, max=20)  # Reduce from full HP
    demo_state.entities["pc.arin"] = demo_state.entities["pc.arin"].model_copy(
        update={"hp": damaged_hp}
    )

    initial_hp = demo_state.entities["pc.arin"].hp.current
    initial_inventory = demo_state.entities["pc.arin"].inventory.copy()

    assert (
        "healing_potion" in initial_inventory
    ), "Should have healing potion in inventory"
    assert initial_hp == 10, "PC should start with reduced HP"

    utterance = Utterance(text="I drink my healing potion", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "healing_potion", "method": "consume"},
        demo_state,
        utterance,
        seed=12345,  # Fixed seed for consistent dice rolls
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check HP increased
    final_hp = demo_state.entities["pc.arin"].hp.current
    assert final_hp > initial_hp, f"HP should increase: {initial_hp} -> {final_hp}"

    # Check item was consumed
    final_inventory = demo_state.entities["pc.arin"].inventory
    assert "healing_potion" not in final_inventory, "Healing potion should be consumed"

    # Check effects were applied
    hp_effects = [e for e in result.effects if e["type"] == "hp"]
    inventory_effects = [e for e in result.effects if e["type"] == "inventory"]

    assert len(hp_effects) == 1, "Should have one HP effect"
    assert hp_effects[0]["delta"] > 0, "HP effect should be positive"
    assert len(inventory_effects) == 1, "Should have one inventory effect"
    assert inventory_effects[0]["delta"] == -1, "Should remove one item"


def test_use_item_poison_vial_on_target(demo_state):
    """Test using poison vial on a target deals damage."""
    initial_hp = demo_state.entities["npc.guard.01"].hp.current

    # Add poison vial to inventory
    demo_state.entities["pc.arin"].inventory.append("poison_vial")

    utterance = Utterance(text="I throw poison at the guard", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {
            "actor": "pc.arin",
            "item_id": "poison_vial",
            "target": "npc.guard.01",
            "method": "consume",
        },
        demo_state,
        utterance,
        seed=54321,  # Fixed seed
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check target took damage
    final_hp = demo_state.entities["npc.guard.01"].hp.current
    assert (
        final_hp < initial_hp
    ), f"Target HP should decrease: {initial_hp} -> {final_hp}"

    # Check item was consumed
    assert "poison_vial" not in demo_state.entities["pc.arin"].inventory


def test_use_item_lantern_activate(demo_state):
    """Test activating a lantern sets lighting tag."""
    # Add lantern to inventory
    demo_state.entities["pc.arin"].inventory.append("lantern")

    utterance = Utterance(text="I light my lantern", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "lantern", "method": "activate"},
        demo_state,
        utterance,
        seed=99999,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check effects include lighting and activation
    tag_effects = [e for e in result.effects if e["type"] == "tag"]
    assert len(tag_effects) >= 1, "Should have tag effects"

    # Lantern should still be in inventory (not consumed)
    assert "lantern" in demo_state.entities["pc.arin"].inventory


def test_use_item_rope_for_mark(demo_state):
    """Test using rope provides a mark/advantage."""
    utterance = Utterance(text="I use my rope", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "rope", "method": "consume"},
        demo_state,
        utterance,
        seed=77777,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check mark effect was applied
    mark_effects = [e for e in result.effects if e["type"] == "mark"]
    assert len(mark_effects) == 1, "Should have one mark effect"
    assert mark_effects[0]["tag"] == "climbing_advantage"

    # Check rope was consumed
    assert "rope" not in demo_state.entities["pc.arin"].inventory


def test_use_item_sword_equip(demo_state):
    """Test equipping a sword applies defensive bonus."""
    # Add sword to inventory
    demo_state.entities["pc.arin"].inventory.append("sword")

    utterance = Utterance(text="I equip my sword", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "sword", "method": "equip"},
        demo_state,
        utterance,
        seed=88888,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check tag and guard effects
    tag_effects = [e for e in result.effects if e["type"] == "tag"]
    guard_effects = [e for e in result.effects if e["type"] == "guard"]

    assert len(tag_effects) >= 1, "Should have tag effects for equipment"
    assert len(guard_effects) >= 1, "Should have guard effects"

    # Sword should still be in inventory (equipped, not consumed)
    assert "sword" in demo_state.entities["pc.arin"].inventory


def test_use_item_scroll_fireball_read(demo_state):
    """Test reading a scroll of fireball deals damage."""
    # Add scroll to inventory
    demo_state.entities["pc.arin"].inventory.append("scroll_fireball")

    utterance = Utterance(text="I read the fireball scroll", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {
            "actor": "pc.arin",
            "item_id": "scroll_fireball",
            "target": "npc.guard.01",
            "method": "read",
        },
        demo_state,
        utterance,
        seed=33333,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check damage effect
    hp_effects = [e for e in result.effects if e["type"] == "hp"]
    assert len(hp_effects) == 1, "Should have one HP effect"
    assert hp_effects[0]["delta"] < 0, "Should deal damage"


def test_use_item_missing_actor(demo_state):
    """Test use_item with missing actor."""
    utterance = Utterance(text="I use an item", actor_id="nonexistent")

    result = validate_and_execute(
        "use_item",
        {"actor": "nonexistent", "item_id": "healing_potion"},
        demo_state,
        utterance,
        seed=11111,
    )

    assert result.ok is False, "Should fail with missing actor"
    assert result.tool_id == "ask_clarifying"
    assert "don't see that character" in result.args["question"]


def test_use_item_missing_item(demo_state):
    """Test use_item with item not in inventory."""
    utterance = Utterance(text="I use a missing item", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "nonexistent_item"},
        demo_state,
        utterance,
        seed=22222,
    )

    assert result.ok is False, "Should fail with missing item"
    assert result.tool_id == "ask_clarifying"
    assert "don't have" in result.args["question"]
    assert "nonexistent_item" in result.args["question"]


def test_use_item_unconscious_actor(demo_state):
    """Test use_item with unconscious actor."""
    # Set actor HP to 0
    from router.game_state import HP

    unconscious_hp = HP(current=0, max=10)
    demo_state.entities["pc.arin"] = demo_state.entities["pc.arin"].model_copy(
        update={"hp": unconscious_hp}
    )

    utterance = Utterance(text="I use an item", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "healing_potion"},
        demo_state,
        utterance,
        seed=33333,
    )

    assert result.ok is False, "Should fail with unconscious actor"
    assert result.tool_id == "ask_clarifying"
    assert "unconscious" in result.args["question"]


def test_use_item_invalid_target(demo_state):
    """Test use_item with invalid target."""
    utterance = Utterance(text="I use potion on invalid target", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "target": "nonexistent_target",
        },
        demo_state,
        utterance,
        seed=44444,
    )

    assert result.ok is False, "Should fail with invalid target"
    assert result.tool_id == "ask_clarifying"
    assert "can't find" in result.args["question"]


def test_use_item_method_mismatch(demo_state):
    """Test use_item with wrong method for item."""
    utterance = Utterance(text="I try to activate a potion", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "activate",  # Wrong method, should be "consume"
        },
        demo_state,
        utterance,
        seed=55555,
    )

    assert result.ok is False, "Should fail with method mismatch"
    assert result.tool_id == "ask_clarifying"
    assert "should be used with method" in result.args["question"]


def test_use_item_insufficient_charges(demo_state):
    """Test use_item with more charges than available."""
    utterance = Utterance(text="I overuse my potion", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "charges": 5,  # More than the 1 charge available
        },
        demo_state,
        utterance,
        seed=66666,
    )

    assert result.ok is False, "Should fail with insufficient charges"
    assert result.tool_id == "ask_clarifying"
    assert "only has" in result.args["question"]
    assert "charges" in result.args["question"]


def test_use_item_dice_rolling(demo_state):
    """Test that dice expressions in item effects are properly rolled."""
    # Create a test item definition with dice
    from router.validator import Validator
    import random

    validator = Validator()

    # Test the dice rolling function directly
    random.seed(12345)
    result1 = validator._roll_dice_expression("2d4+2", random)
    assert isinstance(result1, int), "Should return integer"
    assert 4 <= result1 <= 10, "2d4+2 should be between 4 and 10"

    # Test negative dice
    result2 = validator._roll_dice_expression("-1d6", random)
    assert isinstance(result2, int), "Should return integer"
    assert -6 <= result2 <= -1, "-1d6 should be between -6 and -1"

    # Test complex expression
    result3 = validator._roll_dice_expression("3d6+1-1d4", random)
    assert isinstance(result3, int), "Should return integer"


def test_use_item_unknown_item_fallback(demo_state):
    """Test that unknown items get reasonable default behavior."""
    # Add unknown item to inventory
    demo_state.entities["pc.arin"].inventory.append("mystery_item")

    utterance = Utterance(text="I use my mystery item", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "mystery_item"},
        demo_state,
        utterance,
        seed=77777,
    )

    assert (
        result.ok is True
    ), f"use_item should succeed with unknown item: {result.error_message}"
    assert result.facts["item_id"] == "mystery_item"
    assert result.facts["method"] == "consume"  # Default method

    # Should consume the item even if it has no effects
    inventory_effects = [e for e in result.effects if e["type"] == "inventory"]
    assert len(inventory_effects) == 1, "Should consume unknown item"
    assert "mystery_item" not in demo_state.entities["pc.arin"].inventory


def test_use_item_inventory_effect_registration():
    """Test that inventory effect is properly registered."""
    from router.effects import get_registered_effects

    registered_effects = get_registered_effects()
    assert "inventory" in registered_effects, "inventory effect should be registered"


def test_use_item_narration_hint_structure(demo_state):
    """Test that use_item narration hints have proper structure."""
    # First, reduce PC's HP so healing can have an effect
    from router.game_state import HP

    damaged_hp = HP(current=15, max=20)  # Reduce from full HP
    demo_state.entities["pc.arin"] = demo_state.entities["pc.arin"].model_copy(
        update={"hp": damaged_hp}
    )

    utterance = Utterance(text="I drink my healing potion", actor_id="pc.arin")

    result = validate_and_execute(
        "use_item",
        {"actor": "pc.arin", "item_id": "healing_potion"},
        demo_state,
        utterance,
        seed=88888,
    )

    assert result.ok is True, f"use_item should succeed: {result.error_message}"

    # Check narration hint structure
    hint = result.narration_hint
    assert "summary" in hint, "Should have summary"
    assert "tone_tags" in hint, "Should have tone_tags"
    assert "mentioned_entities" in hint, "Should have mentioned_entities"
    assert "mentioned_items" in hint, "Should have mentioned_items"
    assert "effects_summary" in hint, "Should have effects_summary"
    assert "item" in hint, "Should have item details"

    assert "item" in hint["tone_tags"], "Should have 'item' tone tag"
    assert "healing_potion" in hint["mentioned_items"], "Should mention the item"
    assert "pc.arin" in hint["mentioned_entities"], "Should mention the actor"


def test_get_info_execution(demo_state):
    """Test get_info tool execution."""
    utterance = Utterance(text="What do I see here?", actor_id="pc.arin")

    result = validate_and_execute(
        "get_info",
        {
            "actor": "pc.arin",
            "target": "pc.arin",
            "topic": "zone",
            "detail_level": "brief",
        },
        demo_state,
        utterance,
        seed=22222,
    )

    assert result.ok is True, f"get_info should succeed: {result.error_message}"
    assert result.tool_id == "get_info"
    # Should contain zone information in new format
    expected_keys = [
        "topic",
        "zone_id",
        "name",
        "entities",
        "adjacent_zones",
    ]
    for key in expected_keys:
        assert key in result.facts, f"get_info should return {key}"

    # Check specific values
    assert result.facts["topic"] == "zone"
    assert result.facts["zone_id"] == "courtyard"


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


def test_fallback_outcomes_all_social_intents(demo_state):
    """Test that fallback outcomes include all social interaction intents."""
    from unittest.mock import patch
    from router.validator import Validator

    # Mock file loading to force fallback outcomes
    with patch("builtins.open", side_effect=FileNotFoundError("Mocked file not found")):
        validator = Validator()
        fallback = validator._get_fallback_outcomes()

        # Verify all expected social intents are present
        expected_intents = [
            "persuade",
            "intimidate",
            "deceive",
            "charm",
            "comfort",
            "request",
            "distract",
        ]

        assert "intents" in fallback
        for intent in expected_intents:
            assert (
                intent in fallback["intents"]
            ), f"Missing fallback for intent: {intent}"

            # Verify each intent has proper outcome structure
            intent_data = fallback["intents"][intent]
            assert "outcomes" in intent_data

            expected_outcomes = ["crit_success", "success", "partial", "fail"]
            for outcome in expected_outcomes:
                assert (
                    outcome in intent_data["outcomes"]
                ), f"Missing {outcome} for {intent}"
                assert "effects" in intent_data["outcomes"][outcome]


def test_fallback_outcomes_work_when_json_fails(demo_state):
    """Test that talk works with fallback outcomes when social_outcomes.json fails to load."""
    from unittest.mock import patch
    from router.validator import Validator

    # Mock file loading to force fallback outcomes
    with patch("builtins.open", side_effect=FileNotFoundError("Mocked file not found")):
        # Create a fresh Validator instance inside the patched block
        # so it actually uses the fallback path
        test_validator = Validator()

        # Test each social intent with fallback outcomes
        intents_to_test = [
            "intimidate",
            "deceive",
            "charm",
            "comfort",
            "request",
            "distract",
        ]

        for intent in intents_to_test:
            args = {
                "actor": "pc.arin",
                "target": "npc.guard.01",  # Use correct entity ID from demo_state
                "intent": intent,
                "style": 2,
                "domain": "d6",
                "dc_hint": 12,
            }

            utterance = Utterance(text=f"I {intent} the guard", actor_id="pc.arin")
            result = test_validator.validate_and_execute(
                "talk", args, demo_state, utterance, seed=42
            )

            # Should succeed even with fallback outcomes
            assert (
                result.ok is True
            ), f"Talk with {intent} should work with fallback outcomes"
            assert result.facts["intent"] == intent
            assert result.facts["outcome"] in [
                "crit_success",
                "success",
                "partial",
                "fail",
            ]


def test_empty_targets_list_prevents_indexerror(demo_state):
    """Test that empty targets list is handled gracefully without IndexError."""
    from router.validator import Validator

    validator = Validator()

    # Test with None target by calling _execute_talk directly to bypass schema validation
    args = {
        "actor": "pc.arin",
        "target": None,
        "intent": "persuade",
        "style": 2,
        "domain": "d6",
        "dc_hint": 12,
    }

    utterance = Utterance(text="I persuade nobody", actor_id="pc.arin")
    result = validator._execute_talk(args, demo_state, utterance, seed=42)

    assert result.ok is False, "Should fail gracefully with no target"
    assert result.tool_id == "ask_clarifying"
    assert "Who are you trying to talk to?" in result.args["question"]
    assert result.error_message == "No target specified for talk action"


def test_empty_target_list_prevents_indexerror(demo_state):
    """Test that empty target list is handled gracefully without IndexError."""
    from router.validator import Validator

    validator = Validator()

    # Test with empty list target by calling _execute_talk directly to bypass schema validation
    args = {
        "actor": "pc.arin",
        "target": [],
        "intent": "persuade",
        "style": 2,
        "domain": "d6",
        "dc_hint": 12,
    }

    utterance = Utterance(text="I persuade nobody", actor_id="pc.arin")
    result = validator._execute_talk(args, demo_state, utterance, seed=42)

    assert result.ok is False, "Should fail gracefully with empty target list"
    assert result.tool_id == "ask_clarifying"
    assert "Who are you trying to talk to?" in result.args["question"]
    assert result.error_message == "No target specified for talk action"


def test_scene_target_validation_allows_scene_effects(demo_state):
    """Test that effects with target='scene' are accepted by validator."""
    from router.validator import Validator
    from router.tool_catalog import Effect

    validator = Validator()

    # Create a scene-targeted tag effect
    scene_effect = Effect(type="tag", target="scene", add="combat_active")

    # Validate the effect - should not return an error
    error = validator._validate_effect(scene_effect, demo_state)
    assert error is None, f"Scene-targeted effect should be valid, got error: {error}"


def test_global_target_validation_allows_global_effects(demo_state):
    """Test that effects with target='global' are accepted by validator."""
    from router.validator import Validator
    from router.tool_catalog import Effect

    validator = Validator()

    # Create a global-targeted tag effect
    global_effect = Effect(type="tag", target="global", add="day_cycle")

    # Validate the effect - should not return an error
    error = validator._validate_effect(global_effect, demo_state)
    assert error is None, f"Global-targeted effect should be valid, got error: {error}"


def test_clock_target_validation_allows_targetless_clock_effects(demo_state):
    """Test that clock effects without entity targets are accepted."""
    from router.validator import Validator
    from router.tool_catalog import Effect

    validator = Validator()

    # Create a clock effect that targets a clock rather than an entity
    clock_effect = Effect(
        type="clock", target="clock.alarm_bell", id="alarm_bell", delta=5
    )

    # Validate the effect - should not return an error
    error = validator._validate_effect(clock_effect, demo_state)
    assert error is None, f"Clock effect should be valid, got error: {error}"


def test_scene_snapshot_captures_scene_tags_and_pending_effects(demo_state):
    """Test that scene tags and pending_effects are captured in snapshots."""
    from router.validator import Validator
    from router.tool_catalog import Effect

    validator = Validator()

    # Set up initial scene state
    demo_state.scene.tags = {"alert_level": 1, "combat_active": True}
    demo_state.scene.pending_effects = [
        {"type": "hp", "target": "pc.arin", "delta": -1}
    ]

    # Create effects that would modify scene structures
    effects = [
        Effect(type="tag", target="scene", add="new_tag"),
        Effect(type="timed", target="pc.arin", delta=5, after_rounds=3),
    ]

    # Create snapshot
    snapshot = validator._create_snapshot(demo_state, effects)

    # Verify scene structures are captured
    assert "scene_tags" in snapshot, "Scene tags should be captured in snapshot"
    assert (
        "scene_pending_effects" in snapshot
    ), "Scene pending_effects should be captured in snapshot"

    # Verify the captured values match original
    assert snapshot["scene_tags"] == {"alert_level": 1, "combat_active": True}
    assert len(snapshot["scene_pending_effects"]) == 1
    assert snapshot["scene_pending_effects"][0]["type"] == "hp"


def test_scene_rollback_restores_scene_structures(demo_state):
    """Test that scene tags and pending_effects are restored during rollback."""
    from router.validator import Validator
    from router.tool_catalog import Effect

    validator = Validator()

    # Set up initial scene state
    original_tags = {"alert_level": 1, "combat_active": True}
    original_pending = [{"type": "hp", "target": "pc.arin", "delta": -1}]
    demo_state.scene.tags = original_tags.copy()
    demo_state.scene.pending_effects = original_pending.copy()

    # Create snapshot
    effects = [Effect(type="tag", target="scene", add="new_tag")]
    snapshot = validator._create_snapshot(demo_state, effects)

    # Simulate scene mutations (what would happen during effect application)
    demo_state.scene.tags["new_tag"] = True
    demo_state.scene.tags["alert_level"] = 3
    demo_state.scene.pending_effects.append(
        {"type": "clock", "id": "timer", "delta": 2}
    )

    # Verify mutations happened
    assert demo_state.scene.tags != original_tags
    assert len(demo_state.scene.pending_effects) != len(original_pending)

    # Rollback
    validator._rollback_state(demo_state, snapshot)

    # Verify scene structures are restored
    assert (
        demo_state.scene.tags == original_tags
    ), "Scene tags should be restored to original state"
    assert (
        demo_state.scene.pending_effects == original_pending
    ), "Scene pending_effects should be restored to original state"


def test_transactional_rollback_handles_scene_mutations(demo_state):
    """Test that scene mutations are properly rolled back when later effects fail in transactional mode."""
    from router.validator import Validator
    from router.tool_catalog import Effect
    from router.game_state import Utterance

    validator = Validator()

    # Set up initial scene state
    original_tags = {"alert_level": 0}
    original_pending = []
    demo_state.scene.tags = original_tags.copy()
    demo_state.scene.pending_effects = original_pending.copy()

    # Create effects for apply_effects tool
    effects_data = [
        # This scene effect should be valid and would mutate scene.tags
        {"type": "tag", "target": "scene", "add": "alarm_triggered"},
        # This entity effect should be valid
        {"type": "hp", "target": "pc.arin", "delta": -5},
        # This should be invalid and cause rollback
        {"type": "hp", "target": "nonexistent.entity", "delta": -10},
    ]

    # Use validate_and_execute with apply_effects tool to trigger rollback
    utterance = Utterance(text="Test transactional rollback", actor_id="pc.arin")

    result = validate_and_execute(
        "apply_effects",
        {"effects": effects_data, "mode": "strict"},
        demo_state,
        utterance,
    )

    # Should fail due to invalid target and state should be rolled back
    assert result.ok is False, "Should have failed due to invalid target"
    assert (
        demo_state.scene.tags == original_tags
    ), "Scene tags should be rolled back after failed transaction"
    assert (
        demo_state.scene.pending_effects == original_pending
    ), "Scene pending_effects should be rolled back after failed transaction"


if __name__ == "__main__":
    # Run pytest when script is executed directly
    pytest.main([__file__, "-v"])
