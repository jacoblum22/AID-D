"""
Test script for the game state data structures.

Tests core Pydantic models to ensure:
- Mutable default isolation (critical for preventing shared state bugs)
- Basic model instantiation and validation
- Default factory behavior
- Backward compatibility features
"""

import sys
import os
import pytest
from typing import Dict
from pydantic import ValidationError

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import (
    GameState,
    PC,
    NPC,
    Zone,
    Utterance,
    Scene,
    ObjectEntity,
    ItemEntity,
    HP,
    Stats,
    Entity,
)


class TestMutableDefaultIsolation:
    """Test that mutable defaults are properly isolated between instances."""

    def test_pc_mutable_defaults_isolated(self):
        """Test that PC instances don't share mutable defaults."""
        pc1 = PC(id="pc1", name="Alice", current_zone="zone1", type="pc")
        pc2 = PC(id="pc2", name="Bob", current_zone="zone2", type="pc")

        # Test lists are isolated
        pc1.visible_actors.append("npc1")
        pc1.inventory.append("sword")

        assert (
            pc2.visible_actors == []
        ), "PC instances should have isolated visible_actors lists"
        assert pc2.inventory == [], "PC instances should have isolated inventory lists"

        # Test dicts are isolated
        pc1.conditions["poisoned"] = True
        assert (
            pc2.conditions == {}
        ), "PC instances should have isolated conditions dicts"

        # Test HP objects are isolated
        pc1.hp.current = 10
        assert pc2.hp.current == 20, "PC instances should have isolated HP objects"

        # Test Stats objects are isolated
        pc1.stats.strength = 15
        assert (
            pc2.stats.strength == 10
        ), "PC instances should have isolated Stats objects"

    def test_npc_mutable_defaults_isolated(self):
        """Test that NPC instances don't share mutable defaults."""
        npc1 = NPC(id="npc1", name="Guard1", current_zone="zone1", type="npc")
        npc2 = NPC(id="npc2", name="Guard2", current_zone="zone2", type="npc")

        # Test lists are isolated
        npc1.visible_actors.append("pc1")
        npc1.inventory.append("spear")

        assert (
            npc2.visible_actors == []
        ), "NPC instances should have isolated visible_actors lists"
        assert (
            npc2.inventory == []
        ), "NPC instances should have isolated inventory lists"

        # Test dicts are isolated
        npc1.conditions["stunned"] = True
        assert (
            npc2.conditions == {}
        ), "NPC instances should have isolated conditions dicts"

    def test_scene_mutable_defaults_isolated(self):
        """Test that Scene instances don't share mutable defaults."""
        scene1 = Scene(id="scene1")
        scene2 = Scene(id="scene2")

        # Test lists are isolated
        scene1.turn_order.append("pc1")
        assert (
            scene2.turn_order == []
        ), "Scene instances should have isolated turn_order lists"

        # Test dicts are isolated
        scene1.tags["alert"] = "alarmed"
        scene1.objective["goal"] = "escape"

        # scene2 should have its own default tags
        assert (
            scene2.tags["alert"] == "normal"
        ), "Scene instances should have isolated tags dicts"
        assert (
            scene2.objective == {}
        ), "Scene instances should have isolated objective dicts"

    def test_game_state_mutable_defaults_isolated(self):
        """Test that GameState instances don't share mutable defaults."""
        entities1: Dict[str, Entity] = {
            "pc1": PC(id="pc1", name="Alice", current_zone="zone1", type="pc")
        }
        zones1 = {
            "zone1": Zone(
                id="zone1", name="Zone 1", description="A zone", adjacent_zones=[]
            )
        }

        entities2: Dict[str, Entity] = {
            "pc2": PC(id="pc2", name="Bob", current_zone="zone2", type="pc")
        }
        zones2 = {
            "zone2": Zone(
                id="zone2", name="Zone 2", description="Another zone", adjacent_zones=[]
            )
        }

        state1 = GameState(entities=entities1, zones=zones1)
        state2 = GameState(entities=entities2, zones=zones2)

        # Test Scene objects are isolated
        state1.scene.tags["alert"] = "alarmed"
        assert (
            state2.scene.tags["alert"] == "normal"
        ), "GameState instances should have isolated Scene objects"

        # Test dicts are isolated
        state1.turn_flags["combat"] = True
        state1.clocks["alarm"] = {"value": 3, "max": 5}

        assert (
            state2.turn_flags == {}
        ), "GameState instances should have isolated turn_flags dicts"
        assert (
            state2.clocks == {}
        ), "GameState instances should have isolated clocks dicts"

    def test_utterance_mutable_defaults_isolated(self):
        """Test that Utterance instances don't share mutable defaults."""
        utterance1 = Utterance(text="I attack", actor_id="pc1")
        utterance2 = Utterance(text="I defend", actor_id="pc2")

        # Test lists are isolated
        utterance1.actionable_verbs.append("attack")
        assert (
            utterance2.actionable_verbs == []
        ), "Utterance instances should have isolated actionable_verbs lists"


class TestBasicInstantiation:
    """Test basic instantiation of all game state models."""

    def test_hp_instantiation(self):
        """Test HP model creation."""
        hp = HP(current=15, max=20)
        assert hp.current == 15
        assert hp.max == 20

    def test_stats_instantiation(self):
        """Test Stats model with defaults."""
        stats = Stats()
        assert stats.strength == 10
        assert stats.dexterity == 10
        assert stats.constitution == 10
        assert stats.intelligence == 10
        assert stats.wisdom == 10
        assert stats.charisma == 10

        # Test custom values
        custom_stats = Stats(strength=18, charisma=14)
        assert custom_stats.strength == 18
        assert custom_stats.charisma == 14
        assert custom_stats.dexterity == 10  # Should still have default

    def test_zone_instantiation(self):
        """Test Zone model creation."""
        zone = Zone(
            id="test_zone",
            name="Test Zone",
            description="A test zone",
            adjacent_zones=["zone1", "zone2"],
        )
        assert zone.id == "test_zone"
        assert zone.name == "Test Zone"
        assert zone.description == "A test zone"
        assert zone.adjacent_zones == ["zone1", "zone2"]

    def test_pc_instantiation(self):
        """Test PC model creation with defaults."""
        pc = PC(id="test_pc", name="Test PC", current_zone="zone1", type="pc")

        assert pc.id == "test_pc"
        assert pc.name == "Test PC"
        assert pc.current_zone == "zone1"
        assert pc.type == "pc"
        assert pc.has_weapon is True
        assert pc.has_talked_this_turn is False
        assert pc.hp.current == 20
        assert pc.hp.max == 20
        assert pc.stats.strength == 10
        assert pc.visible_actors == []
        assert pc.inventory == []
        assert pc.conditions == {}

    def test_npc_instantiation(self):
        """Test NPC model creation with defaults."""
        npc = NPC(id="test_npc", name="Test NPC", current_zone="zone1", type="npc")

        assert npc.id == "test_npc"
        assert npc.name == "Test NPC"
        assert npc.current_zone == "zone1"
        assert npc.type == "npc"
        assert npc.has_weapon is True
        assert npc.has_talked_this_turn is False
        assert npc.hp.current == 20
        assert npc.hp.max == 20
        assert npc.visible_actors == []
        assert npc.inventory == []
        assert npc.conditions == {}

    def test_object_entity_instantiation(self):
        """Test ObjectEntity model creation."""
        obj = ObjectEntity(
            id="test_obj",
            name="Test Object",
            current_zone="zone1",
            type="object",
            description="A test object",
        )

        assert obj.id == "test_obj"
        assert obj.name == "Test Object"
        assert obj.type == "object"
        assert obj.description == "A test object"
        assert obj.interactable is True
        assert obj.locked is False

    def test_item_entity_instantiation(self):
        """Test ItemEntity model creation."""
        item = ItemEntity(
            id="test_item",
            name="Test Item",
            current_zone="zone1",
            type="item",
            description="A test item",
        )

        assert item.id == "test_item"
        assert item.name == "Test Item"
        assert item.type == "item"
        assert item.description == "A test item"
        assert item.weight == 1.0
        assert item.value == 0

    def test_scene_instantiation(self):
        """Test Scene model creation with defaults."""
        scene = Scene()

        assert scene.id == "default_scene"
        assert scene.turn_order == []
        assert scene.turn_index == 0
        assert scene.round == 1
        assert scene.base_dc == 12
        assert scene.tags == {
            "alert": "normal",
            "lighting": "normal",
            "noise": "normal",
            "cover": "some",
        }
        assert scene.objective == {}

    def test_utterance_instantiation(self):
        """Test Utterance model creation."""
        utterance = Utterance(text="I attack the goblin", actor_id="pc1")

        assert utterance.text == "I attack the goblin"
        assert utterance.actor_id == "pc1"
        assert utterance.detected_intent is None
        assert utterance.actionable_verbs == []


class TestGameState:
    """Test GameState functionality."""

    def test_game_state_instantiation(self):
        """Test GameState creation."""
        pc = PC(id="pc1", name="Hero", current_zone="zone1", type="pc")
        npc = NPC(id="npc1", name="Guard", current_zone="zone1", type="npc")
        zone = Zone(
            id="zone1",
            name="Starting Zone",
            description="Where it begins",
            adjacent_zones=[],
        )

        entities = {"pc1": pc, "npc1": npc}
        zones = {"zone1": zone}

        state = GameState(entities=entities, zones=zones)

        assert state.entities == entities
        assert state.zones == zones
        assert state.pending_action is None
        assert state.current_actor is None
        assert state.turn_flags == {}
        assert state.clocks == {}
        assert isinstance(state.scene, Scene)

    def test_actors_backward_compatibility(self):
        """Test that the actors property provides backward compatibility."""
        pc = PC(id="pc1", name="Hero", current_zone="zone1", type="pc")
        npc = NPC(id="npc1", name="Guard", current_zone="zone1", type="npc")
        obj = ObjectEntity(id="obj1", name="Door", current_zone="zone1", type="object")
        item = ItemEntity(id="item1", name="Sword", current_zone="zone1", type="item")

        entities = {"pc1": pc, "npc1": npc, "obj1": obj, "item1": item}
        zones = {
            "zone1": Zone(
                id="zone1", name="Zone", description="A zone", adjacent_zones=[]
            )
        }

        state = GameState(entities=entities, zones=zones)

        # actors property should only include PC and NPC entities
        actors = state.actors
        assert "pc1" in actors
        assert "npc1" in actors
        assert "obj1" not in actors  # Objects should be filtered out
        assert "item1" not in actors  # Items should be filtered out

        assert len(actors) == 2
        assert isinstance(actors["pc1"], PC)
        assert isinstance(actors["npc1"], NPC)


class TestUtteranceMethods:
    """Test Utterance method functionality."""

    def test_has_actionable_verb_detection(self):
        """Test that actionable verb detection works."""
        # Test with actionable verbs
        move_utterance = Utterance(text="I want to move to the castle", actor_id="pc1")
        assert move_utterance.has_actionable_verb() is True

        attack_utterance = Utterance(text="I attack the dragon", actor_id="pc1")
        assert attack_utterance.has_actionable_verb() is True

        talk_utterance = Utterance(text="I say hello to the merchant", actor_id="pc1")
        assert talk_utterance.has_actionable_verb() is True

        # Test without actionable verbs
        non_action_utterance = Utterance(
            text="The weather is nice today", actor_id="pc1"
        )
        assert non_action_utterance.has_actionable_verb() is False

        # Test case insensitivity
        case_utterance = Utterance(text="I ATTACK the GOBLIN", actor_id="pc1")
        assert case_utterance.has_actionable_verb() is True


class TestModelValidation:
    """Test Pydantic model validation."""

    def test_pc_type_validation(self):
        """Test that PC type is validated correctly."""
        # Valid PC
        pc = PC(id="pc1", name="Hero", current_zone="zone1", type="pc")
        assert pc.type == "pc"

        # Test invalid type using model_validate to bypass type checker
        with pytest.raises(ValidationError):
            PC.model_validate(
                {
                    "id": "pc1",
                    "name": "Hero",
                    "current_zone": "zone1",
                    "type": "invalid",
                }
            )

    def test_npc_type_validation(self):
        """Test that NPC type is validated correctly."""
        # Valid NPC
        npc = NPC(id="npc1", name="Guard", current_zone="zone1", type="npc")
        assert npc.type == "npc"

        # Test invalid type using model_validate to bypass type checker
        with pytest.raises(ValidationError):
            NPC.model_validate(
                {
                    "id": "npc1",
                    "name": "Guard",
                    "current_zone": "zone1",
                    "type": "invalid",
                }
            )

    def test_hp_validation(self):
        """Test HP model validation."""
        # Valid HP
        hp = HP(current=15, max=20)
        assert hp.current == 15
        assert hp.max == 20

        # Test that required fields are enforced using model_validate
        with pytest.raises(ValidationError):
            HP.model_validate({"current": 15})  # Missing max

        with pytest.raises(ValidationError):
            HP.model_validate({"max": 20})  # Missing current


if __name__ == "__main__":
    # Run pytest when script is executed directly
    pytest.main([__file__, "-v"])
