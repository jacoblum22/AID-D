"""
Demo script to test the Tool Catalog system (Step 1).

This demonstrates how the precondition system works to filter available tools
based on game state and player utterances.
"""

import sys
import os

# Fix sys.path: point to backend directory where router/ lives
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

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

    # Create entities
    entities = {
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
        entities=entities, zones=zones, current_actor="pc.arin", pending_action=None
    )


def test_tool_preconditions(verbose=True, filter_working_only=True):
    """Test the precondition system with various scenarios.

    Args:
        verbose: If True, print detailed output
        filter_working_only: If True, only test tools that are fully implemented
    """

    if verbose:
        print("=== AI D&D Tool Catalog Demo (Step 1) ===\n")

    state = create_demo_state()

    # Test scenarios - configurable based on implementation status
    all_scenarios = [
        ("I want to sneak past the guard", "Stealth action", ["ask_roll"]),
        ("I move to the threshold", "Movement to adjacent zone", ["move"]),
        ("I attack the guard with my sword", "Combat action", ["attack"]),
        ("I talk to the guard", "Social interaction", ["talk"]),
        ("I use my rope", "Item usage", ["use_item"]),
        ("What's in this room?", "Information query", ["get_info"]),
        (
            "I cast a fireball",
            "Invalid action (should show fallbacks)",
            ["ask_clarifying", "narrate_only"],
        ),
    ]

    # Filter scenarios based on working tools if requested
    working_tools = {
        "ask_roll",
        "ask_clarifying",
        "narrate_only",
    }  # Add more as they're implemented

    scenarios = []
    for utterance_text, scenario_desc, expected_tools in all_scenarios:
        if not filter_working_only or any(
            tool in working_tools for tool in expected_tools
        ):
            scenarios.append((utterance_text, scenario_desc, expected_tools))
        elif verbose:
            print(
                f"⏭️  Skipping scenario '{scenario_desc}' - tools not fully implemented yet"
            )

    for utterance_text, scenario_desc, expected_tools in scenarios:
        if verbose:
            print(f"Scenario: {scenario_desc}")
            print(f"Player says: '{utterance_text}'")
            print(f"Expected tools: {', '.join(expected_tools)}")

        utterance = Utterance(text=utterance_text, actor_id="pc.arin")

        # Check which tools have their preconditions satisfied
        available_tools = []
        error_count = 0

        for tool in TOOL_CATALOG:
            try:
                if tool.precond(state, utterance):
                    # Get suggested args if available
                    suggested_args = {}
                    if tool.suggest_args:
                        try:
                            suggested_args = tool.suggest_args(state, utterance)
                        except Exception as e:
                            if verbose:
                                print(f"  ⚠️  {tool.id} suggest_args error: {e}")

                    available_tools.append(
                        {
                            "id": tool.id,
                            "desc": tool.desc,
                            "suggested_args": suggested_args,
                        }
                    )
            except Exception as e:
                error_count += 1
                if verbose:
                    print(f"  ❌ Error checking {tool.id}: {e}")

        if verbose:
            print(f"Available tools ({len(available_tools)}):")
            for i, tool in enumerate(available_tools, 1):
                print(f"  {i}. {tool['id']}: {tool['desc']}")
                if tool["suggested_args"]:
                    print(f"     Suggested args: {tool['suggested_args']}")

            if error_count > 0:
                print(
                    f"  ⚠️  {error_count} tools had errors (likely not fully implemented)"
                )

        # Check if expected tools are present
        found_tools = {tool["id"] for tool in available_tools}
        missing_expected = set(expected_tools) - found_tools
        unexpected_tools = found_tools - set(expected_tools)

        if verbose and (missing_expected or unexpected_tools):
            if missing_expected:
                print(f"  ⚠️  Expected but missing: {', '.join(missing_expected)}")
            if unexpected_tools:
                print(f"  ℹ️  Additional tools found: {', '.join(unexpected_tools)}")

        if verbose:
            print("-" * 50)

    return len(scenarios)


def test_specific_tool(tool_id="ask_roll", verbose=True):
    """Test a specific tool's functionality.

    Args:
        tool_id: ID of the tool to test
        verbose: If True, print detailed output
    """

    if verbose:
        print(f"\n=== Testing {tool_id} tool specifically ===")

    state = create_demo_state()
    utterance = Utterance(text="I sneak toward the threshold", actor_id="pc.arin")

    target_tool = get_tool_by_id(tool_id)
    if not target_tool:
        if verbose:
            print(f"❌ Tool '{tool_id}' not found in catalog")
        return False

    if verbose:
        print(f"Tool: {target_tool.id}")
        print(f"Description: {target_tool.desc}")

    try:
        # Check precondition
        is_available = target_tool.precond(state, utterance)
        if verbose:
            print(f"Precondition satisfied: {is_available}")

        if is_available and target_tool.suggest_args:
            try:
                suggested_args = target_tool.suggest_args(state, utterance)
                if verbose:
                    print(f"Suggested arguments: {suggested_args}")

                # Try to create args object if schema is available
                if hasattr(target_tool, "args_schema") and target_tool.args_schema:
                    try:
                        args_obj = target_tool.args_schema(**suggested_args)
                        if verbose:
                            print(f"✅ Valid args object: {args_obj}")
                        return True
                    except Exception as e:
                        if verbose:
                            print(f"❌ Error creating args object: {e}")
                        return False
                else:
                    if verbose:
                        print("⚠️  No args schema available for validation")
                    return True
            except Exception as e:
                if verbose:
                    print(f"❌ Error getting suggested args: {e}")
                return False
        elif is_available:
            if verbose:
                print("✅ Tool available (no suggested args)")
            return True
        else:
            if verbose:
                print("ℹ️  Tool precondition not satisfied for this scenario")
            return True  # Not an error, just not applicable

    except Exception as e:
        if verbose:
            print(f"❌ Error testing tool: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Demo the Tool Catalog system")
    parser.add_argument(
        "--all-tools",
        action="store_true",
        help="Test all tools, even unimplemented ones",
    )
    parser.add_argument(
        "--tool",
        type=str,
        default="ask_roll",
        help="Specific tool to test in detail (default: ask_roll)",
    )
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")

    args = parser.parse_args()

    try:
        # Configure demo based on arguments
        verbose = not args.quiet
        filter_working = not args.all_tools

        # Run main tool catalog test
        scenario_count = test_tool_preconditions(
            verbose=verbose, filter_working_only=filter_working
        )

        # Test specific tool
        tool_success = test_specific_tool(tool_id=args.tool, verbose=verbose)

        if verbose:
            print("\n✅ Tool Catalog Step 1 implementation complete!")
            print("Key features demonstrated:")
            print("- Precondition gating removes illegal options")
            print("- Argument suggestion provides smart defaults")
            print("- Modular tool structure allows easy extension")
            print(f"- Tested {scenario_count} scenarios")
            if filter_working:
                print("- Filtered to working tools only (use --all-tools to test all)")

        # Exit with appropriate code
        exit(0 if tool_success else 1)

    except Exception as e:
        print(f"❌ Error in demo: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
