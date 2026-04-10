"""Interactive CLI setup wizard for Clanker.

Usage::

    clanker-setup          # CLI wizard
    clanker-setup --web    # launch web wizard instead
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Any

from clanker.setup.wizard import (
    discover_entities,
    generate_config,
    generate_env,
    infer_rooms,
    save_config,
    test_anthropic,
    test_frigate,
    test_ha,
    test_ollama,
    test_openai,
)

# ------------------------------------------------------------------
# ANSI helpers
# ------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"  {_GREEN}✓{_RESET} {msg}"


def _fail(msg: str) -> str:
    return f"  {_RED}✗{_RESET} {msg}"


def _header(step: int, title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}Step {step}: {title}{_RESET}")
    print(f"{_DIM}{'─' * 50}{_RESET}")


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"  {label}{suffix}: ").strip()
    return value or default


def _secret(label: str) -> str:
    return getpass.getpass(f"  {label}: ").strip()


def _confirm(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input(f"  {label} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value.startswith("y")


# ------------------------------------------------------------------
# Steps
# ------------------------------------------------------------------


def _step_ha(answers: dict[str, Any]) -> bool:
    _header(1, "Home Assistant")
    answers["ha_url"] = _prompt("HA URL", "http://localhost:8123")
    answers["ha_token"] = _secret("Long-lived access token")
    if not answers["ha_token"]:
        print(_fail("Token is required"))
        return False

    print("  Testing connection...")
    result = test_ha(answers["ha_url"], answers["ha_token"])
    if result["ok"]:
        print(_ok(result["message"]))
        return True
    print(_fail(result["message"]))
    return _confirm("Continue anyway?", default=False)


def _step_providers(answers: dict[str, Any]) -> None:
    _header(2, "LLM Providers")

    # Anthropic
    if _confirm("Enable Anthropic (Claude)?", default=True):
        answers["anthropic_enabled"] = True
        answers["anthropic_key"] = _secret("Anthropic API key")
        if answers["anthropic_key"]:
            print("  Testing...")
            r = test_anthropic(answers["anthropic_key"])
            print(_ok(r["message"]) if r["ok"] else _fail(r["message"]))
        answers["anthropic_model"] = _prompt("Model", "claude-sonnet-4-20250514")

    # OpenAI
    if _confirm("Enable OpenAI?", default=False):
        answers["openai_enabled"] = True
        answers["openai_key"] = _secret("OpenAI API key")
        if answers["openai_key"]:
            print("  Testing...")
            r = test_openai(answers["openai_key"])
            print(_ok(r["message"]) if r["ok"] else _fail(r["message"]))
        answers["openai_model"] = _prompt("Model", "gpt-4o")

    # Ollama
    if _confirm("Enable Ollama (local)?", default=True):
        answers["ollama_enabled"] = True
        answers["ollama_url"] = _prompt("Ollama URL", "http://localhost:11434")
        print("  Testing...")
        r = test_ollama(answers["ollama_url"])
        if r["ok"]:
            print(_ok(r["message"]))
            models = r.get("models", [])
            default_model = models[0] if models else "llama3.2"
            answers["ollama_model"] = _prompt("Model", default_model)
        else:
            print(_fail(r["message"]))
            answers["ollama_model"] = _prompt("Model", "llama3.2")


def _step_routing(answers: dict[str, Any]) -> None:
    _header(3, "Task Routing")
    providers = []
    if answers.get("anthropic_enabled"):
        providers.append("anthropic")
    if answers.get("openai_enabled"):
        providers.append("openai")
    if answers.get("ollama_enabled"):
        providers.append("ollama")

    if not providers:
        print(_fail("No providers configured — skipping routing"))
        return

    print(f"  Available providers: {', '.join(providers)}")
    default = providers[0]
    local = "ollama" if "ollama" in providers else default

    routes: dict[str, str] = {}
    tasks = [
        ("vision", default, "Vision (image analysis)"),
        ("reasoning", default, "Reasoning (complex tasks)"),
        ("quick_intent", local, "Quick intents (lights, etc.)"),
        ("summarization", local, "Summarization"),
        ("conversation", default, "Conversation"),
    ]
    for task, task_default, label in tasks:
        routes[task] = _prompt(f"{label}", task_default)

    answers["task_routes"] = routes
    answers["default_provider"] = _prompt("Default provider", default)


def _step_frigate(answers: dict[str, Any]) -> None:
    _header(4, "Frigate (Camera Detection)")
    if not _confirm("Enable Frigate?", default=False):
        answers["frigate_enabled"] = False
        return

    answers["frigate_enabled"] = True
    answers["frigate_url"] = _prompt("Frigate URL", "http://localhost:5000")
    print("  Testing...")
    r = test_frigate(answers["frigate_url"])
    print(_ok(r["message"]) if r["ok"] else _fail(r["message"]))


def _step_discovery(answers: dict[str, Any]) -> None:
    _header(5, "Entity Discovery")
    if not answers.get("ha_token"):
        print(f"  {_DIM}Skipping — no HA connection{_RESET}")
        return

    print("  Discovering HA entities...")
    entities = discover_entities(answers["ha_url"], answers["ha_token"])

    speakers = entities.get("speakers", [])
    occ = entities.get("occupancy_sensors", [])
    notify = entities.get("notify_services", [])
    rooms = infer_rooms(entities)

    if speakers:
        print(f"  {_GREEN}Found {len(speakers)} speaker(s){_RESET}")
        for s in speakers[:10]:
            print(f"    • {s['entity_id']} ({s['name']})")
    if occ:
        print(f"  {_GREEN}Found {len(occ)} occupancy sensor(s){_RESET}")
    if rooms:
        print(f"  {_GREEN}Inferred rooms: {', '.join(rooms)}{_RESET}")

    # Build room-speaker mappings
    room_speakers: list[dict[str, Any]] = []
    for room in rooms:
        matched = [
            s["entity_id"] for s in speakers if room in s["entity_id"]
        ]
        if matched:
            room_speakers.append({"room": room, "speaker_entity_ids": matched})
    answers["room_speakers"] = room_speakers

    # Occupancy sensors
    occ_sensors: list[dict[str, str]] = []
    for room in rooms:
        matched = [s["entity_id"] for s in occ if room in s["entity_id"]]
        if matched:
            occ_sensors.append({"room": room, "sensor_entity_id": matched[0]})
    answers["occupancy_sensors"] = occ_sensors

    # Push targets
    if notify:
        mobile = [n for n in notify if "mobile" in n["entity_id"]]
        answers["push_targets"] = [m["entity_id"] for m in mobile[:2]]


def _step_save(answers: dict[str, Any]) -> None:
    _header(6, "Save Configuration")
    yaml_content = generate_config(answers)
    env_content = generate_env(answers)

    print(f"\n{_DIM}--- config/clanker.yaml ---{_RESET}")
    for line in yaml_content.splitlines()[:20]:
        print(f"  {_DIM}{line}{_RESET}")
    if yaml_content.count("\n") > 20:
        print(f"  {_DIM}... ({yaml_content.count(chr(10))} lines total){_RESET}")

    print(f"\n{_DIM}--- .env ---{_RESET}")
    for line in env_content.splitlines():
        if "KEY" in line or "TOKEN" in line:
            key, _, _ = line.partition("=")
            print(f"  {_DIM}{key}=****{_RESET}")
        else:
            print(f"  {_DIM}{line}{_RESET}")

    if not _confirm("\nWrite these files?", default=True):
        print("  Aborted.")
        return

    paths = save_config(yaml_content, env_content)
    print(_ok(f"Wrote {paths['yaml']}"))
    print(_ok(f"Wrote {paths['env']}"))
    print(f"\n{_BOLD}{_GREEN}Setup complete!{_RESET}")
    print(f"  Run: {_CYAN}python -m clanker.main{_RESET}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> None:
    """Entry point for ``clanker-setup``."""
    parser = argparse.ArgumentParser(description="Clanker setup wizard")
    parser.add_argument(
        "--web", action="store_true", help="Launch the web-based setup wizard"
    )
    parser.add_argument(
        "--port", type=int, default=8471, help="Port for web wizard (default: 8471)"
    )
    args = parser.parse_args()

    if args.web:
        from clanker.setup.web import run_server

        run_server(port=args.port)
        return

    print(f"\n{_BOLD}{_CYAN}╔══════════════════════════════════════╗{_RESET}")
    print(f"{_BOLD}{_CYAN}║       Clanker Setup Wizard           ║{_RESET}")
    print(f"{_BOLD}{_CYAN}╚══════════════════════════════════════╝{_RESET}")
    print(f"{_DIM}  Interactive setup for your smart home brain{_RESET}\n")

    answers: dict[str, Any] = {}

    try:
        if not _step_ha(answers) and not _confirm("Continue without HA?", default=False):
            sys.exit(1)
        _step_providers(answers)
        _step_routing(answers)
        _step_frigate(answers)
        _step_discovery(answers)
        _step_save(answers)
    except KeyboardInterrupt:
        print(f"\n{_DIM}  Cancelled.{_RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
