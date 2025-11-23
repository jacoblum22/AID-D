"""
Combined Roll Decision + Action Interpretation System

This combines two previously separate LLM calls:
1. Decide: Roll or Narrate?
2. If Roll: What Domain/Style/DC?

Single LLM call with combined output for efficiency and cost.
"""

import json
from openai import OpenAI
from typing import Optional
import config
from cache_logger import log_cache_stats

client = OpenAI(api_key=config.OPENAI_API_KEY)


def analyze_player_action(player_input: str, context: str = "") -> dict:
    """
    Analyze player input to decide if roll is needed AND suggest Domain/Style/DC.

    Can handle multiple rolls in a single action (e.g., asking several questions at once).

    Args:
        player_input: What the player said/typed
        context: Optional scene context

    Returns:
        {
            "decision": "roll"|"narrate",
            "reasoning": "why this decision",
            "confidence": "high"|"medium"|"low",
            "roll_details": [  # List of rolls if decision="roll"
                {
                    "domain": "physical"|"mental"|"social"|"insight",
                    "style": "forceful"|"subtle"|"precise"|"clever"|"resilient"|"graceful"|"chaotic",
                    "dc": 8-30,
                    "action_description": "brief description of the action"
                },
                ... (more rolls if multiple questions/actions)
            ]
        }
    """
    # Large cached system prompt combining both tasks
    system_prompt = """You are analyzing D&D player actions to determine:
1. Does this require a ROLL or just NARRATION?
2. If ROLL: What Domain, Style, and DC? (Can be multiple rolls!)

OUTPUT FORMAT: Return ONLY valid JSON:
{
  "decision": "roll|narrate",
  "reasoning": "brief 1-sentence explanation",
  "confidence": "high|medium|low",
  "roll_details": [
    {
      "domain": "physical|mental|social|insight",
      "style": "forceful|subtle|precise|clever|resilient|graceful|chaotic",
      "dc": 8-30,
      "action_description": "brief description"
    }
    ... (more objects if multiple rolls needed)
  ]
}

Note: `roll_details` is null if decision="narrate", or an array of 1+ rolls if decision="roll"

**MULTIPLE ROLLS:**
If player asks multiple questions or takes multiple actions requiring different skills, return multiple roll objects.
Example: "Do I know why the boy gave this to me? Why won't the crier look at me? What does this symbol mean?"
→ Returns 3 rolls: Insight+Subtle (read boy's intent), Insight+Subtle (read crier's behavior), Mental+Precise (recall symbol lore)

=== PART 1: ROLL VS. NARRATE DECISION ===

**THE GOLDEN RULE: ONLY ROLL WHEN FAILURE IS INTERESTING**
• Ask yourself: "Would failure create drama, tension, or meaningful consequences?"
• If failure would just be boring or frustrating → NARRATE
• If failure creates interesting problems or story opportunities → ROLL
• Examples:
  - Opening unlocked door: Failure = nothing happens. Boring → NARRATE
  - Climbing crumbling tower: Failure = fall, injury, alerting guards. Interesting → ROLL
  - Talking to ally: Failure = awkward silence? Boring → NARRATE
  - Persuading enemy: Failure = combat, chase, betrayal. Interesting → ROLL

**CRITICAL: SPEECH VS. ACTIONS**
• **Text in quotes ("...") is SPEECH, not an action requiring a roll**
• Examples:
  - "I ask 'What's your name?'" → NARRATE (just asking a question)
  - "I say 'We should leave now'" → NARRATE (stating an opinion)
  - "I tell him 'I know what you did'" → NARRATE (delivering information)
  - "I demand 'Give me the key or else!'" → Maybe ROLL (intimidation with stakes)
• **Only roll if the speech is attempting to manipulate/persuade/deceive/intimidate**

**ROLL when:**
• Character taking uncertain action with real stakes
• Outcome not guaranteed
• Failure would create interesting consequences or complications
• Testing character knowledge of obscure/specialized information

**NARRATE when:**
• **Failure would be boring, frustrating, or just halt progress**
• **Player asking meta/rules/clarification questions**
• **Player confused about situation and asking for info**
• **Player questioning NPC motivations or plot logic**
• Trivial or automatic actions
• Common knowledge or character background guarantees it
• Checking inventory/possessions ("Do I have X?")
• Past events ("Did I previously...")
• **Normal conversation with allies/friends**
• **Simple speech/questions in quotes ("")**

**KEY DISTINCTIONS:**
1. Inventory/Possessions ("Do I have...") → NARRATE (check inventory)
2. Common knowledge → NARRATE (just tell them)
3. Obscure knowledge → ROLL (Mental check, use CONTEXT)
4. Past actions ("Did I previously...") → NARRATE (no retroactive rolls)
5. **Confusion/Clarification ("I'm confused", "Why are they...", "Did they hear...") → NARRATE (out-of-game question)**
6. **Story logic questions ("Shouldn't they know...", "Wouldn't they have heard...") → NARRATE (player seeking clarification)**
7. **TRIVIAL TASKS WITH OBVIOUS OUTCOMES → NARRATE** (unlocking with a key, opening an unlocked door, picking up an object, turning a knob, etc.)
8. **TALKING TO ALLIES/FRIENDS → NARRATE** (normal conversation with friendly NPCs doesn't require rolls - only roll if trying to persuade/deceive/manipulate)

**SOCIAL INTERACTION CLARITY:**
• "I ask my ally what they think" → NARRATE (normal conversation)
• "I tell my friend the plan" → NARRATE (sharing information with allies)
• "I talk to the guard" → NARRATE (basic interaction)
• "I chat with the shopkeeper" → NARRATE (normal conversation)
• "I try to convince the guard to let me pass" → ROLL (persuasion with stakes)
• "I lie to the merchant about the price" → ROLL (deception)
• "I intimidate the bandit into fleeing" → ROLL (social manipulation)
**KEY PRINCIPLE:** Normal conversation = NARRATE. Trying to change someone's mind/behavior = ROLL.

**DECISION CRITERIA:**

**1. PLAYER VS. CHARACTER**
• "What's the DC?" → NARRATE (player meta question)
• "What's the name of this city?" → NARRATE (player asking DM for info)
• "Do I have a map?" → NARRATE (inventory check)
• "Do I know [COMMON thing]?" → NARRATE (if everyone knows)
• "Do I know [OBSCURE thing]?" → ROLL (if specialized/uncertain)
• "I climb the wall" → Maybe ROLL (if uncertain + stakes)
• "I unlock the door with the key" → NARRATE (trivial task, obvious outcome)
• "I turn the iron key to unlock the chained doors" → NARRATE (has key, trivial task)

**2. UNCERTAINTY + STAKES** (BOTH must exist)
• Crossing small stream → NARRATE (no uncertainty, no stakes)
• Sneaking past guards → ROLL (uncertain + stakes)
• Picking up a rock → NARRATE (no uncertainty)
• Unlocking with a key → NARRATE (no uncertainty - has the key!)
• Scaling crumbling tower → ROLL (uncertain + stakes)

**3. PASSIVE OBSERVATION VS. ACTIVE PERCEPTION** (VERY IMPORTANT)
• "Do people react?" → NARRATE (passive observation of obvious behavior)
• "Does anyone seem afraid?" → NARRATE (surface-level emotional reading)
• "What do I see?" → NARRATE (general environmental description)
• "Are there guards?" → NARRATE (obvious presence)
• "Do I notice HIDDEN reactions?" → ROLL (active perception of concealed emotions)
• "Can I spot someone trying to hide their fear?" → ROLL (reading subtle tells)
• "Do I notice anything unusual about their behavior?" → ROLL (detailed analysis)
• "Is anyone secretly watching me?" → ROLL (spotting hidden observers)
**KEY DISTINCTION:** Surface-level, obvious reactions and observations = NARRATE. Detecting hidden, subtle, or concealed information = ROLL.

**4. FICTIONAL POSITIONING**
• "I check under the rug" → NARRATE (if it's there, they find it)
• "I search for hidden compartments" → ROLL (uncertain discovery)
• "I open the unlocked door" → NARRATE (guaranteed)
• "I leap across the chasm" → ROLL (risky)

**5. ACTION VERBS**

**Suggest ROLL for:**
• Attempt: try, attempt, strive
• Perception: search, look for, investigate, notice, spot
• Physical: climb, jump, sneak, dodge, swim, grapple
• Social: persuade, convince, deceive, intimidate, charm, perform
• Combat: attack, defend, parry, feint
• Recall/Knowledge: "Do I know...", "Do I remember...", "Do I recognize..." (if OBSCURE)

**Suggest NARRATE for:**
• Meta questions: "What's...", "How does...", "Can you tell me..."
• Trivial: walk, pick up (simple objects), open (unlocked doors)
• Clarifications: "Is there...", "What does X look like..."
• Inventory: "Do I have...", "Am I carrying...", "Did I bring..."
• Past events: "Did I previously..."

**5. CONSEQUENCE VS. FLAVOR**
• "I balance my dagger to impress" → NARRATE (no stakes)
• "I juggle torches for tips" → ROLL (stakes: embarrassment/money)

=== PART 2: IF ROLL, DETERMINE DOMAIN/STYLE/DC ===

**DOMAINS** (what capability):
• PHYSICAL: bodily actions - moving, fighting, sneaking, climbing, swimming
• MENTAL: thinking - recalling, calculating, analyzing, solving puzzles
• SOCIAL: interacting - persuading, performing, deceiving, commanding
• INSIGHT: perceiving - spotting details, sensing motives, reading situations

**CRITICAL: Domain is determined by the ULTIMATE TASK, not the preparation or approach.**
- Planning a clever escape WHILE running → Physical+Clever (task is running)
- Brute-force logic to solve puzzle → Mental+Forceful (task is puzzle-solving)
- Gracefully negotiating a contract → Social+Graceful (task is negotiation)
- Reading someone's tells with gut instinct → Insight+Chaotic (task is perception)

**Domain Selection Rule:**
1. What is the character DOING in the fiction? (the actual task)
2. Is it bodily (Physical), thinking (Mental), interacting (Social), or perceiving (Insight)?
3. The METHOD/APPROACH is the Style, NOT the Domain

**STYLES** (how you do it):
• FORCEFUL: direct, powerful, brutal - bashing, commanding, overpowering
• SUBTLE: sneaky, hidden, quiet - pickpocketing, tailing, stealth, misdirection
• PRECISE: accurate, controlled, surgical - lockpicks, fine tools, calculation
• CLEVER: inventive, lateral thinking - hacks, improv, trickery, wit
• RESILIENT: enduring, steady, defensive - marathons, resisting, grappling
• GRACEFUL: elegant, flowing, artistic - acrobatics, dance, charm, poise
• CHAOTIC: wild, unpredictable, erratic - berserking, improvised weapons, gut hunches

**COMMON COMBINATIONS:**
• Physical+Forceful: brawling, breaking, shoving, brute force
• Physical+Subtle: stealth, pickpocketing, tailing, sneaking
• Physical+Precise: surgery, fine tools, lockpicks, precise manipulation
• Physical+Clever: parkour, jury-rigging gear, improvised tricks
• Physical+Resilient: marathon running, damage soak, grappling endurance
• Physical+Graceful: martial arts, acrobatics, dance, flowing combat
• Physical+Chaotic: berserk rush, improvised weapons, wild attacks
• Mental+Forceful: bulldozing logic, hard rhetoric, forceful arguments
• Mental+Subtle: deception, traps, misdirection, hidden motives
• Mental+Precise: calculation, recall, proofs, exact reasoning
• Mental+Clever: lateral thinking, hacks, inventions, creative solutions
• Mental+Resilient: deep focus, long study, mental fortitude
• Mental+Graceful: elegant theory, clear exposition, beautiful logic
• Mental+Chaotic: erratic leaps, wild hypotheses, inspired guesses
• Social+Forceful: commanding presence, rallying troops, intimidation
• Social+Subtle: intrigue, rumors, manipulation, secrets
• Social+Precise: diplomacy, contracts, etiquette, formal negotiations
• Social+Clever: banter, improv persuasion, witty arguments
• Social+Resilient: holding the line, poker face, emotional endurance
• Social+Graceful: performance, charm, poise, artistic expression
• Social+Chaotic: stirring crowds, starting riots, unpredictable speeches
• Insight+Forceful: willpower, conviction, zeal, forcing truth
• Insight+Subtle: reading tells, sensing motives, detecting lies
• Insight+Precise: perception, tracking, awareness, noticing details
• Insight+Clever: seeing patterns, trickster wisdom, connections
• Insight+Resilient: resisting influence, fearlessness, steadfast
• Insight+Graceful: flow state, serene clarity, zen awareness
• Insight+Chaotic: gut hunches, prophetic guesses, wild intuition

**FULL DOMAIN × STYLE MATRIX:**

| Domain / Style | Forceful | Subtle | Precise | Clever | Resilient | Graceful | Chaotic |
|----------------|----------|--------|---------|--------|-----------|----------|---------|
| **Physical** | Brawling, breaking, shoving | Stealth, pickpocketing, tailing | Surgery, fine tools, lockpicks | Parkour, jury-rigging gear | Marathon, damage soak, grapples | Martial arts, acrobatics, dance | Berserk rush, improvised weapons |
| **Mental** | Bulldozing logic, hard rhetoric | Deception, traps, misdirection | Calculation, recall, proofs | Lateral ideas, hacks, inventions | Deep focus, long study | Elegant theory, clear exposition | Erratic leaps, wild hypotheses |
| **Social** | Command presence, rallying | Intrigue, rumors, manipulation | Diplomacy, contracts, etiquette | Banter, improv persuasion | Hold the line, poker face | Performance, charm, poise | Stir the crowd, start a riot |
| **Insight** | Willpower, conviction, zeal | Read tells, sense motives | Perception, tracking, awareness | See patterns, trickster wisdom | Resist sway, fearlessness | Flow state, serene clarity | Gut hunch, prophetic guess |

**DIFFICULTY (DC):**
• DC 8 = Easy (routine tasks)
• DC 10 = Routine (standard professional work)
• DC 12 = Tricky (requires skill and focus)
• DC 15 = Hard (challenging even for experts)
• DC 18 = Expert (top-tier capability needed)
• DC 20 = Heroic (extraordinary feats)
• DC 25 = Epic (legendary)
• DC 30 = Mythic (god-like)

=== EXAMPLES ===

Input: "What's the name of the tavern?"
{
  "decision": "narrate",
  "reasoning": "Player asking DM for world information directly",
  "confidence": "high",
  "roll_details": null
}

Input: "Do I have a map?"
{
  "decision": "narrate",
  "reasoning": "Checking inventory/possessions - no roll needed",
  "confidence": "high",
  "roll_details": null
}

Input: "Do I know the name of this ancient city?"
Context: "little-known, abandoned city"
{
  "decision": "roll",
  "reasoning": "Testing character's knowledge of obscure historical information",
  "confidence": "high",
  "roll_details": {
    "domain": "mental",
    "style": "precise",
    "dc": 18,
    "action_description": "recalling obscure historical knowledge"
  }
}

Input: "I sneak past the sleeping guards."
{
  "decision": "roll",
  "reasoning": "Character attempting stealth with failure consequences",
  "confidence": "high",
  "roll_details": {
    "domain": "physical",
    "style": "subtle",
    "dc": 15,
    "action_description": "sneaking quietly past guards"
  }
}

Input: "I convince the merchant to lower the price."
{
  "decision": "roll",
  "reasoning": "Social persuasion with uncertain outcome and stakes",
  "confidence": "high",
  "roll_details": [
    {
      "domain": "social",
      "style": "clever",
      "dc": 15,
      "action_description": "haggling with creative arguments"
    }
  ]
}

Input: "I attack the bandit with my sword."
{
  "decision": "roll",
  "reasoning": "Combat action with clear uncertainty and stakes",
  "confidence": "high",
  "roll_details": [
    {
      "domain": "physical",
      "style": "forceful",
      "dc": 12,
      "action_description": "attacking with sword"
    }
  ]
}

Input: "Do people react when the bell rings? Does anyone seem afraid?"
{
  "decision": "narrate",
  "reasoning": "Passive observation of obvious, surface-level reactions - no roll needed",
  "confidence": "high",
  "roll_details": null
}

Input: "Can I tell if anyone is secretly planning something or hiding their true feelings?"
{
  "decision": "roll",
  "reasoning": "Active perception to detect hidden emotions and concealed intentions",
  "confidence": "high",
  "roll_details": [
    {
      "domain": "insight",
      "style": "subtle",
      "dc": 15,
      "action_description": "reading subtle tells and hidden motives"
    }
  ]
}

Input: "Do I know why the boy gave me this package? Why won't the crier look at me? What does the broken sun symbol mean?"
{
  "decision": "roll",
  "reasoning": "Three separate knowledge/perception questions requiring different skills",
  "confidence": "high",
  "roll_details": [
    {
      "domain": "insight",
      "style": "subtle",
      "dc": 14,
      "action_description": "reading the boy's intent and motives"
    },
    {
      "domain": "insight",
      "style": "subtle",
      "dc": 12,
      "action_description": "noticing why the crier avoids eye contact"
    },
    {
      "domain": "mental",
      "style": "precise",
      "dc": 16,
      "action_description": "recalling lore about the broken sun symbol"
    }
  ]
}

Input: "I'm confused. The captain told me to intervene, so I was just doing what I was told. Did these guards not hear that? Why are they acting against me when I was told to help?"
{
  "decision": "narrate",
  "reasoning": "Player is asking out-of-game clarification question about plot logic and NPC behavior - not taking an action",
  "confidence": "high",
  "roll_details": null
}

Input: "Wait, shouldn't they have heard the captain's orders? I'm confused about why they're stopping me."
{
  "decision": "narrate",
  "reasoning": "Meta question seeking clarification about the fictional situation",
  "confidence": "high",
  "roll_details": null
}

Input: "What's this town called?"
{
  "decision": "narrate",
  "reasoning": "Simple information request - player asking for world detail",
  "confidence": "high",
  "roll_details": null
}

Analyze the player input and respond ONLY with valid JSON."""

    try:
        # Build input with optional context - context FIRST since player responds to it
        if context:
            user_message = f"Scene context: {context}\nPlayer input: {player_input}"
        else:
            user_message = f"Player input: {player_input}"

        print(f"\n{'='*70}")
        print(f"🔍 ROLL ANALYZER DEBUG")
        print(f"{'='*70}")
        print(f"\n[SYSTEM PROMPT (truncated)]")
        print(f"{system_prompt[:500]}...")
        print(f"\n[USER MESSAGE]")
        print(user_message)

        # Use Responses API with low reasoning
        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {
                    "role": "developer",
                    "content": system_prompt,
                },  # Auto-cached (~3000 tokens)
                {"role": "user", "content": user_message},
            ],
            reasoning={"effort": "low"},
            text={"format": {"type": "json_object"}},
            max_output_tokens=1000,
        )

        # Log cache usage (always log, even if 0%)
        cached_tokens = 0
        total_tokens = 0
        if hasattr(response, "usage"):
            usage = response.usage  # type: ignore
            total_tokens = usage.input_tokens  # type: ignore
            if hasattr(usage, "input_tokens_details"):
                details = usage.input_tokens_details  # type: ignore
                if hasattr(details, "cached_tokens"):  # type: ignore
                    cached_tokens = details.cached_tokens or 0  # type: ignore

        # Always log to track all calls
        log_cache_stats("Roll_Analyzer", cached_tokens, total_tokens, "gpt-5-nano")

        if cached_tokens > 0:
            print(f"\n💾 [ROLL ANALYZER] CACHE HIT: {cached_tokens} tokens cached\n")  # type: ignore

        # Extract text
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore

        print(f"\n[LLM OUTPUT]")
        print(output_text)
        print(f"{'='*70}\n")

        if not output_text or output_text.strip() == "":
            raise ValueError("LLM returned empty content")

        result = json.loads(output_text)

        # Validate
        if "decision" not in result or result["decision"] not in ["roll", "narrate"]:
            raise ValueError("Invalid or missing 'decision' field")

        # Normalize
        result["decision"] = result["decision"].lower()
        if result.get("roll_details"):
            # Handle both list and single dict formats
            if isinstance(result["roll_details"], list):
                for details in result["roll_details"]:
                    details["domain"] = details["domain"].lower()
                    details["style"] = details["style"].lower()
            else:
                # Single dict - convert to list
                result["roll_details"]["domain"] = result["roll_details"][
                    "domain"
                ].lower()
                result["roll_details"]["style"] = result["roll_details"][
                    "style"
                ].lower()
                result["roll_details"] = [result["roll_details"]]  # Wrap in list

        return result

    except Exception as e:
        print(f"⚠️  LLM analysis failed: {e}")
        return {
            "decision": "narrate",
            "reasoning": "Fallback due to LLM error",
            "confidence": "low",
            "roll_details": None,
        }
