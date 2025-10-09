"""
Simple event system for AID&D game state changes.

Provides a lightweight pub/sub mechanism for notifying systems
about meta changes, zone transitions, and other game events.
"""

from typing import Dict, List, Callable, Any, Optional
from threading import Lock
from datetime import datetime, timezone


class EventBus:
    """
    Thread-safe event bus for game state notifications.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._lock = Lock()

    def subscribe(
        self, event_type: str, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe a handler to an event type.

        Args:
            event_type: The type of event to listen for
            handler: Function to call when event is published
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            # Prevent duplicate subscriptions
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(
        self, event_type: str, handler: Callable[[Dict[str, Any]], None]
    ) -> bool:
        """
        Unsubscribe a handler from an event type.

        Args:
            event_type: The type of event to stop listening for
            handler: The handler function to remove

        Returns:
            True if handler was found and removed, False otherwise
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    return True
                except ValueError:
                    pass
        return False

    def publish(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event_type: The type of event being published
            event_data: The event data to send to handlers
        """
        # Add timestamp to all events
        event_data = event_data.copy()
        event_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        event_data["event_type"] = event_type

        # Get current subscribers (thread-safe)
        with self._lock:
            handlers = self._subscribers.get(event_type, []).copy()

        # Call handlers outside the lock to prevent deadlock
        for handler in handlers:
            try:
                handler(event_data)
            except Exception as e:
                # Log error but continue with other handlers
                print(f"Error in event handler for {event_type}: {e}")

    def clear_subscribers(self, event_type: Optional[str] = None) -> None:
        """
        Clear subscribers for an event type, or all subscribers.

        Args:
            event_type: Event type to clear, or None to clear all
        """
        with self._lock:
            if event_type:
                self._subscribers.pop(event_type, None)
            else:
                self._subscribers.clear()

    def get_subscriber_count(self, event_type: str) -> int:
        """
        Get the number of subscribers for an event type.

        Args:
            event_type: The event type to check

        Returns:
            Number of subscribers
        """
        with self._lock:
            return len(self._subscribers.get(event_type, []))


# Global event bus instance
event_bus = EventBus()


def publish(event_type: str, event_data: Dict[str, Any]) -> None:
    """
    Convenience function to publish events to the global event bus.

    Args:
        event_type: The type of event being published
        event_data: The event data to send to handlers
    """
    event_bus.publish(event_type, event_data)


def subscribe(event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
    """
    Convenience function to subscribe to events on the global event bus.

    Args:
        event_type: The type of event to listen for
        handler: Function to call when event is published
    """
    event_bus.subscribe(event_type, handler)


def unsubscribe(event_type: str, handler: Callable[[Dict[str, Any]], None]) -> bool:
    """
    Convenience function to unsubscribe from events on the global event bus.

    Args:
        event_type: The type of event to stop listening for
        handler: The handler function to remove

    Returns:
        True if handler was found and removed, False otherwise
    """
    return event_bus.unsubscribe(event_type, handler)


# Predefined event types
class EventTypes:
    """Common event type constants."""

    META_CHANGED = "meta.changed"
    ZONE_ENTER = "zone.enter"
    ZONE_EXIT = "zone.exit"
    ENTITY_CREATED = "entity.created"
    ENTITY_DESTROYED = "entity.destroyed"
    VISIBILITY_CHANGED = "visibility.changed"
    CACHE_INVALIDATED = "cache.invalidated"
