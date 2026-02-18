import base64
from pathlib import Path
from typing import Any

from .base import BaseProvider
from .anthropic_streaming import AnthropicStreamingProvider
from .gemini_image import GeminiImageProvider
from .gemini_streaming import GeminiStreamingProvider
from .langchain import LangChainProvider
from .litellm_provider import LiteLLMProvider
from .litellm_streaming import LiteLLMStreamingProvider
from .openai_chat import OpenAIChatProvider
from .openai_chat_streaming import OpenAIChatStreamingProvider
from .openai_image import OpenAIImageProvider
from .openai_otel import OpenAIOtelProvider
from .openai_streaming import OpenAIStreamingProvider
from .openai_transcription import OpenAITranscriptionProvider


def _extract_latest_user_input(messages: list[dict[str, Any]]):
    user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg
            break

    if not user_message:
        return {"text": "Hello!", "image_base64": None, "audio_path": None}

    text_parts = []
    image_base64 = None
    audio_path = None

    for block in user_message.get("content", []):
        block_type = block.get("type")

        if block_type == "text" and block.get("text"):
            text_parts.append(block["text"])
            continue

        file_path = block.get("path")
        if not file_path:
            continue

        mime_type = block.get("mimeType", "")
        if image_base64 is None and (
            block_type == "image" or mime_type.startswith("image/")
        ):
            try:
                image_base64 = base64.b64encode(Path(file_path).read_bytes()).decode(
                    "utf-8",
                )
            except Exception:
                image_base64 = None
            continue

        if audio_path is None and mime_type.startswith("audio/"):
            audio_path = file_path

    text = "\n".join(text_parts).strip() or "Hello!"
    return {"text": text, "image_base64": image_base64, "audio_path": audio_path}


class _CompatAdapterMixin:
    LEGACY_CLASS = None
    INPUT_MODES = ["text"]

    def __init__(self, posthog_client):
        super().__init__(posthog_client)
        if self.LEGACY_CLASS is None:
            raise RuntimeError("LEGACY_CLASS must be set")
        self._legacy = self.LEGACY_CLASS(posthog_client)

    def get_name(self) -> str:
        return self._legacy.get_name()

    def get_options(self) -> list:
        if hasattr(self._legacy, "get_options"):
            try:
                return self._legacy.get_options() or []
            except Exception:
                return []
        return []

    def set_option(self, option_id: str, value):
        super().set_option(option_id, value)
        if hasattr(self._legacy, "set_option"):
            self._legacy.set_option(option_id, value)
            return
        if option_id == "model" and hasattr(self._legacy, "set_model"):
            self._legacy.set_model(str(value))

    def get_input_modes(self) -> list[str]:
        if hasattr(self._legacy, "get_input_modes"):
            try:
                modes = self._legacy.get_input_modes()
                if modes:
                    return modes
            except Exception:
                pass
        return self.INPUT_MODES

    def chat(self, messages: list) -> dict:
        extracted = _extract_latest_user_input(messages)
        user_text = extracted["text"]
        image_base64 = extracted["image_base64"]
        audio_path = extracted["audio_path"]

        if hasattr(self._legacy, "transcribe"):
            if not audio_path:
                return {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "No audio file provided for transcription.",
                        },
                    ],
                }
            text = self._legacy.transcribe(audio_path)
            return {
                "role": "assistant",
                "content": [{"type": "text", "text": text or ""}],
            }

        if hasattr(self._legacy, "generate_image"):
            image_result = self._legacy.generate_image(user_text)
            return {
                "role": "assistant",
                "content": [{"type": "text", "text": image_result or ""}],
            }

        if hasattr(self._legacy, "chat_stream"):
            chunks = []
            for chunk in self._legacy.chat_stream(user_text, image_base64):
                chunks.append(chunk)
            response = "".join(chunks)
        else:
            response = self._legacy.chat(user_text, image_base64)

        if isinstance(response, dict):
            return response

        return {
            "role": "assistant",
            "content": [{"type": "text", "text": str(response)}],
        }


class AnthropicStreamingCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = AnthropicStreamingProvider
    INPUT_MODES = ["text", "image", "file"]


class GeminiImageCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = GeminiImageProvider
    INPUT_MODES = ["text"]


class GeminiStreamingCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = GeminiStreamingProvider
    INPUT_MODES = ["text", "image", "file"]


class LangChainCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = LangChainProvider
    INPUT_MODES = ["text"]


class LiteLLMCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = LiteLLMProvider
    INPUT_MODES = ["text", "image", "file"]


class LiteLLMStreamingCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = LiteLLMStreamingProvider
    INPUT_MODES = ["text", "image", "file"]


class OpenAIChatCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAIChatProvider
    INPUT_MODES = ["text", "image", "file"]


class OpenAIChatStreamingCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAIChatStreamingProvider
    INPUT_MODES = ["text", "image", "file"]


class OpenAIImageCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAIImageProvider
    INPUT_MODES = ["text"]


class OpenAIOtelCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAIOtelProvider
    INPUT_MODES = ["text", "image", "file"]


class OpenAIStreamingCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAIStreamingProvider
    INPUT_MODES = ["text", "image", "file"]


class OpenAITranscriptionCompatProvider(_CompatAdapterMixin, BaseProvider):
    LEGACY_CLASS = OpenAITranscriptionProvider
    INPUT_MODES = ["audio", "file"]
