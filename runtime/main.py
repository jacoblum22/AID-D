"""
Main prototype runner for AID&D.

This module provides the entry point for the interactive prototype demo.
Sets up the environment, loads the demo world, and starts the game loop.
"""

import json
import os
import sys
import logging
from typing import Optional

# Add project root to path for imports
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.router.game_state import GameState
from runtime.router import process_turn, get_router
import config


def setup_logging(debug: bool = False) -> None:
    """Set up logging for the prototype."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("prototype.log")],
    )


def load_world(world_file: str = "demo_world.json") -> GameState:
    """Load game world from JSON file."""
    world_path = os.path.join(os.path.dirname(__file__), world_file)

    try:
        with open(world_path, "r") as f:
            world_data = json.load(f)

        # Create GameState from the data
        world = GameState.model_validate(world_data)
        logging.info(f"Loaded world from {world_file}")
        return world

    except FileNotFoundError:
        logging.error(f"World file not found: {world_path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in world file: {e}")
        raise
    except Exception as e:
        logging.error(f"Failed to load world: {e}")
        raise


def save_world(world: GameState, save_file: str = "session_state.json") -> None:
    """Save current game state to JSON file."""
    save_path = os.path.join(os.path.dirname(__file__), save_file)

    try:
        # Export world state with JSON-safe serialization
        world_data = world.export_state(mode="save")

        with open(save_path, "w") as f:
            json.dump(world_data, f, indent=2)

        logging.info(f"Saved world to {save_file}")

    except Exception as e:
        logging.error(f"Failed to save world: {e}")


def run_prototype(
    world_file: str = "demo_world.json", debug: bool = False, auto_save: bool = True
) -> None:
    """
    Run the interactive prototype demo.

    Args:
        world_file: JSON file containing the initial world state
        debug: Enable debug logging and output
        auto_save: Save state after each turn
    """
    # Set up environment
    setup_logging(debug)

    try:
        # Load world
        world = load_world(world_file)

        # Initialize router
        router = get_router()
        router.initialize()

        # Display welcome message
        print("=" * 60)
        print("🎲 Welcome to AID&D Prototype! 🎲")
        print("=" * 60)
        print()
        print("You are Arin, standing in a moonlit courtyard.")
        print("Type natural language commands to play.")
        print(
            "Examples: 'look around', 'go north', 'attack guard', 'use healing potion'"
        )
        print("Type 'quit' or 'exit' to stop playing.")
        print()

        # Game loop
        turn_count = 0
        while True:
            try:
                # Get player input
                print(f"[Round {world.scene.round}, Turn {turn_count + 1}]")
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\nThanks for playing! Goodbye!")
                    break

                # Process the turn
                print("\n" + "." * 40)
                result = process_turn(world, user_input, debug=debug)

                # Display result
                if result.success:
                    print(f"\n{result.narration}")
                else:
                    print(f"\n❌ {result.narration}")
                    if debug and result.error_message:
                        print(f"Debug: {result.error_message}")

                # Auto-save if enabled
                if auto_save:
                    save_world(world, "session_state.json")

                turn_count += 1
                print("\n" + "." * 40)

            except KeyboardInterrupt:
                print("\n\nGame interrupted. Saving...")
                if auto_save:
                    save_world(world, "interrupted_session.json")
                break
            except Exception as e:
                logging.error(f"Error during game loop: {e}")
                print(f"\n❌ An error occurred: {e}")
                if debug:
                    raise

    except Exception as e:
        logging.error(f"Failed to start prototype: {e}")
        print(f"❌ Failed to start game: {e}")
        if debug:
            raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AID&D Prototype")
    parser.add_argument("--world", default="demo_world.json", help="World file to load")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--no-save", action="store_true", help="Disable auto-save")

    args = parser.parse_args()

    run_prototype(world_file=args.world, debug=args.debug, auto_save=not args.no_save)
