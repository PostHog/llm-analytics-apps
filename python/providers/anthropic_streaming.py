import os
from posthog.ai.anthropic import Anthropic
from posthog import Posthog
from .base import StreamingProvider
from typing import Generator, Optional
import json
from .constants import (
    ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID
)

class AnthropicStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self.client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            posthog_client=posthog_client
        )
    
    def get_tool_definitions(self):
        """Return tool definitions in Anthropic format"""
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather for a specific location",
                "input_schema": {
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
        ]
    
    def get_name(self):
        return "Anthropic Streaming"
    
    def chat_stream(self, user_input: str, base64_image: Optional[str] = None) -> Generator[str, None, None]:
        """Send a message to Anthropic and stream the response"""
        # Add user message to history
        if base64_image:
            user_content = [
                {"type": "text", "text": user_input},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_image
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

        # Prepare API request parameters
        request_params = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "tools": self.tools,
            "messages": self.messages,
            "stream": True
        }

        # Debug: Log the API request (no response for streaming)
        if self.debug_mode:
            self._debug_log("Anthropic Streaming API Request", request_params)

        # Create streaming response using create() with stream=True
        # The PostHog wrapper's stream() method expects stream=True to be passed
        stream = self.client.messages.create(**request_params)
        
        accumulated_content = ""
        assistant_content = []
        tools_used = []
        current_text_block = None
        
        # Process the stream events
        try:
            event_count = 0
            for event in stream:
                event_count += 1
                
                # Skip events without a type attribute or handle different event structures
                if not hasattr(event, 'type'):
                    continue
                    
                # Handle text delta events
                if event.type == "content_block_delta":
                    if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
                        text = event.delta.text
                        accumulated_content += text
                        yield text
                        # Update the current text block if we're tracking one
                        if current_text_block is not None:
                            current_text_block["text"] += text
                    elif hasattr(event, 'delta') and hasattr(event.delta, 'partial_json'):
                        # Handle tool input JSON delta
                        if tools_used:
                            last_tool = tools_used[-1]
                            if "input_string" not in last_tool:
                                last_tool["input_string"] = ""
                            last_tool["input_string"] += event.delta.partial_json or ""
                
                # Handle content block start
                elif event.type == "content_block_start":
                    if hasattr(event, 'content_block'):
                        content_block = event.content_block
                        
                        if hasattr(content_block, 'type'):
                            if content_block.type == "text":
                                # Start a new text content block
                                current_text_block = {
                                    "type": "text",
                                    "text": ""
                                }
                                assistant_content.append(current_text_block)
                            elif content_block.type == "tool_use":
                                tool_info = {
                                    "id": content_block.id if hasattr(content_block, 'id') else None,
                                    "name": content_block.name if hasattr(content_block, 'name') else None,
                                    "input": {}
                                }
                                tools_used.append(tool_info)
                                
                                # Add tool use to assistant content immediately
                                assistant_content.append({
                                    "type": "tool_use",
                                    "id": tool_info["id"],
                                    "name": tool_info["name"],
                                    "input": tool_info["input"]  # Will be updated later
                                })
                                current_text_block = None  # Not a text block
                
                # Handle content block stop (finalize tool or text)
                elif event.type == "content_block_stop":
                    current_text_block = None  # Reset current text block
                    if tools_used and tools_used[-1].get("input_string"):
                        last_tool = tools_used[-1]
                        try:
                            last_tool["input"] = json.loads(last_tool["input_string"])
                            del last_tool["input_string"]
                            
                            # Update the input in assistant_content
                            # Find the corresponding tool_use in assistant_content and update its input
                            for content in assistant_content:
                                if content.get("type") == "tool_use" and content.get("id") == last_tool["id"]:
                                    content["input"] = last_tool["input"]
                                    break
                            
                            # Execute the tool
                            if last_tool["name"] == "get_weather":
                                location = last_tool["input"].get("location", "unknown")
                                weather_result = self.get_weather(location)
                                tool_result_text = self.format_tool_result("get_weather", weather_result)
                                yield "\n\n" + tool_result_text
                        except (json.JSONDecodeError, AttributeError):
                            pass
                
                # Handle message start/stop events
                elif event.type in ["message_start", "message_stop", "message_delta"]:
                    # These events might contain usage info but we can skip them for now
                    pass
                    
        except Exception as e:
            # If there's an error, yield it as part of the response
            yield f"\n\nError during streaming: {str(e)}"
        
        # If we didn't get any events at all, log it
        if event_count == 0:
            yield "No events received from stream"
        
        # Save assistant message
        assistant_message = {
            "role": "assistant",
            "content": assistant_content if assistant_content else [{"type": "text", "text": accumulated_content or ""}]
        }
        self.messages.append(assistant_message)

        # Debug: Log the completed stream response
        if self.debug_mode:
            self._debug_log("Anthropic Streaming API Response (completed)", {
                "accumulated_content": accumulated_content,
                "assistant_content": assistant_content,
                "tools_used": tools_used,
                "event_count": event_count
            })
        
        # If tools were used, add tool results to messages
        for tool in tools_used:
            if tool.get("name") == "get_weather" and tool.get("input"):
                location = tool["input"].get("location", "unknown")
                weather_result = self.get_weather(location)
                
                tool_result_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool.get("id"),
                            "content": weather_result
                        }
                    ]
                }
                self.messages.append(tool_result_message)
    
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