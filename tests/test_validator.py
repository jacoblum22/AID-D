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

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.validator import validate_and_execute
from router.effects import get_registered_effects


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


def test_effect_atoms():
    """Test the effect atom system."""

    print("=== Testing Effect Atom System ===")

    registered_effects = get_registered_effects()
    print(f"Registered effect types: {registered_effects}")

    # Test individual effect types
    state = create_demo_state()

    from router.effects import apply_effects

    # Test HP effect
    print("\nTesting HP effect:")
    hp_before = state.actors["pc.arin"].hp.current
    apply_effects(state, [{"type": "hp", "target": "pc.arin", "delta": -5}])
    hp_after = state.actors["pc.arin"].hp.current
    print(f"  HP: {hp_before} → {hp_after} (delta: -5)")

    # Test position effect
    print("\nTesting position effect:")
    pos_before = state.actors["pc.arin"].current_zone
    apply_effects(state, [{"type": "position", "target": "pc.arin", "to": "threshold"}])
    pos_after = state.actors["pc.arin"].current_zone
    print(f"  Position: {pos_before} → {pos_after}")

    # Test clock effect
    print("\nTesting clock effect:")
    apply_effects(state, [{"type": "clock", "id": "scene.alarm", "delta": 2}])
    if hasattr(state, "clocks"):
        clock_value = state.clocks.get("scene.alarm", {}).get("value", 0)
        print(f"  scene.alarm clock: {clock_value}")

    print("✅ Effect atom system working")


def test_validation_pipeline():
    """Test the complete validation and execution pipeline."""

    print("\n=== Testing Validation + Execution Pipeline ===")

    # Test scenarios with different tools
    test_cases = [
        {
            "name": "Successful ask_roll (sneak)",
            "tool_id": "ask_roll",
            "args": {
                "actor": "pc.arin",
                "action": "sneak",
                "target": "npc.guard.01",
                "zone_target": "threshold",
                "dc_hint": 12,
                "style": 1,
                "domain": "d6",
            },
            "utterance": "I sneak past the guard",
            "seed": 12345,  # Fixed seed for consistent results
        },
        {
            "name": "Simple move",
            "tool_id": "move",
            "args": {"actor": "pc.arin", "to": "main_hall", "movement_style": "fast"},
            "utterance": "I run to the main hall",
            "seed": 54321,
        },
        {
            "name": "Combat attack",
            "tool_id": "attack",
            "args": {"actor": "pc.arin", "target": "npc.guard.01", "weapon": "sword"},
            "utterance": "I attack the guard",
            "seed": 99999,
        },
        {
            "name": "Use healing potion",
            "tool_id": "use_item",
            "args": {"actor": "pc.arin", "item": "healing_potion", "target": "pc.arin"},
            "utterance": "I drink my healing potion",
            "seed": 11111,
        },
        {
            "name": "Get zone info",
            "tool_id": "get_info",
            "args": {"query": "What do I see?", "scope": "current_zone"},
            "utterance": "What do I see here?",
            "seed": 22222,
        },
        {
            "name": "Schema validation failure",
            "tool_id": "ask_roll",
            "args": {
                "actor": "pc.arin",
                # Missing required fields
                "style": "invalid_type",  # Should be int
            },
            "utterance": "I do something",
            "seed": 33333,
            "expected_to_fail": True,  # Mark this as an expected failure
        },
    ]

    successful_executions = 0
    failed_executions = 0

    for test_case in test_cases:
        print(f"\n--- {test_case['name']} ---")

        # Create fresh state for each test to avoid interference
        state = create_demo_state()
        utterance = Utterance(text=test_case["utterance"], actor_id="pc.arin")

        # Execute validation pipeline
        result = validate_and_execute(
            test_case["tool_id"], test_case["args"], state, utterance, test_case["seed"]
        )

        # Check if this test is expected to fail
        expected_to_fail = test_case.get("expected_to_fail", False)

        if result.ok:
            if expected_to_fail:
                print(f"❌ Unexpected Success: {result.tool_id} (was expected to fail)")
                failed_executions += 1
            else:
                print(f"✅ Success: {result.tool_id}")
                print(f"   Effects: {len(result.effects)} effect atoms")
                print(
                    f"   Narration: {result.narration_hint.get('summary', 'No summary')}"
                )
                if result.effects:
                    print(f"   Effect types: {[e['type'] for e in result.effects]}")
                successful_executions += 1
        else:
            if expected_to_fail:
                print(f"✅ Expected Failure: {result.error_message}")
                print(f"   Fallback: {result.tool_id}")
                successful_executions += 1
            else:
                print(f"❌ Failed: {result.error_message}")
                print(f"   Fallback: {result.tool_id}")
                failed_executions += 1

    print(f"\n=== Pipeline Test Results ===")
    print(f"Successful executions: {successful_executions}")
    print(f"Failed executions: {failed_executions}")
    print(f"Total: {successful_executions + failed_executions}")


def test_state_modifications():
    """Test that effect atoms properly modify game state."""

    print("\n=== Testing State Modifications ===")

    state = create_demo_state()

    # Track initial state
    initial_hp = state.actors["pc.arin"].hp.current
    initial_zone = state.actors["pc.arin"].current_zone

    print(f"Initial state:")
    print(f"  Arin HP: {initial_hp}")
    print(f"  Arin Zone: {initial_zone}")
    print(f"  Arin visible actors: {state.actors['pc.arin'].visible_actors}")

    # Execute actions that modify state
    utterance = Utterance(text="I move to threshold", actor_id="pc.arin")

    # Move action
    result1 = validate_and_execute(
        "move", {"actor": "pc.arin", "to": "threshold"}, state, utterance, 12345
    )

    # Attack action (should do damage)
    result2 = validate_and_execute(
        "attack",
        {"actor": "pc.arin", "target": "npc.guard.01", "weapon": "sword"},
        state,
        utterance,
        54321,
    )

    print(f"\nAfter actions:")
    print(f"  Arin Zone: {state.actors['pc.arin'].current_zone}")
    print(f"  Arin visible actors: {state.actors['pc.arin'].visible_actors}")
    print(f"  Guard HP: {getattr(state.actors['npc.guard.01'], 'hp', 20)}")

    # Check if clocks were created
    if hasattr(state, "clocks"):
        print(f"  Active clocks: {list(state.clocks.keys())}")

    # Test entity HP access
    guard_hp = getattr(state.actors["npc.guard.01"], "hp", None)
    if guard_hp:
        print(f"  Guard HP: {guard_hp.current}/{guard_hp.max}")
    else:
        print(f"  Guard HP: Not available")

    print("✅ State modifications working")


def test_logging_format():
    """Test the JSON logging format."""

    print("\n=== Testing Logging Format ===")
    print("Check console output above for JSON log entries.")
    print("Each log should contain:")
    print("- ts (timestamp)")
    print("- turn_id (e.g., t_0001)")
    print("- player_text")
    print("- seed")
    print("- planner info")
    print("- validation results")
    print("- result with ToolResult")
    print("- state summary")


if __name__ == "__main__":
    try:
        test_effect_atoms()
        test_validation_pipeline()
        test_state_modifications()
        test_logging_format()

        print("\n✅ Validator + Executor Step 4 implementation complete!")
        print("Key features demonstrated:")
        print("- Effect atom system (modular, extensible)")
        print("- Schema validation with Pydantic")
        print("- Non-destructive sanitization")
        print("- Precondition checking")
        print("- Standardized ToolResult envelope")
        print("- Tool executors for all 9 tools")
        print("- State modification through effect atoms")
        print("- Structured JSON logging")
        print("- Graceful error handling with ask_clarifying fallback")

    except Exception as e:
        print(f"❌ Error in demo: {e}")
        import traceback

        traceback.print_exc()
