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
            }
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
        assistant_content = ""
        
        # Extract response from Chat Completions format
        choice = response.choices[0]
        message = choice.message
        
        # Handle text content
        if message.content:
            assistant_content = message.content
            display_parts.append(message.content)
        
        # Handle tool calls
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "get_weather":
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        latitude = arguments.get("latitude", 0.0)
                        longitude = arguments.get("longitude", 0.0)
                        location_name = arguments.get("location_name")
                        weather_result = self.get_weather(latitude, longitude, location_name)
                        tool_result_text = self.format_tool_result("get_weather", weather_result)
                        display_parts.append(tool_result_text)
                        
                        # Add tool response to conversation history
                        self.messages.append({
                            "role": "assistant",
                            "content": assistant_content,
                            "tool_calls": [
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments
                                    }
                                }
                            ]
                        })
                        
                        # Add tool result message
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": weather_result
                        })
                        
                    except json.JSONDecodeError:
                        display_parts.append("❌ Error parsing tool arguments")
        else:
            # Add assistant's response to conversation history (text only)
            if assistant_content:
                assistant_message = {
                    "role": "assistant",
                    "content": assistant_content
                }
                self.messages.append(assistant_message)
        
        return "\n\n".join(display_parts) if display_parts else "No response received"