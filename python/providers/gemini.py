import os
from posthog.ai.gemini import Client
from posthog import Posthog
from google.genai import types
from .base import BaseProvider

class GeminiProvider(BaseProvider):
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
        return "Google Gemini"
    
    def get_tool_definitions(self):
        """Return tool definitions in Gemini format"""
        return [
            {
                "name": "get_current_weather",
                "description": "Gets the current weather for a given location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city name, e.g. San Francisco",
                        },
                    },
                    "required": ["location"],
                },
            }
        ]
    
    def reset_conversation(self):
        """Reset the conversation history"""
        self.history = []
        self.messages = []
    
    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to Gemini and get response"""
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

        # Send all messages in conversation history
        message = self.client.models.generate_content(**request_params)

        # Debug: Log the API call (request + response)
        self._debug_api_call("Google Gemini", request_params, message)

        # Collect response parts for display
        display_parts = []
        model_parts = []
        tool_results = []
        
        # Check if Gemini wants to use tools and collect all response parts
        if hasattr(message, 'candidates') and message.candidates:
            for candidate in message.candidates:
                if hasattr(candidate, 'content') and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call = part.function_call
                            model_parts.append({"function_call": function_call})
                            
                            if function_call.name == "get_current_weather":
                                location = function_call.args.get("location", "unknown")
                                weather_result = self.get_weather(location)
                                tool_result_text = self.format_tool_result("get_weather", weather_result)
                                tool_results.append(tool_result_text)
                                display_parts.append(tool_result_text)
                        elif hasattr(part, 'text'):
                            model_parts.append({"text": part.text})
                            display_parts.append(part.text)
        
        # Add model response to history
        if model_parts:
            self.history.append({
                "role": "model",
                "parts": model_parts
            })
        
        # Add tool results to history
        for tool_result in tool_results:
            self.history.append({
                "role": "model",
                "parts": [{"text": f"Tool result: {tool_result}"}]
            })
        
        return "\n\n".join(display_parts) if display_parts else (message.text if hasattr(message, 'text') else "No response received")