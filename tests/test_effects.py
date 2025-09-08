"""
Test script for the Effects system.

This tests the effect atoms that modify game state, including
all registered effect handlers and edge cases.
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, HP, ObjectEntity, ItemEntity
from router.effects import apply_effects, get_registered_effects, EFFECT_REGISTRY


@pytest.fixture
def demo_state():
    """Create a demo game state for testing effects."""

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
            hp=HP(current=15, max=20),  # Test with non-full HP
            visible_actors=["npc.guard"],
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["pc.arin"],
        ),
        "object.door": ObjectEntity(
            id="object.door",
            name="Door",
            type="object",
            current_zone="threshold",
            description="A wooden door.",
        ),
        "item.sword": ItemEntity(
            id="item.sword",
            name="Sword",
            type="item",
            current_zone="courtyard",
            description="A sharp sword.",
        ),
    }

    return GameState(
        entities=entities,
        zones=zones,
        current_actor="pc.arin",
        clocks={},
        pending_action=None,
    )


class TestHPEffects:
    """Test HP effect handler."""

    def test_hp_positive_delta(self, demo_state):
        """Test healing (positive HP delta)."""
        effects = [{"type": "hp", "target": "pc.arin", "delta": 3}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.hp.current == 18  # 15 + 3
        assert arin.hp.max == 20  # Unchanged

    def test_hp_negative_delta(self, demo_state):
        """Test damage (negative HP delta)."""
        effects = [{"type": "hp", "target": "npc.guard", "delta": -5}]
        apply_effects(demo_state, effects)

        guard = demo_state.entities["npc.guard"]
        assert guard.hp.current == 15  # 20 - 5
        assert guard.hp.max == 20  # Unchanged

    def test_hp_clamp_lower_bound(self, demo_state):
        """Test HP cannot go below 0."""
        effects = [{"type": "hp", "target": "pc.arin", "delta": -30}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.hp.current == 0  # Clamped at 0, not negative
        assert arin.hp.max == 20  # Unchanged

    def test_hp_clamp_upper_bound(self, demo_state):
        """Test HP cannot exceed max (fix from comments)."""
        effects = [{"type": "hp", "target": "pc.arin", "delta": 10}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.hp.current == 20  # Clamped at max, not 25
        assert arin.hp.max == 20  # Unchanged

    def test_hp_exact_max(self, demo_state):
        """Test HP can reach exactly max."""
        effects = [{"type": "hp", "target": "pc.arin", "delta": 5}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.hp.current == 20  # 15 + 5 = exactly max
        assert arin.hp.max == 20

    def test_hp_missing_target_error(self, demo_state):
        """Test error when target doesn't exist (fix from comments)."""
        effects = [{"type": "hp", "target": "nonexistent.entity", "delta": 5}]

        with pytest.raises(
            ValueError, match="HP effect target not found: nonexistent.entity"
        ):
            apply_effects(demo_state, effects)

    def test_hp_non_creature_error(self, demo_state):
        """Test error when applying HP to non-creature entities."""
        effects = [{"type": "hp", "target": "object.door", "delta": 5}]

        with pytest.raises(ValueError, match="hp effect on non-creature: object"):
            apply_effects(demo_state, effects)

    def test_hp_item_error(self, demo_state):
        """Test error when applying HP to item entities."""
        effects = [{"type": "hp", "target": "item.sword", "delta": 5}]

        with pytest.raises(ValueError, match="hp effect on non-creature: item"):
            apply_effects(demo_state, effects)


class TestPositionEffects:
    """Test position effect handler."""

    def test_position_change(self, demo_state):
        """Test moving entity to different zone."""
        effects = [{"type": "position", "target": "pc.arin", "to": "threshold"}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.current_zone == "threshold"

    def test_position_visibility_update(self, demo_state):
        """Test that visibility updates when position changes."""
        # Initially both in courtyard, should see each other
        arin = demo_state.entities["pc.arin"]
        guard = demo_state.entities["npc.guard"]
        assert "npc.guard" in arin.visible_actors
        assert "pc.arin" in guard.visible_actors

        # Move Arin to threshold
        effects = [{"type": "position", "target": "pc.arin", "to": "threshold"}]
        apply_effects(demo_state, effects)

        # Check visibility updated (they shouldn't see each other now)
        arin = demo_state.entities["pc.arin"]
        guard = demo_state.entities["npc.guard"]
        assert "npc.guard" not in arin.visible_actors
        assert "pc.arin" not in guard.visible_actors

    def test_position_invalid_target(self, demo_state):
        """Test position effect with invalid target (silently fails)."""
        effects = [{"type": "position", "target": "nonexistent", "to": "threshold"}]

        # This should not raise an error (unlike HP effects)
        apply_effects(demo_state, effects)

        # Original entities unchanged
        assert demo_state.entities["pc.arin"].current_zone == "courtyard"

    def test_position_invalid_zone(self, demo_state):
        """Test position effect with invalid target zone (silently fails)."""
        effects = [{"type": "position", "target": "pc.arin", "to": "nonexistent_zone"}]

        # This should not raise an error
        apply_effects(demo_state, effects)

        # Entity should remain in original zone
        assert demo_state.entities["pc.arin"].current_zone == "courtyard"


class TestClockEffects:
    """Test clock effect handler."""

    def test_clock_new_clock(self, demo_state):
        """Test creating a new clock."""
        effects = [{"type": "clock", "id": "alarm", "delta": 3}]
        apply_effects(demo_state, effects)

        assert "alarm" in demo_state.clocks
        assert demo_state.clocks["alarm"]["value"] == 3
        assert demo_state.clocks["alarm"]["min"] == 0
        assert demo_state.clocks["alarm"]["max"] == 10  # Default

    def test_clock_increment_existing(self, demo_state):
        """Test incrementing existing clock."""
        # Create clock first
        demo_state.clocks["timer"] = {"value": 5, "min": 0, "max": 10}

        effects = [{"type": "clock", "id": "timer", "delta": 2}]
        apply_effects(demo_state, effects)

        assert demo_state.clocks["timer"]["value"] == 7  # 5 + 2

    def test_clock_decrement(self, demo_state):
        """Test decrementing clock."""
        demo_state.clocks["countdown"] = {"value": 8, "min": 0, "max": 10}

        effects = [{"type": "clock", "id": "countdown", "delta": -3}]
        apply_effects(demo_state, effects)

        assert demo_state.clocks["countdown"]["value"] == 5  # 8 - 3

    def test_clock_clamp_min(self, demo_state):
        """Test clock clamping at minimum."""
        demo_state.clocks["test"] = {"value": 2, "min": 0, "max": 10}

        effects = [{"type": "clock", "id": "test", "delta": -5}]
        apply_effects(demo_state, effects)

        assert demo_state.clocks["test"]["value"] == 0  # Clamped at min

    def test_clock_clamp_max(self, demo_state):
        """Test clock clamping at maximum."""
        demo_state.clocks["test"] = {"value": 8, "min": 0, "max": 10}

        effects = [{"type": "clock", "id": "test", "delta": 5}]
        apply_effects(demo_state, effects)

        assert demo_state.clocks["test"]["value"] == 10  # Clamped at max


class TestGuardEffects:
    """Test guard effect handler."""

    def test_guard_apply(self, demo_state):
        """Test applying guard effect."""
        effects = [{"type": "guard", "target": "pc.arin", "value": 3, "duration": 2}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.guard == 3
        assert arin.guard_duration == 2

    def test_guard_default_duration(self, demo_state):
        """Test guard effect with default duration."""
        effects = [{"type": "guard", "target": "npc.guard", "value": 5}]
        apply_effects(demo_state, effects)

        guard = demo_state.entities["npc.guard"]
        assert guard.guard == 5
        assert guard.guard_duration == 1  # Default

    def test_guard_missing_target(self, demo_state):
        """Test guard effect with missing target (silently fails)."""
        effects = [{"type": "guard", "target": "nonexistent", "value": 3}]

        # Should not raise error
        apply_effects(demo_state, effects)

    def test_guard_non_creature_error(self, demo_state):
        """Test guard effect on non-creature."""
        effects = [{"type": "guard", "target": "object.door", "value": 3}]

        with pytest.raises(ValueError, match="guard effect on non-creature: object"):
            apply_effects(demo_state, effects)


class TestMarkEffects:
    """Test mark effect handler."""

    def test_mark_apply(self, demo_state):
        """Test applying mark effect."""
        effects = [
            {"type": "mark", "target": "pc.arin", "style_bonus": 2, "consumes": False}
        ]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.style_bonus == 2  # 0 + 2
        assert arin.mark_consumes == False

    def test_mark_default_consumes(self, demo_state):
        """Test mark effect with default consumes value."""
        effects = [{"type": "mark", "target": "npc.guard", "style_bonus": 1}]
        apply_effects(demo_state, effects)

        guard = demo_state.entities["npc.guard"]
        assert guard.style_bonus == 1
        assert guard.mark_consumes == True  # Default

    def test_mark_cumulative(self, demo_state):
        """Test that mark effects are cumulative."""
        # Apply first mark
        effects = [{"type": "mark", "target": "pc.arin", "style_bonus": 2}]
        apply_effects(demo_state, effects)

        # Apply second mark
        effects = [{"type": "mark", "target": "pc.arin", "style_bonus": 1}]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.style_bonus == 3  # 2 + 1

    def test_mark_non_creature_error(self, demo_state):
        """Test mark effect on non-creature."""
        effects = [{"type": "mark", "target": "item.sword", "style_bonus": 1}]

        with pytest.raises(ValueError, match="mark effect on non-creature: item"):
            apply_effects(demo_state, effects)


class TestApplyEffects:
    """Test the apply_effects function itself."""

    def test_multiple_effects(self, demo_state):
        """Test applying multiple effects at once."""
        effects = [
            {"type": "hp", "target": "pc.arin", "delta": 2},
            {"type": "position", "target": "pc.arin", "to": "threshold"},
            {"type": "clock", "id": "scene_timer", "delta": 1},
        ]
        apply_effects(demo_state, effects)

        arin = demo_state.entities["pc.arin"]
        assert arin.hp.current == 17  # 15 + 2
        assert arin.current_zone == "threshold"
        assert demo_state.clocks["scene_timer"]["value"] == 1

    def test_unknown_effect_type_error(self, demo_state):
        """Test error on unknown effect type."""
        effects = [{"type": "unknown_effect", "target": "pc.arin"}]

        with pytest.raises(ValueError, match="Unknown effect type: unknown_effect"):
            apply_effects(demo_state, effects)

    def test_missing_effect_type_error(self, demo_state):
        """Test error when effect is missing 'type' field."""
        effects = [{"target": "pc.arin", "delta": 5}]  # Missing "type"

        with pytest.raises(ValueError, match="Effect missing 'type' field"):
            apply_effects(demo_state, effects)

    def test_empty_effects_list(self, demo_state):
        """Test applying empty effects list."""
        original_arin_hp = demo_state.entities["pc.arin"].hp.current

        apply_effects(demo_state, [])

        # Nothing should change
        assert demo_state.entities["pc.arin"].hp.current == original_arin_hp


class TestEffectRegistry:
    """Test the effect registry system."""

    def test_get_registered_effects(self):
        """Test getting list of registered effects."""
        registered = get_registered_effects()

        # Should include all the main effect types
        expected_effects = ["hp", "position", "clock", "guard", "mark"]
        for effect_type in expected_effects:
            assert effect_type in registered

    def test_effect_registry_structure(self):
        """Test that effect registry has proper structure."""
        assert isinstance(EFFECT_REGISTRY, dict)

        # Each registered effect should be callable
        for effect_type, handler in EFFECT_REGISTRY.items():
            assert callable(handler)
            assert isinstance(effect_type, str)


if __name__ == "__main__":
    pytest.main([__file__])
