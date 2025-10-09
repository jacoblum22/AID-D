"""
Test suite for Meta Change Propagation events.

Tests event publishing, subscription, and reactive hooks for
meta change notifications to dependent systems.
"""

import sys
import os
import pytest
import time
from typing import Dict, Any, List

# Add the backend directory to Python path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from router.events import EventBus, publish, subscribe, unsubscribe, EventTypes
from router.game_state import GameState, PC, NPC, Zone, Clock, Scene, Meta, HP, Entity
from router.meta_utils import reveal_to, set_visibility, set_gm_note


class TestEventBus:
    """Test the core event bus functionality."""

    @pytest.fixture
    def event_bus(self):
        """Create a fresh event bus for testing."""
        return EventBus()

    def test_subscribe_and_publish(self, event_bus):
        """Test basic subscription and publishing."""
        events_received = []

        def handler(event_data):
            events_received.append(event_data)

        event_bus.subscribe("test.event", handler)
        event_bus.publish("test.event", {"message": "hello"})

        assert len(events_received) == 1
        assert events_received[0]["message"] == "hello"
        assert events_received[0]["event_type"] == "test.event"
        assert "timestamp" in events_received[0]

    def test_multiple_subscribers(self, event_bus):
        """Test that multiple subscribers receive the same event."""
        events1 = []
        events2 = []

        def handler1(event_data):
            events1.append(event_data)

        def handler2(event_data):
            events2.append(event_data)

        event_bus.subscribe("test.event", handler1)
        event_bus.subscribe("test.event", handler2)
        event_bus.publish("test.event", {"data": "shared"})

        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0]["data"] == "shared"
        assert events2[0]["data"] == "shared"

    def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        events_received = []

        def handler(event_data):
            events_received.append(event_data)

        event_bus.subscribe("test.event", handler)
        event_bus.publish("test.event", {"first": True})

        success = event_bus.unsubscribe("test.event", handler)
        assert success is True

        event_bus.publish("test.event", {"second": True})

        # Should only have received the first event
        assert len(events_received) == 1
        assert events_received[0]["first"] is True

    def test_error_handling(self, event_bus):
        """Test that handler errors don't break the event system."""
        events_received = []

        def broken_handler(event_data):
            raise ValueError("Intentional test error")

        def working_handler(event_data):
            events_received.append(event_data)

        event_bus.subscribe("test.event", broken_handler)
        event_bus.subscribe("test.event", working_handler)

        # Should not raise despite broken handler
        event_bus.publish("test.event", {"message": "test"})

        # Working handler should still receive the event
        assert len(events_received) == 1
        assert events_received[0]["message"] == "test"

    def test_subscriber_count(self, event_bus):
        """Test getting subscriber count."""

        def handler1(event_data):
            pass

        def handler2(event_data):
            pass

        assert event_bus.get_subscriber_count("test.event") == 0

        event_bus.subscribe("test.event", handler1)
        assert event_bus.get_subscriber_count("test.event") == 1

        event_bus.subscribe("test.event", handler2)
        assert event_bus.get_subscriber_count("test.event") == 2

        event_bus.unsubscribe("test.event", handler1)
        assert event_bus.get_subscriber_count("test.event") == 1

    def test_clear_subscribers(self, event_bus):
        """Test clearing subscribers."""

        def handler(event_data):
            pass

        event_bus.subscribe("event1", handler)
        event_bus.subscribe("event2", handler)

        assert event_bus.get_subscriber_count("event1") == 1
        assert event_bus.get_subscriber_count("event2") == 1

        # Clear specific event type
        event_bus.clear_subscribers("event1")
        assert event_bus.get_subscriber_count("event1") == 0
        assert event_bus.get_subscriber_count("event2") == 1

        # Clear all
        event_bus.clear_subscribers()
        assert event_bus.get_subscriber_count("event2") == 0


class TestMetaChangeEvents:
    """Test meta change event propagation."""

    @pytest.fixture
    def game_state_with_events(self):
        """Create a game state for event testing."""
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
            "pc.alice": PC(
                id="pc.alice",
                name="Alice",
                current_zone="room",
                hp=HP(current=20, max=20),
                meta=Meta(visibility="public"),
            )
        }

        return GameState(entities=entities, zones=zones)

    def test_meta_touch_publishes_event(self, game_state_with_events):
        """Test that meta.touch() publishes events."""
        events_received = []

        def meta_handler(event_data):
            events_received.append(event_data)

        subscribe(EventTypes.META_CHANGED, meta_handler)

        try:
            entity = game_state_with_events.entities["pc.alice"]
            entity.meta.touch(game_state_with_events, "pc.alice")

            assert len(events_received) == 1
            event = events_received[0]
            assert event["object_id"] == "pc.alice"
            assert event["visibility"] == "public"
            assert event["gm_only"] is False
            assert event["notes_present"] is False
            assert event["known_by_count"] == 0
            assert event["event_type"] == EventTypes.META_CHANGED

        finally:
            unsubscribe(EventTypes.META_CHANGED, meta_handler)

    def test_meta_utils_trigger_events(self, game_state_with_events):
        """Test that meta utility functions trigger events."""
        events_received = []

        def meta_handler(event_data):
            events_received.append(event_data)

        subscribe(EventTypes.META_CHANGED, meta_handler)

        try:
            entity = game_state_with_events.entities["pc.alice"]

            # Test reveal_to
            reveal_to(entity, "npc.bob", game_state_with_events)
            assert len(events_received) == 1
            assert events_received[0]["known_by_count"] == 1

            # Test set_visibility
            set_visibility(entity, "hidden", game_state_with_events)
            assert len(events_received) == 2
            assert events_received[1]["visibility"] == "hidden"

            # Test add_gm_note
            set_gm_note(entity, "Secret note", game_state_with_events)
            assert len(events_received) == 3
            assert events_received[2]["notes_present"] is True

        finally:
            unsubscribe(EventTypes.META_CHANGED, meta_handler)

    def test_cache_invalidation_events(self, game_state_with_events):
        """Test that cache invalidation publishes events."""
        events_received = []

        def cache_handler(event_data):
            events_received.append(event_data)

        subscribe(EventTypes.CACHE_INVALIDATED, cache_handler)

        try:
            # Create some cache entries first
            game_state_with_events.get_cached_view("pc.alice", "pc.alice")

            # Test specific entity cache invalidation
            game_state_with_events.invalidate_cache("pc.alice")

            assert len(events_received) == 1
            event = events_received[0]
            assert event["entity_id"] == "pc.alice"
            assert event["full_clear"] is False
            assert event["event_type"] == EventTypes.CACHE_INVALIDATED

            # Test full cache clear
            game_state_with_events.invalidate_cache()

            assert len(events_received) == 2
            event = events_received[1]
            assert event["entity_id"] is None
            assert event["full_clear"] is True

        finally:
            unsubscribe(EventTypes.CACHE_INVALIDATED, cache_handler)


class TestReactiveHooks:
    """Test reactive hooks and event-driven behavior."""

    @pytest.fixture
    def reactive_state(self):
        """Create a state for testing reactive behavior."""
        zones = {
            "tavern": Zone(
                id="tavern",
                name="Tavern",
                description="A tavern",
                adjacent_zones=["street"],
                meta=Meta(visibility="public"),
            ),
            "street": Zone(
                id="street",
                name="Street",
                description="A street",
                adjacent_zones=["tavern"],
                meta=Meta(visibility="public"),
            ),
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
                current_zone="street",
                hp=HP(current=15, max=15),
                meta=Meta(visibility="hidden"),
            ),
        }

        return GameState(entities=entities, zones=zones)

    def test_auto_cache_invalidation_on_meta_change(self, reactive_state):
        """Test that meta changes automatically invalidate cache."""
        cache_events = []
        meta_events = []

        def cache_handler(event_data):
            cache_events.append(event_data)

        def meta_handler(event_data):
            meta_events.append(event_data)

        subscribe(EventTypes.CACHE_INVALIDATED, cache_handler)
        subscribe(EventTypes.META_CHANGED, meta_handler)

        try:
            # Create cache entry
            reactive_state.get_cached_view("pc.alice", "pc.alice")

            # Clear event history
            cache_events.clear()
            meta_events.clear()

            # Change meta which should trigger both events
            entity = reactive_state.entities["pc.alice"]
            set_visibility(entity, "hidden", reactive_state)

            # Should have one meta change and one cache invalidation
            assert len(meta_events) == 1
            assert len(cache_events) == 1

            assert meta_events[0]["visibility"] == "hidden"
            assert cache_events[0]["entity_id"] == "pc.alice"

        finally:
            unsubscribe(EventTypes.CACHE_INVALIDATED, cache_handler)
            unsubscribe(EventTypes.META_CHANGED, meta_handler)

    def test_event_driven_visibility_tracking(self, reactive_state):
        """Test tracking visibility changes through events."""
        visibility_log = []

        def track_visibility(event_data):
            if event_data.get("object_id"):
                visibility_log.append(
                    {
                        "entity": event_data["object_id"],
                        "visibility": event_data["visibility"],
                        "timestamp": event_data["timestamp"],
                    }
                )

        subscribe(EventTypes.META_CHANGED, track_visibility)

        try:
            entity = reactive_state.entities["pc.alice"]

            # Make several visibility changes
            set_visibility(entity, "hidden", reactive_state)
            set_visibility(entity, "gm_only", reactive_state)
            set_visibility(entity, "public", reactive_state)

            # Should have tracked all changes
            assert len(visibility_log) == 3
            assert visibility_log[0]["visibility"] == "hidden"
            assert visibility_log[1]["visibility"] == "gm_only"
            assert visibility_log[2]["visibility"] == "public"

            # All should have same entity
            for entry in visibility_log:
                assert entry["entity"] == "pc.alice"
                assert "timestamp" in entry

        finally:
            unsubscribe(EventTypes.META_CHANGED, track_visibility)

    def test_multi_system_coordination(self, reactive_state):
        """Test coordinating multiple systems through events."""
        audit_log = []
        performance_metrics = {"cache_invalidations": 0}

        def audit_handler(event_data):
            audit_log.append(
                f"AUDIT: {event_data['event_type']} at {event_data['timestamp']}"
            )

        def performance_handler(event_data):
            if event_data["event_type"] == EventTypes.CACHE_INVALIDATED:
                performance_metrics["cache_invalidations"] += 1

        # Subscribe multiple systems to the same events
        subscribe(EventTypes.META_CHANGED, audit_handler)
        subscribe(EventTypes.CACHE_INVALIDATED, audit_handler)
        subscribe(EventTypes.CACHE_INVALIDATED, performance_handler)

        try:
            entity = reactive_state.entities["pc.alice"]

            # Create cache then modify entity
            reactive_state.get_cached_view("pc.alice", "pc.alice")
            set_visibility(entity, "hidden", reactive_state)

            # Check that both systems received events
            assert len(audit_log) == 2  # META_CHANGED and CACHE_INVALIDATED
            assert performance_metrics["cache_invalidations"] == 1

            # Check audit log content (events may arrive in any order)
            audit_text = " ".join(audit_log)
            assert "AUDIT: meta.changed" in audit_text
            assert "AUDIT: cache.invalidated" in audit_text

        finally:
            unsubscribe(EventTypes.META_CHANGED, audit_handler)
            unsubscribe(EventTypes.CACHE_INVALIDATED, audit_handler)
            unsubscribe(EventTypes.CACHE_INVALIDATED, performance_handler)


class TestEventPerformance:
    """Test event system performance characteristics."""

    def test_event_overhead_is_minimal(self):
        """Test that event publishing doesn't significantly impact performance."""
        events_received = []

        def fast_handler(event_data):
            events_received.append(len(events_received))

        subscribe("performance.test", fast_handler)

        try:
            # Time publishing many events
            start_time = time.time()

            for i in range(1000):
                publish("performance.test", {"iteration": i})

            elapsed = time.time() - start_time

            # Should complete in reasonable time (less than 1 second)
            assert elapsed < 1.0
            assert len(events_received) == 1000

        finally:
            unsubscribe("performance.test", fast_handler)

    def test_no_memory_leaks_with_many_events(self):
        """Test that event system doesn't leak memory with many events."""
        event_counts = []

        def counting_handler(event_data):
            event_counts.append(event_data.get("count", 0))

        subscribe("memory.test", counting_handler)

        try:
            # Publish many events with different data
            for i in range(100):
                publish("memory.test", {"count": i, "data": "x" * 100})

            # Verify all events were received
            assert len(event_counts) == 100
            assert event_counts[-1] == 99

        finally:
            unsubscribe("memory.test", counting_handler)
