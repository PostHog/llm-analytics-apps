import base64
import importlib
import sys
import types
from pathlib import Path
from typing import Any

from .base import BaseProvider


LEGACY_PROVIDERS_DIR = (
    Path(__file__).resolve().parents[1] / "legacy_providers"
)


def _load_legacy_class(module_name: str, class_name: str):
    module_path = LEGACY_PROVIDERS_DIR / f"{module_name}.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Legacy provider module not found: {module_path}")

    package_name = "legacy_providers"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(LEGACY_PROVIDERS_DIR)]  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    module = importlib.import_module(f"{package_name}.{module_name}")
    provider_class = getattr(module, class_name, None)
    if provider_class is None:
        raise RuntimeError(
            f"Class {class_name} not found in legacy module {module_path.name}",
        )
    return provider_class


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


class LegacyProviderBridge(BaseProvider):
    LEGACY_MODULE = ""
    LEGACY_CLASS = ""
    INPUT_MODES = ["text"]

    def __init__(self, posthog_client):
        super().__init__(posthog_client)
        klass = _load_legacy_class(self.LEGACY_MODULE, self.LEGACY_CLASS)
        self._legacy = klass(posthog_client)

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

        response = self._legacy.chat(user_text, image_base64)
        if isinstance(response, dict):
            return response

        return {
            "role": "assistant",
            "content": [{"type": "text", "text": str(response)}],
        }


class AnthropicStreamingBridge(LegacyProviderBridge):
    LEGACY_MODULE = "anthropic_streaming"
    LEGACY_CLASS = "AnthropicStreamingProvider"
    INPUT_MODES = ["text", "image", "file"]


class GeminiImageBridge(LegacyProviderBridge):
    LEGACY_MODULE = "gemini_image"
    LEGACY_CLASS = "GeminiImageProvider"
    INPUT_MODES = ["text"]


class GeminiStreamingBridge(LegacyProviderBridge):
    LEGACY_MODULE = "gemini_streaming"
    LEGACY_CLASS = "GeminiStreamingProvider"
    INPUT_MODES = ["text", "image", "file"]


class LangChainBridge(LegacyProviderBridge):
    LEGACY_MODULE = "langchain"
    LEGACY_CLASS = "LangChainProvider"
    INPUT_MODES = ["text"]


class LiteLLMBridge(LegacyProviderBridge):
    LEGACY_MODULE = "litellm_provider"
    LEGACY_CLASS = "LiteLLMProvider"
    INPUT_MODES = ["text", "image", "file"]


class LiteLLMStreamingBridge(LegacyProviderBridge):
    LEGACY_MODULE = "litellm_streaming"
    LEGACY_CLASS = "LiteLLMStreamingProvider"
    INPUT_MODES = ["text", "image", "file"]


class OpenAIChatBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_chat"
    LEGACY_CLASS = "OpenAIChatProvider"
    INPUT_MODES = ["text", "image", "file"]


class OpenAIChatStreamingBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_chat_streaming"
    LEGACY_CLASS = "OpenAIChatStreamingProvider"
    INPUT_MODES = ["text", "image", "file"]


class OpenAIImageBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_image"
    LEGACY_CLASS = "OpenAIImageProvider"
    INPUT_MODES = ["text"]


class OpenAIOtelBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_otel"
    LEGACY_CLASS = "OpenAIOtelProvider"
    INPUT_MODES = ["text", "image", "file"]


class OpenAIStreamingBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_streaming"
    LEGACY_CLASS = "OpenAIStreamingProvider"
    INPUT_MODES = ["text", "image", "file"]


class OpenAITranscriptionBridge(LegacyProviderBridge):
    LEGACY_MODULE = "openai_transcription"
    LEGACY_CLASS = "OpenAITranscriptionProvider"
    INPUT_MODES = ["audio", "file"]
