from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
from posthog import Posthog
import os
import json
import random
import requests
from .constants import WEATHER_TEMP_MIN_CELSIUS, WEATHER_TEMP_MAX_CELSIUS

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
        
    def get_weather(self, latitude: float, longitude: float, location_name: str = None) -> str:
        """Get real weather data from Open-Meteo API using coordinates"""
        try:
            # Get weather data from Open-Meteo API
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm"
            }

            weather_response = requests.get(weather_url, params=weather_params, timeout=10)
            weather_response.raise_for_status()
            weather_data = weather_response.json()

            current = weather_data.get("current", {})
            temp_celsius = current.get("temperature_2m", 0)
            temp_fahrenheit = int(temp_celsius * 9/5 + 32)
            feels_like_celsius = current.get("apparent_temperature", temp_celsius)
            humidity = current.get("relative_humidity_2m", 0)
            wind_speed = current.get("wind_speed_10m", 0)
            precipitation = current.get("precipitation", 0)

            # Weather code interpretation (WMO codes)
            weather_code = current.get("weather_code", 0)
            weather_descriptions = {
                0: "clear skies",
                1: "mainly clear",
                2: "partly cloudy",
                3: "overcast",
                45: "foggy",
                48: "depositing rime fog",
                51: "light drizzle",
                53: "moderate drizzle",
                55: "dense drizzle",
                61: "slight rain",
                63: "moderate rain",
                65: "heavy rain",
                71: "slight snow",
                73: "moderate snow",
                75: "heavy snow",
                77: "snow grains",
                80: "slight rain showers",
                81: "moderate rain showers",
                82: "violent rain showers",
                85: "slight snow showers",
                86: "heavy snow showers",
                95: "thunderstorm",
                96: "thunderstorm with slight hail",
                99: "thunderstorm with heavy hail"
            }
            weather_desc = weather_descriptions.get(weather_code, "unknown conditions")

            # Use location_name if provided, otherwise fall back to coordinates
            location_str = location_name if location_name else f"coordinates ({latitude}, {longitude})"

            result = f"The current weather in {location_str} is {temp_celsius}°C ({temp_fahrenheit}°F) "
            result += f"with {weather_desc}. "
            result += f"Feels like {feels_like_celsius}°C. "
            result += f"Humidity: {humidity}%, Wind: {wind_speed} km/h"

            if precipitation > 0:
                result += f", Precipitation: {precipitation} mm"

            return result

        except requests.exceptions.RequestException as e:
            # Fallback to mock data if API fails
            location_str = location_name if location_name else f"coordinates ({latitude}, {longitude})"
            return f"Weather API unavailable for {location_str}. Using mock data: experiencing typical weather conditions."
        except (KeyError, ValueError, TypeError) as e:
            location_str = location_name if location_name else f"coordinates ({latitude}, {longitude})"
            return f"Error parsing weather data for {location_str}: {str(e)}"
        
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