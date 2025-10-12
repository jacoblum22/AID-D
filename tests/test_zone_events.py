"""
Test suite for Zone Graph Events System.

This module tests the dynamic environment system including exit blocking,
unblocking, creation, destruction, and event emission.
"""

import pytest
from typing import Dict, Any, List
import sys
import os

# Add project root to path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import GameState, Zone, PC, Scene, HP, Entity
from backend.router.zone_graph import (
    block_exit,
    unblock_exit,
    toggle_exit,
    create_exit,
    destroy_exit,
    set_exit_conditions,
    get_zone_graph_events,
)
from models.space import Exit
from models.meta import Meta


class TestEventSystem:
    """Test the basic event system functionality."""

    @pytest.fixture
    def empty_world(self):
        """Create an empty world for testing events."""
        return GameState(zones={}, entities={}, scene=Scene())

    def test_event_listener_registration(self, empty_world):
        """Test registering and unregistering event listeners."""
        events_received = []

        def test_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        empty_world.register_event_listener("test.event", test_listener)
        assert len(empty_world.get_event_listeners("test.event")) == 1

        # Emit event
        empty_world.emit("test.event", data="test_data")
        assert len(events_received) == 1
        assert events_received[0][0] == "test.event"
        assert events_received[0][1]["data"] == "test_data"

        # Unregister listener
        assert empty_world.unregister_event_listener("test.event", test_listener)
        assert len(empty_world.get_event_listeners("test.event")) == 0
        assert not empty_world.unregister_event_listener(
            "test.event", test_listener
        )  # Already removed

    def test_multiple_event_listeners(self, empty_world):
        """Test multiple listeners for the same event."""
        events_received = []

        def listener1(event_type, world, **kwargs):
            events_received.append(("listener1", event_type))

        def listener2(event_type, world, **kwargs):
            events_received.append(("listener2", event_type))

        # Register multiple listeners
        empty_world.register_event_listener("test.event", listener1)
        empty_world.register_event_listener("test.event", listener2)
        assert len(empty_world.get_event_listeners("test.event")) == 2

        # Emit event - both should receive it
        empty_world.emit("test.event")
        assert len(events_received) == 2
        assert ("listener1", "test.event") in events_received
        assert ("listener2", "test.event") in events_received

    def test_event_error_handling(self, empty_world):
        """Test that errors in event listeners don't break event processing."""
        events_received = []

        def error_listener(event_type, world, **kwargs):
            raise ValueError("Test error")

        def good_listener(event_type, world, **kwargs):
            events_received.append("good_listener_called")

        # Register both listeners
        empty_world.register_event_listener("test.event", error_listener)
        empty_world.register_event_listener("test.event", good_listener)

        # Emit event - good listener should still work despite error
        empty_world.emit("test.event")
        assert "good_listener_called" in events_received


class TestZoneGraphEvents:
    """Test zone graph event functions."""

    @pytest.fixture
    def events_world(self):
        """Create a world for testing zone graph events."""
        zones = {
            "room_a": Zone(id="room_a", name="Room A", description="First room"),
            "room_b": Zone(id="room_b", name="Room B", description="Second room"),
            "room_c": Zone(id="room_c", name="Room C", description="Third room"),
            "room_d": Zone(id="room_d", name="Room D", description="Fourth room"),
        }

        # Set up initial exits
        zones["room_a"].add_exit("room_b", direction="north")
        zones["room_a"].add_exit("room_c", direction="east", blocked=True)
        zones["room_b"].add_exit("room_a", direction="south")

        entities: Dict[str, Entity] = {
            "pc.player": PC(
                id="pc.player",
                name="Player",
                type="pc",
                current_zone="room_a",
                hp=HP(current=20, max=20),
            )
        }

        return GameState(zones=zones, entities=entities, scene=Scene())

    def test_block_exit(self, events_world):
        """Test blocking an exit."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        events_world.register_event_listener("zone_graph.exit_blocked", event_listener)

        # Block an unblocked exit
        result = block_exit(
            "room_a", "room_b", events_world, cause="magic", reason="Magical barrier!"
        )
        assert result is True

        # Check exit is blocked
        room_a = events_world.zones["room_a"]
        exit_to_b = room_a.get_exit("room_b")
        assert exit_to_b.blocked is True

        # Check event was emitted
        assert len(events_received) == 1
        event_type, event_data = events_received[0]
        assert event_type == "zone_graph.exit_blocked"
        assert event_data["from_zone"] == "room_a"
        assert event_data["to_zone"] == "room_b"
        assert event_data["cause"] == "magic"
        assert event_data["reason"] == "Magical barrier!"

        # Try to block already blocked exit
        result = block_exit("room_a", "room_b", events_world)
        assert result is False  # Already blocked

        # Try to block non-existent exit
        result = block_exit("room_a", "nonexistent", events_world)
        assert result is False

        # Try with non-existent zone
        result = block_exit("nonexistent", "room_b", events_world)
        assert result is False

    def test_unblock_exit(self, events_world):
        """Test unblocking an exit."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        events_world.register_event_listener(
            "zone_graph.exit_unblocked", event_listener
        )

        # Unblock a blocked exit (room_c exit is blocked initially)
        result = unblock_exit(
            "room_a", "room_c", events_world, cause="key", reason="The door unlocks!"
        )
        assert result is True

        # Check exit is unblocked
        room_a = events_world.zones["room_a"]
        exit_to_c = room_a.get_exit("room_c")
        assert exit_to_c.blocked is False

        # Check event was emitted
        assert len(events_received) == 1
        event_type, event_data = events_received[0]
        assert event_type == "zone_graph.exit_unblocked"
        assert event_data["from_zone"] == "room_a"
        assert event_data["to_zone"] == "room_c"
        assert event_data["cause"] == "key"
        assert event_data["reason"] == "The door unlocks!"

        # Try to unblock already unblocked exit
        result = unblock_exit("room_a", "room_c", events_world)
        assert result is False  # Already unblocked

    def test_toggle_exit(self, events_world):
        """Test toggling exit blocked status."""
        # Initially room_b exit is unblocked
        result = toggle_exit("room_a", "room_b", events_world, cause="lever")
        assert result is True  # Now blocked

        room_a = events_world.zones["room_a"]
        exit_to_b = room_a.get_exit("room_b")
        assert exit_to_b.blocked is True

        # Toggle again
        result = toggle_exit("room_a", "room_b", events_world, cause="lever")
        assert result is False  # Now unblocked
        assert exit_to_b.blocked is False

        # Try with non-existent exit
        result = toggle_exit("room_a", "nonexistent", events_world)
        assert result is None

    def test_create_exit(self, events_world):
        """Test creating new exits."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        events_world.register_event_listener("zone_graph.exit_created", event_listener)

        # Create new exit from room_b to room_c
        result = create_exit(
            "room_b",
            "room_c",
            events_world,
            direction="east",
            label="Secret Door",
            blocked=False,
            conditions={"key_required": "silver_key"},
            cause="magic",
        )
        assert result is True

        # Check exit was created
        room_b = events_world.zones["room_b"]
        exit_to_c = room_b.get_exit("room_c")
        assert exit_to_c is not None
        assert exit_to_c.direction == "east"
        assert exit_to_c.label == "Secret Door"
        assert exit_to_c.blocked is False
        assert exit_to_c.conditions == {"key_required": "silver_key"}

        # Check event was emitted
        assert len(events_received) == 1
        event_type, event_data = events_received[0]
        assert event_type == "zone_graph.exit_created"
        assert event_data["from_zone"] == "room_b"
        assert event_data["to_zone"] == "room_c"
        assert event_data["direction"] == "east"
        assert event_data["label"] == "Secret Door"
        assert event_data["cause"] == "magic"

        # Try to create duplicate exit
        result = create_exit("room_b", "room_c", events_world)
        assert result is False  # Already exists

        # Try with non-existent zone
        result = create_exit("nonexistent", "room_c", events_world)
        assert result is False

    def test_destroy_exit(self, events_world):
        """Test destroying exits."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        events_world.register_event_listener(
            "zone_graph.exit_destroyed", event_listener
        )

        # Destroy existing exit
        result = destroy_exit(
            "room_a",
            "room_b",
            events_world,
            cause="collapse",
            reason="The tunnel collapses!",
        )
        assert result is True

        # Check exit was destroyed
        room_a = events_world.zones["room_a"]
        exit_to_b = room_a.get_exit("room_b")
        assert exit_to_b is None

        # Check event was emitted
        assert len(events_received) == 1
        event_type, event_data = events_received[0]
        assert event_type == "zone_graph.exit_destroyed"
        assert event_data["from_zone"] == "room_a"
        assert event_data["to_zone"] == "room_b"
        assert event_data["cause"] == "collapse"
        assert event_data["reason"] == "The tunnel collapses!"

        # Try to destroy non-existent exit
        result = destroy_exit("room_a", "room_b", events_world)
        assert result is False  # Already destroyed

    def test_set_exit_conditions(self, events_world):
        """Test setting exit conditions."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listener
        events_world.register_event_listener(
            "zone_graph.exit_conditions_changed", event_listener
        )

        # Set conditions on existing exit
        new_conditions = {"key_required": "golden_key", "level_required": "3"}
        result = set_exit_conditions(
            "room_a", "room_b", new_conditions, events_world, cause="puzzle"
        )
        assert result is True

        # Check conditions were set
        room_a = events_world.zones["room_a"]
        exit_to_b = room_a.get_exit("room_b")
        assert exit_to_b.conditions == new_conditions

        # Check event was emitted
        assert len(events_received) == 1
        event_type, event_data = events_received[0]
        assert event_type == "zone_graph.exit_conditions_changed"
        assert event_data["from_zone"] == "room_a"
        assert event_data["to_zone"] == "room_b"
        assert event_data["old_conditions"] is None
        assert event_data["new_conditions"] == new_conditions
        assert event_data["cause"] == "puzzle"

        # Clear conditions
        result = set_exit_conditions("room_a", "room_b", None, events_world)
        assert result is True
        assert exit_to_b.conditions is None

        # Try with non-existent exit
        result = set_exit_conditions("room_a", "nonexistent", {}, events_world)
        assert result is False

    def test_event_functions_without_emission(self, events_world):
        """Test that event functions work without emitting events."""
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append((event_type, kwargs))

        # Register listeners for all event types
        for event_type in get_zone_graph_events():
            events_world.register_event_listener(event_type, event_listener)

        # Test functions with emit_event=False
        assert block_exit("room_a", "room_b", events_world, emit_event=False) is True
        assert unblock_exit("room_a", "room_b", events_world, emit_event=False) is True
        assert create_exit("room_a", "room_d", events_world, emit_event=False) is True
        assert destroy_exit("room_a", "room_d", events_world, emit_event=False) is True
        assert (
            set_exit_conditions(
                "room_a", "room_c", {"test": "value"}, events_world, emit_event=False
            )
            is True
        )

        # No events should have been emitted
        assert len(events_received) == 0

    def test_get_zone_graph_events(self):
        """Test getting list of zone graph event types."""
        event_types = get_zone_graph_events()
        expected_events = [
            "zone_graph.exit_blocked",
            "zone_graph.exit_unblocked",
            "zone_graph.exit_created",
            "zone_graph.exit_destroyed",
            "zone_graph.exit_conditions_changed",
        ]
        assert set(event_types) == set(expected_events)


class TestZoneGraphEventsIntegration:
    """Test integration of events with other zone graph features."""

    def test_events_with_discovery_system(self):
        """Test that zone graph events work with discovery tracking."""
        zones = {
            "start": Zone(id="start", name="Start"),
            "hidden": Zone(id="hidden", name="Hidden Room"),
        }

        world = GameState(zones=zones, entities={}, scene=Scene())
        events_received = []

        def event_listener(event_type, world, **kwargs):
            events_received.append(event_type)

        # Register listener
        world.register_event_listener("zone_graph.exit_created", event_listener)

        # Create exit to hidden room
        result = create_exit("start", "hidden", world, cause="secret_discovered")
        assert result is True

        # Check event was emitted
        assert "zone_graph.exit_created" in events_received

        # Check exit exists and can be used for discovery
        start_zone = world.zones["start"]
        hidden_exit = start_zone.get_exit("hidden")
        assert hidden_exit is not None
        assert hidden_exit.to == "hidden"

    def test_events_preserve_zone_metadata(self):
        """Test that zone graph events properly update zone metadata."""
        zones = {
            "room": Zone(id="room", name="Room"),
            "other": Zone(id="other", name="Other"),
        }
        zones["room"].add_exit("other")

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Get initial metadata timestamp
        room = world.zones["room"]
        initial_time = room.meta.last_changed_at

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.001)  # 1ms delay

        # Block exit - should update metadata
        block_exit("room", "other", world)

        # Metadata should be updated
        assert room.meta.last_changed_at != initial_time


if __name__ == "__main__":
    pytest.main([__file__])
