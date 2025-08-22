import os
import json
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import StreamingProvider
from typing import Generator, Optional

class OpenAIStreamingProvider(StreamingProvider):
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
        return "OpenAI Responses Streaming"
    
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
        model_name = "gpt-4o" if base64_image else "gpt-4o-mini"
        
        # Create streaming response
        stream = self.client.responses.create(
            model=model_name,
            max_output_tokens=200,
            temperature=0.7,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "user-hog"),
            input=self.messages,
            instructions="You are a friendly AI that just makes conversation. You have access to a weather tool if the user asks about weather.",
            tools=self.tools,
            stream=True
        )
        
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
                                    
                                    location = arguments.get("location", "unknown")
                                    weather_result = self.get_weather(location)
                                    tool_result_text = self.format_tool_result("get_weather", weather_result)
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
        if accumulated_content:
            assistant_message = {
                "role": "assistant",
                "content": accumulated_content
            }
            self.messages.append(assistant_message)
        elif tool_calls and any(tc.get("arguments") for tc in tool_calls):
            # If there was a tool call but no text content, save the tool result as assistant message
            tool_results_text = ""
            for tool_call in tool_calls:
                if tool_call.get("arguments") and tool_call.get("name") == "get_weather":
                    try:
                        args = json.loads(tool_call["arguments"])
                        location = args.get("location", "unknown")
                        weather_result = self.get_weather(location)
                        tool_results_text += weather_result
                    except json.JSONDecodeError:
                        pass
            
            if tool_results_text:
                assistant_message = {
                    "role": "assistant",
                    "content": tool_results_text
                }
                self.messages.append(assistant_message)
    
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