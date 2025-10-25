"""
Simple demo loop for quick testing of the AID&D prototype.

This is a minimal script to test the prototype functionality quickly
without all the full features of main.py.
"""

import json
import os
import sys
from json import JSONDecodeError
from pydantic import ValidationError

# Add project root to path
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.router.game_state import GameState
from runtime.router import process_turn, get_router


def simple_demo():
    """Run a simple demo with minimal setup."""

    # Load demo world
    world_path = os.path.join(os.path.dirname(__file__), "demo_world.json")
    try:
        with open(world_path, "r") as f:
            world_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Could not find demo world file at {world_path}")
        print("Please ensure demo_world.json exists in the runtime directory.")
        return
    except JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in demo world file: {e}")
        print("Please check the syntax of demo_world.json")
        return

    try:
        world = GameState.model_validate(world_data)
    except ValidationError as e:
        print(f"❌ Error: Demo world data doesn't match expected schema:")
        print(f"  {e}")
        print("Please check the structure of demo_world.json")
        return

    # Initialize router
    router = get_router()
    router.initialize()

    print("🎲 AID&D Simple Demo")
    print("You are Arin in a moonlit courtyard.")
    print("Type commands like 'look around', 'go north', 'quit'")
    print()

    while True:
        cmd = input("> ").strip()
        if cmd.lower() in ["quit", "exit"]:
            break

        if not cmd:
            continue

        try:
            result = process_turn(world, cmd)
            print(f"\n{result.narration}\n")
        except Exception as e:
            print(f"❌ Error processing command: {e}")
            print("Demo continues - try another command or 'quit' to exit.\n")


if __name__ == "__main__":
    simple_demo()
