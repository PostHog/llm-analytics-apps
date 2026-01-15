"""
OpenAI Agents SDK - Multi-Agent Example with PostHog Tracing

This example demonstrates:
- Multiple specialized agents with different capabilities
- Agent handoffs based on user intent
- Tool usage (weather, math)
- Input/Output guardrails for content filtering
- Custom spans for tracking custom operations
- PostHog instrumentation for LLM analytics

The triage agent routes requests to specialized agents:
- Weather Agent: Handles weather-related queries with a weather tool
- Math Agent: Handles calculations and math problems
- General Agent: Handles general questions and conversation
- Guarded Agent: Demonstrates input/output guardrails
"""

from typing import Annotated
from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool, input_guardrail, output_guardrail, GuardrailFunctionOutput, RunContextWrapper, TResponseInputItem, trace
from agents.tracing import custom_span


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


# ============================================================================
# Guardrails - demonstrate input/output content filtering
# ============================================================================

# Blocked words for content filtering demonstration
BLOCKED_INPUT_WORDS = ["hack", "exploit", "bypass", "illegal"]
BLOCKED_OUTPUT_WORDS = ["confidential", "secret", "classified"]


@input_guardrail
async def content_filter_guardrail(
    ctx: RunContextWrapper[None], agent: Agent, input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    """
    Input guardrail that filters potentially harmful content.
    This demonstrates how guardrails trigger $ai_error_type: input_guardrail_triggered
    """
    # Convert input to string for checking
    if isinstance(input, list):
        input_text = " ".join(
            str(item.get("content", "")) if isinstance(item, dict) else str(item)
            for item in input
        ).lower()
    else:
        input_text = input.lower()

    # Check for blocked words
    for word in BLOCKED_INPUT_WORDS:
        if word in input_text:
            return GuardrailFunctionOutput(
                output_info={"blocked_word": word, "reason": "content_policy"},
                tripwire_triggered=True,
            )

    return GuardrailFunctionOutput(
        output_info={"status": "passed"},
        tripwire_triggered=False,
    )


@output_guardrail
async def sensitive_data_guardrail(
    ctx: RunContextWrapper[None], agent: Agent, output: str
) -> GuardrailFunctionOutput:
    """
    Output guardrail that prevents leaking sensitive information.
    This demonstrates how guardrails trigger $ai_error_type: output_guardrail_triggered
    """
    output_lower = output.lower()

    # Check for sensitive words in output
    for word in BLOCKED_OUTPUT_WORDS:
        if word in output_lower:
            return GuardrailFunctionOutput(
                output_info={"blocked_word": word, "reason": "data_protection"},
                tripwire_triggered=True,
            )

    return GuardrailFunctionOutput(
        output_info={"status": "passed"},
        tripwire_triggered=False,
    )


# Guarded Agent - demonstrates guardrails
guarded_agent = Agent(
    name="GuardedAgent",
    instructions="""You are a helpful assistant with content filtering.
    You help users while respecting content policies and data protection rules.
    Be helpful and informative, but avoid discussing anything harmful or leaking sensitive data.""",
    model="gpt-4o-mini",
    input_guardrails=[content_filter_guardrail],
    output_guardrails=[sensitive_data_guardrail],
)


# ============================================================================
# Custom Span Examples - demonstrate custom operation tracking
# ============================================================================

async def process_with_custom_spans(user_input: str, group_id: str = None) -> dict:
    """
    Example function demonstrating custom spans for tracking custom operations.
    This creates nested spans that show up in PostHog as $ai_span events with type=custom.

    Must be wrapped in a trace context to be tracked properly.
    """
    result = {}

    # Wrap everything in a trace context so custom spans are recorded
    with trace("custom_processing_workflow", group_id=group_id):

        # Outer custom span for the entire processing pipeline
        with custom_span(name="data_processing_pipeline"):

            # Custom span for input preprocessing
            with custom_span(name="preprocess_input", data={"input_length": len(user_input)}):
                # Simulate preprocessing
                processed_input = user_input.strip().lower()
                result["preprocessed"] = processed_input

            # Custom span for validation
            with custom_span(name="validate_input", data={"input": processed_input}):
                # Simulate validation
                is_valid = len(processed_input) > 0 and len(processed_input) < 1000
                result["valid"] = is_valid

            # Custom span for any custom business logic
            with custom_span(name="business_logic", data={"validated": is_valid}):
                # Simulate some business logic
                if is_valid:
                    result["processed"] = True
                    result["word_count"] = len(processed_input.split())
                else:
                    result["processed"] = False
                    result["error"] = "Invalid input"

    return result


# ============================================================================
# Error demonstration agent - for testing error tracking
# ============================================================================

@function_tool
def unreliable_tool(
    action: Annotated[str, "The action to perform: 'succeed', 'fail', or 'error'"]
) -> str:
    """A tool that can succeed, fail gracefully, or raise an error for testing."""
    print(f"[tool] unreliable_tool called with action: {action}")
    if action == "succeed":
        return "Operation completed successfully!"
    elif action == "fail":
        return "Error: Operation failed due to invalid state"
    elif action == "error":
        raise ValueError("Simulated tool error for testing error tracking")
    else:
        return f"Unknown action: {action}"


error_demo_agent = Agent(
    name="ErrorDemoAgent",
    instructions="""You are a testing assistant that demonstrates error handling.
    Use the unreliable_tool to test different outcomes:
    - 'succeed': Shows successful tool execution
    - 'fail': Shows graceful failure handling
    - 'error': Shows exception handling and error tracking

    When asked to test errors, use the appropriate action.""",
    model="gpt-4o-mini",
    tools=[unreliable_tool],
)
