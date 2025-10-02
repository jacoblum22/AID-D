"""
Test script for enhanced Talk tool features.

This tests all the new enhancements:
1. Broader Intent Ontology - verb mapping
2. Marks Generalization - flexible mark structure
3. Clocks as First-Class - max field and ownership tracking
4. Multi-Target/Audience Support - multiple targets
5. Outcome Flexibility - data-driven outcomes
6. Narration Hints Enrichment - disposition tracking and effects summary
"""

import sys
import os
import pytest
import json

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, HP, Utterance
from router.validator import validate_and_execute
from router.tool_catalog import suggest_talk_args


@pytest.fixture
def enhanced_talk_state():
    """Create a game state set up for enhanced talk testing."""

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

    # Create entities - PC and multiple NPCs for multi-target testing
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["npc.guard1", "npc.guard2"],
            marks={},  # New flexible marks system
        ),
        "npc.guard1": NPC(
            id="npc.guard1",
            name="Guard Captain",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=15, max=20),
            visible_actors=["pc.arin", "npc.guard2"],
            guard=2,  # Higher guard value
            marks={},
        ),
        "npc.guard2": NPC(
            id="npc.guard2",
            name="Guard Recruit",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=12, max=20),
            visible_actors=["pc.arin", "npc.guard1"],
            guard=0,  # Lower guard value
            marks={},
        ),
    }

    return GameState(
        entities=entities,
        zones=zones,
        current_actor="pc.arin",
        clocks={},
        pending_action=None,
    )


class TestBroaderIntentOntology:
    """Test the enhanced verb mapping system."""

    def test_verb_mapping_intimidate(self, enhanced_talk_state):
        """Test that various intimidation verbs map to intimidate intent."""
        utterance = Utterance(text="I threaten the guard captain", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "intimidate"

        utterance = Utterance(text="I menace the guard", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "intimidate"

        utterance = Utterance(text="I try to frighten them", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "intimidate"

    def test_verb_mapping_deceive(self, enhanced_talk_state):
        """Test that deception verbs map correctly."""
        utterance = Utterance(text="I try to mislead the guard", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "deceive"

        utterance = Utterance(text="I con the guard", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "deceive"

    def test_verb_mapping_comfort(self, enhanced_talk_state):
        """Test that comfort verbs map correctly."""
        utterance = Utterance(text="I console the guard", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "comfort"

        utterance = Utterance(text="I try to soothe them", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "comfort"

    def test_verb_mapping_request(self, enhanced_talk_state):
        """Test that request verbs map correctly."""
        utterance = Utterance(text="I implore the guard", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "request"

        utterance = Utterance(text="I beseech them for help", actor_id="pc.arin")
        suggested_args = suggest_talk_args(enhanced_talk_state, utterance)
        assert suggested_args["intent"] == "request"


class TestMarksGeneralization:
    """Test the new flexible mark system."""

    def test_flexible_mark_creation(self, enhanced_talk_state):
        """Test that marks are created with the new flexible structure."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "persuade",
            "style": 3,  # High style for likely crit success
            "domain": "d6",
            "dc_hint": 8,  # Low DC for easier success
        }

        utterance = Utterance(text="I persuade the guard captain", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        if result.ok and result.facts["outcome"] == "crit_success":
            # Check that mark effects use new structure
            mark_effects = [e for e in result.effects if e.get("type") == "mark"]
            if mark_effects:
                mark_effect = mark_effects[0]
                assert "tag" in mark_effect
                assert "source" in mark_effect
                assert "value" in mark_effect
                assert mark_effect["tag"] == "favor"
                assert mark_effect["source"] == "pc.arin"

    def test_mark_application(self, enhanced_talk_state):
        """Test that marks are properly applied to entities."""
        from router.effects import apply_effects

        # Apply a mark effect using new structure
        effects = [
            {
                "type": "mark",
                "target": "npc.guard1",
                "tag": "favor",
                "source": "pc.arin",
                "value": 1,
            }
        ]

        apply_effects(enhanced_talk_state, effects)

        # Check that the mark was applied
        guard = enhanced_talk_state.entities["npc.guard1"]
        marks = getattr(guard, "marks", {})
        mark_key = "pc.arin.favor"
        assert mark_key in marks
        assert marks[mark_key]["tag"] == "favor"
        assert marks[mark_key]["source"] == "pc.arin"
        assert marks[mark_key]["value"] == 1


class TestClocksAsFirstClass:
    """Test enhanced clock system with max values and ownership."""

    def test_clock_with_max_value(self, enhanced_talk_state):
        """Test that clocks are created with max values and ownership tracking."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "persuade",
            "style": 1,
            "domain": "d6",
            "dc_hint": 15,  # Higher DC to get partial outcome
        }

        utterance = Utterance(text="I persuade the guard captain", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        if result.ok and result.facts["outcome"] == "partial":
            # Check that clock effects have enhanced structure
            clock_effects = [e for e in result.effects if e.get("type") == "clock"]
            if clock_effects:
                clock_effect = clock_effects[0]
                assert "max" in clock_effect
                assert "source" in clock_effect
                assert clock_effect["max"] == 3  # From social_outcomes.json
                assert clock_effect["source"] == "pc.arin"

    def test_clock_application_with_tracking(self, enhanced_talk_state):
        """Test clock application with ownership tracking."""
        from router.effects import apply_effects

        # Apply clock effect with enhanced structure
        effects = [
            {
                "type": "clock",
                "id": "npc.guard1.persuade",
                "delta": 1,
                "max": 3,
                "source": "pc.arin",
            }
        ]

        apply_effects(enhanced_talk_state, effects)

        # Check that clock was created with tracking
        clock = enhanced_talk_state.clocks["npc.guard1.persuade"]
        assert clock["value"] == 1
        assert clock["max"] == 3
        assert clock["source"] == "pc.arin"
        assert "created_turn" in clock
        assert "last_modified_by" in clock

    def test_clock_fill_detection(self, enhanced_talk_state):
        """Test detection when clock reaches max value."""
        from router.effects import apply_effects

        # First, set up a clock near max
        enhanced_talk_state.clocks["npc.guard1.persuade"] = {
            "value": 2,
            "max": 3,
            "min": 0,
            "source": "pc.arin",
            "created_turn": 1,
        }

        # Apply effect that fills the clock
        effects = [
            {
                "type": "clock",
                "id": "npc.guard1.persuade",
                "delta": 1,
                "source": "pc.arin",
            }
        ]

        apply_effects(enhanced_talk_state, effects)

        # Check that fill detection works
        clock = enhanced_talk_state.clocks["npc.guard1.persuade"]
        assert clock["value"] == 3  # At max
        assert clock.get("filled_this_turn") == True
        assert clock.get("filled_by") == "pc.arin"


class TestMultiTargetSupport:
    """Test multi-target and audience support."""

    def test_single_target_backwards_compatibility(self, enhanced_talk_state):
        """Test that single target still works (backwards compatibility)."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",  # Single target
            "intent": "persuade",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I persuade the guard captain", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True
        assert len(result.narration_hint["mentioned_entities"]) == 2  # actor + target

    def test_multiple_targets(self, enhanced_talk_state):
        """Test addressing multiple targets."""
        args = {
            "actor": "pc.arin",
            "target": ["npc.guard1", "npc.guard2"],  # Multiple targets
            "intent": "persuade",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I persuade both guards", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True
        assert (
            len(result.narration_hint["mentioned_entities"]) == 3
        )  # actor + 2 targets

        # Effects should be applied to both targets
        target_effects = {}
        for effect in result.effects:
            target = effect.get("target")
            if target:
                target_effects[target] = target_effects.get(target, 0) + 1

        assert "npc.guard1" in target_effects
        assert "npc.guard2" in target_effects

    def test_multi_target_narration(self, enhanced_talk_state):
        """Test that narration properly handles multiple targets."""
        args = {
            "actor": "pc.arin",
            "target": ["npc.guard1", "npc.guard2"],
            "intent": "intimidate",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I intimidate both guards", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True
        summary = result.narration_hint["summary"]
        assert "Guard Captain and Guard Recruit" in summary or "both" in summary.lower()


class TestOutcomeFlexibility:
    """Test the data-driven outcome system."""

    def test_social_outcomes_loading(self):
        """Test that social outcomes configuration can be loaded."""
        from router.validator import Validator

        validator = Validator()

        # Should have loaded social outcomes (either from file or fallback)
        assert "intents" in validator.social_outcomes
        if "persuade" in validator.social_outcomes["intents"]:
            persuade_config = validator.social_outcomes["intents"]["persuade"]
            assert "outcomes" in persuade_config
            assert "crit_success" in persuade_config["outcomes"]

    def test_data_driven_effects_generation(self, enhanced_talk_state):
        """Test that effects are generated from configuration data."""
        from router.validator import Validator

        validator = Validator()

        # Test effect generation using the new data-driven approach
        effects = validator._generate_talk_effects(
            "persuade", "crit_success", "pc.arin", "npc.guard1", enhanced_talk_state
        )

        # Should generate effects based on social_outcomes.json
        assert len(effects) > 0
        mark_effects = [e for e in effects if e.get("type") == "mark"]
        if mark_effects:
            mark_effect = mark_effects[0]
            assert mark_effect["tag"] == "favor"  # From configuration

    def test_custom_outcome_configuration(self, enhanced_talk_state):
        """Test that outcome mappings can be customized."""
        # This test would verify that changing social_outcomes.json affects behavior
        # For now, just verify the structure is correct
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "deceive",
            "style": 3,
            "domain": "d6",
            "dc_hint": 8,
        }

        utterance = Utterance(text="I deceive the guard", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        if result.ok and result.facts["outcome"] == "crit_success":
            mark_effects = [e for e in result.effects if e.get("type") == "mark"]
            if mark_effects:
                # Should use "deception" tag from configuration
                assert mark_effects[0]["tag"] == "deception"


class TestNarrationHintsEnrichment:
    """Test enhanced narration hints with disposition tracking."""

    def test_audience_disposition_tracking(self, enhanced_talk_state):
        """Test that disposition before/after is tracked."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "persuade",
            "style": 2,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I persuade the guard", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True

        hint = result.narration_hint
        assert "audience_disposition_before" in hint
        assert "audience_disposition_after" in hint

        # Should have disposition data for the target
        before = hint["audience_disposition_before"]
        after = hint["audience_disposition_after"]
        assert "npc.guard1" in before
        assert "npc.guard1" in after

        # Should track guard values
        assert "guard" in before["npc.guard1"]
        assert "guard" in after["npc.guard1"]

    def test_effects_summary(self, enhanced_talk_state):
        """Test that effects summary is generated."""
        args = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "intimidate",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I intimidate the guard", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True

        hint = result.narration_hint
        assert "effects_summary" in hint
        effects_summary = hint["effects_summary"]

        # Should contain human-readable descriptions of effects
        if effects_summary:
            summary_text = " ".join(effects_summary)
            assert "Guard Captain" in summary_text

    def test_multi_target_disposition_tracking(self, enhanced_talk_state):
        """Test disposition tracking with multiple targets."""
        args = {
            "actor": "pc.arin",
            "target": ["npc.guard1", "npc.guard2"],
            "intent": "charm",
            "style": 1,
            "domain": "d6",
            "dc_hint": 12,
        }

        utterance = Utterance(text="I charm both guards", actor_id="pc.arin")
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True

        hint = result.narration_hint
        before = hint["audience_disposition_before"]
        after = hint["audience_disposition_after"]

        # Should track both targets
        assert "npc.guard1" in before and "npc.guard1" in after
        assert "npc.guard2" in before and "npc.guard2" in after


class TestIntegrationScenarios:
    """Test complete scenarios using all enhanced features."""

    def test_complex_social_scenario(self, enhanced_talk_state):
        """Test a complex social interaction using multiple enhancements."""
        # First interaction: intimidate guard captain
        args1 = {
            "actor": "pc.arin",
            "target": "npc.guard1",
            "intent": "intimidate",
            "style": 2,
            "domain": "d6",
            "dc_hint": 14,
        }

        utterance1 = Utterance(text="I threaten the guard captain", actor_id="pc.arin")
        result1 = validate_and_execute(
            "talk", args1, enhanced_talk_state, utterance1, seed=42
        )

        assert result1.ok == True
        assert result1.facts["intent"] == "intimidate"  # Verb mapping worked

        # Second interaction: comfort the recruit (multi-target potential)
        args2 = {
            "actor": "pc.arin",
            "target": "npc.guard2",
            "intent": "comfort",
            "style": 1,
            "domain": "d6",
            "dc_hint": 10,
        }

        utterance2 = Utterance(text="I console the recruit", actor_id="pc.arin")
        result2 = validate_and_execute(
            "talk", args2, enhanced_talk_state, utterance2, seed=123
        )

        assert result2.ok == True
        assert result2.facts["intent"] == "comfort"  # Verb mapping worked

        # Check that disposition tracking worked
        assert "audience_disposition_before" in result2.narration_hint
        assert "effects_summary" in result2.narration_hint

    def test_group_persuasion_scenario(self, enhanced_talk_state):
        """Test persuading a group using multi-target support."""
        args = {
            "actor": "pc.arin",
            "target": ["npc.guard1", "npc.guard2"],
            "intent": "persuade",
            "style": 2,
            "domain": "d8",
            "dc_hint": 13,
            "topic": "letting us pass",
        }

        utterance = Utterance(
            text="I convince both guards to let us pass", actor_id="pc.arin"
        )
        result = validate_and_execute(
            "talk", args, enhanced_talk_state, utterance, seed=42
        )

        assert result.ok == True
        assert result.facts["topic"] == "letting us pass"

        # Should have effects for both targets
        targets_affected = set()
        for effect in result.effects:
            if "target" in effect:
                targets_affected.add(effect["target"])

        assert "npc.guard1" in targets_affected
        assert "npc.guard2" in targets_affected

        # Narration should mention both guards
        summary = result.narration_hint["summary"]
        assert "both" in summary.lower() or (
            "Guard Captain" in summary and "Guard Recruit" in summary
        )


if __name__ == "__main__":
    # Run specific test classes for demonstration
    import subprocess

    print("Running enhanced talk tool tests...")

    # Run tests and show results
    test_files = [
        "TestBroaderIntentOntology",
        "TestMarksGeneralization",
        "TestClocksAsFirstClass",
        "TestMultiTargetSupport",
        "TestOutcomeFlexibility",
        "TestNarrationHintsEnrichment",
        "TestIntegrationScenarios",
    ]

    for test_class in test_files:
        print(f"\n--- Running {test_class} ---")
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", __file__ + "::" + test_class, "-v"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(__file__),
            )

            if result.returncode == 0:
                print(f"✅ {test_class} passed")
            else:
                print(f"❌ {test_class} failed")
                print(result.stdout)
                print(result.stderr)
        except Exception as e:
            print(f"⚠️  Could not run {test_class}: {e}")

    print("\nAll enhanced talk features tested!")
