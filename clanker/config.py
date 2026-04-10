"""Configuration — pydantic Settings loaded from clanker.yaml + environment variables.

Environment variables override YAML values. Secrets (API keys, tokens) should
only be set via environment variables or .env, never in the YAML file.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskType(str, Enum):
    """Task categories for LLM routing."""

    VISION = "vision"
    REASONING = "reasoning"
    QUICK_INTENT = "quick_intent"
    SUMMARIZATION = "summarization"
    CONVERSATION = "conversation"


class ProviderName(str, Enum):
    """Supported LLM provider identifiers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    OPENAI_COMPAT = "openai_compat"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class HAConfig(BaseModel):
    """Home Assistant connection settings."""

    url: str = "http://homeassistant.local:8123"
    token: str = ""


class AnthropicConfig(BaseModel):
    """Anthropic provider settings."""

    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


class OpenAIConfig(BaseModel):
    """OpenAI provider settings."""

    api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 4096
    base_url: str | None = None


class OllamaConfig(BaseModel):
    """Ollama provider settings."""

    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    max_tokens: int = 4096


class OpenAICompatConfig(BaseModel):
    """Generic OpenAI-compatible endpoint (llama.cpp, vLLM, etc.)."""

    base_url: str = "http://localhost:8080/v1"
    api_key: str = ""
    model: str = "default"
    max_tokens: int = 4096


class TaskRoute(BaseModel):
    """Maps a task type to a provider."""

    task: TaskType
    provider: ProviderName


class MemoryConfig(BaseModel):
    """Memory system paths."""

    db_path: str = "data/clanker.db"
    markdown_dir: str = "config/memory"
    chromadb_path: str = "data/chroma"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = "http://localhost:11434"


class QuietHoursConfig(BaseModel):
    """Quiet hours — suppress non-critical TTS announcements."""

    enabled: bool = True
    start_hour: int = Field(default=22, ge=0, le=23)
    end_hour: int = Field(default=7, ge=0, le=23)


class RoomSpeaker(BaseModel):
    """Maps a room name to its media_player entity IDs."""

    room: str
    speaker_entity_ids: list[str]


class OccupancySensor(BaseModel):
    """Maps a room to its occupancy sensor entity ID."""

    room: str
    sensor_entity_id: str


class AnnounceConfig(BaseModel):
    """Announcement routing settings."""

    quiet_hours: QuietHoursConfig = QuietHoursConfig()
    room_speakers: list[RoomSpeaker] = []
    occupancy_sensors: list[OccupancySensor] = []
    fallback_push_targets: list[str] = Field(
        default_factory=list,
        description="mobile_app entity IDs for push fallback when no one is home",
    )
    tts_service: str = "tts.speak"


class FrigateConfig(BaseModel):
    """Frigate NVR connection settings."""

    enabled: bool = False
    url: str = "http://localhost:5000"
    cooldown_seconds: float = 30.0
    min_score: float = 0.6
    cameras: list[str] = Field(
        default_factory=list,
        description="Camera names to monitor (empty = all)",
    )


class ConversationConfig(BaseModel):
    """Conversation agent / voice pipeline settings."""

    host: str = "0.0.0.0"
    port: int = 8472
    system_prompt: str = ""
    session_ttl_seconds: float = 600.0
    tts_engine: str = ""
    tts_voice: str = ""
    stt_engine: str = ""


class ProactiveConfig(BaseModel):
    """Proactive automation settings."""

    morning_briefing_after_hour: int = Field(default=6, ge=0, le=23)
    briefing_motion_sensor: str = ""
    briefing_speaker: str = ""


class TelegramConfig(BaseModel):
    """Telegram bot settings."""

    enabled: bool = False
    bot_token: str = ""
    chat_ids: list[int] = Field(
        default_factory=list,
        description="Allowed Telegram chat IDs for notifications and control",
    )


class SMSConfig(BaseModel):
    """SMS via Twilio settings."""

    enabled: bool = False
    account_sid: str = ""
    auth_token: str = ""
    from_number: str = ""
    to_numbers: list[str] = Field(
        default_factory=list,
        description="Phone numbers to send alerts to (E.164 format: +1234567890)",
    )


class RemoteConfig(BaseModel):
    """Remote access settings."""

    telegram: TelegramConfig = TelegramConfig()
    sms: SMSConfig = SMSConfig()
    allowed_actions: list[str] = Field(
        default_factory=lambda: ["check_cameras", "get_state", "notify"],
        description="Actions permitted via remote chat surface",
    )


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML config file, returning an empty dict if missing."""
    if not path.exists():
        return {}
    with path.open() as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


class ClankerSettings(BaseSettings):
    """Root configuration for Clanker.

    Values are loaded in order of precedence (highest first):
    1. Environment variables (prefixed with CLANKER_)
    2. .env file
    3. config/clanker.yaml
    4. Defaults defined here
    """

    model_config = SettingsConfigDict(
        env_prefix="CLANKER_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configs
    ha: HAConfig = HAConfig()
    anthropic: AnthropicConfig = AnthropicConfig()
    openai: OpenAIConfig = OpenAIConfig()
    ollama: OllamaConfig = OllamaConfig()
    openai_compat: OpenAICompatConfig = OpenAICompatConfig()

    # Task routing — which provider handles which task type
    task_routes: list[TaskRoute] = Field(
        default_factory=lambda: [
            TaskRoute(task=TaskType.VISION, provider=ProviderName.ANTHROPIC),
            TaskRoute(task=TaskType.REASONING, provider=ProviderName.ANTHROPIC),
            TaskRoute(task=TaskType.QUICK_INTENT, provider=ProviderName.OLLAMA),
            TaskRoute(task=TaskType.SUMMARIZATION, provider=ProviderName.OLLAMA),
            TaskRoute(task=TaskType.CONVERSATION, provider=ProviderName.ANTHROPIC),
        ]
    )

    # Default provider when no task route matches
    default_provider: ProviderName = ProviderName.ANTHROPIC

    memory: MemoryConfig = MemoryConfig()
    announce: AnnounceConfig = AnnounceConfig()
    conversation: ConversationConfig = ConversationConfig()
    frigate: FrigateConfig = FrigateConfig()
    proactive: ProactiveConfig = ProactiveConfig()
    remote: RemoteConfig = RemoteConfig()

    # Logging
    log_level: str = "INFO"
    log_json: bool = False


def load_settings(config_path: Path | None = None) -> ClankerSettings:
    """Load settings from YAML config file + environment.

    Args:
        config_path: Path to the YAML config file. Defaults to ``config/clanker.yaml``.

    Returns:
        Fully resolved ``ClankerSettings`` instance.
    """
    if config_path is None:
        config_path = Path("config/clanker.yaml")

    yaml_data = _load_yaml(config_path)

    return ClankerSettings(**yaml_data)
