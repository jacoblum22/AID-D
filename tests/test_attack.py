"""
Test script for the Attack tool.

This tests the full attack mechanics including Style+Domain rolling,
damage calculation, mark consumption, and all outcome bands.
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, HP, Utterance
from router.validator import validate_and_execute


@pytest.fixture
def attack_state():
    """Create a game state set up for attack testing."""

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

    # Create entities - PC and NPC in same zone for attacking
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["npc.guard"],
            style_bonus=0,  # No mark initially
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=15, max=20),
            visible_actors=["pc.arin"],
            style_bonus=0,  # No mark initially
        ),
        "npc.guard2": NPC(
            id="npc.guard2",
            name="Guard2",
            type="npc",
            current_zone="threshold",  # Different zone, not visible
            hp=HP(current=10, max=20),
            visible_actors=[],
        ),
        "npc.marked_guard": NPC(
            id="npc.marked_guard",
            name="Marked Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["pc.arin"],
            style_bonus=2,  # Has mark
        ),
    }

    return GameState(
        entities=entities,
        zones=zones,
        current_actor="pc.arin",
        clocks={},
        pending_action=None,
    )


class TestAttackBasics:
    """Test basic attack functionality."""

    def test_attack_hit_basic(self, attack_state):
        """Test a basic successful attack."""
        # Force a predictable success: high style, low DC
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 3,
            "domain": "d6",
            "dc_hint": 8,  # Low DC for guaranteed hit
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack the guard", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        assert result.tool_id == "attack"
        assert "outcome" in result.facts
        assert result.facts["outcome"] in ["success", "crit_success"]

        # Should have damage effect
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        assert len(hp_effects) == 1
        assert hp_effects[0]["target"] == "npc.guard"
        assert hp_effects[0]["delta"] < 0  # Negative for damage

    def test_attack_miss(self, attack_state):
        """Test a missed attack."""
        # Force a miss: low style, high DC
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 0,
            "domain": "d4",
            "dc_hint": 20,  # High DC for likely miss
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack poorly", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=1)

        assert result.ok == True
        assert result.facts["outcome"] == "fail"
        assert result.facts["applied_damage"] == 0

        # Should have no damage effects
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        assert len(hp_effects) == 0

    def test_attack_with_mark_consumption(self, attack_state):
        """Test attack that consumes a mark for bonus."""
        # Set up marked target
        attack_state.entities["pc.arin"].visible_actors = ["npc.marked_guard"]

        args = {
            "actor": "pc.arin",
            "target": "npc.marked_guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "consume_mark": True,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack the marked guard", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["mark_consumed"] == True

        # Should have mark removal effect
        mark_effects = [e for e in result.effects if e["type"] == "mark"]
        assert len(mark_effects) == 1
        assert mark_effects[0]["target"] == "npc.marked_guard"
        assert mark_effects[0]["remove"] == True

    def test_attack_no_mark_consumption(self, attack_state):
        """Test attack that doesn't consume mark even when available."""
        attack_state.entities["pc.arin"].visible_actors = ["npc.marked_guard"]

        args = {
            "actor": "pc.arin",
            "target": "npc.marked_guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "consume_mark": False,  # Don't consume
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack without using mark", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        assert result.facts["mark_consumed"] == False

        # Should have no mark removal effect
        mark_effects = [e for e in result.effects if e["type"] == "mark"]
        assert len(mark_effects) == 0


class TestAttackOutcomes:
    """Test different attack outcome bands."""

    def test_critical_success(self, attack_state):
        """Test critical success outcome."""
        # High style + low DC to force crit
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 3,
            "domain": "d8",
            "dc_hint": 8,  # Low DC within valid range
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack critically", actor_id="pc.arin")
        # Try multiple seeds to find a crit (or force with d20=20 scenario)
        result = validate_and_execute("attack", args, attack_state, utterance, seed=123)

        assert result.ok == True
        # Should have enhanced damage for crit
        if result.facts["outcome"] == "crit_success":
            assert (
                result.facts["applied_damage"] >= 2
            )  # At least base damage + some crit bonus
            assert "crit" in str(result.narration_hint["dice"]["damage_dice"])

    def test_partial_success(self, attack_state):
        """Test partial success (graze) outcome."""
        # Medium style, medium-high DC to get partial
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 16,  # High enough to force partial
            "damage_expr": "2d4",  # Multiple dice to test halving
        }

        utterance = Utterance(text="I attack with difficulty", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=50)

        assert result.ok == True
        if result.facts["outcome"] == "partial":
            # Damage should be halved
            total_rolled = sum(
                [
                    d
                    for d in result.narration_hint["dice"]["damage_dice"]
                    if isinstance(d, int)
                ]
            )
            expected_damage = total_rolled // 2
            assert result.facts["applied_damage"] == expected_damage
            assert result.facts["raw_damage"] == total_rolled

    def test_advantage_disadvantage(self, attack_state):
        """Test advantage and disadvantage modifiers."""
        # Test advantage
        args_adv = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "adv_style_delta": 1,  # Advantage
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack with advantage", actor_id="pc.arin")
        result_adv = validate_and_execute(
            "attack", args_adv, attack_state, utterance, seed=42
        )

        assert result_adv.ok == True
        assert result_adv.narration_hint["dice"]["effective_style"] == 2  # 1 + 1

        # Test disadvantage
        args_dis = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 2,
            "domain": "d6",
            "dc_hint": 12,
            "adv_style_delta": -1,  # Disadvantage
            "damage_expr": "1d6",
        }

        result_dis = validate_and_execute(
            "attack", args_dis, attack_state, utterance, seed=42
        )

        assert result_dis.ok == True
        assert result_dis.narration_hint["dice"]["effective_style"] == 1  # 2 - 1


class TestAttackDamage:
    """Test damage calculation mechanics."""

    def test_damage_expressions(self, attack_state):
        """Test different damage expressions."""
        expressions = ["1d6", "1d6+1", "2d4"]

        for expr in expressions:
            args = {
                "actor": "pc.arin",
                "target": "npc.guard",
                "style": 3,
                "domain": "d6",
                "dc_hint": 8,  # Ensure hit with valid range
                "damage_expr": expr,
            }

            utterance = Utterance(text=f"I attack with {expr}", actor_id="pc.arin")
            result = validate_and_execute(
                "attack", args, attack_state, utterance, seed=42
            )

            assert result.ok == True
            if result.facts["outcome"] != "fail":
                assert result.facts["applied_damage"] > 0
                assert len(result.narration_hint["dice"]["damage_dice"]) > 0

    def test_damage_bounds(self, attack_state):
        """Test damage calculation doesn't go negative."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 0,
            "domain": "d4",
            "dc_hint": 22,  # High DC within valid range to force miss
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I miss completely", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=1)

        assert result.ok == True
        assert result.facts["applied_damage"] == 0
        assert result.facts["outcome"] == "fail"


class TestAttackValidation:
    """Test attack validation and error handling."""

    def test_invalid_actor(self, attack_state):
        """Test attack with non-existent actor."""
        args = {
            "actor": "nonexistent.actor",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack", actor_id="nonexistent.actor")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "attacker" in result.args["question"].lower()

    def test_invalid_target(self, attack_state):
        """Test attack with non-existent target."""
        args = {
            "actor": "pc.arin",
            "target": "nonexistent.target",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack nothing", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "target" in result.args["question"].lower()

    def test_invisible_target(self, attack_state):
        """Test attack on target not in visible_actors."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard2",  # In different zone, not visible
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack invisible target", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        assert "see" in result.args["question"].lower()

    def test_invalid_domain(self, attack_state):
        """Test attack with invalid domain format."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "invalid",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack with bad dice", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        # Schema validation catches this before my custom error handling
        assert "try something else" in result.args["question"].lower()


class TestAttackNarration:
    """Test attack narration and hints."""

    def test_narration_hint_structure(self, attack_state):
        """Test that narration hints have proper structure."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 2,
            "domain": "d6",
            "dc_hint": 12,
            "weapon": "sword",
            "damage_expr": "1d6+1",
        }

        utterance = Utterance(text="I swing my sword", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        hint = result.narration_hint

        # Check required fields
        assert "summary" in hint
        assert "dice" in hint
        assert "outcome" in hint
        assert "applied_damage" in hint
        assert "raw_damage" in hint
        assert "tone_tags" in hint
        assert "salient_entities" in hint

        # Check dice details
        dice = hint["dice"]
        assert "d20" in dice
        assert "style" in dice
        assert "total" in dice
        assert "dc" in dice
        assert "margin" in dice

        # Check entities mentioned
        assert "pc.arin" in hint["salient_entities"]
        assert "npc.guard" in hint["salient_entities"]

    def test_outcome_specific_summaries(self, attack_state):
        """Test that different outcomes generate appropriate summaries."""
        base_args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "weapon": "axe",
            "damage_expr": "1d6",
        }

        # Test different DC levels to get different outcomes
        dc_levels = [8, 12, 18, 22]  # Valid range that should give different outcomes

        for dc in dc_levels:
            args = {**base_args, "dc_hint": dc}
            utterance = Utterance(text="I attack", actor_id="pc.arin")
            result = validate_and_execute(
                "attack", args, attack_state, utterance, seed=42
            )

            assert result.ok == True
            summary = result.narration_hint["summary"]
            outcome = result.facts["outcome"]

            # Summary should mention the weapon and be appropriate for outcome
            assert "axe" in summary.lower()

            if outcome == "fail":
                assert "miss" in summary.lower()
            if outcome in ["success", "crit_success"]:
                assert "damage" in summary.lower() or "hit" in summary.lower()


class TestAttackImprovements:
    """Test recent improvements to attack system."""

    def test_dead_target_validation(self, attack_state):
        """Test that attacking dead targets is prevented by preconditions."""
        # Set target to 0 HP
        dead_guard = attack_state.entities["npc.guard"].model_copy(
            update={"hp": HP(current=0, max=20)}
        )
        attack_state.entities["npc.guard"] = dead_guard

        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack dead target", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        # Should fail due to preconditions (dead targets can't be attacked)
        assert result.ok == False
        assert result.tool_id == "ask_clarifying"
        # The precondition check prevents this tool from being available
        assert "try something else" in result.args["question"].lower()

    def test_partial_damage_tracking(self, attack_state):
        """Test that partial attacks track both raw and applied damage."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 1,
            "domain": "d6",
            "dc_hint": 15,  # Higher DC to potentially get partial
            "damage_expr": "2d4",  # Multiple dice for clear halving
        }

        utterance = Utterance(text="I attack for partial", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=50)

        assert result.ok == True
        if result.facts["outcome"] == "partial":
            # Should have both raw and applied damage
            assert "raw_damage" in result.facts
            assert "applied_damage" in result.facts
            assert result.facts["applied_damage"] == result.facts["raw_damage"] // 2
            assert result.facts["applied_damage"] < result.facts["raw_damage"]

    def test_effect_source_tracking(self, attack_state):
        """Test that effects include source and cause information."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 3,
            "domain": "d6",
            "dc_hint": 8,  # Low DC to ensure hit
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack with tracking", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        if result.facts["applied_damage"] > 0:
            # Find the HP effect
            hp_effects = [e for e in result.effects if e["type"] == "hp"]
            assert len(hp_effects) == 1

            hp_effect = hp_effects[0]
            assert "source" in hp_effect
            assert "cause" in hp_effect
            assert hp_effect["source"] == "pc.arin"
            assert hp_effect["cause"] == "attack"

    def test_style_zero_edge_case(self, attack_state):
        """Test that style=0 is legal but weak."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard",
            "style": 0,  # Minimum style
            "domain": "d6",
            "dc_hint": 12,
            "damage_expr": "1d6",
        }

        utterance = Utterance(text="I attack weakly", actor_id="pc.arin")
        result = validate_and_execute("attack", args, attack_state, utterance, seed=42)

        assert result.ok == True
        assert result.narration_hint["dice"]["effective_style"] == 0
        # With style 0, only d20 roll contributes to total


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
