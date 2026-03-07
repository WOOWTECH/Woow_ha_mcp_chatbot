"""OpenAI Compatible AI Service Provider."""

import logging
from typing import Any

from .openai import OpenAIService

_LOGGER = logging.getLogger(__name__)


class OpenAICompatibleService(OpenAIService):
    """OpenAI-compatible AI service provider for third-party services."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize OpenAI-compatible service."""
        # Ensure base_url is set for compatible services
        if not config.get("base_url"):
            raise ValueError("base_url is required for OpenAI-compatible services")
        super().__init__(config)

    @property
    def name(self) -> str:
        """Return the name of the AI service."""
        return f"OpenAI Compatible ({self._base_url})"
