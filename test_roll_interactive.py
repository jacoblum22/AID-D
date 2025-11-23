"""
Interactive dice roll tester for d20 + Domain + Style system.

This script:
1. Loads a test character with Domain/Style ratings
2. Prompts you to describe an action
3. Uses GPT-5-nano to interpret which Domain+Style+DC applies
4. Auto-rolls using your character's ratings
5. Shows detailed results with margin bands
"""

import os
import sys
import json
import random
from typing import Optional
from openai import OpenAI

# Add project root to path
_project_root = os.path.abspath(os.path.dirname(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import PC, HP, Stats

# Import API key from config
try:
    from config import OPENAI_API_KEY
except ImportError:
    raise ImportError("Could not import OPENAI_API_KEY from config.py. Make sure config.py exists with your API key.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Domain and Style interpretation matrix
DOMAIN_STYLE_MATRIX = """
| **Domain ↓ / Style →** | **Forceful** | **Subtle** | **Precise** | **Clever** | **Resilient** | **Graceful** | **Chaotic** |
|------------------------|--------------|------------|-------------|------------|---------------|--------------|-------------|
| **Physical** | Brawling, breaking, shoving | Stealth, pickpocketing, tailing | Surgery, fine tools, lockpicks | Parkour, jury-rigging gear | Marathon, damage soak, grapples | Martial arts, acrobatics, dance | Berserk rush, improvised weapons |
| **Mental** | Bulldozing logic, hard rhetoric | Deception, traps, misdirection | Calculation, recall, proofs | Lateral ideas, hacks, inventions | Deep focus, long study | Elegant theory, clear exposition | Erratic leaps, wild hypotheses |
| **Social** | Command presence, rallying | Intrigue, rumors, manipulation | Diplomacy, contracts, etiquette | Banter, improv persuasion | Hold the line, poker face | Performance, charm, poise | Stir the crowd, start a riot |
| **Insight** | Willpower, conviction, zeal | Read tells, sense motives | Perception, tracking, awareness | See patterns, trickster wisdom | Resist sway, fearlessness | Flow state, serene clarity | Gut hunch, prophetic guess |
"""

DC_LADDER = """
| DC | Difficulty | Description |
|----|------------|-------------|
| 8 | Easy | Routine tasks, minimal risk |
| 10 | Routine | Standard professional work |
| 12 | Tricky | Requires skill and focus |
| 15 | Hard | Challenging even for experts |
| 18 | Expert | Top-tier professional capability |
| 20 | Heroic | Extraordinary feats |
| 25 | Epic | Legendary accomplishments |
| 30 | Mythic | God-like achievements |
"""

MARGIN_BANDS = """
| Margin | Band | Narration Guidance |
|--------|------|-------------------|
| < 0 | Fail | Attempt fails with consequences |
| 0-2 | Mixed | Success with a cost or complication |
| 3-6 | Clean | Straightforward success |
| 7-11 | Strong | Impressive success with style |
| 12+ | Dramatic | Spectacular, memorable achievement |
"""


def create_test_character() -> PC:
    """Create a test character with balanced Domain/Style ratings."""
    return PC(
        id="pc.test",
        name="Test Character",
        current_zone="courtyard",
        hp=HP(current=20, max=20),
        stats=Stats(
            # Domain ratings (number of dice)
            physical=2,  # Trained
            mental=2,  # Trained
            social=2,  # Trained
            insight=3,  # Master
            # Style ratings (0, 4, 6, 8)
            # Experienced character: mostly d6s with ONE d8 signature
            forceful=4,  # d4 (novice)
            subtle=6,  # d6 (practiced)
            precise=4,  # d4 (novice)
            clever=6,  # d6 (practiced)
            resilient=6,  # d6 (practiced)
            graceful=8,  # d8 (SIGNATURE STYLE!)
            chaotic=0,  # 0 (untrained)
        ),
    )


def interpret_action_with_llm(action_description: str) -> dict:
    """
    Use GPT-5-nano to interpret which Domain+Style+DC applies to an action.
    
    Args:
        action_description: Player's description of what they want to do
        
    Returns:
        Dictionary with domain, style, dc, reasoning
    """
    # Long system prompt for automatic prompt caching (≥1024 tokens = 50% cost reduction)
    # Put this FIRST in messages array so it gets cached
    system_prompt = """You are analyzing D&D player actions to determine Domain, Style, and Difficulty Class (DC).

OUTPUT FORMAT: Return ONLY valid JSON with these exact fields:
{
  "domain": "physical|mental|social|insight",
  "style": "forceful|subtle|precise|clever|resilient|graceful|chaotic",
  "dc": 8-30,
  "reasoning": "brief 1-sentence explanation"
}

=== DOMAINS (What Capability) ===
• PHYSICAL: bodily actions - moving, fighting, sneaking, climbing, swimming, breaking things
• MENTAL: thinking - recalling facts, calculating, analyzing, solving puzzles, understanding languages
• SOCIAL: interacting with others - persuading, performing, deceiving, commanding, charming
• INSIGHT: perceiving and sensing - spotting details, reading body language, sensing motives, intuition

=== STYLES (How You Do It) ===
• FORCEFUL: direct, powerful, brutal, overwhelming - bashing down doors, commanding armies, overpowering foes
• SUBTLE: sneaky, hidden, quiet, deceptive - pickpocketing, tailing targets, hiding, misdirection, spreading rumors
• PRECISE: accurate, controlled, surgical, methodical - lockpicking, fine tools, calculations, contracts, proofs
• CLEVER: inventive, lateral thinking, creative - hacking systems, improvising solutions, witty banter, trickery
• RESILIENT: enduring, steady, defensive, persistent - marathons, resisting persuasion, grappling, poker face, deep focus
• GRACEFUL: elegant, flowing, artistic, beautiful - acrobatics, dance, martial arts, charming performances, serene clarity
• CHAOTIC: wild, unpredictable, erratic, random - berserking, improvised weapons, wild guesses, stirring mobs, prophetic hunches

=== ALL DOMAIN × STYLE COMBINATIONS ===

PHYSICAL DOMAIN:
• Physical+Forceful: Brawling, breaking doors, shoving boulders, tackling enemies, smashing through walls
• Physical+Subtle: Stealth, pickpocketing, tailing someone quietly, hiding in shadows, sneaking past guards
• Physical+Precise: Lockpicking, surgery, defusing traps, fine manipulation, precise knife throws
• Physical+Clever: Parkour, jury-rigging equipment, improvising climbing tools, creative use of environment
• Physical+Resilient: Marathon running, enduring pain, grappling holds, damage soaking, prolonged swimming
• Physical+Graceful: Martial arts, acrobatics, dancing, flowing combat techniques, elegant parkour
• Physical+Chaotic: Berserker rage, improvised weapons, wild haymaker punches, unpredictable movements

MENTAL DOMAIN:
• Mental+Forceful: Bulldozing logic, hard rhetoric, forceful arguments, overwhelming with facts
• Mental+Subtle: Deception, setting traps, planting false clues, misdirection, subtle lies
• Mental+Precise: Mathematical calculation, precise recall, detailed analysis, proving theorems, exact translation
• Mental+Clever: Lateral thinking, inventions, hacking systems, solving riddles creatively, witty wordplay
• Mental+Resilient: Deep concentration, long study sessions, resisting mental influence, persistent problem-solving
• Mental+Graceful: Elegant theories, clear exposition, beautiful proofs, articulate explanations
• Mental+Chaotic: Erratic leaps of logic, wild hypotheses, random brainstorming, intuitive guesses

SOCIAL DOMAIN:
• Social+Forceful: Command presence, rallying troops, intimidation, forceful demands, inspiring speeches
• Social+Subtle: Intrigue, spreading rumors, subtle manipulation, reading tells, quiet influence
• Social+Precise: Diplomacy, formal negotiations, contracts, perfect etiquette, measured persuasion
• Social+Clever: Witty banter, improvisational persuasion, clever lies, creative flattery, fast talk
• Social+Resilient: Holding the line in debate, maintaining poker face, resisting interrogation, enduring social pressure
• Social+Graceful: Charming performances, elegant dancing, poised public speaking, graceful flattery
• Social+Chaotic: Stirring up a crowd, starting riots, unpredictable social behavior, wild performances

INSIGHT DOMAIN:
• Insight+Forceful: Force of willpower, zealous conviction, burning determination, intimidating glare
• Insight+Subtle: Reading subtle tells, sensing hidden motives, detecting lies, noticing small details
• Insight+Precise: Careful perception, methodical tracking, detailed observation, systematic searching
• Insight+Clever: Seeing hidden patterns, trickster wisdom, connecting unusual dots, creative interpretation
• Insight+Resilient: Resisting mental sway, fearless observation, unwavering focus, mental fortitude
• Insight+Graceful: Flow state awareness, serene clarity, intuitive grace, effortless perception
• Insight+Chaotic: Gut hunches, prophetic guesses, wild intuition, random lucky insights

=== DIFFICULTY CLASSES (DC) ===
• DC 8 = Easy: Routine everyday tasks, minimal risk or skill needed
• DC 10 = Routine: Standard professional work, what a trained person does regularly
• DC 12 = Tricky: Requires real skill and focus, not guaranteed even for professionals
• DC 15 = Hard: Challenging even for experts, significant risk of failure
• DC 18 = Expert: Top-tier professional capability required, difficult for masters
• DC 20 = Heroic: Extraordinary feats that push human limits
• DC 25 = Epic: Legendary accomplishments, nearly impossible
• DC 30 = Mythic: God-like achievements, defying mortal capabilities

=== EXAMPLES ===
{"domain":"physical","style":"forceful","dc":12,"reasoning":"Shoving a heavy boulder uses direct physical strength"}
{"domain":"physical","style":"subtle","dc":15,"reasoning":"Sneaking past an alert guard requires quiet movement"}
{"domain":"physical","style":"precise","dc":18,"reasoning":"Picking a complex lock needs fine motor control"}
{"domain":"physical","style":"graceful","dc":20,"reasoning":"Performing a triple backflip requires expert acrobatics"}
{"domain":"mental","style":"clever","dc":15,"reasoning":"Inventing a makeshift trap uses creative problem-solving"}
{"domain":"mental","style":"precise","dc":12,"reasoning":"Recalling exact historical dates requires detailed memory"}
{"domain":"social","style":"forceful","dc":15,"reasoning":"Inspiring troops before battle uses commanding presence"}
{"domain":"social","style":"subtle","dc":18,"reasoning":"Manipulating a noble without detection requires finesse"}
{"domain":"social","style":"clever","dc":12,"reasoning":"Fast-talking past a guard uses quick wit"}
{"domain":"insight","style":"subtle","dc":20,"reasoning":"Detecting a master spy's lies requires exceptional perception"}
{"domain":"insight","style":"forceful","dc":15,"reasoning":"Intimidating with a piercing stare uses force of will"}

Analyze the player's action and respond with ONLY valid JSON matching the format above."""

    try:
        # Use Responses API - system prompt at beginning will be auto-cached (50% cost reduction)
        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "developer", "content": system_prompt},  # This gets cached!
                {"role": "user", "content": action_description}
            ],
            reasoning={"effort": "low"},  # Low reasoning for better quality
            text={"format": {"type": "json_object"}},
            max_output_tokens=1000  # Increased from 200 to 1000
        )
        
        # Extract text from Responses API output
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore
        
        # Log cache usage for monitoring
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            input_tokens = usage.input_tokens
            cached_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0) if hasattr(usage, "input_tokens_details") else 0
            if cached_tokens > 0:
                cache_savings = (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                print(f"💰 Cache hit! {cached_tokens}/{input_tokens} tokens cached ({cache_savings:.0f}% saved)")
        
        if not output_text or output_text.strip() == "":
            raise ValueError("LLM returned empty content")
        
        result = json.loads(output_text)
        
        # Validate required fields
        if not all(k in result for k in ["domain", "style", "dc"]):
            raise ValueError("Missing required fields in LLM response")
        
        # Normalize to lowercase
        result["domain"] = result["domain"].lower()
        result["style"] = result["style"].lower()
        
        return result
        
    except Exception as e:
        print(f"⚠️  LLM interpretation failed: {e}")
        print("Using fallback: Physical + Forceful, DC 12")
        return {
            "domain": "physical",
            "style": "forceful",
            "dc": 12,
            "reasoning": "Fallback due to LLM error"
        }


def execute_roll(character: PC, domain: str, style: str, dc: int, seed: Optional[int] = None) -> dict:
    """
    Execute a d20 + Domain + Style roll.
    
    Args:
        character: PC with stats
        domain: Domain name (physical/mental/social/insight)
        style: Style name (forceful/subtle/precise/clever/resilient/graceful/chaotic)
        dc: Difficulty Class
        seed: Random seed for deterministic rolling
        
    Returns:
        Dictionary with roll results
    """
    if seed is not None:
        random.seed(seed)
    
    # Get Domain rating (number of dice)
    domain_rating = getattr(character.stats, domain, 2)
    
    # Get Style rating (die size: 0, 4, 6, 8)
    style_die_size = getattr(character.stats, style, 0)
    
    # Roll dice (handle die size = 0)
    d20 = random.randint(1, 20)
    if style_die_size == 0:
        domain_dice = []  # No dice if untrained
        domain_sum = 0
    else:
        domain_dice = [random.randint(1, style_die_size) for _ in range(domain_rating)]
        domain_sum = sum(domain_dice)
    total = d20 + domain_sum
    
    # Calculate margin and outcome band
    margin = total - dc
    if margin < 0:
        outcome_band = "Fail"
    elif margin <= 2:
        outcome_band = "Mixed"
    elif margin <= 6:
        outcome_band = "Clean"
    elif margin <= 11:
        outcome_band = "Strong"
    else:
        outcome_band = "Dramatic"
    
    return {
        "d20": d20,
        "domain_dice": domain_dice,
        "domain_sum": domain_sum,
        "total": total,
        "dc": dc,
        "margin": margin,
        "outcome_band": outcome_band,
        "domain": domain.capitalize(),
        "domain_rating": domain_rating,
        "style": style.capitalize(),
        "style_die_size": style_die_size,
    }


def display_character_sheet(character: PC):
    """Display character's Domain and Style ratings."""
    print("\n" + "="*60)
    print(f"  CHARACTER: {character.name}")
    print("="*60)
    
    print("\n📊 DOMAIN RATINGS (Number of Dice):")
    print(f"  Physical:  {character.stats.physical} dice")
    print(f"  Mental:    {character.stats.mental} dice")
    print(f"  Social:    {character.stats.social} dice")
    print(f"  Insight:   {character.stats.insight} dice")
    
    print("\n🎲 STYLE RATINGS (Die Size):")
    def format_die(size):
        return f"d{size}" if size > 0 else "  0 (untrained)"
    print(f"  Forceful:   {format_die(character.stats.forceful)}")
    print(f"  Subtle:     {format_die(character.stats.subtle)}")
    print(f"  Precise:    {format_die(character.stats.precise)}")
    print(f"  Clever:     {format_die(character.stats.clever)}")
    print(f"  Resilient:  {format_die(character.stats.resilient)}")
    print(f"  Graceful:   {format_die(character.stats.graceful)}")
    print(f"  Chaotic:    {format_die(character.stats.chaotic)}")
    
    print("="*60 + "\n")


def display_roll_results(results: dict, interpretation: dict):
    """Display roll results in a formatted way."""
    print("\n" + "="*60)
    print("  🎯 ROLL RESULTS")
    print("="*60)
    
    print(f"\n📝 Interpretation:")
    print(f"  Domain: {interpretation['domain'].capitalize()}")
    print(f"  Style: {interpretation['style'].capitalize()}")
    print(f"  DC: {interpretation['dc']} ({get_dc_description(interpretation['dc'])})")
    print(f"  Reasoning: {interpretation.get('reasoning', 'N/A')}")
    
    print(f"\n🎲 Roll Breakdown:")
    print(f"  d20: {results['d20']}")
    print(f"  {results['domain']} {results['domain_rating']} × d{results['style_die_size']}: {results['domain_dice']} (sum: {results['domain_sum']})")
    print(f"  Total: {results['total']}")
    
    print(f"\n📊 Outcome:")
    print(f"  DC: {results['dc']}")
    print(f"  Margin: {results['margin']:+d}")
    print(f"  Result: {results['outcome_band']}")
    print(f"  {get_outcome_description(results['outcome_band'])}")
    
    print("="*60 + "\n")


def get_dc_description(dc: int) -> str:
    """Get difficulty description for a DC."""
    if dc <= 8:
        return "Easy"
    elif dc <= 10:
        return "Routine"
    elif dc <= 12:
        return "Tricky"
    elif dc <= 15:
        return "Hard"
    elif dc <= 18:
        return "Expert"
    elif dc <= 20:
        return "Heroic"
    elif dc <= 25:
        return "Epic"
    else:
        return "Mythic"


def get_outcome_description(band: str) -> str:
    """Get narrative description for an outcome band."""
    descriptions = {
        "Fail": "❌ Attempt fails with consequences",
        "Mixed": "⚠️  Success with a cost or complication",
        "Clean": "✅ Straightforward success",
        "Strong": "💪 Impressive success with style",
        "Dramatic": "🌟 Spectacular, memorable achievement"
    }
    return descriptions.get(band, "Unknown outcome")


def main():
    """Main interactive loop."""
    print("\n" + "="*60)
    print("  d20 + DOMAIN + STYLE DICE SYSTEM TEST")
    print("="*60)
    
    # Create test character
    character = create_test_character()
    display_character_sheet(character)
    
    print("Enter an action to test the dice system.")
    print("Examples:")
    print("  - I shove a big boulder off a cliff")
    print("  - I sneak past the sleeping guard")
    print("  - I convince the merchant to trust me")
    print("  - I spot the hidden trap")
    print("\nType 'quit' to exit.\n")
    
    while True:
        # Get action from user
        action = input("🎭 What do you do? ").strip()
        
        if not action:
            continue
        
        if action.lower() in ["quit", "exit", "q"]:
            print("\n👋 Exiting dice tester. Goodbye!\n")
            break
        
        print(f"\n🤔 Interpreting action with GPT-5-nano...")
        
        # Interpret with LLM
        interpretation = interpret_action_with_llm(action)
        
        # Execute roll
        results = execute_roll(
            character,
            interpretation["domain"],
            interpretation["style"],
            interpretation["dc"]
        )
        
        # Display results
        display_roll_results(results, interpretation)


if __name__ == "__main__":
    main()
