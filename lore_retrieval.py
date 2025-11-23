"""
Lore Retrieval System

Retrieves relevant lore entries and narrations based on player input.
Uses tag/keyword matching to find the most relevant context.
"""

import json
import re
from typing import List, Dict, Any, Set, Optional
from openai import OpenAI
import config
from lore_extractor import load_lore, load_narration_history
from cache_logger import log_cache_stats

client = OpenAI(api_key=config.OPENAI_API_KEY)


def extract_search_keywords(player_input: str, last_narration: str = "") -> List[str]:
    """
    Use GPT-5-nano to extract search keywords/tags from player input and context.

    Args:
        player_input: What the player said
        last_narration: Previous DM narration for context

    Returns:
        List of keywords/tags to search for
    """
    system_prompt = """You are extracting search keywords from D&D player input.

OUTPUT FORMAT: Return ONLY valid JSON:
{
  "keywords": ["keyword1", "keyword2", "keyword3", ...]
}

=== WHAT TO EXTRACT ===

Extract keywords that would help find relevant lore:
• **Proper names**: NPCs, locations, factions, items mentioned
• **Topics**: What the player is asking about or interacting with
• **Context clues**: Implied subjects from the narration

**Rules:**
• Single words only (lowercase)
• 5-10 keywords max
• Focus on nouns (people, places, things)
• Include synonyms if helpful (e.g., "merchant" + "trader")
• Avoid generic words ("the", "a", "do", "is")

=== EXAMPLES ===

Player: "I ask the merchant about the Rusty Nail tavern."
Last narration: "Gareth, the halfling merchant, eyes you suspiciously."

Output:
{
  "keywords": ["merchant", "gareth", "halfling", "tavern", "rusty", "nail", "trader", "shop"]
}

Player: "I search for hidden passages."
Last narration: "You're in a crumbling stone chamber beneath the old temple."

Output:
{
  "keywords": ["hidden", "passage", "secret", "chamber", "temple", "stone", "underground", "dungeon"]
}

Player: "What do I know about the Silver Covenant?"
Last narration: ""

Output:
{
  "keywords": ["silver", "covenant", "faction", "organization", "guild", "group"]
}

Analyze the input and return ONLY valid JSON with keywords."""

    try:
        user_message = f"Player input: {player_input}"
        if last_narration:
            user_message += f"\nLast narration: {last_narration}"

        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            reasoning={"effort": "low"},
            text={"format": {"type": "json_object"}},
            max_output_tokens=4000,  # Quadrupled from 1000
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
        log_cache_stats("Lore_Retrieval", cached_tokens, total_tokens, "gpt-5-nano")

        if cached_tokens > 0:
            print(f"💾 [LORE RETRIEVAL] CACHE HIT: {cached_tokens} tokens cached")  # type: ignore

        # Extract text
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore

        if not output_text or output_text.strip() == "":
            return []

        result = json.loads(output_text)
        keywords = result.get("keywords", [])

        # Normalize to lowercase
        keywords = [k.lower() for k in keywords if isinstance(k, str)]

        return keywords

    except Exception as e:
        print(f"⚠️  Keyword extraction failed: {e}")
        import traceback

        traceback.print_exc()
        # Fallback: simple word extraction
        words = re.findall(r"\b\w{3,}\b", player_input.lower())
        print(f"   Using fallback keywords: {words[:10]}")
        return words[:10]


def score_lore_entry(entry: Dict[str, Any], keywords: Set[str]) -> int:
    """
    Score a lore entry based on keyword/tag overlap.

    Args:
        entry: Lore entry with tags, name, summary, full_text
        keywords: Set of search keywords

    Returns:
        Score (higher = more relevant)
    """
    score = 0

    # Tags are most important (5 points each)
    tags = entry.get("tags", [])
    for tag in tags:
        if tag.lower() in keywords:
            score += 5

    # Name matches (3 points)
    name_words = set(re.findall(r"\b\w+\b", entry.get("name", "").lower()))
    score += len(name_words & keywords) * 3

    # Summary matches (1 point each)
    summary_words = set(re.findall(r"\b\w+\b", entry.get("summary", "").lower()))
    score += len(summary_words & keywords) * 1

    return score


def score_narration(narration: Dict[str, Any], keywords: Set[str]) -> int:
    """
    Score a narration entry based on keyword overlap.

    Args:
        narration: Narration entry with player, dm text
        keywords: Set of search keywords

    Returns:
        Score (higher = more relevant)
    """
    score = 0

    # Check player input (2 points each)
    player_words = set(re.findall(r"\b\w+\b", narration.get("player", "").lower()))
    score += len(player_words & keywords) * 2

    # Check DM narration (1 point each)
    dm_words = set(re.findall(r"\b\w+\b", narration.get("dm", "").lower()))
    score += len(dm_words & keywords) * 1

    return score


def retrieve_relevant_context(
    player_input: str,
    last_narration: str = "",
    top_lore: int = 4,
    top_narrations: int = 1,
    exclude_turn_numbers: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Retrieve the most relevant lore and narrations for the current player input.

    Args:
        player_input: What the player said
        last_narration: Previous DM narration for context
        top_lore: Number of lore entries to retrieve (default 4)
        top_narrations: Number of past narrations to retrieve (default 1)
        exclude_turn_numbers: List of turn numbers to exclude (already in conversation window)

    Returns:
        {
            "keywords": [...],
            "lore_entries": [...],
            "narrations": [...]
        }
    """
    if exclude_turn_numbers is None:
        exclude_turn_numbers = []

    # Step 1: Extract keywords
    print(f"🔍 Extracting keywords...")
    keywords = extract_search_keywords(player_input, last_narration)
    keywords_set = set(keywords)
    print(f"   Keywords: {', '.join(keywords)}")

    # Step 2: Load and score lore entries
    lore_data = load_lore()
    lore_entries = lore_data.get("entries", [])

    scored_lore = []
    for entry in lore_entries:
        score = score_lore_entry(entry, keywords_set)
        if score > 0:  # Only include if relevant
            scored_lore.append((score, entry))

    # Sort by score descending and take top N
    scored_lore.sort(reverse=True, key=lambda x: x[0])
    top_lore_entries = [entry for score, entry in scored_lore[:top_lore]]

    print(f"   Found {len(top_lore_entries)} relevant lore entries:")
    for entry in top_lore_entries:
        print(f"   - {entry['type'].upper()}: {entry['name']}")

    # Step 3: Load and score narrations, excluding turns already in conversation window
    narrations = load_narration_history()

    # Filter out excluded turns BEFORE scoring
    available_narrations = [
        n for n in narrations if n.get("turn") not in exclude_turn_numbers
    ]

    if exclude_turn_numbers:
        excluded_count = len(narrations) - len(available_narrations)
        if excluded_count > 0:
            print(
                f"   Excluding {excluded_count} turn(s) already in conversation window: {sorted(exclude_turn_numbers)}"
            )

    scored_narrations = []
    for narration in available_narrations:
        score = score_narration(narration, keywords_set)
        if score > 0:  # Only include if relevant
            scored_narrations.append((score, narration))

    # Sort by score descending and take top N
    scored_narrations.sort(reverse=True, key=lambda x: x[0])
    top_narration_entries = [
        narration for score, narration in scored_narrations[:top_narrations]
    ]

    if top_narration_entries:
        print(f"   Found {len(top_narration_entries)} relevant past narrations:")
        for narration in top_narration_entries:
            turn = narration.get("turn", "?")
            snippet = narration.get("dm", "")[:60] + "..."
            print(f"   - Turn {turn}: {snippet}")

    return {
        "keywords": keywords,
        "lore_entries": top_lore_entries,
        "narrations": top_narration_entries,
    }


def format_context_for_prompt(retrieved_context: Dict[str, Any]) -> str:
    """
    Format retrieved context into a string for the DM prompt.

    Args:
        retrieved_context: Output from retrieve_relevant_context()

    Returns:
        Formatted context string
    """
    output = ""

    # Lore entries
    lore_entries = retrieved_context.get("lore_entries", [])
    if lore_entries:
        output += "=== RELEVANT LORE ===\n\n"
        for entry in lore_entries:
            output += f"**{entry['type'].upper()}: {entry['name']}**\n"
            output += f"{entry['full_text']}\n"
            output += f"(Tags: {', '.join(entry.get('tags', []))})\n\n"

    # Past narrations
    narrations = retrieved_context.get("narrations", [])
    if narrations:
        output += "=== RELEVANT PAST EVENTS ===\n\n"
        for narration in narrations:
            turn = narration.get("turn", "?")
            player = narration.get("player", "")
            dm = narration.get("dm", "")
            output += f"**Turn {turn}**\n"
            output += f"Player: {player}\n"
            output += f"DM: {dm}\n\n"

    return output


if __name__ == "__main__":
    # Test retrieval
    test_player_input = "I ask the merchant about the Rusty Nail tavern."
    test_last_narration = "Gareth, the portly halfling merchant, eyes you suspiciously."

    context = retrieve_relevant_context(test_player_input, test_last_narration)

    print("\n" + "=" * 70)
    print("RETRIEVED CONTEXT")
    print("=" * 70)
    print(format_context_for_prompt(context))
