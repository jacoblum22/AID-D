"""
Lore Extraction & Storage System

This module extracts lore from DM narration and stores it in world_lore.json.
Uses GPT-5-nano to identify new NPCs, locations, factions, events, items, and world facts.
"""

import json
import os
import sys
from typing import List, Dict, Any, Optional
from openai import OpenAI
import config
from cache_logger import log_cache_stats

# Platform-specific imports for file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

client = OpenAI(api_key=config.OPENAI_API_KEY)

LORE_FILE = "world_lore.json"
NARRATION_FILE = "narration_history.json"
LOCK_FILE = "narration_history.lock"  # Lock file for concurrency protection


def load_lore() -> Dict[str, List[Dict[str, Any]]]:
    """Load existing lore from file."""
    if not os.path.exists(LORE_FILE):
        return {"entries": []}

    try:
        with open(LORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading lore file: {e}")
        return {"entries": []}


def save_lore(lore_data: Dict[str, List[Dict[str, Any]]]):
    """Save lore to file using atomic write to prevent corruption."""
    try:
        # Write to temporary file first
        temp_file = LORE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(lore_data, f, indent=2, ensure_ascii=False)

        # Atomic rename (replaces existing file)
        os.replace(temp_file, LORE_FILE)
    except Exception as e:
        print(f"⚠️  Error saving lore file: {e}")
        # Clean up temp file if it exists
        if os.path.exists(LORE_FILE + ".tmp"):
            os.remove(LORE_FILE + ".tmp")


def load_narration_history() -> List[Dict[str, Any]]:
    """Load narration history from file."""
    if not os.path.exists(NARRATION_FILE):
        return []

    try:
        with open(NARRATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading narration history: {e}")
        return []


def save_narration_history(history: List[Dict[str, Any]]):
    """Save narration history to file using atomic write to prevent corruption."""
    try:
        # Write to temporary file first
        temp_file = NARRATION_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        # Atomic rename (replaces existing file)
        os.replace(temp_file, NARRATION_FILE)
    except Exception as e:
        print(f"⚠️  Error saving narration history: {e}")
        # Clean up temp file if it exists
        if os.path.exists(NARRATION_FILE + ".tmp"):
            os.remove(NARRATION_FILE + ".tmp")


def save_narration(player_input: str, dm_response: str, turn_number: int):
    """
    Save a narration exchange to history with concurrency protection.

    Args:
        player_input: What the player said
        dm_response: DM's narration
        turn_number: Current turn number
    """
    # Use file locking to prevent race conditions
    lock_path = LOCK_FILE
    lock_file = None  # Initialize to None to prevent UnboundLocalError

    try:
        # Create/open lock file
        lock_file = open(lock_path, "w")

        # Acquire exclusive lock (platform-specific)
        if sys.platform == "win32":
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        # Now safely read, modify, and write
        history = load_narration_history()
        entry = {"turn": turn_number, "player": player_input, "dm": dm_response}
        history.append(entry)
        save_narration_history(history)

    finally:
        # Release lock and close file (only if successfully opened)
        if lock_file is not None:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()


def get_narrations_range(start_turn: int, end_turn: int) -> List[Dict[str, Any]]:
    """
    Get narrations from a specific turn range.

    Args:
        start_turn: First turn to retrieve (inclusive)
        end_turn: Last turn to retrieve (inclusive)

    Returns:
        List of narration entries in the range
    """
    history = load_narration_history()
    return [
        entry for entry in history if start_turn <= entry.get("turn", 0) <= end_turn
    ]


def extract_lore_from_narration(
    narration: str,
    turn_number: int,
    existing_lore: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Use GPT-5-nano to extract lore from DM narration.
    Also handles updates, merges, and duplicate detection.

    Args:
        narration: The DM's narration text
        turn_number: Current turn number for tracking
        existing_lore: Retrieved relevant lore for context

    Returns:
        Dictionary with new_entries, updated_entries, deleted_ids, or None if extraction fails
    """
    # Format existing lore for prompt
    existing_lore_text = ""
    if existing_lore:
        existing_lore_text = "\n\n=== EXISTING RELATED LORE ===\n"
        for entry in existing_lore:
            existing_lore_text += f"\nID: {entry.get('id', 'unknown')}\n"
            existing_lore_text += f"Type: {entry.get('type', 'unknown')}\n"
            existing_lore_text += f"Name: {entry.get('name', 'unknown')}\n"
            existing_lore_text += f"Tags: {', '.join(entry.get('tags', []))}\n"
            existing_lore_text += f"Full text: {entry.get('full_text', '')}\n"

    system_prompt = f"""You are analyzing D&D narration to extract lore AND manage existing lore.

OUTPUT FORMAT: Return ONLY valid JSON:
{{
  "new_entries": [
    {{
      "type": "npc|location|faction|event|item|worldfact",
      "name": "Name or title",
      "tags": ["keyword1", "keyword2", "keyword3"],
      "full_text": "Detailed description (2-4 sentences with all relevant information)"
    }}
  ],
  "updated_entries": [
    {{
      "id": "lore_003",
      "additional_text": "New information to append to full_text",
      "new_tags": ["additional", "tags"]
    }}
  ],
  "deleted_ids": ["lore_005"]
}}

**CRITICAL:** ALL new lore entries MUST go in the "new_entries" array. Do NOT create additional fields like "new_entries_additional" - everything goes in "new_entries".

=== LORE MANAGEMENT RULES ===

**NEW ENTRIES (new_entries):**
• Create for genuinely new NPCs, locations, factions, events, items, world facts
• Don't duplicate if already exists in existing lore

**UPDATED ENTRIES (updated_entries):**
• If narration adds NEW details about existing lore, update it
• Append new information to `additional_text` (will be added to full_text)
• Add new relevant tags to `new_tags`
• **Be conservative**: Only update if there's genuinely new information

**DELETED ENTRIES (deleted_ids):**
• Only for OBVIOUS duplicates (same entity with different name or ID)
• Example: "Gareth" and "Gareth the Merchant" are the same person
• **Be very conservative**: Only delete if 100% certain it's a duplicate

=== WHAT TO EXTRACT ===

**NPCs (type: "npc"):**
• Named characters with speaking roles or significance
• Include personality traits, goals, relationships
• Tags: profession, species, personality, affiliations

**Locations (type: "location"):**
• Named places (towns, buildings, dungeons, landmarks)
• Include atmosphere, notable features, dangers
• Tags: type (tavern, city, dungeon), danger level, region

**Factions (type: "faction"):**
• Groups, organizations, guilds, religions
• Include goals, methods, leadership
• Tags: alignment, power level, domain

**Events (type: "event"):**
• Significant happenings (battles, discoveries, betrayals)
• Include consequences and participants
• Tags: type (battle, discovery), participants, outcome

**Items (type: "item"):**
• Named magical items, artifacts, unique objects
• Include powers, history, current location
• Tags: type (weapon, artifact), power level, location

**World Facts (type: "worldfact"):**
• Cosmology, history, magic rules, cultural norms
• Include scope and implications
• Tags: category (history, magic, culture), scope

=== EXTRACTION RULES ===

**DO extract:**
• Anything with a proper name
• Significant descriptive details (NPC personality, location atmosphere)
• New revelations about the world or plot
• Things players might want to remember later

**EXTRAPOLATE IMPLICATIONS:**
• Read between the lines - what does the narration imply?
• Example: "old imperial eagles" suggests:
  1. There WAS an old empire
  2. That empire used eagles as symbols
  3. The empire likely no longer exists (they're "old")
  4. We're probably in what used to be imperial territory
• Example: "the bell tolls...impossible, because its rope burned in the spring fire"
  1. There was a fire in spring
  2. The bell is ringing mysteriously (potential plot hook)
  3. Locals remember the fire (recent event)
• Add these extrapolations as world facts or update existing lore

**DON'T extract:**
• Generic unnamed things ("a guard", "the forest")
• Temporary/disposable elements
• Mechanics or dice roll results
• Player actions (focus on world, not PCs)

**Tags should be:**
• Lowercase, single words
• Searchable keywords (professions, species, alignments, etc.)
• 3-5 tags per entry

=== EXAMPLES ===

Narration: "The merchant, a portly halfling named Gareth, eyes you suspiciously. 'No credit here, stranger. Gold up front.' His fingers drum on a dagger at his belt."
Existing lore: (none)

Output:
{{
  "new_entries": [
    {{
      "type": "npc",
      "name": "Gareth",
      "tags": ["merchant", "halfling", "suspicious", "greedy"],
      "full_text": "Gareth is a portly halfling merchant who eyes strangers suspiciously and demands payment upfront. He refuses credit and keeps a dagger at his belt, suggesting he's had trouble with customers before."
    }}
  ],
  "updated_entries": [],
  "deleted_ids": []
}}

Narration: "Gareth's eyes widen as you mention the Silver Covenant. 'Them? They're trouble. I don't deal with their kind.'"
Existing lore: 
  ID: lore_001, Name: Gareth, Type: npc, Full text: "Gareth is a portly halfling merchant..."

Output:
{{
  "new_entries": [],
  "updated_entries": [
    {{
      "id": "lore_001",
      "additional_text": " Gareth is wary of the Silver Covenant and refuses to do business with them, calling them 'trouble.'",
      "new_tags": ["wary", "covenant"]
    }}
  ],
  "deleted_ids": []
}}

Narration: "The guard simply nods and waves you through the gate."
Existing lore: (none)

Output:
{{
  "new_entries": [],
  "updated_entries": [],
  "deleted_ids": []
}}

Narration: "An old imperial eagle, half-buried in the road like a fossil, stares up with a cracked eye. The Bent Nail tavern sign groans in the wind."
Existing lore: (none)

Output (WITH EXTRAPOLATION):
{{
  "new_entries": [
    {{
      "type": "location",
      "name": "The Bent Nail",
      "tags": ["tavern", "duskwold"],
      "full_text": "The Bent Nail is a tavern in Duskwold. Its wooden sign groans in the wind, suggesting age and neglect."
    }},
    {{
      "type": "worldfact",
      "name": "The Old Empire",
      "tags": ["history", "empire", "fallen", "eagles"],
      "full_text": "There was once an empire that used eagles as its symbol. These imperial eagles are now described as 'old' and half-buried, suggesting the empire has fallen or collapsed. The area is likely former imperial territory where remnants of the old regime still linger."
    }}
  ],
  "updated_entries": [],
  "deleted_ids": []
}}

Analyze the narration and existing lore, then return ONLY valid JSON.{existing_lore_text}"""

    try:
        # Use Responses API like roll_analyzer does - nano works fine with this!
        print(f"\n{'='*70}")
        print(f"🔍 LORE EXTRACTION DEBUG")
        print(f"{'='*70}")
        print(f"\n[SYSTEM PROMPT]")
        print(system_prompt)
        print(f"\n[USER MESSAGE]")
        user_message = f"Turn {turn_number} narration:\n{narration}"
        print(user_message)
        print(f"\n{'='*70}\n")

        print(f"[DEBUG] Calling GPT-5-nano for lore extraction (Responses API)...")
        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            reasoning={"effort": "low"},  # Low reasoning for faster generation
            text={"format": {"type": "json_object"}},
            max_output_tokens=64000,  # Quadrupled again from 16000 for extremely detailed extraction
        )
        print(f"[DEBUG] API call completed successfully")

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
        log_cache_stats("Lore_Extractor", cached_tokens, total_tokens, "gpt-5-nano")

        if cached_tokens > 0:
            print(f"💾 [LORE EXTRACTOR] CACHE HIT: {cached_tokens} tokens cached")  # type: ignore

        # Extract text from Responses API output (like roll_analyzer does)
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore

        print(f"[DEBUG] Output text length: {len(output_text)} characters")
        print(f"\n[LLM OUTPUT]")
        print(output_text)
        print(f"\n{'='*70}\n")

        if not output_text or output_text.strip() == "":
            print(f"[DEBUG] Output text is empty!")
            return None

        result = json.loads(output_text)
        print(
            f"[DEBUG] JSON parsed successfully: {len(result.get('new_entries', []))} new entries"
        )

        # Add turn number to each entry
        if "new_entries" in result:
            for entry in result["new_entries"]:
                entry["created_turn"] = turn_number
                entry["last_updated"] = turn_number

        return result

    except Exception as e:
        print(f"\n⚠️  LORE EXTRACTION ERROR: {e}")
        import traceback

        traceback.print_exc()
        return None


def extract_lore_from_narration_batch(
    narrations: List[Dict[str, Any]],
    existing_lore: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Use GPT-5-nano to extract lore from a BATCH of narrations (e.g., 5 turns).
    Processes multiple narrations at once for better context and efficiency.

    Args:
        narrations: List of narration dictionaries with 'turn', 'player', 'dm' keys
        existing_lore: Retrieved relevant lore for context

    Returns:
        Dictionary with new_entries, updated_entries, deleted_ids, or None if extraction fails
    """
    if not narrations:
        return None

    # Format narrations for prompt
    narrations_text = ""
    for entry in narrations:
        turn = entry.get("turn", "?")
        player = entry.get("player", "")
        dm = entry.get("dm", "")
        narrations_text += f"\n--- TURN {turn} ---\n"
        narrations_text += f"Player: {player}\n"
        narrations_text += f"DM: {dm}\n"

    # Format existing lore for prompt (batch version)
    existing_lore_text = ""
    if existing_lore:
        existing_lore_text = "\n\n=== EXISTING RELATED LORE ===\n"
        for entry in existing_lore:
            existing_lore_text += f"\nID: {entry.get('id', 'unknown')}\n"
            existing_lore_text += f"Type: {entry.get('type', 'unknown')}\n"
            existing_lore_text += f"Name: {entry.get('name', 'unknown')}\n"
            existing_lore_text += f"Tags: {', '.join(entry.get('tags', []))}\n"
            existing_lore_text += f"Full text: {entry.get('full_text', '')}\n"

    system_prompt = f"""You are analyzing MULTIPLE D&D narration turns to extract lore AND manage existing lore.

You will receive 5 consecutive turns of narration. Extract lore from ALL of them together.

OUTPUT FORMAT: Return ONLY valid JSON:
{{
  "new_entries": [
    {{
      "type": "npc|location|faction|event|item|worldfact",
      "name": "Name or title",
      "tags": ["keyword1", "keyword2", "keyword3"],
      "full_text": "Detailed description (2-4 sentences with all relevant information)"
    }}
  ],
  "updated_entries": [
    {{
      "id": "lore_003",
      "additional_text": "New information to append to full_text",
      "new_tags": ["additional", "tags"]
    }}
  ],
  "deleted_ids": ["lore_005"]
}}

=== LORE MANAGEMENT RULES ===

**NEW ENTRIES (new_entries):**
• Create for genuinely new NPCs, locations, factions, events, items, world facts
• Look across ALL turns for recurring elements
• Don't duplicate if already exists in existing lore

**UPDATED ENTRIES (updated_entries):**
• If narrations add NEW details about existing lore, update it
• Append new information to `additional_text` (will be added to full_text)
• Add new relevant tags to `new_tags`
• **Be conservative**: Only update if there's genuinely new information

**DELETED ENTRIES (deleted_ids):**
• Only for OBVIOUS duplicates (same entity with different name or ID)
• Example: "Gareth" and "Gareth the Merchant" are the same person
• **Be very conservative**: Only delete if 100% certain it's a duplicate

**EXTRACTION GUIDELINES:**

**DO extract:**
• Anything with a proper name
• Significant descriptive details (NPC personality, location atmosphere)
• New revelations about the world or plot
• Things players might want to remember later
• Patterns and connections across multiple turns

**DON'T extract:**
• Generic unnamed things ("a guard", "the forest")
• Temporary/disposable elements
• Mechanics or dice roll results
• Player actions (focus on world, not PCs)

**Tags should be:**
• Lowercase, single words
• Searchable keywords (professions, species, alignments, etc.)
• 3-5 tags per entry

Analyze ALL the narrations and existing lore, then return ONLY valid JSON.{existing_lore_text}"""

    try:
        response = client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": f"Narrations to analyze:{narrations_text}"},
            ],
            reasoning={"effort": "low"},
            text={"format": {"type": "json_object"}},
            max_output_tokens=8000,  # Quadrupled from 2000 for batch processing
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
        log_cache_stats(
            "Lore_Extractor_Batch", cached_tokens, total_tokens, "gpt-5-nano"
        )

        if cached_tokens > 0:
            print(f"💾 [LORE EXTRACTOR BATCH] CACHE HIT: {cached_tokens} tokens cached")  # type: ignore

        # Extract text
        output_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content is not None:  # type: ignore
                for content in item.content:  # type: ignore
                    if hasattr(content, "text") and content.text is not None:  # type: ignore
                        output_text += content.text  # type: ignore

        if not output_text or output_text.strip() == "":
            return None

        result = json.loads(output_text)

        # Add turn number range to each new entry (use last turn number)
        last_turn = narrations[-1].get("turn", 0) if narrations else 0
        if "new_entries" in result:
            for entry in result["new_entries"]:
                entry["created_turn"] = last_turn
                entry["last_updated"] = last_turn

        return result

    except Exception as e:
        print(f"⚠️  Batch lore extraction failed: {e}")
        return None


def apply_lore_operations(
    new_entries: List[Dict[str, Any]],
    updated_entries: List[Dict[str, Any]],
    deleted_ids: List[str],
):
    """
    Apply lore operations: add new entries, update existing ones, delete duplicates.

    Args:
        new_entries: List of new lore entries to add
        updated_entries: List of entries to update (with id, additional_text, new_tags)
        deleted_ids: List of lore IDs to delete
    """
    # Load existing lore
    lore_data = load_lore()

    # 1. Delete duplicates
    if deleted_ids:
        original_count = len(lore_data["entries"])
        lore_data["entries"] = [
            e for e in lore_data["entries"] if e.get("id") not in deleted_ids
        ]
        deleted_count = original_count - len(lore_data["entries"])
        print(f"🗑️  Deleted {deleted_count} duplicate entries: {', '.join(deleted_ids)}")

    # 2. Update existing entries
    if updated_entries:
        for update in updated_entries:
            update_id = update.get("id")
            additional_text = update.get("additional_text", "")
            new_tags = update.get("new_tags", [])

            # Find the entry to update
            for entry in lore_data["entries"]:
                if entry.get("id") == update_id:
                    # Append new text
                    if additional_text:
                        entry["full_text"] = (
                            entry.get("full_text", "") + additional_text
                        )

                    # Add new tags (avoid duplicates)
                    existing_tags = set(entry.get("tags", []))
                    for tag in new_tags:
                        if tag not in existing_tags:
                            entry.setdefault("tags", []).append(tag)

                    # Update last_updated
                    entry["last_updated"] = update.get(
                        "turn", entry.get("last_updated", 0)
                    )

                    print(f"📝 Updated lore entry: {entry.get('name', update_id)}")
                    break

    # 3. Add new entries
    if new_entries:
        # Generate IDs for new entries - extract max ID from existing entries
        max_id = 0
        for entry in lore_data["entries"]:
            entry_id = entry.get("id", "")
            if entry_id.startswith("lore_"):
                try:
                    id_num = int(entry_id.split("_")[1])
                    max_id = max(max_id, id_num)
                except (ValueError, IndexError):
                    pass

        next_id = max_id + 1

        for entry in new_entries:
            entry["id"] = f"lore_{next_id:03d}"
            next_id += 1
            lore_data["entries"].append(entry)

        print(f"📝 Added {len(new_entries)} new lore entries")

    # Save
    save_lore(lore_data)


def process_narration_for_lore(
    player_input: str,
    narration: str,
    turn_number: int,
    existing_lore: Optional[List[Dict[str, Any]]] = None,
):
    """
    Main function: save narration and extract lore.

    Args:
        player_input: What the player said
        narration: DM's narration text
        turn_number: Current turn number
        existing_lore: Retrieved relevant lore for context
    """
    print(f"\n[DEBUG] process_narration_for_lore called for turn {turn_number}")

    # Save narration to history
    save_narration(player_input, narration, turn_number)
    print(f"[DEBUG] Narration saved, calling extract_lore_from_narration...")

    # Extract and save lore
    print(f"\n🔍 Extracting lore from turn {turn_number}...")

    result = extract_lore_from_narration(narration, turn_number, existing_lore)
    print(f"[DEBUG] Extraction result: {type(result)}, {result is not None}")

    if result:
        new_entries = result.get("new_entries", [])
        updated_entries = result.get("updated_entries", [])
        deleted_ids = result.get("deleted_ids", [])

        # Add turn number to entries
        for entry in new_entries:
            entry["created_turn"] = turn_number
            entry["last_updated"] = turn_number

        for update in updated_entries:
            update["turn"] = turn_number

        # Show what was found
        if new_entries:
            print(f"   Found {len(new_entries)} new lore entries:")
            for entry in new_entries:
                print(f"   - {entry['type'].upper()}: {entry['name']}")

        if updated_entries:
            print(f"   Updating {len(updated_entries)} existing entries")

        if deleted_ids:
            print(f"   Deleting {len(deleted_ids)} duplicate entries")

        # Apply all operations
        if new_entries or updated_entries or deleted_ids:
            apply_lore_operations(new_entries, updated_entries, deleted_ids)
        else:
            print(f"   No lore changes needed.")
    else:
        print(f"   No significant lore to extract.")


def process_narration_batch_for_lore(
    start_turn: int, end_turn: int, existing_lore: Optional[List[Dict[str, Any]]] = None
):
    """
    Batch process multiple narrations for lore extraction.
    Called every 5 turns to extract lore before it drops out of conversation window.

    Args:
        start_turn: First turn to process (inclusive)
        end_turn: Last turn to process (inclusive)
        existing_lore: Retrieved relevant lore for context
    """
    # Get narrations from turn range
    narrations = get_narrations_range(start_turn, end_turn)

    if not narrations:
        print(f"\n⚠️  No narrations found for turns {start_turn}-{end_turn}")
        return

    print(
        f"\n🔍 Batch extracting lore from turns {start_turn}-{end_turn} ({len(narrations)} narrations)..."
    )

    # Extract lore from batch
    result = extract_lore_from_narration_batch(narrations, existing_lore)

    if result:
        new_entries = result.get("new_entries", [])
        updated_entries = result.get("updated_entries", [])
        deleted_ids = result.get("deleted_ids", [])

        # Add turn number to updates
        for update in updated_entries:
            update["turn"] = end_turn

        # Show what was found
        if new_entries:
            print(f"   Found {len(new_entries)} new lore entries:")
            for entry in new_entries:
                print(f"   - {entry['type'].upper()}: {entry['name']}")

        if updated_entries:
            print(f"   Updating {len(updated_entries)} existing entries")

        if deleted_ids:
            print(f"   Deleting {len(deleted_ids)} duplicate entries")

        # Apply all operations
        if new_entries or updated_entries or deleted_ids:
            apply_lore_operations(new_entries, updated_entries, deleted_ids)
        else:
            print(f"   No lore changes needed.")
    else:
        print(f"   No significant lore to extract from batch.")


if __name__ == "__main__":
    # Test extraction
    test_narration = """
    The merchant, a portly halfling named Gareth, eyes you suspiciously. 
    'No credit here, stranger. Gold up front.' His fingers drum on a dagger at his belt.
    You're in the Rusty Nail, a dimly-lit tavern reeking of ale and desperation.
    """

    test_player_input = "I approach the merchant."

    process_narration_for_lore(test_player_input, test_narration, turn_number=1)

    # Display results
    lore = load_lore()
    print(f"\n📚 World Lore ({len(lore['entries'])} entries):")
    print(json.dumps(lore, indent=2))

    narrations = load_narration_history()
    print(f"\n📖 Narration History ({len(narrations)} turns):")
    print(json.dumps(narrations, indent=2))
