"""Shared setup logic — connection testing, entity discovery, config generation.

Used by both the CLI and web setup wizards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml

# ------------------------------------------------------------------
# Connection testers
# ------------------------------------------------------------------


def test_ha(url: str, token: str) -> dict[str, Any]:
    """Test Home Assistant connection via its REST API."""
    result: dict[str, Any] = {"ok": False, "message": "", "ha_version": ""}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{url.rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 401:
                result["message"] = "Invalid access token"
                return result
            resp.raise_for_status()
            data = resp.json()
            result["ha_version"] = data.get("version", "unknown")
            result["ok"] = True
            result["message"] = f"Connected — HA {result['ha_version']}"
    except httpx.ConnectError:
        result["message"] = f"Cannot connect to {url}"
    except Exception as exc:
        result["message"] = str(exc)
    return result


def test_anthropic(api_key: str) -> dict[str, Any]:
    """Validate an Anthropic API key."""
    result: dict[str, Any] = {"ok": False, "message": ""}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if resp.status_code in (401, 403):
                result["message"] = "Invalid API key"
                return result
            resp.raise_for_status()
            result["ok"] = True
            result["message"] = "API key valid"
    except httpx.ConnectError:
        result["message"] = "Cannot reach api.anthropic.com"
    except Exception as exc:
        result["message"] = str(exc)
    return result


def test_openai(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Validate an OpenAI (or compatible) API key."""
    result: dict[str, Any] = {"ok": False, "message": ""}
    url = (base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code in (401, 403):
                result["message"] = "Invalid API key"
                return result
            resp.raise_for_status()
            result["ok"] = True
            result["message"] = "API key valid"
    except httpx.ConnectError:
        result["message"] = f"Cannot connect to {url}"
    except Exception as exc:
        result["message"] = str(exc)
    return result


def test_ollama(base_url: str) -> dict[str, Any]:
    """Test Ollama connection and list installed models."""
    result: dict[str, Any] = {"ok": False, "message": "", "models": []}
    url = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            result["models"] = models
            result["ok"] = True
            if models:
                result["message"] = f"Connected — {len(models)} model(s): {', '.join(models[:5])}"
            else:
                result["message"] = "Connected but no models. Run: ollama pull llama3.2"
    except httpx.ConnectError:
        result["message"] = f"Cannot connect to {url}. Is Ollama running?"
    except Exception as exc:
        result["message"] = str(exc)
    return result


def test_frigate(url: str) -> dict[str, Any]:
    """Test Frigate connection and list cameras."""
    result: dict[str, Any] = {"ok": False, "message": "", "cameras": []}
    base = url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base}/api/config")
            resp.raise_for_status()
            data = resp.json()
            cameras = list(data.get("cameras", {}).keys())
            result["cameras"] = cameras
            result["ok"] = True
            result["message"] = f"Connected — {len(cameras)} camera(s): {', '.join(cameras)}"
    except httpx.ConnectError:
        result["message"] = f"Cannot connect to {url}. Is Frigate running?"
    except Exception as exc:
        result["message"] = str(exc)
    return result


# ------------------------------------------------------------------
# Entity discovery
# ------------------------------------------------------------------


def discover_entities(url: str, token: str) -> dict[str, list[dict[str, str]]]:
    """Discover HA entities relevant to Clanker (speakers, sensors, etc.)."""
    found: dict[str, list[dict[str, str]]] = {
        "speakers": [],
        "occupancy_sensors": [],
        "motion_sensors": [],
        "lights": [],
        "cameras": [],
        "notify_services": [],
    }
    try:
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=15.0) as client:
            # Entity states
            resp = client.get(f"{url.rstrip('/')}/api/states", headers=headers)
            resp.raise_for_status()
            for entity in resp.json():
                eid: str = entity.get("entity_id", "")
                name: str = entity.get("attributes", {}).get("friendly_name", eid)
                entry = {"entity_id": eid, "name": name}

                if eid.startswith("media_player."):
                    found["speakers"].append(entry)
                elif eid.startswith("binary_sensor.") and "occupancy" in eid:
                    found["occupancy_sensors"].append(entry)
                elif eid.startswith("binary_sensor.") and "motion" in eid:
                    found["motion_sensors"].append(entry)
                elif eid.startswith("light."):
                    found["lights"].append(entry)
                elif eid.startswith("camera."):
                    found["cameras"].append(entry)

            # Notify services
            resp = client.get(f"{url.rstrip('/')}/api/services", headers=headers)
            if resp.status_code == 200:
                for svc in resp.json():
                    if svc.get("domain") == "notify":
                        for name in svc.get("services", {}):
                            found["notify_services"].append(
                                {"entity_id": f"notify.{name}", "name": name}
                            )
    except Exception:
        pass

    return found


# ------------------------------------------------------------------
# Room inference
# ------------------------------------------------------------------


def infer_rooms(entities: dict[str, list[dict[str, str]]]) -> list[str]:
    """Guess room names from entity IDs."""
    rooms: set[str] = set()
    skip = {
        "media", "player", "binary", "sensor", "light", "camera",
        "all", "group", "home", "assistant",
    }
    for category in ("speakers", "occupancy_sensors", "motion_sensors"):
        for ent in entities.get(category, []):
            parts = ent["entity_id"].split(".", 1)[-1].rsplit("_", 1)
            # e.g. "living_room_speaker" → take everything before last known suffix
            candidate = parts[0] if len(parts) > 1 else ent["entity_id"].split(".", 1)[-1]
            # Strip common suffixes
            for suffix in ("speaker", "occupancy", "motion", "sensor", "light", "display"):
                candidate = candidate.removesuffix(f"_{suffix}")
            tokens = set(candidate.split("_"))
            if not tokens & skip and candidate:
                rooms.add(candidate)
    return sorted(rooms)


# ------------------------------------------------------------------
# Config generation
# ------------------------------------------------------------------


def generate_config(answers: dict[str, Any]) -> str:
    """Build ``clanker.yaml`` content from wizard answers."""
    cfg: dict[str, Any] = {}

    # HA
    cfg["ha"] = {"url": answers.get("ha_url", "http://localhost:8123")}

    # Providers (keys go in .env, not yaml)
    if answers.get("anthropic_enabled"):
        cfg["anthropic"] = {
            "model": answers.get("anthropic_model", "claude-sonnet-4-20250514"),
            "max_tokens": 4096,
        }
    if answers.get("openai_enabled"):
        cfg["openai"] = {
            "model": answers.get("openai_model", "gpt-4o"),
            "max_tokens": 4096,
        }
    if answers.get("ollama_enabled"):
        cfg["ollama"] = {
            "base_url": answers.get("ollama_url", "http://localhost:11434"),
            "model": answers.get("ollama_model", "llama3.2"),
            "max_tokens": 4096,
        }

    # Task routing
    routes = answers.get("task_routes", {})
    if routes:
        cfg["task_routes"] = [
            {"task": task, "provider": provider} for task, provider in routes.items()
        ]
    cfg["default_provider"] = answers.get("default_provider", "anthropic")

    # Memory
    cfg["memory"] = {
        "db_path": "data/clanker.db",
        "markdown_dir": "config/memory",
        "chromadb_path": "data/chroma",
    }

    # Frigate
    if answers.get("frigate_enabled"):
        cfg["frigate"] = {
            "enabled": True,
            "url": answers.get("frigate_url", "http://localhost:5000"),
        }

    # Announcements
    room_speakers = answers.get("room_speakers", [])
    occupancy_sensors = answers.get("occupancy_sensors", [])
    if room_speakers or occupancy_sensors:
        cfg["announce"] = {}
        if room_speakers:
            cfg["announce"]["room_speakers"] = room_speakers
        if occupancy_sensors:
            cfg["announce"]["occupancy_sensors"] = occupancy_sensors
        push = answers.get("push_targets", [])
        if push:
            cfg["announce"]["fallback_push_targets"] = push

    # Logging
    cfg["log_level"] = "INFO"

    return yaml.dump(cfg, default_flow_style=False, sort_keys=False)


def generate_env(answers: dict[str, Any]) -> str:
    """Build ``.env`` content from wizard answers."""
    lines: list[str] = ["# Generated by clanker-setup\n"]

    if answers.get("ha_token"):
        lines.append(f"CLANKER_HA__TOKEN={answers['ha_token']}")
    if answers.get("anthropic_key"):
        lines.append(f"CLANKER_ANTHROPIC__API_KEY={answers['anthropic_key']}")
    if answers.get("openai_key"):
        lines.append(f"CLANKER_OPENAI__API_KEY={answers['openai_key']}")

    lines.append("")
    return "\n".join(lines)


def save_config(
    yaml_content: str,
    env_content: str,
    config_dir: Path = Path("config"),
    project_dir: Path = Path("."),
) -> dict[str, str]:
    """Write config and env files.  Returns paths written."""
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "clanker.yaml"
    env_path = project_dir / ".env"

    yaml_path.write_text(yaml_content)
    env_path.write_text(env_content)

    return {"yaml": str(yaml_path), "env": str(env_path)}
