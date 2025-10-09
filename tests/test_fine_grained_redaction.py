"""
Test suite for Fine-Grained Redaction Policies.

Tests role-based redaction system supporting player/narrator/gm
access levels for different AI contexts.
"""

import sys
import os
import pytest
from typing import Dict, Any

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Clock, Scene, Meta, HP, Entity
from router.visibility import redact_entity, redact_zone, RedactionRole
from router.meta_utils import set_gm_note


class TestRedactionRoles:
    """Test role-based redaction policies."""

    @pytest.fixture
    def role_test_state(self):
        """Create a game state for testing role-based redaction."""
        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            ),
            "hidden_room": Zone(
                id="hidden_room",
                name="Secret Room",
                description="A hidden chamber",
                adjacent_zones=["tavern"],
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        entities: Dict[str, Entity] = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="tavern",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public", gm_only=False),
            ),
            "npc.hidden": NPC(
                id="npc.hidden",
                name="Hidden NPC",
                current_zone="tavern",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="hidden", gm_only=False),
            ),
            "npc.secret": NPC(
                id="npc.secret",
                name="Secret Agent",
                current_zone="tavern",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        # Add GM notes to entities
        set_gm_note(entities["pc.alice"], "Player character with important backstory")
        set_gm_note(entities["npc.hidden"], "Will reveal information if befriended")
        set_gm_note(entities["npc.secret"], "Working for the villain")

        return GameState(entities=entities, zones=zones)

    def test_player_role_redaction(self, role_test_state):
        """Test player role sees appropriate level of information."""
        alice = role_test_state.entities["pc.alice"]
        hidden_npc = role_test_state.entities["npc.hidden"]
        secret_npc = role_test_state.entities["npc.secret"]

        # Player viewing public entity
        alice_view = redact_entity("pc.alice", alice, role_test_state, "player")
        assert alice_view["is_visible"] is True
        assert alice_view["name"] == "Alice"
        assert alice_view["meta"]["notes"] is None  # GM notes hidden

        # Player viewing hidden entity (not in known_by)
        hidden_view = redact_entity("pc.alice", hidden_npc, role_test_state, "player")
        assert hidden_view["is_visible"] is False
        assert hidden_view["name"] == "Unknown"
        assert hidden_view["hp"]["current"] is None

        # Player viewing GM-only entity
        secret_view = redact_entity("pc.alice", secret_npc, role_test_state, "player")
        assert secret_view["is_visible"] is False
        assert secret_view["name"] == "Unknown"

    def test_narrator_role_redaction(self, role_test_state):
        """Test narrator role sees enhanced information for storytelling."""
        alice = role_test_state.entities["pc.alice"]
        hidden_npc = role_test_state.entities["npc.hidden"]
        secret_npc = role_test_state.entities["npc.secret"]

        # Narrator viewing public entity
        alice_view = redact_entity("pc.alice", alice, role_test_state, "narrator")
        assert alice_view["is_visible"] is True
        assert alice_view["name"] == "Alice"
        assert alice_view["meta"]["visibility"] == "public"  # Narrator sees visibility
        assert alice_view["meta"]["notes"] is None  # But not GM notes

        # Narrator viewing hidden entity (partial visibility)
        hidden_view = redact_entity("pc.alice", hidden_npc, role_test_state, "narrator")
        assert hidden_view["is_visible"] is False  # Not visible to player
        assert hidden_view["name"] == "Hidden NPC"  # But narrator knows name
        assert hidden_view["current_zone"] == "tavern"  # And location
        assert hidden_view["meta"]["visibility"] == "hidden"  # And visibility state
        assert (
            hidden_view["hp"]["current"] == -1
        )  # But stats are redacted with type-safe sentinels
        assert hidden_view["meta"]["notes"] is None  # Still no GM notes

        # Narrator viewing GM-only entity (still hidden)
        secret_view = redact_entity("pc.alice", secret_npc, role_test_state, "narrator")
        assert secret_view["is_visible"] is False
        assert secret_view["name"] == "Unknown"  # GM-only stays hidden from narrator

    def test_gm_role_redaction(self, role_test_state):
        """Test GM role sees everything unredacted."""
        alice = role_test_state.entities["pc.alice"]
        hidden_npc = role_test_state.entities["npc.hidden"]
        secret_npc = role_test_state.entities["npc.secret"]

        # GM viewing public entity
        alice_view = redact_entity("pc.alice", alice, role_test_state, "gm")
        assert alice_view["is_visible"] is True
        assert alice_view["name"] == "Alice"
        assert (
            alice_view["meta"]["notes"] == "Player character with important backstory"
        )

        # GM viewing hidden entity
        hidden_view = redact_entity("pc.alice", hidden_npc, role_test_state, "gm")
        assert hidden_view["is_visible"] is True  # GM sees everything
        assert hidden_view["name"] == "Hidden NPC"
        assert hidden_view["hp"]["current"] == 15  # Real stats
        assert hidden_view["meta"]["notes"] == "Will reveal information if befriended"

        # GM viewing GM-only entity
        secret_view = redact_entity("pc.alice", secret_npc, role_test_state, "gm")
        assert secret_view["is_visible"] is True
        assert secret_view["name"] == "Secret Agent"
        assert secret_view["meta"]["notes"] == "Working for the villain"

    def test_zone_role_redaction(self, role_test_state):
        """Test zone redaction respects role-based policies."""
        tavern = role_test_state.zones["tavern"]
        hidden_room = role_test_state.zones["hidden_room"]

        # Player role
        player_tavern = redact_zone("pc.alice", tavern, role_test_state, "player")
        assert player_tavern["is_visible"] is True
        assert player_tavern["name"] == "The Prancing Pony"

        player_hidden = redact_zone("pc.alice", hidden_room, role_test_state, "player")
        assert player_hidden["name"] == "Unknown Area"

        # Narrator role
        narrator_tavern = redact_zone("pc.alice", tavern, role_test_state, "narrator")
        assert narrator_tavern["is_visible"] is True
        assert narrator_tavern["name"] == "The Prancing Pony"

        narrator_hidden = redact_zone(
            "pc.alice", hidden_room, role_test_state, "narrator"
        )
        assert narrator_hidden["name"] == "Unknown Area"  # Still hidden from narrator

        # GM role
        gm_hidden = redact_zone("pc.alice", hidden_room, role_test_state, "gm")
        assert gm_hidden["is_visible"] is True
        assert gm_hidden["name"] == "Secret Room"  # GM sees everything

    def test_game_state_role_integration(self, role_test_state):
        """Test GameState.get_state() with role parameter."""
        # Player state
        player_state = role_test_state.get_state(
            pov_id="pc.alice", redact=True, role="player"
        )

        assert player_state["entities"]["pc.alice"]["is_visible"] is True
        assert player_state["entities"]["npc.hidden"]["is_visible"] is False
        assert player_state["entities"]["npc.secret"]["is_visible"] is False

        # Narrator state
        narrator_state = role_test_state.get_state(
            pov_id="pc.alice", redact=True, role="narrator"
        )

        assert narrator_state["entities"]["pc.alice"]["is_visible"] is True
        assert (
            narrator_state["entities"]["npc.hidden"]["name"] == "Hidden NPC"
        )  # Narrator sees name
        assert (
            narrator_state["entities"]["npc.secret"]["is_visible"] is False
        )  # GM-only still hidden

        # GM state
        gm_state = role_test_state.get_state(pov_id="pc.alice", redact=True, role="gm")

        assert gm_state["entities"]["pc.alice"]["is_visible"] is True
        assert gm_state["entities"]["npc.hidden"]["is_visible"] is True  # GM sees all
        assert gm_state["entities"]["npc.secret"]["is_visible"] is True
        assert gm_state["zones"]["hidden_room"]["name"] == "Secret Room"


class TestNarratorSpecialFeatures:
    """Test narrator-specific redaction features."""

    @pytest.fixture
    def narrator_state(self):
        """Create a state for testing narrator features."""
        entities: Dict[str, Entity] = {
            "npc.bartender": NPC(
                id="npc.bartender",
                name="Suspicious Bartender",
                current_zone="tavern",
                hp=HP(current=8, max=10),
                meta=Meta(visibility="hidden", gm_only=False),
                marks={"nervous": {"value": 2}, "guilty": {"value": 1}},
                guard=3,
            )
        }

        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Tavern",
                description="A dimly lit tavern",
                adjacent_zones=[],
                meta=Meta(visibility="public", gm_only=False),
            )
        }

        return GameState(entities=entities, zones=zones)

    def test_narrator_sees_hidden_entity_context(self, narrator_state):
        """Test that narrator gets contextual info about hidden entities."""
        bartender = narrator_state.entities["npc.bartender"]

        narrator_view = redact_entity(
            "pc.player", bartender, narrator_state, "narrator"
        )

        # Narrator should see basic context
        assert narrator_view["name"] == "Suspicious Bartender"
        assert narrator_view["current_zone"] == "tavern"
        assert narrator_view["meta"]["visibility"] == "hidden"

        # But stats should be redacted with type-safe sentinels
        assert narrator_view["hp"]["current"] == -1
        assert narrator_view["hp"]["max"] == -1
        assert narrator_view["guard"] is None

        # Marks should show count for context
        assert narrator_view["marks"]["hidden_mark_count"] == 2

    def test_narrator_inventory_redaction(self, narrator_state):
        """Test narrator sees inventory placeholder."""
        # Add inventory to entity
        bartender = narrator_state.entities["npc.bartender"]
        bartender.inventory = ["poison_vial", "ledger", "coin_purse"]

        narrator_view = redact_entity(
            "pc.player", bartender, narrator_state, "narrator"
        )

        # Narrator should see empty inventory (type-safe)
        assert narrator_view["inventory"] == []

    def test_player_vs_narrator_comparison(self, narrator_state):
        """Test clear differences between player and narrator views."""
        bartender = narrator_state.entities["npc.bartender"]

        player_view = redact_entity("pc.player", bartender, narrator_state, "player")
        narrator_view = redact_entity(
            "pc.player", bartender, narrator_state, "narrator"
        )

        # Player sees nothing
        assert player_view["name"] == "Unknown"
        assert player_view["current_zone"] is None
        assert player_view["meta"]["visibility"] == "hidden"

        # Narrator sees context
        assert narrator_view["name"] == "Suspicious Bartender"
        assert narrator_view["current_zone"] == "tavern"
        assert narrator_view["meta"]["visibility"] == "hidden"

        # Both hide GM notes
        assert player_view["meta"]["notes"] is None
        assert narrator_view["meta"]["notes"] is None


class TestRoleBasedCaching:
    """Test caching behavior with role-based redaction."""

    @pytest.fixture
    def cache_role_state(self):
        """Create a minimal state for caching tests."""
        entities: Dict[str, Entity] = {
            "pc.test": PC(
                id="pc.test",
                name="Test PC",
                current_zone="room",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public", gm_only=False),
            )
        }

        zones = {
            "room": Zone(
                id="room",
                name="Test Room",
                description="A test room",
                adjacent_zones=[],
                meta=Meta(visibility="public", gm_only=False),
            )
        }

        return GameState(entities=entities, zones=zones)

    def test_caching_only_works_for_player_role(self, cache_role_state):
        """Test that caching is only used for player role."""
        # Clear cache
        cache_role_state.invalidate_cache()

        # Player role should use cache
        player_state = cache_role_state.get_state(
            "pc.test", redact=True, use_cache=True, role="player"
        )
        assert len(cache_role_state._redaction_cache) == 1

        # Clear cache
        cache_role_state.invalidate_cache()

        # Narrator role should not use cache
        narrator_state = cache_role_state.get_state(
            "pc.test", redact=True, use_cache=True, role="narrator"
        )
        assert len(cache_role_state._redaction_cache) == 0

        # Clear cache
        cache_role_state.invalidate_cache()

        # GM role should not use cache
        gm_state = cache_role_state.get_state(
            "pc.test", redact=True, use_cache=True, role="gm"
        )
        assert len(cache_role_state._redaction_cache) == 0

    def test_role_parameter_affects_output(self, cache_role_state):
        """Test that role parameter actually affects the output."""
        # Different roles should produce different outputs
        player_state = cache_role_state.get_state("pc.test", redact=True, role="player")
        narrator_state = cache_role_state.get_state(
            "pc.test", redact=True, role="narrator"
        )
        gm_state = cache_role_state.get_state("pc.test", redact=True, role="gm")

        # All should have the entity visible (it's public)
        assert player_state["entities"]["pc.test"]["is_visible"] is True
        assert narrator_state["entities"]["pc.test"]["is_visible"] is True
        assert gm_state["entities"]["pc.test"]["is_visible"] is True

        # But metadata access should differ (when GM notes exist)
        # This is more obvious with GM notes present
        entity = cache_role_state.entities["pc.test"]
        set_gm_note(entity, "Secret GM information")

        player_state2 = cache_role_state.get_state(
            "pc.test", redact=True, role="player"
        )
        gm_state2 = cache_role_state.get_state("pc.test", redact=True, role="gm")

        # Player should not see GM notes
        assert player_state2["entities"]["pc.test"]["meta"]["notes"] is None

        # GM should see GM notes
        assert (
            gm_state2["entities"]["pc.test"]["meta"]["notes"] == "Secret GM information"
        )
