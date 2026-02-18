import os
import base64
from posthog.ai.anthropic import Anthropic
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic provider using Messages API with PostHog tracking"""

    def __init__(self, posthog_client):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {
            **existing_props,
            "$ai_span_name": "anthropic_messages",
        }

        # Initialize PostHog-wrapped Anthropic client
        self.client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"), posthog_client=posthog_client
        )

    def get_name(self) -> str:
        return "Anthropic"

    def get_options(self) -> list:
        """Return available options"""
        return [
            {
                "id": "thinking",
                "name": "Extended Thinking",
                "shortcutKey": "t",
                "type": "boolean",
                "default": False,
            }
        ]

    def get_input_modes(self) -> list[str]:
        """Anthropic supports text, images, and files"""
        return ["text", "image", "file"]

    def chat(self, messages: list) -> dict:
        """
        Convert our Message format to Anthropic format, call API, return Message format.
        """
        # Convert our messages to Anthropic format
        anthropic_messages = []

        for msg in messages:
            role = msg["role"]
            if role == "system":
                # Anthropic handles system messages separately (not supported in v2 yet)
                continue

            # Build content array for Anthropic
            content = []

            for block in msg["content"]:
                if block["type"] == "text":
                    content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "file" or block["type"] == "image":
                    # Read and encode file
                    file_path = block["path"]

                    with open(file_path, "rb") as f:
                        base64_data = base64.b64encode(f.read()).decode("utf-8")

                    # Determine media type
                    if block["type"] == "image":
                        # For explicit image blocks, detect image type
                        mime_type = "image/png"  # Default
                        if file_path.lower().endswith(".jpg") or file_path.lower().endswith(
                            ".jpeg"
                        ):
                            mime_type = "image/jpeg"
                        elif file_path.lower().endswith(".gif"):
                            mime_type = "image/gif"
                        elif file_path.lower().endswith(".webp"):
                            mime_type = "image/webp"

                        content.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64_data,
                                },
                            }
                        )
                    else:
                        # For file blocks, use the provided MIME type
                        mime_type = block.get("mimeType", "application/octet-stream")

                        # Images as files should use image type
                        if mime_type.startswith("image/"):
                            content.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_data,
                                    },
                                }
                            )
                        else:
                            # All other files use document type
                            content.append(
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_data,
                                    },
                                }
                            )

            if content:
                anthropic_messages.append({"role": role, "content": content})

        # Prepare API request parameters
        request_params = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        # Add extended thinking if enabled
        thinking_enabled = self.get_option("thinking", False)
        if thinking_enabled:
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": 10000,
            }
            # Increase max_tokens to accommodate thinking
            request_params["max_tokens"] = 16000

        # Call Anthropic API
        response = self.client.messages.create(**request_params)

        # Process response content blocks
        response_content = []

        for block in response.content:
            if block.type == "text":
                response_content.append({"type": "text", "text": block.text})
            elif block.type == "thinking" and thinking_enabled:
                # Include thinking as text block with special marker
                response_content.append(
                    {"type": "text", "text": f"[Thinking]\n{block.thinking}"}
                )

        # Return in our Message format
        return {
            "role": "assistant",
            "content": response_content if response_content else [{"type": "text", "text": ""}],
        }
