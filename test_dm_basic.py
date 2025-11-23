"""
Basic AI DM Interactive Test

This is a simple interactive test to experience the DM system prompt with GPT-5.
No lore wiki, no complex tools yet - just the core DM experience.

Usage:
    python test_dm_basic.py
"""

from openai import OpenAI
import os
import config
from dm_system_prompt import DM_SYSTEM_PROMPT
from lore_extractor import process_narration_for_lore, LORE_FILE, NARRATION_FILE
from lore_retrieval import retrieve_relevant_context, format_context_for_prompt
from roll_analyzer import analyze_player_action
from test_roll_interactive import create_test_character, execute_roll
from cache_logger import log_cache_stats

# Initialize OpenAI client
client = OpenAI(api_key=config.OPENAI_API_KEY)

# Conversation history
conversation = []

# Test character for dice rolling
test_character = create_test_character()

# Last DM narration (for lore retrieval context)
last_dm_narration = ""

# Current lore context (persists across batch of 5 turns)
current_lore_context = {}

# Max conversation window (last N back-and-forths)
MAX_CONVERSATION_WINDOW = 5

# Debug mode - print all prompts
DEBUG_PROMPTS = True

# Turn counter
turn_number = 0


def reset_world_data():
    """Reset lore and narration history files."""
    try:
        # Reset lore
        with open(LORE_FILE, "w", encoding="utf-8") as f:
            f.write('{"entries": []}')

        # Reset narration history
        with open(NARRATION_FILE, "w", encoding="utf-8") as f:
            f.write("[]")

        print("🗑️  World lore and narration history cleared.")
    except Exception as e:
        print(f"⚠️  Error resetting files: {e}")


def call_dm(user_message: str, model: str = "gpt-5") -> str:
    """
    Call the DM with user message and get response.

    Args:
        user_message: What the player said
        model: Which OpenAI model to use (gpt-5, gpt-4o, gpt-4o-mini, or o1)

    Returns:
        DM's response
    """
    global turn_number, last_dm_narration, current_lore_context
    turn_number += 1

    # Calculate which turn numbers are already in the conversation window
    # Conversation window holds last MAX_CONVERSATION_WINDOW exchanges
    # Each exchange = player + DM = 2 messages, so we need to map messages to turn numbers
    #
    # Example: If we're on turn 6 with window=3:
    # - Conversation has turns: 4, 5, 6 (last 3 turns)
    # - So exclude_turns = [4, 5, 6]
    # - Lore retriever can then select from turns 1, 2, 3
    exclude_turn_numbers = []
    if turn_number > MAX_CONVERSATION_WINDOW:
        # Window contains turns: (current - window + 1) to current
        exclude_turn_numbers = list(
            range(turn_number - MAX_CONVERSATION_WINDOW + 1, turn_number + 1)
        )

    # Retrieve relevant lore EVERY turn (except turn 1 when no lore exists yet)
    if turn_number > 1:
        print(f"🔍 Retrieving relevant lore...")
        current_lore_context = retrieve_relevant_context(
            user_message, last_dm_narration, exclude_turn_numbers=exclude_turn_numbers
        )
    else:
        # Turn 1: No lore exists yet
        current_lore_context = {"keywords": [], "lore_entries": [], "narrations": []}

    # Format context for prompt
    context_text = format_context_for_prompt(current_lore_context)

    # Add user message to conversation (WITHOUT lore - lore goes separately before)
    conversation.append({"role": "user", "content": user_message})

    # Keep only last N exchanges (player + DM = 2 messages per exchange)
    # So keep last MAX_CONVERSATION_WINDOW * 2 messages
    max_messages = MAX_CONVERSATION_WINDOW * 2
    recent_conversation = (
        conversation[-max_messages:]
        if len(conversation) > max_messages
        else conversation
    )

    # No need for deduplication anymore - lore retrieval already excludes conversation window turns

    # Build messages array: system, lore (if any), then conversation
    messages = [
        {"role": "system", "content": DM_SYSTEM_PROMPT},
    ]

    # Add lore context BEFORE conversation if it exists
    if context_text:
        messages.append({"role": "user", "content": context_text})

    # Add recent conversation
    messages.extend(recent_conversation)

    # Debug: Print full prompt
    if DEBUG_PROMPTS:
        print("\n" + "=" * 70)
        print("🔍 DM PROMPT DEBUG")
        print("=" * 70)
        print(f"\n[SYSTEM PROMPT]")
        print(f"\n📋 DM SYSTEM PROMPT (FULL):")
        print("=" * 70)
        print(DM_SYSTEM_PROMPT)
        print("=" * 70 + "\n")
        print(f"\n[CONVERSATION MESSAGES] ({len(recent_conversation)} messages)")
        for i, msg in enumerate(recent_conversation):
            role = msg["role"]
            content = msg["content"]
            print(f"\n--- Message {i+1} ({role.upper()}) ---")
            print(content)  # No truncation
        print("\n" + "=" * 70 + "\n")

    try:
        # Call OpenAI API
        # Note: GPT-5/o-series have different parameters than GPT-4o
        if (
            model.startswith("gpt-5")
            or model.startswith("o1")
            or model.startswith("o3")
        ):
            # GPT-5 and o-series:
            # - Use max_completion_tokens instead of max_tokens
            # - Temperature is NOT supported (only default value 1.0 is used)
            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                max_completion_tokens=4000,  # GPT-5/o-series parameter (safety limit, not target)
                # No temperature parameter - GPT-5 only supports temperature=1.0 (default)
            )
        else:
            # GPT-4o and older models use standard parameters
            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=0.8,  # Creative but not too random
                max_tokens=4000,  # GPT-4o/older models parameter (safety limit, not target)
            )

        # Extract response
        dm_response = response.choices[0].message.content or ""

        # Log cache usage (always log, even if 0%)
        if hasattr(response, "usage"):
            usage = response.usage
            cached_tokens = 0
            if hasattr(usage, "prompt_tokens_details"):
                details = usage.prompt_tokens_details  # type: ignore
                if hasattr(details, "cached_tokens"):  # type: ignore
                    cached_tokens = details.cached_tokens or 0  # type: ignore

            # Always log to track all calls
            log_cache_stats("DM_Narrator", cached_tokens, usage.prompt_tokens, model)  # type: ignore

            if cached_tokens > 0:
                cache_pct = cached_tokens / usage.prompt_tokens * 100  # type: ignore
                print(f"\n💾 CACHE HIT: {cached_tokens} tokens cached ({cache_pct:.1f}% of prompt)\n")  # type: ignore

        # Add to conversation history
        conversation.append({"role": "assistant", "content": dm_response})

        # Update last narration for next turn
        last_dm_narration = dm_response

        return dm_response

    except Exception as e:
        return f"⚠️ Error calling DM: {e}"


def main():
    """Run the interactive DM test."""
    global turn_number, last_dm_narration, current_lore_context

    # Reset world lore and narration history on startup
    print("\n🗑️  Resetting world lore and narration history...")
    reset_world_data()

    print("\n" + "=" * 70)
    print("  🎲 AI DUNGEON MASTER - BASIC TEST")
    print("=" * 70)
    print("\nYou are testing the core DM system prompt with GPT-5.")
    print("The DM will narrate and guide your adventure.")
    print("\nCommands:")
    print("  - Type your actions and dialogue normally")
    print("  - 'quit' to exit")
    print("  - 'reset' to clear conversation")
    print("  - 'clear_lore' to reset world lore and narration history")
    print("  - 'character' to view your character stats")
    print("  - 'model <name>' to switch models (gpt-5, gpt-4o, gpt-4o-mini, o1)")
    print(f"\n📝 Lore system:")
    print(
        f"   • Lore extraction: EVERY turn (captures critical names/facts immediately)"
    )
    print(
        f"   • Lore retrieval: Every turn (searches relevant lore based on player input)"
    )
    print(f"   • Uses gpt-5-nano for extraction (cheap + fast)")
    print(f"\n🎲 Roll system:")
    print(f"   • Roll detection: Analyzes each action with gpt-5-nano")
    print(f"   • Auto-rolls if action needs dice (d20 + Domain + Style)")
    print(f"   • Type 'character' to see your Domain/Style ratings")
    print(f"\n🔄 Conversation window: Last {MAX_CONVERSATION_WINDOW} back-and-forths")
    print("=" * 70 + "\n")

    # Starting scenario - no specific setting, let DM create varied openings
    print("🌟 THE DM BEGINS THE ADVENTURE:\n")
    initial_scene = call_dm(
        "Start a brief adventure. Give a vivid opening scene (2-3 paragraphs) and end with a hook for action.",
        model="gpt-5.1",
    )
    print(f"DM: {initial_scene}\n")

    # Extract lore from initial scene
    process_narration_for_lore(
        "Start a brief adventure. Give a vivid opening scene (2-3 paragraphs) and end with a hook for action.",
        initial_scene,
        turn_number,
        existing_lore=current_lore_context.get("lore_entries", []),
    )

    print("=" * 70 + "\n")

    current_model = "gpt-5.1"  # Default to gpt-5.1 to match initial scene

    while True:
        # Get player input
        player_input = input("You: ").strip()

        if not player_input:
            continue

        if player_input.lower() == "quit":
            print(f"\n👋 Thanks for playing! Session lasted {turn_number} turns.")
            print(f"📝 Narrations saved to narration_history.json")
            print(f"📚 Lore saved to world_lore.json\n")
            break

        if player_input.lower() == "reset":
            conversation.clear()
            turn_number = 0
            last_dm_narration = ""
            current_lore_context = {}
            print("\n🔄 Conversation reset. Starting fresh.\n")
            continue

        if player_input.lower() == "clear_lore":
            reset_world_data()
            print()
            continue

        if player_input.lower() == "character":
            from test_roll_interactive import display_character_sheet

            display_character_sheet(test_character)
            continue

        if player_input.lower().startswith("model "):
            new_model = player_input[6:].strip()
            if new_model in ["gpt-5.1", "gpt-5", "gpt-4o", "gpt-4o-mini", "o1"]:
                current_model = new_model
                print(f"\n🔧 Switched to {current_model}\n")
            else:
                print(
                    "\n⚠️  Invalid model. Use: gpt-5.1, gpt-5, gpt-4o, gpt-4o-mini, or o1\n"
                )
            continue

        # Check if roll is needed BEFORE calling DM
        print("🤔 Analyzing action...")
        try:
            roll_analysis = analyze_player_action(
                player_input, context=last_dm_narration
            )
            print(f"[DEBUG] Roll analysis result: {roll_analysis}")
        except Exception as e:
            print(f"⚠️  LLM analysis failed: {e}")
            import traceback

            traceback.print_exc()
            roll_analysis = {"decision": "narrate", "roll_details": None}

        # If roll is needed, execute it and show results
        roll_outcome_text = ""
        if roll_analysis["decision"] == "roll" and roll_analysis.get("roll_details"):
            details_list = roll_analysis["roll_details"]
            if not isinstance(details_list, list):
                details_list = [details_list]  # Backwards compatibility

            # Execute all rolls
            all_outcomes = []
            for details in details_list:
                print(f"🎲 Roll needed: {details['action_description']}")
                print(
                    f"   {details['domain'].capitalize()} + {details['style'].capitalize()}, DC {details['dc']}"
                )

                # Execute the roll
                roll_results = execute_roll(
                    character=test_character,
                    domain=details["domain"],
                    style=details["style"],
                    dc=details["dc"],
                )

                # Format roll results for display
                domain_dice_str = (
                    " + ".join(str(d) for d in roll_results["domain_dice"])
                    if roll_results["domain_dice"]
                    else "0"
                )
                print(
                    f"   d20: {roll_results['d20']}, Domain: [{domain_dice_str}] = {roll_results['domain_sum']}"
                )
                print(f"   Total: {roll_results['total']} vs DC {roll_results['dc']}")

                # Show outcome
                margin = roll_results["margin"]
                outcome = roll_results["outcome_band"]
                if outcome == "Fail":
                    print(f"   ❌ {outcome}: {margin:+d}\n")
                elif outcome == "Mixed":
                    print(f"   ⚠️  {outcome}: {margin:+d}\n")
                elif outcome == "Clean":
                    print(f"   ✅ {outcome}: {margin:+d}\n")
                elif outcome == "Strong":
                    print(f"   💪 {outcome}: {margin:+d}\n")
                else:  # Dramatic
                    print(f"   🌟 {outcome}: {margin:+d}\n")

                # Collect outcome for DM
                all_outcomes.append(
                    f"{details['action_description']}: {details['domain'].capitalize()}+{details['style'].capitalize()} = {roll_results['total']} vs DC {details['dc']} → {outcome} ({margin:+d})"
                )

            # Pass all roll outcomes to DM
            if len(all_outcomes) == 1:
                roll_outcome_text = f"\n[ROLL RESULT: {all_outcomes[0]}]"
            else:
                roll_outcome_text = (
                    "\n[ROLL RESULTS:\n"
                    + "\n".join(f"  - {o}" for o in all_outcomes)
                    + "\n]"
                )
        else:
            print("📖 No roll needed - narrating...\n")

        # Get DM response (with roll outcome if applicable)
        dm_input = player_input + roll_outcome_text
        dm_response = call_dm(dm_input, model=current_model)
        print(f"DM: {dm_response}\n")

        # Extract lore AFTER displaying narration
        process_narration_for_lore(
            player_input,
            dm_response,
            turn_number,
            existing_lore=current_lore_context.get("lore_entries", []),
        )

        print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
