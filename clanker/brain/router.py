"""Brain router — maps task types to LLM providers based on config.

The router is the single entry point the rest of Clanker uses to get
an LLM provider. It reads the task_routes config and lazily initializes
provider instances on first use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from clanker.brain.anthropic import AnthropicProvider
from clanker.brain.base import LLMProvider
from clanker.brain.ollama import OllamaProvider
from clanker.brain.openai import OpenAIProvider
from clanker.config import ProviderName, TaskType

if TYPE_CHECKING:
    from clanker.config import ClankerSettings

logger = structlog.get_logger(__name__)


class BrainRouter:
    """Routes task types to the appropriate LLM provider.

    Providers are lazily initialized on first access. The routing
    table is built from ``ClankerSettings.task_routes``.
    """

    def __init__(self, settings: ClankerSettings) -> None:
        """Initialize the router from config.

        Args:
            settings: Full Clanker settings with provider configs and task routes.
        """
        self._settings = settings
        self._providers: dict[ProviderName, LLMProvider] = {}

        # Build routing table: task_type → provider_name
        self._routes: dict[TaskType, ProviderName] = {}
        for route in settings.task_routes:
            self._routes[route.task] = route.provider

        logger.info(
            "brain_router.init",
            routes={t.value: p.value for t, p in self._routes.items()},
            default=settings.default_provider.value,
        )

    def _create_provider(self, name: ProviderName) -> LLMProvider:
        """Create a provider instance by name.

        Args:
            name: Provider identifier.

        Returns:
            Initialized LLM provider.

        Raises:
            ValueError: If the provider name is unknown.
        """
        if name == ProviderName.ANTHROPIC:
            return AnthropicProvider(self._settings.anthropic)
        if name == ProviderName.OPENAI:
            return OpenAIProvider(self._settings.openai)
        if name == ProviderName.OLLAMA:
            return OllamaProvider(self._settings.ollama)
        if name == ProviderName.OPENAI_COMPAT:
            # OpenAI-compat uses the OpenAI provider with a custom base URL
            from clanker.config import OpenAIConfig

            compat = self._settings.openai_compat
            config = OpenAIConfig(
                api_key=compat.api_key,
                model=compat.model,
                max_tokens=compat.max_tokens,
                base_url=compat.base_url,
            )
            return OpenAIProvider(config)
        msg = f"Unknown provider: {name}"
        raise ValueError(msg)

    def get_provider(self, name: ProviderName) -> LLMProvider:
        """Get a provider by name, creating it lazily.

        Args:
            name: Provider identifier.

        Returns:
            LLM provider instance.
        """
        if name not in self._providers:
            self._providers[name] = self._create_provider(name)
            logger.info("brain_router.provider_created", provider=name.value)
        return self._providers[name]

    def for_task(self, task: TaskType) -> LLMProvider:
        """Get the provider configured for a specific task type.

        Falls back to the default provider if no route is defined.

        Args:
            task: The task type to route.

        Returns:
            LLM provider for this task.
        """
        provider_name = self._routes.get(task, self._settings.default_provider)
        logger.debug("brain_router.route", task=task.value, provider=provider_name.value)
        return self.get_provider(provider_name)

    @property
    def default(self) -> LLMProvider:
        """Get the default provider."""
        return self.get_provider(self._settings.default_provider)

    async def close(self) -> None:
        """Close all initialized providers."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
