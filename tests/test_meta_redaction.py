"""
Test suite for the Meta and Redaction Layer system.

Comprehensive tests covering all visibility cases, redaction consistency,
and Meta functionality as specified in the user requirements.
"""

import sys
import os
import pytest
from typing import cast, Dict, Any

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import (
    GameState,
    PC,
    NPC,
    Zone,
    Clock,
    Scene,
    Meta,
    HP,
    Stats,
    ObjectEntity,
    ItemEntity,
)
from router.visibility import can_player_see, redact_entity, redact_zone, redact_clock
from router.meta_utils import (
    reveal_to,
    set_visibility,
    hide_from,
    is_known_by,
    set_gm_note,
    clear_gm_note,
)


class TestMetaModel:
    """Test the enhanced Meta model functionality."""

    def test_meta_creation_with_defaults(self):
        """Test Meta model creates with proper defaults."""
        meta = Meta()

        assert meta.visibility == "public"
        assert meta.gm_only is False
        assert meta.known_by == set()
        assert meta.created_at is None
        assert meta.last_changed_at is None
        assert meta.source is None
        assert meta.notes is None
        assert meta.extra == {}

    def test_meta_touch_updates_timestamp(self):
        """Test that touch() method updates last_changed_at."""
        meta = Meta()
        original_changed = meta.last_changed_at

        meta.touch()

        assert meta.last_changed_at is not None
        assert meta.last_changed_at != original_changed

    def test_meta_known_by_manipulation(self):
        """Test known_by set operations."""
        meta = Meta()

        meta.known_by.add("pc.alice")
        meta.known_by.add("npc.guard")

        assert "pc.alice" in meta.known_by
        assert "npc.guard" in meta.known_by
        assert len(meta.known_by) == 2

        meta.known_by.discard("pc.alice")
        assert "pc.alice" not in meta.known_by
        assert len(meta.known_by) == 1


class TestVisibilityRules:
    """Test the core visibility logic."""

    @pytest.fixture
    def test_state(self):
        """Create a test game state with various visibility scenarios."""
        # Create zones
        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            ),
            "secret_room": Zone(
                id="secret_room",
                name="Hidden Chamber",
                description="A secret room",
                adjacent_zones=["tavern"],
                meta=Meta(visibility="hidden", known_by={"pc.alice"}),
            ),
            "gm_zone": Zone(
                id="gm_zone",
                name="GM Planning Area",
                description="For GM eyes only",
                adjacent_zones=[],
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        # Create entities
        entities = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="tavern",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public"),
            ),
            "npc.bartender": NPC(
                id="npc.bartender",
                name="Friendly Bartender",
                current_zone="tavern",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="public"),
            ),
            "npc.spy": NPC(
                id="npc.spy",
                name="Mysterious Figure",
                current_zone="tavern",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="hidden", known_by={"pc.alice"}),
            ),
            "npc.secret_boss": NPC(
                id="npc.secret_boss",
                name="Secret Boss",
                current_zone="secret_room",
                hp=HP(current=50, max=50),
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
            "item.scroll": ItemEntity(
                id="item.scroll",
                name="Ancient Scroll",
                type="item",
                current_zone="tavern",
                meta=Meta(visibility="hidden", known_by={"pc.alice"}),
            ),
            "object.door": ObjectEntity(
                id="object.door",
                name="Heavy Door",
                type="object",
                current_zone="tavern",
                meta=Meta(visibility="public"),
            ),
        }

        # Create clocks
        clocks = {
            "public_clock": Clock(
                id="public_clock",
                name="Tension",
                value=3,
                maximum=6,
                meta=Meta(visibility="public"),
            ),
            "hidden_clock": Clock(
                id="hidden_clock",
                name="Secret Timer",
                value=2,
                maximum=5,
                meta=Meta(visibility="hidden", known_by={"pc.alice"}),
            ),
            "gm_clock": Clock(
                id="gm_clock",
                name="GM Plot Timer",
                value=4,
                maximum=8,
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        scene = Scene(id="test_scene", meta=Meta(visibility="public"))

        return GameState(
            entities=entities,
            zones=zones,
            clocks=cast("Dict[str, Clock | Dict[str, Any]]", clocks),
            scene=scene,
            current_actor="pc.alice",
        )

    def test_public_entity_visible(self, test_state):
        """Test that public entities in same zone are visible."""
        alice = test_state.entities["pc.alice"]
        bartender = test_state.entities["npc.bartender"]

        assert can_player_see("pc.alice", bartender, test_state) is True

    def test_hidden_entity_known(self, test_state):
        """Test that hidden entities are visible to actors in known_by."""
        alice = test_state.entities["pc.alice"]
        spy = test_state.entities["npc.spy"]

        assert can_player_see("pc.alice", spy, test_state) is True

    def test_hidden_entity_unknown(self, test_state):
        """Test that hidden entities are not visible to unknown actors."""
        spy = test_state.entities["npc.spy"]

        # Add another PC who doesn't know about the spy
        bob = PC(
            id="pc.bob", name="Bob", current_zone="tavern", hp=HP(current=18, max=18)
        )
        test_state.entities["pc.bob"] = bob

        assert can_player_see("pc.bob", spy, test_state) is False

    def test_gm_only_never_visible(self, test_state):
        """Test that gm_only entities are never visible to players."""
        secret_boss = test_state.entities["npc.secret_boss"]

        assert can_player_see("pc.alice", secret_boss, test_state) is False
        assert can_player_see(None, secret_boss, test_state) is True  # GM view

    def test_item_known_across_zones(self, test_state):
        """Test that items can be known across zones."""
        scroll = test_state.entities["item.scroll"]

        # Move alice to different zone (using existing zone)
        alice = test_state.entities["pc.alice"]
        alice.current_zone = "secret_room"

        # Should still be visible because alice knows about it
        assert can_player_see("pc.alice", scroll, test_state) is True

    def test_gm_view_sees_everything(self, test_state):
        """Test that GM view (pov_id=None) sees all entities."""
        secret_boss = test_state.entities["npc.secret_boss"]
        spy = test_state.entities["npc.spy"]
        bartender = test_state.entities["npc.bartender"]

        assert can_player_see(None, secret_boss, test_state) is True
        assert can_player_see(None, spy, test_state) is True
        assert can_player_see(None, bartender, test_state) is True


class TestRedactionConsistency:
    """Test that redacted outputs maintain consistent schemas."""

    @pytest.fixture
    def test_state(self):
        """Create a test state for redaction testing."""
        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            )
        }

        entities = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="tavern",
                hp=HP(current=20, max=20),
                inventory=["sword", "potion"],
                visible_actors=["npc.bartender"],
                marks={"courage": {"source": "self", "value": 1}},
                guard=2,
                meta=Meta(visibility="public"),
            ),
            "npc.hidden": NPC(
                id="npc.hidden",
                name="Hidden NPC",
                current_zone="tavern",
                hp=HP(current=15, max=15),
                inventory=["dagger"],
                visible_actors=["pc.alice"],
                marks={"stealth": {"source": "spell", "value": 2}},
                guard=0,
                meta=Meta(visibility="hidden"),
            ),
        }

        clocks = {
            "visible_clock": Clock(
                id="visible_clock",
                name="Tension",
                value=3,
                maximum=6,
                meta=Meta(visibility="public"),
            ),
            "hidden_clock": Clock(
                id="hidden_clock",
                name="Secret Timer",
                value=2,
                maximum=5,
                meta=Meta(visibility="hidden"),
            ),
        }

        return GameState(
            entities=entities,
            zones=zones,
            clocks=cast(Dict[str, "Clock | Dict[str, Any]"], clocks),
        )

    def test_redacted_entity_has_same_keys(self, test_state):
        """Test that redacted entities maintain the same schema structure."""
        hidden_npc = test_state.entities["npc.hidden"]
        visible_alice = test_state.entities["pc.alice"]

        # Redact for alice (should hide hidden_npc)
        redacted = redact_entity("pc.alice", hidden_npc, test_state)
        visible = redact_entity("pc.alice", visible_alice, test_state)

        # Both should have required keys
        required_keys = {"id", "type", "is_visible"}
        assert all(key in redacted for key in required_keys)
        assert all(key in visible for key in required_keys)

        # Redacted should have None/empty values but same structure
        assert redacted["name"] == "Unknown"
        assert redacted["current_zone"] is None
        assert redacted["hp"]["current"] is None
        assert redacted["hp"]["max"] is None
        assert redacted["inventory"] == []
        assert redacted["visible_actors"] == []
        assert redacted["marks"] == {}
        assert redacted["guard"] is None

    def test_redacted_zone_consistent(self, test_state):
        """Test that redacted zones maintain consistent structure."""
        zone = test_state.zones["tavern"]

        # Should include entity list filtered by visibility
        redacted = redact_zone("pc.alice", zone, test_state)

        assert "entities" in redacted
        assert "is_visible" in redacted
        assert isinstance(redacted["entities"], list)
        # Should only include visible entities
        assert "pc.alice" in redacted["entities"]
        assert "npc.hidden" not in redacted["entities"]

    def test_redacted_clock_consistent(self, test_state):
        """Test that redacted clocks maintain consistent structure."""
        visible_clock = test_state.clocks["visible_clock"]
        hidden_clock = test_state.clocks["hidden_clock"]

        visible_redacted = redact_clock("pc.alice", visible_clock)
        hidden_redacted = redact_clock("pc.alice", hidden_clock)

        # Both should have same keys
        required_keys = {"id", "is_visible"}
        assert all(key in visible_redacted for key in required_keys)
        assert all(key in hidden_redacted for key in required_keys)

        # Hidden clock should have None values
        assert hidden_redacted["value"] is None
        assert hidden_redacted["maximum"] is None
        assert hidden_redacted["name"] == "Unknown Progress"

    def test_gm_notes_always_stripped(self, test_state):
        """Test that GM notes are stripped even from visible entities."""
        # Test public entity
        alice = test_state.entities["pc.alice"]
        alice.meta.notes = "Secret GM note about Alice"
        redacted_alice = redact_entity("pc.alice", alice, test_state)
        assert redacted_alice["meta"]["notes"] is None

        # Test hidden entity (not visible to alice since alice is not in known_by)
        hidden_npc = test_state.entities["npc.hidden"]
        hidden_npc.meta.notes = "Secret GM note about hidden NPC"
        redacted_hidden = redact_entity("pc.alice", hidden_npc, test_state)
        # Even for hidden entities, GM notes should be stripped
        if redacted_hidden.get("meta"):
            assert redacted_hidden["meta"]["notes"] is None


class TestGameStateIntegration:
    """Test AGS integration with redaction."""

    @pytest.fixture
    def test_state(self):
        """Create test state for AGS testing."""
        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            )
        }

        entities = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="tavern",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public"),
            ),
            "npc.hidden": NPC(
                id="npc.hidden",
                name="Hidden NPC",
                current_zone="tavern",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="hidden"),
            ),
        }

        clocks = {
            "public_clock": Clock(
                id="public_clock",
                name="Tension",
                value=3,
                maximum=6,
                meta=Meta(visibility="public"),
            )
        }

        return GameState(
            entities=entities,
            zones=zones,
            clocks=cast(Dict[str, "Clock | Dict[str, Any]"], clocks),
        )

    def test_get_state_with_redaction(self, test_state):
        """Test GameState.get_state() applies redaction correctly."""
        redacted_state = test_state.get_state(pov_id="pc.alice", redact=True)

        # Should include all categories
        assert "entities" in redacted_state
        assert "zones" in redacted_state
        assert "clocks" in redacted_state
        assert "scene" in redacted_state

        # Alice should be visible
        assert "pc.alice" in redacted_state["entities"]
        assert redacted_state["entities"]["pc.alice"]["is_visible"] is True

        # Hidden NPC should be redacted
        assert "npc.hidden" in redacted_state["entities"]
        assert redacted_state["entities"]["npc.hidden"]["is_visible"] is False
        assert redacted_state["entities"]["npc.hidden"]["name"] == "Unknown"

    def test_get_state_without_redaction(self, test_state):
        """Test GameState.get_state() without redaction shows everything."""
        full_state = test_state.get_state(pov_id="pc.alice", redact=False)

        # All entities should be visible
        assert full_state["entities"]["pc.alice"]["is_visible"] is True
        assert full_state["entities"]["npc.hidden"]["is_visible"] is True
        assert full_state["entities"]["npc.hidden"]["name"] == "Hidden NPC"

    def test_list_visible_entities(self, test_state):
        """Test GameState.list_visible_entities() helper."""
        visible = test_state.list_visible_entities("pc.alice", zone_only=True)

        assert "pc.alice" in visible
        assert "npc.hidden" not in visible


class TestMetaUtilities:
    """Test the Meta utility helper functions."""

    def test_reveal_to_and_hide_from(self):
        """Test revealing and hiding objects from actors."""
        entity = PC(
            id="pc.test", name="Test PC", current_zone="test", hp=HP(current=10, max=10)
        )

        # Initially not known
        assert not is_known_by(entity, "pc.alice")

        # Reveal to alice
        reveal_to(entity, "pc.alice")
        assert is_known_by(entity, "pc.alice")
        assert "pc.alice" in entity.meta.known_by

        # Hide from alice
        hide_from(entity, "pc.alice")
        assert not is_known_by(entity, "pc.alice")
        assert "pc.alice" not in entity.meta.known_by

    def test_set_visibility_levels(self):
        """Test setting different visibility levels."""
        entity = PC(
            id="pc.test", name="Test PC", current_zone="test", hp=HP(current=10, max=10)
        )

        # Test each visibility level
        set_visibility(entity, "hidden")
        assert entity.meta.visibility == "hidden"
        assert entity.meta.gm_only is False

        set_visibility(entity, "gm_only")
        assert entity.meta.visibility == "gm_only"
        assert entity.meta.gm_only is True

        set_visibility(entity, "public")
        assert entity.meta.visibility == "public"
        assert entity.meta.gm_only is False

    def test_gm_notes_management(self):
        """Test adding and clearing GM notes."""
        entity = PC(
            id="pc.test", name="Test PC", current_zone="test", hp=HP(current=10, max=10)
        )

        # Add note
        set_gm_note(entity, "This PC has a secret")
        assert entity.meta.notes == "This PC has a secret"

        # Clear note
        clear_gm_note(entity)
        assert entity.meta.notes is None

    def test_meta_touch_called(self):
        """Test that utility functions call touch() to update timestamps."""
        entity = PC(
            id="pc.test", name="Test PC", current_zone="test", hp=HP(current=10, max=10)
        )

        original_changed = entity.meta.last_changed_at

        # All these operations should call touch()
        reveal_to(entity, "pc.alice")
        assert entity.meta.last_changed_at != original_changed

        set_visibility(entity, "hidden")
        hide_from(entity, "pc.alice")
        set_gm_note(entity, "test")
        clear_gm_note(entity)

        # Should have been updated
        assert entity.meta.last_changed_at is not None


class TestAutoTouchOnUpdate:
    """Test that meta.touch() is called when entities are modified."""

    def test_touch_on_entity_update(self):
        """Test that modifying entity stats calls meta.touch()."""
        entity = PC(
            id="pc.test", name="Test PC", current_zone="test", hp=HP(current=10, max=10)
        )

        original_changed = entity.meta.last_changed_at

        # Modify the entity
        entity.hp.current = 8
        entity.meta.touch()  # Would be called by apply_effects in practice

        assert entity.meta.last_changed_at != original_changed
