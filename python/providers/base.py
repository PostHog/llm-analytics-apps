from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
from posthog import Posthog

class BaseProvider(ABC):
    """Base class for all AI providers"""
    
    def __init__(self, posthog_client: Posthog):
        self.posthog_client = posthog_client
        self.messages: List[Dict[str, Any]] = []
        self.tools: List[Dict[str, Any]] = []
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