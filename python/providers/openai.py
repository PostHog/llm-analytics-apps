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
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_responses"}

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
                            "description": "The setup of the joke, typically a question (e.g., 'Why did the chicken cross the road?')"
                        },
                        "punchline": {
                            "type": "string",
                            "description": "The punchline or answer to the joke (e.g., 'To get to the other side!')"
                        }
                    },
                    "required": ["setup", "punchline"]
                }
            },
            {
                "type": "function",
                "name": "roll_dice",
                "description": "Roll one or more dice with a specified number of sides",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "num_dice": {"type": "integer", "description": "Number of dice to roll (default: 1)"},
                        "sides": {"type": "integer", "description": "Number of sides per die (default: 6)"},
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "check_time",
                "description": "Get the current time in a specific timezone (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo')",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "description": "IANA timezone name (e.g., 'US/Eastern', 'Europe/Paris')"},
                    },
                    "required": ["timezone"]
                }
            },
            {
                "type": "function",
                "name": "calculate",
                "description": "Evaluate a mathematical expression (basic arithmetic: +, -, *, /, parentheses)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "The math expression to evaluate (e.g., '(2 + 3) * 4')"},
                    },
                    "required": ["expression"]
                }
            },
            {
                "type": "function",
                "name": "convert_units",
                "description": "Convert a value between common units (km/miles, kg/lbs, celsius/fahrenheit, meters/feet, liters/gallons)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "description": "The numeric value to convert"},
                        "from_unit": {"type": "string", "description": "The source unit (e.g., 'km', 'celsius', 'kg')"},
                        "to_unit": {"type": "string", "description": "The target unit (e.g., 'miles', 'fahrenheit', 'lbs')"},
                    },
                    "required": ["value", "from_unit", "to_unit"]
                }
            },
            {
                "type": "function",
                "name": "generate_inspirational_quote",
                "description": "Get an inspirational quote, optionally on a specific topic (general, perseverance, creativity, success, teamwork)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Topic for the quote (general, perseverance, creativity, success, teamwork)"},
                    },
                    "required": []
                }
            },
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
                if hasattr(output_item, 'name'):
                    # Get the tool call details from the response
                    call_id = getattr(output_item, 'call_id', f"call_{output_item.name}")
                    tool_arguments = getattr(output_item, 'arguments', '{}')

                    # Parse arguments to execute the tool
                    arguments = {}
                    try:
                        arguments = json.loads(tool_arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_result = self.execute_tool(output_item.name, arguments)
                    if tool_result is not None:
                        tool_result_text = self.format_tool_result(output_item.name, tool_result)
                        display_parts.append(tool_result_text)
                        assistant_content_items.append({
                            "type": "output_text",
                            "text": tool_result
                        })

        if assistant_content_items:
            assistant_message = {
                "role": "assistant",
                "content": assistant_content_items
            }
            self.messages.append(assistant_message)

        return "\n\n".join(display_parts) if display_parts else "No response received"