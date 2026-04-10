"""Config validation with actionable error messages.

Checks the generated config for common mistakes before saving,
and validates a running Clanker instance for health.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def validate_config(answers: dict[str, Any]) -> list[str]:
    """Validate wizard answers and return a list of issues.

    Returns:
        List of human-readable warning/error strings. Empty = all good.
    """
    issues: list[str] = []

    # HA URL
    ha_url = answers.get("ha_url", "")
    if not ha_url:
        issues.append("Home Assistant URL is required.")
    elif not ha_url.startswith(("http://", "https://")):
        issues.append(f"HA URL should start with http:// or https:// (got: {ha_url})")

    # HA Token
    if not answers.get("ha_token"):
        issues.append("Home Assistant access token is required.")

    # At least one provider
    has_provider = any(
        answers.get(f"{p}_enabled")
        for p in ("anthropic", "openai", "ollama")
    )
    if not has_provider:
        issues.append("At least one LLM provider must be enabled.")

    # Anthropic key format
    if answers.get("anthropic_enabled") and answers.get("anthropic_key"):
        key = answers["anthropic_key"]
        if not key.startswith("sk-ant-"):
            issues.append(
                "Anthropic API key should start with 'sk-ant-'. "
                "Check that you copied the full key."
            )

    # Ollama URL
    if answers.get("ollama_enabled"):
        url = answers.get("ollama_url", "")
        if not url.startswith(("http://", "https://")):
            issues.append(f"Ollama URL should be a valid HTTP URL (got: {url})")

    # Conversation port
    port = answers.get("conversation_port", 8472)
    if isinstance(port, int) and (port < 1024 or port > 65535):
        issues.append(
            f"Conversation API port {port} is outside valid range (1024-65535)."
        )

    # Telegram
    if answers.get("telegram_enabled"):
        if not answers.get("telegram_token"):
            issues.append("Telegram bot token is required when Telegram is enabled.")
        if not answers.get("telegram_chat_ids"):
            issues.append(
                "At least one verified Telegram chat ID is required. "
                "Run the verification flow again."
            )

    # SMS phone numbers
    if answers.get("sms_enabled"):
        e164 = re.compile(r"^\+[1-9]\d{6,14}$")
        from_num = answers.get("sms_from", "")
        if not e164.match(from_num):
            issues.append(
                f"Twilio phone number '{from_num}' is not valid E.164 format. "
                "Should be like +15551234567."
            )
        for num in answers.get("sms_to_numbers", []):
            if not e164.match(num):
                issues.append(
                    f"Phone number '{num}' is not valid E.164 format. "
                    "Should be like +15551234567."
                )

    # Frigate URL
    if answers.get("frigate_enabled"):
        furl = answers.get("frigate_url", "")
        if not furl.startswith(("http://", "https://")):
            issues.append(f"Frigate URL should be a valid HTTP URL (got: {furl})")

    return issues


def validate_files() -> list[str]:
    """Check that required config files exist and are readable."""
    issues: list[str] = []

    config_path = Path("config/clanker.yaml")
    if not config_path.exists():
        issues.append(
            "config/clanker.yaml not found. "
            "Run 'clanker-setup' or copy config/clanker.yaml.example."
        )

    env_path = Path(".env")
    if not env_path.exists():
        issues.append(
            ".env file not found. "
            "Run 'clanker-setup' or copy .env.example."
        )
    elif env_path.exists():
        content = env_path.read_text()
        if "CLANKER_HA__TOKEN=" not in content or "CLANKER_HA__TOKEN=\n" in content:
            issues.append(
                "CLANKER_HA__TOKEN is missing or empty in .env. "
                "Set your Home Assistant long-lived access token."
            )

    data_dir = Path("data")
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    return issues
