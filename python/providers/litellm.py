import os
from posthog.ai.litellm import completion
from posthog import Posthog
from .base import BaseProvider, StreamingProvider


class LiteLLMProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog, api_provider="openai", model=None):
        super().__init__(posthog_client)
        self.api_provider = api_provider.lower()
        
        if model is None:
            if self.api_provider == "openai":
                self.model = "openai/gpt-4"
            elif self.api_provider == "anthropic":
                self.model = "claude-3-5-haiku-latest"
            elif self.api_provider == "gemini":
                self.model = "gemini/gemini-1.5-flash"
            else:
                raise ValueError(f"Unsupported API provider: {api_provider}")
        else:
            self.model = f"{self.api_provider}/{model}" if "/" not in model else model
            
        self.reset_conversation()

    def get_name(self):
        return f"LiteLLM ({self.api_provider.title()}) - {self.model}"

    def get_tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather information for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and country, e.g. San Francisco, CA"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]

    def get_initial_messages(self):
        return [
            {
                "role": "system",
                "content": "You are a helpful AI assistant. When users ask about weather, use the get_weather function to provide current conditions."
            }
        ]

    def chat(self, user_input: str, base64_image: str = None) -> str:
        if base64_image:
            message_content = [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        else:
            message_content = user_input

        self.messages.append({"role": "user", "content": message_content})

        response = completion(
            posthog_client=self.posthog_client,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "python-cli-user"),
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto" if self.tools else None
        )

        assistant_message = response.choices[0].message
        
        if assistant_message.tool_calls:
            self.messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": assistant_message.tool_calls
            })

            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                function_args = eval(tool_call.function.arguments)
                
                if function_name == "get_weather":
                    function_result = self.get_weather(function_args["location"])
                else:
                    function_result = f"Unknown function: {function_name}"
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": function_result
                })

            final_response = completion(
                posthog_client=self.posthog_client,
                posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "python-cli-user"),
                model=self.model,
                messages=self.messages
            )
            
            final_message = final_response.choices[0].message.content
            self.messages.append({"role": "assistant", "content": final_message})
            return final_message
        else:
            content = assistant_message.content or ""
            self.messages.append({"role": "assistant", "content": content})
            return content


class LiteLLMStreamingProvider(StreamingProvider):
    def __init__(self, posthog_client: Posthog, api_provider="openai", model=None):
        super().__init__(posthog_client)
        self.api_provider = api_provider.lower()
        
        if model is None:
            if self.api_provider == "openai":
                self.model = "openai/gpt-4"
            elif self.api_provider == "anthropic":
                self.model = "claude-3-5-haiku-latest"
            elif self.api_provider == "gemini":
                self.model = "gemini/gemini-1.5-flash"
            else:
                raise ValueError(f"Unsupported API provider: {api_provider}")
        else:
            self.model = f"{self.api_provider}/{model}" if "/" not in model else model
            
        self.reset_conversation()

    def get_name(self):
        return f"LiteLLM Streaming ({self.api_provider.title()}) - {self.model}"

    def get_tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather information for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and country, e.g. San Francisco, CA"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]

    def get_initial_messages(self):
        return [
            {
                "role": "system",
                "content": "You are a helpful AI assistant. When users ask about weather, use the get_weather function to provide current conditions."
            }
        ]

    def chat(self, user_input: str, base64_image: str = None) -> str:
        response_parts = []
        for chunk in self.chat_stream(user_input, base64_image):
            response_parts.append(chunk)
        return "".join(response_parts)

    def chat_stream(self, user_input: str, base64_image: str = None):
        if base64_image:
            message_content = [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        else:
            message_content = user_input

        self.messages.append({"role": "user", "content": message_content})

        stream = completion(
            posthog_client=self.posthog_client,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "python-cli-user"),
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto" if self.tools else None,
            stream=True
        )

        collected_content = []
        tool_calls = []

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            
            if delta and delta.content:
                content = delta.content
                collected_content.append(content)
                yield content
            
            if delta and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    if tool_call.index is not None:
                        while len(tool_calls) <= tool_call.index:
                            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        
                        if tool_call.id:
                            tool_calls[tool_call.index]["id"] = tool_call.id
                        if tool_call.function.name:
                            tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                        if tool_call.function.arguments:
                            tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments

        final_content = "".join(collected_content)
        
        if tool_calls:
            self.messages.append({
                "role": "assistant",
                "content": final_content,
                "tool_calls": tool_calls
            })

            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = eval(tool_call["function"]["arguments"])
                
                if function_name == "get_weather":
                    function_result = self.get_weather(function_args["location"])
                else:
                    function_result = f"Unknown function: {function_name}"
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": function_result
                })

            final_stream = completion(
                posthog_client=self.posthog_client,
                posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", "python-cli-user"),
                model=self.model,
                messages=self.messages,
                stream=True
            )
            
            for chunk in final_stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content = delta.content
                    yield content
            
            final_message = "".join([chunk.choices[0].delta.content for chunk in final_stream if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content])
            self.messages.append({"role": "assistant", "content": final_message})
        else:
            self.messages.append({"role": "assistant", "content": final_content})