"""
Test script for the get_info tool.

Tests the complete get_info implementation including all topics,
detail levels, error conditions, and edge cases as specified.
"""

import sys
import os
import pytest

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import (
    GameState,
    PC,
    NPC,
    Zone,
    HP,
    Utterance,
    Scene,
    ObjectEntity,
    ItemEntity,
    Meta,
)
from router.validator import validate_and_execute


@pytest.fixture
def get_info_state():
    """Create a rich game state for get_info testing."""

    # Create zones
    zones = {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard with a fountain.",
            adjacent_zones=["hall", "garden"],
        ),
        "hall": Zone(
            id="hall",
            name="Great Hall",
            description="A large hall with tapestries.",
            adjacent_zones=["courtyard", "kitchen"],
        ),
        "garden": Zone(
            id="garden",
            name="Garden",
            description="A peaceful garden.",
            adjacent_zones=["courtyard"],
        ),
    }

    # Create entities with rich data
    entities = {
        "pc.arin": PC(
            id="pc.arin",
            name="Arin",
            type="pc",
            current_zone="courtyard",
            hp=HP(current=17, max=20),
            visible_actors=["npc.guard", "npc.cat"],
            inventory=[
                "healing_potion",
                "rope",
                "healing_potion",
            ],  # Duplicate for testing
            marks={
                "npc.guard.favor": {
                    "tag": "favor",
                    "source": "npc.guard",
                    "value": 1,
                    "consumes": True,
                    "created_turn": 1,
                }
            },
            tags={"stealthed": True, "blessed": "divine"},
            guard=2,
            guard_duration=1,
        ),
        "npc.guard": NPC(
            id="npc.guard",
            name="Guard Captain",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=25, max=25),
            visible_actors=["pc.arin", "npc.cat"],
            inventory=["sword", "shield"],
            marks={},
            tags={},
        ),
        "npc.cat": NPC(
            id="npc.cat",
            name="Fluffy",
            type="npc",
            current_zone="courtyard",
            hp=HP(current=5, max=5),
            visible_actors=["pc.arin", "npc.guard"],
            inventory=[],
            marks={},
            tags={"cute": True},
        ),
        "obj.fountain": ObjectEntity(
            id="obj.fountain",
            name="Stone Fountain",
            type="object",
            current_zone="courtyard",
            description="A beautiful stone fountain.",
            interactable=True,
            locked=False,
            tags={"magical": "water"},
        ),
        "item.gem": ItemEntity(
            id="item.gem",
            name="Ruby Gem",
            type="item",
            current_zone="hall",
            description="A precious ruby gem.",
            weight=0.1,
            value=100,
            tags={"precious": True},
        ),
    }

    # Create scene with rich tags
    scene = Scene(
        id="test_scene",
        turn_order=["pc.arin", "npc.guard"],
        turn_index=0,
        round=3,
        base_dc=12,
        tags={"alert": "wary", "lighting": "dim", "noise": "quiet", "cover": "some"},
        objective={"type": "infiltrate", "target": "hall"},
    )

    # Create game state with clocks
    state = GameState(
        entities=entities,
        zones=zones,
        scene=scene,
        current_actor="pc.arin",
        clocks={
            "stealth_detection": {
                "value": 2,
                "max": 5,
                "min": 0,
                "source": "pc.arin",
                "created_turn": 1,
                "last_modified_turn": 2,
                "last_modified_by": "npc.guard",
            },
            "guard_patrol": {
                "value": 4,
                "max": 6,
                "min": 0,
                "source": "npc.guard",
                "created_turn": 1,
                "last_modified_turn": 3,
                "last_modified_by": "system",
                "filled_this_turn": False,
            },
        },
    )

    return state


class TestGetInfoStatus:
    """Test get_info with topic='status'."""

    def test_status_self_brief(self, get_info_state):
        """Test getting brief status info about self."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.tool_id == "get_info"
        assert result.facts["topic"] == "status"
        assert result.facts["entity_id"] == "pc.arin"
        assert result.facts["hp"] == 17
        assert result.facts["max_hp"] == 20
        assert result.facts["guard"] == 2
        assert "npc.guard.favor" in result.facts["marks"]
        assert "stealthed" in result.facts["tags"]
        assert result.facts["position"] == "courtyard"

    def test_status_other_entity(self, get_info_state):
        """Test getting status info about another entity."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "npc.guard",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check guard status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["entity_id"] == "npc.guard"
        assert result.facts["hp"] == 25
        assert result.facts["max_hp"] == 25
        assert result.facts["name"] == "Guard Captain"

    def test_status_full_detail(self, get_info_state):
        """Test getting full status details."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="full status check", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "stats" in result.facts
        assert "conditions" in result.facts
        assert result.facts["stats"]["strength"] == 10  # Default value

    def test_status_object_entity(self, get_info_state):
        """Test getting status info about an object."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "obj.fountain",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check fountain", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["entity_type"] == "object"
        assert result.facts["interactable"] is True
        assert result.facts["locked"] is False

    def test_status_item_entity(self, get_info_state):
        """Test getting status info about an item."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "item.gem",
                "topic": "status",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="examine gem", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["entity_type"] == "item"
        assert result.facts["weight"] == 0.1
        assert result.facts["value"] == 100
        assert "description" in result.facts


class TestGetInfoInventory:
    """Test get_info with topic='inventory'."""

    def test_inventory_brief(self, get_info_state):
        """Test getting brief inventory info."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "inventory",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check inventory", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "inventory"
        assert result.facts["item_count"] == 3
        assert "healing_potion" in result.facts["items"]
        assert "rope" in result.facts["items"]

    def test_inventory_full_detail(self, get_info_state):
        """Test getting full inventory details."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "inventory",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="detailed inventory", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "item_details" in result.facts
        # Should show healing_potion count as 2
        assert result.facts["item_details"]["healing_potion"]["count"] == 2
        assert result.facts["item_details"]["rope"]["count"] == 1

    def test_inventory_empty(self, get_info_state):
        """Test getting inventory of entity with no items."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "npc.cat",
                "topic": "inventory",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check cat inventory", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["item_count"] == 0
        assert result.facts["items"] == []

    def test_inventory_non_creature(self, get_info_state):
        """Test getting inventory of non-creature entity should fail."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "obj.fountain",
                "topic": "inventory",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check fountain inventory", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is False
        assert result.error_message is not None
        assert "does not have inventory" in result.error_message


class TestGetInfoZone:
    """Test get_info with topic='zone'."""

    def test_zone_current_brief(self, get_info_state):
        """Test getting brief zone info for current zone."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",  # Should resolve to their zone
                "topic": "zone",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="look around", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "zone"
        assert result.facts["zone_id"] == "courtyard"
        assert result.facts["name"] == "Courtyard"
        assert result.facts["entity_count"] == 4  # arin, guard, cat, fountain
        assert "pc.arin" in result.facts["entities"]
        assert "npc.guard" in result.facts["entities"]
        assert "obj.fountain" in result.facts["entities"]

    def test_zone_direct_id(self, get_info_state):
        """Test getting zone info by zone ID."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "hall",
                "topic": "zone",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check hall", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["zone_id"] == "hall"
        assert result.facts["name"] == "Great Hall"
        assert "item.gem" in result.facts["entities"]

    def test_zone_full_detail(self, get_info_state):
        """Test getting full zone details."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "courtyard",
                "topic": "zone",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="detailed zone info", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "description" in result.facts
        assert "entity_details" in result.facts
        assert result.facts["entity_details"]["pc.arin"]["name"] == "Arin"
        assert result.facts["entity_details"]["pc.arin"]["type"] == "pc"


class TestGetInfoScene:
    """Test get_info with topic='scene'."""

    def test_scene_brief(self, get_info_state):
        """Test getting brief scene info."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "scene", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check scene", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "scene"
        assert result.facts["round"] == 3
        assert result.facts["base_dc"] == 12
        assert result.facts["tags"]["alert"] == "wary"
        assert result.facts["tags"]["lighting"] == "dim"

    def test_scene_full_detail(self, get_info_state):
        """Test getting full scene details."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "scene", "detail_level": "full"},
            get_info_state,
            Utterance(text="detailed scene", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "turn_order" in result.facts
        assert "objective" in result.facts
        assert result.facts["objective"]["type"] == "infiltrate"


class TestGetInfoEffects:
    """Test get_info with topic='effects'."""

    def test_effects_with_active_effects(self, get_info_state):
        """Test getting effects info for entity with active effects."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "effects",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check effects", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "effects"
        assert len(result.facts["active_effects"]) > 0

        # Should have guard effect
        guard_effects = [
            e for e in result.facts["active_effects"] if e["type"] == "guard"
        ]
        assert len(guard_effects) == 1
        assert guard_effects[0]["value"] == 2

        # Should have mark effects
        mark_effects = [
            e for e in result.facts["active_effects"] if e["type"] == "mark"
        ]
        assert len(mark_effects) == 1
        assert mark_effects[0]["tag"] == "favor"

        # Should have tag effects
        tag_effects = [e for e in result.facts["active_effects"] if e["type"] == "tag"]
        assert len(tag_effects) >= 2  # stealthed and blessed

    def test_effects_no_effects(self, get_info_state):
        """Test getting effects info for entity with no effects."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "npc.guard",
                "topic": "effects",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check guard effects", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["active_effects"] == []


class TestGetInfoClocks:
    """Test get_info with topic='clocks'."""

    def test_clocks_brief(self, get_info_state):
        """Test getting brief clocks info."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "clocks", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check clocks", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "clocks"
        assert result.facts["clock_count"] == 2
        assert "stealth_detection" in result.facts["active_clocks"]
        assert "guard_patrol" in result.facts["active_clocks"]
        assert result.facts["active_clocks"]["stealth_detection"]["value"] == 2

    def test_clocks_full_detail(self, get_info_state):
        """Test getting full clocks details."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "clocks", "detail_level": "full"},
            get_info_state,
            Utterance(text="detailed clocks", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        clock_data = result.facts["active_clocks"]["stealth_detection"]
        assert "source" in clock_data
        assert "created_turn" in clock_data
        assert "last_modified_turn" in clock_data
        assert clock_data["source"] == "pc.arin"

    def test_clocks_empty(self):
        """Test getting clocks info when no clocks exist."""
        # Create minimal state with no clocks
        minimal_state = GameState(
            entities={"pc.test": PC(id="pc.test", name="Test", current_zone="test")},
            zones={
                "test": Zone(
                    id="test", name="Test", description="Test", adjacent_zones=[]
                )
            },
            current_actor="pc.test",
            clocks={},
        )

        result = validate_and_execute(
            "get_info",
            {"actor": "pc.test", "topic": "clocks", "detail_level": "brief"},
            minimal_state,
            Utterance(text="check clocks", actor_id="pc.test"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["clock_count"] == 0
        assert result.facts["active_clocks"] == {}


class TestGetInfoRelationships:
    """Test get_info with topic='relationships'."""

    def test_relationships_with_marks(self, get_info_state):
        """Test getting relationships info for entity with marks."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "relationships",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check relationships", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "relationships"
        assert "npc.guard" in result.facts["relationships"]
        assert len(result.facts["relationships"]["npc.guard"]) == 1
        assert result.facts["relationships"]["npc.guard"][0]["tag"] == "favor"

    def test_relationships_no_marks(self, get_info_state):
        """Test getting relationships info for entity with no marks."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "npc.guard",
                "topic": "relationships",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check guard relationships", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["relationships"] == {}

    def test_relationships_full_detail(self, get_info_state):
        """Test getting full relationships details."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "relationships",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="detailed relationships", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        relationship = result.facts["relationships"]["npc.guard"][0]
        assert "created_turn" in relationship
        assert "consumes" in relationship
        assert relationship["created_turn"] == 1


class TestGetInfoRules:
    """Test get_info with topic='rules'."""

    def test_rules_brief(self, get_info_state):
        """Test getting brief rules info."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "rules", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check rules", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["topic"] == "rules"
        assert result.facts["base_dc"] == 12
        assert result.facts["current_round"] == 3

    def test_rules_full_detail(self, get_info_state):
        """Test getting full rules details."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "rules", "detail_level": "full"},
            get_info_state,
            Utterance(text="detailed rules", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "dc_ranges" in result.facts
        assert "outcomes" in result.facts
        assert "style_domains" in result.facts
        assert "scene_tags" in result.facts
        assert result.facts["dc_ranges"]["moderate"] == "12-14"
        assert result.facts["outcomes"]["success"] == "Margin >= 0"


class TestGetInfoErrorCases:
    """Test get_info error handling and edge cases."""

    def test_no_context(self, get_info_state):
        """Test get_info with no valid context should ask for clarification."""
        result = validate_and_execute(
            "get_info",
            {"actor": None, "target": None, "topic": "status", "detail_level": "brief"},
            get_info_state,
            Utterance(text="get info", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is False
        assert result.tool_id == "ask_clarifying"
        assert (
            "Who or what would you like to get information about?"
            in result.args["question"]
        )

    def test_invalid_target(self, get_info_state):
        """Test get_info with invalid target should ask for clarification."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "nonexistent.entity",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check something", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is False
        assert result.tool_id == "ask_clarifying"
        assert "nonexistent.entity" in result.args["question"]

    def test_unknown_topic(self, get_info_state):
        """Test get_info with unknown topic should be caught by schema validation."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "unknown_topic",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check unknown", actor_id="pc.arin"),
            seed=42,
        )

        # Schema validation should catch invalid topic and return ask_clarifying
        assert result.ok is False
        assert result.tool_id == "ask_clarifying"

    def test_default_to_actor(self, get_info_state):
        """Test that target defaults to actor when not specified."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": None,  # Should default to actor
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["entity_id"] == "pc.arin"

    def test_read_only_no_effects(self, get_info_state):
        """Test that get_info returns no effects (read-only)."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.effects == []  # Read-only tool should have no effects

    def test_narration_hints(self, get_info_state):
        """Test that appropriate narration hints are provided."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert "informative" in result.narration_hint["tone_tags"]
        assert "status" in result.narration_hint["tone_tags"]
        assert result.narration_hint["sentences_max"] == 2  # Brief mode
        assert result.narration_hint["salient_entities"] == ["pc.arin"]

    def test_full_detail_narration(self, get_info_state):
        """Test that full detail mode affects narration hints."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="detailed status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.narration_hint["sentences_max"] == 4  # Full mode


class TestMetaSystem:
    """Test the Meta submodel system and default behavior."""

    def test_meta_defaults(self):
        """Test that Meta objects are created with proper defaults."""
        # Test PC with default meta
        pc = PC(id="pc.test", name="Test PC", current_zone="test")
        assert pc.meta.visibility == "public"
        assert pc.meta.created_at is None
        assert pc.meta.extra == {}

        # Test Zone with default meta
        zone = Zone(id="test", name="Test Zone", description="Test", adjacent_zones=[])
        assert zone.meta.visibility == "public"

        # Test Scene with default meta
        scene = Scene()
        assert scene.meta.visibility == "public"

    def test_meta_custom_values(self):
        """Test setting custom meta values."""
        meta = Meta(
            visibility="gm_only",
            created_at="2025-10-04T21:00:00Z",
            source="manual",
            notes="Test entity",
            extra={"custom_field": "value"},
        )

        pc = PC(id="pc.secret", name="Secret PC", current_zone="test", meta=meta)

        assert pc.meta.visibility == "gm_only"
        assert pc.meta.created_at == "2025-10-04T21:00:00Z"
        assert pc.meta.source == "manual"
        assert pc.meta.notes == "Test entity"
        assert pc.meta.extra["custom_field"] == "value"

    def test_meta_serialization(self):
        """Test that Meta objects serialize and deserialize correctly."""
        pc = PC(
            id="pc.test",
            name="Test PC",
            current_zone="test",
            meta=Meta(visibility="gm_only", notes="Secret character"),
        )

        # Test model_dump (new Pydantic method)
        data = pc.model_dump()
        assert data["meta"]["visibility"] == "gm_only"
        assert data["meta"]["notes"] == "Secret character"

        # Test reconstruction from data
        pc_rebuilt = PC(**data)
        assert pc_rebuilt.meta.visibility == "gm_only"
        assert pc_rebuilt.meta.notes == "Secret character"


class TestPerceptionGuards:
    """Test perception guards and visibility system."""

    @pytest.fixture
    def perception_state(self):
        """Create a game state with mixed visible/hidden content."""

        # Create zones - one hidden, one visible
        zones = {
            "public_room": Zone(
                id="public_room",
                name="Public Room",
                description="A visible room.",
                adjacent_zones=["secret_room"],
                meta=Meta(visibility="public"),
            ),
            "secret_room": Zone(
                id="secret_room",
                name="Secret Room",
                description="A hidden room.",
                adjacent_zones=["public_room"],
                meta=Meta(visibility="gm_only"),
            ),
        }

        # Create entities with mixed visibility
        entities = {
            "pc.player": PC(
                id="pc.player",
                name="Player",
                type="pc",
                current_zone="public_room",
                hp=HP(current=20, max=20),
                visible_actors=["npc.visible", "npc.hidden"],
                meta=Meta(visibility="public"),
            ),
            "npc.visible": NPC(
                id="npc.visible",
                name="Visible NPC",
                type="npc",
                current_zone="public_room",
                hp=HP(current=15, max=15),
                visible_actors=["pc.player"],
                meta=Meta(visibility="public"),
            ),
            "npc.hidden": NPC(
                id="npc.hidden",
                name="Hidden NPC",
                type="npc",
                current_zone="public_room",
                hp=HP(current=10, max=10),
                visible_actors=["pc.player"],
                meta=Meta(visibility="hidden"),
            ),
            "npc.gm_only": NPC(
                id="npc.gm_only",
                name="GM Only NPC",
                type="npc",
                current_zone="public_room",
                hp=HP(current=25, max=25),
                visible_actors=["pc.player"],
                meta=Meta(visibility="gm_only"),
            ),
        }

        # Create scene
        scene = Scene(id="perception_test", meta=Meta(visibility="public"))

        # Create game state with mixed visible/hidden clocks
        state = GameState(
            entities=entities,
            zones=zones,
            scene=scene,
            current_actor="pc.player",
            clocks={
                "visible_clock": {
                    "value": 3,
                    "max": 5,
                    "meta": {"gm_only": False, "visibility": "public"},
                },
                "hidden_clock": {
                    "value": 2,
                    "max": 4,
                    "meta": {"gm_only": False, "visibility": "hidden"},
                },
                "gm_clock": {
                    "value": 1,
                    "max": 3,
                    "meta": {"gm_only": True, "visibility": "gm_only"},
                },
            },
        )

        return state

    def test_zone_visibility_filtering(self, perception_state):
        """Test that hidden entities are filtered from zone info."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "public_room",
                "topic": "zone",
                "detail_level": "brief",
            },
            perception_state,
            Utterance(text="look around", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only see visible entities
        assert "pc.player" in facts["entities"]
        assert "npc.visible" in facts["entities"]
        assert "npc.hidden" not in facts["entities"]
        assert "npc.gm_only" not in facts["entities"]

        # Entity count should reflect only visible entities
        assert facts["entity_count"] == 2

        # Summary should mention hidden entities
        assert (
            "hidden" in result.narration_hint["summary"]
            or "+2 hidden" in result.narration_hint["summary"]
        )

    def test_hidden_zone_redaction(self, perception_state):
        """Test that GM-only zones are redacted."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "secret_room",
                "topic": "zone",
                "detail_level": "brief",
            },
            perception_state,
            Utterance(text="check secret room", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Zone should be redacted
        assert facts["name"] == "[hidden]"
        assert facts["entities"] == []
        assert facts["entity_count"] == 0
        assert facts["adjacent_zones"] == []

    def test_clock_visibility_filtering(self, perception_state):
        """Test that hidden clocks are filtered or redacted."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.player", "topic": "clocks", "detail_level": "brief"},
            perception_state,
            Utterance(text="check clocks", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only see visible clocks
        assert "visible_clock" in facts["active_clocks"]
        assert "hidden_clock" not in facts["active_clocks"]
        assert "gm_clock" not in facts["active_clocks"]

        # Clock count should reflect only visible clocks
        assert facts["clock_count"] == 1

        # Should have redacted placeholders for hidden clocks
        hidden_placeholders = [
            k for k in facts["active_clocks"].keys() if k.startswith("[hidden_clock_")
        ]
        assert len(hidden_placeholders) == 2  # For hidden_clock and gm_clock

    def test_entity_status_visibility(self, perception_state):
        """Test that hidden entities can't be inspected."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "npc.hidden",
                "topic": "status",
                "detail_level": "brief",
            },
            perception_state,
            Utterance(text="check hidden npc", actor_id="pc.player"),
            seed=42,
        )

        # Should fail with clarification since entity is not visible
        assert result.ok is False
        assert result.tool_id == "ask_clarifying"
        assert "npc.hidden" in result.args["question"]

    def test_gm_mode_bypass(self):
        """Test that GM mode would bypass visibility restrictions (future feature)."""
        # This is a placeholder for when GM mode is implemented
        # For now, just ensure the visibility system is working as expected
        pass

    def test_visibility_helpers(self):
        """Test the visibility helper functions directly."""
        from router.game_state import (
            is_visible_to,
            is_zone_visible_to,
            is_clock_visible_to,
            Meta,
        )

        # Test entity visibility
        visible_entity = PC(
            id="pc.visible",
            name="Visible",
            current_zone="test",
            meta=Meta(visibility="public"),
        )
        hidden_entity = PC(
            id="pc.hidden",
            name="Hidden",
            current_zone="test",
            meta=Meta(visibility="hidden"),
        )
        gm_entity = PC(
            id="pc.gm",
            name="GM Only",
            current_zone="test",
            meta=Meta(visibility="gm_only"),
        )

        assert is_visible_to(visible_entity) is True
        assert is_visible_to(hidden_entity) is False
        assert is_visible_to(gm_entity) is False

        # Test zone visibility
        visible_zone = Zone(
            id="public",
            name="Public",
            description="",
            adjacent_zones=[],
            meta=Meta(visibility="public"),
        )
        hidden_zone = Zone(
            id="secret",
            name="Secret",
            description="",
            adjacent_zones=[],
            meta=Meta(visibility="gm_only"),
        )

        assert is_zone_visible_to(visible_zone) is True
        assert is_zone_visible_to(hidden_zone) is False

        # Test clock visibility
        visible_clock = {
            "value": 1,
            "max": 5,
            "meta": {"visibility": "public"},
        }
        hidden_clock = {
            "value": 2,
            "max": 5,
            "meta": {"visibility": "gm_only"},
        }

        assert is_clock_visible_to(visible_clock) is True
        assert is_clock_visible_to(hidden_clock) is False


class TestBackwardCompatibility:
    """Test that existing functionality still works with Meta system."""

    def test_existing_tests_still_pass(self, get_info_state):
        """Test that the original get_info functionality still works."""
        # This should work exactly as before since entities have default meta
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        assert result.facts["entity_id"] == "pc.arin"
        assert result.facts["hp"] == 17

    def test_meta_absent_in_legacy_data(self):
        """Test handling of entities without meta fields."""
        # Create entity data without meta (simulating legacy saves)
        legacy_data = {
            "id": "pc.legacy",
            "name": "Legacy PC",
            "type": "pc",
            "current_zone": "test",
            "hp": {"current": 20, "max": 20},
            "stats": {
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
            },
            "visible_actors": [],
            "inventory": [],
            "marks": {},
            "tags": {},
        }

        # Should create with default meta
        pc = PC(**legacy_data)
        assert pc.meta.visibility == "public"


class TestDeterministicOrdering:
    """Test deterministic ordering and stable IDs."""

    @pytest.fixture
    def ordering_state(self):
        """Create a game state with multiple entities to test ordering."""

        zones = {
            "test_zone": Zone(
                id="test_zone",
                name="Test Zone",
                description="Test zone for ordering.",
                adjacent_zones=["zone_b", "zone_a", "zone_c"],  # Unsorted
            ),
        }

        # Create entities with names that would sort differently than IDs
        entities = {
            "pc.charlie": PC(
                id="pc.charlie",
                name="Charlie",  # C
                type="pc",
                current_zone="test_zone",
                hp=HP(current=15, max=20),
                visible_actors=[],
                inventory=["sword", "apple", "potion", "bow"],  # Unsorted
            ),
            "npc.alice": NPC(
                id="npc.alice",
                name="Alice",  # A (should come before Charlie by name)
                type="npc",
                current_zone="test_zone",
                hp=HP(current=10, max=10),
                visible_actors=[],
            ),
            "object.box": ObjectEntity(
                id="object.box",
                name="Box",  # B
                type="object",
                current_zone="test_zone",
                interactable=True,
            ),
            "pc.bob": PC(
                id="pc.bob",
                name="Bob",  # B (same as Box, should sort by type then name)
                type="pc",
                current_zone="test_zone",
                hp=HP(current=20, max=20),
                visible_actors=[],
                inventory=[],
            ),
        }

        state = GameState(
            entities=entities,
            zones=zones,
            current_actor="pc.charlie",
            clocks={
                "clock_z": {"value": 1, "max": 5},
                "clock_a": {"value": 2, "max": 5},
                "clock_m": {"value": 3, "max": 5},
            },
        )

        return state

    def test_entity_sorting_in_zone(self, ordering_state):
        """Test that entities in zone are sorted by (type, name, id)."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "brief",
            },
            ordering_state,
            Utterance(text="look around", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        entities = result.facts["entities"]

        # Expected order: npc.alice (npc, Alice), object.box (object, Box), pc.bob (pc, Bob), pc.charlie (pc, Charlie)
        expected_order = ["npc.alice", "object.box", "pc.bob", "pc.charlie"]
        assert entities == expected_order

    def test_adjacent_zones_sorted(self, ordering_state):
        """Test that adjacent zones are sorted alphabetically."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "brief",
            },
            ordering_state,
            Utterance(text="look around", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        adjacent_zones = result.facts["adjacent_zones"]

        # Should be sorted alphabetically
        expected_order = ["zone_a", "zone_b", "zone_c"]
        assert adjacent_zones == expected_order

    def test_clocks_sorted_by_id(self, ordering_state):
        """Test that clocks are sorted by ID."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.charlie", "topic": "clocks", "detail_level": "brief"},
            ordering_state,
            Utterance(text="check clocks", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        clocks = result.facts["active_clocks"]

        # Should be sorted by clock ID
        expected_order = ["clock_a", "clock_m", "clock_z"]
        assert list(clocks.keys()) == expected_order

    def test_inventory_sorted(self, ordering_state):
        """Test that inventory items are sorted."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "pc.charlie",
                "topic": "inventory",
                "detail_level": "brief",
            },
            ordering_state,
            Utterance(text="check my inventory", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        items = result.facts["items"]

        # Should be sorted alphabetically
        expected_order = ["apple", "bow", "potion", "sword"]
        assert items == expected_order

    def test_id_name_format_consistency(self, ordering_state):
        """Test that entities include both ID and name consistently."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "full",
            },
            ordering_state,
            Utterance(text="examine zone", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        entity_details = result.facts["entity_details"]

        # Check that each entity has both id and name
        for entity_id, details in entity_details.items():
            assert "id" in details
            assert "name" in details
            assert "type" in details
            assert details["id"] == entity_id

    def test_status_includes_id(self, ordering_state):
        """Test that status includes entity ID."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "pc.charlie",
                "topic": "status",
                "detail_level": "brief",
            },
            ordering_state,
            Utterance(text="check my status", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should include both entity_id and id fields
        assert facts["entity_id"] == "pc.charlie"
        assert facts["id"] == "pc.charlie"
        assert facts["name"] == "Charlie"

    def test_clock_includes_id(self, ordering_state):
        """Test that clocks include their ID."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.charlie", "topic": "clocks", "detail_level": "full"},
            ordering_state,
            Utterance(text="check clocks", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        clocks = result.facts["active_clocks"]

        # Each clock should include its ID
        for clock_id, clock_data in clocks.items():
            assert clock_data["id"] == clock_id

    def test_inventory_full_includes_id(self, ordering_state):
        """Test that full inventory details include item IDs."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.charlie",
                "target": "pc.charlie",
                "topic": "inventory",
                "detail_level": "full",
            },
            ordering_state,
            Utterance(text="examine my inventory", actor_id="pc.charlie"),
            seed=42,
        )

        assert result.ok is True
        if "item_details" in result.facts:
            item_details = result.facts["item_details"]

            # Each item should include its ID
            for item_id, item_data in item_details.items():
                assert item_data["id"] == item_id

    def test_reproducible_output(self, ordering_state):
        """Test that identical states produce identical output (excluding non-deterministic metadata)."""
        args = {
            "actor": "pc.charlie",
            "target": "test_zone",
            "topic": "zone",
            "detail_level": "full",
        }
        utterance = Utterance(text="look around", actor_id="pc.charlie")

        # Run the same query twice
        result1 = validate_and_execute(
            "get_info", args, ordering_state, utterance, seed=42
        )
        result2 = validate_and_execute(
            "get_info", args, ordering_state, utterance, seed=42
        )

        # Extract facts without non-deterministic metadata
        facts1 = result1.facts.copy()
        facts2 = result2.facts.copy()

        # Remove non-deterministic metadata fields but preserve deterministic ones
        if "_metadata" in facts1:
            metadata1 = facts1["_metadata"].copy()
            metadata2 = facts2["_metadata"].copy()

            # Remove non-deterministic fields
            for field in ["query_id", "timestamp"]:
                metadata1.pop(field, None)
                metadata2.pop(field, None)

            facts1["_metadata"] = metadata1
            facts2["_metadata"] = metadata2

        # Results should be identical after removing non-deterministic fields
        assert facts1 == facts2
        assert result1.narration_hint == result2.narration_hint

        # But the query IDs should be different (timestamps might be same due to speed)
        if "_metadata" in result1.facts and "_metadata" in result2.facts:
            assert (
                result1.facts["_metadata"]["query_id"]
                != result2.facts["_metadata"]["query_id"]
            )

            # Deterministic fields should be the same
            assert (
                result1.facts["_metadata"]["snapshot_id"]
                == result2.facts["_metadata"]["snapshot_id"]
            )
            assert (
                result1.facts["_metadata"]["turn_id"]
                == result2.facts["_metadata"]["turn_id"]
            )


class TestSizeControl:
    """Test size control features: pagination and field projection."""

    @pytest.fixture
    def large_state(self):
        """Create a game state with many items for pagination testing."""

        zones = {
            "test_zone": Zone(
                id="test_zone",
                name="Test Zone",
                description="Test zone with many entities.",
                adjacent_zones=[],
            ),
        }

        # Create many entities for pagination testing
        entities = {}

        # Add 15 entities for pagination tests
        for i in range(15):
            entities[f"npc.guard_{i:02d}"] = NPC(
                id=f"npc.guard_{i:02d}",
                name=f"Guard {i:02d}",
                type="npc",
                current_zone="test_zone",
                hp=HP(current=10, max=10),
                visible_actors=[],
            )

        # Add a PC with many inventory items
        entities["pc.player"] = PC(
            id="pc.player",
            name="Player",
            type="pc",
            current_zone="test_zone",
            hp=HP(current=20, max=20),
            visible_actors=[],
            inventory=[f"item_{i:02d}" for i in range(20)],  # 20 items
        )

        state = GameState(
            entities=entities,
            zones=zones,
            current_actor="pc.player",
            clocks={
                f"clock_{i:02d}": {"value": i, "max": 10} for i in range(12)
            },  # 12 clocks
        )

        return state

    def test_inventory_pagination_limit(self, large_state):
        """Test inventory pagination with limit parameter."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "brief",
                "limit": 5,
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return only 5 items
        assert len(facts["items"]) == 5
        assert facts["item_count"] == 5

        # Should have pagination metadata
        assert "pagination" in facts
        assert facts["pagination"]["total_count"] == 20
        assert facts["pagination"]["returned_count"] == 5
        assert facts["pagination"]["has_more"] is True
        assert facts["pagination"]["offset"] == 0
        assert facts["pagination"]["limit"] == 5

    def test_inventory_pagination_offset(self, large_state):
        """Test inventory pagination with offset parameter."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "brief",
                "limit": 5,
                "offset": 10,
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return 5 items starting from item 10
        assert len(facts["items"]) == 5
        assert facts["pagination"]["offset"] == 10
        assert facts["pagination"]["returned_count"] == 5
        assert facts["pagination"]["has_more"] is True

    def test_zone_entities_pagination(self, large_state):
        """Test zone entity pagination."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "brief",
                "limit": 3,
            },
            large_state,
            Utterance(text="look around", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return only 3 entities
        assert len(facts["entities"]) == 3
        assert facts["entity_count"] == 3

        # Should have pagination metadata
        assert "pagination" in facts
        assert facts["pagination"]["total_count"] == 16  # 15 NPCs + 1 PC
        assert facts["pagination"]["has_more"] is True

    def test_clocks_pagination(self, large_state):
        """Test clocks pagination."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "topic": "clocks",
                "detail_level": "brief",
                "limit": 4,
            },
            large_state,
            Utterance(text="check clocks", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return only 4 clocks
        assert len(facts["active_clocks"]) == 4
        assert facts["clock_count"] == 4

        # Should have pagination metadata
        assert "pagination" in facts
        assert facts["pagination"]["total_count"] == 12
        assert facts["pagination"]["has_more"] is True

    def test_field_projection_status(self, large_state):
        """Test field projection for status topic."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "status",
                "detail_level": "full",
                "fields": ["name", "hp", "max_hp"],
            },
            large_state,
            Utterance(text="check my status", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only include requested fields
        assert "name" in facts
        assert "hp" in facts
        assert "max_hp" in facts

        # Should not include other fields
        assert "entity_id" not in facts
        assert "position" not in facts
        assert "tags" not in facts

    def test_field_projection_zone(self, large_state):
        """Test field projection for zone topic."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "full",
                "fields": ["name", "entities"],
            },
            large_state,
            Utterance(text="look around", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only include requested fields
        assert "name" in facts
        assert "entities" in facts

        # Should not include other fields
        assert "zone_id" not in facts
        assert "entity_count" not in facts
        assert "description" not in facts
        assert "entity_details" not in facts

    def test_field_projection_inventory(self, large_state):
        """Test field projection for inventory topic."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "full",
                "fields": ["items", "item_count"],
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only include requested fields
        assert "items" in facts
        assert "item_count" in facts

        # Should not include other fields
        assert "entity_id" not in facts
        assert "item_details" not in facts

    def test_pagination_with_field_projection(self, large_state):
        """Test combining pagination and field projection."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "brief",
                "limit": 3,
                "offset": 5,
                "fields": ["items", "pagination"],
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only include requested fields
        assert "items" in facts
        assert "pagination" in facts

        # Should not include other fields
        assert "entity_id" not in facts
        assert "item_count" not in facts

        # Pagination should still work
        assert len(facts["items"]) == 3
        assert facts["pagination"]["offset"] == 5
        assert facts["pagination"]["limit"] == 3

    def test_pagination_beyond_end(self, large_state):
        """Test pagination when offset is beyond available items."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "brief",
                "limit": 5,
                "offset": 25,  # Beyond 20 items
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return empty items
        assert facts["items"] == []
        assert facts["item_count"] == 0

        # Pagination metadata should reflect this
        assert facts["pagination"]["returned_count"] == 0
        assert facts["pagination"]["has_more"] is False

    def test_no_pagination_by_default(self, large_state):
        """Test that pagination is not applied when not requested."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.player",
                "target": "pc.player",
                "topic": "inventory",
                "detail_level": "brief",
            },
            large_state,
            Utterance(text="check my inventory", actor_id="pc.player"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should return all items
        assert len(facts["items"]) == 20
        assert facts["item_count"] == 20

        # Should not have pagination metadata
        assert "pagination" not in facts

    def test_relationships_pagination(self):
        """Test relationships pagination with multiple sources."""
        # Create entity with many relationships
        pc = PC(
            id="pc.social",
            name="Social PC",
            type="pc",
            current_zone="test",
            hp=HP(current=20, max=20),
            visible_actors=[],
            marks={
                f"mark_{i}": {
                    "tag": f"reputation_{i}",
                    "source": f"npc_{i // 3}",  # Group marks by source
                    "value": 1,
                }
                for i in range(15)
            },
        )

        state = GameState(
            entities={"pc.social": pc},
            zones={
                "test": Zone(id="test", name="Test", description="", adjacent_zones=[])
            },
            current_actor="pc.social",
        )

        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.social",
                "target": "pc.social",
                "topic": "relationships",
                "detail_level": "brief",
                "limit": 3,
            },
            state,
            Utterance(text="check my relationships", actor_id="pc.social"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should have pagination metadata
        assert "pagination" in facts
        assert (
            facts["pagination"]["has_more"] is True
            or facts["pagination"]["returned_count"] <= 3
        )


class TestSchemaVersioning:
    """Test schema versioning and query metadata features."""

    def test_metadata_included_in_all_responses(self, get_info_state):
        """Test that all get_info responses include metadata."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should include metadata
        assert "_metadata" in facts
        metadata = facts["_metadata"]

        # Should include all required fields
        assert "schema_version" in metadata
        assert "query_id" in metadata
        assert "timestamp" in metadata
        assert "round" in metadata
        assert "turn_id" in metadata
        assert "turn_index" in metadata
        assert "snapshot_id" in metadata
        assert "current_actor" in metadata
        assert "scene_id" in metadata
        assert "game_state_summary" in metadata

    def test_schema_version_format(self, get_info_state):
        """Test schema version follows semantic versioning."""
        result = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "clocks", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check clocks", actor_id="pc.arin"),
            seed=42,
        )

        metadata = result.facts["_metadata"]

        # Should be semantic version format
        schema_version = metadata["schema_version"]
        assert isinstance(schema_version, str)
        version_parts = schema_version.split(".")
        assert len(version_parts) == 3
        for part in version_parts:
            assert part.isdigit()

    def test_query_id_uniqueness(self, get_info_state):
        """Test that each query gets a unique ID."""
        result1 = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "scene", "detail_level": "brief"},
            get_info_state,
            Utterance(text="look around", actor_id="pc.arin"),
            seed=42,
        )

        result2 = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "scene", "detail_level": "brief"},
            get_info_state,
            Utterance(text="look around", actor_id="pc.arin"),
            seed=42,
        )

        query_id1 = result1.facts["_metadata"]["query_id"]
        query_id2 = result2.facts["_metadata"]["query_id"]

        # Should be different UUIDs
        assert query_id1 != query_id2
        assert len(query_id1) == 36  # UUID4 format
        assert len(query_id2) == 36

    def test_turn_id_consistency(self, get_info_state):
        """Test that turn_id reflects game state."""
        metadata = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "scene", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check scene", actor_id="pc.arin"),
            seed=42,
        ).facts["_metadata"]

        # Should match game state
        assert metadata["round"] == get_info_state.scene.round
        assert metadata["turn_index"] == get_info_state.scene.turn_index
        assert (
            metadata["turn_id"]
            == f"r{get_info_state.scene.round}_t{get_info_state.scene.turn_index}"
        )

    def test_snapshot_id_deterministic(self, get_info_state):
        """Test that snapshot_id is deterministic for same state."""
        result1 = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "rules", "detail_level": "brief"},
            get_info_state,
            Utterance(text="check rules", actor_id="pc.arin"),
            seed=42,
        )

        result2 = validate_and_execute(
            "get_info",
            {"actor": "pc.arin", "topic": "rules", "detail_level": "full"},
            get_info_state,
            Utterance(text="check rules", actor_id="pc.arin"),
            seed=42,
        )

        snapshot_id1 = result1.facts["_metadata"]["snapshot_id"]
        snapshot_id2 = result2.facts["_metadata"]["snapshot_id"]

        # Should be same for same game state
        assert snapshot_id1 == snapshot_id2
        assert snapshot_id1.startswith("snap_")
        assert len(snapshot_id1) == 13  # "snap_" + 8 digits

    def test_game_state_summary(self, get_info_state):
        """Test game state summary in metadata."""
        metadata = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "zone",
                "target": "courtyard",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="look around", actor_id="pc.arin"),
            seed=42,
        ).facts["_metadata"]

        summary = metadata["game_state_summary"]

        # Should reflect actual game state
        assert summary["entity_count"] == len(get_info_state.entities)
        assert summary["clock_count"] == len(get_info_state.clocks)
        assert summary["pending_action"] == get_info_state.pending_action

    def test_metadata_preserved_with_field_filtering(self, get_info_state):
        """Test that metadata is preserved even with field filtering."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
                "fields": ["name", "hp"],  # Don't include _metadata
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should only have requested fields plus metadata
        assert "name" in facts
        assert "hp" in facts
        assert "_metadata" in facts  # Should be preserved

        # Should not have other fields
        assert "entity_id" not in facts
        assert "position" not in facts

    def test_metadata_with_pagination(self):
        """Test metadata inclusion with pagination."""
        # Create state with many items
        pc = PC(
            id="pc.test",
            name="Test PC",
            type="pc",
            current_zone="test",
            hp=HP(current=20, max=20),
            visible_actors=[],
            inventory=[f"item_{i}" for i in range(10)],
        )

        state = GameState(
            entities={"pc.test": pc},
            zones={
                "test": Zone(id="test", name="Test", description="", adjacent_zones=[])
            },
            current_actor="pc.test",
        )

        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.test",
                "target": "pc.test",
                "topic": "inventory",
                "detail_level": "brief",
                "limit": 3,
            },
            state,
            Utterance(text="check inventory", actor_id="pc.test"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts

        # Should have both pagination and metadata
        assert "pagination" in facts
        assert "_metadata" in facts
        assert facts["pagination"]["total_count"] == 10
        assert facts["_metadata"]["schema_version"] == "1.0.0"

    def test_timestamp_format(self, get_info_state):
        """Test timestamp is in ISO format."""
        metadata = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "effects",
                "target": "pc.arin",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check effects", actor_id="pc.arin"),
            seed=42,
        ).facts["_metadata"]

        timestamp = metadata["timestamp"]

        # Should be valid ISO format with timezone
        assert isinstance(timestamp, str)
        assert "T" in timestamp
        assert timestamp.endswith("Z") or "+" in timestamp or timestamp.endswith(":00")

        # Should be parseable as datetime
        from datetime import datetime

        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    def test_current_actor_tracking(self, get_info_state):
        """Test current actor is correctly tracked in metadata."""
        metadata = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "relationships",
                "target": "pc.arin",
                "detail_level": "brief",
            },
            get_info_state,
            Utterance(text="check relationships", actor_id="pc.arin"),
            seed=42,
        ).facts["_metadata"]

        assert metadata["current_actor"] == "pc.arin"
        assert metadata["scene_id"] == get_info_state.scene.id

    def test_different_snapshot_ids_for_different_states(self):
        """Test that different game states produce different snapshot IDs."""
        # Create two different states
        state1 = GameState(
            entities={
                "pc.test": PC(
                    id="pc.test",
                    name="Test",
                    type="pc",
                    current_zone="zone1",
                    hp=HP(current=20, max=20),
                    visible_actors=[],
                )
            },
            zones={
                "zone1": Zone(
                    id="zone1", name="Zone 1", description="", adjacent_zones=[]
                )
            },
            current_actor="pc.test",
        )

        state2 = GameState(
            entities={
                "pc.test": PC(
                    id="pc.test",
                    name="Test",
                    type="pc",
                    current_zone="zone1",
                    hp=HP(current=20, max=20),
                    visible_actors=[],
                ),
                "npc.guard": NPC(
                    id="npc.guard",
                    name="Guard",
                    type="npc",
                    current_zone="zone1",
                    hp=HP(current=10, max=10),
                    visible_actors=[],
                ),
            },
            zones={
                "zone1": Zone(
                    id="zone1", name="Zone 1", description="", adjacent_zones=[]
                )
            },
            current_actor="pc.test",
        )

        result1 = validate_and_execute(
            "get_info",
            {"actor": "pc.test", "topic": "zone", "target": "zone1"},
            state1,
            Utterance(text="look", actor_id="pc.test"),
            seed=42,
        )

        result2 = validate_and_execute(
            "get_info",
            {"actor": "pc.test", "topic": "zone", "target": "zone1"},
            state2,
            Utterance(text="look", actor_id="pc.test"),
            seed=42,
        )

        snapshot_id1 = result1.facts["_metadata"]["snapshot_id"]
        snapshot_id2 = result2.facts["_metadata"]["snapshot_id"]

        # Should be different for different states
        assert snapshot_id1 != snapshot_id2


class TestRefsStructure:
    """Test refs map structure for reducing duplication and improving LLM grounding."""

    def test_basic_refs_structure(self, get_info_state):
        """Test basic refs structure transformation."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True

        # Should have facts and refs structure
        assert "facts" in result.facts
        assert "refs" in result.facts

        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should contain the entity_id
        assert "entity_id" in facts
        assert facts["entity_id"] == "pc.arin"

        # Refs should contain full entity details
        assert "entities" in refs
        assert "pc.arin" in refs["entities"]

        entity_ref = refs["entities"]["pc.arin"]
        assert entity_ref["id"] == "pc.arin"
        assert entity_ref["name"] == "Arin"
        assert entity_ref["type"] == "pc"

    def test_zone_refs_structure(self, get_info_state):
        """Test zone info with refs structure."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "courtyard",
                "topic": "zone",
                "detail_level": "full",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="look around", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should have thin structure
        assert "zone_id" in facts
        assert facts["zone_id"] == "courtyard"
        assert "entity_ids" in facts  # Should convert from entity_details

        # Refs should have full details
        assert "zones" in refs
        assert "courtyard" in refs["zones"]
        assert "entities" in refs

        # All referenced entities should be in refs
        for entity_id in facts["entity_ids"]:
            assert entity_id in refs["entities"]

    def test_inventory_refs_structure(self, get_info_state):
        """Test inventory with refs structure."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "inventory",
                "detail_level": "full",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="check my inventory", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should have items list and entity_id
        assert "items" in facts
        assert "entity_id" in facts

        # If there are item details, they should be converted to item_ids
        if facts.get("items"):
            # Entity should be in refs
            assert "entities" in refs
            assert facts["entity_id"] in refs["entities"]

    def test_clocks_refs_structure(self, get_info_state):
        """Test clocks with refs structure."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "clocks",
                "detail_level": "full",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="check clocks", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should have clock_ids instead of active_clocks
        if get_info_state.clocks:
            assert "clock_ids" in facts

            # Refs should have full clock details
            assert "clocks" in refs
            for clock_id in facts["clock_ids"]:
                assert clock_id in refs["clocks"]
                clock_ref = refs["clocks"][clock_id]
                assert "value" in clock_ref
                assert "max" in clock_ref

    def test_relationships_refs_structure(self):
        """Test relationships with refs structure."""
        # Create PC with relationships
        pc = PC(
            id="pc.social",
            name="Social PC",
            type="pc",
            current_zone="test",
            hp=HP(current=20, max=20),
            visible_actors=[],
            marks={
                "rep_guard": {"tag": "reputation", "source": "npc.guard", "value": 2},
                "rep_merchant": {
                    "tag": "reputation",
                    "source": "npc.merchant",
                    "value": -1,
                },
            },
        )

        state = GameState(
            entities={"pc.social": pc},
            zones={
                "test": Zone(id="test", name="Test", description="", adjacent_zones=[])
            },
            current_actor="pc.social",
        )

        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.social",
                "target": "pc.social",
                "topic": "relationships",
                "detail_level": "full",
                "use_refs": True,
            },
            state,
            Utterance(text="check my relationships", actor_id="pc.social"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should have relationship_source_ids instead of relationships
        if pc.marks:
            assert "relationship_source_ids" in facts

            # Refs should have full relationship details
            assert "relationships" in refs

    def test_metadata_preserved_in_refs_structure(self, get_info_state):
        """Test that metadata is preserved in refs structure."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "scene",
                "detail_level": "brief",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="check scene", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]

        # Metadata should be preserved in the facts section
        assert "_metadata" in facts
        assert facts["_metadata"]["schema_version"] == "1.0.0"

    def test_refs_structure_with_pagination(self):
        """Test refs structure with pagination."""
        # Create state with many entities
        entities = {}
        for i in range(10):
            entities[f"npc.guard_{i:02d}"] = NPC(
                id=f"npc.guard_{i:02d}",
                name=f"Guard {i:02d}",
                type="npc",
                current_zone="test_zone",
                hp=HP(current=10, max=10),
                visible_actors=[],
            )

        state = GameState(
            entities=entities,
            zones={
                "test_zone": Zone(
                    id="test_zone", name="Test Zone", description="", adjacent_zones=[]
                )
            },
            current_actor=list(entities.keys())[0],
        )

        result = validate_and_execute(
            "get_info",
            {
                "actor": list(entities.keys())[0],
                "target": "test_zone",
                "topic": "zone",
                "detail_level": "full",
                "limit": 3,
                "use_refs": True,
            },
            state,
            Utterance(text="look around", actor_id=list(entities.keys())[0]),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Should have pagination metadata
        assert "pagination" in facts
        assert facts["pagination"]["limit"] == 3

        # Should have entity_ids for the paginated entities
        assert "entity_ids" in facts
        assert len(facts["entity_ids"]) == 3

        # All referenced entities should be in refs
        for entity_id in facts["entity_ids"]:
            assert entity_id in refs["entities"]

    def test_refs_structure_with_field_filtering(self, get_info_state):
        """Test refs structure with field filtering."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
                "use_refs": True,
                "fields": ["entity_id", "name", "hp"],
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        facts = result.facts["facts"]
        refs = result.facts["refs"]

        # Facts should only include requested fields (plus metadata)
        assert "entity_id" in facts
        assert "name" in facts
        assert "hp" in facts
        assert "_metadata" in facts  # Always preserved

        # Should not include other fields
        assert "type" not in facts
        assert "current_zone" not in facts

        # Refs should still contain full entity details
        if "entities" in refs:
            entity_ref = refs["entities"]["pc.arin"]
            assert "id" in entity_ref
            assert "name" in entity_ref
            assert "type" in entity_ref

    def test_no_refs_by_default(self, get_info_state):
        """Test that refs structure is not used by default."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "target": "pc.arin",
                "topic": "status",
                "detail_level": "full",
            },
            get_info_state,
            Utterance(text="check my status", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True

        # Should have traditional structure, not refs structure
        assert "facts" not in result.facts
        assert "refs" not in result.facts

        # Should have direct facts structure
        assert "entity_id" in result.facts
        assert "_metadata" in result.facts

    def test_empty_refs_sections_removed(self, get_info_state):
        """Test that empty refs sections are removed."""
        result = validate_and_execute(
            "get_info",
            {
                "actor": "pc.arin",
                "topic": "rules",
                "detail_level": "brief",
                "use_refs": True,
            },
            get_info_state,
            Utterance(text="check rules", actor_id="pc.arin"),
            seed=42,
        )

        assert result.ok is True
        refs = result.facts["refs"]

        # Empty sections should be removed
        for section in refs.values():
            assert len(section) > 0  # No empty sections
