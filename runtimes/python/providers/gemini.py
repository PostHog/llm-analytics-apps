import os
import base64
import time
import wave
from pathlib import Path
from posthog.ai.gemini import Client
from google.genai import types
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini provider with PostHog tracking"""

    def __init__(self, posthog_client):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {
            **existing_props,
            "$ai_span_name": "gemini_generate_content",
        }

        # Initialize PostHog-wrapped Gemini client
        self.client = Client(
            api_key=os.getenv("GEMINI_API_KEY"), posthog_client=posthog_client
        )

    def get_name(self) -> str:
        return "Gemini"

    def get_options(self) -> list:
        """Return available mode options"""
        return [
            {
                "id": "mode",
                "name": "Mode",
                "shortcutKey": "m",
                "type": "enum",
                "default": "text",
                "options": [
                    {"id": "text", "label": "Text Mode"},
                    {"id": "audio", "label": "Audio Mode (TTS)"},
                ],
            }
        ]

    def get_input_modes(self) -> list[str]:
        """Return input modes based on current mode"""
        mode = self.get_option("mode", "text")

        if mode == "audio":
            # Audio mode only accepts text input
            return ["text"]
        else:
            # Text mode accepts text, images, and files
            return ["text", "image", "file"]

    def chat(self, messages: list) -> dict:
        """
        Convert our Message format to Gemini format, call API, return Message format.
        """
        # Get current mode (defaults to text)
        mode = self.get_option("mode", "text")

        if mode == "audio":
            return self._chat_audio_mode(messages)
        else:
            return self._chat_text_mode(messages)

    def _chat_text_mode(self, messages: list) -> dict:
        """Use Gemini in text mode with multimodal support"""
        # Convert our messages to Gemini format
        gemini_contents = []

        for msg in messages:
            role = msg["role"]
            if role == "system":
                # Gemini doesn't have a separate system role, skip for now
                continue

            # Map role: "assistant" -> "model" for Gemini
            gemini_role = "model" if role == "assistant" else "user"

            # Build parts array for Gemini
            parts = []

            for block in msg["content"]:
                if block["type"] == "text":
                    parts.append({"text": block["text"]})
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
                    else:
                        # For file blocks, use the provided MIME type
                        mime_type = block.get("mimeType", "application/octet-stream")

                    # Gemini uses inline_data format for all files (images, PDFs, etc.)
                    parts.append(
                        {"inline_data": {"mime_type": mime_type, "data": base64_data}}
                    )

            if parts:
                gemini_contents.append({"role": gemini_role, "parts": parts})

        # Call Gemini API
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=gemini_contents,
        )

        # Extract response text
        response_text = ""
        if hasattr(response, "text"):
            response_text = response.text
        elif (
            hasattr(response, "candidates")
            and response.candidates
            and hasattr(response.candidates[0], "content")
            and response.candidates[0].content
        ):
            # Extract text from parts
            text_parts = []
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text"):
                    text_parts.append(part.text)
            response_text = "".join(text_parts)

        # Return in our Message format
        return {
            "role": "assistant",
            "content": [{"type": "text", "text": response_text}],
        }

    def _chat_audio_mode(self, messages: list) -> dict:
        """Use Gemini TTS - converts provided text to speech (does NOT generate content)"""
        # Extract only text content from messages
        text_parts = []
        for msg in messages:
            if msg["role"] == "system":
                continue
            for block in msg["content"]:
                if block["type"] == "text":
                    text_parts.append(block["text"])

        # Combine all text - this is what will be spoken
        text_to_speak = "\n".join(text_parts)

        try:
            # Call Gemini TTS API with PostHog tracking
            # NOTE: TTS models only convert text to speech - they don't generate content
            # Valid: "Say hello" -> speaks "Say hello"
            # Invalid: "Tell me a joke" -> model doesn't generate a joke
            tts_response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text_to_speak,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Kore",
                            )
                        )
                    ),
                ),
            )

            # Extract audio data using official documented path
            # According to docs: response.candidates[0].content.parts[0].inline_data.data
            pcm_data = None

            # Comprehensive logging
            debug_file = Path.home() / ".llm-analytics-apps" / "gemini_full_debug.txt"
            with open(debug_file, "w") as f:
                f.write(f"=== FULL RESPONSE DEBUG ===\n")
                f.write(f"Input text: {text_to_speak}\n\n")
                f.write(f"Response: {tts_response}\n\n")
                f.write(f"Has candidates: {hasattr(tts_response, 'candidates')}\n")
                if hasattr(tts_response, "candidates"):
                    f.write(f"Candidates len: {len(tts_response.candidates) if tts_response.candidates else 'None'}\n")
                    if tts_response.candidates and len(tts_response.candidates) > 0:
                        cand = tts_response.candidates[0]
                        f.write(f"Finish reason: {cand.finish_reason}\n")
                        f.write(f"Finish message: {cand.finish_message if hasattr(cand, 'finish_message') else 'N/A'}\n")
                        f.write(f"Safety ratings: {cand.safety_ratings if hasattr(cand, 'safety_ratings') else 'N/A'}\n")
                        f.write(f"Content is None: {cand.content is None}\n\n")
                        if cand.content:
                            f.write(f"Content parts: {cand.content.parts}\n")
                # Check prompt_feedback for safety issues
                if hasattr(tts_response, "prompt_feedback"):
                    f.write(f"\nPrompt feedback: {tts_response.prompt_feedback}\n")

            if (
                hasattr(tts_response, "candidates")
                and tts_response.candidates
                and len(tts_response.candidates) > 0
            ):
                candidate = tts_response.candidates[0]
                if hasattr(candidate, "content") and candidate.content:
                    if hasattr(candidate.content, "parts") and candidate.content.parts:
                        audio_part = candidate.content.parts[0]
                        if hasattr(audio_part, "inline_data") and audio_part.inline_data:
                            data = audio_part.inline_data.data

                            # Handle both formats (GitHub issue #837):
                            # - Sometimes returns raw bytes (can use directly)
                            # - Sometimes returns base64 string (must decode)
                            if isinstance(data, bytes):
                                pcm_data = data
                            elif isinstance(data, str):
                                pcm_data = base64.b64decode(data)
                            else:
                                pcm_data = data  # Hope it works

            # If we got audio data, save it
            if pcm_data:
                # Create audio output directory
                audio_dir = Path.home() / ".llm-analytics-apps" / "audio"
                audio_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with timestamp
                timestamp = int(time.time() * 1000)
                audio_filename = f"gemini_audio_{timestamp}.wav"
                audio_file_path = str(audio_dir / audio_filename)

                # Save as WAV file with proper headers
                with wave.open(audio_file_path, "wb") as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(24000)  # 24kHz
                    wav_file.writeframes(pcm_data)

                # Try to get transcript from response text
                transcript = ""
                if hasattr(tts_response, "text"):
                    transcript = tts_response.text

                # Return audio response with transcript
                return {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "audio",
                            "path": audio_file_path,
                            "transcript": transcript,
                        }
                    ],
                }

            # No audio in response - likely because TTS model can't generate content
            error_msg = (
                "Gemini TTS failed to generate audio.\n\n"
                "NOTE: TTS models only convert text to speech - they don't generate content.\n"
                f"Your input: '{text_to_speak}'\n\n"
                "Valid examples:\n"
                "  • 'Say hello' -> speaks 'Say hello'\n"
                "  • 'Have a wonderful day!' -> speaks it\n\n"
                "Invalid examples:\n"
                "  • 'Tell me a joke' -> model won't generate a joke\n"
                "  • 'What's 2+2?' -> model won't answer\n\n"
                "Use Text mode for content generation."
            )

            return {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": error_msg}
                ],
            }

        except Exception as e:
            # If audio generation fails, return text with error
            error_text = f"(Audio generation failed: {str(e)})"
            return {
                "role": "assistant",
                "content": [{"type": "text", "text": error_text}],
            }
