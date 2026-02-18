import os
from posthog.ai.openai import OpenAI
from posthog import Posthog
from .base import BaseProvider
from .constants import OPENAI_IMAGE_MODEL, DEFAULT_POSTHOG_DISTINCT_ID

class OpenAIImageProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)

        # Set span name for this provider
        existing_props = posthog_client.super_properties or {}
        posthog_client.super_properties = {**existing_props, "$ai_span_name": "openai_image_generation"}

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            posthog_client=posthog_client
        )

    def get_tool_definitions(self):
        """Return empty tool definitions - image generation doesn't use tools"""
        return []

    def get_name(self):
        return "OpenAI Responses (Image Generation)"

    def generate_image(self, prompt: str, model: str = OPENAI_IMAGE_MODEL) -> str:
        """Generate an image using OpenAI Responses API"""
        try:
            request_params = {
                "model": model,
                "input": prompt,
                "tools": [{"type": "image_generation"}],
                "posthog_distinct_id": os.getenv("POSTHOG_DISTINCT_ID", DEFAULT_POSTHOG_DISTINCT_ID)
            }

            response = self.client.responses.create(**request_params)
            self._debug_api_call("OpenAI Responses Image Generation", request_params, response)

            # Extract image data from output array
            if hasattr(response, 'output') and response.output:
                for output_item in response.output:
                    # Check for image_generation_call type
                    if hasattr(output_item, 'type') and output_item.type == 'image_generation_call':
                        if hasattr(output_item, 'result'):
                            image_base64 = output_item.result
                            return f"data:image/png;base64,{image_base64[:100]}... (base64 image data, {len(image_base64)} chars total)"

            return ""
        except Exception as error:
            print(f'Error in OpenAI image generation: {error}')
            raise Exception(f"OpenAI Image Generation error: {str(error)}")

    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Not implemented - this provider is for image generation only"""
        raise Exception("This provider is for image generation only. Use generate_image() instead.")
