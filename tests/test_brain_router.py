"""Tests for the brain router (task → provider selection)."""

from __future__ import annotations

import pytest

from clanker.brain.anthropic import AnthropicProvider
from clanker.brain.ollama import OllamaProvider
from clanker.brain.router import BrainRouter
from clanker.config import (
    ClankerSettings,
    ProviderName,
    TaskRoute,
    TaskType,
)


@pytest.fixture
def settings() -> ClankerSettings:
    """Create settings with known task routes."""
    return ClankerSettings(
        task_routes=[
            TaskRoute(task=TaskType.VISION, provider=ProviderName.ANTHROPIC),
            TaskRoute(task=TaskType.REASONING, provider=ProviderName.ANTHROPIC),
            TaskRoute(task=TaskType.QUICK_INTENT, provider=ProviderName.OLLAMA),
            TaskRoute(task=TaskType.SUMMARIZATION, provider=ProviderName.OLLAMA),
            TaskRoute(task=TaskType.CONVERSATION, provider=ProviderName.ANTHROPIC),
        ],
        default_provider=ProviderName.ANTHROPIC,
    )


def test_route_vision_to_anthropic(settings: ClankerSettings) -> None:
    """Vision tasks route to Anthropic."""
    router = BrainRouter(settings)
    provider = router.for_task(TaskType.VISION)
    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"


def test_route_quick_intent_to_ollama(settings: ClankerSettings) -> None:
    """Quick intent tasks route to Ollama."""
    router = BrainRouter(settings)
    provider = router.for_task(TaskType.QUICK_INTENT)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_route_summarization_to_ollama(settings: ClankerSettings) -> None:
    """Summarization tasks route to Ollama."""
    router = BrainRouter(settings)
    provider = router.for_task(TaskType.SUMMARIZATION)
    assert isinstance(provider, OllamaProvider)


def test_default_provider(settings: ClankerSettings) -> None:
    """Default provider is accessible."""
    router = BrainRouter(settings)
    provider = router.default
    assert isinstance(provider, AnthropicProvider)


def test_provider_caching(settings: ClankerSettings) -> None:
    """The same provider instance is reused across calls."""
    router = BrainRouter(settings)
    p1 = router.for_task(TaskType.VISION)
    p2 = router.for_task(TaskType.REASONING)
    # Both route to anthropic, should be the same instance
    assert p1 is p2


def test_custom_routes() -> None:
    """Custom task routes override defaults."""
    settings = ClankerSettings(
        task_routes=[
            TaskRoute(task=TaskType.VISION, provider=ProviderName.OLLAMA),
        ],
        default_provider=ProviderName.ANTHROPIC,
    )
    router = BrainRouter(settings)

    # Vision now goes to Ollama
    provider = router.for_task(TaskType.VISION)
    assert isinstance(provider, OllamaProvider)

    # Unrouted tasks fall back to default (Anthropic)
    provider = router.for_task(TaskType.CONVERSATION)
    assert isinstance(provider, AnthropicProvider)


async def test_close_providers(settings: ClankerSettings) -> None:
    """Close cleans up all provider instances."""
    router = BrainRouter(settings)
    _ = router.for_task(TaskType.VISION)
    _ = router.for_task(TaskType.QUICK_INTENT)

    await router.close()
    # After close, the providers dict should be empty
    assert len(router._providers) == 0
