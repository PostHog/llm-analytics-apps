import os
import json
import logging
import litellm
from posthog import Posthog
from .base import BaseProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class LiteLLMProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        # Set PostHog configuration environment variables
        os.environ["POSTHOG_API_KEY"] = os.getenv("POSTHOG_API_KEY", "")
        os.environ["POSTHOG_API_URL"] = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
        
        # Use string-based callbacks - our fixed PostHogLogger will handle both sync and async
        try:
            litellm.success_callback = ["posthog"]
            litellm.failure_callback = ["posthog"]
            logging.getLogger(__name__).info("PostHog LiteLLM integration enabled")
        except Exception as e:
            logging.getLogger(__name__).warning(f"PostHog setup failed: {e}, continuing without PostHog")
        
        super().__init__(posthog_client)
        self.model = OPENAI_CHAT_MODEL  # Default model
    
    def get_tool_definitions(self):
        """Return tool definitions in OpenAI format (LiteLLM uses OpenAI schema)"""
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
        return f"LiteLLM ({self.model})"
    
    def set_model(self, model: str):
        """Set the model to use for completions"""
        self.model = model
    
    def get_initial_messages(self):
        """Return initial system message"""
        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_FRIENDLY
            }
        ]
    
    def embed(self, text: str, model: str = OPENAI_EMBEDDING_MODEL) -> list:
        """Create embeddings using LiteLLM"""
        try:
            response = litellm.embedding(
                model=model,
                input=text,
                metadata={"distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "user-hog")}
            )
            
            # Extract embedding vector from response
            if hasattr(response, 'data') and response.data:
                return response.data[0]['embedding']
            return []
        except Exception as e:
            print(f"Embedding error: {e}")
            return []
    
    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message using LiteLLM and get response"""
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
            # Use vision model for images
            model_to_use = OPENAI_VISION_MODEL
        else:
            user_content = user_input
            model_to_use = self.model
            
        user_message = {
            "role": "user",
            "content": user_content
        }
        
        # Initialize messages if empty
        if not self.messages:
            self.messages = self.get_initial_messages()
            
        self.messages.append(user_message)
        
        try:
            # Prepare API request parameters
            request_params = {
                "model": model_to_use,
                "messages": self.messages,
                "tools": self.tools,
                "tool_choice": "auto",
                "max_tokens": 500,
                "temperature": 0.7,
                "metadata": {
                    "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                    "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                }
            }

            # Send all messages in conversation history
            response = litellm.completion(**request_params)

            # Debug: Log the API call (request + response)
            self._debug_api_call(f"LiteLLM ({self.model})", request_params, response)

            # Extract the assistant's response
            assistant_message = response.choices[0].message
            
            # Handle tool calls
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                # Add assistant message with tool calls to history
                self.messages.append({
                    "role": "assistant", 
                    "content": assistant_message.content,
                    "tool_calls": [tc.dict() for tc in assistant_message.tool_calls]
                })
                
                # Process tool calls
                display_parts = []
                if assistant_message.content:
                    display_parts.append(assistant_message.content)
                
                for tool_call in assistant_message.tool_calls:
                    if tool_call.function.name == "get_weather":
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                            location = arguments.get("location", "unknown")
                            weather_result = self.get_weather(location)
                            tool_result_text = self.format_tool_result("get_weather", weather_result)
                            display_parts.append(tool_result_text)
                            
                            # Add tool result to message history
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": weather_result
                            })
                            
                        except json.JSONDecodeError:
                            display_parts.append("❌ Error parsing weather tool arguments")
                
                # Get final response after tool execution
                try:
                    # Prepare API request parameters for final response
                    final_request_params = {
                        "model": model_to_use,
                        "messages": self.messages,
                        "max_tokens": 200,
                        "temperature": 0.7,
                        "metadata": {
                            "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "user-hog"),
                            "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                        }
                    }

                    final_response = litellm.completion(**final_request_params)

                    # Debug: Log the API call (request + response)
                    self._debug_api_call(f"LiteLLM ({self.model})", final_request_params, final_response)

                    final_content = final_response.choices[0].message.content
                    if final_content:
                        display_parts.append(final_content)
                        
                        # Add final assistant response to history
                        self.messages.append({
                            "role": "assistant",
                            "content": final_content
                        })
                
                except Exception as e:
                    display_parts.append(f"❌ Error getting final response: {str(e)}")
                
                return "\n\n".join(display_parts)
            
            else:
                # No tool calls, regular response
                content = assistant_message.content or "No response received"
                
                # Add assistant's response to conversation history
                self.messages.append({
                    "role": "assistant",
                    "content": content
                })
                
                return content
                
        except Exception as e:
            return f"❌ Error: {str(e)}"