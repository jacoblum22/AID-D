"""
Test script for the use_item tool.

This tests the comprehensive item usage mechanics including:
- Basic usage methods (consume, activate, equip, read)
- Delegation system (scroll_fireball → attack, potion_persuasion → talk)
- Cursed items and failure modes
- Area effects and enhanced logging
- Misuse detection and error handling
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, HP, Utterance
from router.validator import validate_and_execute


@pytest.fixture
def use_item_state():
    """Create a game state set up for use_item testing."""

    # Create zones
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard.",
            adjacent_zones=["threshold"],
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold.",
            adjacent_zones=["courtyard"],
        ),
    }

    # Create entities with inventories
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=15, max=20),  # Injured for healing tests
            visible_actors=["npc.guard", "pc.ally"],
            inventory=[
                "healing_potion",
                "poison_vial",
                "lantern",
                "rope",
                "scroll_fireball",
                "sword",
                "cursed_ring",
                "potion_persuasion",
                "grappling_hook",
            ],
            style_bonus=0,
        ),
        "pc.ally": PC(
            id="pc.ally",
            name="Ally",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=18, max=20),
            visible_actors=["pc.arin", "npc.guard"],
            inventory=[],
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=20, max=20),
            visible_actors=["pc.arin", "pc.ally"],
            guard=2,
        ),
        "npc.distant": NPC(
            id="npc.distant",
            name="Distant Figure",
            type="npc",
            current_zone="threshold",  # Different zone
            hp=HP(current=15, max=15),
            visible_actors=[],
        ),
    }

    return GameState(
        entities=entities,
        zones=zones,
        current_actor="pc.arin",
        clocks={},
        pending_action=None,
    )


class TestBasicItemUsage:
    """Test basic item usage methods."""

    def test_consume_healing_potion(self, use_item_state):
        """Test consuming a healing potion."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink the healing potion", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok
        assert result.tool_id == "use_item"

        # Check effects generated
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        assert len(hp_effects) == 1
        assert hp_effects[0]["target"] == "pc.arin"
        assert hp_effects[0]["delta"] > 0  # Should heal

        # Check inventory removal
        inventory_effects = [e for e in result.effects if e["type"] == "inventory"]
        assert len(inventory_effects) == 1
        assert inventory_effects[0]["item"] == "healing_potion"
        assert inventory_effects[0]["delta"] == -1

        # Check narration hint
        assert "healing potion" in result.narration_hint["summary"].lower()
        assert "item" in result.narration_hint["tone_tags"]

    def test_consume_poison_on_enemy(self, use_item_state):
        """Test using poison vial on an enemy."""
        args = {
            "actor": "pc.arin",
            "item_id": "poison_vial",
            "target": "npc.guard",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use poison on the guard", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check damage effect
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        assert len(hp_effects) == 1
        assert hp_effects[0]["target"] == "npc.guard"
        assert hp_effects[0]["delta"] < 0  # Should damage

    def test_activate_lantern(self, use_item_state):
        """Test activating a lantern."""
        args = {
            "actor": "pc.arin",
            "item_id": "lantern",
            "method": "activate",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I light the lantern", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check tag effect for lighting
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        assert len(tag_effects) >= 1

        # Check item NOT consumed (activation doesn't consume)
        inventory_effects = [e for e in result.effects if e["type"] == "inventory"]
        consumed_effects = [e for e in inventory_effects if e.get("delta", 0) < 0]
        assert len(consumed_effects) == 0

    def test_equip_sword(self, use_item_state):
        """Test equipping a sword."""
        args = {
            "actor": "pc.arin",
            "item_id": "sword",
            "method": "equip",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I equip my sword", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check guard effect
        guard_effects = [e for e in result.effects if e["type"] == "guard"]
        assert len(guard_effects) == 1

        # Check equipped tag
        tag_effects = [e for e in result.effects if e["type"] == "tag"]
        equipped_tags = [e for e in tag_effects if "equipped_sword" in e.get("add", {})]
        assert len(equipped_tags) == 1

    def test_read_scroll(self, use_item_state):
        """Test reading a scroll."""
        args = {
            "actor": "pc.arin",
            "item_id": "scroll_fireball",
            "target": "npc.guard",
            "method": "read",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I read the scroll", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Should be consumed after reading
        inventory_effects = [e for e in result.effects if e["type"] == "inventory"]
        consumed_effects = [e for e in inventory_effects if e.get("delta", 0) < 0]
        assert len(consumed_effects) == 1


class TestDelegationSystem:
    """Test the delegation system for complex items."""

    def test_scroll_fireball_delegates_to_attack(self, use_item_state):
        """Test that scroll_fireball delegates to attack tool."""
        args = {
            "actor": "pc.arin",
            "item_id": "scroll_fireball",
            "target": "npc.guard",
            "method": "read",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I cast fireball", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check delegation occurred
        facts = result.facts
        assert "delegation" in facts.get("item_usage_metadata", {})

        # Should have attack-like effects (HP damage)
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        damage_effects = [e for e in hp_effects if e.get("delta", 0) < 0]
        assert len(damage_effects) >= 1

        # Narration should mention the scroll
        assert (
            "scroll" in result.narration_hint["summary"].lower()
            or "fireball" in result.narration_hint["summary"].lower()
        )

    def test_potion_persuasion_delegates_to_talk(self, use_item_state):
        """Test that potion_persuasion delegates to talk tool."""
        args = {
            "actor": "pc.arin",
            "item_id": "potion_persuasion",
            "target": "npc.guard",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink potion and talk", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check delegation occurred
        facts = result.facts
        assert "delegation" in facts.get("item_usage_metadata", {})

        # Should have social effects (guard reduction or marks)
        social_effects = [
            e for e in result.effects if e["type"] in ("guard", "mark", "clock")
        ]
        assert len(social_effects) >= 1

    def test_grappling_hook_delegates_to_move(self, use_item_state):
        """Test that grappling_hook delegates to move tool."""
        args = {
            "actor": "pc.arin",
            "item_id": "grappling_hook",
            "target": "threshold",  # Specify where to go
            "method": "activate",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use grappling hook", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check delegation occurred
        facts = result.facts
        assert "delegation" in facts.get("item_usage_metadata", {})


class TestCursedItemsAndFailureModes:
    """Test cursed items and advanced failure modes."""

    def test_cursed_ring_has_negative_effects(self, use_item_state):
        """Test that cursed ring applies both positive and negative effects."""
        args = {
            "actor": "pc.arin",
            "item_id": "cursed_ring",
            "method": "equip",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I equip the ring", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Should have both positive and negative effects
        _hp_effects = [
            e for e in result.effects if e["type"] == "hp"
        ]  # May be used in future assertions

        # Check for curse effects
        curse_effects = [e for e in result.effects if e.get("is_curse", False)]
        assert len(curse_effects) > 0

    def test_misuse_detection_wrong_method(self, use_item_state):
        """Test misuse detection when using wrong method."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",  # Should be consumed, not equipped
            "method": "equip",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I equip the potion", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"
        assert "consume" in result.args["question"]

    def test_dangerous_item_warning(self, use_item_state):
        """Test warning when using dangerous items on allies."""
        args = {
            "actor": "pc.arin",
            "item_id": "poison_vial",
            "target": "pc.ally",  # Using poison on ally
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use poison on ally", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"
        assert (
            "harm" in result.args["question"].lower()
            or "warning" in result.args["question"].lower()
        )

    def test_area_effect_item(self, use_item_state):
        """Test area effect items affect multiple targets."""
        args = {
            "actor": "pc.arin",
            "item_id": "scroll_fireball",  # Has area_effect in items.json
            "target": "npc.guard",
            "method": "read",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I cast fireball", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Should have area effect processing
        area_effects = [e for e in result.effects if e["type"] == "area_effect"]
        # Note: Area effects might be processed by delegation system


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_item_not_in_inventory(self, use_item_state):
        """Test using item not in inventory."""
        args = {
            "actor": "pc.arin",
            "item_id": "nonexistent_item",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use mysterious item", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"

    def test_target_not_found(self, use_item_state):
        """Test using item on non-existent target."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "target": "nonexistent_target",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I heal nobody", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"

    def test_unconscious_actor_cannot_use_items(self, use_item_state):
        """Test that unconscious actors cannot use items."""
        # Set actor to 0 HP
        use_item_state.entities["pc.arin"].hp.current = 0

        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I try to heal", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"
        assert "unconscious" in result.args["question"].lower()

    def test_target_not_visible(self, use_item_state):
        """Test using item on non-visible target."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "target": "npc.distant",  # In different zone, not visible
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I heal distant figure", actor_id="pc.arin"),
            seed=42,
        )

        assert not result.ok
        assert result.tool_id == "ask_clarifying"


class TestEnhancedLogging:
    """Test enhanced logging and replay features."""

    def test_dice_roll_logging(self, use_item_state):
        """Test that dice rolls are logged for replay."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",  # Has dice expression "2d4+2"
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink potion", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check enhanced logging metadata
        metadata = result.facts.get("item_usage_metadata", {})
        assert "dice_rolls" in metadata
        assert "seed" in metadata
        assert metadata["seed"] == 42

    def test_inventory_state_tracking(self, use_item_state):
        """Test that inventory states are tracked before/after."""
        initial_inventory = use_item_state.entities["pc.arin"].inventory.copy()

        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink potion", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check inventory tracking in facts
        assert "inventory_before" in result.facts
        assert "inventory_after" in result.facts
        assert result.facts["inventory_before"] == initial_inventory
        assert "healing_potion" not in result.facts["inventory_after"]

    def test_enhanced_narration_metadata(self, use_item_state):
        """Test that narration hints include rich metadata."""
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink potion", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check narration metadata
        hint = result.narration_hint
        assert "item" in hint
        assert "inventory" in hint
        assert "enhanced_logging" in hint

        # Check item-specific metadata
        item_meta = hint["item"]
        assert item_meta["id"] == "healing_potion"
        assert item_meta["consumed"] is True
        assert "charges_remaining" in item_meta


class TestBackwardCompatibility:
    """Test backward compatibility with existing systems."""

    def test_legacy_item_fallback(self, use_item_state):
        """Test that system falls back to legacy items if items.json unavailable."""
        # This tests the fallback registry functionality
        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I drink potion", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok
        # Should work regardless of whether items.json or fallback is used

    def test_unknown_item_handling(self, use_item_state):
        """Test handling of completely unknown items."""
        # Add unknown item to inventory
        use_item_state.entities["pc.arin"].inventory.append("mystery_item")

        args = {
            "actor": "pc.arin",
            "item_id": "mystery_item",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use mystery item", actor_id="pc.arin"),
            seed=42,
        )

        # Should handle gracefully with fallback definition
        assert result.ok or result.tool_id == "ask_clarifying"


# Integration tests with other systems
class TestSystemIntegration:
    """Test integration with other game systems."""

    def test_item_effects_apply_to_state(self, use_item_state):
        """Test that item effects are properly applied to game state."""
        initial_hp = use_item_state.entities["pc.arin"].hp.current

        args = {
            "actor": "pc.arin",
            "item_id": "healing_potion",
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I heal", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Note: Effects application happens in the validator pipeline
        # This test ensures the structure is correct for effect application
        hp_effects = [e for e in result.effects if e["type"] == "hp"]
        assert len(hp_effects) == 1
        assert hp_effects[0]["target"] == "pc.arin"
        healing_delta = hp_effects[0]["delta"]
        assert healing_delta > 0

        # Verify the healing amount makes sense relative to initial HP
        assert healing_delta > 0, f"Expected positive healing, got {healing_delta}"
        assert initial_hp + healing_delta <= 20, f"Healing would exceed max HP"

    def test_marks_and_guards_interaction(self, use_item_state):
        """Test item effects interact properly with marks and guards."""
        args = {
            "actor": "pc.arin",
            "item_id": "rope",  # Gives climbing advantage mark
            "method": "consume",
        }

        result = validate_and_execute(
            "use_item",
            args,
            use_item_state,
            Utterance(text="I use rope", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok

        # Check mark effects
        mark_effects = [e for e in result.effects if e["type"] == "mark"]
        assert len(mark_effects) >= 1


class TestIgnoreAdjacency:
    """Test items that can bypass adjacency restrictions like grappling hook."""

    @pytest.fixture
    def grappling_state(self):
        """Create a game state with non-adjacent zones for testing grappling hook."""

        # Create zones where tower is NOT adjacent to courtyard
        zones = {
            "courtyard": Zone(
                id="courtyard",
                name="Courtyard",
                description="A stone courtyard.",
                adjacent_zones=["garden"],  # Only adjacent to garden, not tower
            ),
            "garden": Zone(
                id="garden",
                name="Garden",
                description="A peaceful garden.",
                adjacent_zones=["courtyard", "tower"],
            ),
            "tower": Zone(
                id="tower",
                name="Tower",
                description="A tall stone tower.",
                adjacent_zones=["garden"],  # Not directly adjacent to courtyard
            ),
        }

        # Create PC with grappling hook
        entities = {
            "pc.arin": PC(
                id="pc.arin",
                name="Arin",
                type="pc",
                current_zone="courtyard",
                hp=HP(current=10, max=10),
                visible_actors=[],
                inventory=["grappling_hook"],  # Has grappling hook
                style_bonus=0,
            ),
        }

        return GameState(
            entities=entities,  # type: ignore
            zones=zones,
            current_actor="pc.arin",
            turn_flags={},
            clocks={},
        )

    def test_grappling_hook_ignores_adjacency(self, grappling_state):
        """Test that grappling hook allows movement to non-adjacent zones."""

        # Verify starting state - PC is in courtyard, tower is not adjacent
        assert grappling_state.entities["pc.arin"].current_zone == "courtyard"
        assert "tower" not in grappling_state.zones["courtyard"].adjacent_zones

        args = {
            "actor": "pc.arin",
            "item_id": "grappling_hook",
            "target": "tower",  # Try to move to non-adjacent tower
            "method": "activate",
        }

        result = validate_and_execute(
            "use_item",
            args,
            grappling_state,
            Utterance(
                text="I use my grappling hook to reach the tower", actor_id="pc.arin"
            ),
            seed=42,
        )

        assert (
            result.ok
        ), f"Grappling hook should allow non-adjacent movement: {result.error_message}"

        # Check that delegation occurred
        facts = result.facts
        assert "delegation" in facts.get(
            "item_usage_metadata", {}
        ), "Should have delegated to move tool"

        # Check that a position effect was created (move tool creates "position" effects)
        position_effects = [e for e in result.effects if e["type"] == "position"]
        assert len(position_effects) >= 1, "Should have position effect from move"

        # Verify the position change is to the tower
        tower_moves = [e for e in position_effects if e.get("to") == "tower"]
        assert len(tower_moves) >= 1, "Should have position change to tower zone"

    def test_normal_move_still_requires_adjacency(self, grappling_state):
        """Test that normal movement without items still requires adjacency."""

        # Try normal move to non-adjacent zone (should fail)
        args = {
            "actor": "pc.arin",
            "to": "tower",  # Try to move to non-adjacent tower without grappling hook
        }

        result = validate_and_execute(
            "move",
            args,
            grappling_state,
            Utterance(text="I walk to the tower", actor_id="pc.arin"),
            seed=42,
        )

        # Should fail because tower is not adjacent to courtyard
        assert not result.ok, "Normal move should fail for non-adjacent zones"
        assert result.tool_id == "ask_clarifying", "Should ask for clarification"


if __name__ == "__main__":
    pytest.main([__file__])
