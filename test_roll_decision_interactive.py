"""
Interactive test for the Roll Decision System.

This script tests GPT-5-nano's ability to decide whether player input
requires a dice roll or should just be narrated.

Usage:
    python test_roll_decision_interactive.py
"""

import json
from openai import OpenAI
import config

# Initialize OpenAI client
client = OpenAI(api_key=config.OPENAI_API_KEY)


def decide_roll_or_narrate(player_input: str, context: str = "") -> dict:
    """
    Use GPT-5-nano to decide if player input requires a roll or just narration.

    Args:
        player_input: What the player said/typed
        context: Optional scene context to help inform the decision

    Returns:
        Dictionary with decision, reasoning, confidence, and suggested action
    """
    # Cached system prompt for roll decision (auto-cached by OpenAI)
    system_prompt = """You are a D&D Game Master deciding whether player input requires a dice roll or just narration.

OUTPUT FORMAT: Return ONLY valid JSON with these exact fields:
{
  "decision": "roll|narrate",
  "reasoning": "brief 1-sentence explanation",
  "confidence": "high|medium|low",
  "suggested_action_if_roll": {
    "domain": "physical|mental|social|insight",
    "style": "forceful|subtle|precise|clever|resilient|graceful|chaotic",
    "dc_hint": 8-30
  }
}

=== CORE PRINCIPLES ===

**ROLL when:**
• Character is acting in the world (not player asking meta questions)
• Outcome is UNCERTAIN (not guaranteed)
• Stakes MATTER (failure has consequences)
• Success not guaranteed by fictional positioning

**NARRATE when:**
• Player asking meta/rules questions
• Trivial/automatic action (no uncertainty)
• Guaranteed success (good positioning)
• Impossible action (just say no)
• Pure flavor (no mechanical stakes)

=== DECISION CRITERIA ===

1. PLAYER VS. CHARACTER
• "What's the DC for climbing?" → NARRATE (player meta question)
• "How do spell slots work?" → NARRATE (rules question)
• "What's the name of this city?" → NARRATE (player asking DM for info)
• "Do I have a map?" → NARRATE (checking inventory/possessions, not uncertain)
• "Would I know how hard this is?" → ROLL (character assessing difficulty)
• "Do I know/remember/recognize [UNCERTAIN thing]?" → ROLL (character knowledge check if obscure/specialized)
• "Do I know/remember/recognize [COMMON thing]?" → NARRATE (if everyone would know or character's background guarantees it)
• "I climb the wall" → Maybe ROLL (character action)

**KEY DISTINCTIONS:**
1. Inventory/Possessions ("Do I have...") → NARRATE (either you have it or you don't - check inventory or ask DM)
2. Common knowledge → NARRATE (just tell them)
3. Obscure knowledge → ROLL (Mental check, use CONTEXT)
4. Past actions ("Did I previously...") → NARRATE (no retroactive rolls)

2. UNCERTAINTY + STAKES (BOTH must exist)
• Crossing small stream → NARRATE (no uncertainty, no stakes)
• Sneaking past guards → ROLL (uncertain + stakes)
• Picking up a rock → NARRATE (no uncertainty)
• Scaling crumbling tower → ROLL (uncertain + stakes)

3. FICTIONAL POSITIONING
• "I check under the rug" → NARRATE (if it's there, they find it)
• "I search for hidden compartments" → ROLL (uncertain discovery)
• "I open the unlocked door" → NARRATE (guaranteed)
• "I leap across the chasm" → ROLL (risky)

4. ACTION VERBS (Keywords)

**Suggest ROLL for:**
• Attempt verbs: try, attempt, strive
• Perception: search, look for, investigate, notice, spot
• Physical: climb, jump, sneak, dodge, swim, grapple
• Social: persuade, convince, deceive, intimidate, charm, perform
• Combat: attack, defend, parry, feint
• Recall/Knowledge: "Do I know...", "Do I remember...", "Do I recognize...", "Would I know..."
  (Testing CHARACTER's knowledge of uncertain facts)

**Suggest NARRATE for:**
• Meta questions: "What's...", "How does...", "Can you tell me..."
  (Player asking DM to provide information directly)
• Trivial: walk, pick up (simple objects), open (unlocked doors)
• Clarifications: "Is there...", "What does X look like..." (DM describing scene)
• Inventory/Possessions: "Do I have...", "Am I carrying...", "Did I bring..."
  (Checking possessions is not uncertain - either you have it or you don't)
• Past events: "Did I previously..." (not retroactive rolls for past actions)

5. CONSEQUENCE VS. FLAVOR
• "I balance my dagger to impress" → NARRATE (no stakes)
• "I flip across the room" → NARRATE (pure flavor unless guards/traps)
• "I juggle torches for tips" → ROLL (stakes: embarrassment/money)

=== CONFIDENCE LEVELS ===
• **high**: Clear keywords (attack, sneak, persuade) or obvious meta question
• **medium**: Could go either way, depends on context
• **low**: Very ambiguous, need more info

=== EXAMPLES ===

Input: "Do I have a map of the local area?"
{
  "decision": "narrate",
  "reasoning": "Checking inventory/possessions - either they have it or don't, no roll needed",
  "confidence": "high",
  "suggested_action_if_roll": null
}

Input: "I try to sneak past the sleeping guards."
{
  "decision": "roll",
  "reasoning": "Character attempting stealth with failure consequences",
  "confidence": "high",
  "suggested_action_if_roll": {"domain": "physical", "style": "subtle", "dc_hint": 15}
}

Input: "What's the name of the tavern again?"
{
  "decision": "narrate",
  "reasoning": "Player asking DM for world information directly",
  "confidence": "high",
  "suggested_action_if_roll": null
}

Input: "Do I know the name of this ancient city the merchant is describing?"
Context: "little-known, abandoned city"
{
  "decision": "roll",
  "reasoning": "Testing character's knowledge of obscure historical information",
  "confidence": "high",
  "suggested_action_if_roll": {"domain": "mental", "style": "precise", "dc_hint": 18}
}

Input: "Do I know the name of the capital city?"
{
  "decision": "narrate",
  "reasoning": "Common knowledge that any resident would know",
  "confidence": "high",
  "suggested_action_if_roll": null
}

Input: "I open the door."
{
  "decision": "narrate",
  "reasoning": "Trivial action unless door is locked or trapped",
  "confidence": "medium",
  "suggested_action_if_roll": null
}

Input: "I convince the merchant to lower the price."
{
  "decision": "roll",
  "reasoning": "Social persuasion with uncertain outcome and stakes",
  "confidence": "high",
  "suggested_action_if_roll": {"domain": "social", "style": "clever", "dc_hint": 15}
}

Input: "I attack the bandit with my sword."
{
  "decision": "roll",
  "reasoning": "Combat action with clear uncertainty and stakes",
  "confidence": "high",
  "suggested_action_if_roll": {"domain": "physical", "style": "forceful", "dc_hint": 12}
}

Input: "Do I recognize this noble family's crest?"
Context: "Character is a court diplomat"
{
  "decision": "narrate",
  "reasoning": "Character's background guarantees they know noble heraldry",
  "confidence": "high",
  "suggested_action_if_roll": null
}

Analyze the player input and respond ONLY with valid JSON."""

    try:
        # Build input with optional context
        user_message = f"Player input: {player_input}"
        if context:
            user_message += f"\nScene context: {context}"

        # Use Responses API with low reasoning for quality
        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "developer", "content": system_prompt},  # Auto-cached
                {"role": "user", "content": user_message},
            ],
            reasoning={"effort": "low"},
            text={"format": {"type": "json_object"}},
            max_output_tokens=1000,  # Increased from 300 to 1000
        )

        # Extract text from response
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore

        # Log cache usage
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            input_tokens = usage.input_tokens
            cached_tokens = (
                getattr(usage.input_tokens_details, "cached_tokens", 0)
                if hasattr(usage, "input_tokens_details")
                else 0
            )
            if cached_tokens > 0:
                cache_savings = (
                    (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                )
                print(
                    f"💰 Cache hit! {cached_tokens}/{input_tokens} tokens cached ({cache_savings:.0f}% saved)"
                )

        if not output_text or output_text.strip() == "":
            raise ValueError("LLM returned empty content")

        result = json.loads(output_text)

        # Validate required fields
        if "decision" not in result or result["decision"] not in ["roll", "narrate"]:
            raise ValueError("Invalid or missing 'decision' field")

        # Normalize to lowercase
        result["decision"] = result["decision"].lower()

        return result

    except Exception as e:
        print(f"⚠️  LLM decision failed: {e}")
        print("Using fallback: narrate (safe default)")
        return {
            "decision": "narrate",
            "reasoning": "Fallback due to LLM error",
            "confidence": "low",
            "suggested_action_if_roll": None,
        }


def display_decision(player_input: str, decision: dict, context: str = ""):
    """Display the decision results in a formatted way."""
    print("\n" + "=" * 70)
    print("  🎭 ROLL DECISION ANALYSIS")
    print("=" * 70)

    if context:
        print(f"\n📍 Scene Context: {context}")

    print(f"\n💬 Player Input:")
    print(f'   "{player_input}"')

    decision_emoji = "🎲" if decision["decision"] == "roll" else "📖"
    decision_text = decision["decision"].upper()

    print(f"\n{decision_emoji} Decision: {decision_text}")
    print(f"   Reasoning: {decision.get('reasoning', 'N/A')}")
    print(f"   Confidence: {decision.get('confidence', 'N/A')}")

    if decision["decision"] == "roll" and decision.get("suggested_action_if_roll"):
        suggested = decision["suggested_action_if_roll"]
        print(f"\n🎯 Suggested Roll:")
        print(f"   Domain: {suggested.get('domain', 'N/A').capitalize()}")
        print(f"   Style: {suggested.get('style', 'N/A').capitalize()}")
        print(f"   DC Hint: {suggested.get('dc_hint', 'N/A')}")

    print("=" * 70 + "\n")


def run_interactive_test():
    """Run the interactive roll decision test."""
    print("\n" + "=" * 70)
    print("  ROLL VS. NARRATE DECISION SYSTEM TEST")
    print("=" * 70)
    print("\nThis tool analyzes player input to determine if a dice roll is needed.")
    print("\nExamples to try:")
    print("  - 'I sneak past the sleeping guard'")
    print("  - 'What's the name of this city?'")
    print("  - 'I convince the merchant to give me a discount'")
    print("  - 'I open the door'")
    print("  - 'I attack the orc with my sword'")
    print("\nType 'quit' to exit.")
    print("=" * 70 + "\n")

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

        if not player_input:
            print("⚠️  Please enter some text.\n")
            continue

        # Get decision from LLM
        print("\n🤔 Analyzing with GPT-5-nano...")
        decision = decide_roll_or_narrate(player_input, context)

        # Display results
        display_decision(player_input, decision, context)


if __name__ == "__main__":
    run_interactive_test()
