import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import BaseProvider

class OpenAIChatProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
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
                "content": "You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather."
            }
        ]
    
    def get_tool_definitions(self):
        """Return tool definitions in OpenAI Chat format"""
        return [
            {
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
        return "OpenAI Chat Completions"
    
    
    def embed(self, text: str, model: str = "text-embedding-3-small") -> list:
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
        model_name = "gpt-4o" if base64_image else "gpt-4o-mini"
        response = self.client.chat.completions.create(
            model=model_name,
            max_tokens=200,
            temperature=0.7,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "user-hog"),
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto"
        )
        
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
                        location = arguments.get("location", "unknown")
                        weather_result = self.get_weather(location)
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