import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import BaseProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class OpenAIProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            posthog_client=posthog_client
        )
    
    def get_tool_definitions(self):
        """Return tool definitions in OpenAI format"""
        return [
            {
                "name": "get_weather",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a specific location",
                    "parameters": {
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
            "max_output_tokens": 200,
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
        assistant_content = ""
        
        # Extract text from the complex response structure
        if hasattr(message, 'output') and message.output:
            for output_item in message.output:
                if hasattr(output_item, 'content') and output_item.content:
                    # Extract text from content array
                    for content_item in output_item.content:
                        if hasattr(content_item, 'text') and content_item.text:
                            assistant_content += content_item.text
                            display_parts.append(content_item.text)
                
                # Check for tool calls (these would be separate output items)
                if hasattr(output_item, 'name') and output_item.name == "get_weather":
                    # Try to get arguments from the tool call
                    arguments = {}
                    if hasattr(output_item, 'arguments') and output_item.arguments:
                        try:
                            arguments = json.loads(output_item.arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    
                    location = arguments.get("location", "unknown")
                    weather_result = self.get_weather(location)
                    tool_result_text = self.format_tool_result("get_weather", weather_result)
                    display_parts.append(tool_result_text)
        
        # Add assistant's response to conversation history with proper string content
        if assistant_content:
            assistant_message = {
                "role": "assistant",
                "content": assistant_content
            }
            self.messages.append(assistant_message)
        
        return "\n\n".join(display_parts) if display_parts else "No response received"