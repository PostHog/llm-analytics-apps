from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Base class for all AI providers"""

    def __init__(self, posthog_client):
        self.posthog_client = posthog_client
        self.option_values = {}  # Store current option values

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the provider"""
        pass

    def get_options(self) -> list:
        """
        Return list of option definitions for this provider.

        Returns:
            List of option dicts with keys: id, name, shortcutKey, type, default, options (for enum)
        """
        return []

    def set_option(self, option_id: str, value):
        """Set an option value"""
        self.option_values[option_id] = value

    def get_option(self, option_id: str, default=None):
        """Get current option value"""
        return self.option_values.get(option_id, default)

    def get_input_modes(self) -> list[str]:
        """
        Return list of input modes this provider accepts.

        Returns:
            List of mode strings: "text", "audio", "image", "video", "file"
        """
        return ["text"]

    @abstractmethod
    def chat(self, messages: list) -> dict:
        """
        Send messages and get response.

        Args:
            messages: List of Message objects in format:
                [{"role": "user"|"assistant", "content": [{"type": "text"|"file", ...}]}]

        Returns:
            Message object: {"role": "assistant", "content": [{"type": "text", "text": "..."}]}
        """
        pass
