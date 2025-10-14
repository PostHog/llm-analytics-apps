import os
from posthog.ai.anthropic import Anthropic
from posthog import Posthog
from .base import BaseProvider
from .constants import (
    ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_POSTHOG_DISTINCT_ID
)

class AnthropicProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self.client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            posthog_client=posthog_client
        )
    
    def get_tool_definitions(self):
        """Return tool definitions in Anthropic format"""
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather for a specific location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city or location name to get weather for"
                        }
                    },
                    "required": ["location"]
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
        request_params = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "tools": self.tools,
            "messages": self.messages
        }

        # Send all messages in conversation history
        message = self.client.messages.create(**request_params)

        # Debug: Log the API call (request + response)
        self._debug_api_call("Anthropic", request_params, message)

        # Process all content blocks to handle both text and tool calls
        assistant_content = []
        tool_results = []
        display_parts = []
        
        if message.content and len(message.content) > 0:
            for content_block in message.content:
                if content_block.type == "tool_use":
                    # Store the tool use block for message history
                    assistant_content.append(content_block)
                    
                    # Execute the tool and prepare result for display and history
                    tool_name = content_block.name
                    tool_input = content_block.input
                    
                    if tool_name == "get_weather":
                        location = tool_input.get("location", "unknown")
                        weather_result = self.get_weather(location)
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