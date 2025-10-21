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
                        "latitude": {
                            "type": "number",
                            "description": "The latitude of the location (e.g., 37.7749 for San Francisco)"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "The longitude of the location (e.g., -122.4194 for San Francisco)"
                        },
                        "location_name": {
                            "type": "string",
                            "description": "A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')"
                        }
                    },
                    "required": ["latitude", "longitude", "location_name"]
                }
            }
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
                    tool_name = content_block.name
                    tool_input = content_block.input
                    
                    if tool_name == "get_weather":
                        latitude = tool_input.get("latitude", 0.0)
                        longitude = tool_input.get("longitude", 0.0)
                        location_name = tool_input.get("location_name")
                        weather_result = self.get_weather(latitude, longitude, location_name)
                        tool_result_text = self.format_tool_result("get_weather", weather_result)
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