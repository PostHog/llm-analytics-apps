import os
from posthog.ai.gemini import Client
from posthog import Posthog
from google.genai import types
from .base import StreamingProvider
from typing import Generator, Optional

class GeminiStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self.client = Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            # vertexai=True,
            # project="project-id",
            # location="us-central1",
            posthog_client=posthog_client
        )
        # Store conversation history in Gemini's native format
        self.history = []
        
        # Configure tools using proper Google GenAI types
        weather_function = self.get_tool_definitions()[0]
        self.tools = types.Tool(function_declarations=[weather_function])
        self.config = types.GenerateContentConfig(tools=[self.tools])
    
    def get_name(self):
        return "Google Gemini Streaming"
    
    def get_tool_definitions(self):
        """Return tool definitions in Gemini format"""
        return [
            {
                "name": "get_current_weather",
                "description": "Gets the current weather for a given location using geographical coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "The latitude of the location (e.g., 37.7749 for San Francisco)",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "The longitude of the location (e.g., -122.4194 for San Francisco)",
                        },
                        "location_name": {
                            "type": "string",
                            "description": "A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')",
                        },
                    },
                    "required": ["latitude", "longitude", "location_name"],
                },
            }
        ]
    
    def reset_conversation(self):
        """Reset the conversation history"""
        self.history = []
        self.messages = []
    
    def chat_stream(self, user_input: str, base64_image: Optional[str] = None) -> Generator[str, None, None]:
        """Send a message to Gemini and stream the response"""
        # Build content parts for this message
        if base64_image:
            # Use native Gemini format for images
            parts = [
                {"text": user_input},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64_image
                    }
                }
            ]
        else:
            # Text-only content
            parts = [{"text": user_input}]
        
        # Add user message to history
        self.history.append({
            "role": "user",
            "parts": parts
        })

        # Prepare API request parameters
        request_params = {
            "model": "gemini-2.5-flash",
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "user-hog"),
            "contents": self.history,
            "config": self.config
        }

        # Debug: Log the API request
        if self.debug_mode:
            self._debug_log("Google Gemini Streaming API Request", request_params)

        # Create streaming response
        stream = self.client.models.generate_content_stream(**request_params)

        accumulated_text = ""
        model_parts = []
        tool_results = []
        
        # Process the stream
        try:
            for chunk in stream:
                # Handle text chunks and function calls
                if hasattr(chunk, 'candidates') and chunk.candidates:
                    for candidate in chunk.candidates:
                        if hasattr(candidate, 'content') and candidate.content:
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    # Yield the text delta
                                    text_delta = part.text
                                    accumulated_text += text_delta
                                    yield text_delta
                                elif hasattr(part, 'function_call') and part.function_call:
                                    # Handle function calls during streaming
                                    function_call = part.function_call
                                    
                                    if function_call.name == "get_current_weather":
                                        latitude = function_call.args.get("latitude", 0.0)
                                        longitude = function_call.args.get("longitude", 0.0)
                                        location_name = function_call.args.get("location_name")
                                        weather_result = self.get_weather(latitude, longitude, location_name)
                                        tool_result_text = self.format_tool_result("get_weather", weather_result)
                                        tool_results.append(tool_result_text)
                                        
                                        # Yield the tool result to the stream
                                        yield "\n\n" + tool_result_text
                                        
                                        # Track the function call for history
                                        model_parts.append({"function_call": function_call})
        except Exception as e:
            # If there's an error, yield it as part of the response
            yield f"\n\nError during streaming: {str(e)}"
        
        # Build model parts for history
        if accumulated_text:
            model_parts.append({"text": accumulated_text})
        
        # Add model response to history
        if model_parts:
            self.history.append({
                "role": "model",
                "parts": model_parts
            })

        # Debug: Log the completed stream response
        if self.debug_mode:
            self._debug_log("Google Gemini Streaming API Response (completed)", {
                "accumulated_text": accumulated_text,
                "model_parts": model_parts,
                "tool_results": tool_results
            })

        # Add tool results to history if any
        for tool_result in tool_results:
            self.history.append({
                "role": "model",
                "parts": [{"text": f"Tool result: {tool_result}"}]
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