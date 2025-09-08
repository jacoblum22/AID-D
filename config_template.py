# Configuration template for AI D&D system
#
# SECURITY IMPORTANT:
# 1. Copy this to config.py and verify config.py is in .gitignore
# 2. Use environment variables for secrets - DO NOT hardcode API keys
# 3. Create a .env file for local development (also gitignored)
# 4. Verify config.py is not tracked by git before adding secrets

import os

# OpenAI API Configuration - loads from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Set in .env or environment
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY environment variable is required. Set it in .env file or environment."
    )

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default with override
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "500"))
OPENAI_TEMPERATURE = float(
    os.getenv("OPENAI_TEMPERATURE", "0.1")
)  # Low temperature for consistent planning decisions

# LLM Fallback Settings
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "10"))
FALLBACK_TOOL = os.getenv("FALLBACK_TOOL", "ask_clarifying")

# Example .env file content (create this file in project root):
# OPENAI_API_KEY=your-actual-api-key-here
# OPENAI_MODEL=gpt-4o-mini
# OPENAI_MAX_TOKENS=500
# OPENAI_TEMPERATURE=0.1
