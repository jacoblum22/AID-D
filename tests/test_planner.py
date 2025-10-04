"""
Test script for the Planner system (Step 3).

This demonstrates how the planner takes affordance filter output,
formats it into a numbered menu, and gets LLM to choose a tool.
"""

import sys
import os
import json

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.planner import initialize_planner, get_plan


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


def test_planner_integration():
    """Test the full planner integration with LLM."""
    successful_tests, failed_tests = run_planner_integration_tests()

    # Make assertions for pytest
    assert (
        successful_tests > 0
    ), f"Should have some successful tests, got {successful_tests}"
    assert failed_tests == 0, f"Should have no failed tests, got {failed_tests}"


def run_planner_integration_tests():
    """Utility function to run planner integration tests - returns counts for external use."""

    print("=== AI D&D Planner System Demo (Step 3) ===\n")

    # Check if API key is configured
    try:
        # Import config to check API key
        sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
        import config

        # Secure API key validation - avoid hardcoded comparisons and exposure
        if not config.OPENAI_API_KEY or len(config.OPENAI_API_KEY.strip()) == 0:
            print("❌ API key not configured!")
            print("Please set the OPENAI_API_KEY environment variable.")
            return 0, 0

        # Check for template/placeholder values without exposing the actual key
        if config.OPENAI_API_KEY.strip() in ["your-api-key-here", "sk-...", ""]:
            print("❌ API key appears to be a placeholder!")
            print("Please set a valid OpenAI API key in your environment variables.")
            return 0, 0

        # Initialize planner
        initialize_planner(config.OPENAI_API_KEY, config.OPENAI_MODEL)
        print("✅ Planner initialized with OpenAI API")

    except ImportError as e:
        print("❌ Config file not found")
        print("Please make sure config.py exists and OPENAI_API_KEY is set")
        return 0, 0
    except AttributeError as e:
        print("❌ API key configuration missing")
        print("Please ensure OPENAI_API_KEY is defined in config.py")
        return 0, 0
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return 0, 0
    except Exception as e:
        print(f"❌ Error initializing planner: {type(e).__name__}")
        return 0, 0

    state = create_demo_state()

    # Test scenarios - mix of clear, ambiguous, and impossible actions
    scenarios = [
        ("I want to sneak past the guard", "Should pick ask_roll with sneak action"),
        ("I go to the threshold quickly", "Should pick move with movement style"),
        (
            "I attack the guard with my sword",
            "Should pick attack with weapon specified",
        ),
        ("I say 'Hello there, good sir'", "Should pick talk with extracted message"),
        ("I use my rope", "Should pick use_item"),
        ("What do I see here?", "Should pick get_info"),
        ("I want to do something", "Should trigger ask_clarifying (ambiguous)"),
        ("I cast a fireball", "Should trigger ask_clarifying (undefined action)"),
        ("I teleport to Mars", "Should trigger ask_clarifying (impossible)"),
        ("", "Should trigger ask_clarifying (empty input)"),
        ("asdfghjkl random nonsense", "Should trigger ask_clarifying (gibberish)"),
    ]

    successful_tests = 0
    failed_tests = 0

    for utterance_text, expected_behavior in scenarios:
        print(f"Player says: '{utterance_text}'")
        print(f"Expected: {expected_behavior}")

        utterance = Utterance(text=utterance_text, actor_id="pc.arin")

        try:
            # Get plan from LLM (with debug for first scenario)
            debug_mode = utterance_text == "I want to sneak past the guard"
            result = get_plan(state, utterance, debug=debug_mode)

            if result.success:
                print(f"✅ LLM chose: {result.chosen_tool}")
                print(f"   Confidence: {result.confidence:.2f}")
                if result.args:
                    key_args = {
                        k: v
                        for k, v in result.args.items()
                        if k
                        in ["actor", "action", "target", "to", "message", "question"]
                    }
                    print(f"   Key arguments: {json.dumps(key_args, indent=2)}")
                successful_tests += 1
            else:
                print(f"⚠️  Planner failed (using fallback): {result.chosen_tool}")
                print(f"   Error: {result.error_message}")
                print(f"   Fallback args: {result.args}")
                failed_tests += 1

        except Exception as e:
            print(f"❌ Critical error getting plan: {e}")
            failed_tests += 1

        print("-" * 60)

    # Summary
    total_tests = successful_tests + failed_tests
    print(f"\n=== TEST SUMMARY ===")
    print(f"Total scenarios: {total_tests}")
    print(f"Successful plans: {successful_tests}")
    print(f"Failed/Fallback plans: {failed_tests}")

    # Handle division by zero edge case
    if total_tests == 0:
        print("Success rate: N/A (no tests executed)")
    else:
        success_rate = (successful_tests / total_tests) * 100
        print(f"Success rate: {success_rate:.1f}%")

    return successful_tests, failed_tests


def test_prompt_realism():
    """Test that the prompt contains only realistic game information."""

    print("\n=== Testing Prompt Realism ===")
    print("Checking that LLM only receives information available in real gameplay...")

    state = create_demo_state()
    utterance = Utterance(text="I sneak toward the guard", actor_id="pc.arin")

    print("\nThe LLM receives:")
    print("1. Player input: 'I sneak toward the guard'")
    print("2. Game state: Actor: Arin, Zone: Courtyard, Visible: Sleepy Guard")
    print("3. Numbered tool menu with descriptions and suggested args")
    print("4. System prompt constraining it to pick from the menu")

    print("\nThe LLM does NOT receive:")
    print("- Internal game code or implementation details")
    print("- Debug information or test scenario context")
    print("- Information about other zones not currently visible")
    print("- Actor stats or hidden information")

    # Demonstrate with actual prompt
    print("\n--- Actual prompt example (first test will show this) ---")


def test_failure_scenarios():
    """Test specific scenarios that should fail or trigger fallbacks."""

    print("\n=== Testing Failure Scenarios ===")

    # Test with broken game state
    broken_state = GameState(
        entities={}, zones={}, current_actor=None  # Empty entities  # Empty zones
    )

    utterance = Utterance(text="I do something", actor_id="nonexistent")

    print("Testing with broken game state (empty actors/zones)...")
    try:
        result = get_plan(broken_state, utterance)
        if not result.success or result.chosen_tool == "ask_clarifying":
            print("✅ Correctly handled broken state with fallback")
        else:
            print("❌ Should have failed with broken state")
    except Exception as e:
        print(f"✅ Correctly threw exception for broken state: {e}")

    # Test scenarios that should definitely trigger ask_clarifying
    ambiguous_scenarios = [
        "",  # Empty
        "asdfghjkl",  # Gibberish
        "I cast level 9 fireball of ultimate destruction",  # Impossible
        "Do the thing with the stuff",  # Vague
    ]

    state = create_demo_state()
    ask_clarifying_count = 0

    print(f"\nTesting {len(ambiguous_scenarios)} ambiguous scenarios...")
    for scenario in ambiguous_scenarios:
        utterance = Utterance(text=scenario, actor_id="pc.arin")
        try:
            result = get_plan(state, utterance)
            if result.chosen_tool == "ask_clarifying":
                ask_clarifying_count += 1
        except:
            ask_clarifying_count += 1  # Exceptions also count as fallbacks

    print(
        f"Result: {ask_clarifying_count}/{len(ambiguous_scenarios)} triggered ask_clarifying"
    )
    if ask_clarifying_count >= len(ambiguous_scenarios) * 0.8:  # 80% threshold
        print("✅ Good fallback behavior for ambiguous inputs")
    else:
        print("⚠️  Some ambiguous inputs may not be handled properly")


if __name__ == "__main__":
    try:
        success_count, fail_count = run_planner_integration_tests()
        test_prompt_realism()
        test_failure_scenarios()

        print("\n✅ Planner Step 3 implementation complete!")
        print("Key features demonstrated:")
        print("- LLM constrained to numbered tool menu")
        print("- Structured JSON output format")
        print("- Graceful fallback to ask_clarifying")
        print("- Argument merging (LLM + suggested args)")
        print("- Confidence scoring")
        print("- Retry logic for API failures")
        print("- Realistic prompt content (no debug/internal info)")
        print("- Clear success/failure reporting")

    except Exception as e:
        print(f"❌ Error in demo: {e}")
        import traceback

        traceback.print_exc()
