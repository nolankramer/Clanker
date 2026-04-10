"""VLM (Vision Language Model) provider abstraction.

Routes vision tasks to different backends — cloud (Claude, GPT-4o) or
local (Ollama multimodal models like LLaVA, Qwen2-VL).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from clanker.brain.base import LLMProvider

logger = structlog.get_logger(__name__)


class VLMProvider(ABC):
    """Abstract base for vision-language model providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    async def describe(
        self,
        image: bytes,
        prompt: str,
        *,
        media_type: str = "image/jpeg",
    ) -> str:
        """Describe an image given a text prompt.

        Args:
            image: Raw image bytes.
            prompt: Text prompt to accompany the image.
            media_type: MIME type of the image.

        Returns:
            Natural-language description.
        """


class BrainVLM(VLMProvider):
    """VLM backed by any brain :class:`LLMProvider` that supports vision.

    This is the primary implementation — it delegates to whichever brain
    provider is configured for vision tasks (e.g. Claude, GPT-4o, or a
    local multimodal Ollama model).
    """

    def __init__(self, provider: LLMProvider) -> None:
        if not provider.supports_vision:
            msg = f"Provider {provider.name} does not support vision"
            raise ValueError(msg)
        self._provider = provider

    @property
    def name(self) -> str:
        return f"brain:{self._provider.name}"

    async def describe(
        self,
        image: bytes,
        prompt: str,
        *,
        media_type: str = "image/jpeg",
    ) -> str:
        logger.debug(
            "vlm.describe", provider=self._provider.name, prompt_len=len(prompt)
        )
        return await self._provider.vision(prompt, image, media_type=media_type)
