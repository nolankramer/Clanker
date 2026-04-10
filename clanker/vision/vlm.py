"""VLM (Vision Language Model) provider abstraction.

Supports routing vision tasks to different backends:
- Claude (high quality, cloud)
- Local VLM (LLaVA, Qwen2-VL via Ollama — private, lower cost)

TODO:
- Define VLMProvider ABC with describe(image, prompt) method
- Implement Anthropic VLM using the brain's Anthropic provider
- Implement local VLM via Ollama multimodal models
- Add caching to avoid re-describing the same snapshot
"""

from __future__ import annotations


# TODO: Implement VLMProvider ABC and implementations
# class VLMProvider(ABC):
#     async def describe(self, image: bytes, prompt: str) -> str: ...
