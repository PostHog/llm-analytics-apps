import os
from posthog.ai.anthropic import Anthropic
from posthog import Posthog
from .compat_base import StreamingProvider
from typing import Generator, Optional
import json
from .constants import (
    ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    DEFAULT_THINKING_ENABLED,
    DEFAULT_THINKING_BUDGET_TOKENS
)

class AnthropicStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog, enable_thinking: bool = False, thinking_budget: int = None):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "anthropic_messages_streaming"}

        self.client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            posthog_client=posthog_client
        )
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget or DEFAULT_THINKING_BUDGET_TOKENS
    
    def get_tool_definitions(self):
        """Return tool definitions in Anthropic format"""
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather for a specific location using geographical coordinates",
                "input_schema": {
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
                "name": "tell_joke",
                "description": "Tell a joke with a question-style setup and an answer punchline",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "setup": {
                            "type": "string",
                            "description": "The setup of the joke, typically a question (e.g., 'Why did the chicken cross the road?')"
                        },
                        "punchline": {
                            "type": "string",
                            "description": "The punchline or answer to the joke (e.g., 'To get to the other side!')"
                        }
                    },
                    "required": ["setup", "punchline"]
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
        # Note: max_tokens must be greater than thinking.budget_tokens
        thinking_budget = max(self.thinking_budget, 1024) if self.enable_thinking else 0
        max_tokens = max(DEFAULT_MAX_TOKENS, thinking_budget + 2000) if self.enable_thinking else DEFAULT_MAX_TOKENS
        
        request_params = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "tools": self.tools,
            "messages": self.messages,
            "stream": True
        }
        
        # Add extended thinking if enabled
        if self.enable_thinking:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget
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
        current_thinking_block = None
        
        # Process the stream events
        try:
            event_count = 0
            for event in stream:
                event_count += 1
                
                # Skip events without a type attribute or handle different event structures
                if not hasattr(event, 'type'):
                    continue
                    
                # Handle delta events (text, thinking, tool input)
                if event.type == "content_block_delta":
                    if hasattr(event, 'delta') and hasattr(event.delta, 'thinking'):
                        # Handle thinking content delta
                        thinking_text = event.delta.thinking
                        if current_thinking_block is not None:
                            current_thinking_block["thinking"] += thinking_text
                        # Only yield thinking if enabled
                        if self.enable_thinking:
                            yield thinking_text
                    elif hasattr(event, 'delta') and hasattr(event.delta, 'text'):
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
                            if content_block.type == "thinking":
                                # Start a new thinking content block
                                if self.enable_thinking:
                                    yield "\n\n💭 Thinking: "
                                current_thinking_block = {
                                    "type": "thinking",
                                    "thinking": ""
                                }
                                assistant_content.append(current_thinking_block)
                                current_text_block = None
                            elif content_block.type == "text":
                                # Start a new text content block
                                # If we just had thinking, add some spacing
                                if current_thinking_block is not None and self.enable_thinking:
                                    yield "\n\n"
                                current_text_block = {
                                    "type": "text",
                                    "text": ""
                                }
                                assistant_content.append(current_text_block)
                                current_thinking_block = None
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
                                current_text_block = None
                                current_thinking_block = None
                
                # Handle content block stop (finalize tool, text, or thinking)
                elif event.type == "content_block_stop":
                    current_text_block = None  # Reset current text block
                    current_thinking_block = None  # Reset current thinking block
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
                                latitude = last_tool["input"].get("latitude", 0.0)
                                longitude = last_tool["input"].get("longitude", 0.0)
                                location_name = last_tool["input"].get("location_name")
                                weather_result = self.get_weather(latitude, longitude, location_name)
                                tool_result_text = self.format_tool_result("get_weather", weather_result)
                                yield "\n\n" + tool_result_text
                            elif last_tool["name"] == "tell_joke":
                                setup = last_tool["input"].get("setup", "")
                                punchline = last_tool["input"].get("punchline", "")
                                joke_result = self.tell_joke(setup, punchline)
                                tool_result_text = self.format_tool_result("tell_joke", joke_result)
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
                latitude = tool["input"].get("latitude", 0.0)
                longitude = tool["input"].get("longitude", 0.0)
                location_name = tool["input"].get("location_name")
                weather_result = self.get_weather(latitude, longitude, location_name)

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
            elif tool.get("name") == "tell_joke" and tool.get("input"):
                setup = tool["input"].get("setup", "")
                punchline = tool["input"].get("punchline", "")
                joke_result = self.tell_joke(setup, punchline)

                tool_result_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool.get("id"),
                            "content": joke_result
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