import os
import base64
import time
from pathlib import Path
from posthog.ai.openai import OpenAI
from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI provider using Responses API with PostHog tracking"""

    def __init__(self, posthog_client):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {
            **existing_props,
            "$ai_span_name": "openai_responses",
        }

        # Initialize PostHog-wrapped OpenAI client
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"), posthog_client=posthog_client
        )

    def get_name(self) -> str:
        return "OpenAI"

    def get_options(self) -> list:
        """Return available endpoint options"""
        return [
            {
                "id": "endpoint",
                "name": "Endpoint",
                "shortcutKey": "e",
                "type": "enum",
                "default": "responses_api_gpt5",
                "options": [
                    {"id": "responses_api_gpt5", "label": "Responses API (GPT-5)"},
                    {
                        "id": "audio_api_gpt4o_audio_preview",
                        "label": "Audio API (gpt-4o-audio-preview)",
                    },
                ],
            }
        ]

    def get_input_modes(self) -> list[str]:
        """Return input modes based on current endpoint"""
        endpoint = self.get_option("endpoint", "responses_api_gpt5")

        if endpoint == "audio_api_gpt4o_audio_preview":
            # Audio API only accepts text input (for conversational TTS)
            return ["text"]
        else:
            # Responses API accepts multimodal input (image and file)
            return ["text", "image", "file"]

    def chat(self, messages: list) -> dict:
        """
        Convert our Message format to OpenAI format, call API, return Message format.
        """
        # Get current endpoint (defaults to responses API)
        endpoint = self.get_option("endpoint", "responses_api_gpt5")

        if endpoint == "audio_api_gpt4o_audio_preview":
            return self._chat_audio_api(messages)
        else:
            return self._chat_responses_api(messages)

    def _chat_responses_api(self, messages: list) -> dict:
        """Use the Responses API (GPT-5)"""
        # Convert our messages to OpenAI format
        openai_messages = []
        for msg in messages:
            role = msg["role"]
            # Build content array for OpenAI
            content = []

            for block in msg["content"]:
                if block["type"] == "text":
                    content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "file":
                    # Read and encode file
                    file_path = block["path"]
                    filename = os.path.basename(file_path)
                    mime_type = block["mimeType"]  # Use pre-detected MIME type

                    with open(file_path, "rb") as f:
                        base64_data = base64.b64encode(f.read()).decode("utf-8")

                    # Determine OpenAI content type based on MIME type
                    if mime_type.startswith("image/"):
                        # Image files
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            }
                        })
                    elif mime_type.startswith("audio/"):
                        # Audio files - extract format from extension
                        file_ext = os.path.splitext(file_path)[1].lower()[1:]  # Remove leading dot
                        content.append({
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64_data,
                                "format": file_ext
                            }
                        })
                    else:
                        # All other files (PDF, documents, etc.)
                        content.append({
                            "type": "file",
                            "file": {
                                "filename": filename,
                                "file_data": f"data:{mime_type};base64,{base64_data}"
                            }
                        })

            if content:
                openai_messages.append({"role": role, "content": content})

        # Call OpenAI API
        response = self.client.chat.completions.create(
            model="gpt-5",
            messages=openai_messages,
        )

        # Extract response text
        response_text = response.choices[0].message.content or ""

        # Return in our Message format
        return {
            "role": "assistant",
            "content": [{"type": "text", "text": response_text}],
        }

    def _chat_audio_api(self, messages: list) -> dict:
        """Use the Audio API (gpt-4o-audio-preview) - single call with audio output"""
        # Extract only text content from messages (audio API doesn't support files)
        openai_messages = []
        for msg in messages:
            role = msg["role"]
            text_content = []

            for block in msg["content"]:
                if block["type"] == "text":
                    text_content.append({"type": "text", "text": block["text"]})

            if text_content:
                openai_messages.append({"role": role, "content": text_content})

        # Single API call with audio modality
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-audio-preview",
                modalities=["text", "audio"],
                audio={"voice": "alloy", "format": "wav"},
                messages=openai_messages,
            )

            # Extract and decode audio (symmetrical to input encoding at line 91)
            if hasattr(response.choices[0].message, "audio") and response.choices[0].message.audio:
                audio_obj = response.choices[0].message.audio
                audio_data = audio_obj.data
                transcript = getattr(audio_obj, "transcript", "") or ""
                wav_bytes = base64.b64decode(audio_data)

                # Create audio output directory
                audio_dir = Path.home() / ".llm-analytics-apps" / "audio"
                audio_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with timestamp
                timestamp = int(time.time() * 1000)
                audio_filename = f"audio_{timestamp}.wav"
                audio_file_path = str(audio_dir / audio_filename)

                # Save decoded audio to file
                with open(audio_file_path, "wb") as f:
                    f.write(wav_bytes)

                # Return audio response with transcript
                return {
                    "role": "assistant",
                    "content": [
                        {"type": "audio", "path": audio_file_path, "transcript": transcript}
                    ],
                }
            else:
                # No audio in response, return text only
                text_content = response.choices[0].message.content or ""
                return {
                    "role": "assistant",
                    "content": [{"type": "text", "text": text_content}],
                }

        except Exception as e:
            # If audio generation fails, return text with error
            error_text = f"(Audio generation failed: {str(e)})"
            return {
                "role": "assistant",
                "content": [{"type": "text", "text": error_text}],
            }
