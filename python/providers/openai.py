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

class OpenAIProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        posthog_client.super_properties = {"$ai_span_name": "openai_responses"}

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            posthog_client=posthog_client
        )
    
    def get_tool_definitions(self):
        """Return tool definitions in OpenAI Responses API format"""
        return [
            {
                "type": "function",
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
        ]
    
    def get_name(self):
        return "OpenAI Responses"
    
    
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
                    "type": "input_text",
                    "text": user_input
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{base64_image}"
                }
            ]
        else:
            user_content = user_input
            
        user_message = {
            "role": "user",
            "content": user_content
        }
        self.messages.append(user_message)

        # Send all messages in conversation history
        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL
        request_params = {
            "model": model_name,
            "max_output_tokens": DEFAULT_MAX_TOKENS,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "input": self.messages,
            "instructions": SYSTEM_PROMPT_FRIENDLY,
            "tools": self.tools
        }

        message = self.client.responses.create(**request_params)

        # Debug: Log the API call
        self._debug_api_call("OpenAI", request_params, message)
        
        # Collect response parts for display
        display_parts = []
        assistant_content_items = []

        # Extract text and tool calls from the response structure
        if hasattr(message, 'output') and message.output:
            for output_item in message.output:
                # Handle message content (text)
                if hasattr(output_item, 'content') and output_item.content:
                    # Extract text from content array
                    for content_item in output_item.content:
                        if hasattr(content_item, 'text') and content_item.text:
                            display_parts.append(content_item.text)
                            # Add to conversation history as output_text
                            assistant_content_items.append({
                                "type": "output_text",
                                "text": content_item.text
                            })

                # Handle tool calls (separate output items in Responses API)
                if hasattr(output_item, 'name') and output_item.name == "get_weather":
                    # Get the tool call details from the response
                    call_id = getattr(output_item, 'call_id', f"call_{output_item.name}")
                    tool_arguments = getattr(output_item, 'arguments', '{}')

                    # Parse arguments to execute the tool
                    arguments = {}
                    try:
                        arguments = json.loads(tool_arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    latitude = arguments.get("latitude", 0.0)
                    longitude = arguments.get("longitude", 0.0)
                    location_name = arguments.get("location_name")
                    weather_result = self.get_weather(latitude, longitude, location_name)
                    tool_result_text = self.format_tool_result("get_weather", weather_result)
                    display_parts.append(tool_result_text)

                    # Store tool call info to add to conversation history
                    tool_call_for_history = {
                        "id": call_id,
                        "name": output_item.name,
                        "result": weather_result
                    }

        # Add messages to conversation history
        # For client-side history management (not using previous_response_id),
        # we add tool results as assistant messages with output_text
        if 'tool_call_for_history' in locals():
            assistant_content_items.append({
                "type": "output_text",
                "text": tool_call_for_history["result"]
            })

        if assistant_content_items:
            assistant_message = {
                "role": "assistant",
                "content": assistant_content_items
            }
            self.messages.append(assistant_message)

        return "\n\n".join(display_parts) if display_parts else "No response received"