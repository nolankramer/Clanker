"""Voice pipeline configuration helpers.

Auto-configures the HA voice pipeline (STT, TTS, conversation agent,
wake word) via the HA WebSocket and REST APIs.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


def install_ha_component(ha_config_dir: str) -> dict[str, Any]:
    """Copy the Clanker HA custom component into the HA config directory.

    Args:
        ha_config_dir: Path to HA's config directory (e.g. ~/homeassistant).

    Returns:
        Dict with ``ok`` and ``message``.
    """
    import shutil
    from pathlib import Path

    src = Path(__file__).parent.parent.parent / "ha_component" / "custom_components" / "clanker"
    dst = Path(ha_config_dir) / "custom_components" / "clanker"

    if not src.exists():
        return {"ok": False, "message": f"Component source not found: {src}"}

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return {"ok": True, "message": f"Installed to {dst}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def add_clanker_to_ha_config(
    ha_config_dir: str, clanker_url: str = "http://localhost:8472"
) -> dict[str, Any]:
    """Add the ``clanker:`` entry to HA's configuration.yaml.

    Args:
        ha_config_dir: Path to HA's config directory.
        clanker_url: URL where Clanker's conversation API is running.

    Returns:
        Dict with ``ok`` and ``message``.
    """
    from pathlib import Path

    config_path = Path(ha_config_dir) / "configuration.yaml"
    if not config_path.exists():
        return {"ok": False, "message": f"configuration.yaml not found in {ha_config_dir}"}

    content = config_path.read_text()
    if "clanker:" in content:
        return {"ok": True, "message": "Clanker already configured in configuration.yaml"}

    entry = f'\nclanker:\n  url: "{clanker_url}"\n'
    config_path.write_text(content + entry)
    return {"ok": True, "message": "Added clanker entry to configuration.yaml"}


def list_stt_engines(ha_url: str, token: str) -> list[dict[str, str]]:
    """List available STT engines in HA."""
    engines: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{ha_url.rstrip('/')}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for entity in resp.json():
                eid = entity.get("entity_id", "")
                if eid.startswith("stt."):
                    name = entity.get("attributes", {}).get("friendly_name", eid)
                    engines.append({"entity_id": eid, "name": name})
    except Exception:
        pass
    return engines


def list_tts_engines(ha_url: str, token: str) -> list[dict[str, str]]:
    """List available TTS engines in HA."""
    engines: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{ha_url.rstrip('/')}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for entity in resp.json():
                eid = entity.get("entity_id", "")
                if eid.startswith("tts."):
                    name = entity.get("attributes", {}).get("friendly_name", eid)
                    engines.append({"entity_id": eid, "name": name})
    except Exception:
        pass
    return engines


def list_wake_word_engines(ha_url: str, token: str) -> list[dict[str, str]]:
    """List available wake word engines in HA."""
    engines: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{ha_url.rstrip('/')}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for entity in resp.json():
                eid = entity.get("entity_id", "")
                if eid.startswith("wake_word."):
                    name = entity.get("attributes", {}).get("friendly_name", eid)
                    engines.append({"entity_id": eid, "name": name})
    except Exception:
        pass
    return engines


def check_voice_addons(ha_url: str, token: str) -> dict[str, bool]:
    """Check which voice-related integrations are available in HA."""
    result = {
        "whisper": False,
        "piper": False,
        "openwakeword": False,
        "clanker": False,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{ha_url.rstrip('/')}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            for entity in resp.json():
                eid = entity.get("entity_id", "")
                if "whisper" in eid:
                    result["whisper"] = True
                if "piper" in eid:
                    result["piper"] = True
                if "openwakeword" in eid:
                    result["openwakeword"] = True
                if eid.startswith("conversation.clanker"):
                    result["clanker"] = True
    except Exception:
        pass
    return result
