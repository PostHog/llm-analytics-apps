import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import StreamingProvider
from typing import Generator, Optional
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class OpenAIChatStreamingProvider(StreamingProvider):
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
        return "OpenAI Chat Completions Streaming"
    
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
        
        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL

        # Prepare API request parameters
        request_params = {
            "model": model_name,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": "auto",
            "stream": True,
            "stream_options": {
                "include_usage": True
            }
        }

        # Debug: Log the API request
        if self.debug_mode:
            self._debug_log("OpenAI Chat Completions Streaming API Request", request_params)

        # Create streaming response
        stream = self.client.chat.completions.create(**request_params)

        accumulated_content = ""
        tool_calls = []
        tool_calls_by_index = {}
        
        try:
            for chunk in stream:
                # Handle text content
                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    
                    # Process text delta
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'content') and choice.delta.content:
                        content = choice.delta.content
                        accumulated_content += content
                        yield content
                    
                    # Process tool calls
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                        for tool_call_delta in choice.delta.tool_calls:
                            index = tool_call_delta.index
                            
                            # Initialize or get existing tool call
                            if index not in tool_calls_by_index:
                                tool_calls_by_index[index] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": ""
                                    }
                                }
                            
                            tool_call = tool_calls_by_index[index]
                            
                            # Update tool call information
                            if hasattr(tool_call_delta, 'id') and tool_call_delta.id:
                                tool_call["id"] = tool_call_delta.id
                            
                            if hasattr(tool_call_delta, 'function'):
                                if hasattr(tool_call_delta.function, 'name') and tool_call_delta.function.name:
                                    tool_call["function"]["name"] = tool_call_delta.function.name
                                if hasattr(tool_call_delta.function, 'arguments') and tool_call_delta.function.arguments:
                                    tool_call["function"]["arguments"] += tool_call_delta.function.arguments
                    
                    # Check for finish reason
                    if hasattr(choice, 'finish_reason') and choice.finish_reason == 'tool_calls':
                        # Convert indexed tool calls to list and execute them
                        completed_tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]
                        
                        for tool_call in completed_tool_calls:
                            tool_calls.append(tool_call)
                            
                            if tool_call["function"]["name"] == "get_weather":
                                try:
                                    args = json.loads(tool_call["function"]["arguments"])
                                    location = args.get("location", "unknown")
                                    weather_result = self.get_weather(location)
                                    tool_result_text = self.format_tool_result("get_weather", weather_result)
                                    yield "\n\n" + tool_result_text
                                except json.JSONDecodeError as e:
                                    print(f"Error parsing tool arguments: {e}")
        
        except Exception as e:
            yield f"\n\nError during streaming: {str(e)}"
        
        # Save assistant message
        assistant_message = {
            "role": "assistant"
        }
        
        if accumulated_content:
            assistant_message["content"] = accumulated_content
        
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        
        self.messages.append(assistant_message)

        # Debug: Log the completed stream response
        if self.debug_mode:
            self._debug_log("OpenAI Chat Completions Streaming API Response (completed)", {
                "accumulated_content": accumulated_content,
                "tool_calls": tool_calls
            })

        # Add tool results to messages if any tools were called
        for tool_call in tool_calls:
            if tool_call["function"]["name"] == "get_weather":
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                    location = args.get("location", "unknown")
                    weather_result = self.get_weather(location)

                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": weather_result
                    }
                    self.messages.append(tool_result_message)
                except json.JSONDecodeError:
                    pass
    
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