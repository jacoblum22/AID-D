"""
Test script for the ask_clarifying tool implementation.

Tests the complete ask_clarifying pipeline:
- Schema validation with ClarifyingOption and AskClarifyingArgs
- Pending choice creation and storage
- ToolResult structure
- Pending choice consumption logic
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.validator import Validator
from router.tool_catalog import AskClarifyingArgs, ClarifyingOption


@pytest.fixture
def demo_state():
    """Create a demo game state for testing."""
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
            adjacent_zones=["courtyard"],
        ),
    }

    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            current_zone="courtyard",
            visible_actors=["npc.guard.01"],
        ),
        "npc.guard.01": NPC(
            id="npc.guard.01",
            name="Sleepy Guard",
            current_zone="courtyard",
            visible_actors=["pc.arin"],
        ),
    }

    return GameState(entities=entities, zones=zones, current_actor="pc.arin")


@pytest.fixture
def validator():
    """Create a validator instance for testing."""
    return Validator()


def test_ask_clarifying_schema_validation():
    """Test that the ask_clarifying Pydantic models work correctly."""
    # Test ClarifyingOption model
    option = ClarifyingOption(
        id="A",
        label="Look around first",
        tool_id="narrate_only",
        args_patch={"topic": "look around"},
    )

    assert option.id == "A"
    assert option.label == "Look around first"
    assert option.tool_id == "narrate_only"
    assert option.args_patch == {"topic": "look around"}

    # Test AskClarifyingArgs model
    args = AskClarifyingArgs(
        question="What would you like to do?",
        options=[
            ClarifyingOption(
                id="A",
                label="Look around",
                tool_id="narrate_only",
                args_patch={"topic": "look around"},
            ),
            ClarifyingOption(
                id="B",
                label="Move to threshold",
                tool_id="move",
                args_patch={"to": "threshold"},
            ),
        ],
        reason="ambiguous_intent",
        actor="pc.arin",
    )

    assert args.question == "What would you like to do?"
    assert len(args.options) == 2
    assert args.reason == "ambiguous_intent"
    assert args.actor == "pc.arin"
    assert args.expires_in_turns == 1  # default value


def test_ask_clarifying_execution(demo_state, validator):
    """Test ask_clarifying tool execution creates proper pending choice."""
    # Set up test arguments
    raw_args = {
        "question": "What would you like to do next?",
        "options": [
            {
                "id": "A",
                "label": "Look around first",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
            },
            {
                "id": "B",
                "label": "Move to threshold",
                "tool_id": "move",
                "args_patch": {"to": "threshold"},
            },
        ],
        "reason": "ambiguous_intent",
        "actor": "pc.arin",
    }

    utterance = Utterance(text="I want to do something", actor_id="pc.arin")

    # Execute the tool
    result = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    # Check ToolResult structure
    assert result.ok == True
    assert result.tool_id == "ask_clarifying"

    # Check that core args are present (Pydantic adds defaults and metadata)
    assert result.args["question"] == raw_args["question"]
    assert result.args["reason"] == raw_args["reason"]
    assert result.args["actor"] == raw_args["actor"]

    # Check options length matches
    assert len(result.args["options"]) == len(raw_args["options"])

    # Check core option fields match (allowing for added metadata)
    for i, raw_opt in enumerate(raw_args["options"]):
        result_opt = result.args["options"][i]
        assert result_opt["id"] == raw_opt["id"]
        assert result_opt["label"] == raw_opt["label"]
        assert result_opt["tool_id"] == raw_opt["tool_id"]
        assert result_opt["args_patch"] == raw_opt["args_patch"]

        # These should have defaults added by Pydantic
        assert "category" in result_opt
        assert "risk_hint" in result_opt
        assert "tags" in result_opt

    assert len(result.effects) == 0  # ask_clarifying should not generate effects

    # Check facts
    assert "pending_choice_id" in result.facts
    assert result.facts["actor"] == "pc.arin"
    assert result.facts["question"] == "What would you like to do next?"
    assert len(result.facts["options"]) == 2
    assert result.facts["reason"] == "ambiguous_intent"

    # Check narration hint
    assert "interactive" in result.narration_hint["tone_tags"]
    assert "concise" in result.narration_hint["tone_tags"]
    assert result.narration_hint["sentences_max"] == 1

    # Check that pending choice was stored in state
    assert demo_state.scene.pending_choice is not None
    pending = demo_state.scene.pending_choice
    assert pending["actor"] == "pc.arin"
    assert pending["question"] == "What would you like to do next?"
    assert len(pending["options"]) == 2
    assert pending["reason"] == "ambiguous_intent"
    assert pending["expires_round"] == demo_state.scene.round + 1


def test_pending_choice_consumption(demo_state, validator):
    """Test that pending choices are correctly consumed when user responds."""
    # First create a pending choice
    demo_state.scene.pending_choice = {
        "id": "pc_test123",
        "actor": "pc.arin",
        "question": "What would you like to do?",
        "options": [
            {
                "id": "A",
                "label": "Look around",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
            },
            {
                "id": "B",
                "label": "Move to threshold",
                "tool_id": "move",
                "args_patch": {"to": "threshold", "method": "walk"},
            },
        ],
        "reason": "ambiguous_intent",
        "expires_round": demo_state.scene.round + 1,
    }

    # Test exact ID match
    utterance_a = Utterance(text="A", actor_id="pc.arin")
    result = validator.maybe_consume_pending_choice(demo_state, utterance_a)

    assert result is not None
    tool_id, args = result
    assert tool_id == "narrate_only"
    assert "topic" in args
    assert args["topic"] == "look around"
    # Should clear pending choice
    assert demo_state.scene.pending_choice is None

    # Recreate pending choice for label matching test
    demo_state.scene.pending_choice = {
        "id": "pc_test456",
        "actor": "pc.arin",
        "question": "What would you like to do?",
        "options": [
            {
                "id": "A",
                "label": "Look around",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
            },
            {
                "id": "B",
                "label": "Move to threshold",
                "tool_id": "move",
                "args_patch": {"to": "threshold", "method": "walk"},
            },
        ],
        "reason": "ambiguous_intent",
        "expires_round": demo_state.scene.round + 1,
    }

    # Test fuzzy label matching
    utterance_move = Utterance(
        text="I want to move to the threshold", actor_id="pc.arin"
    )
    result = validator.maybe_consume_pending_choice(demo_state, utterance_move)

    assert result is not None
    tool_id, args = result
    assert tool_id == "move"
    assert "to" in args
    assert args["to"] == "threshold"


def test_pending_choice_expiration(demo_state, validator):
    """Test that expired pending choices are automatically cleared."""
    # Create an expired pending choice
    demo_state.scene.pending_choice = {
        "id": "pc_expired",
        "actor": "pc.arin",
        "question": "This should expire",
        "options": [
            {
                "id": "A",
                "label": "Option A",
                "tool_id": "narrate_only",
                "args_patch": {},
            }
        ],
        "reason": "ambiguous_intent",
        "expires_round": demo_state.scene.round - 1,  # Already expired
    }

    utterance = Utterance(text="A", actor_id="pc.arin")
    result = validator.maybe_consume_pending_choice(demo_state, utterance)

    # Should return None and clear the expired choice
    assert result is None
    assert demo_state.scene.pending_choice is None


def test_max_clarifications_limit(demo_state, validator):
    """Test that max 3 clarifications per turn are enforced."""
    # Set choice count to 2 (one away from limit)
    demo_state.scene.choice_count_this_turn = 2

    raw_args = {
        "question": "Third clarification attempt",
        "options": [
            {
                "id": "A",
                "label": "Option A",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
            },
            {
                "id": "B",
                "label": "Option B",
                "tool_id": "move",
                "args_patch": {"to": "threshold"},
            },
        ],
    }

    utterance = Utterance(text="I need help", actor_id="pc.arin")

    # This should still work (3rd clarification)
    result = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    assert result.ok == True
    assert result.tool_id == "ask_clarifying"
    assert demo_state.scene.choice_count_this_turn == 3

    # Now try a 4th clarification - should fall back to narrate_only
    result_fallback = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    assert result_fallback.ok == True
    assert result_fallback.tool_id == "narrate_only"
    assert "clarification_limit_reached" in result_fallback.facts
    assert result_fallback.facts["max_clarifications"] == 3
    assert "hesitate" in result_fallback.narration_hint["summary"]

    # Pending choice should be cleared
    assert demo_state.scene.pending_choice is None


def test_turn_advance_resets_counter(demo_state, validator):
    """Test that advancing turns resets the clarification counter."""
    # Set counter to max
    demo_state.scene.choice_count_this_turn = 3

    # Advance turn
    validator.advance_turn(demo_state)

    # Counter should be reset
    assert demo_state.scene.choice_count_this_turn == 0


def test_option_metadata_preserved(demo_state, validator):
    """Test that option metadata (category, risk_hint, tags) is preserved."""
    raw_args = {
        "question": "What would you like to do?",
        "options": [
            {
                "id": "A",
                "label": "Sneak forward",
                "tool_id": "ask_roll",
                "args_patch": {"action": "sneak"},
                "category": "stealth",
                "risk_hint": "risky",
                "tags": ["stealth", "risky"],
            },
            {
                "id": "B",
                "label": "Look around",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
                "category": "info",
                "risk_hint": "safe",
                "tags": ["observation", "safe"],
            },
        ],
    }

    utterance = Utterance(text="I'm not sure", actor_id="pc.arin")

    result = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    assert result.ok == True

    # Check that metadata is preserved in stored pending choice
    stored_options = demo_state.scene.pending_choice["options"]
    assert stored_options[0]["category"] == "stealth"
    assert stored_options[0]["risk_hint"] == "risky"
    assert stored_options[0]["tags"] == ["stealth", "risky"]

    assert stored_options[1]["category"] == "info"
    assert stored_options[1]["risk_hint"] == "safe"
    assert stored_options[1]["tags"] == ["observation", "safe"]


def test_enhanced_narration_hint(demo_state, validator):
    """Test that narration hint includes options_summary."""
    raw_args = {
        "question": "What's your move?",
        "options": [
            {
                "id": "A",
                "label": "Attack the guard",
                "tool_id": "attack",
                "args_patch": {"target": "npc.guard.01"},
            },
            {
                "id": "B",
                "label": "Sneak past",
                "tool_id": "ask_roll",
                "args_patch": {"action": "sneak"},
            },
        ],
    }

    utterance = Utterance(text="What should I do?", actor_id="pc.arin")

    result = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    assert result.ok == True

    # Check narration hint structure
    hint = result.narration_hint
    assert "options_summary" in hint
    assert len(hint["options_summary"]) == 2
    assert hint["options_summary"][0] == "A: Attack the guard"
    assert hint["options_summary"][1] == "B: Sneak past"

    # Check open_choice flag in facts
    assert result.facts["open_choice"] == True


def test_open_choice_philosophy_flag(demo_state, validator):
    """Test that open_choice flag is set to indicate options are suggestions."""
    raw_args = {
        "question": "How do you proceed?",
        "options": [
            {
                "id": "A",
                "label": "Direct approach",
                "tool_id": "move",
                "args_patch": {"to": "threshold"},
            },
            {
                "id": "B",
                "label": "Careful observation",
                "tool_id": "narrate_only",
                "args_patch": {"topic": "look around"},
            },
        ],
    }

    utterance = Utterance(text="I need guidance", actor_id="pc.arin")

    result = validator.validate_and_execute(
        "ask_clarifying", raw_args, demo_state, utterance, seed=1234
    )

    assert result.ok == True
    assert result.facts["open_choice"] == True
    assert "clarification_number" in result.facts
    assert result.facts["clarification_number"] == 1


if __name__ == "__main__":
    pytest.main([__file__])
