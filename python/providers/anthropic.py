import os
from posthog.ai.anthropic import Anthropic
from posthog import Posthog
from .base import BaseProvider
from .constants import (
    ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    DEFAULT_THINKING_ENABLED,
    DEFAULT_THINKING_BUDGET_TOKENS
)

class AnthropicProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog, enable_thinking: bool = False, thinking_budget: int = None):
        super().__init__(posthog_client)

        # Set span name for this provider (merge with existing super_properties)
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "anthropic_messages"}

        self.client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            posthog_client=posthog_client
        )
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget or DEFAULT_THINKING_BUDGET_TOKENS
    
    def get_tool_definitions(self):
        """Return tool definitions in Anthropic format"""
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather for a specific location using geographical coordinates",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "latitude": {"type": "number", "description": "The latitude of the location"},
                        "longitude": {"type": "number", "description": "The longitude of the location"},
                        "location_name": {"type": "string", "description": "A human-readable name for the location"},
                    },
                    "required": ["latitude", "longitude", "location_name"],
                },
            },
            {
                "name": "tell_joke",
                "description": "Tell a joke with a question-style setup and an answer punchline",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "setup": {"type": "string", "description": "The setup or question part of the joke"},
                        "punchline": {"type": "string", "description": "The punchline or answer to the joke"},
                    },
                    "required": ["setup", "punchline"],
                },
            },
            {
                "name": "roll_dice",
                "description": "Roll one or more dice with a specified number of sides",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "num_dice": {"type": "integer", "description": "Number of dice to roll (default: 1)"},
                        "sides": {"type": "integer", "description": "Number of sides per die (default: 6)"},
                    },
                    "required": [],
                },
            },
            {
                "name": "check_time",
                "description": "Get the current time in a specific timezone (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo')",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "description": "IANA timezone name (e.g., 'US/Eastern', 'Europe/Paris')"},
                    },
                    "required": ["timezone"],
                },
            },
            {
                "name": "calculate",
                "description": "Evaluate a mathematical expression (basic arithmetic: +, -, *, /, parentheses)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "The math expression to evaluate (e.g., '(2 + 3) * 4')"},
                    },
                    "required": ["expression"],
                },
            },
            {
                "name": "convert_units",
                "description": "Convert a value between common units (km/miles, kg/lbs, celsius/fahrenheit, meters/feet, liters/gallons)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "description": "The numeric value to convert"},
                        "from_unit": {"type": "string", "description": "The source unit (e.g., 'km', 'celsius', 'kg')"},
                        "to_unit": {"type": "string", "description": "The target unit (e.g., 'miles', 'fahrenheit', 'lbs')"},
                    },
                    "required": ["value", "from_unit", "to_unit"],
                },
            },
            {
                "name": "generate_inspirational_quote",
                "description": "Get an inspirational quote, optionally on a specific topic (general, perseverance, creativity, success, teamwork)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Topic for the quote (general, perseverance, creativity, success, teamwork)"},
                    },
                    "required": [],
                },
            },
        ]
    
    def get_name(self):
        return "Anthropic"
    
    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to Anthropic and get response"""
        # Add user message to history
        if base64_image:
            # For image input, create content array with text and image
            user_content = [
                {"type": "text", "text": user_input},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_image
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

        # Prepare API request parameters
        # Note: max_tokens must be greater than thinking.budget_tokens
        thinking_budget = max(self.thinking_budget, 1024) if self.enable_thinking else 0
        max_tokens = max(DEFAULT_MAX_TOKENS, thinking_budget + 2000) if self.enable_thinking else DEFAULT_MAX_TOKENS
        
        request_params = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "tools": self.tools,
            "messages": self.messages
        }
        
        # Add extended thinking if enabled
        if self.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget
            }

        # Send all messages in conversation history
        message = self.client.messages.create(**request_params)

        # Debug: Log the API call (request + response)
        self._debug_api_call("Anthropic", request_params, message)

        # Process all content blocks to handle text, thinking, and tool calls
        assistant_content = []
        tool_results = []
        display_parts = []
        
        if message.content and len(message.content) > 0:
            for content_block in message.content:
                if content_block.type == "thinking":
                    # Store thinking block for message history
                    assistant_content.append(content_block)
                    # Display thinking content if enabled
                    if self.enable_thinking:
                        display_parts.append(f"💭 Thinking: {content_block.thinking}")
                elif content_block.type == "tool_use":
                    # Store the tool use block for message history
                    assistant_content.append(content_block)

                    # Execute the tool and prepare result for display and history
                    tool_result = self.execute_tool(content_block.name, content_block.input)
                    if tool_result is not None:
                        tool_result_text = self.format_tool_result(content_block.name, tool_result)
                        tool_results.append(tool_result_text)
                        display_parts.append(tool_result_text)
                elif content_block.type == "text":
                    # Store text content for both display and history
                    assistant_content.append(content_block)
                    display_parts.append(content_block.text)
        
        # Add assistant's response to conversation history
        assistant_message = {
            "role": "assistant", 
            "content": assistant_content
        }
        self.messages.append(assistant_message)
        
        # If we have tool results, add them as tool result messages to history
        if tool_results:
            for i, content_block in enumerate(message.content):
                if content_block.type == "tool_use":
                    tool_result_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content_block.id,
                                "content": tool_results[0] if tool_results else "Tool executed"
                            }
                        ]
                    }
                    self.messages.append(tool_result_message)
                    break
            
        return "\n\n".join(display_parts) if display_parts else "No response received"