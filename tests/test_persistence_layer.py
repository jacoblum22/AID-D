"""
Tests for Persistence Layer Integration - Multi-file persistence functionality.

Tests the persistence layer with separate public.json and gm.json files,
ensuring proper integration with Meta Serialization Policy and robust
save/load operations.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Union, cast
from unittest.mock import patch, mock_open

from models.meta import Meta
from backend.router.game_state import GameState, PC, NPC, Zone, Scene, Clock, Entity
from backend.router.persistence import (
    PersistenceManager,
    PersistenceError,
    SaveFileCorrupted,
)


class TestPersistenceManager:
    """Test PersistenceManager functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def persistence_manager(self, temp_dir):
        """Create PersistenceManager with temporary directory."""
        return PersistenceManager(base_path=temp_dir)

    @pytest.fixture
    def sample_game_state(self):
        """Create a sample GameState for testing."""
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
                meta=Meta(visibility="public", source="manual"),
            )
        }

        clocks = {
            "tension": Clock(
                id="tension",
                name="Rising Tension",
                maximum=6,
                value=2,
                meta=Meta(visibility="hidden", notes="Track overall tension"),
            )
        }

        return GameState(
            entities=cast(Dict[str, Entity], entities),
            zones=zones,
            clocks=cast(Dict[str, "Clock | Dict[str, Any]"], clocks),
            scene=Scene(id="test_scene"),
        )

    def test_persistence_manager_initialization(self, temp_dir):
        """Test PersistenceManager initialization creates directory."""
        manager = PersistenceManager(base_path=temp_dir / "new_saves")

        assert (temp_dir / "new_saves").exists()
        assert (temp_dir / "new_saves").is_dir()

    def test_save_game_state_creates_files(
        self, persistence_manager, sample_game_state
    ):
        """Test saving game state creates expected files."""
        metadata = {"campaign": "Test Campaign", "session": 1}

        saved_files = persistence_manager.save_game_state(
            sample_game_state,
            "test_save",
            save_public=True,
            save_gm=True,
            save_session=True,
            metadata=metadata,
        )

        # Should create all requested files
        assert "public" in saved_files
        assert "gm" in saved_files
        assert "session" in saved_files
        assert "manifest" in saved_files

        # Files should exist
        for file_type, file_path in saved_files.items():
            assert Path(file_path).exists()

    def test_save_game_state_public_excludes_sensitive_data(
        self, persistence_manager, sample_game_state
    ):
        """Test public save excludes sensitive data."""
        saved_files = persistence_manager.save_game_state(
            sample_game_state,
            "test_public",
            save_public=True,
            save_gm=False,
            save_session=False,
        )

        # Load and verify public file content
        public_path = Path(saved_files["public"])
        with open(public_path, "r") as f:
            data = json.load(f)

        game_state = data["game_state"]

        # GM-only entities should not be in public save
        assert "npc.secret" not in game_state["entities"]

        # Public entities should be present but with public meta
        alice_meta = game_state["entities"]["pc.alice"]["meta"]
        assert "visibility" in alice_meta
        assert "known_by_count" in alice_meta  # Public mode shows count
        assert "known_by" not in alice_meta  # But not actual list

    def test_save_game_state_gm_includes_all_data(
        self, persistence_manager, sample_game_state
    ):
        """Test GM save includes all data."""
        saved_files = persistence_manager.save_game_state(
            sample_game_state,
            "test_gm",
            save_public=False,
            save_gm=True,
            save_session=False,
        )

        # Load and verify GM file content
        gm_path = Path(saved_files["gm"])
        with open(gm_path, "r") as f:
            data = json.load(f)

        game_state = data["game_state"]

        # GM-only entities should be included
        assert "npc.secret" in game_state["entities"]

        # Full meta data should be present
        alice_meta = game_state["entities"]["pc.alice"]["meta"]
        assert "visibility" in alice_meta
        assert "notes" in alice_meta

        secret_meta = game_state["entities"]["npc.secret"]["meta"]
        assert secret_meta["visibility"] == "gm_only"
        assert secret_meta["notes"] == "Hidden from players"

    def test_save_game_state_session_format(
        self, persistence_manager, sample_game_state
    ):
        """Test session save format."""
        saved_files = persistence_manager.save_game_state(
            sample_game_state,
            "test_session",
            save_public=False,
            save_gm=False,
            save_session=True,
        )

        # Load and verify session file content
        session_path = Path(saved_files["session"])
        with open(session_path, "r") as f:
            data = json.load(f)

        # Should have session info
        assert "session_info" in data
        session_info = data["session_info"]
        assert session_info["entity_count"] == 3
        assert session_info["zone_count"] == 1
        assert session_info["clock_count"] == 1

    def test_save_game_state_with_metadata(
        self, persistence_manager, sample_game_state
    ):
        """Test saving with custom metadata."""
        metadata = {
            "campaign": "Lost Mines",
            "session": 5,
            "dm": "Alice",
            "players": ["Bob", "Charlie"],
        }

        saved_files = persistence_manager.save_game_state(
            sample_game_state, "test_metadata", save_gm=True, metadata=metadata
        )

        # Verify metadata in saved file
        gm_path = Path(saved_files["gm"])
        with open(gm_path, "r") as f:
            data = json.load(f)

        saved_metadata = data["metadata"]
        assert saved_metadata["campaign"] == "Lost Mines"
        assert saved_metadata["session"] == 5
        assert saved_metadata["dm"] == "Alice"
        assert saved_metadata["players"] == ["Bob", "Charlie"]

    def test_save_game_state_creates_manifest(
        self, persistence_manager, sample_game_state
    ):
        """Test manifest file creation."""
        saved_files = persistence_manager.save_game_state(
            sample_game_state, "test_manifest", save_public=True, save_gm=True
        )

        # Load and verify manifest
        manifest_path = Path(saved_files["manifest"])
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        assert manifest["save_name"] == "test_manifest"
        assert "created" in manifest
        assert set(manifest["files"]) == {"public", "gm"}
        assert "metadata" in manifest

    def test_load_game_state_gm_file(self, persistence_manager, sample_game_state):
        """Test loading game state from GM file."""
        # Save first
        persistence_manager.save_game_state(
            sample_game_state, "test_load_gm", save_gm=True
        )

        # Load and verify
        loaded_state = persistence_manager.load_game_state(
            "test_load_gm", file_type="gm"
        )

        assert len(loaded_state.entities) == 3
        assert "pc.alice" in loaded_state.entities
        assert "npc.secret" in loaded_state.entities

        # Verify meta reconstruction
        alice = loaded_state.entities["pc.alice"]
        assert alice.meta.visibility == "public"
        assert alice.meta.notes == "Player character"
        assert "npc.bob" in alice.meta.known_by

    def test_load_game_state_public_file(self, persistence_manager, sample_game_state):
        """Test loading game state from public file."""
        # Save first
        persistence_manager.save_game_state(
            sample_game_state, "test_load_public", save_public=True
        )

        # Load and verify
        loaded_state = persistence_manager.load_game_state(
            "test_load_public", file_type="public"
        )

        # Should not have GM-only entities (they're filtered during save)
        assert "npc.secret" not in loaded_state.entities
        assert len(loaded_state.entities) == 2  # Only alice and bob

    def test_load_game_state_session_file(self, persistence_manager, sample_game_state):
        """Test loading game state from session file."""
        # Save first
        persistence_manager.save_game_state(
            sample_game_state, "test_load_session", save_session=True
        )

        # Load and verify
        loaded_state = persistence_manager.load_game_state(
            "test_load_session", file_type="session"
        )

        # Should have all entities (session includes runtime data)
        assert len(loaded_state.entities) >= 2  # At least public entities

    def test_load_game_state_nonexistent_save_raises_error(self, persistence_manager):
        """Test loading nonexistent save raises error."""
        with pytest.raises(PersistenceError, match="Save 'nonexistent' does not exist"):
            persistence_manager.load_game_state("nonexistent")

    def test_load_game_state_missing_file_type_raises_error(
        self, persistence_manager, sample_game_state
    ):
        """Test loading missing file type raises error."""
        # Save only GM file
        persistence_manager.save_game_state(
            sample_game_state, "test_missing_type", save_public=False, save_gm=True
        )

        # Try to load public file
        with pytest.raises(PersistenceError, match="File type 'public' not found"):
            persistence_manager.load_game_state("test_missing_type", file_type="public")

    def test_load_game_state_corrupted_file_raises_error(
        self, persistence_manager, temp_dir
    ):
        """Test loading corrupted file raises error."""
        # Create corrupted save
        save_dir = temp_dir / "corrupted_save"
        save_dir.mkdir()

        corrupted_file = save_dir / "gm.json"
        with open(corrupted_file, "w") as f:
            f.write("{ invalid json")

        with pytest.raises(SaveFileCorrupted, match="corrupted"):
            persistence_manager.load_game_state("corrupted_save")

    def test_list_saves_returns_save_info(self, persistence_manager, sample_game_state):
        """Test listing saves returns proper information."""
        # Create multiple saves
        for i in range(3):
            persistence_manager.save_game_state(
                sample_game_state,
                f"test_save_{i}",
                save_public=True,
                save_gm=True,
                metadata={"session": i},
            )

        saves = persistence_manager.list_saves()

        assert len(saves) == 3

        # Verify save info structure
        save_info = saves[0]
        assert "name" in save_info
        assert "created" in save_info
        assert "files" in save_info
        assert "file_info" in save_info
        assert "metadata" in save_info

        # Should include file size and modification info
        assert "public" in save_info["file_info"]
        assert "gm" in save_info["file_info"]
        assert "size" in save_info["file_info"]["public"]

    def test_list_saves_empty_directory(self, persistence_manager):
        """Test listing saves in empty directory."""
        saves = persistence_manager.list_saves()
        assert saves == []

    def test_delete_save_requires_confirmation(
        self, persistence_manager, sample_game_state
    ):
        """Test delete_save requires confirmation for safety."""
        persistence_manager.save_game_state(sample_game_state, "test_delete")

        with pytest.raises(PersistenceError, match="requires confirm=True"):
            persistence_manager.delete_save("test_delete")

    def test_delete_save_with_confirmation(
        self, persistence_manager, sample_game_state, temp_dir
    ):
        """Test delete_save works with confirmation."""
        persistence_manager.save_game_state(sample_game_state, "test_delete_confirm")

        save_dir = temp_dir / "test_delete_confirm"
        assert save_dir.exists()

        result = persistence_manager.delete_save("test_delete_confirm", confirm=True)

        assert result is True
        assert not save_dir.exists()

    def test_delete_save_nonexistent_raises_error(self, persistence_manager):
        """Test deleting nonexistent save raises error."""
        with pytest.raises(PersistenceError, match="does not exist"):
            persistence_manager.delete_save("nonexistent", confirm=True)

    def test_export_save_uncompressed(
        self, persistence_manager, sample_game_state, temp_dir
    ):
        """Test exporting save to uncompressed directory."""
        persistence_manager.save_game_state(
            sample_game_state, "test_export", save_public=True, save_gm=True
        )

        export_dir = temp_dir / "exports" / "test_export"

        exported_path = persistence_manager.export_save(
            "test_export", export_dir, compress=False
        )

        assert exported_path == str(export_dir)
        assert (export_dir / "public.json").exists()
        assert (export_dir / "gm.json").exists()
        assert (export_dir / "manifest.json").exists()

    def test_export_save_compressed(
        self, persistence_manager, sample_game_state, temp_dir
    ):
        """Test exporting save to compressed archive."""
        persistence_manager.save_game_state(
            sample_game_state, "test_export_zip", save_public=True, save_gm=True
        )

        export_path = temp_dir / "exports" / "test_export_zip"

        exported_path = persistence_manager.export_save(
            "test_export_zip", export_path, compress=True
        )

        assert exported_path.endswith(".zip")
        assert Path(exported_path).exists()

    def test_export_save_specific_file_types(
        self, persistence_manager, sample_game_state, temp_dir
    ):
        """Test exporting only specific file types."""
        persistence_manager.save_game_state(
            sample_game_state,
            "test_export_selective",
            save_public=True,
            save_gm=True,
            save_session=True,
        )

        export_dir = temp_dir / "exports" / "selective"

        persistence_manager.export_save(
            "test_export_selective",
            export_dir,
            file_types=["public", "manifest"],
            compress=False,
        )

        assert (export_dir / "public.json").exists()
        assert (export_dir / "manifest.json").exists()
        assert not (export_dir / "gm.json").exists()
        assert not (export_dir / "session.json").exists()

    def test_backup_creation(self, persistence_manager, sample_game_state, temp_dir):
        """Test backup file creation when overwriting saves."""
        save_name = "test_backup"

        # Save initial version
        persistence_manager.save_game_state(sample_game_state, save_name, save_gm=True)

        # Save again to trigger backup
        persistence_manager.save_game_state(sample_game_state, save_name, save_gm=True)

        save_dir = temp_dir / save_name

        # Should have backup file
        backup_files = list(save_dir.glob("*.bak.*.json"))
        assert len(backup_files) > 0

    def test_round_trip_persistence(self, persistence_manager, sample_game_state):
        """Test complete round-trip save and load preserves data."""
        # Save
        persistence_manager.save_game_state(
            sample_game_state, "test_round_trip", save_gm=True
        )

        # Load
        loaded_state = persistence_manager.load_game_state("test_round_trip")

        # Verify key data is preserved
        assert len(loaded_state.entities) == len(sample_game_state.entities)
        assert len(loaded_state.zones) == len(sample_game_state.zones)
        assert len(loaded_state.clocks) == len(sample_game_state.clocks)

        # Verify specific entity data
        original_alice = sample_game_state.entities["pc.alice"]
        loaded_alice = loaded_state.entities["pc.alice"]

        assert loaded_alice.name == original_alice.name
        assert loaded_alice.current_zone == original_alice.current_zone
        assert loaded_alice.meta.visibility == original_alice.meta.visibility
        assert loaded_alice.meta.known_by == original_alice.meta.known_by

    def test_legacy_clock_handling(self, persistence_manager, temp_dir):
        """Test handling of legacy clock format in persistence."""
        # Create game state with legacy clock
        entities = {"pc.test": PC(id="pc.test", name="Test", current_zone="test")}
        zones = {
            "test": Zone(
                id="test", name="Test Zone", description="Test", adjacent_zones=[]
            )
        }
        clocks: Dict[str, Union[Clock, Dict[str, Any]]] = {
            "legacy": {"value": 3, "max": 10}  # Legacy format
        }

        game_state = GameState(
            entities=cast(Dict[str, "Entity"], entities),
            zones=zones,
            clocks=cast(Dict[str, "Clock | Dict[str, Any]"], clocks),
            scene=Scene(id="test"),
        )

        # Save and load
        persistence_manager.save_game_state(game_state, "test_legacy", save_gm=True)
        loaded_state = persistence_manager.load_game_state("test_legacy")

        # Legacy clock should be preserved
        assert "legacy" in loaded_state.clocks
        assert loaded_state.clocks["legacy"]["value"] == 3
        assert loaded_state.clocks["legacy"]["max"] == 10


class TestPersistenceErrorHandling:
    """Test error handling in persistence operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_save_with_io_error(self, temp_dir):
        """Test handling of I/O errors during save."""
        manager = PersistenceManager(base_path=temp_dir)

        game_state = GameState(entities={}, zones={}, scene=Scene(id="test"))

        # Mock the _write_json_file method to raise an IOError
        from unittest.mock import patch

        with patch.object(
            manager, "_write_json_file", side_effect=IOError("Simulated I/O error")
        ):
            with pytest.raises(PersistenceError, match="Failed to save"):
                manager.save_game_state(game_state, "test_save")

    def test_validation_with_missing_required_fields(self, temp_dir):
        """Test validation catches missing required fields."""
        manager = PersistenceManager(base_path=temp_dir)

        # Create invalid save data
        save_dir = temp_dir / "invalid_save"
        save_dir.mkdir()

        invalid_data = {
            "metadata": {"version": "1.0"},
            "game_state": {
                "entities": {},
                # Missing required "zones" and "scene"
            },
        }

        with open(save_dir / "gm.json", "w") as f:
            json.dump(invalid_data, f)

        with pytest.raises(SaveFileCorrupted, match="missing required key"):
            manager.load_game_state("invalid_save")

    def test_validation_with_invalid_data_structure(self, temp_dir):
        """Test validation catches invalid data structure."""
        manager = PersistenceManager(base_path=temp_dir)

        # Create save with invalid structure
        save_dir = temp_dir / "bad_structure"
        save_dir.mkdir()

        with open(save_dir / "gm.json", "w") as f:
            json.dump("not a dictionary", f)

        with pytest.raises(SaveFileCorrupted, match="must be a dictionary"):
            manager.load_game_state("bad_structure")


class TestPersistenceIntegration:
    """Test integration between persistence and serialization policies."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_persistence_uses_correct_serialization_modes(self, temp_dir):
        """Test persistence layer uses appropriate serialization modes."""
        manager = PersistenceManager(base_path=temp_dir)

        # Create game state with mixed visibility
        entities = {
            "public_npc": NPC(
                id="public_npc",
                name="Public NPC",
                current_zone="town",
                meta=Meta(visibility="public", notes="Public character"),
            ),
            "hidden_npc": NPC(
                id="hidden_npc",
                name="Hidden NPC",
                current_zone="town",
                meta=Meta(visibility="hidden", notes="Hidden character"),
            ),
            "gm_npc": NPC(
                id="gm_npc",
                name="GM NPC",
                current_zone="town",
                meta=Meta(
                    visibility="gm_only", gm_only=True, notes="GM-only character"
                ),
            ),
        }

        zones = {
            "town": Zone(
                id="town",
                name="Town Square",
                description="A busy town square",
                adjacent_zones=[],
                meta=Meta(visibility="public"),
            )
        }

        game_state = GameState(
            entities=cast(Dict[str, Entity], entities),
            zones=zones,
            scene=Scene(id="test"),
        )

        # Save all file types
        manager.save_game_state(
            game_state,
            "test_serialization",
            save_public=True,
            save_gm=True,
            save_session=True,
        )

        # Load and verify each file type has appropriate content
        save_dir = temp_dir / "test_serialization"

        # Public file should exclude GM-only content
        with open(save_dir / "public.json", "r") as f:
            public_data = json.load(f)

        public_entities = public_data["game_state"]["entities"]
        assert "gm_npc" not in public_entities  # GM-only excluded

        # GM file should include everything
        with open(save_dir / "gm.json", "r") as f:
            gm_data = json.load(f)

        gm_entities = gm_data["game_state"]["entities"]
        assert "gm_npc" in gm_entities  # GM-only included
        assert "public_npc" in gm_entities
        assert "hidden_npc" in gm_entities

        # Session file should include runtime data
        with open(save_dir / "session.json", "r") as f:
            session_data = json.load(f)

        assert "session_info" in session_data
        assert session_data["session_info"]["entity_count"] >= 2

    def test_meta_export_modes_in_different_file_types(self, temp_dir):
        """Test that different file types use appropriate meta export modes."""
        manager = PersistenceManager(base_path=temp_dir)

        # Create entity with rich meta data
        entity = NPC(
            id="test_npc",
            name="Test NPC",
            current_zone="test",
            meta=Meta(
                visibility="public",
                known_by={"pc.alice", "pc.bob"},
                notes="Secret GM notes",
                source="generator",
                extra={"mood": "happy", "faction": "guards"},
            ),
        )

        game_state = GameState(
            entities={"test_npc": entity},
            zones={
                "test": Zone(
                    id="test", name="Test Zone", description="Test", adjacent_zones=[]
                )
            },
            scene=Scene(id="test"),
        )

        manager.save_game_state(
            game_state, "test_meta_modes", save_public=True, save_gm=True
        )

        save_dir = temp_dir / "test_meta_modes"

        # Check public file uses public meta mode
        with open(save_dir / "public.json", "r") as f:
            public_data = json.load(f)

        public_meta = public_data["game_state"]["entities"]["test_npc"]["meta"]
        assert "known_by_count" in public_meta  # Public mode shows count
        assert "known_by" not in public_meta  # But not full list

        # Check GM file uses full meta mode
        with open(save_dir / "gm.json", "r") as f:
            gm_data = json.load(f)

        gm_meta = gm_data["game_state"]["entities"]["test_npc"]["meta"]
        assert "known_by" in gm_meta  # Full mode includes known_by
        assert "notes" in gm_meta  # And notes
        assert "extra" in gm_meta  # And extra data
