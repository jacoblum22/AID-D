"""
Test suite for GM-Only Field Enforcement.

Tests validation rules that prevent drift between gm_only boolean
and visibility string fields, ensuring data consistency.
"""

import sys
import os
import pytest
from typing import Dict, Union, Any

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Clock, Scene, Meta, HP, Entity
from router.meta_utils import set_visibility


class TestGMOnlyFieldEnforcement:
    """Test GM-only field consistency validation."""

    def test_meta_creation_with_consistent_fields(self):
        """Test that Meta objects with consistent fields validate correctly."""
        # All valid combinations
        valid_combinations = [
            {"visibility": "public", "gm_only": False},
            {"visibility": "hidden", "gm_only": False},
            {"visibility": "gm_only", "gm_only": True},
        ]

        for combo in valid_combinations:
            meta = Meta(**combo)
            assert meta.visibility == combo["visibility"]
            assert meta.gm_only == combo["gm_only"]

    def test_meta_creation_with_inconsistent_fields_raises_error(self):
        """Test that Meta objects with inconsistent fields raise validation errors."""
        # Invalid combinations that should fail
        invalid_combinations = [
            {"visibility": "public", "gm_only": True},
            {"visibility": "hidden", "gm_only": True},
            {"visibility": "gm_only", "gm_only": False},
        ]

        for combo in invalid_combinations:
            with pytest.raises(ValueError) as exc_info:
                Meta(**combo)

            assert "Inconsistent gm_only flag" in str(exc_info.value)
            assert f"visibility='{combo['visibility']}'" in str(exc_info.value)
            assert f"gm_only={combo['gm_only']}" in str(exc_info.value)

    def test_entity_creation_validates_meta_consistency(self):
        """Test that creating entities validates Meta field consistency."""
        # Valid entity should work
        valid_entity = PC(
            id="pc.valid",
            name="Valid PC",
            current_zone="test",
            hp=HP(current=10, max=10),
            meta=Meta(visibility="public", gm_only=False),
        )
        assert valid_entity.meta.visibility == "public"
        assert valid_entity.meta.gm_only is False

        # Invalid entity should fail
        with pytest.raises(ValueError) as exc_info:
            PC(
                id="pc.invalid",
                name="Invalid PC",
                current_zone="test",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="gm_only", gm_only=False),
            )

        assert "Inconsistent gm_only flag" in str(exc_info.value)

    def test_zone_creation_validates_meta_consistency(self):
        """Test that creating zones validates Meta field consistency."""
        # Valid zone should work
        valid_zone = Zone(
            id="zone.valid",
            name="Valid Zone",
            description="A valid zone",
            adjacent_zones=[],
            meta=Meta(visibility="hidden", gm_only=False),
        )
        assert valid_zone.meta.visibility == "hidden"
        assert valid_zone.meta.gm_only is False

        # Invalid zone should fail
        with pytest.raises(ValueError):
            Zone(
                id="zone.invalid",
                name="Invalid Zone",
                description="An invalid zone",
                adjacent_zones=[],
                meta=Meta(visibility="public", gm_only=True),
            )

    def test_clock_creation_validates_meta_consistency(self):
        """Test that creating clocks validates Meta field consistency."""
        # Valid clock should work
        valid_clock = Clock(
            id="clock.valid",
            name="Valid Clock",
            value=2,
            maximum=5,
            meta=Meta(visibility="gm_only", gm_only=True),
        )
        assert valid_clock.meta.visibility == "gm_only"
        assert valid_clock.meta.gm_only is True

        # Invalid clock should fail
        with pytest.raises(ValueError):
            Clock(
                id="clock.invalid",
                name="Invalid Clock",
                value=1,
                maximum=3,
                meta=Meta(visibility="hidden", gm_only=True),
            )

    def test_set_visibility_maintains_consistency(self):
        """Test that set_visibility utility maintains field consistency."""
        entity = PC(
            id="pc.test",
            name="Test PC",
            current_zone="test",
            hp=HP(current=10, max=10),
            meta=Meta(visibility="public", gm_only=False),
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


class TestGameStateInvariantValidation:
    """Test GameState.validate_invariants() method."""

    @pytest.fixture
    def valid_state(self):
        """Create a game state with all valid Meta fields."""
        zones = {
            "room": Zone(
                id="room",
                name="Test Room",
                description="A test room",
                adjacent_zones=[],
                meta=Meta(visibility="public", gm_only=False),
            )
        }

        entities: Dict[str, Entity] = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="room",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public", gm_only=False),
            ),
            "npc.hidden": NPC(
                id="npc.hidden",
                name="Hidden NPC",
                current_zone="room",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="hidden", gm_only=False),
            ),
            "npc.gm_secret": NPC(
                id="npc.gm_secret",
                name="GM Secret NPC",
                current_zone="room",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        clocks: Dict[str, Union[Clock, Dict[str, Any]]] = {
            "tension": Clock(
                id="tension",
                name="Tension Clock",
                value=3,
                maximum=6,
                meta=Meta(visibility="public", gm_only=False),
            ),
            "secret_timer": Clock(
                id="secret_timer",
                name="Secret Timer",
                value=2,
                maximum=4,
                meta=Meta(visibility="gm_only", gm_only=True),
            ),
        }

        return GameState(entities=entities, zones=zones, clocks=clocks)

    def test_validate_invariants_with_valid_state(self, valid_state):
        """Test that validate_invariants returns no errors for valid state."""
        errors = valid_state.validate_invariants()
        assert errors == []

    def test_validate_invariants_detects_entity_inconsistencies(self, valid_state):
        """Test that validate_invariants detects entity Meta inconsistencies."""
        # Manually corrupt an entity's meta fields
        entity = valid_state.entities["pc.alice"]

        # Bypass validation by directly setting fields
        entity.meta.__dict__["visibility"] = "gm_only"
        entity.meta.__dict__["gm_only"] = False  # Inconsistent!

        errors = valid_state.validate_invariants()

        assert len(errors) == 1
        assert "Entity pc.alice" in errors[0]
        assert "Inconsistent gm_only flag" in errors[0]
        assert "visibility='gm_only'" in errors[0]
        assert "gm_only=False" in errors[0]

    def test_validate_invariants_detects_zone_inconsistencies(self, valid_state):
        """Test that validate_invariants detects zone Meta inconsistencies."""
        # Manually corrupt a zone's meta fields
        zone = valid_state.zones["room"]

        # Bypass validation by directly setting fields
        zone.meta.__dict__["visibility"] = "public"
        zone.meta.__dict__["gm_only"] = True  # Inconsistent!

        errors = valid_state.validate_invariants()

        assert len(errors) == 1
        assert "Zone room" in errors[0]
        assert "Inconsistent gm_only flag" in errors[0]

    def test_validate_invariants_detects_clock_inconsistencies(self, valid_state):
        """Test that validate_invariants detects clock Meta inconsistencies."""
        # Manually corrupt a clock's meta fields
        clock = valid_state.clocks["tension"]

        # Bypass validation by directly setting fields
        clock.meta.__dict__["visibility"] = "hidden"
        clock.meta.__dict__["gm_only"] = True  # Inconsistent!

        errors = valid_state.validate_invariants()

        assert len(errors) == 1
        assert "Clock tension" in errors[0]
        assert "Inconsistent gm_only flag" in errors[0]

    def test_validate_invariants_detects_multiple_inconsistencies(self, valid_state):
        """Test that validate_invariants detects multiple inconsistencies."""
        # Corrupt multiple objects
        valid_state.entities["pc.alice"].meta.__dict__["gm_only"] = True
        valid_state.zones["room"].meta.__dict__["gm_only"] = True
        valid_state.clocks["tension"].meta.__dict__["gm_only"] = True

        errors = valid_state.validate_invariants()

        assert len(errors) == 3

        # Check that all three objects are mentioned
        error_text = " ".join(errors)
        assert "Entity pc.alice" in error_text
        assert "Zone room" in error_text
        assert "Clock tension" in error_text

    def test_validate_invariants_handles_legacy_clock_dicts(self, valid_state):
        """Test that validate_invariants handles legacy dictionary clocks."""
        # Add a legacy clock format
        valid_state.clocks["legacy_clock"] = {
            "value": 2,
            "max": 5,
            "meta": {"visibility": "public", "gm_only": False},
        }

        # Should not cause errors since we skip validation for dict clocks
        errors = valid_state.validate_invariants()
        assert errors == []

    def test_validate_invariants_handles_scene_meta(self, valid_state):
        """Test that validate_invariants checks scene meta if present."""
        # Add meta to scene
        valid_state.scene.meta = Meta(visibility="public", gm_only=False)

        # Should validate correctly
        errors = valid_state.validate_invariants()
        assert errors == []

        # Corrupt scene meta
        valid_state.scene.meta.__dict__["gm_only"] = True  # Inconsistent!

        errors = valid_state.validate_invariants()
        assert len(errors) == 1
        assert f"Scene {valid_state.scene.id}" in errors[0]


class TestFieldEnforcementIntegration:
    """Test integration with existing Meta and Redaction system."""

    def test_enforcement_works_with_caching(self):
        """Test that field enforcement works with redaction caching."""
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

        state = GameState(entities=entities, zones=zones)

        # Use caching
        view = state.get_cached_view("pc.test", "pc.test")
        assert view["is_visible"] is True

        # Validate invariants
        errors = state.validate_invariants()
        assert errors == []

    def test_enforcement_prevents_corruption_during_updates(self):
        """Test that enforcement prevents field corruption during updates."""
        entity = PC(
            id="pc.test",
            name="Test PC",
            current_zone="room",
            hp=HP(current=10, max=10),
            meta=Meta(visibility="public", gm_only=False),
        )

        # Valid update should work
        set_visibility(entity, "gm_only")
        assert entity.meta.visibility == "gm_only"
        assert entity.meta.gm_only is True

        # Try to create inconsistent state manually (should fail on next validation)
        entity.meta.__dict__["gm_only"] = False

        # Direct validation should catch this
        with pytest.raises(ValueError):
            entity.meta.model_validate(entity.meta.model_dump())
