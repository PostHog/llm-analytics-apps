import os
from typing import List, Dict, Any, Optional
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import BaseProvider
from .constants import DEFAULT_POSTHOG_DISTINCT_ID


class OpenAITranscriptionProvider(BaseProvider):
    """
    OpenAI Transcription provider using Whisper API.

    This provider supports audio transcription using OpenAI's Whisper model.
    Supported audio formats: mp3, mp4, mpeg, mpga, m4a, wav, webm
    """

    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_transcription"}

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            posthog_client=posthog_client
        )

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Transcription doesn't use tools"""
        return []

    def get_name(self) -> str:
        return "OpenAI Transcriptions"

    def transcribe(
        self,
        audio_path: str,
        model: str = "whisper-1",
        language: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> str:
        """
        Transcribe audio from a file path.

        Args:
            audio_path: Path to the audio file (supports mp3, mp4, mpeg, mpga, m4a, wav, webm)
            model: Model to use (default: whisper-1)
            language: Optional language code (e.g., 'en', 'es', 'ca')
            prompt: Optional prompt to guide transcription

        Returns:
            Transcription text
        """
        with open(audio_path, "rb") as audio_file:
            transcription_params = {
                "file": audio_file,
                "model": model
            }

            # Add optional parameters
            if language:
                transcription_params["language"] = language
            if prompt:
                transcription_params["prompt"] = prompt

            transcription = self.client.audio.transcriptions.create(**transcription_params)

            # Debug log (excluding file object for cleaner output)
            debug_params = {k: v for k, v in transcription_params.items() if k != "file"}
            debug_params["file"] = audio_path
            self._debug_api_call("OpenAI Transcription", debug_params, transcription)

            return transcription.text if hasattr(transcription, 'text') else str(transcription)

    def transcribe_verbose(
        self,
        audio_path: str,
        model: str = "whisper-1",
        language: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio with verbose response format.

        Args:
            audio_path: Path to the audio file
            model: Model to use (default: whisper-1)
            language: Optional language code
            prompt: Optional prompt to guide transcription

        Returns:
            Verbose transcription with segments, language, duration
        """
        with open(audio_path, "rb") as audio_file:
            transcription_params = {
                "file": audio_file,
                "model": model,
                "response_format": "verbose_json",
                "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
            }

            # Add optional parameters
            if language:
                transcription_params["language"] = language
            if prompt:
                transcription_params["prompt"] = prompt

            transcription = self.client.audio.transcriptions.create(**transcription_params)

            # Debug log (excluding file object for cleaner output)
            debug_params = {k: v for k, v in transcription_params.items() if k != "file"}
            debug_params["file"] = audio_path
            self._debug_api_call("OpenAI Transcription (Verbose)", debug_params, transcription)

            return transcription

    def chat(self, user_input: str, base64_image: Optional[str] = None) -> str:
        """This provider is for transcriptions only. Use transcribe() method instead."""
        return "This provider is for transcriptions only. Use transcribe() method instead."
