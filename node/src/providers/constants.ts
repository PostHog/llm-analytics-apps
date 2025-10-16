/**
 * Provider configuration constants.
 *
 * This module centralizes default parameters for all AI providers,
 * making it easy to update model names, token limits, and other
 * default settings in one place.
 */

// OpenAI Models
export const OPENAI_CHAT_MODEL = "gpt-5-mini";
export const OPENAI_VISION_MODEL = "gpt-4o";
export const OPENAI_EMBEDDING_MODEL = "text-embedding-3-small";

// Anthropic Models
export const ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929";

// Google Gemini Models
export const GEMINI_MODEL = "gemini-2.5-flash";

// Default API Parameters
export const DEFAULT_MAX_TOKENS = 200;

// Extended Thinking Configuration (Anthropic)
// Set ENABLE_THINKING=1 in .env to enable extended thinking
// Set THINKING_BUDGET_TOKENS in .env to customize (default: 10000, min: 1024)
export const DEFAULT_THINKING_ENABLED = false;
export const DEFAULT_THINKING_BUDGET_TOKENS = 10000;

// PostHog Configuration
export const DEFAULT_POSTHOG_DISTINCT_ID = "user-hog";

// Weather Tool Configuration
export const WEATHER_TEMP_MIN_CELSIUS = -10;
export const WEATHER_TEMP_MAX_CELSIUS = 40;

// System Prompts
export const SYSTEM_PROMPT_FRIENDLY = "You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather.";
export const SYSTEM_PROMPT_ASSISTANT = "You are a helpful assistant. You have access to tools that you can use to help answer questions.";
export const SYSTEM_PROMPT_STRUCTURED = "You are an AI assistant that provides structured responses. You can provide weather information, create user profiles, or generate task plans based on user requests.";
