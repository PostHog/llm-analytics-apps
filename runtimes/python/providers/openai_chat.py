import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .compat_base import BaseProvider
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
            },
            {
                "type": "function",
                "function": {
                    "name": "tell_joke",
                    "description": "Tell a joke with a question-style setup and an answer punchline",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "setup": {
                                "type": "string",
                                "description": "The setup or question part of the joke"
                            },
                            "punchline": {
                                "type": "string",
                                "description": "The punchline or answer part of the joke"
                            }
                        },
                        "required": ["setup", "punchline"]
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
                tool_result = None

                if tool_call.function.name == "get_weather":
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        latitude = arguments.get("latitude", 0.0)
                        longitude = arguments.get("longitude", 0.0)
                        location_name = arguments.get("location_name")
                        tool_result = self.get_weather(latitude, longitude, location_name)
                        display_parts.append(self.format_tool_result("get_weather", tool_result))
                    except json.JSONDecodeError:
                        tool_result = "Error parsing tool arguments"
                        display_parts.append("❌ Error parsing tool arguments")

                elif tool_call.function.name == "tell_joke":
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        setup = arguments.get("setup", "")
                        punchline = arguments.get("punchline", "")
                        tool_result = self.tell_joke(setup, punchline)
                        display_parts.append(self.format_tool_result("tell_joke", tool_result))
                    except json.JSONDecodeError:
                        tool_result = "Error parsing tool arguments"
                        display_parts.append("❌ Error parsing tool arguments")

                # Add tool result to conversation history
                if tool_result is not None:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })

        return "\n\n".join(display_parts) if display_parts else "No response received"