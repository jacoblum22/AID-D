"""
Runtime execution layer for AID&D prototype.

This module coordinates the flow:
Player input → Planner → Validator → Narration → Effects → State Update
"""

from runtime.router import process_turn
from runtime.main import run_prototype

__all__ = ["process_turn", "run_prototype"]
