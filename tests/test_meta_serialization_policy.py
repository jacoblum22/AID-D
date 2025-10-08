"""
Tests for Meta Serialization Policy - Export modes for meta serialization functionality.

Tests different serialization modes for Meta objects and GameState export functionality,
ensuring proper handling of known_by sets and context-specific data inclusion.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Union
from models.meta import Meta
from backend.router.game_state import GameState, PC, NPC, Zone, Scene, HP, Clock


class TestMetaExportModes:
    """Test Meta class export functionality with different modes."""

    @pytest.fixture
    def sample_meta(self):
        """Create a Meta instance with comprehensive test data."""
        return Meta(
            visibility="public",
            gm_only=False,
            known_by={"pc.alice", "npc.bob", "pc.charlie"},
            created_at="2024-01-01T10:00:00Z",
            last_changed_at="2024-01-01T12:00:00Z",
            source="manual",
            notes="Test entity for serialization",
            extra={"custom_field": "test_value", "priority": 5},
        )

    def test_export_full_mode(self, sample_meta):
        """Test full export mode includes all fields."""
        result = sample_meta.export(mode="full")

        expected_fields = {
            "visibility",
            "gm_only",
            "known_by",
            "created_at",
            "last_changed_at",
            "source",
            "notes",
            "extra",
        }
        assert set(result.keys()) == expected_fields

        # Verify content
        assert result["visibility"] == "public"
        assert result["gm_only"] == False
        assert set(result["known_by"]) == {"pc.alice", "npc.bob", "pc.charlie"}
        assert result["created_at"] == "2024-01-01T10:00:00Z"
        assert result["last_changed_at"] == "2024-01-01T12:00:00Z"
        assert result["source"] == "manual"
        assert result["notes"] == "Test entity for serialization"
        assert result["extra"] == {"custom_field": "test_value", "priority": 5}

    def test_export_public_mode(self, sample_meta):
        """Test public export mode excludes sensitive data."""
        result = sample_meta.export(mode="public")

        expected_fields = {
            "visibility",
            "gm_only",
            "known_by_count",
            "created_at",
            "source",
        }
        assert set(result.keys()) == expected_fields

        # Should have count instead of actual known_by list
        assert result["known_by_count"] == 3
        assert "known_by" not in result
        assert "notes" not in result
        assert "extra" not in result

    def test_export_minimal_mode(self, sample_meta):
        """Test minimal export mode includes only core fields."""
        result = sample_meta.export(mode="minimal")

        expected_fields = {"visibility", "gm_only"}
        assert set(result.keys()) == expected_fields

        assert result["visibility"] == "public"
        assert result["gm_only"] == False

    def test_export_save_mode(self, sample_meta):
        """Test save export mode includes persistent fields."""
        result = sample_meta.export(mode="save")

        expected_fields = {
            "visibility",
            "gm_only",
            "known_by",
            "created_at",
            "last_changed_at",
            "source",
            "notes",
            "extra",
        }
        assert set(result.keys()) == expected_fields

        # Should be same as full for this test case
        assert result == sample_meta.export(mode="full")

    def test_export_session_mode(self, sample_meta):
        """Test session export mode includes runtime fields."""
        result = sample_meta.export(mode="session")

        expected_fields = {"visibility", "gm_only", "known_by", "last_changed_at"}
        assert set(result.keys()) == expected_fields

        assert result["visibility"] == "public"
        assert result["gm_only"] == False
        assert set(result["known_by"]) == {"pc.alice", "npc.bob", "pc.charlie"}
        assert result["last_changed_at"] == "2024-01-01T12:00:00Z"

    def test_export_include_known_by_override(self, sample_meta):
        """Test explicit override of known_by inclusion."""
        # Force include known_by in minimal mode
        result = sample_meta.export(mode="minimal", include_known_by=True)
        assert "known_by" in result
        assert set(result["known_by"]) == {"pc.alice", "npc.bob", "pc.charlie"}

        # Force exclude known_by in full mode
        result = sample_meta.export(mode="full", include_known_by=False)
        assert "known_by" not in result
        # Should still have other full fields
        assert "notes" in result
        assert "extra" in result

    def test_export_handles_empty_optional_fields(self):
        """Test export properly handles empty or None optional fields."""
        minimal_meta = Meta(visibility="hidden")

        result = minimal_meta.export(mode="full")

        # Should not include None or empty fields
        assert "last_changed_at" not in result
        assert "source" not in result
        assert "notes" not in result
        assert "extra" not in result

        # But should include empty known_by as list
        assert result["known_by"] == []

    def test_convenience_methods(self, sample_meta):
        """Test convenience export methods."""
        # Test all convenience methods
        save_result = sample_meta.for_save()
        session_result = sample_meta.for_session()
        public_result = sample_meta.for_public()
        minimal_result = sample_meta.for_minimal()

        # Should match explicit mode calls
        assert save_result == sample_meta.export(mode="save")
        assert session_result == sample_meta.export(mode="session")
        assert public_result == sample_meta.export(mode="public")
        assert minimal_result == sample_meta.export(mode="minimal")

    def test_from_export_reconstruction(self, sample_meta):
        """Test round-trip export and reconstruction."""
        # Test with full export
        exported = sample_meta.export(mode="full")
        reconstructed = Meta.from_export(exported)

        assert reconstructed.visibility == sample_meta.visibility
        assert reconstructed.gm_only == sample_meta.gm_only
        assert reconstructed.known_by == sample_meta.known_by
        assert reconstructed.source == sample_meta.source
        assert reconstructed.notes == sample_meta.notes
        assert reconstructed.extra == sample_meta.extra

    def test_from_export_handles_missing_fields(self):
        """Test from_export fills in defaults for missing fields."""
        minimal_data = {"visibility": "hidden"}  # Don't set inconsistent gm_only

        meta = Meta.from_export(minimal_data)

        assert meta.visibility == "hidden"
        assert meta.gm_only == False  # Should be auto-corrected to match visibility
        assert meta.known_by == set()  # Default empty set
        assert meta.source is None
        assert meta.notes is None
        assert meta.extra == {}
        assert meta.created_at  # Should have a timestamp

    def test_from_export_converts_known_by_list(self):
        """Test from_export properly converts known_by from list to set."""
        data = {
            "visibility": "public",
            "known_by": ["pc.alice", "npc.bob", "pc.alice"],  # List with duplicate
        }

        meta = Meta.from_export(data)

        # Should be converted to set, removing duplicates
        assert meta.known_by == {"pc.alice", "npc.bob"}

    def test_invalid_export_mode_raises_error(self, sample_meta):
        """Test that invalid export mode raises appropriate error."""
        with pytest.raises(ValueError, match="Unknown export mode: invalid"):
            sample_meta.export(mode="invalid")  # type: ignore


class TestGameStateExportMethods:
    """Test GameState export functionality with different modes."""

    @pytest.fixture
    def sample_game_state(self):
        """Create a GameState with comprehensive test data."""
        entities = {
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="tavern",
                meta=Meta(
                    visibility="public", known_by={"npc.bob"}, notes="Player character"
                ),
            ),
            "npc.bob": NPC(
                id="npc.bob",
                name="Bob the Bartender",
                current_zone="tavern",
                meta=Meta(
                    visibility="public", known_by={"pc.alice"}, source="generator"
                ),
            ),
            "npc.secret": NPC(
                id="npc.secret",
                name="Secret Agent",
                current_zone="tavern",
                meta=Meta(
                    visibility="gm_only", gm_only=True, notes="Hidden from players"
                ),
            ),
        }

        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(
                    visibility="public", source="manual", extra={"atmosphere": "cozy"}
                ),
            )
        }

        clocks: Dict[str, Union[Clock, Dict[str, Any]]] = {
            "tension": Clock(
                id="tension",
                name="Rising Tension",
                maximum=6,
                value=2,
                meta=Meta(visibility="hidden", notes="Track overall tension"),
            )
        }

        return GameState(
            entities=entities, zones=zones, clocks=clocks, scene=Scene(id="scene1")
        )

    def test_export_state_full_mode(self, sample_game_state):
        """Test full export mode includes all data."""
        result = sample_game_state.export_state(mode="full")

        assert "scene" in result
        assert "zones" in result
        assert "entities" in result
        assert "clocks" in result

        # Check that meta is exported in full mode
        alice_meta = result["entities"]["pc.alice"]["meta"]
        assert "known_by" in alice_meta
        assert "notes" in alice_meta

        # GM-only entities should be included in full mode
        assert "npc.secret" in result["entities"]

    def test_export_state_public_mode(self, sample_game_state):
        """Test public export mode with redaction."""
        result = sample_game_state.export_state(
            mode="public", pov_id="pc.alice", role="player"
        )

        # Should apply redaction for player role
        alice_meta = result["entities"]["pc.alice"]["meta"]
        assert "known_by_count" in alice_meta  # Public mode shows count
        assert "known_by" not in alice_meta  # But not actual list

        # GM-only entities should be redacted out
        assert "npc.secret" not in result["entities"]

    def test_export_state_minimal_mode(self, sample_game_state):
        """Test minimal export mode includes only core fields."""
        result = sample_game_state.export_state(mode="minimal")

        alice_meta = result["entities"]["pc.alice"]["meta"]

        # Should only have core meta fields
        expected_fields = {"visibility", "gm_only"}
        assert set(alice_meta.keys()) == expected_fields

    def test_export_state_save_mode(self, sample_game_state):
        """Test save export mode for persistence."""
        result = sample_game_state.export_state(mode="save")

        alice_meta = result["entities"]["pc.alice"]["meta"]

        # Should include persistent fields
        assert "known_by" in alice_meta
        assert "notes" in alice_meta
        assert "created_at" in alice_meta

    def test_export_state_session_mode(self, sample_game_state):
        """Test session export mode for runtime management."""
        result = sample_game_state.export_state(
            mode="session", pov_id="pc.alice", role="player"
        )

        alice_meta = result["entities"]["pc.alice"]["meta"]

        # Should include runtime fields (but last_changed_at might be None)
        expected_fields = {"visibility", "gm_only", "known_by"}
        actual_fields = set(alice_meta.keys())

        # Must have these core fields
        assert expected_fields.issubset(actual_fields)

        # May optionally have last_changed_at if it's set
        if "last_changed_at" in alice_meta:
            expected_fields.add("last_changed_at")

        assert actual_fields == expected_fields

    def test_to_save_format(self, sample_game_state):
        """Test convenience method for save format."""
        result = sample_game_state.to_save_format()

        # Should match save mode export with default include_known_by=False (persistent only)
        expected = sample_game_state.export_state(
            mode="save", role="gm", include_known_by=False
        )
        assert result == expected

    def test_to_save_format_exclude_runtime(self, sample_game_state):
        """Test save format without runtime data."""
        result = sample_game_state.to_save_format(include_runtime_data=False)

        alice_meta = result["entities"]["pc.alice"]["meta"]

        # Should not include known_by when runtime data excluded
        assert "known_by" not in alice_meta

    def test_to_session_format(self, sample_game_state):
        """Test convenience method for session format."""
        result = sample_game_state.to_session_format(pov_id="pc.alice")

        # Should match session mode export
        expected = sample_game_state.export_state(
            mode="session", pov_id="pc.alice", role="player"
        )
        assert result == expected

    def test_to_public_format(self, sample_game_state):
        """Test convenience method for public format."""
        result = sample_game_state.to_public_format(pov_id="pc.alice", role="player")

        # Should match public mode export
        expected = sample_game_state.export_state(
            mode="public", pov_id="pc.alice", role="player", include_known_by=False
        )
        assert result == expected

    def test_to_minimal_format(self, sample_game_state):
        """Test convenience method for minimal format."""
        result = sample_game_state.to_minimal_format()

        # Should match minimal mode export
        expected = sample_game_state.export_state(
            mode="minimal", role="gm", include_known_by=False
        )
        assert result == expected

    def test_export_handles_legacy_clocks(self, sample_game_state):
        """Test export properly handles legacy clock format."""
        # Add legacy clock
        sample_game_state.clocks["legacy"] = {"value": 3, "max": 10}

        result = sample_game_state.export_state(mode="full")

        # Legacy clocks should be preserved as-is
        assert result["clocks"]["legacy"] == {"value": 3, "max": 10}

        # Regular clocks should have exported meta
        assert "meta" in result["clocks"]["tension"]

    def test_export_state_include_known_by_override(self, sample_game_state):
        """Test explicit override of known_by inclusion."""
        # Force exclude known_by in save mode
        result = sample_game_state.export_state(mode="save", include_known_by=False)

        alice_meta = result["entities"]["pc.alice"]["meta"]
        assert "known_by" not in alice_meta

        # Force include known_by in minimal mode
        result = sample_game_state.export_state(mode="minimal", include_known_by=True)

        alice_meta = result["entities"]["pc.alice"]["meta"]
        assert "known_by" in alice_meta


class TestSerializationIntegration:
    """Test integration between Meta and GameState serialization."""

    def test_consistent_export_modes(self):
        """Test that Meta and GameState export modes are consistent."""
        meta = Meta(visibility="public", known_by={"pc.test"}, notes="Test note")

        # All modes should work consistently
        modes: List[Literal["full", "public", "minimal", "save", "session"]] = [
            "full",
            "public",
            "minimal",
            "save",
            "session",
        ]

        for mode in modes:
            meta_result = meta.export(mode=mode)

            # Should not raise any errors
            assert isinstance(meta_result, dict)
            assert "visibility" in meta_result  # Always present
            assert "gm_only" in meta_result  # Always present

    def test_round_trip_serialization(self):
        """Test complete round-trip serialization through export and reconstruction."""
        original_meta = Meta(
            visibility="hidden",
            known_by={"pc.alice", "npc.bob"},
            source="generator",
            notes="Round trip test",
            extra={"test": True},
        )

        # Export in save format
        exported = original_meta.for_save()

        # Reconstruct
        reconstructed = Meta.from_export(exported)

        # Should be equivalent
        assert reconstructed.visibility == original_meta.visibility
        assert reconstructed.known_by == original_meta.known_by
        assert reconstructed.source == original_meta.source
        assert reconstructed.notes == original_meta.notes
        assert reconstructed.extra == original_meta.extra

    def test_json_serialization_compatibility(self):
        """Test that exported data is JSON-serializable."""
        import json

        meta = Meta(
            visibility="public",
            known_by={"pc.alice", "npc.bob"},
            extra={"nested": {"value": 42}},
        )

        # Export and convert to JSON
        exported = meta.export(mode="full")
        json_str = json.dumps(exported)

        # Should round-trip through JSON
        parsed = json.loads(json_str)
        reconstructed = Meta.from_export(parsed)

        assert reconstructed.visibility == meta.visibility
        assert reconstructed.known_by == meta.known_by
        assert reconstructed.extra == meta.extra
