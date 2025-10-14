"""
Provider configuration constants.

This module centralizes default parameters for all AI providers,
making it easy to update model names, tokens limits, and other
default settings in one place.
"""

# OpenAI Models
OPENAI_CHAT_MODEL = "gpt-5-mini"
OPENAI_VISION_MODEL = "gpt-4o"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Anthropic Models
ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"

# Google Gemini Models
GEMINI_MODEL = "gemini-2.5-flash"

# Default API Parameters
DEFAULT_MAX_TOKENS = 1000

# PostHog Configuration
DEFAULT_POSTHOG_DISTINCT_ID = "user-hog"

# Weather Tool Configuration
WEATHER_TEMP_MIN_CELSIUS = -10
WEATHER_TEMP_MAX_CELSIUS = 40

# System Prompts
SYSTEM_PROMPT_FRIENDLY = "You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather."
SYSTEM_PROMPT_ASSISTANT = "You are a helpful assistant. You have access to tools that you can use to help answer questions."
SYSTEM_PROMPT_STRUCTURED = "You are an AI assistant that provides structured responses. You can provide weather information, create user profiles, or generate task plans based on user requests."
