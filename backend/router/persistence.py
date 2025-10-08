"""
Persistence Layer Integration for AID&D game state management.

Provides multi-file persistence with separate public.json and gm.json files
for different visibility levels, utilizing the Meta Serialization Policy
for appropriate data inclusion/exclusion.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Literal, Union, List
from datetime import datetime, timezone

from backend.router.game_state import GameState, PC, NPC, Zone, Scene, Clock
from models.meta import Meta


class PersistenceError(Exception):
    """Base exception for persistence operations."""

    pass


class SaveFileCorrupted(PersistenceError):
    """Raised when save file is corrupted or invalid."""

    pass


class PersistenceManager:
    """
    Manages persistence layer with multi-file architecture for different visibility levels.

    Uses the Meta Serialization Policy to control what data is saved in different contexts:
    - public.json: Public-safe data for sharing/logs (excludes sensitive data)
    - gm.json: Complete GM data with full state information
    - session.json: Runtime session data for quick resumption
    - backup files: Automatic backups for safety
    """

    def __init__(self, base_path: Union[str, Path] = "saves"):
        """
        Initialize persistence manager.

        Args:
            base_path: Base directory for save files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_game_state(
        self,
        game_state: GameState,
        save_name: str,
        save_public: bool = True,
        save_gm: bool = True,
        save_session: bool = False,
        create_backup: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Save game state to appropriate files based on configuration.

        Args:
            game_state: The game state to save
            save_name: Name for the save (used as filename prefix)
            save_public: Whether to save public.json file
            save_gm: Whether to save gm.json file
            save_session: Whether to save session.json file
            create_backup: Whether to create backup copies
            metadata: Optional metadata to include in save

        Returns:
            Dictionary mapping file types to saved file paths
        """
        save_dir = self.base_path / save_name
        save_dir.mkdir(parents=True, exist_ok=True)

        saved_files = {}
        timestamp = datetime.now(timezone.utc).isoformat()

        # Create metadata for save
        save_metadata = {
            "save_name": save_name,
            "timestamp": timestamp,
            "version": "1.0",
            "created_by": "AID&D Persistence Layer",
            **(metadata or {}),
        }

        try:
            # Save public file (public-safe data)
            if save_public:
                public_data = {
                    "metadata": save_metadata,
                    "game_state": game_state.to_public_format(
                        role="player"
                    ),  # Player role for strict filtering
                }
                public_path = save_dir / "public.json"
                self._write_json_file(public_path, public_data, create_backup)
                saved_files["public"] = str(public_path)

            # Save GM file (complete data)
            if save_gm:
                gm_data = {
                    "metadata": save_metadata,
                    "game_state": game_state.to_save_format(include_runtime_data=True),
                }
                gm_path = save_dir / "gm.json"
                self._write_json_file(gm_path, gm_data, create_backup)
                saved_files["gm"] = str(gm_path)

            # Save session file (runtime data)
            if save_session:
                session_data = {
                    "metadata": save_metadata,
                    "game_state": game_state.to_session_format(),
                    "session_info": {
                        "last_updated": timestamp,
                        "entity_count": len(game_state.entities),
                        "zone_count": len(game_state.zones),
                        "clock_count": len(game_state.clocks),
                    },
                }
                session_path = save_dir / "session.json"
                self._write_json_file(session_path, session_data, create_backup)
                saved_files["session"] = str(session_path)

            # Save manifest file
            manifest = {
                "save_name": save_name,
                "created": timestamp,
                "files": list(saved_files.keys()),
                "metadata": save_metadata,
            }
            manifest_path = save_dir / "manifest.json"
            self._write_json_file(manifest_path, manifest, create_backup=False)
            saved_files["manifest"] = str(manifest_path)

            return saved_files

        except Exception as e:
            raise PersistenceError(f"Failed to save game state: {str(e)}") from e

    def load_game_state(
        self,
        save_name: str,
        file_type: Literal["public", "gm", "session"] = "gm",
        validate_data: bool = True,
    ) -> GameState:
        """
        Load game state from saved files.

        Args:
            save_name: Name of the save to load
            file_type: Which file to load from
            validate_data: Whether to validate loaded data

        Returns:
            Loaded GameState instance

        Raises:
            PersistenceError: If save doesn't exist or is invalid
            SaveFileCorrupted: If save file is corrupted
        """
        save_dir = self.base_path / save_name

        if not save_dir.exists():
            raise PersistenceError(f"Save '{save_name}' does not exist")

        file_path = save_dir / f"{file_type}.json"

        if not file_path.exists():
            available_files = [
                f.stem for f in save_dir.glob("*.json") if f.stem != "manifest"
            ]
            raise PersistenceError(
                f"File type '{file_type}' not found in save '{save_name}'. "
                f"Available: {available_files}"
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if validate_data:
                self._validate_save_data(data)

            # Extract game state data
            game_state_data = data["game_state"]

            # Reconstruct GameState from saved data
            return self._reconstruct_game_state(game_state_data)

        except json.JSONDecodeError as e:
            raise SaveFileCorrupted(
                f"Save file '{file_path}' is corrupted: {str(e)}"
            ) from e
        except SaveFileCorrupted:
            # Re-raise SaveFileCorrupted as-is
            raise
        except Exception as e:
            raise PersistenceError(f"Failed to load game state: {str(e)}") from e

    def list_saves(self) -> List[Dict[str, Any]]:
        """
        List all available saves with metadata.

        Returns:
            List of save information dictionaries
        """
        saves = []

        for save_dir in self.base_path.iterdir():
            if not save_dir.is_dir():
                continue

            manifest_path = save_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)

                # Add file size information
                file_info = {}
                for file_type in manifest.get("files", []):
                    file_path = save_dir / f"{file_type}.json"
                    if file_path.exists():
                        file_info[file_type] = {
                            "size": file_path.stat().st_size,
                            "modified": datetime.fromtimestamp(
                                file_path.stat().st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }

                save_info = {
                    "name": manifest.get("save_name", save_dir.name),
                    "created": manifest.get("created"),
                    "files": manifest.get("files", []),
                    "file_info": file_info,
                    "metadata": manifest.get("metadata", {}),
                }

                saves.append(save_info)

            except Exception:
                # Skip corrupted manifest files
                continue

        # Sort by creation date (newest first)
        saves.sort(key=lambda x: x.get("created", ""), reverse=True)
        return saves

    def delete_save(self, save_name: str, confirm: bool = False) -> bool:
        """
        Delete a save directory and all its files.

        Args:
            save_name: Name of the save to delete
            confirm: Safety confirmation flag

        Returns:
            True if deleted successfully

        Raises:
            PersistenceError: If save doesn't exist or deletion fails
        """
        if not confirm:
            raise PersistenceError("delete_save requires confirm=True for safety")

        save_dir = self.base_path / save_name

        if not save_dir.exists():
            raise PersistenceError(f"Save '{save_name}' does not exist")

        try:
            import shutil

            shutil.rmtree(save_dir)
            return True
        except Exception as e:
            raise PersistenceError(
                f"Failed to delete save '{save_name}': {str(e)}"
            ) from e

    def export_save(
        self,
        save_name: str,
        export_path: Union[str, Path],
        file_types: Optional[List[str]] = None,
        compress: bool = True,
    ) -> str:
        """
        Export save to external location, optionally compressed.

        Args:
            save_name: Name of the save to export
            export_path: Destination path for export
            file_types: Which file types to include (None = all)
            compress: Whether to create compressed archive

        Returns:
            Path to exported file/directory

        Raises:
            PersistenceError: If export fails
        """
        save_dir = self.base_path / save_name

        if not save_dir.exists():
            raise PersistenceError(f"Save '{save_name}' does not exist")

        export_path = Path(export_path)

        try:
            if compress:
                import zipfile

                zip_path = export_path.with_suffix(".zip")
                zip_path.parent.mkdir(
                    parents=True, exist_ok=True
                )  # Ensure parent directory exists

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in save_dir.glob("*.json"):
                        if file_types is None or file_path.stem in file_types:
                            zipf.write(file_path, file_path.name)

                return str(zip_path)
            else:
                import shutil

                export_path.mkdir(parents=True, exist_ok=True)

                for file_path in save_dir.glob("*.json"):
                    if file_types is None or file_path.stem in file_types:
                        shutil.copy2(file_path, export_path / file_path.name)

                return str(export_path)

        except Exception as e:
            raise PersistenceError(
                f"Failed to export save '{save_name}': {str(e)}"
            ) from e

    def _write_json_file(
        self, file_path: Path, data: Dict[str, Any], create_backup: bool = True
    ) -> None:
        """
        Write JSON data to file with optional backup.

        Args:
            file_path: Path to write to
            data: Data to write
            create_backup: Whether to create backup of existing file
        """
        # Create backup if file exists and backup requested
        if create_backup and file_path.exists():
            backup_path = file_path.with_suffix(
                f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            try:
                file_path.rename(backup_path)
            except OSError:
                # Fallback for cross-filesystem rename failures
                import shutil

                shutil.move(str(file_path), str(backup_path))

        # Write new file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _validate_save_data(self, data: Dict[str, Any]) -> None:
        """
        Validate save file data structure.

        Args:
            data: Loaded save data

        Raises:
            SaveFileCorrupted: If data is invalid
        """
        if not isinstance(data, dict):
            raise SaveFileCorrupted("Save data must be a dictionary")

        if "metadata" not in data:
            raise SaveFileCorrupted("Save data missing metadata")

        if "game_state" not in data:
            raise SaveFileCorrupted("Save data missing game_state")

        game_state = data["game_state"]

        # Validate basic game state structure
        required_keys = ["entities", "zones", "scene"]
        for key in required_keys:
            if key not in game_state:
                raise SaveFileCorrupted(f"Game state missing required key: {key}")

    def _reconstruct_game_state(self, data: Dict[str, Any]) -> GameState:
        """
        Reconstruct GameState from saved data.

        Args:
            data: Game state data dictionary

        Returns:
            Reconstructed GameState instance
        """
        # Reconstruct entities
        entities = {}
        for eid, entity_data in data.get("entities", {}).items():
            entity_type = entity_data.get("type", "unknown")

            # Clean redaction artifacts
            clean_data = {k: v for k, v in entity_data.items() if k != "is_visible"}

            # Reconstruct meta if present
            if "meta" in clean_data:
                clean_data["meta"] = Meta.from_export(clean_data["meta"])

            # Create appropriate entity type
            if entity_type == "pc":
                entities[eid] = PC(**clean_data)
            elif entity_type == "npc":
                entities[eid] = NPC(**clean_data)
            else:
                # For unknown types, try NPC as fallback
                try:
                    entities[eid] = NPC(**clean_data)
                except Exception:
                    # Skip corrupted entities
                    continue

        # Reconstruct zones
        zones = {}
        for zid, zone_data in data.get("zones", {}).items():
            # Clean redaction artifacts
            clean_data = {k: v for k, v in zone_data.items() if k != "is_visible"}

            if "meta" in clean_data:
                clean_data["meta"] = Meta.from_export(clean_data["meta"])
            zones[zid] = Zone(**clean_data)

        # Reconstruct clocks
        clocks = {}
        for cid, clock_data in data.get("clocks", {}).items():
            if isinstance(clock_data, dict):
                if "meta" in clock_data and "id" in clock_data:
                    # Full Clock object - clean redaction artifacts
                    clean_data = {
                        k: v for k, v in clock_data.items() if k != "is_visible"
                    }
                    clean_data["meta"] = Meta.from_export(clean_data["meta"])
                    clocks[cid] = Clock(**clean_data)
                else:
                    # Legacy format
                    clocks[cid] = clock_data

        # Reconstruct scene
        scene_data = data.get("scene", {"id": "default_scene"})
        # Clean redaction artifacts
        clean_scene_data = {k: v for k, v in scene_data.items() if k != "is_visible"}
        if "meta" in clean_scene_data:
            clean_scene_data["meta"] = Meta.from_export(clean_scene_data["meta"])
        scene = Scene(**clean_scene_data)

        return GameState(entities=entities, zones=zones, clocks=clocks, scene=scene)
