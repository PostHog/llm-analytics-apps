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
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"

# Google Gemini Models
GEMINI_MODEL = "gemini-2.5-flash"

# Default API Parameters
# Note: gpt-5-mini uses reasoning tokens internally, so needs higher limit
DEFAULT_MAX_TOKENS = 4000

# Extended Thinking Configuration (Anthropic)
# Set ENABLE_THINKING=1 in .env to enable extended thinking
# Set THINKING_BUDGET_TOKENS in .env to customize (default: 10000, min: 1024)
DEFAULT_THINKING_ENABLED = False
DEFAULT_THINKING_BUDGET_TOKENS = 10000

# PostHog Configuration
DEFAULT_POSTHOG_DISTINCT_ID = "user-hog"

# Weather Tool Configuration
WEATHER_TEMP_MIN_CELSIUS = -10
WEATHER_TEMP_MAX_CELSIUS = 40

# System Prompts
SYSTEM_PROMPT_FRIENDLY = "You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather."
SYSTEM_PROMPT_ASSISTANT = "You are a helpful assistant. You have access to tools that you can use to help answer questions."
SYSTEM_PROMPT_STRUCTURED = "You are an AI assistant that provides structured responses. You can provide weather information, create user profiles, or generate task plans based on user requests."
