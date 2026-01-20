"""
Pydantic AI provider with PostHog instrumentation via OpenTelemetry.

This provider uses Pydantic AI's native OTel instrumentation, translated to PostHog
events via the PostHogSpanExporter.
"""

import os
from typing import Optional
from posthog import Posthog

from .base import BaseProvider
from .constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_VISION_MODEL,
    DEFAULT_POSTHOG_DISTINCT_ID,
    SYSTEM_PROMPT_FRIENDLY
)


class PydanticAIProvider(BaseProvider):
    """Pydantic AI provider with PostHog OpenTelemetry instrumentation."""

    _instrumented = False  # Class-level flag to prevent double instrumentation

    def __init__(self, posthog_client: Posthog):
        # Import pydantic-ai here to avoid import errors if not installed
        try:
            from pydantic_ai import Agent
        except ImportError:
            raise ImportError(
                "pydantic-ai is required for this provider. "
                "Install it with: pip install pydantic-ai"
            )

        super().__init__(posthog_client)

        # Extract distinct_id from environment or use default
        self.distinct_id = os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID)

        # Extract session ID from super_properties if available
        existing_props = posthog_client.super_properties or {}
        self.ai_session_id = existing_props.get("$ai_session_id")

        # Set up PostHog instrumentation for Pydantic AI (once globally)
        if not PydanticAIProvider._instrumented:
            self._setup_instrumentation(posthog_client)
            PydanticAIProvider._instrumented = True

        # Configure model
        self.model = f"openai:{OPENAI_CHAT_MODEL}"

        # Create the agent with tools
        self.agent = self._create_agent()

        # Store conversation history for multi-turn conversations
        self._message_history = None

    def _setup_instrumentation(self, posthog_client: Posthog):
        """Set up PostHog instrumentation for Pydantic AI."""
        try:
            from posthog.ai.pydantic_ai import instrument_pydantic_ai
        except ImportError:
            raise ImportError(
                "PostHog pydantic-ai integration is required. "
                "Make sure you're using a posthog version with pydantic-ai support."
            )

        # Build additional properties
        properties = {}
        if self.ai_session_id:
            properties["$ai_session_id"] = self.ai_session_id

        # Instrument all Pydantic AI agents with PostHog
        instrument_pydantic_ai(
            client=posthog_client,
            distinct_id=self.distinct_id,
            privacy_mode=False,  # Include content in traces
            properties=properties,
            debug=self.debug_mode,
        )

        if self.debug_mode:
            print("✅ Pydantic AI instrumentation configured for PostHog")

    def _create_agent(self):
        """Create a Pydantic AI agent with tools."""
        from pydantic_ai import Agent

        # Create agent with system prompt
        agent = Agent(
            self.model,
            system_prompt=SYSTEM_PROMPT_FRIENDLY,
        )

        # Register tools using decorator
        @agent.tool_plain
        def get_weather(latitude: float, longitude: float, location_name: str) -> str:
            """Get the current weather for a specific location using geographical coordinates.

            Args:
                latitude: The latitude of the location (e.g., 37.7749 for San Francisco)
                longitude: The longitude of the location (e.g., -122.4194 for San Francisco)
                location_name: A human-readable name for the location (e.g., 'San Francisco, CA')
            """
            return self.get_weather(latitude, longitude, location_name)

        @agent.tool_plain
        def tell_joke(setup: str, punchline: str) -> str:
            """Tell a joke with a question-style setup and an answer punchline.

            Args:
                setup: The setup or question part of the joke
                punchline: The punchline or answer part of the joke
            """
            return self.tell_joke(setup, punchline)

        return agent

    def get_tool_definitions(self):
        """Return tool definitions (for interface compatibility).

        Note: Pydantic AI tools are defined via decorators, so this returns
        a description of the available tools rather than provider-specific format.
        """
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather for a specific location using geographical coordinates",
            },
            {
                "name": "tell_joke",
                "description": "Tell a joke with a question-style setup and an answer punchline",
            },
        ]

    def get_name(self):
        return "Pydantic AI (OpenTelemetry)"

    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        """Send a message to the Pydantic AI agent and get response.

        Args:
            user_input: The user's message
            base64_image: Optional base64-encoded image (not currently supported)

        Returns:
            The agent's response as a string
        """
        if base64_image:
            # Pydantic AI image handling would require additional setup
            return "❌ Image input is not yet supported with Pydantic AI provider"

        try:
            # Run the agent with conversation history for multi-turn support
            result = self.agent.run_sync(
                user_input,
                message_history=self._message_history,
            )

            # Store message history for next turn
            self._message_history = result.all_messages()

            # Debug logging
            if self.debug_mode:
                self._debug_log("Pydantic AI Result", {
                    "output": str(result.output),
                    "all_messages_count": len(result.all_messages()),
                })

            # Return the result output (the agent's response)
            return str(result.output)

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            if self.debug_mode:
                import traceback
                self._debug_log("Pydantic AI Error", traceback.format_exc())
            return error_msg

    def reset_conversation(self):
        """Reset the conversation by clearing message history."""
        self._message_history = None
