"""
Provider configuration constants.

This module centralizes default parameters for all AI providers,
making it easy to update model names, tokens limits, and other
default settings in one place.
"""

# OpenAI Models
OPENAI_CHAT_MODEL = "gpt-4o-mini"
OPENAI_VISION_MODEL = "gpt-4o"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Anthropic Models
ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"

# Google Gemini Models
GEMINI_MODEL = "gemini-2.5-flash"

# Default API Parameters
DEFAULT_MAX_TOKENS = 200
DEFAULT_TEMPERATURE = 0.7

# PostHog Configuration
DEFAULT_POSTHOG_DISTINCT_ID = "user-hog"

# Weather Tool Configuration
WEATHER_TEMP_MIN_CELSIUS = -10
WEATHER_TEMP_MAX_CELSIUS = 40
