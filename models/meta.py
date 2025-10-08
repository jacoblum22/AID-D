from pydantic import BaseModel, Field, model_validator
from typing import Optional, Set, Dict, Any, Literal, TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from backend.router.game_state import GameState


class Meta(BaseModel):
    """
    Metadata for every world object (entities, zones, scene, clocks, etc.).

    Controls visibility, tracking, and administrative metadata while keeping
    it separate from core gameplay state. Supports the centralized redaction
    system to prevent information leaks.
    """

    visibility: Literal["public", "hidden", "gm_only"] = "public"
    gm_only: bool = False  # redundant but convenient flag
    known_by: Set[str] = Field(default_factory=set)
    created_at: Optional[str] = None
    last_changed_at: Optional[str] = None
    source: Optional[str] = None  # "manual" | "generator" | "import"
    notes: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        """Clean up internal markers after validation."""
        # Remove the __from_export marker if present to keep extra clean
        if self.extra and "__from_export" in self.extra:
            del self.extra["__from_export"]

    @model_validator(mode="after")
    def validate_gm_only_consistency(self) -> "Meta":
        """
        Ensure gm_only flag is consistent with visibility setting.

        Validation behavior depends on the context:
        - Normal construction: Strict validation (raises ValueError)
        - Deserialization: Auto-fix inconsistencies (from_export context)

        Returns:
            The Meta instance, potentially with corrected gm_only flag

        Raises:
            ValueError: If inconsistent and in strict validation mode
        """
        # gm_only should be True if and only if visibility is "gm_only"
        expected_gm_only = self.visibility == "gm_only"

        if self.gm_only != expected_gm_only:
            # Check if we're in lenient mode by looking for a special marker in extra
            is_from_export = self.extra.get("__from_export", False)

            if is_from_export:
                # Auto-fix in deserialization context
                import sys

                print(
                    f"Warning: Auto-fixing gm_only inconsistency during deserialization: "
                    f"visibility='{self.visibility}' but gm_only={self.gm_only}. "
                    f"Setting gm_only={expected_gm_only}",
                    file=sys.stderr,
                )
                self.gm_only = expected_gm_only
                # Note: __from_export marker will be cleaned up in model_post_init
            else:
                # Strict validation for normal construction
                raise ValueError(
                    f"Inconsistent gm_only flag: visibility='{self.visibility}' "
                    f"but gm_only={self.gm_only}. Expected gm_only={expected_gm_only}"
                )

        return self

    def touch(
        self, game_state: Optional["GameState"] = None, entity_id: Optional[str] = None
    ):
        """
        Update last_changed_at whenever something mutates.

        Args:
            game_state: Optional GameState to invalidate cache on
            entity_id: Optional entity ID to invalidate specific cache entries
        """
        self.last_changed_at = datetime.now(timezone.utc).isoformat()

        # Invalidate redaction cache if game_state provided
        if game_state:
            game_state.invalidate_cache(entity_id)

        # Publish meta change event using deferred import to avoid circular dependencies
        try:
            import importlib

            # Try import paths in order of preference (tests use router.events via path modification)
            events_module = None
            for module_path in ["router.events", "backend.router.events"]:
                try:
                    events_module = importlib.import_module(module_path)
                    break
                except ImportError:
                    continue

            if (
                events_module
                and hasattr(events_module, "publish")
                and hasattr(events_module, "EventTypes")
            ):
                events_module.publish(
                    events_module.EventTypes.META_CHANGED,
                    {
                        "object_id": entity_id,
                        "visibility": self.visibility,
                        "gm_only": self.gm_only,
                        "notes_present": self.notes is not None,
                        "known_by_count": len(self.known_by),
                    },
                )

        except (ImportError, AttributeError) as e:
            # Event system not available or event missing, continue silently
            # This is expected when event system isn't set up
            pass
        except Exception as e:
            # Unexpected error in event publishing - log and continue
            # TODO: Consider using proper logging when logger is available
            import sys

            print(
                f"Warning: Unexpected error in meta event publishing: {e}",
                file=sys.stderr,
            )
            # In development/testing, you might want to re-raise:
            # if __debug__: raise

    def export(
        self,
        mode: Literal["full", "public", "minimal", "save", "session"] = "full",
        include_known_by: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Export Meta with different serialization policies for various contexts.

        Args:
            mode: Export mode determining which fields to include
                - "full": All fields (default, for debugging/GM tools)
                - "public": Public-safe fields only (for sharing/logs)
                - "minimal": Core fields only (for storage efficiency)
                - "save": Persistent fields for save files
                - "session": Runtime fields for session management
            include_known_by: Override known_by inclusion (None=auto based on mode)

        Returns:
            Dictionary with selected fields based on mode
        """
        # Determine which fields to include based on mode
        fields = self._get_export_fields(mode)

        # Handle known_by inclusion logic
        if include_known_by is None:
            include_known_by = mode in ("full", "session", "save")

        result = {}

        # Always include basic fields
        if "visibility" in fields:
            result["visibility"] = self.visibility
        if "gm_only" in fields:
            result["gm_only"] = self.gm_only

        # Conditional fields based on mode
        if include_known_by:
            result["known_by"] = list(
                self.known_by
            )  # Convert set to list for JSON, include even if empty
        elif "known_by_count" in fields:
            result["known_by_count"] = len(self.known_by)

        if "created_at" in fields:
            result["created_at"] = self.created_at
        if "last_changed_at" in fields and self.last_changed_at:
            result["last_changed_at"] = self.last_changed_at
        if "source" in fields and self.source:
            result["source"] = self.source
        if "notes" in fields and self.notes:
            result["notes"] = self.notes
        if "extra" in fields and self.extra:
            result["extra"] = self.extra

        return result

    def _get_export_fields(
        self, mode: Literal["full", "public", "minimal", "save", "session"]
    ) -> Set[str]:
        """
        Get the set of fields to include for a given export mode.

        Args:
            mode: The export mode

        Returns:
            Set of field names to include in export
        """
        if mode == "full":
            # All fields for debugging/GM tools
            return {
                "visibility",
                "gm_only",
                "known_by",
                "created_at",
                "last_changed_at",
                "source",
                "notes",
                "extra",
            }
        elif mode == "public":
            # Public-safe fields for sharing/logs (no sensitive data)
            return {"visibility", "gm_only", "known_by_count", "created_at", "source"}
        elif mode == "minimal":
            # Core fields only for storage efficiency
            return {"visibility", "gm_only"}
        elif mode == "save":
            # Persistent fields for save files
            return {
                "visibility",
                "gm_only",
                "known_by",
                "created_at",
                "last_changed_at",
                "source",
                "notes",
                "extra",
            }
        elif mode == "session":
            # Runtime fields for session management
            return {"visibility", "gm_only", "known_by", "last_changed_at"}
        else:
            raise ValueError(f"Unknown export mode: {mode}")

    def for_save(self) -> Dict[str, Any]:
        """
        Export Meta for save files - includes all persistent data.

        Returns:
            Dictionary suitable for save files
        """
        return self.export(mode="save")

    def for_session(self) -> Dict[str, Any]:
        """
        Export Meta for session management - includes runtime data.

        Returns:
            Dictionary suitable for session management
        """
        return self.export(mode="session")

    def for_public(self) -> Dict[str, Any]:
        """
        Export Meta for public sharing - excludes sensitive data.

        Returns:
            Dictionary suitable for public sharing
        """
        return self.export(mode="public")

    def for_minimal(self) -> Dict[str, Any]:
        """
        Export Meta in minimal format - core fields only.

        Returns:
            Dictionary with minimal field set
        """
        return self.export(mode="minimal")

    @classmethod
    def from_export(cls, data: Dict[str, Any]) -> "Meta":
        """
        Create Meta instance from exported data, handling missing fields gracefully.

        Args:
            data: Exported meta data dictionary

        Returns:
            Meta instance with defaults for missing fields
        """
        # Work with a copy to avoid contaminating the original data
        data = data.copy()

        # Handle known_by conversion from list to set
        if "known_by" in data and isinstance(data["known_by"], list):
            data["known_by"] = set(data["known_by"])

        # Fill in defaults for missing fields
        defaults = {
            "visibility": "public",
            "gm_only": False,
            "known_by": set(),
            "last_changed_at": None,
            "source": None,
            "notes": None,
            "extra": {},
        }

        # Only set created_at if not already present (preserve original timestamps)
        if "created_at" not in data:
            defaults["created_at"] = datetime.now(timezone.utc).isoformat()

        # Merge with defaults
        merged_data = defaults.copy()
        merged_data.update(data)

        # Ensure gm_only consistency - fix it automatically instead of failing
        if "visibility" in merged_data:
            expected_gm_only = merged_data["visibility"] == "gm_only"
            merged_data["gm_only"] = expected_gm_only

        # Set flag to indicate this is from deserialization
        if "extra" not in merged_data:
            merged_data["extra"] = {}
        # Ensure we have a copy of extra to avoid modifying original data
        merged_data["extra"] = merged_data["extra"].copy()
        merged_data["extra"]["__from_export"] = True

        return cls(**merged_data)
