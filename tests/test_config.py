"""Tests for the Clanker config system."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from clanker.config import (
    ClankerSettings,
    ProviderName,
    TaskType,
    load_settings,
)


def test_default_settings() -> None:
    """Loading with no YAML and no env produces sane defaults."""
    settings = ClankerSettings()

    assert settings.ha.url == "http://homeassistant.local:8123"
    assert settings.anthropic.model == "claude-sonnet-4-20250514"
    assert settings.ollama.base_url == "http://localhost:11434"
    assert settings.default_provider == ProviderName.ANTHROPIC
    assert settings.log_level == "INFO"
    assert settings.announce.quiet_hours.enabled is True
    assert settings.announce.quiet_hours.start_hour == 22
    assert settings.announce.quiet_hours.end_hour == 7


def test_load_from_yaml(tmp_path: Path) -> None:
    """Settings load correctly from a YAML file."""
    config_file = tmp_path / "clanker.yaml"
    config_file.write_text(
        dedent("""\
            ha:
              url: "http://192.168.1.100:8123"
            anthropic:
              model: "claude-opus-4-20250514"
              max_tokens: 8192
            log_level: DEBUG
            default_provider: ollama
            announce:
              quiet_hours:
                start_hour: 23
                end_hour: 8
        """)
    )

    settings = load_settings(config_file)

    assert settings.ha.url == "http://192.168.1.100:8123"
    assert settings.anthropic.model == "claude-opus-4-20250514"
    assert settings.anthropic.max_tokens == 8192
    assert settings.log_level == "DEBUG"
    assert settings.default_provider == ProviderName.OLLAMA
    assert settings.announce.quiet_hours.start_hour == 23
    assert settings.announce.quiet_hours.end_hour == 8


def test_load_missing_yaml() -> None:
    """Loading a nonexistent YAML file falls back to defaults."""
    settings = load_settings(Path("/nonexistent/clanker.yaml"))
    assert settings.ha.url == "http://homeassistant.local:8123"


def test_task_routes_default() -> None:
    """Default task routes are present and correctly typed."""
    settings = ClankerSettings()

    route_map = {r.task: r.provider for r in settings.task_routes}

    assert route_map[TaskType.VISION] == ProviderName.ANTHROPIC
    assert route_map[TaskType.REASONING] == ProviderName.ANTHROPIC
    assert route_map[TaskType.QUICK_INTENT] == ProviderName.OLLAMA
    assert route_map[TaskType.SUMMARIZATION] == ProviderName.OLLAMA
    assert route_map[TaskType.CONVERSATION] == ProviderName.ANTHROPIC


def test_room_speakers_from_yaml(tmp_path: Path) -> None:
    """Room-to-speaker mapping loads from YAML."""
    config_file = tmp_path / "clanker.yaml"
    config_file.write_text(
        dedent("""\
            announce:
              room_speakers:
                - room: kitchen
                  speaker_entity_ids:
                    - media_player.kitchen_nest
                    - media_player.kitchen_sonos
                - room: office
                  speaker_entity_ids:
                    - media_player.office_homepod
        """)
    )

    settings = load_settings(config_file)

    assert len(settings.announce.room_speakers) == 2
    assert settings.announce.room_speakers[0].room == "kitchen"
    assert len(settings.announce.room_speakers[0].speaker_entity_ids) == 2
    assert settings.announce.room_speakers[1].room == "office"
