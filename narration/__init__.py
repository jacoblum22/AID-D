"""
Narration layer for converting structured ToolResult data into rich prose.

This module provides LLM-based narration generation that takes the mechanical
output from tools and transforms it into immersive, literary descriptions.
"""

from .generator import generate_narration

__all__ = ["generate_narration"]
