import os
import json
import logging
import asyncio
import litellm
from posthog import Posthog
from .compat_base import StreamingProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    OPENAI_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)

class LiteLLMStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog):
        # Set PostHog configuration environment variables
        os.environ["POSTHOG_API_KEY"] = os.getenv("POSTHOG_API_KEY", "")
        os.environ["POSTHOG_API_URL"] = os.getenv("POSTHOG_HOST", "https://app.posthog.com")

        # Use string-based callbacks - our fixed PostHogLogger will handle both sync and async
        try:
            litellm.success_callback = ["posthog"]
            litellm.failure_callback = ["posthog"]
            logging.getLogger(__name__).info("PostHog LiteLLM integration enabled (async)")
        except Exception as e:
            logging.getLogger(__name__).warning(f"PostHog setup failed: {e}, continuing without PostHog")

        super().__init__(posthog_client)

        # Extract session ID from super_properties if available
        existing_props = posthog_client.super_properties or {}
        self.ai_session_id = existing_props.get("$ai_session_id")

        # Set span name for this provider
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "litellm_acompletion"}

        self.model = OPENAI_CHAT_MODEL  # Default model

    def get_tool_definitions(self):
        """Return tool definitions in OpenAI format (LiteLLM uses OpenAI schema)"""
        return [
            {
                "type": "function",
                "function": {
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
                }
            },
            {
                "type": "function",
                "function": {
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
            }
        ]

    def get_name(self):
        return f"LiteLLM Async ({self.model})"

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

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message using LiteLLM async and get response (non-streaming fallback)"""
        # Run the async version synchronously
        return asyncio.run(self._chat_async(user_input, base64_image))

    async def _chat_async(self, user_input: str, base64_image: str = None) -> str:
        """Async implementation of chat"""
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
            metadata = {
                "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            }

            # Add session ID to metadata if available
            if self.ai_session_id:
                metadata["$ai_session_id"] = self.ai_session_id

            request_params = {
                "model": model_to_use,
                "messages": self.messages,
                "tools": self.tools,
                "tool_choice": "auto",
                "max_tokens": DEFAULT_MAX_TOKENS,
                "metadata": metadata
            }

            # Send all messages in conversation history using acompletion
            response = await litellm.acompletion(**request_params)

            # Debug: Log the API call (request + response)
            self._debug_api_call(f"LiteLLM Async ({self.model})", request_params, response)

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
                            latitude = arguments.get("latitude", 0.0)
                            longitude = arguments.get("longitude", 0.0)
                            location_name = arguments.get("location_name")
                            weather_result = self.get_weather(latitude, longitude, location_name)
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
                    elif tool_call.function.name == "tell_joke":
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                            setup = arguments.get("setup", "")
                            punchline = arguments.get("punchline", "")
                            joke_result = self.tell_joke(setup, punchline)
                            tool_result_text = self.format_tool_result("tell_joke", joke_result)
                            display_parts.append(tool_result_text)

                            # Add tool result to message history
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": joke_result
                            })

                        except json.JSONDecodeError:
                            display_parts.append("❌ Error parsing joke tool arguments")

                # Get final response after tool execution
                try:
                    # Prepare API request parameters for final response
                    final_metadata = {
                        "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", "user-hog"),
                        "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                    }

                    # Add session ID to metadata if available
                    if self.ai_session_id:
                        final_metadata["$ai_session_id"] = self.ai_session_id

                    final_request_params = {
                        "model": model_to_use,
                        "messages": self.messages,
                        "max_tokens": DEFAULT_MAX_TOKENS,
                        "metadata": final_metadata
                    }

                    final_response = await litellm.acompletion(**final_request_params)

                    # Debug: Log the API call (request + response)
                    self._debug_api_call(f"LiteLLM Async ({self.model})", final_request_params, final_response)

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

    def chat_stream(self, user_input: str, base64_image: str = None):
        """Stream response using LiteLLM async streaming"""
        # Run async generator in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = self._chat_stream_async(user_input, base64_image)
            while True:
                try:
                    chunk = loop.run_until_complete(async_gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def _chat_stream_async(self, user_input: str, base64_image: str = None):
        """Async streaming implementation"""
        # Add user message to history
        if base64_image:
            user_content = [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
            model_to_use = OPENAI_VISION_MODEL
        else:
            user_content = user_input
            model_to_use = self.model

        user_message = {"role": "user", "content": user_content}

        if not self.messages:
            self.messages = self.get_initial_messages()

        self.messages.append(user_message)

        try:
            metadata = {
                "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            }

            if self.ai_session_id:
                metadata["$ai_session_id"] = self.ai_session_id

            # Use acompletion with streaming
            response = await litellm.acompletion(
                model=model_to_use,
                messages=self.messages,
                tools=self.tools,
                tool_choice="auto",
                max_tokens=DEFAULT_MAX_TOKENS,
                metadata=metadata,
                stream=True
            )

            full_content = ""
            tool_calls_data = []

            async for chunk in response:
                delta = chunk.choices[0].delta

                # Handle content streaming
                if hasattr(delta, 'content') and delta.content:
                    full_content += delta.content
                    yield delta.content

                # Handle tool calls
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index >= len(tool_calls_data):
                            tool_calls_data.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": ""}
                            })
                        if tc.function.arguments:
                            tool_calls_data[tc.index]["function"]["arguments"] += tc.function.arguments

            # Process tool calls if any
            if tool_calls_data:
                self.messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls_data
                })

                for tool_call in tool_calls_data:
                    if tool_call["function"]["name"] == "get_weather":
                        try:
                            arguments = json.loads(tool_call["function"]["arguments"])
                            weather_result = self.get_weather(
                                arguments.get("latitude", 0.0),
                                arguments.get("longitude", 0.0),
                                arguments.get("location_name")
                            )
                            yield f"\n\n{self.format_tool_result('get_weather', weather_result)}"

                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": weather_result
                            })
                        except Exception as e:
                            yield f"\n\n❌ Error processing weather tool: {str(e)}"
                    elif tool_call["function"]["name"] == "tell_joke":
                        try:
                            arguments = json.loads(tool_call["function"]["arguments"])
                            joke_result = self.tell_joke(
                                arguments.get("setup", ""),
                                arguments.get("punchline", "")
                            )
                            yield f"\n\n{self.format_tool_result('tell_joke', joke_result)}"

                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": joke_result
                            })
                        except Exception as e:
                            yield f"\n\n❌ Error processing joke tool: {str(e)}"

                # Get final response after tool calls
                final_response = await litellm.acompletion(
                    model=model_to_use,
                    messages=self.messages,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    metadata=metadata,
                    stream=True
                )

                final_content = ""
                async for chunk in final_response:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        final_content += delta.content
                        yield delta.content

                if final_content:
                    self.messages.append({"role": "assistant", "content": final_content})

            else:
                # No tool calls, just add the response
                if full_content:
                    self.messages.append({"role": "assistant", "content": full_content})

        except Exception as e:
            yield f"❌ Error: {str(e)}"
