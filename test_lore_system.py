"""
Test the enhanced lore extraction system with updates, merges, and deletions.
"""

from lore_extractor import process_narration_for_lore, load_lore, reset_world_data
from lore_retrieval import retrieve_relevant_context
import json


def test_lore_system():
    """Test the complete lore system with automated assertions."""
    print("\n" + "=" * 70)
    print("  TESTING ENHANCED LORE SYSTEM")
    print("=" * 70)

    # Reset lore
    print("\n1. Resetting lore...")
    reset_world_data()
    lore = load_lore()
    assert len(lore["entries"]) == 0, "Lore should be empty after reset"
    print("✅ Lore reset successful")

    # Turn 1: Create initial lore
    print("\n2. Turn 1: Creating initial lore (Gareth the merchant)...")
    narration_1 = "The merchant, a portly halfling named Gareth, eyes you suspiciously. 'No credit here, stranger. Gold up front.' His fingers drum on a dagger at his belt."
    player_1 = "I approach the merchant."

    process_narration_for_lore(player_1, narration_1, turn_number=1)

    # Verify lore creation
    lore = load_lore()
    print(f"\n📚 Lore after turn 1: {len(lore['entries'])} entries")
    assert (
        len(lore["entries"]) > 0
    ), "Lore should contain at least one entry after turn 1"

    # Find Gareth entry
    gareth_entry = next(
        (e for e in lore["entries"] if "gareth" in e.get("name", "").lower()), None
    )
    assert gareth_entry is not None, "Should have created a lore entry for Gareth"
    assert (
        gareth_entry["type"] == "npc"
    ), f"Gareth should be an NPC, got {gareth_entry['type']}"
    print(f"✅ Created NPC entry for Gareth (ID: {gareth_entry['id']})")

    initial_gareth_text = gareth_entry["full_text"]
    initial_entry_count = len(lore["entries"])

    for entry in lore["entries"]:
        print(f"  - {entry['type'].upper()}: {entry['name']} (ID: {entry['id']})")

    # Turn 2: Update existing lore
    print("\n3. Turn 2: Updating Gareth with new info...")
    narration_2 = "Gareth's eyes widen as you mention the Silver Covenant. 'Them? They're trouble. I don't deal with their kind. They nearly burned down my shop last year.'"
    player_2 = "I ask Gareth about the Silver Covenant."

    # Retrieve relevant lore first
    context = retrieve_relevant_context(player_2, narration_1)

    process_narration_for_lore(
        player_2,
        narration_2,
        turn_number=2,
        existing_lore=context.get("lore_entries", []),
    )

    # Verify update instead of duplicate
    lore = load_lore()
    print(f"\n📚 Lore after turn 2: {len(lore['entries'])} entries")

    # Should have created Silver Covenant entry but NOT duplicated Gareth
    gareth_entries = [
        e for e in lore["entries"] if "gareth" in e.get("name", "").lower()
    ]
    assert (
        len(gareth_entries) == 1
    ), f"Should have exactly 1 Gareth entry, found {len(gareth_entries)}"
    print("✅ Gareth entry was updated, not duplicated")

    # Verify Gareth's text was updated
    updated_gareth = gareth_entries[0]
    assert len(updated_gareth["full_text"]) > len(
        initial_gareth_text
    ), "Gareth's description should be longer after update"
    assert (
        "silver covenant" in updated_gareth["full_text"].lower()
    ), "Gareth's entry should mention Silver Covenant"
    print("✅ Gareth's entry contains new information about Silver Covenant")

    # Check for new faction entry
    covenant_entry = next(
        (e for e in lore["entries"] if "silver covenant" in e.get("name", "").lower()),
        None,
    )
    if covenant_entry:
        assert (
            covenant_entry["type"] == "faction"
        ), f"Silver Covenant should be a faction, got {covenant_entry['type']}"
        print(
            f"✅ Created faction entry for Silver Covenant (ID: {covenant_entry['id']})"
        )

    for entry in lore["entries"]:
        print(f"  - {entry['type'].upper()}: {entry['name']} (ID: {entry['id']})")
        if entry["id"] == gareth_entry["id"]:
            print(f"    Full text: {entry['full_text'][:200]}...")

    # Turn 3: Create new location
    print("\n4. Turn 3: Creating new location (The Rusty Nail)...")
    narration_3 = "You enter the Rusty Nail, a dimly-lit tavern reeking of ale and desperation. Wanted posters peel from the walls. Gareth was right - this place looks like trouble."
    player_3 = "I enter the Rusty Nail tavern."

    context = retrieve_relevant_context(player_3, narration_2)

    process_narration_for_lore(
        player_3,
        narration_3,
        turn_number=3,
        existing_lore=context.get("lore_entries", []),
    )

    # Verify new location
    lore = load_lore()
    print(f"\n📚 Final lore: {len(lore['entries'])} entries")

    tavern_entry = next(
        (e for e in lore["entries"] if "rusty nail" in e.get("name", "").lower()), None
    )
    assert (
        tavern_entry is not None
    ), "Should have created a lore entry for Rusty Nail tavern"
    assert (
        tavern_entry["type"] == "location"
    ), f"Rusty Nail should be a location, got {tavern_entry['type']}"
    print(f"✅ Created location entry for Rusty Nail (ID: {tavern_entry['id']})")

    # Verify all entries have required fields
    for entry in lore["entries"]:
        assert "id" in entry, f"Entry missing 'id': {entry}"
        assert "type" in entry, f"Entry missing 'type': {entry}"
        assert "name" in entry, f"Entry missing 'name': {entry}"
        assert "full_text" in entry, f"Entry missing 'full_text': {entry}"
        assert "tags" in entry, f"Entry missing 'tags': {entry}"
        assert isinstance(entry["tags"], list), f"Tags should be a list: {entry}"
    print("✅ All entries have required fields with correct types")

    print("\n" + json.dumps(lore, indent=2))

    print("\n" + "=" * 70)
    print("  ✅ ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    test_lore_system()
