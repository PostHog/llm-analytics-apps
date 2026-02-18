import os
import json
from posthog.ai.gemini import Client
from posthog import Posthog
from .compat_base import BaseProvider
from .constants import GEMINI_IMAGE_MODEL, DEFAULT_POSTHOG_DISTINCT_ID

class GeminiImageProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "gemini_generate_image"}

        self.client = Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            posthog_client=posthog_client
        )

    def get_tool_definitions(self):
        """Return empty tool definitions - image generation doesn't use tools"""
        return []

    def get_name(self):
        return "Google Gemini (Image Generation)"

    def _log_token_usage_by_modality(self, response):
        """Log token usage breakdown by modality in debug mode"""
        if not self.debug_mode:
            return

        try:
            usage_metadata = getattr(response, 'usage_metadata', None)
            if not usage_metadata:
                print("\n📊 Token Usage: No modality breakdown available\n")
                return

            print("\n" + "─" * 60)
            print("📊 TOKEN USAGE BY MODALITY")
            print("─" * 60)

            # Input tokens breakdown
            prompt_details = getattr(usage_metadata, 'prompt_tokens_details', [])
            print("\n  INPUT TOKENS:")
            if prompt_details:
                for detail in prompt_details:
                    modality = getattr(detail, 'modality', 'unknown')
                    token_count = getattr(detail, 'token_count', 0)
                    print(f"    {modality}: {token_count} tokens")
            else:
                prompt_token_count = getattr(usage_metadata, 'prompt_token_count', 0)
                print(f"    Total: {prompt_token_count} tokens")

            # Output tokens breakdown
            candidates_details = getattr(usage_metadata, 'candidates_tokens_details', [])
            print("\n  OUTPUT TOKENS:")
            if candidates_details:
                for detail in candidates_details:
                    modality = getattr(detail, 'modality', 'unknown')
                    token_count = getattr(detail, 'token_count', 0)
                    print(f"    {modality}: {token_count} tokens")
            else:
                candidates_token_count = getattr(usage_metadata, 'candidates_token_count', 0)
                print(f"    Total: {candidates_token_count} tokens")

            total_token_count = getattr(usage_metadata, 'total_token_count', 0)
            print(f"\n  TOTAL: {total_token_count} tokens")
            print("─" * 60 + "\n")
        except Exception:
            # Silently ignore errors in debug logging
            pass

    def generate_image(self, prompt: str, model: str = GEMINI_IMAGE_MODEL) -> str:
        """Generate an image using Google Gemini"""
        try:
            request_params = {
                "model": model,
                "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID),
                "contents": prompt
            }

            response = self.client.models.generate_content(**request_params)
            self._debug_api_call("Google Gemini Image Generation", request_params, response)
            self._log_token_usage_by_modality(response)

            # Check for images in the response candidates
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = getattr(candidate.content, 'parts', [])
                        for part in parts:
                            # Check for inline image data
                            inline_data = getattr(part, 'inline_data', None)
                            if inline_data:
                                data = getattr(inline_data, 'data', None)
                                mime_type = getattr(inline_data, 'mime_type', '')
                                if data and mime_type.startswith('image/'):
                                    return f"data:{mime_type};base64,{data[:100]}... (base64 image data, {len(data)} chars total)"

            return ""
        except Exception as error:
            print(f'Error in Gemini image generation: {error}')
            raise Exception(f"Gemini Image Generation error: {str(error)}")

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Not implemented - this provider is for image generation only"""
        raise Exception("This provider is for image generation only. Use generate_image() instead.")
