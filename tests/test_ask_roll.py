"""
Focused test for ask_roll tool - the core dice mechanics of the AI D&D system.

Tests the locked-down rules using real random seeds for deterministic results:
- Roll math: total = d20 + sum(style × d<domain>)
- 4 outcome bands: crit_success, success, partial, fail
- DC derivation from scene tags
- Effect generation for "sneak" action
- ToolResult envelope structure
- Precondition checking for illegal moves

Uses real random seeds discovered through testing for realistic behavior.
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Utterance, Scene
from router.validator import validate_and_execute


def create_test_state(scene_tags=None, adjacent_zones=None):
    """Create a minimal test state for ask_roll testing."""

    if adjacent_zones is None:
        adjacent_zones = ["threshold", "main_hall"]

    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard.",
            adjacent_zones=adjacent_zones,
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold.",
            adjacent_zones=["courtyard"],
        ),
        "main_hall": Zone(
            id="main_hall",
            name="Main Hall",
            description="A grand hall.",
            adjacent_zones=["courtyard"],
        ),
    }

    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            visible_actors=["npc.guard"],
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            visible_actors=["pc.arin"],
        ),
    }

    # Default scene with base_dc=12
    scene = Scene(
        base_dc=12,
        tags=scene_tags
        or {
            "alert": "normal",
            "lighting": "normal",
            "noise": "normal",
            "cover": "some",
        },
    )

    return GameState(
        entities=entities, zones=zones, scene=scene, current_actor="pc.arin"
    )


class TestAskRollMath:
    """Test the core dice math: total = d20 + sum(style × d<domain>)"""

    def test_style_0_no_style_dice(self):
        """Style 0 should roll only d20, no style dice"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 0,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces success with style 0
        )

        assert result.ok
        assert result.narration_hint["dice"]["style"] == []  # No style dice
        assert result.narration_hint["dice"]["style_sum"] == 0
        assert result.narration_hint["dice"]["effective_style"] == 0

    def test_style_1_single_die(self):
        """Style 1 should roll d20 + 1 style die"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces success with style 1
        )

        assert result.ok
        dice = result.narration_hint["dice"]
        assert len(dice["style"]) == 1  # Exactly 1 style die
        assert dice["style_sum"] == sum(dice["style"])
        assert dice["total"] == dice["d20"] + dice["style_sum"]
        assert dice["effective_style"] == 1

    def test_style_3_multiple_dice(self):
        """Style 3 should roll d20 + 3 style dice"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 3,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=1,  # Seed that works with style 3
        )

        assert result.ok
        dice = result.narration_hint["dice"]
        assert len(dice["style"]) == 3  # Exactly 3 style dice
        assert dice["style_sum"] == sum(dice["style"])
        assert dice["total"] == dice["d20"] + dice["style_sum"]
        assert dice["effective_style"] == 3

    def test_different_domains(self):
        """Test different die sizes: d4, d6, d8"""

        # Test d4
        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d4",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=7,  # Seed for d4 test
        )

        assert result.ok
        dice = result.narration_hint["dice"]
        assert len(dice["style"]) == 1
        assert 1 <= dice["style"][0] <= 4  # d4 range

        # Test d6 - create fresh state
        state = create_test_state()
        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed for d6 test
        )

        assert result.ok
        dice = result.narration_hint["dice"]
        assert len(dice["style"]) == 1
        assert 1 <= dice["style"][0] <= 6  # d6 range

        # Test d8 - create fresh state
        state = create_test_state()
        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d8",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=4,  # Seed for d8 test
        )

        assert result.ok
        dice = result.narration_hint["dice"]
        assert len(dice["style"]) == 1
        assert 1 <= dice["style"][0] <= 8  # d8 range


class TestOutcomeBanding:
    """Test the 4 outcome bands based on margin = total - dc"""

    def test_crit_success_margin_5_plus(self):
        """Margin ≥ +5 should be crit_success"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=5,  # Seed that produces crit_success
        )

        assert result.ok
        assert result.facts["outcome"] == "crit_success"
        assert result.facts["margin"] >= 5

    def test_success_margin_0_to_4(self):
        """Margin ≥ 0 but < 5 should be success"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces success
        )

        assert result.ok
        assert result.facts["outcome"] == "success"
        margin = result.facts["margin"]
        assert 0 <= margin < 5

    def test_partial_margin_negative_1_to_3(self):
        """Margin ≥ -3 but < 0 should be partial"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=1,  # Seed that produces partial
        )

        assert result.ok
        assert result.facts["outcome"] == "partial"
        margin = result.facts["margin"]
        assert -3 <= margin < 0

    def test_fail_margin_negative_4_or_less(self):
        """Margin ≤ -4 should be fail"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=2,  # Seed that produces fail
        )

        assert result.ok
        assert result.facts["outcome"] == "fail"
        assert result.facts["margin"] <= -4


class TestDCDerivation:
    """Test DC adjustment from scene tags"""

    def test_dc_decrease_sleepy_guard(self):
        """alert=sleepy should decrease DC for sneak"""
        scene_tags = {
            "alert": "sleepy",
            "lighting": "normal",
            "noise": "normal",
            "cover": "some",
        }

        state = create_test_state(scene_tags=scene_tags)
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                # No dc_hint provided, should derive from scene
            },
            state,
            utterance,
            seed=1,  # Seed for sleepy guard test
        )

        assert result.ok
        # Base DC 12 - 2 for sleepy = 10
        assert result.facts["dc"] == 10
        assert result.facts["outcome"] == "success"  # Should succeed with lower DC

    def test_dc_increase_bright_lighting(self):
        """lighting=bright should increase DC for sneak"""
        scene_tags = {
            "alert": "normal",
            "lighting": "bright",
            "noise": "normal",
            "cover": "some",
        }

        state = create_test_state(scene_tags=scene_tags)
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                # No dc_hint provided, should derive from scene
            },
            state,
            utterance,
            seed=16,  # Seed for bright lighting test
        )

        assert result.ok
        # Base DC 12 + 2 for bright = 14
        assert result.facts["dc"] == 14
        assert result.facts["outcome"] == "success"  # Should still succeed with seed 16


class TestSneakEffects:
    """Test effect generation for 'sneak' action based on outcomes"""

    def test_crit_success_effects(self):
        """crit_success: position change + clock -1"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=5,  # Seed that produces crit_success
        )

        assert result.ok
        assert result.facts["outcome"] == "crit_success"

        # Should have position effect and clock effect
        effect_types = [e["type"] for e in result.effects]
        assert "position" in effect_types
        assert "clock" in effect_types

        # Check position effect
        position_effect = next(e for e in result.effects if e["type"] == "position")
        assert position_effect["target"] == "pc.arin"
        assert position_effect["to"] == "threshold"

        # Check clock effect (delta -1)
        clock_effect = next(e for e in result.effects if e["type"] == "clock")
        assert clock_effect["delta"] == -1

    def test_success_effects(self):
        """success: position change only"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces success
        )

        assert result.ok
        assert result.facts["outcome"] == "success"

        # Should have only position effect
        effect_types = [e["type"] for e in result.effects]
        assert "position" in effect_types
        assert "clock" not in effect_types

        # Check position effect
        position_effect = next(e for e in result.effects if e["type"] == "position")
        assert position_effect["target"] == "pc.arin"
        assert position_effect["to"] == "threshold"

    def test_partial_effects(self):
        """partial: no position change, clock +1"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=1,  # Seed that produces partial
        )

        assert result.ok
        assert result.facts["outcome"] == "partial"

        # Should have only clock effect
        effect_types = [e["type"] for e in result.effects]
        assert "position" not in effect_types
        assert "clock" in effect_types

        # Check clock effect
        clock_effect = next(e for e in result.effects if e["type"] == "clock")
        assert clock_effect["delta"] == 1

    def test_fail_effects(self):
        """fail: clock +2"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=2,  # Seed that produces fail
        )

        assert result.ok
        assert result.facts["outcome"] == "fail"

        # Should have only clock effect
        effect_types = [e["type"] for e in result.effects]
        assert "position" not in effect_types
        assert "clock" in effect_types

        # Check clock effect
        clock_effect = next(e for e in result.effects if e["type"] == "clock")
        assert clock_effect["delta"] == 2


class TestToolResultEnvelope:
    """Test the standardized ToolResult envelope structure"""

    def test_result_envelope_structure(self):
        """Verify all required ToolResult fields are present and correct"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces a clean success
        )

        # Check ToolResult structure
        assert hasattr(result, "ok")
        assert hasattr(result, "tool_id")
        assert hasattr(result, "args")
        assert hasattr(result, "facts")
        assert hasattr(result, "effects")
        assert hasattr(result, "narration_hint")

        assert result.ok is True
        assert result.tool_id == "ask_roll"
        assert isinstance(result.args, dict)
        assert isinstance(result.facts, dict)
        assert isinstance(result.effects, list)
        assert isinstance(result.narration_hint, dict)

    def test_narration_hint_dice_details(self):
        """Verify narration_hint.dice contains all required dice details"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 2,
                "domain": "d6",
                "dc_hint": 14,
            },
            state,
            utterance,
            seed=1,  # Seed that works with style 2
        )

        dice_info = result.narration_hint["dice"]

        assert "d20" in dice_info
        assert "style" in dice_info
        assert "style_sum" in dice_info
        assert "total" in dice_info
        assert "dc" in dice_info
        assert "margin" in dice_info
        assert "effective_style" in dice_info

        # Verify dice math
        assert dice_info["style_sum"] == sum(dice_info["style"])
        assert dice_info["total"] == dice_info["d20"] + dice_info["style_sum"]
        assert dice_info["margin"] == dice_info["total"] - dice_info["dc"]
        assert dice_info["effective_style"] == 2

    def test_narration_hint_summary(self):
        """Verify narration_hint.summary is meaningful"""

        state = create_test_state()
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "threshold",
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed that produces success
        )

        summary = result.narration_hint["summary"]
        assert isinstance(summary, str)
        assert "sneak" in summary.lower()
        assert "succeeded" in summary.lower()  # Should indicate success


class TestPreconditions:
    """Test precondition checking and fallback to ask_clarifying"""

    def test_illegal_zone_target_not_adjacent(self):
        """zone_target not adjacent should return ask_clarifying fallback"""
        # Create state where "forbidden_zone" is not adjacent to courtyard
        state = create_test_state(
            adjacent_zones=["threshold"]
        )  # Only threshold is adjacent
        utterance = Utterance(text="I sneak", actor_id="pc.arin")

        result = validate_and_execute(
            "ask_roll",
            {
                "actor": "pc.arin",
                "action": "sneak",
                "zone_target": "forbidden_zone",  # Not in adjacent_zones
                "style": 1,
                "domain": "d6",
                "dc_hint": 12,
            },
            state,
            utterance,
            seed=3,  # Seed doesn't matter for this test
        )

        # Should return ask_clarifying fallback
        assert result.ok is False
        assert result.tool_id == "ask_clarifying"
        assert "question" in result.args
        assert isinstance(result.error_message, str)


if __name__ == "__main__":
    # Run with pytest for better output
    pytest.main([__file__, "-v"])
