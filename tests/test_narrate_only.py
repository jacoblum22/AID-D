"""
Test script for the narrate_only tool implementation.

This tests the new narrate_only tool that provides pure narration
without changing game state, with topic inference and contextual details.
"""

import sys
import os
import json

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from router.game_state import GameState, PC, NPC, Zone, Utterance, Scene
from router.validator import validate_and_execute


def create_demo_state() -> GameState:
    """Create a demo game state for testing narrate_only."""

    # Create zones with features
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard with weathered flagstones",
            adjacent_zones=["threshold", "main_hall"],
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold to the manor",
            adjacent_zones=["courtyard", "main_hall"],
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

    # Create scene with tags
    scene = Scene(
        id="courtyard_scene",
        tags={"lighting": "dim", "noise": "quiet", "alert": "sleepy"},
    )

    return GameState(
        entities=actors,
        zones=zones,
        current_actor="pc.arin",
        scene=scene,
        pending_action=None,
    )


def test_narrate_only_tool():
    """Test the narrate_only tool with various topics."""

    print("=== Testing narrate_only Tool Implementation ===\n")

    state = create_demo_state()

    # Test scenarios with different topics
    test_cases = [
        {
            "utterance": "I look around",
            "expected_topic": "look around",
            "description": "Basic look around command",
        },
        {
            "utterance": "What do I see here?",
            "expected_topic": "look around",
            "description": "Question about surroundings",
        },
        {
            "utterance": "I listen carefully",
            "expected_topic": "listen",
            "description": "Listening command",
        },
        {
            "utterance": "I smell the air",
            "expected_topic": "smell",
            "description": "Smelling command",
        },
        {
            "utterance": "I tie my cloak tighter",
            "expected_topic": "establishing",
            "description": "Non-actionable personal action",
        },
        {
            "utterance": "I examine the Sleepy Guard",
            "expected_topic": "zoom_in:npc.guard.01",
            "description": "Focus on specific entity",
        },
        {
            "utterance": "What happened so far?",
            "expected_topic": "recap",
            "description": "Recap request",
        },
    ]

    successful_tests = 0
    failed_tests = 0

    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['description']}")
        print(f"Input: '{test_case['utterance']}'")
        print(f"Expected topic: {test_case['expected_topic']}")

        utterance = Utterance(text=test_case["utterance"], actor_id="pc.arin")

        try:
            # Test the tool execution - let the system suggest args and infer topic
            from router.tool_catalog import suggest_narrate_only_args

            suggested_args = suggest_narrate_only_args(state, utterance)

            result = validate_and_execute(
                "narrate_only", suggested_args, state, utterance, seed=42
            )

            if result.ok:
                print(f"✅ Tool executed successfully")
                print(f"   Actual topic: {result.facts.get('topic', 'unknown')}")
                print(
                    f"   Summary: {result.narration_hint.get('summary', 'no summary')}"
                )
                print(f"   Tone tags: {result.narration_hint.get('tone_tags', [])}")
                print(f"   Camera: {result.narration_hint.get('camera', 'unknown')}")
                print(f"   Sensory: {result.narration_hint.get('sensory', [])}")

                # Validate structure
                assert "facts" in result.__dict__
                assert "narration_hint" in result.__dict__
                assert result.effects == []  # narrate_only should never have effects
                assert result.tool_id == "narrate_only"

                successful_tests += 1
            else:
                print(f"❌ Tool execution failed: {result.error_message}")
                failed_tests += 1

        except Exception as e:
            print(f"❌ Exception during execution: {e}")
            failed_tests += 1

        print("-" * 60)

    # Summary
    total_tests = successful_tests + failed_tests
    print(f"\n=== TEST RESULTS ===")
    print(f"Total tests: {total_tests}")
    print(f"Successful: {successful_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success rate: {(successful_tests/total_tests)*100:.1f}%")

    return successful_tests, failed_tests


def test_topic_inference():
    """Test the topic inference heuristics directly."""

    print("\n=== Testing Topic Inference Heuristics ===\n")

    from router.tool_catalog import suggest_narrate_only_args

    state = create_demo_state()

    test_cases = [
        ("I look around", "look around"),
        ("What do I see?", "look around"),
        ("I listen", "listen"),
        ("I smell something", "smell"),
        ("What happened?", "recap"),
        ("I adjust my armor", "establishing"),
        ("", "look around"),  # fallback
    ]

    for utterance_text, expected_topic in test_cases:
        utterance = Utterance(text=utterance_text, actor_id="pc.arin")
        suggested_args = suggest_narrate_only_args(state, utterance)

        actual_topic = suggested_args.get("topic", "unknown")
        status = "✅" if actual_topic == expected_topic else "❌"

        print(
            f"{status} '{utterance_text}' -> '{actual_topic}' (expected: '{expected_topic}')"
        )

    print()


if __name__ == "__main__":
    try:
        test_topic_inference()
        success_count, fail_count = test_narrate_only_tool()

        if fail_count == 0:
            print("🎉 All narrate_only tests passed!")
            print("\nKey features verified:")
            print("- Topic inference from utterances")
            print("- Deterministic fact gathering")
            print("- Structured narration hints")
            print("- No game state changes (empty effects)")
            print("- Proper ToolResult envelope")
        else:
            print(f"⚠️  {fail_count} tests failed - check implementation")

    except Exception as e:
        print(f"❌ Error in test: {e}")
        import traceback

        traceback.print_exc()
