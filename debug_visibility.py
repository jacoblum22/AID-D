#!/usr/bin/env python3
"""Debug script to understand why GM-only entities are not being filtered in public mode."""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.meta import Meta
from backend.router.game_state import GameState, PC, NPC, Zone, Scene

# Create test entity with GM-only visibility
npc_secret = NPC(
    id="npc.secret",
    name="Secret Agent",
    current_zone="tavern",
    meta=Meta(visibility="gm_only", gm_only=True, notes="Hidden from players"),
)

# Create simple game state
game_state = GameState(
    entities={"npc.secret": npc_secret},
    zones={
        "tavern": Zone(
            id="tavern", name="Tavern", description="A tavern", adjacent_zones=[]
        )
    },
    scene=Scene(id="test"),
)

print("=== Original Entity ===")
print(f"Entity visibility: {npc_secret.meta.visibility}")
print(f"Entity gm_only: {npc_secret.meta.gm_only}")

print("\n=== Export State in Public Mode ===")
public_state = game_state.export_state(mode="public", role="player")
print(f"Entities in public export: {list(public_state['entities'].keys())}")

if "npc.secret" in public_state["entities"]:
    entity_data = public_state["entities"]["npc.secret"]
    print(f"Entity is_visible: {entity_data.get('is_visible', 'N/A')}")
    print(f"Entity name: {entity_data.get('name', 'N/A')}")

print("\n=== Direct Redaction Test ===")
from backend.router.visibility import redact_entity

redacted = redact_entity(None, npc_secret, game_state, "player")
print(f"Redacted entity is_visible: {redacted.get('is_visible', 'N/A')}")
print(f"Redacted entity keys: {list(redacted.keys())}")
