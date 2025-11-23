"""
Test the combined Roll Decision + Action Interpretation analyzer.

This tests the single LLM call that decides:
1. Roll or Narrate?
2. If Roll: Domain, Style, DC

Usage:
    python test_roll_analyzer.py
"""

from roll_analyzer import analyze_player_action
from test_roll_interactive import (
    create_test_character,
    execute_roll,
    display_character_sheet,
)
from typing import Optional


def display_analysis_results(
    player_input: str,
    analysis: dict,
    roll_results: Optional[dict] = None,
    context: str = "",
):
    """Display the analysis and optional roll results."""
    print("\n" + "=" * 70)
    print("  🎯 COMBINED ROLL ANALYZER TEST")
    print("=" * 70)

    if context:
        print(f"\n📍 Scene Context: {context}")

    print(f"\n💬 Player Input:")
    print(f'   "{player_input}"')

    # Decision
    decision_emoji = "🎲" if analysis["decision"] == "roll" else "📖"
    decision_text = analysis["decision"].upper()

    print(f"\n{decision_emoji} Decision: {decision_text}")
    print(f"   Reasoning: {analysis.get('reasoning', 'N/A')}")
    print(f"   Confidence: {analysis.get('confidence', 'N/A')}")

    # Roll details (if decision was roll)
    if analysis["decision"] == "roll" and analysis.get("roll_details"):
        details = analysis["roll_details"]
        print(f"\n🎯 Roll Details:")
        print(f"   Action: {details.get('action_description', 'N/A')}")
        print(f"   Domain: {details.get('domain', 'N/A').capitalize()}")
        print(f"   Style: {details.get('style', 'N/A').capitalize()}")
        print(f"   DC: {details.get('dc', 'N/A')}")

        # Roll results (if performed)
        if roll_results:
            print(f"\n🎲 Dice Roll:")
            print(
                f"   Formula: d20 + {roll_results['domain_rating']}d{roll_results['style_die_size']}"
            )

            domain_dice_str = (
                " + ".join(str(d) for d in roll_results["domain_dice"])
                if roll_results["domain_dice"]
                else "0"
            )
            print(f"   d20: {roll_results['d20']}")
            print(f"   Domain Dice: [{domain_dice_str}] = {roll_results['domain_sum']}")
            print(f"   Total: {roll_results['total']}")

            # Outcome
            margin = roll_results["margin"]
            outcome_band = roll_results["outcome_band"]

            if outcome_band == "Fail":
                outcome_emoji = "❌"
            elif outcome_band == "Mixed":
                outcome_emoji = "⚠️"
            elif outcome_band == "Clean":
                outcome_emoji = "✅"
            elif outcome_band == "Strong":
                outcome_emoji = "💪"
            else:  # Dramatic
                outcome_emoji = "🌟"

            print(f"\n{outcome_emoji} Outcome: {outcome_band}")
            print(f"   Margin: {margin:+d}")
    else:
        print(f"\n📖 No roll needed - DM narrates the outcome.")

    print("=" * 70 + "\n")


def main():
    """Run the interactive combined analyzer test."""
    print("\n" + "=" * 70)
    print("  COMBINED ROLL DECISION + INTERPRETATION TEST")
    print("=" * 70)
    print("\nThis tool combines LLM 2 + LLM 3 into a single call:")
    print("  1. Analyzes player input (GPT-5-nano)")
    print("  2. Decides: Roll or Narrate?")
    print("  3. If Roll: Determines Domain, Style, DC")
    print("  4. Optionally performs the dice roll")
    print("\nExamples to try:")
    print("  - 'I sneak past the sleeping guard'")
    print("  - 'What's the name of this city?'")
    print("  - 'I convince the merchant to give me a discount'")
    print("  - 'Do I have a map?'")
    print("  - 'Do I know the ancient history of this place?'")
    print("\nType 'quit' to exit, 'character' to view character sheet.")
    print("=" * 70 + "\n")

    # Create test character
    character = create_test_character()

    # Optional: add scene context
    use_context = input("🌍 Add scene context? (y/n): ").strip().lower()
    context = ""
    if use_context == "y":
        context = input("📍 Enter scene context: ").strip()
        print()

    # Ask if they want to auto-roll
    auto_roll = (
        input("🎲 Automatically perform rolls when suggested? (y/n): ").strip().lower()
        == "y"
    )
    print()

    while True:
        # Get player input
        player_input = input("💬 What does the player say? ").strip()

        if player_input.lower() == "quit":
            print("\n👋 Exiting. Thanks for testing!\n")
            break

        if player_input.lower() == "character":
            display_character_sheet(character)
            continue

        if not player_input:
            print("⚠️  Please enter some text.\n")
            continue

        # Analyze with combined LLM
        print("\n🤔 Analyzing with GPT-5-nano (combined decision + interpretation)...")
        analysis = analyze_player_action(player_input, context)

        # If roll, optionally perform it
        roll_results = None
        if (
            auto_roll
            and analysis["decision"] == "roll"
            and analysis.get("roll_details")
        ):
            details = analysis["roll_details"]
            print("🎲 Rolling dice...")
            roll_results = execute_roll(
                character=character,
                domain=details.get("domain", "physical"),
                style=details.get("style", "forceful"),
                dc=details.get("dc", 12),
            )

        # Display results
        display_analysis_results(player_input, analysis, roll_results, context)


if __name__ == "__main__":
    main()
