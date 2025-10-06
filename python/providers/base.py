from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
from posthog import Posthog
import os
import json

class BaseProvider(ABC):
    """Base class for all AI providers"""

    def __init__(self, posthog_client: Posthog):
        self.posthog_client = posthog_client
        self.messages: List[Dict[str, Any]] = []
        self.tools: List[Dict[str, Any]] = []
        self.debug_mode = os.getenv('DEBUG') == '1'
        self._initialize_tools()
        
    def _initialize_tools(self):
        """Initialize tools from provider-specific definitions"""
        self.tools = self.get_tool_definitions()
        
    @abstractmethod
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return tool definitions in provider-specific format"""
        pass
        
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the provider"""
        pass
        
    @abstractmethod
    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        """Send a message and get response"""
        pass
        
    def reset_conversation(self):
        """Reset the conversation history"""
        self.messages = self.get_initial_messages()
        
    def get_initial_messages(self) -> List[Dict[str, Any]]:
        """Return initial messages (e.g., system prompts)"""
        return []
        
    def get_weather(self, location: str) -> str:
        """Mock weather function - returns fake weather data"""
        return f"The current weather in {location} is 22°C (72°F) with partly cloudy skies and light winds."
        
    def format_tool_result(self, tool_name: str, result: str) -> str:
        """Format tool result for display"""
        if tool_name == "get_weather":
            return f"🌤️  Weather: {result}"
        return result

    def _debug_log(self, title: str, data: Any, truncate: bool = True):
        """Log debug information in a clear, formatted way"""
        if not self.debug_mode:
            return

        print("\n" + "=" * 80)
        print(f"🐛 DEBUG: {title}")
        print("=" * 80)

        if isinstance(data, (dict, list)):
            json_str = json.dumps(data, indent=2, default=str)
            # Truncate very long outputs
            if truncate and len(json_str) > 5000:
                json_str = json_str[:5000] + "\n... (truncated)"
            print(json_str)
        else:
            data_str = str(data)
            if truncate and len(data_str) > 5000:
                data_str = data_str[:5000] + "\n... (truncated)"
            print(data_str)

        print("=" * 80 + "\n")

    def _debug_api_call(self, provider_name: str, request_data: Any, response_data: Any = None):
        """
        Simplified debug logging for API calls.
        Just pass the request and optionally response objects - they'll be converted to JSON automatically.

        Usage:
            # Log request only (before API call)
            self._debug_api_call("Anthropic", request_params)

            # Log both request and response (after API call)
            self._debug_api_call("Anthropic", request_params, response)
        """
        if not self.debug_mode:
            return

        # Convert objects to dict for JSON serialization
        def to_dict(obj):
            if hasattr(obj, 'model_dump'):  # Pydantic models
                return obj.model_dump()
            elif hasattr(obj, '__dict__'):  # Regular objects
                return obj.__dict__
            elif isinstance(obj, (dict, list, str, int, float, bool, type(None))):
                return obj
            else:
                return str(obj)

        self._debug_log(f"{provider_name} API Request", to_dict(request_data))

        if response_data is not None:
            self._debug_log(f"{provider_name} API Response", to_dict(response_data))


class StreamingProvider(BaseProvider):
    """Base class for providers that support streaming"""
    
    @abstractmethod
    def chat_stream(self, user_input: str, base64_image: Optional[str] = None) -> Generator[str, None, None]:
        """Send a message and stream the response"""
        pass
        
    def default_chat_stream(self, user_input: str, base64_image: Optional[str] = None) -> Generator[str, None, None]:
        """Default implementation that yields the full response at once"""
        response = self.chat(user_input, base64_image)
        yield response