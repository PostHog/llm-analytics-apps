#!/usr/bin/env python3
"""
Demo Data Generator for PostHog LLM Analytics

Generates realistic chat data by using a LangChain-powered "User Simulator" agent
that has actual conversations with various LLM providers.

The User Simulator acts as a curious human user, picking random topics and having
natural multi-turn conversations with the target providers.

This script is self-contained and uses the PostHog AI SDKs directly,
without depending on the providers/ directory.
"""

import argparse
import json
import logging
import math
import os
import random
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from posthog import Posthog


# ---------------------------------------------------------------------------
# Constants (matching providers/constants.py)
# ---------------------------------------------------------------------------

OPENAI_CHAT_MODEL = "gpt-4o-mini"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_TOKENS = 4000
DEFAULT_POSTHOG_DISTINCT_ID = "user-hog"
SYSTEM_PROMPT_FRIENDLY = (
    "You are a friendly AI that just makes conversation. "
    "You have access to a weather tool if the user asks about weather."
)
SYSTEM_PROMPT_ASSISTANT = (
    "You are a helpful assistant. "
    "You have access to tools that you can use to help answer questions."
)


# ---------------------------------------------------------------------------
# Tool helpers
# ---------------------------------------------------------------------------

def get_weather(latitude: float, longitude: float, location_name: str = None) -> str:
    """Get real weather data from Open-Meteo API using coordinates."""
    try:
        from urllib.parse import urlencode
        params = urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urlopen(url, timeout=10) as resp:
            weather_data = json.loads(resp.read().decode())

        current = weather_data.get("current", {})
        temp_celsius = current.get("temperature_2m", 0)
        temp_fahrenheit = int(temp_celsius * 9 / 5 + 32)
        feels_like_celsius = current.get("apparent_temperature", temp_celsius)
        humidity = current.get("relative_humidity_2m", 0)
        wind_speed = current.get("wind_speed_10m", 0)
        precipitation = current.get("precipitation", 0)

        weather_descriptions = {
            0: "clear skies", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
            45: "foggy", 48: "depositing rime fog",
            51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
            61: "slight rain", 63: "moderate rain", 65: "heavy rain",
            71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
            80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
            85: "slight snow showers", 86: "heavy snow showers",
            95: "thunderstorm", 96: "thunderstorm with slight hail",
            99: "thunderstorm with heavy hail",
        }
        weather_desc = weather_descriptions.get(current.get("weather_code", 0), "unknown conditions")
        location_str = location_name if location_name else f"coordinates ({latitude}, {longitude})"

        result = (
            f"The current weather in {location_str} is {temp_celsius}\u00b0C ({temp_fahrenheit}\u00b0F) "
            f"with {weather_desc}. Feels like {feels_like_celsius}\u00b0C. "
            f"Humidity: {humidity}%, Wind: {wind_speed} km/h"
        )
        if precipitation > 0:
            result += f", Precipitation: {precipitation} mm"
        return result
    except Exception:
        location_str = location_name if location_name else f"coordinates ({latitude}, {longitude})"
        return f"Weather API unavailable for {location_str}. Using mock data: experiencing typical weather conditions."


def tell_joke(setup: str, punchline: str) -> str:
    return f"{setup}\n\n{punchline}"


def roll_dice(num_dice: int = 1, sides: int = 6) -> str:
    num_dice = max(1, min(num_dice, 20))
    sides = max(2, min(sides, 100))
    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    total = sum(rolls)
    if num_dice == 1:
        return f"Rolled a d{sides}: {rolls[0]}"
    return f"Rolled {num_dice}d{sides}: {rolls} (total: {total})"


def check_time(timezone_name: str = "UTC") -> str:
    try:
        tz = ZoneInfo(timezone_name)
        now = datetime.now(tz)
        return f"The current time in {timezone_name} is {now.strftime('%I:%M %p on %A, %B %d, %Y')}"
    except Exception:
        now = datetime.now(timezone.utc)
        return f"Unknown timezone '{timezone_name}'. UTC time is {now.strftime('%I:%M %p on %A, %B %d, %Y')}"


def calculate(expression: str) -> str:
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return f"Invalid expression: '{expression}'. Only basic arithmetic is supported."
    try:
        result = eval(expression, {"__builtins__": {}}, {"math": math})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    conversions = {
        ("km", "miles"): lambda v: v * 0.621371,
        ("miles", "km"): lambda v: v * 1.60934,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v * 0.453592,
        ("celsius", "fahrenheit"): lambda v: v * 9 / 5 + 32,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5 / 9,
        ("meters", "feet"): lambda v: v * 3.28084,
        ("feet", "meters"): lambda v: v * 0.3048,
        ("liters", "gallons"): lambda v: v * 0.264172,
        ("gallons", "liters"): lambda v: v * 3.78541,
    }
    key = (from_unit.lower(), to_unit.lower())
    if key in conversions:
        result = conversions[key](value)
        return f"{value} {from_unit} = {result:.2f} {to_unit}"
    return (
        f"Cannot convert from {from_unit} to {to_unit}. "
        f"Supported pairs: {', '.join(f'{a}->{b}' for a, b in conversions.keys())}"
    )


def generate_inspirational_quote(topic: str = "general") -> str:
    quotes = {
        "general": [
            "The only way to do great work is to love what you do. - Steve Jobs",
            "In the middle of difficulty lies opportunity. - Albert Einstein",
            "What you get by achieving your goals is not as important as what you become by achieving your goals. - Zig Ziglar",
        ],
        "perseverance": [
            "It does not matter how slowly you go as long as you do not stop. - Confucius",
            "Fall seven times, stand up eight. - Japanese Proverb",
            "Perseverance is not a long race; it is many short races one after the other. - Walter Elliot",
        ],
        "creativity": [
            "Creativity is intelligence having fun. - Albert Einstein",
            "The chief enemy of creativity is good sense. - Pablo Picasso",
            "Creativity takes courage. - Henri Matisse",
        ],
        "success": [
            "Success is not final, failure is not fatal: it is the courage to continue that counts. - Winston Churchill",
            "The secret of success is to do the common thing uncommonly well. - John D. Rockefeller Jr.",
            "Success usually comes to those who are too busy to be looking for it. - Henry David Thoreau",
        ],
        "teamwork": [
            "Alone we can do so little; together we can do so much. - Helen Keller",
            "Coming together is a beginning, staying together is progress, and working together is success. - Henry Ford",
            "If everyone is moving forward together, then success takes care of itself. - Henry Ford",
        ],
    }
    topic_quotes = quotes.get(topic.lower(), quotes["general"])
    return random.choice(topic_quotes)


def execute_tool(tool_name: str, tool_input: dict) -> Optional[str]:
    """Execute a tool by name and return the result."""
    if tool_name in ("get_weather", "get_current_weather"):
        return get_weather(
            tool_input.get("latitude", 0.0),
            tool_input.get("longitude", 0.0),
            tool_input.get("location_name"),
        )
    elif tool_name == "tell_joke":
        return tell_joke(tool_input.get("setup", ""), tool_input.get("punchline", ""))
    elif tool_name == "roll_dice":
        return roll_dice(tool_input.get("num_dice", 1), tool_input.get("sides", 6))
    elif tool_name == "check_time":
        return check_time(tool_input.get("timezone", "UTC"))
    elif tool_name == "calculate":
        return calculate(tool_input.get("expression", "0"))
    elif tool_name == "convert_units":
        return convert_units(
            tool_input.get("value", 0),
            tool_input.get("from_unit", ""),
            tool_input.get("to_unit", ""),
        )
    elif tool_name == "generate_inspirational_quote":
        return generate_inspirational_quote(tool_input.get("topic", "general"))
    return None


def format_tool_result(tool_name: str, result: str) -> str:
    icons = {
        "get_weather": "\U0001f324\ufe0f  Weather",
        "get_current_weather": "\U0001f324\ufe0f  Weather",
        "tell_joke": "\U0001f602 Joke",
        "roll_dice": "\U0001f3b2 Dice",
        "check_time": "\U0001f550 Time",
        "calculate": "\U0001f9ee Calculate",
        "convert_units": "\U0001f4cf Convert",
        "generate_inspirational_quote": "\U0001f4a1 Quote",
    }
    label = icons.get(tool_name, tool_name)
    return f"{label}: {result}"


# ---------------------------------------------------------------------------
# Tool definitions in each provider format
# ---------------------------------------------------------------------------

WEATHER_TOOL_ANTHROPIC = {
    "name": "get_weather",
    "description": "Get the current weather for a specific location using geographical coordinates",
    "input_schema": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "description": "The latitude of the location"},
            "longitude": {"type": "number", "description": "The longitude of the location"},
            "location_name": {"type": "string", "description": "A human-readable name for the location"},
        },
        "required": ["latitude", "longitude", "location_name"],
    },
}

JOKE_TOOL_ANTHROPIC = {
    "name": "tell_joke",
    "description": "Tell a joke with a question-style setup and an answer punchline",
    "input_schema": {
        "type": "object",
        "properties": {
            "setup": {"type": "string", "description": "The setup or question part of the joke"},
            "punchline": {"type": "string", "description": "The punchline or answer to the joke"},
        },
        "required": ["setup", "punchline"],
    },
}

ANTHROPIC_TOOLS = [WEATHER_TOOL_ANTHROPIC, JOKE_TOOL_ANTHROPIC]

WEATHER_TOOL_OPENAI_RESPONSES = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the current weather for a specific location using geographical coordinates",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "description": "The latitude of the location"},
            "longitude": {"type": "number", "description": "The longitude of the location"},
            "location_name": {"type": "string", "description": "A human-readable name for the location"},
        },
        "required": ["latitude", "longitude", "location_name"],
    },
}

JOKE_TOOL_OPENAI_RESPONSES = {
    "type": "function",
    "name": "tell_joke",
    "description": "Tell a joke with a question-style setup and an answer punchline",
    "parameters": {
        "type": "object",
        "properties": {
            "setup": {"type": "string", "description": "The setup or question part of the joke"},
            "punchline": {"type": "string", "description": "The punchline or answer to the joke"},
        },
        "required": ["setup", "punchline"],
    },
}

OPENAI_RESPONSES_TOOLS = [WEATHER_TOOL_OPENAI_RESPONSES, JOKE_TOOL_OPENAI_RESPONSES]

WEATHER_TOOL_OPENAI_CHAT = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a specific location using geographical coordinates",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "The latitude of the location"},
                "longitude": {"type": "number", "description": "The longitude of the location"},
                "location_name": {"type": "string", "description": "A human-readable name for the location"},
            },
            "required": ["latitude", "longitude", "location_name"],
        },
    },
}

JOKE_TOOL_OPENAI_CHAT = {
    "type": "function",
    "function": {
        "name": "tell_joke",
        "description": "Tell a joke with a question-style setup and an answer punchline",
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "The setup or question part of the joke"},
                "punchline": {"type": "string", "description": "The punchline or answer to the joke"},
            },
            "required": ["setup", "punchline"],
        },
    },
}

OPENAI_CHAT_TOOLS = [WEATHER_TOOL_OPENAI_CHAT, JOKE_TOOL_OPENAI_CHAT]

GEMINI_TOOL_DECLARATIONS = [
    {
        "name": "get_current_weather",
        "description": "Gets the current weather for a given location using geographical coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "The latitude of the location"},
                "longitude": {"type": "number", "description": "The longitude of the location"},
                "location_name": {"type": "string", "description": "A human-readable name for the location"},
            },
            "required": ["latitude", "longitude", "location_name"],
        },
    },
    {
        "name": "tell_joke",
        "description": "Tell a joke with a question-style setup and an answer punchline",
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "The setup of the joke"},
                "punchline": {"type": "string", "description": "The punchline or answer to the joke"},
            },
            "required": ["setup", "punchline"],
        },
    },
]


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------

class Provider:
    """
    Wraps an LLM SDK client with a uniform interface for the demo data generator.

    Each provider instance tracks its own conversation history and exposes
    ``chat()`` for non-streaming calls and ``chat_stream()`` (optional) for
    streaming calls.
    """

    def __init__(self, name: str):
        self._name = name
        self.messages = []

    def get_name(self) -> str:
        return self._name

    def reset_conversation(self):
        self.messages = []

    def chat(self, message: str) -> str:
        raise NotImplementedError

    # Streaming providers override this; the presence of this method is checked
    # by ``get_response_from_provider``.
    # def chat_stream(self, message: str) -> Generator[str, None, None]: ...


# ---------------------------------------------------------------------------
# Provider factory functions
# ---------------------------------------------------------------------------

def _make_anthropic(posthog_client: Posthog) -> Provider:
    from posthog.ai.anthropic import Anthropic

    client = Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("Anthropic")

    def chat(message: str) -> str:
        provider.messages.append({"role": "user", "content": message})
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            tools=ANTHROPIC_TOOLS,
            messages=provider.messages,
        )
        assistant_content = []
        display_parts = []
        tool_results = []

        for block in (response.content or []):
            if block.type == "tool_use":
                assistant_content.append(block)
                result = execute_tool(block.name, block.input)
                if result is not None:
                    text = format_tool_result(block.name, result)
                    tool_results.append(text)
                    display_parts.append(text)
            elif block.type == "text":
                assistant_content.append(block)
                display_parts.append(block.text)

        provider.messages.append({"role": "assistant", "content": assistant_content})

        if tool_results:
            for block in response.content:
                if block.type == "tool_use":
                    provider.messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": block.id, "content": tool_results[0]}],
                    })
                    break

        return "\n\n".join(display_parts) if display_parts else "No response received"

    provider.chat = chat
    return provider


def _make_anthropic_streaming(posthog_client: Posthog) -> Provider:
    from posthog.ai.anthropic import Anthropic

    client = Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("Anthropic Streaming")

    def chat_stream(message: str) -> Generator[str, None, None]:
        provider.messages.append({"role": "user", "content": message})
        stream = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            tools=ANTHROPIC_TOOLS,
            messages=provider.messages,
            stream=True,
        )

        accumulated = ""
        assistant_content = []
        tools_used = []
        current_text_block = None

        for event in stream:
            if not hasattr(event, "type"):
                continue

            if event.type == "content_block_start" and hasattr(event, "content_block"):
                cb = event.content_block
                if hasattr(cb, "type"):
                    if cb.type == "text":
                        current_text_block = {"type": "text", "text": ""}
                        assistant_content.append(current_text_block)
                    elif cb.type == "tool_use":
                        tools_used.append({
                            "id": getattr(cb, "id", None),
                            "name": getattr(cb, "name", None),
                            "input": {},
                        })
                        assistant_content.append({
                            "type": "tool_use",
                            "id": getattr(cb, "id", None),
                            "name": getattr(cb, "name", None),
                            "input": {},
                        })
                        current_text_block = None

            elif event.type == "content_block_delta" and hasattr(event, "delta"):
                if hasattr(event.delta, "text"):
                    text = event.delta.text
                    accumulated += text
                    if current_text_block is not None:
                        current_text_block["text"] += text
                    yield text
                elif hasattr(event.delta, "partial_json") and tools_used:
                    last = tools_used[-1]
                    last.setdefault("input_string", "")
                    last["input_string"] += event.delta.partial_json or ""

            elif event.type == "content_block_stop":
                current_text_block = None
                if tools_used and tools_used[-1].get("input_string"):
                    last = tools_used[-1]
                    try:
                        last["input"] = json.loads(last.pop("input_string"))
                        for c in assistant_content:
                            if c.get("type") == "tool_use" and c.get("id") == last["id"]:
                                c["input"] = last["input"]
                                break
                        result = execute_tool(last["name"], last["input"])
                        if result is not None:
                            yield "\n\n" + format_tool_result(last["name"], result)
                    except (json.JSONDecodeError, AttributeError):
                        pass

        provider.messages.append({
            "role": "assistant",
            "content": assistant_content if assistant_content else [{"type": "text", "text": accumulated or ""}],
        })

        for tool in tools_used:
            if tool.get("input"):
                result = execute_tool(tool["name"], tool["input"])
                if result is not None:
                    provider.messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool["id"], "content": result}],
                    })

    def chat(message: str) -> str:
        return "".join(chat_stream(message)) or "No response received"

    provider.chat = chat
    provider.chat_stream = chat_stream
    return provider


def _make_openai(posthog_client: Posthog) -> Provider:
    from posthog.ai.openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("OpenAI Responses")

    def chat(message: str) -> str:
        provider.messages.append({"role": "user", "content": message})
        response = client.responses.create(
            model=OPENAI_CHAT_MODEL,
            max_output_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            input=provider.messages,
            instructions=SYSTEM_PROMPT_FRIENDLY,
            tools=OPENAI_RESPONSES_TOOLS,
        )

        display_parts = []
        assistant_items = []

        for item in (getattr(response, "output", None) or []):
            if hasattr(item, "content") and item.content:
                for ci in item.content:
                    if hasattr(ci, "text") and ci.text:
                        display_parts.append(ci.text)
                        assistant_items.append({"type": "output_text", "text": ci.text})
            if hasattr(item, "name"):
                args = {}
                try:
                    args = json.loads(getattr(item, "arguments", "{}"))
                except json.JSONDecodeError:
                    pass
                result = execute_tool(item.name, args)
                if result is not None:
                    display_parts.append(format_tool_result(item.name, result))
                    assistant_items.append({"type": "output_text", "text": result})

        if assistant_items:
            provider.messages.append({"role": "assistant", "content": assistant_items})

        return "\n\n".join(display_parts) if display_parts else "No response received"

    provider.chat = chat
    return provider


def _make_openai_streaming(posthog_client: Posthog) -> Provider:
    from posthog.ai.openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("OpenAI Responses Streaming")

    def chat_stream(message: str) -> Generator[str, None, None]:
        provider.messages.append({"role": "user", "content": message})
        stream = client.responses.create(
            model=OPENAI_CHAT_MODEL,
            max_output_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            input=provider.messages,
            instructions=SYSTEM_PROMPT_FRIENDLY,
            tools=OPENAI_RESPONSES_TOOLS,
            stream=True,
        )

        accumulated = ""
        tool_calls = []
        assistant_items = []

        for chunk in stream:
            if not hasattr(chunk, "type"):
                continue
            if chunk.type == "response.output_text.delta" and hasattr(chunk, "delta") and chunk.delta:
                accumulated += chunk.delta
                yield chunk.delta
            elif chunk.type == "response.output_item.added":
                if hasattr(chunk, "item") and getattr(chunk.item, "type", None) == "function_call":
                    idx = getattr(chunk, "output_index", len(tool_calls))
                    if idx >= len(tool_calls):
                        tool_calls.append({
                            "name": getattr(chunk.item, "name", "get_weather"),
                            "call_id": getattr(chunk.item, "call_id", ""),
                            "arguments": "",
                        })
            elif chunk.type == "response.function_call_arguments.done":
                idx = getattr(chunk, "output_index", 0)
                if idx < len(tool_calls):
                    tc = tool_calls[idx]
                    tc["arguments"] = getattr(chunk, "arguments", "{}")
                    args = {}
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        pass
                    result = execute_tool(tc["name"], args)
                    if result is not None:
                        yield "\n\n" + format_tool_result(tc["name"], result)

        if accumulated:
            assistant_items.append({"type": "output_text", "text": accumulated})
        for tc in tool_calls:
            if tc.get("arguments"):
                args = {}
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    pass
                result = execute_tool(tc["name"], args)
                if result is not None:
                    assistant_items.append({"type": "output_text", "text": result})

        if assistant_items:
            provider.messages.append({"role": "assistant", "content": assistant_items})

    def chat(message: str) -> str:
        return "".join(chat_stream(message)) or "No response received"

    provider.chat = chat
    provider.chat_stream = chat_stream
    return provider


def _make_openai_chat(posthog_client: Posthog) -> Provider:
    from posthog.ai.openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("OpenAI Chat Completions")
    provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    def reset():
        provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    provider.reset_conversation = reset

    def chat(message: str) -> str:
        provider.messages.append({"role": "user", "content": message})
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            max_completion_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            messages=provider.messages,
            tools=OPENAI_CHAT_TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        msg = choice.message
        display_parts = []
        assistant_content = msg.content or ""
        if assistant_content:
            display_parts.append(assistant_content)

        if msg.tool_calls:
            provider.messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                args = {}
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    pass
                result = execute_tool(tc.function.name, args)
                if result is not None:
                    display_parts.append(format_tool_result(tc.function.name, result))
                    provider.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        else:
            provider.messages.append({"role": "assistant", "content": assistant_content})

        return "\n\n".join(display_parts) if display_parts else "No response received"

    provider.chat = chat
    return provider


def _make_openai_chat_streaming(posthog_client: Posthog) -> Provider:
    from posthog.ai.openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        posthog_client=posthog_client,
    )

    provider = Provider("OpenAI Chat Completions Streaming")
    provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    def reset():
        provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    provider.reset_conversation = reset

    def chat_stream(message: str) -> Generator[str, None, None]:
        provider.messages.append({"role": "user", "content": message})
        stream = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            max_completion_tokens=DEFAULT_MAX_TOKENS,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            messages=provider.messages,
            tools=OPENAI_CHAT_TOOLS,
            tool_choice="auto",
            stream=True,
            stream_options={"include_usage": True},
        )

        accumulated = ""
        tool_calls_by_index = {}
        tool_calls = []

        for chunk in stream:
            if not (hasattr(chunk, "choices") and chunk.choices):
                continue
            choice = chunk.choices[0]
            if hasattr(choice, "delta"):
                if hasattr(choice.delta, "content") and choice.delta.content:
                    accumulated += choice.delta.content
                    yield choice.delta.content

                if hasattr(choice.delta, "tool_calls") and choice.delta.tool_calls:
                    for tcd in choice.delta.tool_calls:
                        idx = tcd.index
                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                        tc = tool_calls_by_index[idx]
                        if hasattr(tcd, "id") and tcd.id:
                            tc["id"] = tcd.id
                        if hasattr(tcd, "function"):
                            if hasattr(tcd.function, "name") and tcd.function.name:
                                tc["function"]["name"] = tcd.function.name
                            if hasattr(tcd.function, "arguments") and tcd.function.arguments:
                                tc["function"]["arguments"] += tcd.function.arguments

            if hasattr(choice, "finish_reason") and choice.finish_reason == "tool_calls":
                completed = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())]
                for tc in completed:
                    tool_calls.append(tc)
                    args = {}
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        pass
                    result = execute_tool(tc["function"]["name"], args)
                    if result is not None:
                        yield "\n\n" + format_tool_result(tc["function"]["name"], result)

        assistant_msg = {"role": "assistant"}
        if accumulated:
            assistant_msg["content"] = accumulated
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        provider.messages.append(assistant_msg)

        for tc in tool_calls:
            args = {}
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                pass
            result = execute_tool(tc["function"]["name"], args)
            if result is not None:
                provider.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    def chat(message: str) -> str:
        return "".join(chat_stream(message)) or "No response received"

    provider.chat = chat
    provider.chat_stream = chat_stream
    return provider


def _make_gemini(posthog_client: Posthog) -> Provider:
    from posthog.ai.gemini import Client
    from google.genai import types

    client = Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        posthog_client=posthog_client,
    )

    tools_obj = types.Tool(function_declarations=GEMINI_TOOL_DECLARATIONS)
    config = types.GenerateContentConfig(tools=[tools_obj])

    provider = Provider("Google Gemini")
    provider._history = []

    def reset():
        provider.messages = []
        provider._history = []

    provider.reset_conversation = reset

    def chat(message: str) -> str:
        provider._history.append({"role": "user", "parts": [{"text": message}]})
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            contents=provider._history,
            config=config,
        )

        display_parts = []
        model_parts = []

        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            model_parts.append({"function_call": fc})
                            result = execute_tool(fc.name, dict(fc.args))
                            if result is not None:
                                display_parts.append(format_tool_result(fc.name, result))
                        elif hasattr(part, "text"):
                            model_parts.append({"text": part.text})
                            display_parts.append(part.text)

        if model_parts:
            provider._history.append({"role": "model", "parts": model_parts})

        return "\n\n".join(display_parts) if display_parts else (
            response.text if hasattr(response, "text") else "No response received"
        )

    provider.chat = chat
    return provider


def _make_gemini_streaming(posthog_client: Posthog) -> Provider:
    from posthog.ai.gemini import Client
    from google.genai import types

    client = Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        posthog_client=posthog_client,
    )

    tools_obj = types.Tool(function_declarations=GEMINI_TOOL_DECLARATIONS)
    config = types.GenerateContentConfig(tools=[tools_obj])

    provider = Provider("Google Gemini Streaming")
    provider._history = []

    def reset():
        provider.messages = []
        provider._history = []

    provider.reset_conversation = reset

    def chat_stream(message: str) -> Generator[str, None, None]:
        provider._history.append({"role": "user", "parts": [{"text": message}]})
        stream = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            posthog_distinct_id=os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            contents=provider._history,
            config=config,
        )

        accumulated = ""
        model_parts = []
        tool_results = []

        for chunk in stream:
            if hasattr(chunk, "candidates") and chunk.candidates:
                for candidate in chunk.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                accumulated += part.text
                                yield part.text
                            elif hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                model_parts.append({"function_call": fc})
                                result = execute_tool(fc.name, dict(fc.args))
                                if result is not None:
                                    text = format_tool_result(fc.name, result)
                                    tool_results.append(text)
                                    yield "\n\n" + text

        if accumulated:
            model_parts.append({"text": accumulated})
        if model_parts:
            provider._history.append({"role": "model", "parts": model_parts})
        for tr in tool_results:
            provider._history.append({"role": "model", "parts": [{"text": f"Tool result: {tr}"}]})

    def chat(message: str) -> str:
        return "".join(chat_stream(message)) or "No response received"

    provider.chat = chat
    provider.chat_stream = chat_stream
    return provider


def _make_langchain(posthog_client: Posthog) -> Provider:
    from posthog.ai.langchain import CallbackHandler
    from langchain_core.tools import tool
    from langchain_core.messages import ToolMessage

    callback_handler = CallbackHandler(client=posthog_client)
    openai_api_key = os.getenv("OPENAI_API_KEY")

    @tool
    def get_weather_tool(latitude: float, longitude: float, location_name: str) -> str:
        """Get the current weather for a specific location using geographical coordinates.

        Args:
            latitude: The latitude of the location
            longitude: The longitude of the location
            location_name: A human-readable name for the location
        """
        return get_weather(latitude, longitude, location_name)

    @tool
    def tell_joke_tool(setup: str, punchline: str) -> str:
        """Tell a joke with a question-style setup and an answer punchline.

        Args:
            setup: The setup or question part of the joke
            punchline: The punchline or answer part of the joke
        """
        return tell_joke(setup, punchline)

    langchain_tools = [get_weather_tool, tell_joke_tool]
    tool_map = {t.name: t for t in langchain_tools}

    provider = Provider("LangChain (OpenAI)")
    provider._lc_messages = [SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)]

    def reset():
        provider.messages = []
        provider._lc_messages = [SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)]

    provider.reset_conversation = reset

    def chat(message: str) -> str:
        provider._lc_messages.append(HumanMessage(content=message))

        model = ChatOpenAI(openai_api_key=openai_api_key, temperature=0, model_name=OPENAI_CHAT_MODEL)
        model_with_tools = model.bind_tools(langchain_tools)
        response = model_with_tools.invoke(
            provider._lc_messages,
            config={"callbacks": [callback_handler]},
        )

        display_parts = []
        if response.content:
            display_parts.append(response.content)

        tool_messages = []
        if response.tool_calls:
            for tc in response.tool_calls:
                name = tc["name"]
                if name in tool_map:
                    result = tool_map[name].invoke(tc["args"])
                    display_parts.append(format_tool_result(name, result))
                    tool_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        provider._lc_messages.append(response)
        provider._lc_messages.extend(tool_messages)

        return "\n\n".join(display_parts) if display_parts else "No response received"

    provider.chat = chat
    return provider


def _make_litellm(posthog_client: Posthog) -> Provider:
    import litellm

    os.environ["POSTHOG_API_KEY"] = os.getenv("POSTHOG_API_KEY", "")
    os.environ["POSTHOG_API_URL"] = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    try:
        litellm.success_callback = ["posthog"]
        litellm.failure_callback = ["posthog"]
    except Exception:
        pass

    existing_props = posthog_client.super_properties or {}
    ai_session_id = existing_props.get("$ai_session_id")

    provider = Provider("LiteLLM (Sync)")
    provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    def reset():
        provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    provider.reset_conversation = reset

    def _metadata():
        m = {
            "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
        }
        if ai_session_id:
            m["$ai_session_id"] = ai_session_id
        return m

    def chat(message: str) -> str:
        provider.messages.append({"role": "user", "content": message})
        try:
            response = litellm.completion(
                model=OPENAI_CHAT_MODEL,
                messages=provider.messages,
                tools=OPENAI_CHAT_TOOLS,
                tool_choice="auto",
                max_tokens=DEFAULT_MAX_TOKENS,
                metadata=_metadata(),
            )

            assistant_message = response.choices[0].message
            if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
                provider.messages.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [tc.dict() for tc in assistant_message.tool_calls],
                })
                display_parts = []
                if assistant_message.content:
                    display_parts.append(assistant_message.content)

                for tc in assistant_message.tool_calls:
                    args = {}
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        pass
                    result = execute_tool(tc.function.name, args)
                    if result is not None:
                        display_parts.append(format_tool_result(tc.function.name, result))
                        provider.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                # Get final response after tool execution
                try:
                    final = litellm.completion(
                        model=OPENAI_CHAT_MODEL,
                        messages=provider.messages,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        metadata=_metadata(),
                    )
                    final_content = final.choices[0].message.content
                    if final_content:
                        display_parts.append(final_content)
                        provider.messages.append({"role": "assistant", "content": final_content})
                except Exception as e:
                    display_parts.append(f"Error getting final response: {e}")

                return "\n\n".join(display_parts)
            else:
                content = assistant_message.content or "No response received"
                provider.messages.append({"role": "assistant", "content": content})
                return content
        except Exception as e:
            return f"Error: {e}"

    provider.chat = chat
    return provider


def _make_litellm_streaming(posthog_client: Posthog) -> Provider:
    import asyncio
    import litellm

    os.environ["POSTHOG_API_KEY"] = os.getenv("POSTHOG_API_KEY", "")
    os.environ["POSTHOG_API_URL"] = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    try:
        litellm.success_callback = ["posthog"]
        litellm.failure_callback = ["posthog"]
    except Exception:
        pass

    existing_props = posthog_client.super_properties or {}
    ai_session_id = existing_props.get("$ai_session_id")

    provider = Provider("LiteLLM (Async)")
    provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    def reset():
        provider.messages = [{"role": "system", "content": SYSTEM_PROMPT_FRIENDLY}]

    provider.reset_conversation = reset

    def _metadata():
        m = {
            "distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            "user_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
        }
        if ai_session_id:
            m["$ai_session_id"] = ai_session_id
        return m

    def chat_stream(message: str) -> Generator[str, None, None]:
        provider.messages.append({"role": "user", "content": message})

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run():
            response = await litellm.acompletion(
                model=OPENAI_CHAT_MODEL,
                messages=provider.messages,
                tools=OPENAI_CHAT_TOOLS,
                tool_choice="auto",
                max_tokens=DEFAULT_MAX_TOKENS,
                metadata=_metadata(),
                stream=True,
            )

            full_content = ""
            tool_calls_data = []
            chunks_out = []

            async for chunk in response:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    full_content += delta.content
                    chunks_out.append(delta.content)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index >= len(tool_calls_data):
                            tool_calls_data.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": ""},
                            })
                        if tc.function.arguments:
                            tool_calls_data[tc.index]["function"]["arguments"] += tc.function.arguments

            return full_content, tool_calls_data, chunks_out

        try:
            full_content, tool_calls_data, chunks_out = loop.run_until_complete(_run())
            for c in chunks_out:
                yield c

            if tool_calls_data:
                provider.messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls_data,
                })
                for tc in tool_calls_data:
                    args = {}
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        pass
                    result = execute_tool(tc["function"]["name"], args)
                    if result is not None:
                        text = format_tool_result(tc["function"]["name"], result)
                        yield "\n\n" + text
                        provider.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                # Get final response
                async def _final():
                    resp = await litellm.acompletion(
                        model=OPENAI_CHAT_MODEL,
                        messages=provider.messages,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        metadata=_metadata(),
                        stream=True,
                    )
                    final_content = ""
                    chunks = []
                    async for chunk in resp:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            final_content += delta.content
                            chunks.append(delta.content)
                    return final_content, chunks

                final_content, final_chunks = loop.run_until_complete(_final())
                for c in final_chunks:
                    yield c
                if final_content:
                    provider.messages.append({"role": "assistant", "content": final_content})
            else:
                if full_content:
                    provider.messages.append({"role": "assistant", "content": full_content})
        except Exception as e:
            yield f"Error: {e}"
        finally:
            loop.close()

    def chat(message: str) -> str:
        return "".join(chat_stream(message)) or "No response received"

    provider.chat = chat
    provider.chat_stream = chat_stream
    return provider


# ---------------------------------------------------------------------------
# PROVIDERS dict and TOOL_CAPABLE_PROVIDERS
# ---------------------------------------------------------------------------

PROVIDERS = {
    "anthropic": ("Anthropic", _make_anthropic),
    "anthropic_streaming": ("Anthropic Streaming", _make_anthropic_streaming),
    "gemini": ("Google Gemini", _make_gemini),
    "gemini_streaming": ("Google Gemini Streaming", _make_gemini_streaming),
    "langchain": ("LangChain (OpenAI)", _make_langchain),
    "openai": ("OpenAI Responses", _make_openai),
    "openai_streaming": ("OpenAI Responses Streaming", _make_openai_streaming),
    "openai_chat": ("OpenAI Chat Completions", _make_openai_chat),
    "openai_chat_streaming": ("OpenAI Chat Completions Streaming", _make_openai_chat_streaming),
    "litellm": ("LiteLLM (Sync)", _make_litellm),
    "litellm_streaming": ("LiteLLM (Async)", _make_litellm_streaming),
}


# Topics the user simulator can choose from
TOPICS = [
    # Weather & Environment
    "weather in various cities around the world",
    "climate patterns and seasonal changes",
    "extreme weather events and how to prepare",

    # Programming & Tech
    "how to write code in Python",
    "helping debug a programming problem",
    "understanding how technology works",
    "learning about APIs and how to use them",
    "best practices for writing clean code",
    "how databases work and when to use them",
    "getting started with machine learning",
    "web development tips and frameworks",
    "mobile app development basics",
    "DevOps and deployment strategies",
    "cybersecurity basics and staying safe online",

    # Food & Cooking
    "how to cook a specific dish",
    "meal planning and nutrition advice",
    "baking tips and dessert recipes",
    "cooking techniques for beginners",
    "international cuisines and their specialties",
    "dietary restrictions and alternative ingredients",

    # Science & Education
    "explaining a scientific concept",
    "learning about history",
    "understanding economics and finance basics",
    "exploring philosophy and ethics",
    "learning about astronomy and space",
    "biology and how the human body works",
    "chemistry in everyday life",
    "physics concepts made simple",
    "environmental science and sustainability",

    # Entertainment & Culture
    "recommending books or movies",
    "asking for jokes or humor",
    "discussing music and artists",
    "video games and gaming culture",
    "TV shows worth watching",
    "podcasts and audiobook recommendations",
    "art and creative expression",

    # Travel & Lifestyle
    "discussing travel destinations",
    "planning a vacation itinerary",
    "budget travel tips and tricks",
    "local attractions and hidden gems",
    "cultural etiquette when traveling abroad",

    # Productivity & Career
    "getting advice on productivity",
    "career advice and job searching",
    "learning a new skill",
    "time management strategies",
    "work-life balance tips",
    "negotiation and communication skills",
    "leadership and team management",
    "starting a business or side project",

    # Health & Wellness
    "asking about health and fitness",
    "mental health and stress management",
    "sleep hygiene and better rest",
    "meditation and mindfulness practices",
    "workout routines for different goals",

    # Writing & Communication
    "getting help with writing",
    "improving grammar and style",
    "public speaking tips",
    "email etiquette and professional communication",
    "storytelling techniques",
    "learning a new language",

    # Home & DIY
    "home improvement and DIY projects",
    "gardening tips and plant care",
    "organizing and decluttering",
    "interior design ideas",
    "basic car maintenance",

    # Finance & Legal
    "personal finance and budgeting",
    "investing basics for beginners",
    "understanding taxes and deductions",
    "retirement planning",
    "understanding contracts and agreements",

    # Relationships & Social
    "relationship advice and communication",
    "parenting tips and child development",
    "making new friends as an adult",
    "dealing with difficult people",
    "gift ideas for different occasions",

    # Miscellaneous
    "fun facts and trivia",
    "brain teasers and riddles",
    "explaining pop culture references",
    "pet care and animal behavior",
    "photography tips for beginners",
    "crafts and hobbies to try",

    # Tool-triggering scenarios (weather + jokes)
    "checking the weather in 5 different cities around the world",
    "comparing weather between Tokyo, London, and New York right now",
    "planning outdoor activities based on weather in multiple locations",
    "asking for the current weather and a joke to lighten the mood",
    "checking if it's good beach weather in several coastal cities",
    "wanting weather updates for a multi-city road trip",
    "asking about weather in their hometown and several vacation destinations",
    "telling a series of jokes on different topics",
    "wanting weather info for event planning in 3 different venues",
    "asking for jokes about programming, weather, and animals",

    # Frustrated & Negative scenarios
    "complaining about a product that keeps breaking",
    "dealing with a billing error that won't get resolved",
    "ranting about terrible customer service experiences",
    "frustrated with software that lost their work",
    "angry about misleading advertising",
    "upset about a cancelled flight and ruined travel plans",
    "complaining about noisy neighbors and landlord issues",
    "furious about a data breach affecting their account",
    "venting about a bad restaurant experience",
    "annoyed by repeated spam calls and scam attempts",
    "arguing that a previous AI answer was completely wrong",
    "demanding a refund for a defective product",
]

# User personas the simulator can adopt
USER_PERSONAS = [
    # Learning styles
    "a curious beginner who asks simple follow-up questions",
    "an enthusiastic learner who loves to dig deeper into topics",
    "a visual learner who asks for examples and analogies",
    "someone who learns by doing and wants step-by-step instructions",

    # Professional personas
    "an experienced developer looking for specific technical details",
    "a busy professional who wants quick, concise answers",
    "a manager trying to understand technical concepts at a high level",
    "a freelancer looking for practical tips to improve their work",
    "a startup founder exploring new ideas",
    "a teacher preparing lesson materials",

    # Student personas
    "a student working on a homework assignment",
    "a graduate student doing research",
    "someone preparing for a job interview",
    "a self-taught learner filling knowledge gaps",

    # Personality types
    "someone who's a bit skeptical and asks clarifying questions",
    "a friendly conversationalist who enjoys chatting",
    "an impatient person who wants direct answers without fluff",
    "a detail-oriented person who wants comprehensive information",
    "someone who likes to play devil's advocate",
    "a humorous person who appreciates wit and wordplay",

    # Situational personas
    "someone planning a trip and needing recommendations",
    "a parent trying to explain something to their child",
    "someone dealing with a problem and looking for solutions",
    "a hobbyist exploring a new interest",
    "someone comparing options before making a decision",
    "a person who just wants to have a casual conversation",

    # Communication styles
    "someone who asks lots of follow-up questions",
    "a person who likes to summarize and confirm understanding",
    "someone who shares personal anecdotes while chatting",
    "a minimalist communicator who uses short messages",
    "someone who thinks out loud and refines their questions",

    # Specific needs
    "someone with accessibility needs looking for inclusive solutions",
    "a non-native English speaker who appreciates clear explanations",
    "an expert fact-checking information they already know",
    "someone procrastinating who went down a rabbit hole",
    "a night owl having a late-night curiosity session",

    # Frustrated & Angry personas
    "an extremely frustrated customer who has been passed around to 5 different support agents",
    "someone who is furious and uses lots of caps and exclamation marks",
    "a sarcastic person who mocks every response they get",
    "someone who keeps saying the AI is useless and demands to speak to a human",
    "an angry user who threatens to switch to a competitor",
    "a passive-aggressive person who says 'fine I guess' to every suggestion",
    "someone having an absolutely terrible day who takes it out on the chat",
    "a person who insists the AI gave them wrong information last time and wants it fixed NOW",
]

# Tool-triggering topics — these strongly encourage the LLM to call available tools
TOOL_TOPICS = [
    # Weather-heavy
    "checking the weather in 5 different cities around the world",
    "comparing weather between Tokyo, London, and New York right now",
    "planning outdoor activities based on weather in multiple locations",
    "checking if it's good beach weather in several coastal cities",
    "wanting weather updates for a multi-city road trip",
    "checking weather in Paris, Sydney, and Rio de Janeiro for holiday planning",
    "planning a ski trip and checking weather in multiple mountain resorts",

    # Jokes
    "telling a series of jokes on different topics",
    "asking for jokes about programming, weather, and animals",
    "wanting a joke for each day of the week",

    # Mixed weather + jokes
    "asking for the current weather and a joke to lighten the mood",
    "asking for weather in Dublin and a few Irish jokes",
    "wanting the forecast in 4 cities and a joke for each one",

    # Dice rolling
    "playing a tabletop RPG and needing lots of dice rolls",
    "settling a debate by rolling dice multiple times",
    "running a probability experiment with different dice",

    # Time zones
    "checking what time it is in 5 different cities for scheduling a global meeting",
    "figuring out the best time to call friends in Tokyo, London, and Sydney",
    "comparing current times across US time zones",

    # Calculator
    "working through a series of math problems step by step",
    "calculating tip amounts and splitting bills for a group dinner",
    "doing unit price comparisons for grocery shopping",

    # Unit conversion
    "converting recipe measurements between metric and imperial",
    "comparing distances in km and miles for a road trip",
    "converting temperatures between celsius and fahrenheit for travel packing",

    # Inspirational quotes
    "needing motivational quotes for a team presentation",
    "wanting inspirational quotes about perseverance and creativity",
    "collecting quotes on different topics for a vision board",

    # Multi-tool combos
    "planning a world trip: check weather, convert currencies, check time zones",
    "hosting an international party: time zones, weather, unit conversions, and jokes",
    "a curious person who wants weather, time, a dice game, and some quotes all in one chat",
    "asking for the weather, then a math problem, then a joke, then a quote — rapid fire",
]

# Personas that naturally ask about multiple things (triggering multiple tool calls)
TOOL_PERSONAS = [
    "a travel planner who always checks weather in multiple cities before recommending destinations",
    "someone who wants weather for 3+ cities and a joke after each weather update",
    "an event organizer checking weather across multiple venues and wanting icebreaker jokes",
    "a curious person who keeps asking 'what about the weather in [new city]?' after every answer",
    "someone planning a world trip who wants weather in at least 5 different cities",
    "a parent planning weekend activities in different parks and wanting jokes for the kids",
    "a data nerd who wants to compare weather across as many cities as possible",
    "a tabletop gamer who constantly asks for dice rolls with different numbers of dice and sides",
    "a remote worker who always needs to check what time it is in different time zones",
    "a math tutor who asks the assistant to calculate and convert things as examples",
    "someone who wants an inspirational quote after every answer, on different topics each time",
    "a chaotic person who rapid-fires requests: weather, dice, time, jokes, quotes, calculations",
]

# Providers that have tool definitions wired up
TOOL_CAPABLE_PROVIDERS = ["openai_chat", "anthropic", "openai"]


class UserSimulator:
    """
    A LangChain-powered agent that simulates a human user having conversations.

    It generates realistic user messages based on:
    - A randomly selected topic
    - A randomly selected persona
    - The conversation history so far
    """

    def __init__(self, topic: str, persona: str, max_turns: int):
        self.topic = topic
        self.persona = persona
        self.max_turns = max_turns
        self.current_turn = 0

        # Use a lightweight model for user simulation
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.8,  # Higher temperature for more varied user messages
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        self.system_prompt = f"""You are simulating a human user having a conversation with an AI assistant.

Your persona: {persona}

The topic you're interested in: {topic}

Your job is to generate realistic user messages as if you were actually chatting with an AI assistant.

Rules:
1. Start with an opening message related to your topic
2. Ask follow-up questions based on the assistant's responses
3. Be natural - sometimes agree, sometimes ask for clarification, sometimes change direction slightly
4. Keep messages relatively short (1-3 sentences typically)
5. After a few turns, you may naturally wrap up the conversation with thanks or a closing remark
6. Don't be overly formal or robotic - be conversational

You will receive the conversation history and should generate ONLY the next user message.
Do not include any prefix like "User:" - just output the message content directly."""

        self.messages = [SystemMessage(content=self.system_prompt)]

    def generate_message(self, assistant_response: Optional[str] = None) -> tuple[str, bool]:
        """
        Generate the next user message based on conversation history.

        Returns:
            tuple: (message, should_end) where should_end indicates if this should be the last turn
        """
        self.current_turn += 1

        # Add assistant's response to our history if provided
        if assistant_response:
            self.messages.append(AIMessage(content=f"[Assistant's response]: {assistant_response}"))

        # Add instruction for this turn
        if self.current_turn == 1:
            instruction = "Generate your opening message to start the conversation about your topic."
        elif self.current_turn >= self.max_turns:
            instruction = "This is your final turn. Generate a brief closing message (like thanking the assistant or saying goodbye)."
        else:
            # Occasionally prompt for natural conversation endings
            if self.current_turn >= 3 and random.random() < 0.3:
                instruction = "Based on the conversation so far, generate your next message. You may choose to wrap up naturally if you feel satisfied, or continue if you want to know more."
            else:
                instruction = "Based on the assistant's response, generate your next natural follow-up message."

        self.messages.append(HumanMessage(content=instruction))

        # Generate the user message
        response = self.llm.invoke(self.messages)
        user_message = response.content.strip()

        # Clean up - remove any "User:" prefix if the model added one
        if user_message.lower().startswith("user:"):
            user_message = user_message[5:].strip()

        # Update history with what we generated (for context)
        self.messages.append(AIMessage(content=f"[You said]: {user_message}"))

        # Determine if conversation should end
        should_end = self.current_turn >= self.max_turns

        # Check for natural endings
        closing_indicators = ["thank", "thanks", "goodbye", "bye", "that's all", "appreciate", "helpful"]
        if any(indicator in user_message.lower() for indicator in closing_indicators):
            should_end = True

        return user_message, should_end


def slugify(text: str) -> str:
    """Convert text to a URL/identifier-friendly slug."""
    # Lowercase, replace spaces and special chars with underscores
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = re.sub(r'_+', '_', slug)  # Collapse multiple underscores
    slug = slug.strip('_')  # Remove leading/trailing underscores
    return slug


def create_posthog_client(
    session_id: Optional[str] = None,
    span_name: Optional[str] = None,
) -> Posthog:
    """Create a PostHog client with optional session ID and span name."""
    super_properties = {}
    if session_id:
        super_properties["$ai_session_id"] = session_id
    if span_name:
        super_properties["$ai_span_name"] = span_name

    return Posthog(
        os.getenv("POSTHOG_API_KEY"),
        host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
        super_properties=super_properties if super_properties else None,
    )


def create_provider(provider_key: str, posthog_client: Posthog):
    """Create a provider instance by key."""
    if provider_key not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_key}")

    name, factory_fn = PROVIDERS[provider_key]
    return factory_fn(posthog_client)


def get_response_from_provider(provider, message: str, verbose: bool = True) -> str:
    """Get a response from the provider, handling both streaming and non-streaming."""
    if hasattr(provider, 'chat_stream'):
        response_parts = []
        if verbose:
            print("Assistant: ", end="", flush=True)
        for chunk in provider.chat_stream(message):
            response_parts.append(chunk)
            if verbose:
                print(chunk, end="", flush=True)
        if verbose:
            print()
        return "".join(response_parts)
    else:
        response = provider.chat(message)
        if verbose:
            print(f"Assistant: {response}")
        return response


def run_conversation(
    provider_key: str,
    max_turns: int = 5,
    verbose: bool = True,
    delay_between_turns: float = 1.0,
    topic: Optional[str] = None,
    persona: Optional[str] = None,
    distinct_id: Optional[str] = None,
) -> dict:
    """
    Run a single conversation between the User Simulator and a provider.

    Returns a dict with conversation metadata.
    """
    # Select random topic and persona if not specified (do this first for span name)
    topic = topic or random.choice(TOPICS)
    persona = persona or random.choice(USER_PERSONAS)
    provider_name = PROVIDERS[provider_key][0]

    # Set distinct_id for this conversation (providers read from env var)
    conversation_distinct_id = distinct_id or f"user-{uuid.uuid4().hex[:8]}"
    os.environ["POSTHOG_DISTINCT_ID"] = conversation_distinct_id

    # Create span name: topic_provider (e.g., "weather_in_various_cities_openai_chat")
    span_name = f"{slugify(topic)}_{slugify(provider_name)}"

    # Create a new session for this conversation
    session_id = str(uuid.uuid4())
    posthog_client = create_posthog_client(session_id=session_id)

    # Create the target provider (this may set its own span name)
    provider = create_provider(provider_key, posthog_client)

    # Override the span name AFTER provider creation (providers set their own, we want ours)
    posthog_client.super_properties = {
        **(posthog_client.super_properties or {}),
        "$ai_span_name": span_name,
    }

    # Create the user simulator
    simulator = UserSimulator(topic=topic, persona=persona, max_turns=max_turns)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Session: {session_id}")
        print(f"Distinct ID: {conversation_distinct_id}")
        print(f"Span: {span_name}")
        print(f"Provider: {provider_name}")
        print(f"Topic: {topic}")
        print(f"Persona: {persona}")
        print(f"Max turns: {max_turns}")
        print(f"{'='*60}\n")

    conversation_history = []
    actual_turns = 0
    assistant_response = None

    while True:
        actual_turns += 1

        # Generate user message
        try:
            user_message, should_end = simulator.generate_message(assistant_response)
        except Exception as e:
            if verbose:
                print(f"Error generating user message: {e}")
            break

        if verbose:
            print(f"[Turn {actual_turns}]")
            print(f"User: {user_message}")

        conversation_history.append({"role": "user", "content": user_message})

        # Get response from provider
        try:
            assistant_response = get_response_from_provider(provider, user_message, verbose)
            conversation_history.append({"role": "assistant", "content": assistant_response})
        except Exception as e:
            if verbose:
                print(f"Error from provider: {e}")
            conversation_history.append({"role": "error", "content": str(e)})
            break

        if verbose:
            print()

        # Check if we should end
        if should_end:
            if verbose:
                print("[Conversation ended naturally]")
            break

        # Delay between turns
        time.sleep(delay_between_turns)

    # Flush PostHog events
    posthog_client.flush()

    return {
        "session_id": session_id,
        "distinct_id": conversation_distinct_id,
        "span_name": span_name,
        "provider": provider_name,
        "topic": topic,
        "persona": persona,
        "turns": actual_turns,
        "history": conversation_history,
    }


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate demo chat data for PostHog LLM Analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 5 conversations with random providers
  python generate_demo_data.py --conversations 5

  # Use specific providers only
  python generate_demo_data.py --providers openai_chat anthropic --conversations 3

  # Quick test with 3 turns per conversation
  python generate_demo_data.py --max-turns 3 --conversations 2

  # Quiet mode (no output)
  python generate_demo_data.py --quiet --conversations 10

  # Specify a topic
  python generate_demo_data.py --topic "weather in various cities" --conversations 3

  # Use a specific distinct ID for all conversations
  python generate_demo_data.py --distinct-id "demo-user@example.com" --conversations 3

  # Run 20 conversations in parallel with 5 workers
  python generate_demo_data.py --conversations 20 --parallel 5

Available providers:
  anthropic, anthropic_streaming, gemini, gemini_streaming,
  langchain, openai, openai_streaming, openai_chat,
  openai_chat_streaming, litellm, litellm_streaming
        """,
    )

    parser.add_argument(
        "-n", "--conversations",
        type=int,
        default=5,
        help="Number of conversations to generate (default: 5)",
    )
    parser.add_argument(
        "-t", "--max-turns",
        type=int,
        default=5,
        help="Maximum turns per conversation (default: 5)",
    )
    parser.add_argument(
        "-p", "--providers",
        nargs="+",
        choices=list(PROVIDERS.keys()),
        help="Specific providers to use (default: random from all available)",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=1.0,
        help="Delay between turns in seconds (default: 1.0)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode - suppress conversation output",
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Specific topic for all conversations (default: random)",
    )
    parser.add_argument(
        "--persona",
        type=str,
        help="Specific persona for the user simulator (default: random)",
    )
    parser.add_argument(
        "--distinct-id",
        type=str,
        help="PostHog distinct ID for the simulated user (default: random UUID per conversation)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Run N conversations in parallel (default: 1, sequential)",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="Generate tool-heavy conversations (weather lookups, jokes). Forces tool-capable providers and tool-triggering topics.",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List all available providers and exit",
    )
    parser.add_argument(
        "--list-topics",
        action="store_true",
        help="List all conversation topics and exit",
    )
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="List all user personas and exit",
    )

    args = parser.parse_args()

    # Handle list commands
    if args.list_providers:
        print("\nAvailable Providers:")
        print("=" * 50)
        for key, (name, _) in PROVIDERS.items():
            print(f"  {key:25} -> {name}")
        print()
        return

    if args.list_topics:
        print("\nConversation Topics:")
        print("=" * 50)
        for topic in TOPICS:
            print(f"  - {topic}")
        print()
        return

    if args.list_personas:
        print("\nUser Personas:")
        print("=" * 50)
        for persona in USER_PERSONAS:
            print(f"  - {persona}")
        print()
        return

    # Load environment variables
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)

    # Validate environment
    if not os.getenv("POSTHOG_API_KEY"):
        print("Error: POSTHOG_API_KEY not set in environment")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set (needed for User Simulator)")
        sys.exit(1)

    # Determine which providers to use
    if args.tools:
        available_providers = args.providers or TOOL_CAPABLE_PROVIDERS
        # Validate that selected providers actually support tools
        for p in available_providers:
            if p not in TOOL_CAPABLE_PROVIDERS:
                print(f"Warning: provider '{p}' may not support tools, skipping")
        available_providers = [p for p in available_providers if p in TOOL_CAPABLE_PROVIDERS]
        if not available_providers:
            print(f"Error: no tool-capable providers selected. Available: {', '.join(TOOL_CAPABLE_PROVIDERS)}")
            sys.exit(1)
    else:
        available_providers = args.providers or list(PROVIDERS.keys())

    verbose = not args.quiet

    if verbose:
        print("\n" + "=" * 60)
        print("PostHog LLM Analytics Demo Data Generator")
        print("=" * 60)
        print(f"Conversations to generate: {args.conversations}")
        print(f"Max turns per conversation: {args.max_turns}")
        print(f"Providers: {', '.join(available_providers)}")
        print(f"Delay between turns: {args.delay}s")
        print(f"Parallel workers: {args.parallel}")
        if args.tools:
            print(f"Mode: TOOLS (tool-heavy conversations)")
        if args.topic:
            print(f"Topic: {args.topic}")
        if args.persona:
            print(f"Persona: {args.persona}")
        if args.distinct_id:
            print(f"Distinct ID: {args.distinct_id}")
        else:
            print(f"Distinct ID: random per conversation")
        print("=" * 60)

    results = []

    # Helper function for running a single conversation (used by both sequential and parallel)
    def run_single_conversation(conv_index: int):
        provider_key = random.choice(available_providers)
        # In parallel mode, we use quiet mode to avoid jumbled output
        use_verbose = verbose and args.parallel == 1

        # Pick topic and persona — use tool-specific lists when --tools is set
        topic = args.topic
        persona = args.persona
        if args.tools:
            topic = topic or random.choice(TOOL_TOPICS)
            persona = persona or random.choice(TOOL_PERSONAS)

        return run_conversation(
            provider_key=provider_key,
            max_turns=args.max_turns,
            verbose=use_verbose,
            delay_between_turns=args.delay,
            topic=topic,
            persona=persona,
            distinct_id=args.distinct_id,
        )

    if args.parallel > 1:
        # Parallel execution
        if verbose:
            print(f"\nRunning {args.conversations} conversations with {args.parallel} workers...")

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_single_conversation, i): i
                for i in range(args.conversations)
            }

            completed = 0
            for future in as_completed(futures):
                conv_index = futures[future]
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                    if verbose:
                        print(f"[{completed}/{args.conversations}] {result['span_name']} - {result['turns']} turns")
                except Exception as e:
                    print(f"[{completed}/{args.conversations}] Error: {e}")
    else:
        # Sequential execution
        for i in range(args.conversations):
            if verbose:
                print(f"\n>>> Starting conversation {i + 1}/{args.conversations}")

            try:
                result = run_single_conversation(i)
                results.append(result)

                if verbose:
                    print(f"\n>>> Completed conversation {i + 1}/{args.conversations}")
                    print(f"    Session: {result['session_id']}")
                    print(f"    Span: {result['span_name']}")
                    print(f"    Turns: {result['turns']}")

            except Exception as e:
                print(f"\nError in conversation {i + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue

            # Small delay between conversations
            if i < args.conversations - 1:
                time.sleep(0.5)

    # Print summary
    if verbose and results:
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total conversations: {len(results)}")

        provider_counts = {}
        topic_counts = {}
        total_turns = 0

        for r in results:
            provider_counts[r["provider"]] = provider_counts.get(r["provider"], 0) + 1
            topic_counts[r["topic"]] = topic_counts.get(r["topic"], 0) + 1
            total_turns += r["turns"]

        print(f"Total turns: {total_turns}")
        print(f"\nBy Provider:")
        for provider, count in sorted(provider_counts.items()):
            print(f"  {provider}: {count}")

        print(f"\nBy Topic:")
        for topic, count in sorted(topic_counts.items()):
            print(f"  {topic}: {count}")

        print("=" * 60)
        print("Done! Check your PostHog dashboard for LLM analytics data.")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
