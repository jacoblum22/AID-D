"""
Test script for the apply_effects tool - comprehensive testing.

Tests the sophisticated apply_effects tool implementation including:
- All effect types (hp, guard, mark, clock, position, inventory, tag, resource, meta)
- Transactional rollback
- Error conditions and validation
- Integration with the validator system
- Narration hint generation
"""

import sys
import os
import pytest
from typing import Dict, List, Any

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import (
    GameState,
    PC,
    NPC,
    Zone,
    HP,
    ObjectEntity,
    Scene,
    Utterance,
)
from router.validator import Validator, ToolResult
from router.tool_catalog import Effect, ApplyEffectsArgs


@pytest.fixture
def demo_state():
    """Create a demo game state for testing apply_effects tool."""
    # Create zones
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard.",
            adjacent_zones=["threshold"],
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold.",
            adjacent_zones=["courtyard"],
        ),
    }

    # Create entities
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=15, max=20),
            visible_actors=["npc.guard"],
            inventory=["sword", "potion"],
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["pc.arin"],
            guard=0,
            marks={},
        ),
        "object.door": ObjectEntity(
            id="object.door",
            name="Door",
            type="object",
            current_zone="threshold",
            description="A wooden door.",
        ),
    }

    state = GameState(
        entities=entities,
        zones=zones,
        current_actor="pc.arin",
        clocks={
            "tension": {"value": 3, "max": 10, "source": "scene"},
        },
    )

    return state


@pytest.fixture
def validator():
    """Create a validator instance for testing."""
    return Validator()


class TestEffectValidation:
    """Test effect validation."""

    def test_valid_hp_effect(self, validator, demo_state):
        """Test valid HP effect validation."""
        effect = Effect(type="hp", target="pc.arin", delta=-5, source="test")
        error = validator._validate_effect(effect, demo_state)
        assert error is None

    def test_invalid_hp_target(self, validator, demo_state):
        """Test HP effect with invalid target."""
        effect = Effect(type="hp", target="nonexistent", delta=-5)
        error = validator._validate_effect(effect, demo_state)
        assert "not found" in error

    def test_hp_effect_on_non_creature(self, validator, demo_state):
        """Test HP effect on non-creature entity."""
        effect = Effect(type="hp", target="object.door", delta=-5)
        error = validator._validate_effect(effect, demo_state)
        assert "non-creature" in error

    def test_position_effect_validation(self, validator, demo_state):
        """Test position effect validation."""
        # Valid position effect
        effect = Effect(type="position", target="pc.arin", to="threshold")
        error = validator._validate_effect(effect, demo_state)
        assert error is None

        # Invalid zone
        effect = Effect(type="position", target="pc.arin", to="nonexistent")
        error = validator._validate_effect(effect, demo_state)
        assert "not found" in error

        # Missing 'to' field - now caught by Pydantic validation
        import pytest
        from pydantic_core import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            Effect(type="position", target="pc.arin")  # type: ignore
        assert "position effect requires 'to' field" in str(exc_info.value)

    def test_clock_effect_validation(self, validator, demo_state):
        """Test clock effect validation."""
        # Valid clock effect
        effect = Effect(type="clock", target="pc.arin", id="test_clock", delta=2)
        error = validator._validate_effect(effect, demo_state)
        assert error is None

        # Missing id - now caught by Pydantic validation
        import pytest
        from pydantic_core import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            Effect(type="clock", target="pc.arin", delta=2)  # type: ignore
        assert "clock effect requires 'id' field" in str(exc_info.value)

        # Missing delta - now caught by Pydantic validation
        with pytest.raises(ValidationError) as exc_info:
            Effect(type="clock", target="pc.arin", id="test_clock")  # type: ignore
        assert "clock effect requires 'delta' field" in str(exc_info.value)

    def test_new_effect_validation_features(self, validator, demo_state):
        """Test the new validation features added to Effect class."""
        import pytest
        from pydantic_core import ValidationError

        # Test dice notation validation
        # Valid dice notations should work
        Effect(type="hp", target="pc.arin", delta="2d6+3")
        Effect(type="hp", target="pc.arin", delta="1d4")
        Effect(type="hp", target="pc.arin", delta="+3d8-2")
        Effect(type="hp", target="pc.arin", delta="5")  # Plain number

        # Invalid dice notation should fail
        with pytest.raises(ValidationError) as exc_info:
            Effect(type="hp", target="pc.arin", delta="invalid_dice")  # type: ignore
        assert "Invalid delta format" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Effect(type="hp", target="pc.arin", delta="3d")  # type: ignore  # Missing die size
        assert "Invalid delta format" in str(exc_info.value)

        # Test timing field bounds
        with pytest.raises(ValidationError) as exc_info:
            Effect(type="hp", target="pc.arin", delta=5, after_rounds=-1)  # type: ignore
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Effect(type="hp", target="pc.arin", delta=5, duration=-5)  # type: ignore
        assert "greater than or equal to 0" in str(exc_info.value)

        # Test every_round without duration
        with pytest.raises(ValidationError) as exc_info:
            Effect(type="hp", target="pc.arin", delta=5, every_round=True)  # type: ignore
        assert "every_round=True requires duration > 0" in str(exc_info.value)

        # Test mark/tag requires add or remove
        with pytest.raises(ValidationError) as exc_info:
            Effect(type="mark", target="pc.arin")  # type: ignore
        assert "requires at least one of: 'add', 'remove'" in str(exc_info.value)

        # Valid mark with add
        Effect(type="mark", target="pc.arin", add="blessed")

        # Valid mark with remove
        Effect(type="mark", target="pc.arin", remove="cursed")

        # Valid mark with both
        Effect(type="mark", target="pc.arin", add="blessed", remove="cursed")

    def test_apply_effects_args_validation(self, validator, demo_state):
        """Test ApplyEffectsArgs validation including seed bounds."""
        import pytest
        from pydantic_core import ValidationError
        from router.tool_catalog import ApplyEffectsArgs, Effect

        # Valid args
        valid_effect = Effect(type="hp", target="pc.arin", delta=5)
        args = ApplyEffectsArgs(
            effects=[valid_effect], transaction_mode="strict", seed=42
        )
        assert args.seed == 42

        # Test negative seed validation
        with pytest.raises(ValidationError) as exc_info:
            ApplyEffectsArgs(effects=[valid_effect], seed=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Test empty effects list
        with pytest.raises(ValidationError) as exc_info:
            ApplyEffectsArgs(effects=[])
        assert "at least 1 item" in str(exc_info.value)

        # Test valid transaction modes
        valid_modes = ["strict", "partial", "best_effort"]
        for mode in valid_modes:
            ApplyEffectsArgs(effects=[valid_effect], transaction_mode=mode)  # type: ignore

    def test_typed_effect_log_and_pending_models(self, validator, demo_state):
        """Test that the new typed models for effect logs and pending effects work correctly."""
        from router.game_state import EffectLogEntry, PendingEffect, Scene
        from router.tool_catalog import Effect

        # Test EffectLogEntry creation and validation
        effect_dict = {"type": "hp", "target": "pc.arin", "delta": -5}
        log_entry = EffectLogEntry(
            effect=effect_dict,
            before={"hp": {"current": 15, "max": 15}},
            after={"hp": {"current": 10, "max": 15}},
            ok=True,
            actor="test_actor",
            seed=12345,
            impact_level=5,
            resolved_delta=-5,
        )

        assert log_entry.effect == effect_dict
        assert log_entry.ok is True
        assert log_entry.actor == "test_actor"
        assert log_entry.impact_level == 5

        # Test PendingEffect creation and validation
        pending_effect = PendingEffect(
            effect=effect_dict,
            trigger_round=10,
            scheduled_at=5,
            id="test_pending_effect_1",
            actor="test_actor",
            seed=54321,
        )

        assert pending_effect.trigger_round == 10
        assert pending_effect.scheduled_at == 5
        assert pending_effect.id == "test_pending_effect_1"
        assert pending_effect.effect == effect_dict

        # Test Scene with typed fields
        scene = Scene()

        # Test FIFO queue behavior documentation
        # Add multiple pending effects
        scene.pending_effects.append(
            PendingEffect(
                effect={"type": "hp", "target": "pc.arin", "delta": 1},
                trigger_round=8,
                scheduled_at=5,
                id="effect_1",
            )
        )
        scene.pending_effects.append(
            PendingEffect(
                effect={"type": "hp", "target": "pc.arin", "delta": 2},
                trigger_round=10,
                scheduled_at=5,
                id="effect_2",
            )
        )

        # Verify FIFO queue structure
        assert len(scene.pending_effects) == 2
        assert scene.pending_effects[0].trigger_round == 8
        assert scene.pending_effects[1].trigger_round == 10

        # Test effect log
        scene.last_effect_log.append(log_entry)
        assert len(scene.last_effect_log) == 1
        assert scene.last_effect_log[0].actor == "test_actor"

        # Test validation catches invalid data
        import pytest
        from pydantic_core import ValidationError

        # Required fields should still be validated - effect is required
        with pytest.raises(ValidationError):
            EffectLogEntry()  # type: ignore  # Missing required effect field

        # PendingEffect missing required fields should fail
        with pytest.raises(ValidationError):
            PendingEffect(effect={})  # type: ignore  # Missing trigger_round, scheduled_at, and id


class TestEffectApplication:
    """Test individual effect application functions."""

    def test_apply_hp_effect(self, validator, demo_state):
        """Test HP effect application."""
        effect = Effect(type="hp", target="pc.arin", delta=-5, source="test")
        log = validator._apply_hp_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["hp"] == 15
        assert log["after"]["hp"] == 10
        assert demo_state.entities["pc.arin"].hp.current == 10

    def test_apply_hp_effect_clamps_at_zero(self, validator, demo_state):
        """Test HP effect clamps at zero."""
        effect = Effect(type="hp", target="pc.arin", delta=-25, source="test")
        log = validator._apply_hp_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["hp"] == 15
        assert log["after"]["hp"] == 0
        assert demo_state.entities["pc.arin"].hp.current == 0

    def test_apply_hp_effect_clamps_at_max(self, validator, demo_state):
        """Test HP effect clamps at max."""
        effect = Effect(type="hp", target="pc.arin", delta=10, source="test")
        log = validator._apply_hp_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["hp"] == 15
        assert log["after"]["hp"] == 20  # Clamped at max
        assert demo_state.entities["pc.arin"].hp.current == 20

    def test_apply_guard_effect(self, validator, demo_state):
        """Test guard effect application."""
        effect = Effect(type="guard", target="npc.guard", delta=3, source="test")
        log = validator._apply_guard_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["guard"] == 0
        assert log["after"]["guard"] == 3
        assert demo_state.entities["npc.guard"].guard == 3

    def test_apply_position_effect(self, validator, demo_state):
        """Test position effect application."""
        effect = Effect(type="position", target="pc.arin", to="threshold")
        log = validator._apply_position_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["zone"] == "courtyard"
        assert log["after"]["zone"] == "threshold"
        assert demo_state.entities["pc.arin"].current_zone == "threshold"

    def test_apply_mark_effect_add(self, validator, demo_state):
        """Test mark effect addition."""
        effect = Effect(type="mark", target="npc.guard", add="fear", source="pc.arin")
        log = validator._apply_mark_effect(effect, demo_state)

        assert log["ok"] is True
        assert "fear" in demo_state.entities["npc.guard"].marks
        assert demo_state.entities["npc.guard"].marks["fear"]["source"] == "pc.arin"

    def test_apply_mark_effect_remove(self, validator, demo_state):
        """Test mark effect removal."""
        # First add a mark
        demo_state.entities["npc.guard"].marks["fear"] = {"source": "test"}

        effect = Effect(type="mark", target="npc.guard", remove="fear")
        log = validator._apply_mark_effect(effect, demo_state)

        assert log["ok"] is True
        assert "fear" not in demo_state.entities["npc.guard"].marks

    def test_apply_inventory_effect_add(self, validator, demo_state):
        """Test inventory effect addition."""
        effect = Effect(type="inventory", target="pc.arin", id="new_item", delta=2)
        log = validator._apply_inventory_effect(effect, demo_state)

        assert log["ok"] is True
        assert demo_state.entities["pc.arin"].inventory.count("new_item") == 2

    def test_apply_inventory_effect_remove(self, validator, demo_state):
        """Test inventory effect removal."""
        effect = Effect(type="inventory", target="pc.arin", id="sword", delta=-1)
        log = validator._apply_inventory_effect(effect, demo_state)

        assert log["ok"] is True
        assert "sword" not in demo_state.entities["pc.arin"].inventory

    def test_apply_clock_effect_new(self, validator, demo_state):
        """Test clock effect on new clock."""
        effect = Effect(type="clock", target="pc.arin", id="new_clock", delta=3)
        log = validator._apply_clock_effect(effect, demo_state)

        assert log["ok"] is True
        assert "new_clock" in demo_state.clocks
        assert demo_state.clocks["new_clock"]["value"] == 3

    def test_apply_clock_effect_existing(self, validator, demo_state):
        """Test clock effect on existing clock."""
        effect = Effect(type="clock", target="pc.arin", id="tension", delta=2)
        log = validator._apply_clock_effect(effect, demo_state)

        assert log["ok"] is True
        assert log["before"]["value"] == 3
        assert log["after"]["value"] == 5
        assert demo_state.clocks["tension"]["value"] == 5

    def test_apply_tag_effect_entity(self, validator, demo_state):
        """Test tag effect on entity."""
        effect = Effect(type="tag", target="pc.arin", add="blessed", note="divine")
        log = validator._apply_tag_effect(effect, demo_state)

        assert log["ok"] is True
        assert demo_state.entities["pc.arin"].tags["blessed"] == "divine"

    def test_apply_tag_effect_scene(self, validator, demo_state):
        """Test tag effect on scene."""
        effect = Effect(type="tag", target="scene", add="combat", note="active")
        log = validator._apply_tag_effect(effect, demo_state)

        assert log["ok"] is True
        assert demo_state.scene.tags["combat"] == "active"


class TestApplyEffectsTool:
    """Test the complete apply_effects tool."""

    def test_successful_single_effect(self, validator, demo_state):
        """Test applying a single effect successfully."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": -5}],
            "actor": "test",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert result.facts["applied"] == 1
        assert result.facts["skipped"] == 0
        assert len(result.effects) == 1
        assert demo_state.entities["pc.arin"].hp.current == 10

    def test_successful_multiple_effects(self, validator, demo_state):
        """Test applying multiple effects successfully."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -5},
                {"type": "guard", "target": "npc.guard", "delta": 2},
                {"type": "position", "target": "pc.arin", "to": "threshold"},
            ],
            "actor": "test",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert result.facts["applied"] == 3
        assert result.facts["skipped"] == 0
        assert len(result.effects) == 3

        # Check all effects were applied
        assert demo_state.entities["pc.arin"].hp.current == 10
        assert demo_state.entities["npc.guard"].guard == 2
        assert demo_state.entities["pc.arin"].current_zone == "threshold"

    def test_validation_failure(self, validator, demo_state):
        """Test effect validation failure."""
        args = {
            "effects": [{"type": "hp", "target": "nonexistent", "delta": -5}],
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is False
        assert "not found" in result.error_message
        assert demo_state.entities["pc.arin"].hp.current == 15  # Unchanged

    def test_empty_effects_list(self, validator, demo_state):
        """Test empty effects list."""
        args = {"effects": [], "transactional": True}

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is False
        assert "No effects provided" in result.error_message

    def test_invalid_effect_schema(self, validator, demo_state):
        """Test invalid effect schema - unknown types are skipped, not failed."""
        args = {
            "effects": [{"type": "invalid_type", "target": "pc.arin"}],
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Transaction succeeds but unknown effect is skipped
        assert result.ok is True
        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 1
        assert "Unknown effect type" in result.effects[0]["error"]

    def test_narration_hint_generation(self, validator, demo_state):
        """Test narration hint generation."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -5},
                {"type": "hp", "target": "npc.guard", "delta": 3},
            ],
            "actor": "test",
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        hint = result.narration_hint
        assert "Arin" in hint["summary"]
        assert "Guard" in hint["summary"]
        assert "damage" in hint["tone_tags"]
        assert "healing" in hint["tone_tags"]

    def test_effect_logging(self, validator, demo_state):
        """Test that effects are logged to scene."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": -5}],
            "actor": "test",
        }

        utterance = Utterance(text="test", actor_id="test")

        initial_log_count = len(demo_state.scene.last_effect_log)
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert len(demo_state.scene.last_effect_log) == initial_log_count + 1

        log_entry = demo_state.scene.last_effect_log[-1]
        assert log_entry["ok"] is True
        assert log_entry["effect"]["type"] == "hp"

    def test_enhanced_logging_fields(self, validator, demo_state):
        """Test that enhanced logging fields are populated correctly."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": -5}],
            "actor": "test_actor",
            "seed": 42,
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        log_entry = result.effects[0]

        # Check enhanced fields
        assert log_entry["seed"] == 42
        assert log_entry["actor"] == "test_actor"
        assert log_entry["round"] == demo_state.scene.round
        assert "rolled" in log_entry
        assert "summary" in log_entry
        assert "impact_level" in log_entry

        # Check summary generation
        assert "Arin" in log_entry["summary"]
        assert "damage" in log_entry["summary"] or "took" in log_entry["summary"]

        # Check impact level
        assert log_entry["impact_level"] == 5  # abs(delta)

        # Check timestamp format
        assert "T" in log_entry["timestamp"]  # ISO format

    def test_effect_type_registry_system(self, validator, demo_state):
        """Test that the effect type registry system works correctly."""
        # Test that all effect types are registered
        registered_types = validator.get_registered_effect_types()
        expected_types = [
            "hp",
            "guard",
            "position",
            "mark",
            "inventory",
            "clock",
            "tag",
            "resource",
            "meta",
        ]

        for effect_type in expected_types:
            assert (
                effect_type in registered_types
            ), f"Effect type {effect_type} not registered"

        # Test registry dispatch works for a known effect
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": -3}],
            "actor": "test_registry",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert demo_state.entities["pc.arin"].hp.current == 12  # 15 - 3

        # Test that unknown effect types are handled gracefully
        args_unknown = {
            "effects": [{"type": "unknown_effect", "target": "pc.arin", "delta": -1}],
            "actor": "test_registry",
            "transactional": True,
        }

        result_unknown = validator._execute_apply_effects(
            args_unknown, demo_state, utterance, 12345
        )
        assert result_unknown.ok is True  # Transaction succeeds but effect is skipped
        assert result_unknown.facts["applied"] == 0  # No effects applied
        assert result_unknown.facts["skipped"] == 1  # Unknown effect skipped
        assert "Unknown effect type" in result_unknown.effects[0]["error"]

        # Test dynamic registration of new effect type
        def test_custom_effect(self, effect, state, actor=None, seed=None):
            return validator._create_enhanced_log_entry(
                effect=effect,
                before={"custom": "before"},
                after={"custom": "after"},
                ok=True,
                actor=actor,
                seed=seed,
                state=state,
            )

        # Add method dynamically
        validator.test_custom_effect = test_custom_effect.__get__(
            validator, type(validator)
        )
        validator.register_effect_handler("custom", "test_custom_effect")

        # Test the custom effect works
        assert "custom" in validator.get_registered_effect_types()

        # Cleanup: Remove the custom effect handler and method to avoid affecting other tests
        if (
            hasattr(validator, "_effect_handlers")
            and "custom" in validator._effect_handlers
        ):
            del validator._effect_handlers["custom"]
        if hasattr(validator, "test_custom_effect"):
            delattr(validator, "test_custom_effect")

    def test_dice_expressions_in_effects(self, validator, demo_state):
        """Test that dice expressions in effect deltas are properly rolled and logged."""
        args = {
            "effects": [
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": "1d4+1",
                },  # Dice expression
                {
                    "type": "guard",
                    "target": "npc.guard",
                    "delta": "2d6",
                },  # Dice expression
                {"type": "resource", "target": "pc.arin", "id": "mana", "delta": "1d6"},
            ],
            "actor": "test_dice",
            "seed": 42,  # Fixed seed for deterministic results
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert result.facts["applied"] == 3
        assert len(result.effects) == 3

        # Check that dice were rolled and logged
        for effect_log in result.effects:
            if effect_log["effect"]["delta"] in ["1d4+1", "2d6", "1d6"]:
                # Should have dice log entries
                assert "rolled" in effect_log
                assert len(effect_log["rolled"]) > 0

                # Check dice log structure
                dice_entry = effect_log["rolled"][0]
                assert "expression" in dice_entry
                assert "parts" in dice_entry
                assert "total" in dice_entry
                assert "individual_rolls" in dice_entry

                # Verify the expression was parsed
                assert dice_entry["expression"] == effect_log["effect"]["delta"]

    def test_deterministic_dice_replay(self, validator, demo_state):
        """Test that dice expressions give same results with same seed."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": "2d6+2"}],
            "actor": "test_replay",
            "seed": 123,
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        # Run same effect twice with same seed
        result1 = validator._execute_apply_effects(args, demo_state, utterance, 123)

        # Reset HP for second test
        demo_state.entities["pc.arin"].hp.current = 15

        result2 = validator._execute_apply_effects(args, demo_state, utterance, 123)

        # Both should succeed
        assert result1.ok is True
        assert result2.ok is True

        # Dice results should be identical
        dice1 = result1.effects[0]["rolled"][0]
        dice2 = result2.effects[0]["rolled"][0]

        assert dice1["total"] == dice2["total"]
        assert dice1["individual_rolls"] == dice2["individual_rolls"]


class TestTransactionModes:
    """Test different transaction modes: strict, partial, best_effort."""

    def test_strict_mode_fails_on_any_error(self, validator, demo_state):
        """Test that strict mode fails entire transaction on any effect error."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": 5},  # Valid effect
                {"type": "hp", "target": "nonexistent", "delta": 3},  # Invalid target
                {"type": "hp", "target": "npc.guard", "delta": 2},  # Valid effect
            ],
            "transaction_mode": "strict",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Strict mode should fail entirely
        assert result.ok is False
        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 3  # All effects skipped due to failure
        assert result.facts["transaction_mode"] == "strict"
        assert (
            "not found" in result.error_message.lower()
        )  # Changed from "failed" to "not found"

        # State should be rolled back - HP unchanged
        assert demo_state.entities["pc.arin"].hp.current == 15

    def test_partial_mode_continues_on_error(self, validator, demo_state):
        """Test that partial mode continues processing after individual effect errors."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": 5},  # Valid effect
                {"type": "hp", "target": "nonexistent", "delta": 3},  # Invalid target
                {"type": "hp", "target": "npc.guard", "delta": 2},  # Valid effect
            ],
            "transaction_mode": "partial",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Partial mode should succeed with partial application
        assert result.ok is True
        assert result.facts["applied"] == 2  # Two valid effects applied
        assert result.facts["skipped"] == 1  # One effect failed
        assert result.facts["transaction_mode"] == "partial"
        assert result.facts["total_effects"] == 3

        # Valid effects should have been applied
        assert demo_state.entities["pc.arin"].hp.current == 20  # 15 + 5
        assert (
            demo_state.entities["npc.guard"].hp.current == 20
        )  # 20 + 2, but capped at max_hp (20)

    def test_partial_mode_fails_if_no_effects_applied(self, validator, demo_state):
        """Test that partial mode fails if zero effects were successfully applied."""
        args = {
            "effects": [
                {"type": "hp", "target": "nonexistent1", "delta": 3},
                {"type": "hp", "target": "nonexistent2", "delta": 5},
            ],
            "transaction_mode": "partial",
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Partial mode should fail if no effects succeeded
        assert result.ok is False
        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 2
        assert result.facts["transaction_mode"] == "partial"

    def test_best_effort_mode_always_succeeds(self, validator, demo_state):
        """Test that best_effort mode always succeeds even if all effects fail."""
        args = {
            "effects": [
                {"type": "hp", "target": "nonexistent1", "delta": 3},
                {"type": "hp", "target": "nonexistent2", "delta": 5},
            ],
            "transaction_mode": "best_effort",
            "transactional": False,  # Best effort usually doesn't use transactions
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Best effort always succeeds
        assert result.ok is True
        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 2
        assert result.facts["transaction_mode"] == "best_effort"

    def test_best_effort_with_mixed_results(self, validator, demo_state):
        """Test best_effort mode with mix of successful and failed effects."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": 3},  # Valid
                {"type": "hp", "target": "nonexistent", "delta": 5},  # Invalid
                {
                    "type": "position",
                    "target": "pc.arin",
                    "to": "threshold",
                },  # Valid - threshold exists
            ],
            "transaction_mode": "best_effort",
            "transactional": False,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Best effort succeeds with partial application
        assert result.ok is True
        assert result.facts["applied"] == 2
        assert result.facts["skipped"] == 1
        assert result.facts["transaction_mode"] == "best_effort"

        # Successful effects should be applied
        assert demo_state.entities["pc.arin"].hp.current == 18  # 15 + 3
        assert demo_state.entities["pc.arin"].current_zone == "threshold"

    def test_transaction_mode_default_is_strict(self, validator, demo_state):
        """Test that transaction_mode defaults to 'strict' when not specified."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": 5}],
            # No transaction_mode specified
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert result.facts["transaction_mode"] == "strict"  # Should default to strict


class TestAuditTrail:
    """Test human-readable audit trail generation."""

    def test_audit_trail_single_hp_effect(self, validator, demo_state):
        """Test audit trail for single HP effect."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": 5}],
            "actor": "test_gm",
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        # Check that audit trail was stored in scene
        assert hasattr(demo_state.scene, "last_diff_summary")
        assert demo_state.scene.last_diff_summary is not None

        # Verify format: [Round X] [actor] entity.field: before → after
        audit_trail = demo_state.scene.last_diff_summary
        assert "[Round 1]" in audit_trail
        assert "[test_gm]" in audit_trail
        assert "Arin.hp: 15 → 20" in audit_trail

    def test_audit_trail_multiple_effects(self, validator, demo_state):
        """Test audit trail for multiple effects."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": 3},
                {"type": "position", "target": "pc.arin", "to": "threshold"},
                {"type": "guard", "target": "npc.guard", "delta": 2},
            ],
            "actor": "test_player",
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        audit_trail = demo_state.scene.last_diff_summary

        # Should contain all changes
        assert "Arin.hp: 15 → 18" in audit_trail
        assert "Arin.zone: courtyard → threshold" in audit_trail
        assert "Guard.guard: 0 → 2" in audit_trail
        assert "[test_player]" in audit_trail

    def test_audit_trail_mark_effects(self, validator, demo_state):
        """Test audit trail for mark addition/removal."""
        # First add a mark to the guard so we can remove it later
        demo_state.entities["npc.guard"].marks = {"confidence": {"source": "initial"}}

        args = {
            "effects": [
                {
                    "type": "mark",
                    "target": "npc.guard",
                    "add": "fear",
                    "source": "spell",
                },
                {
                    "type": "mark",
                    "target": "npc.guard",
                    "remove": "confidence",
                    "source": "spell",
                },
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        audit_trail = demo_state.scene.last_diff_summary

        # Should show mark changes
        assert "Guard.marks: +fear" in audit_trail
        assert "Guard.marks: -confidence" in audit_trail

    def test_audit_trail_inventory_effects(self, validator, demo_state):
        """Test audit trail for inventory changes."""
        args = {
            "effects": [
                {"type": "inventory", "target": "pc.arin", "id": "potion", "delta": 2},
                {"type": "inventory", "target": "pc.arin", "id": "sword", "delta": -1},
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        audit_trail = demo_state.scene.last_diff_summary

        # Should show inventory changes
        assert "Arin.inventory: +2 potion" in audit_trail
        assert "Arin.inventory: -1 sword" in audit_trail

    def test_audit_trail_no_changes(self, validator, demo_state):
        """Test audit trail when no visible changes occur."""
        # Try to remove a mark that doesn't exist
        args = {
            "effects": [
                {"type": "mark", "target": "npc.guard", "remove": "nonexistent"}
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        audit_trail = demo_state.scene.last_diff_summary

        # Should indicate no visible changes
        assert "No visible changes" in audit_trail

    def test_audit_trail_failed_effects_excluded(self, validator, demo_state):
        """Test that failed effects are excluded from audit trail."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": 5},  # Valid
                {
                    "type": "hp",
                    "target": "nonexistent",
                    "delta": 3,
                },  # Invalid - should be excluded
            ],
            "transaction_mode": "best_effort",  # Allow partial success
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        audit_trail = demo_state.scene.last_diff_summary

        # Should only show successful changes
        assert "Arin.hp: 15 → 20" in audit_trail
        assert "nonexistent" not in audit_trail


class TestReactiveEffects:
    """Test cascading/reactive effects system."""

    def test_hp_zero_triggers_unconscious(self, validator, demo_state):
        """Test that HP dropping to 0 or below triggers unconscious tag."""
        # Reduce PC HP to 0
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -15}
            ],  # 15 - 15 = 0
            "actor": "test_gm",
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Check that unconscious tag was added by reactive effect
        entity = demo_state.entities["pc.arin"]
        assert "unconscious" in entity.tags

        # Verify reactive effect appears in logs
        reactive_logs = [
            log for log in result.effects if log.get("actor") == "test_gm_reaction"
        ]
        assert len(reactive_logs) == 1
        assert reactive_logs[0]["effect"]["type"] == "tag"
        assert reactive_logs[0]["effect"]["add"] == "unconscious"

    def test_hp_critical_triggers_bloodied(self, validator, demo_state):
        """Test that HP dropping to 3 or below triggers bloodied tag."""
        # Reset PC state to clean slate
        demo_state.entities["pc.arin"].tags = {}
        demo_state.entities["pc.arin"].hp.current = 15

        # Reduce PC HP from 15 to 2
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -13}
            ],  # 15 - 13 = 2
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Check that bloodied tag was added by reactive effect
        entity = demo_state.entities["pc.arin"]
        assert "bloodied" in entity.tags

        # Should NOT trigger unconscious (HP > 0)
        assert "unconscious" not in entity.tags

    def test_fear_mark_triggers_guard_penalty(self, validator, demo_state):
        """Test that adding fear mark triggers guard penalty."""
        args = {
            "effects": [
                {
                    "type": "mark",
                    "target": "npc.guard",
                    "add": "fear",
                    "source": "spell",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Check that guard was reduced by reactive effect
        entity = demo_state.entities["npc.guard"]
        assert entity.guard == -1  # 0 - 1 = -1 from fear reaction

        # Verify reactive effect appears in logs
        reactive_logs = [
            log
            for log in result.effects
            if log.get("actor") and "_reaction" in log.get("actor", "")
        ]
        assert len(reactive_logs) == 1
        assert reactive_logs[0]["effect"]["type"] == "guard"
        assert reactive_logs[0]["effect"]["delta"] == -1

    def test_confidence_mark_triggers_guard_bonus(self, validator, demo_state):
        """Test that adding confidence mark triggers guard bonus."""
        args = {
            "effects": [
                {
                    "type": "mark",
                    "target": "npc.guard",
                    "add": "confidence",
                    "source": "spell",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Check that guard was increased by reactive effect
        entity = demo_state.entities["npc.guard"]
        assert entity.guard == 1  # 0 + 1 = 1 from confidence reaction

    def test_multiple_reactive_effects(self, validator, demo_state):
        """Test multiple reactive effects triggered simultaneously."""
        args = {
            "effects": [
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": -15,
                },  # Should trigger unconscious
                {
                    "type": "mark",
                    "target": "npc.guard",
                    "add": "fear",
                    "source": "spell",
                },  # Should trigger guard penalty
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Check both reactive effects occurred
        pc = demo_state.entities["pc.arin"]
        assert "unconscious" in pc.tags

        guard = demo_state.entities["npc.guard"]
        assert guard.guard == -1

        # Should have 2 reactive effect logs
        reactive_logs = [
            log
            for log in result.effects
            if log.get("actor") and "_reaction" in log.get("actor", "")
        ]
        assert len(reactive_logs) == 2

    def test_no_reactive_effects_on_failed_primary(self, validator, demo_state):
        """Test that reactive effects don't trigger from failed primary effects."""
        args = {
            "effects": [
                {"type": "hp", "target": "nonexistent", "delta": -15}
            ],  # Invalid target
            "transaction_mode": "best_effort",  # Allow to continue
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Should have no reactive effects since primary effect failed
        reactive_logs = [
            log
            for log in result.effects
            if log.get("actor") and "_reaction" in log.get("actor", "")
        ]
        assert len(reactive_logs) == 0

    def test_reactive_effects_count_in_applied_total(self, validator, demo_state):
        """Test that reactive effects are counted separately from primary effects."""
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -15}
            ]  # Should trigger unconscious
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Primary effects: 1 applied
        assert result.facts["applied"] == 1
        assert result.facts["total_effects"] == 1  # Original count

        # Reactive effects: 1 applied
        assert result.facts["reactive_applied"] == 1
        assert result.facts["reactive_failed"] == 0

    def test_second_order_reactions(self, validator, demo_state):
        """Test that reactive effects can trigger further reactions."""
        # Reset PC state and start with PC at 4 HP to test cascading reactions
        demo_state.entities["pc.arin"].tags = {}
        demo_state.entities["pc.arin"].hp.current = 4

        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -2}
            ]  # 4 - 2 = 2, should trigger bloodied
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Should have bloodied tag from reactive effect
        entity = demo_state.entities["pc.arin"]
        assert "bloodied" in entity.tags

        # Check that we have both primary and reactive logs
        primary_logs = [
            log
            for log in result.effects
            if not (log.get("actor") and "_reaction" in log.get("actor", ""))
        ]
        reactive_logs = [
            log
            for log in result.effects
            if log.get("actor") and "_reaction" in log.get("actor", "")
        ]

        assert len(primary_logs) == 1  # HP reduction
        assert len(reactive_logs) == 1  # Bloodied tag addition


class TestConditionalAndTimedEffects:
    """Test conditional effects and timed effects system."""

    def test_conditional_effect_hp_condition_met(self, validator, demo_state):
        """Test conditional effect triggers when HP condition is met."""
        # Reduce PC HP to 5 first
        demo_state.entities["pc.arin"].hp.current = 5

        args = {
            "effects": [
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "desperate",
                    "condition": "target.hp.current < 10",
                    "source": "conditional",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Condition should be met (5 < 10), so tag should be added
        entity = demo_state.entities["pc.arin"]
        assert "desperate" in entity.tags

        assert result.facts["applied"] == 1

    def test_conditional_effect_hp_condition_not_met(self, validator, demo_state):
        """Test conditional effect skipped when HP condition is not met."""
        # PC has full HP (15)
        args = {
            "effects": [
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "desperate",
                    "condition": "target.hp.current < 10",
                    "source": "conditional",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True  # Operation succeeds but effect skipped

        # Condition not met (15 < 10 is false), so tag should NOT be added
        entity = demo_state.entities["pc.arin"]
        assert "desperate" not in entity.tags

        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 1

    def test_conditional_effect_guard_condition(self, validator, demo_state):
        """Test conditional effect based on guard value."""
        # Set guard to -1
        demo_state.entities["npc.guard"].guard = -1

        args = {
            "effects": [
                {
                    "type": "tag",
                    "target": "npc.guard",
                    "add": "vulnerable",
                    "condition": "target.guard < 0",
                    "source": "conditional",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Condition met (-1 < 0), so tag should be added
        entity = demo_state.entities["npc.guard"]
        assert "vulnerable" in entity.tags

    def test_timed_effect_scheduling(self, validator, demo_state):
        """Test that timed effects are scheduled correctly."""
        args = {
            "effects": [
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": -5,
                    "after_rounds": 2,
                    "source": "poison",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True

        # Effect should be scheduled, not applied immediately
        entity = demo_state.entities["pc.arin"]
        assert entity.hp.current == 15  # HP unchanged

        # Should have 1 pending effect
        assert result.facts["pending_effects_count"] == 1
        assert (
            result.facts["scheduled"] == 1
        )  # Scheduling counts as scheduled, not applied

        # Check pending effects queue
        assert len(demo_state.scene.pending_effects) == 1
        pending = demo_state.scene.pending_effects[0]
        assert pending.trigger_round == demo_state.scene.round + 2

    def test_timed_effect_triggering(self, validator, demo_state):
        """Test that timed effects trigger at the right time."""
        # Schedule a timed effect first
        args = {
            "effects": [
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": -3,
                    "after_rounds": 1,
                    "source": "poison",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        # Schedule the effect
        result1 = validator._execute_apply_effects(args, demo_state, utterance, 12345)
        assert result1.ok is True
        assert demo_state.entities["pc.arin"].hp.current == 15  # No immediate effect

        # Advance the round
        demo_state.scene.round += 1

        # Apply new effects (this should trigger pending effects)
        args2 = {
            "effects": [
                {"type": "tag", "target": "pc.arin", "add": "tested", "source": "test"}
            ]
        }

        result2 = validator._execute_apply_effects(args2, demo_state, utterance, 54321)
        assert result2.ok is True

        # Timed effect should have triggered
        entity = demo_state.entities["pc.arin"]
        assert entity.hp.current == 12  # 15 - 3 = 12 from timed effect
        assert "tested" in entity.tags  # Regular effect also applied

        # Should have processed 1 timed effect
        assert result2.facts["timed_applied"] == 1
        assert result2.facts["applied"] == 1  # New effect

        # Pending effects queue should be empty now
        assert result2.facts["pending_effects_count"] == 0

    def test_multiple_timed_effects_different_timing(self, validator, demo_state):
        """Test multiple timed effects with different trigger times."""
        # Reset PC state to clean slate
        demo_state.entities["pc.arin"].tags = {}
        demo_state.entities["pc.arin"].hp.current = 15
        demo_state.scene.pending_effects = []
        demo_state.scene.round = 1

        args = {
            "effects": [
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": -2,
                    "after_rounds": 1,
                    "source": "poison",
                    "note": "early",
                },
                {
                    "type": "hp",
                    "target": "pc.arin",
                    "delta": -3,
                    "after_rounds": 3,
                    "source": "curse",
                    "note": "late",
                },
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)
        assert result.ok is True

        # Both effects scheduled, none applied immediately
        assert result.facts["pending_effects_count"] == 2
        assert result.facts["scheduled"] == 2
        assert result.facts["applied"] == 0

        # Advance 1 round - first effect should trigger
        demo_state.scene.round += 1

        args2 = {"effects": []}
        result2 = validator._execute_apply_effects(args2, demo_state, utterance, 54321)

        assert demo_state.entities["pc.arin"].hp.current == 13  # 15 - 2 = 13
        assert result2.facts["timed_applied"] == 1
        assert result2.facts["pending_effects_count"] == 1  # One left

        # Advance 2 more rounds - second effect should trigger
        demo_state.scene.round += 2
        args3 = {"effects": []}
        result3 = validator._execute_apply_effects(args3, demo_state, utterance, 98765)

        assert demo_state.entities["pc.arin"].hp.current == 10  # 13 - 3 = 10
        assert result3.facts["timed_applied"] == 1
        assert result3.facts["pending_effects_count"] == 0  # All done

    def test_conditional_and_timed_combined(self, validator, demo_state):
        """Test effect with both condition and timing."""
        # Reset PC state to clean slate
        demo_state.entities["pc.arin"].tags = {}
        demo_state.entities["pc.arin"].hp.current = 15
        demo_state.scene.pending_effects = []
        demo_state.scene.round = 1

        # PC starts with full HP (15)
        args = {
            "effects": [
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "healing_soon",
                    "condition": "target.hp.current < 20",  # Should be met (15 < 20)
                    "after_rounds": 2,
                    "source": "conditional_timed",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)
        assert result.ok is True

        # Effect should be scheduled (condition was met)
        assert result.facts["pending_effects_count"] == 1
        assert (
            "healing_soon" not in demo_state.entities["pc.arin"].tags
        )  # Not applied yet

        # Advance rounds and trigger
        demo_state.scene.round += 2
        args2 = {"effects": []}
        result2 = validator._execute_apply_effects(args2, demo_state, utterance, 54321)

        # Timed effect should have triggered
        assert "healing_soon" in demo_state.entities["pc.arin"].tags
        assert result2.facts["timed_applied"] == 1

    def test_conditional_effect_fails_not_scheduled(self, validator, demo_state):
        """Test that effects with unmet conditions are not scheduled."""
        args = {
            "effects": [
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "never_happens",
                    "condition": "target.hp.current > 100",  # Will not be met (15 > 100 = false)
                    "after_rounds": 1,
                    "source": "conditional_timed",
                }
            ]
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)
        assert result.ok is True

        # Effect should be skipped, not scheduled
        assert result.facts["pending_effects_count"] == 0
        assert result.facts["applied"] == 0
        assert result.facts["skipped"] == 1


class TestTransactionalRollback:
    """Test transactional rollback functionality."""

    def test_snapshot_creation(self, validator, demo_state):
        """Test snapshot creation."""
        effects = [
            Effect(type="hp", target="pc.arin", delta=-5),
            Effect(type="guard", target="npc.guard", delta=2),
        ]

        snapshot = validator._create_snapshot(demo_state, effects)

        assert "pc.arin" in snapshot
        assert "npc.guard" in snapshot
        assert snapshot["pc.arin"].hp.current == 15
        assert snapshot["npc.guard"].guard == 0

    def test_rollback_state(self, validator, demo_state):
        """Test state rollback."""
        # Create snapshot
        effects = [Effect(type="hp", target="pc.arin", delta=-5)]
        snapshot = validator._create_snapshot(demo_state, effects)

        # Modify state
        demo_state.entities["pc.arin"].hp.current = 5

        # Rollback
        validator._rollback_state(demo_state, snapshot)

        # Check state is restored
        assert demo_state.entities["pc.arin"].hp.current == 15

    def test_transactional_mode_rollback_on_error(self, validator, demo_state):
        """Test that transactional mode rolls back on error."""
        # This test requires modifying the validator to simulate an error mid-transaction
        # For simplicity, we'll test with an invalid second effect

        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": -5},
                {
                    "type": "hp",
                    "target": "nonexistent",
                    "delta": -5,
                },  # This will fail validation
            ],
            "transactional": True,
        }

        utterance = Utterance(text="test", actor_id="test")

        original_hp = demo_state.entities["pc.arin"].hp.current
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Should fail and rollback - HP should be unchanged
        assert result.ok is False
        assert demo_state.entities["pc.arin"].hp.current == original_hp


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_over_heal_clamps_to_max(self, validator, demo_state):
        """Test that over-healing clamps to max HP."""
        args = {
            "effects": [{"type": "hp", "target": "pc.arin", "delta": 50}],
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert demo_state.entities["pc.arin"].hp.current == 20  # Max HP

    def test_inventory_underflow_safe(self, validator, demo_state):
        """Test that removing more items than exist is safe."""
        args = {
            "effects": [
                {
                    "type": "inventory",
                    "target": "pc.arin",
                    "id": "nonexistent",
                    "delta": -5,
                }
            ],
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True  # Should succeed without crashing

    def test_clock_value_clamps(self, validator, demo_state):
        """Test that clock values clamp properly."""
        # Test negative clamp
        args = {
            "effects": [
                {"type": "clock", "target": "pc.arin", "id": "tension", "delta": -10}
            ],
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert demo_state.clocks["tension"]["value"] == 0  # Clamped at 0

    def test_remove_nonexistent_mark_safe(self, validator, demo_state):
        """Test that removing non-existent mark is safe."""
        args = {
            "effects": [
                {"type": "mark", "target": "npc.guard", "remove": "nonexistent"}
            ],
        }

        utterance = Utterance(text="test", actor_id="test")

        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True  # Should succeed without crashing

    def test_conditional_effects(self, validator, demo_state):
        """Test conditional effect evaluation."""
        # Reset PC state for clean test
        demo_state.entities["pc.arin"].hp.current = 15
        demo_state.entities["pc.arin"].tags = {}

        args = {
            "effects": [
                # Should apply - PC has enough HP
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "confident",
                    "value": "Has high HP",
                    "condition": "hp > 10",
                },
                # Should not apply - PC doesn't have low HP
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "desperate",
                    "value": "Has low HP",
                    "condition": "hp <= 5",
                },
            ],
        }

        utterance = Utterance(text="conditional test", actor_id="test")
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        assert result.ok is True
        assert result.facts["applied"] == 1  # Only one effect should apply
        assert result.facts["skipped"] == 1  # One effect should be skipped
        assert demo_state.entities["pc.arin"].tags.get("confident") == "Has high HP"
        assert "desperate" not in demo_state.entities["pc.arin"].tags

    def test_timed_effects(self, validator, demo_state):
        """Test timed effect scheduling and execution."""
        # Reset PC state
        demo_state.entities["pc.arin"].hp.current = 15
        demo_state.entities["pc.arin"].tags = {}
        demo_state.scene.round = 1

        # Schedule timed effects for round 2
        args = {
            "effects": [
                {"type": "hp", "target": "pc.arin", "delta": "-3", "after_rounds": 1},
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "delayed",
                    "value": "Applied later",
                    "after_rounds": 1,
                },
            ],
        }

        utterance = Utterance(text="timed test", actor_id="test")
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # Effects should be scheduled, not applied yet
        assert result.ok is True
        assert result.facts["scheduled"] == 2
        assert result.facts["applied"] == 0
        assert demo_state.entities["pc.arin"].hp.current == 15  # Unchanged
        assert "delayed" not in demo_state.entities["pc.arin"].tags
        assert len(demo_state.scene.pending_effects) == 2

        # Advance to round 2 and trigger timed effects
        demo_state.scene.round = 2
        args2 = {"effects": []}  # Empty effects to trigger pending processing
        result2 = validator._execute_apply_effects(args2, demo_state, utterance, 12345)

        # Timed effects should now be applied
        assert result2.ok is True
        assert result2.facts["timed_applied"] == 2
        assert demo_state.entities["pc.arin"].hp.current == 12  # HP reduced
        assert demo_state.entities["pc.arin"].tags.get("delayed") == "Applied later"
        assert len(demo_state.scene.pending_effects) == 0  # Queue should be empty

    def test_combined_conditional_timed(self, validator, demo_state):
        """Test combination of conditional and timed effects."""
        # Reset state
        demo_state.entities["pc.arin"].hp.current = 8
        demo_state.entities["pc.arin"].tags = {}
        demo_state.scene.round = 1

        args = {
            "effects": [
                # Conditional timed effect - should apply because HP <= 10
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "healing",
                    "value": "Delayed heal",
                    "condition": "hp <= 10",
                    "after_rounds": 1,
                },
                # Conditional immediate effect - should not apply because HP > 5
                {
                    "type": "tag",
                    "target": "pc.arin",
                    "add": "critical",
                    "value": "Very low HP",
                    "condition": "hp <= 5",
                },
            ],
        }

        utterance = Utterance(text="combined test", actor_id="test")
        result = validator._execute_apply_effects(args, demo_state, utterance, 12345)

        # One effect scheduled, one skipped
        assert result.ok is True
        assert result.facts["scheduled"] == 1
        assert result.facts["skipped"] == 1
        assert result.facts["applied"] == 0

        # Advance to trigger timed effect
        demo_state.scene.round = 2
        args2 = {"effects": []}
        result2 = validator._execute_apply_effects(args2, demo_state, utterance, 12345)

        assert result2.facts["timed_applied"] == 1
        assert demo_state.entities["pc.arin"].tags.get("healing") == "Delayed heal"
        assert "critical" not in demo_state.entities["pc.arin"].tags


if __name__ == "__main__":
    # Run pytest when script is executed directly
    pytest.main([__file__, "-v"])
