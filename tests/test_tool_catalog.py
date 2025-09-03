"""
Demo script to test the Tool Catalog system (Step 1).

This demonstrates how the precondition system works to filter available tools
based on game state and player utterances.
"""

import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from router.game_state import GameState, PC, NPC, Zone, Utterance
from router.tool_catalog import TOOL_CATALOG, get_tool_by_id


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
            name="Guard",
            type="npc",
            current_zone="courtyard",
            visible_actors=["pc.arin"],
            has_weapon=True,
        ),
    }

    return GameState(
        entities=actors, zones=zones, current_actor="pc.arin", pending_action=None
    )


def test_tool_preconditions():
    """Test the precondition system with various scenarios."""

    print("=== AI D&D Tool Catalog Demo (Step 1) ===\n")

    state = create_demo_state()

    # Test scenarios
    scenarios = [
        ("I want to sneak past the guard", "Stealth action"),
        ("I move to the threshold", "Movement to adjacent zone"),
        ("I attack the guard with my sword", "Combat action"),
        ("I talk to the guard", "Social interaction"),
        ("I use my rope", "Item usage"),
        ("What's in this room?", "Information query"),
        ("I cast a fireball", "Non-adjacent movement (should filter out move)"),
    ]

    for utterance_text, scenario_desc in scenarios:
        print(f"Scenario: {scenario_desc}")
        print(f"Player says: '{utterance_text}'")

        utterance = Utterance(text=utterance_text, actor_id="pc.arin")

        # Check which tools have their preconditions satisfied
        available_tools = []
        for tool in TOOL_CATALOG:
            try:
                if tool.precond(state, utterance):
                    # Get suggested args if available
                    suggested_args = {}
                    if tool.suggest_args:
                        suggested_args = tool.suggest_args(state, utterance)

                    available_tools.append(
                        {
                            "id": tool.id,
                            "desc": tool.desc,
                            "suggested_args": suggested_args,
                        }
                    )
            except Exception as e:
                print(f"  Error checking {tool.id}: {e}")

        print(f"Available tools ({len(available_tools)}):")
        for i, tool in enumerate(available_tools, 1):
            print(f"  {i}. {tool['id']}: {tool['desc']}")
            if tool["suggested_args"]:
                print(f"     Suggested args: {tool['suggested_args']}")

        print("-" * 50)


def test_specific_tool():
    """Test a specific tool's functionality."""

    print("\n=== Testing ask_roll tool specifically ===")

    state = create_demo_state()
    utterance = Utterance(text="I sneak toward the threshold", actor_id="pc.arin")

    ask_roll_tool = get_tool_by_id("ask_roll")
    if ask_roll_tool:
        print(f"Tool: {ask_roll_tool.id}")
        print(f"Description: {ask_roll_tool.desc}")

        # Check precondition
        is_available = ask_roll_tool.precond(state, utterance)
        print(f"Precondition satisfied: {is_available}")

        if is_available and ask_roll_tool.suggest_args:
            suggested_args = ask_roll_tool.suggest_args(state, utterance)
            print(f"Suggested arguments: {suggested_args}")

            # Try to create args object
            try:
                args_obj = ask_roll_tool.args_schema(**suggested_args)
                print(f"Valid args object: {args_obj}")
            except Exception as e:
                print(f"Error creating args object: {e}")


if __name__ == "__main__":
    try:
        test_tool_preconditions()
        test_specific_tool()
        print("\n✅ Tool Catalog Step 1 implementation complete!")
        print("Key features demonstrated:")
        print("- Precondition gating removes illegal options")
        print("- Argument suggestion provides smart defaults")
        print("- Modular tool structure allows easy extension")

    except Exception as e:
        print(f"❌ Error in demo: {e}")
        import traceback

        traceback.print_exc()
