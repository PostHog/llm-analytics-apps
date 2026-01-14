"""
OpenAI Agents SDK - Multi-Agent Example with PostHog Tracing

This example demonstrates:
- Multiple specialized agents with different capabilities
- Agent handoffs based on user intent
- Tool usage (weather, math)
- PostHog instrumentation for LLM analytics

The triage agent routes requests to specialized agents:
- Weather Agent: Handles weather-related queries with a weather tool
- Math Agent: Handles calculations and math problems
- General Agent: Handles general questions and conversation
"""

from typing import Annotated
from pydantic import BaseModel, Field
from agents import Agent, function_tool


# Weather tool and agent
class WeatherInfo(BaseModel):
    city: str = Field(description="The city name")
    temperature_range: str = Field(description="The temperature range")
    conditions: str = Field(description="Weather conditions")
    humidity: str = Field(description="Humidity percentage")


@function_tool
def get_weather(
    city: Annotated[str, "The city to get weather for"],
    country: Annotated[str, "The country (optional)"] = ""
) -> WeatherInfo:
    """Get current weather information for a city."""
    print(f"[tool] get_weather called for {city}")
    # Mock weather data - in production this would call a real API
    weather_data = {
        "tokyo": WeatherInfo(
            city="Tokyo",
            temperature_range="18-24°C",
            conditions="Partly cloudy",
            humidity="65%"
        ),
        "london": WeatherInfo(
            city="London",
            temperature_range="12-18°C",
            conditions="Overcast with light rain",
            humidity="78%"
        ),
        "new york": WeatherInfo(
            city="New York",
            temperature_range="15-22°C",
            conditions="Clear and sunny",
            humidity="55%"
        ),
        "paris": WeatherInfo(
            city="Paris",
            temperature_range="14-20°C",
            conditions="Sunny",
            humidity="60%"
        ),
        "montreal": WeatherInfo(
            city="Montreal",
            temperature_range="-5-2°C",
            conditions="Snow showers",
            humidity="82%"
        ),
    }
    city_lower = city.lower()
    if city_lower in weather_data:
        return weather_data[city_lower]
    return WeatherInfo(
        city=city,
        temperature_range="15-25°C",
        conditions="Clear",
        humidity="50%"
    )


# Math tool
@function_tool
def calculate(
    expression: Annotated[str, "A mathematical expression to evaluate (e.g., '2 + 2 * 3')"]
) -> str:
    """Safely evaluate a mathematical expression."""
    print(f"[tool] calculate called with: {expression}")
    try:
        # Only allow safe math operations
        allowed_chars = set("0123456789+-*/().^ ")
        if not all(c in allowed_chars for c in expression):
            return f"Error: Invalid characters in expression"
        # Replace ^ with ** for exponentiation
        expression = expression.replace("^", "**")
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error calculating: {str(e)}"


# Specialized Agents
weather_agent = Agent(
    name="WeatherAgent",
    instructions="""You are a helpful weather assistant.
    Use the get_weather tool to fetch weather information for any city the user asks about.
    Provide friendly, informative responses about the weather.
    Always include the temperature, conditions, and humidity in your response.""",
    model="gpt-4o-mini",
    tools=[get_weather],
)

math_agent = Agent(
    name="MathAgent",
    instructions="""You are a helpful math assistant.
    Use the calculate tool to solve mathematical problems.
    Explain your work step by step when solving complex problems.
    You can handle basic arithmetic, percentages, and simple algebra.""",
    model="gpt-4o-mini",
    tools=[calculate],
)

general_agent = Agent(
    name="GeneralAgent",
    instructions="""You are a helpful general assistant.
    You help with general questions, provide information, and engage in friendly conversation.
    If the user asks about weather or math, let them know you can help with that too!""",
    model="gpt-4o-mini",
)

# Triage Agent - routes to specialized agents
triage_agent = Agent(
    name="TriageAgent",
    instructions="""You are a helpful assistant that routes requests to specialized agents.

    Analyze the user's message and hand off to the appropriate agent:
    - WeatherAgent: For weather-related questions (forecasts, temperature, conditions)
    - MathAgent: For math problems, calculations, or number-related questions
    - GeneralAgent: For general questions, conversation, or anything else

    Be efficient - hand off to the specialist right away without asking follow-up questions.""",
    model="gpt-4o-mini",
    handoffs=[weather_agent, math_agent, general_agent],
)


# Simple single agent for basic testing
simple_agent = Agent(
    name="SimpleAgent",
    instructions="""You are a helpful assistant with weather and math capabilities.
    Use your tools to help users with weather queries and calculations.""",
    model="gpt-4o-mini",
    tools=[get_weather, calculate],
)
