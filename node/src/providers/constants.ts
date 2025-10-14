/**
 * Provider configuration constants.
 *
 * This module centralizes default parameters for all AI providers,
 * making it easy to update model names, token limits, and other
 * default settings in one place.
 */

// OpenAI Models
export const OPENAI_CHAT_MODEL = "gpt-4o-mini";
export const OPENAI_VISION_MODEL = "gpt-4o";
export const OPENAI_EMBEDDING_MODEL = "text-embedding-3-small";

// Anthropic Models
export const ANTHROPIC_MODEL = "claude-sonnet-4-20250514";

// Google Gemini Models
export const GEMINI_MODEL = "gemini-2.5-flash";

// Default API Parameters
export const DEFAULT_MAX_TOKENS = 200;
export const DEFAULT_TEMPERATURE = 0.7;

// PostHog Configuration
export const DEFAULT_POSTHOG_DISTINCT_ID = "user-hog";

// Weather Tool Configuration
export const WEATHER_TEMP_MIN_CELSIUS = -10;
export const WEATHER_TEMP_MAX_CELSIUS = 40;
