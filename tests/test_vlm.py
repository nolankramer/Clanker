"""Tests for VLM providers."""

from __future__ import annotations

import pytest

from clanker.brain.base import LLMProvider
from clanker.vision.vlm import BrainVLM


class FakeVisionProvider(LLMProvider):
    """Minimal provider stub that supports vision."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def supports_vision(self) -> bool:
        return True

    async def chat(self, messages, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def stream(self, messages, **kwargs):  # type: ignore[override]
        raise NotImplementedError
        yield

    async def vision(
        self,
        prompt: str,
        image_data: bytes,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int | None = None,
    ) -> str:
        return f"described: {prompt}"


class FakeNoVisionProvider(LLMProvider):
    """Provider that does NOT support vision."""

    @property
    def name(self) -> str:
        return "no-vision"

    async def chat(self, messages, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def stream(self, messages, **kwargs):  # type: ignore[override]
        raise NotImplementedError
        yield


def test_brain_vlm_rejects_non_vision_provider() -> None:
    with pytest.raises(ValueError, match="does not support vision"):
        BrainVLM(FakeNoVisionProvider())


async def test_brain_vlm_describe() -> None:
    provider = FakeVisionProvider()
    vlm = BrainVLM(provider)

    result = await vlm.describe(b"\xff\xd8", "What is this?")
    assert result == "described: What is this?"


def test_brain_vlm_name() -> None:
    vlm = BrainVLM(FakeVisionProvider())
    assert vlm.name == "brain:fake"
