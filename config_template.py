# Configuration template for AI D&D system
# Copy this to config.py and add your actual API key

# OpenAI API Configuration
OPENAI_API_KEY = "your-api-key-here"  # Replace with your actual API key
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_TOKENS = 500
OPENAI_TEMPERATURE = 0.1  # Low temperature for consistent planning decisions

# LLM Fallback Settings
LLM_TIMEOUT_SECONDS = 10
FALLBACK_TOOL = "ask_clarifying"
