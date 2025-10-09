"""
Test suite for redaction-level caching system.

Tests performance optimization features and cache invalidation logic.
"""

import sys
import os
import pytest
import time
from typing import Dict

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.game_state import GameState, PC, NPC, Zone, Clock, Scene, Meta, HP, Entity
from router.meta_utils import reveal_to, set_visibility, hide_from


class TestRedactionCaching:
    """Test the redaction-level caching system."""

    @pytest.fixture
    def cache_state(self):
        """Create a game state for cache testing."""
        zones = {
            "tavern": Zone(
                id="tavern",
                name="The Prancing Pony",
                description="A cozy tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            )
        }

        entities: Dict[str, Entity] = {
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
            "npc.visible": NPC(
                id="npc.visible",
                name="Visible NPC",
                current_zone="tavern",
                hp=HP(current=12, max=12),
                meta=Meta(visibility="public"),
            ),
        }

        return GameState(entities=entities, zones=zones)

    def test_get_cached_view_computes_and_stores(self, cache_state):
        """Test that get_cached_view computes redacted view and caches it."""
        # Initially cache should be empty
        assert len(cache_state._redaction_cache) == 0

        # Get cached view for alice viewing herself
        view = cache_state.get_cached_view("pc.alice", "pc.alice")

        # Should have computed and cached the view
        assert len(cache_state._redaction_cache) == 1
        assert view["id"] == "pc.alice"
        assert view["is_visible"] is True
        assert view["name"] == "Alice"

        # Cache key should be correct
        key = ("pc.alice", "pc.alice")
        assert key in cache_state._redaction_cache
        assert cache_state._redaction_cache[key] == view

    def test_get_cached_view_returns_cached_result(self, cache_state):
        """Test that subsequent calls return cached result without recomputation."""
        # First call
        view1 = cache_state.get_cached_view("pc.alice", "npc.visible")

        # Second call should return same object
        view2 = cache_state.get_cached_view("pc.alice", "npc.visible")

        assert view1 is view2
        assert len(cache_state._redaction_cache) == 1

    def test_different_pov_creates_separate_cache_entries(self, cache_state):
        """Test that different POV actors create separate cache entries."""
        # Same entity viewed by different actors
        view1 = cache_state.get_cached_view("pc.alice", "npc.visible")
        view2 = cache_state.get_cached_view(None, "npc.visible")  # GM view

        # Should have two cache entries
        assert len(cache_state._redaction_cache) == 2

        # Views might be different (GM sees more)
        key1 = ("pc.alice", "npc.visible")
        key2 = (None, "npc.visible")
        assert key1 in cache_state._redaction_cache
        assert key2 in cache_state._redaction_cache

    def test_hidden_entity_cached_correctly(self, cache_state):
        """Test that hidden entities are cached with correct redaction."""
        # Alice viewing hidden NPC she doesn't know about
        view = cache_state.get_cached_view("pc.alice", "npc.hidden")

        assert view["id"] == "npc.hidden"
        assert view["is_visible"] is False
        assert view["name"] == "Unknown"

        # Should be cached
        key = ("pc.alice", "npc.hidden")
        assert key in cache_state._redaction_cache

    def test_nonexistent_entity_cached_as_not_found(self, cache_state):
        """Test that non-existent entities are cached as 'not found'."""
        view = cache_state.get_cached_view("pc.alice", "does.not.exist")

        assert view["id"] == "does.not.exist"
        assert view["type"] == "unknown"
        assert view["is_visible"] is False
        assert view["name"] == "Not Found"

        # Should be cached to avoid repeated lookups
        key = ("pc.alice", "does.not.exist")
        assert key in cache_state._redaction_cache

    def test_invalidate_cache_specific_entity(self, cache_state):
        """Test invalidating cache for specific entity."""
        # Create multiple cache entries
        cache_state.get_cached_view("pc.alice", "pc.alice")
        cache_state.get_cached_view("pc.alice", "npc.visible")
        cache_state.get_cached_view(None, "pc.alice")

        assert len(cache_state._redaction_cache) == 3

        # Invalidate only pc.alice
        cache_state.invalidate_cache("pc.alice")

        # Should remove entries for pc.alice but keep npc.visible
        assert len(cache_state._redaction_cache) == 1
        remaining_key = list(cache_state._redaction_cache.keys())[0]
        assert remaining_key == ("pc.alice", "npc.visible")

    def test_invalidate_cache_all_entries(self, cache_state):
        """Test invalidating entire cache."""
        # Create multiple cache entries
        cache_state.get_cached_view("pc.alice", "pc.alice")
        cache_state.get_cached_view("pc.alice", "npc.visible")
        cache_state.get_cached_view(None, "npc.hidden")

        assert len(cache_state._redaction_cache) == 3

        # Invalidate all
        cache_state.invalidate_cache()

        # Should be empty
        assert len(cache_state._redaction_cache) == 0

    def test_get_state_uses_cache_by_default(self, cache_state):
        """Test that get_state uses cache by default."""
        # Clear any existing cache
        cache_state.invalidate_cache()

        # Call get_state with caching (default)
        state = cache_state.get_state(pov_id="pc.alice", redact=True)

        # Should have cached entries for each entity
        assert len(cache_state._redaction_cache) == len(cache_state.entities)

        # Cache should contain correct keys
        for eid in cache_state.entities:
            key = ("pc.alice", eid)
            assert key in cache_state._redaction_cache

    def test_get_state_bypasses_cache_when_disabled(self, cache_state):
        """Test that get_state can bypass cache when use_cache=False."""
        # Clear any existing cache
        cache_state.invalidate_cache()

        # Call get_state without caching
        state = cache_state.get_state(pov_id="pc.alice", redact=True, use_cache=False)

        # Should not have created cache entries
        assert len(cache_state._redaction_cache) == 0

    def test_meta_utils_invalidate_cache(self, cache_state):
        """Test that meta utility functions invalidate cache."""
        # Create cache entries
        cache_state.get_cached_view("pc.alice", "npc.visible")
        cache_state.get_cached_view(None, "npc.visible")

        assert len(cache_state._redaction_cache) == 2

        # Use meta utility to change visibility
        npc = cache_state.entities["npc.visible"]
        set_visibility(npc, "hidden", cache_state)

        # Cache for npc.visible should be invalidated
        assert len(cache_state._redaction_cache) == 0

    def test_cache_performance_benefit(self, cache_state):
        """Test that caching provides performance benefit for repeated calls."""
        # Create larger state to see performance difference
        for i in range(50):
            eid = f"npc.extra_{i}"
            cache_state.entities[eid] = NPC(
                id=eid,
                name=f"Extra NPC {i}",
                current_zone="tavern",
                hp=HP(current=10, max=10),
                meta=Meta(visibility="public"),
            )

        # Time uncached calls
        start = time.perf_counter()
        for _ in range(100):  # More iterations for reliable measurement
            cache_state.get_state(pov_id="pc.alice", redact=True, use_cache=False)
        uncached_time = time.perf_counter() - start

        # Clear cache and time cached calls
        cache_state.invalidate_cache()

        # First call to populate cache
        cache_state.get_state(pov_id="pc.alice", redact=True, use_cache=True)

        # Time subsequent cached calls
        start = time.perf_counter()
        for _ in range(100):  # More iterations for reliable measurement
            cache_state.get_state(pov_id="pc.alice", redact=True, use_cache=True)
        cached_time = time.perf_counter() - start

        # Cached should be faster or at least not slower
        assert (
            cached_time <= uncached_time
        ), f"Cached time {cached_time:.3f}s should not be slower than uncached {uncached_time:.3f}s"


class TestCacheInvalidationHooks:
    """Test cache invalidation through meta changes."""

    @pytest.fixture
    def hook_state(self):
        """Create a state for testing invalidation hooks."""
        zones = {
            "room": Zone(
                id="room",
                name="Test Room",
                description="A test room",
                adjacent_zones=[],
                meta=Meta(visibility="public"),
            )
        }

        entities: Dict[str, Entity] = {
            "pc.test": PC(
                id="pc.test",
                name="Test PC",
                current_zone="room",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="public"),
            )
        }

        return GameState(entities=entities, zones=zones)

    def test_reveal_to_invalidates_cache(self, hook_state):
        """Test that reveal_to invalidates relevant cache entries."""
        # Create cache entry
        hook_state.get_cached_view("pc.test", "pc.test")
        assert len(hook_state._redaction_cache) == 1

        # Use reveal_to
        entity = hook_state.entities["pc.test"]
        reveal_to(entity, "other.actor", hook_state)

        # Cache should be invalidated
        assert len(hook_state._redaction_cache) == 0

    def test_hide_from_invalidates_cache(self, hook_state):
        """Test that hide_from invalidates relevant cache entries."""
        # Create cache entry
        hook_state.get_cached_view("pc.test", "pc.test")
        assert len(hook_state._redaction_cache) == 1

        # Use hide_from
        entity = hook_state.entities["pc.test"]
        hide_from(entity, "some.actor", hook_state)

        # Cache should be invalidated
        assert len(hook_state._redaction_cache) == 0
