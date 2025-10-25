#!/usr/bin/env python3
"""
Startup script for AID&D prototype.

To run:
    python run_prototype.py [options]

Example usage:
    python run_prototype.py --new-game --debug
    python run_prototype.py --world custom_world.json
    $env:SHOW_PROMPTS="1"; python run_prototype.py --debug

Run this from the project root directory.
"""

import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the prototype
from runtime.main import run_prototype

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AID&D Prototype")
    parser.add_argument("--world", default="demo_world.json", help="World file to load")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--no-save", action="store_true", help="Disable auto-save")
    parser.add_argument(
        "--new-game",
        action="store_true",
        help="Force new game (ignore saved session), respects --world argument",
    )

    args = parser.parse_args()

    run_prototype(
        world_file=args.world,
        debug=args.debug,
        auto_save=not args.no_save,
        force_new_game=args.new_game,
    )
