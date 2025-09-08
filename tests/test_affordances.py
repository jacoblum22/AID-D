"""
Test script for the Affordance Filter (Step 2).

This demonstrates how the affordance filter computes applicable tools
and enriches them with context-aware argument hints.
"""

import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.affordances import get_tool_candidates


def create_demo_state() -> GameState:
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

    # Create actors
    actors = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            visible_actors=["npc.guard.01"],
            has_weapon=True,
            inventory=["rope", "lockpicks"],
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
        entities=actors, zones=zones, current_actor="pc.arin", pending_action=None
    )


def test_affordance_filter():
    """Test the affordance filter with various scenarios."""

    print("=== AI D&D Affordance Filter Demo (Step 2) ===\n")

    state = create_demo_state()

    # Test scenarios with expected enrichments
    scenarios = [
        (
            "I want to sneak past the guard",
            "Should show enriched ask_roll with sleepy guard DC",
        ),
        (
            "I go to the threshold quickly",
            "Should show enriched move with fast movement style",
        ),
        (
            "I attack the guard with my sword",
            "Should show enriched attack with weapon specified",
        ),
        (
            "I say 'Hello there, good sir'",
            "Should show enriched talk with extracted message",
        ),
        ("I use my rope", "Should show enriched use_item"),
        ("What do I see here?", "Should show get_info with high confidence"),
        (
            "I want to do something",
            "Should trigger ask_clarifying with context question",
        ),
    ]

    for utterance_text, expectation in scenarios:
        print(f"Player says: '{utterance_text}'")
        print(f"Expected: {expectation}")

        utterance = Utterance(text=utterance_text, actor_id="pc.arin")

        # Get candidates from affordance filter
        candidates = get_tool_candidates(state, utterance)

        # Add minimal assertions to prevent false positives
        assert candidates is not None, "get_tool_candidates should not return None"
        assert (
            len(candidates) > 0
        ), f"Should return at least one candidate for utterance: '{utterance_text}'"

        # Basic sanity checks
        for candidate in candidates:
            assert hasattr(candidate, "id"), "Candidate should have an id"
            assert hasattr(candidate, "confidence"), "Candidate should have confidence"
            assert (
                0 <= candidate.confidence <= 1
            ), f"Confidence should be 0-1, got {candidate.confidence}"

        print(f"Tool candidates ({len(candidates)}):")
        for i, candidate in enumerate(candidates, 1):
            print(f"  {i}. {candidate.id} (confidence: {candidate.confidence:.2f})")
            print(f"     Description: {candidate.desc}")
            if candidate.args_hint:
                print(f"     Enriched args: {candidate.args_hint}")

        print("-" * 60)


def test_enrichment_details():
    """Test specific enrichment features."""

    print("\n=== Testing Enrichment Details ===")

    state = create_demo_state()

    # Test DC enrichment for sleepy guard
    print("\n1. Testing DC enrichment for sleepy guard:")
    utterance = Utterance(text="I sneak toward the threshold", actor_id="pc.arin")
    candidates = get_tool_candidates(state, utterance)

    ask_roll_candidate = next((c for c in candidates if c.id == "ask_roll"), None)
    if ask_roll_candidate:
        args_hint = ask_roll_candidate.args_hint or {}
        print(f"   Base DC would be 12, enriched: {args_hint}")

    # Test message extraction
    print("\n2. Testing message extraction:")
    utterance = Utterance(
        text='I tell the guard "Stand aside, I have business inside"',
        actor_id="pc.arin",
    )
    candidates = get_tool_candidates(state, utterance)

    talk_candidate = next((c for c in candidates if c.id == "talk"), None)
    if talk_candidate:
        args_hint = talk_candidate.args_hint or {}
        print(f"   Extracted message: {args_hint.get('message', 'None')}")

    # Test movement style detection
    print("\n3. Testing movement style detection:")
    utterance = Utterance(text="I run quickly to the main hall", actor_id="pc.arin")
    candidates = get_tool_candidates(state, utterance)

    move_candidate = next((c for c in candidates if c.id == "move"), None)
    if move_candidate:
        args_hint = move_candidate.args_hint or {}
        print(f"   Movement style: {args_hint.get('movement_style', 'None')}")

    # Test clarifying question generation
    print("\n4. Testing clarifying question generation:")
    utterance = Utterance(text="I want to approach it", actor_id="pc.arin")
    candidates = get_tool_candidates(state, utterance)

    clarify_candidate = next((c for c in candidates if c.id == "ask_clarifying"), None)
    if clarify_candidate:
        args_hint = clarify_candidate.args_hint or {}
        print(f"   Generated question: {args_hint.get('question', 'None')}")


def test_confidence_ranking():
    """Test that tools are ranked by confidence appropriately."""

    print("\n=== Testing Confidence Ranking ===")

    state = create_demo_state()

    # Clear utterance about attacking
    utterance = Utterance(text="I attack the guard with my sword!", actor_id="pc.arin")
    candidates = get_tool_candidates(state, utterance)

    print("\nFor clear attack intent, confidence ranking:")
    for i, candidate in enumerate(candidates[:5], 1):  # Top 5
        print(f"  {i}. {candidate.id}: {candidate.confidence:.2f}")

    # Assert confidence ordering (non-increasing)
    assert len(candidates) > 0, "Should have candidates for clear attack intent"
    for i in range(len(candidates) - 1):
        assert (
            candidates[i].confidence >= candidates[i + 1].confidence
        ), f"Confidence should be non-increasing: {candidates[i].confidence} >= {candidates[i + 1].confidence}"

    # Ambiguous utterance
    utterance = Utterance(text="I do something", actor_id="pc.arin")
    candidates = get_tool_candidates(state, utterance)

    print("\nFor ambiguous intent, confidence ranking:")
    for i, candidate in enumerate(candidates[:5], 1):  # Top 5
        print(f"  {i}. {candidate.id}: {candidate.confidence:.2f}")

    # Assert confidence ordering for ambiguous case
    assert len(candidates) > 0, "Should have candidates for ambiguous utterance"
    for i in range(len(candidates) - 1):
        assert (
            candidates[i].confidence >= candidates[i + 1].confidence
        ), f"Confidence should be non-increasing: {candidates[i].confidence} >= {candidates[i + 1].confidence}"

    # Assert that ask_clarifying appears for ambiguous text
    clarifying_candidates = [c for c in candidates if c.id == "ask_clarifying"]
    assert (
        len(clarifying_candidates) > 0
    ), "ask_clarifying should appear for ambiguous utterances"

    # Assert that ask_clarifying has reasonable confidence for ambiguous text
    clarifying_candidate = clarifying_candidates[0]
    assert (
        clarifying_candidate.confidence >= 0.3
    ), f"ask_clarifying should have decent confidence for ambiguous text, got {clarifying_candidate.confidence}"


if __name__ == "__main__":
    try:
        test_affordance_filter()
        test_enrichment_details()
        test_confidence_ranking()

        print("\n✅ Affordance Filter Step 2 implementation complete!")
        print("Key features demonstrated:")
        print("- Runtime tool filtering based on preconditions")
        print("- Always includes escape hatches (narrate_only, ask_clarifying)")
        print("- Context-aware argument enrichment")
        print("- Confidence-based ranking")
        print("- Smart DC adjustments (sleepy guard)")
        print("- Message extraction from utterances")
        print("- Movement style detection")
        print("- Context-specific clarifying questions")

    except Exception as e:
        print(f"❌ Error in demo: {e}")
        import traceback

        traceback.print_exc()
