import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import BaseProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class OpenAIChatProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_chat_completions"}

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            posthog_client=posthog_client
        )
        self.messages = self.get_initial_messages()
    
    def get_initial_messages(self):
        """Return initial messages with system prompt"""
        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_FRIENDLY
            }
        ]
    
    def get_tool_definitions(self):
        """Return tool definitions in OpenAI Chat format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a specific location using geographical coordinates",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "The latitude of the location"},
                            "longitude": {"type": "number", "description": "The longitude of the location"},
                            "location_name": {"type": "string", "description": "A human-readable name for the location"},
                        },
                        "required": ["latitude", "longitude", "location_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "tell_joke",
                    "description": "Tell a joke with a question-style setup and an answer punchline",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "setup": {"type": "string", "description": "The setup or question part of the joke"},
                            "punchline": {"type": "string", "description": "The punchline or answer part of the joke"},
                        },
                        "required": ["setup", "punchline"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "roll_dice",
                    "description": "Roll one or more dice with a specified number of sides",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "num_dice": {"type": "integer", "description": "Number of dice to roll (default: 1)"},
                            "sides": {"type": "integer", "description": "Number of sides per die (default: 6)"},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_time",
                    "description": "Get the current time in a specific timezone (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo')",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string", "description": "IANA timezone name (e.g., 'US/Eastern', 'Europe/Paris')"},
                        },
                        "required": ["timezone"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Evaluate a mathematical expression (basic arithmetic: +, -, *, /, parentheses)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string", "description": "The math expression to evaluate (e.g., '(2 + 3) * 4')"},
                        },
                        "required": ["expression"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "convert_units",
                    "description": "Convert a value between common units (km/miles, kg/lbs, celsius/fahrenheit, meters/feet, liters/gallons)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number", "description": "The numeric value to convert"},
                            "from_unit": {"type": "string", "description": "The source unit (e.g., 'km', 'celsius', 'kg')"},
                            "to_unit": {"type": "string", "description": "The target unit (e.g., 'miles', 'fahrenheit', 'lbs')"},
                        },
                        "required": ["value", "from_unit", "to_unit"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_inspirational_quote",
                    "description": "Get an inspirational quote, optionally on a specific topic (general, perseverance, creativity, success, teamwork)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "Topic for the quote (general, perseverance, creativity, success, teamwork)"},
                        },
                        "required": [],
                    },
                },
            },
        ]
    
    def get_name(self):
        return "OpenAI Chat Completions"
    
    
    def embed(self, text: str, model: str = OPENAI_EMBEDDING_MODEL) -> list:
        """Create embeddings for the given text"""
        response = self.client.embeddings.create(
            model=model,
            input=text,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "user-hog")
        )
        
        # Extract embedding vector from response
        if hasattr(response, 'data') and response.data:
            return response.data[0].embedding
        return []
    
    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to OpenAI and get response"""
        # Add user message to history
        if base64_image:
            # For image input, create content array with text and image
            user_content = [
                {
                    "type": "text",
                    "text": user_input
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        else:
            user_content = user_input
            
        user_message = {
            "role": "user",
            "content": user_content
        }
        self.messages.append(user_message)
        
        # Send all messages in conversation history using PostHog wrapper
        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL

        # Prepare API request parameters
        # Note: gpt-5-mini and newer models use max_completion_tokens instead of max_tokens
        request_params = {
            "model": model_name,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": "auto"
        }

        response = self.client.chat.completions.create(**request_params)

        # Debug: Log the API call (request + response)
        self._debug_api_call("OpenAI Chat Completions", request_params, response)

        # Collect response parts for display
        display_parts = []

        # Extract response from Chat Completions format
        choice = response.choices[0]
        message = choice.message

        # Handle text content
        assistant_content = message.content or ""
        if assistant_content:
            display_parts.append(assistant_content)

        # Build and add assistant message to conversation history ONCE
        # This must happen before processing tool calls for proper history
        if message.tool_calls:
            # Assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            }
        else:
            # Plain assistant message without tool calls
            assistant_message = {
                "role": "assistant",
                "content": assistant_content
            }
        self.messages.append(assistant_message)

        # Process tool calls (execute tools and add results to history)
        if message.tool_calls:
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                tool_result = self.execute_tool(tool_call.function.name, arguments)
                if tool_result is not None:
                    display_parts.append(self.format_tool_result(tool_call.function.name, tool_result))
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })

        return "\n\n".join(display_parts) if display_parts else "No response received"