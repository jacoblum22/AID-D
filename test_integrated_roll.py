"""
Integrated test for Roll Decision + Dice Rolling System.

This script:
1. Analyzes player input to decide if a roll is needed
2. If yes, automatically runs the dice roll with suggested Domain/Style/DC
3. Displays the full workflow from input → decision → roll → outcome

Usage:
    python test_integrated_roll.py
"""

import json
import os
import random
from typing import Optional
from openai import OpenAI
import config

# Import the roll decision function
from test_roll_decision_interactive import decide_roll_or_narrate

# Import character and roll functions
from test_roll_interactive import (
    create_test_character,
    execute_roll,
    display_character_sheet,
)

# Initialize OpenAI client
client = OpenAI(api_key=config.OPENAI_API_KEY)


def display_integrated_results(
    player_input: str,
    decision: dict,
    roll_results: Optional[dict] = None,
    context: str = "",
):
    """Display the full workflow from decision to roll outcome."""
    print("\n" + "=" * 70)
    print("  🎮 INTEGRATED ROLL SYSTEM")
    print("=" * 70)

    if context:
        print(f"\n📍 Scene Context: {context}")

    print(f"\n💬 Player Input:")
    print(f'   "{player_input}"')

    # Step 1: Decision
    decision_emoji = "🎲" if decision["decision"] == "roll" else "📖"
    decision_text = decision["decision"].upper()

    print(f"\n{decision_emoji} Decision: {decision_text}")
    print(f"   Reasoning: {decision.get('reasoning', 'N/A')}")
    print(f"   Confidence: {decision.get('confidence', 'N/A')}")

    if decision["decision"] == "roll":
        if decision.get("suggested_action_if_roll"):
            suggested = decision["suggested_action_if_roll"]
            print(f"\n🎯 Suggested Roll:")
            print(f"   Domain: {suggested.get('domain', 'N/A').capitalize()}")
            print(f"   Style: {suggested.get('style', 'N/A').capitalize()}")
            print(f"   DC: {suggested.get('dc_hint', 'N/A')}")

        # Step 2: Roll (if performed)
        if roll_results:
            print(f"\n🎲 Dice Roll:")
            print(
                f"   Formula: d20 + {roll_results['domain_rating']}d{roll_results['style_die_size']}"
            )

            # Display roll breakdown
            domain_dice_str = (
                " + ".join(str(d) for d in roll_results["domain_dice"])
                if roll_results["domain_dice"]
                else "0"
            )
            print(f"   d20: {roll_results['d20']}")
            print(f"   Domain Dice: [{domain_dice_str}] = {roll_results['domain_sum']}")
            print(f"   Total: {roll_results['total']}")

            # Display outcome
            margin = roll_results["margin"]
            outcome_band = roll_results["outcome_band"]

            # Outcome emoji
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
            print(f"   DC: {roll_results['dc']}")
            print(f"   Margin: {margin:+d}")
    else:
        print(f"\n📖 No roll needed - DM narrates the outcome.")

    print("=" * 70 + "\n")


def run_integrated_test():
    """Run the integrated decision + roll test."""
    print("\n" + "=" * 70)
    print("  INTEGRATED ROLL DECISION + DICE ROLLING SYSTEM")
    print("=" * 70)
    print("\nThis tool:")
    print("  1. Decides if player input needs a roll")
    print("  2. If yes, runs the dice roll automatically")
    print("  3. Shows the full workflow and outcome")
    print("\nExamples to try:")
    print("  - 'I sneak past the sleeping guard'")
    print("  - 'What's the name of this city?'")
    print("  - 'I convince the merchant to give me a discount'")
    print("  - 'Do I have a map?'")
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

        # Step 1: Get decision from LLM
        print("\n🤔 Analyzing with GPT-5-nano...")
        decision = decide_roll_or_narrate(player_input, context)

        # Step 2: If roll, perform it
        roll_results = None
        if decision["decision"] == "roll" and decision.get("suggested_action_if_roll"):
            suggested = decision["suggested_action_if_roll"]
            domain = suggested.get("domain", "physical")
            style = suggested.get("style", "forceful")
            dc = suggested.get("dc_hint", 12)

            print("🎲 Rolling dice...")
            roll_results = execute_roll(
                character=character, domain=domain, style=style, dc=dc
            )

        # Display integrated results
        display_integrated_results(player_input, decision, roll_results, context)


if __name__ == "__main__":
    run_integrated_test()
