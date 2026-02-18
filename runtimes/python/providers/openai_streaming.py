import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .compat_base import StreamingProvider
from typing import Generator, Optional
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class OpenAIStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_responses_streaming"}

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
            },
            {
                "type": "function",
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
        ]
    
    def get_name(self):
        return "OpenAI Responses Streaming"
    
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
    
    def chat_stream(self, user_input: str, base64_image: Optional[str] = None) -> Generator[str, None, None]:
        """Send a message to OpenAI and stream the response"""
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
        
        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL

        # Prepare API request parameters
        request_params = {
            "model": model_name,
            "max_output_tokens": DEFAULT_MAX_TOKENS,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "input": self.messages,
            "instructions": SYSTEM_PROMPT_FRIENDLY,
            "tools": self.tools,
            "stream": True
        }

        # Debug: Log the API request
        if self.debug_mode:
            self._debug_log("OpenAI Responses Streaming API Request", request_params)

        # Create streaming response
        stream = self.client.responses.create(**request_params)

        accumulated_content = ""
        final_output = []
        tool_calls = []
        
        try:
            for chunk in stream:
                # Handle different event types from the responses API stream
                if hasattr(chunk, 'type'):
                    if chunk.type == 'response.output_text.delta':
                        # Text delta streaming - this is the main text streaming event
                        if hasattr(chunk, 'delta') and chunk.delta:
                            accumulated_content += chunk.delta
                            yield chunk.delta
                    
                    elif chunk.type == 'response.output_item.added':
                        # Track when a function call starts
                        if hasattr(chunk, 'item') and hasattr(chunk.item, 'type') and chunk.item.type == 'function_call':
                            # Store the function info for later use
                            output_index = getattr(chunk, 'output_index', len(tool_calls))
                            if output_index >= len(tool_calls):
                                tool_calls.append({
                                    "name": getattr(chunk.item, 'name', 'get_weather'),
                                    "call_id": getattr(chunk.item, 'call_id', f"call_{getattr(chunk.item, 'name', 'unknown')}"),
                                    "arguments": ""
                                })
                    
                    elif chunk.type == 'response.function_call_arguments.done':
                        # Function call arguments completed
                        if hasattr(chunk, 'arguments') and hasattr(chunk, 'output_index'):
                            # Get the function info we stored earlier
                            output_index = chunk.output_index
                            if output_index < len(tool_calls):
                                tool_call = tool_calls[output_index]
                                if tool_call["name"] == "get_weather":
                                    arguments = {}
                                    try:
                                        arguments = json.loads(chunk.arguments)
                                    except json.JSONDecodeError:
                                        arguments = {}

                                    latitude = arguments.get("latitude", 0.0)
                                    longitude = arguments.get("longitude", 0.0)
                                    location_name = arguments.get("location_name")
                                    weather_result = self.get_weather(latitude, longitude, location_name)
                                    tool_result_text = self.format_tool_result("get_weather", weather_result)
                                    yield "\n\n" + tool_result_text

                                    # Update the arguments
                                    tool_call["arguments"] = chunk.arguments
                                elif tool_call["name"] == "tell_joke":
                                    arguments = {}
                                    try:
                                        arguments = json.loads(chunk.arguments)
                                    except json.JSONDecodeError:
                                        arguments = {}

                                    setup = arguments.get("setup", "")
                                    punchline = arguments.get("punchline", "")
                                    joke_result = self.tell_joke(setup, punchline)
                                    tool_result_text = self.format_tool_result("tell_joke", joke_result)
                                    yield "\n\n" + tool_result_text

                                    # Update the arguments
                                    tool_call["arguments"] = chunk.arguments
                    
                    elif chunk.type == 'response.completed':
                        # Response completed event - only handle content that wasn't already streamed
                        if hasattr(chunk, 'response') and chunk.response:
                            if hasattr(chunk.response, 'output') and chunk.response.output:
                                for output_item in chunk.response.output:
                                    # Check if this is a content message that wasn't already streamed
                                    if hasattr(output_item, 'content') and isinstance(output_item.content, list):
                                        # Only add content if we didn't stream it already
                                        for content_item in output_item.content:
                                            if hasattr(content_item, 'text') and content_item.text:
                                                if content_item.text not in accumulated_content:
                                                    accumulated_content += content_item.text
                                                    yield content_item.text
                                    
                                    # Tool calls are already handled in response.function_call_arguments.done
                                    # So we don't need to handle them here
        
        except Exception as e:
            yield f"\n\nError during streaming: {str(e)}"
        
        # Save assistant message with accumulated content or tool results
        # Use proper Responses API format with content arrays
        assistant_content_items = []

        # Add text content if any
        if accumulated_content:
            assistant_content_items.append({
                "type": "output_text",
                "text": accumulated_content
            })

        # Add tool results if any
        if tool_calls and any(tc.get("arguments") for tc in tool_calls):
            for tool_call in tool_calls:
                if tool_call.get("arguments") and tool_call.get("name") == "get_weather":
                    try:
                        args = json.loads(tool_call["arguments"])
                        latitude = args.get("latitude", 0.0)
                        longitude = args.get("longitude", 0.0)
                        location_name = args.get("location_name")
                        weather_result = self.get_weather(latitude, longitude, location_name)

                        # Add tool result as output_text for conversation history
                        # For client-side history management, add as assistant message with output_text
                        assistant_content_items.append({
                            "type": "output_text",
                            "text": weather_result
                        })
                    except json.JSONDecodeError:
                        pass
                elif tool_call.get("arguments") and tool_call.get("name") == "tell_joke":
                    try:
                        args = json.loads(tool_call["arguments"])
                        setup = args.get("setup", "")
                        punchline = args.get("punchline", "")
                        joke_result = self.tell_joke(setup, punchline)

                        # Add tool result as output_text for conversation history
                        # For client-side history management, add as assistant message with output_text
                        assistant_content_items.append({
                            "type": "output_text",
                            "text": joke_result
                        })
                    except json.JSONDecodeError:
                        pass

        # Add to conversation history if there's any content
        if assistant_content_items:
            assistant_message = {
                "role": "assistant",
                "content": assistant_content_items
            }
            self.messages.append(assistant_message)

        # Debug: Log the completed stream response
        if self.debug_mode:
            self._debug_log("OpenAI Responses Streaming API Response (completed)", {
                "accumulated_content": accumulated_content,
                "tool_calls": tool_calls,
                "final_output": final_output
            })
    
    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        """Non-streaming chat for compatibility"""
        chunks = []
        for chunk in self.chat_stream(user_input, base64_image):
            chunks.append(chunk)
        result = "".join(chunks)
        # If no result, return a message indicating no response
        if not result.strip():
            return "No response received from streaming"
        return result