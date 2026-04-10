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

from clanker.setup.discovery import quick_discover
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

    # Auto-discovery
    print("  Scanning for Home Assistant...")
    discovered = quick_discover(timeout=3.0)
    if discovered:
        print(_ok(f"Found HA at {discovered['url']}"))
        if _confirm(f"Use {discovered['url']}?", default=True):
            answers["ha_url"] = discovered["url"]
        else:
            answers["ha_url"] = _prompt("HA URL", discovered["url"])
    else:
        print(f"  {_DIM}No HA instance found automatically{_RESET}")
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

        from clanker.setup.ollama import (
            _RECOMMENDED_MODELS,
            get_optimization_advice,
            install_ollama,
            is_ollama_installed,
            pull_model,
        )

        # Auto-install if missing
        if not is_ollama_installed():
            print(f"  {_DIM}Ollama not found.{_RESET}")
            if _confirm("Install Ollama automatically?", default=True):
                print("  Installing Ollama...")
                r = install_ollama()
                print(_ok(r["message"]) if r["ok"] else _fail(r["message"]))

        answers["ollama_url"] = _prompt("Ollama URL", "http://localhost:11434")
        print("  Testing...")
        r = test_ollama(answers["ollama_url"])
        if r["ok"]:
            print(_ok(r["message"]))
            models = r.get("models", [])
            installed_names = {m.split(":")[0] for m in models}

            # Offer to pull recommended models
            if not models or _confirm("Pull recommended models?"):
                for _key, rec in _RECOMMENDED_MODELS.items():
                    name = rec["model"].split(":")[0]
                    if name in installed_names:
                        print(_ok(f"{rec['model']} ({rec['description']})"))
                    else:
                        if _confirm(
                            f"  Pull {rec['model']}? "
                            f"({rec['description']}, {rec['size']})"
                        ):
                            print(f"  Pulling {rec['model']}...")
                            pr = pull_model(rec["model"])
                            if pr["ok"]:
                                print(_ok(f"Pulled {rec['model']}"))
                            else:
                                print(_fail(pr["message"]))

            # Re-check models after pulling
            r2 = test_ollama(answers["ollama_url"])
            models = r2.get("models", []) if r2["ok"] else models
            default_model = models[0] if models else "llama3.2"
            answers["ollama_model"] = _prompt("Model", default_model)
        else:
            print(_fail(r["message"]))
            answers["ollama_model"] = _prompt("Model", "llama3.2")

        # Optimization advice
        print(f"\n  {_BOLD}Optimization for voice assistant:{_RESET}")
        advice = get_optimization_advice()
        for tip in advice["tips"]:
            print(f"  {_DIM}- {tip}{_RESET}")
        answers["ollama_options"] = advice["options"]
        answers["ollama_env"] = advice["env"]

        if _confirm("\n  Apply Ollama optimizations? (requires sudo)"):
            from clanker.setup.ollama import apply_systemd_env

            ar = apply_systemd_env(advice["env"])
            print(_ok(ar["message"]) if ar["ok"] else _fail(ar["message"]))


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


def _step_voice(answers: dict[str, Any]) -> None:
    _header(6, "Voice Pipeline")
    print(f"  {_DIM}Configure how 'Hey Clanker' voice control works.{_RESET}\n")

    # HA component installation
    if answers.get("ha_token"):
        ha_config_dir = _prompt(
            "HA config directory (for custom component install)",
            "/config" if _confirm("Is HA running in Docker?", default=True) else "~/homeassistant",
        )
        answers["ha_config_dir"] = ha_config_dir

        from clanker.setup.voice import check_voice_addons

        print("  Checking voice add-ons...")
        addons = check_voice_addons(answers["ha_url"], answers["ha_token"])
        if addons["whisper"]:
            print(_ok("Whisper STT detected"))
        else:
            print(f"  {_YELLOW}!{_RESET} Whisper not found - install the Whisper add-on")
        if addons["piper"]:
            print(_ok("Piper TTS detected"))
        else:
            print(f"  {_YELLOW}!{_RESET} Piper not found — install the Piper add-on for local TTS")
        if addons["openwakeword"]:
            print(_ok("openWakeWord detected"))
        else:
            print(f"  {_YELLOW}!{_RESET} openWakeWord not found - install for wake word")

    # Conversation API
    answers["conversation_port"] = int(
        _prompt("Conversation API port", "8472")
    )

    # TTS
    if _confirm("Configure TTS (text-to-speech)?", default=True):
        answers["tts_engine"] = _prompt("TTS engine entity", "tts.piper")
        answers["tts_voice"] = _prompt("TTS voice (blank for default)", "")

    # Wake word training
    print(f"\n  {_DIM}To train the 'Hey Clanker' wake word:{_RESET}")
    print(f"  {_DIM}  pip install openwakeword tensorflow{_RESET}")
    print(f"  {_DIM}  python -m clanker.setup.wakeword{_RESET}")
    print(f"  {_DIM}  python -m clanker.setup.wakeword --deploy /share/openwakeword{_RESET}")


def _step_notifications(answers: dict[str, Any]) -> None:
    _header(7, "Remote Notifications")
    print(f"  {_BOLD}Choose a notification platform:{_RESET}\n")
    print(f"  {_CYAN}1{_RESET}  Telegram (recommended — images, buttons, chat)")
    print(f"  {_CYAN}2{_RESET}  SMS via Twilio (universal — requires Twilio account)")
    print(f"  {_CYAN}3{_RESET}  Both")
    print(f"  {_CYAN}4{_RESET}  Skip (HA push only)")
    print()

    choice = _prompt("Choice", "1")

    if choice in ("1", "3"):
        _setup_telegram(answers)
    if choice in ("2", "3"):
        _setup_sms(answers)


def _setup_telegram(answers: dict[str, Any]) -> None:
    print(f"\n  {_BOLD}Telegram Setup{_RESET}")
    if not _confirm("  Set up Telegram?"):
        return

    print(f"\n  {_DIM}1. Open Telegram and message @BotFather{_RESET}")
    print(f"  {_DIM}2. Send /newbot and follow the prompts{_RESET}")
    print(f"  {_DIM}3. Copy the bot token below{_RESET}\n")

    bot_token = _secret("Bot token from @BotFather")
    if not bot_token:
        return

    from clanker.remote.chat import get_bot_info, get_chat_id

    print("  Verifying token...")
    info = get_bot_info(bot_token)
    if not info["ok"]:
        print(_fail(info.get("message", "Invalid token")))
        return

    print(_ok(f"Bot verified: @{info['username']}"))
    answers["telegram_token"] = bot_token

    print(f"\n  Now send any message to @{info['username']} on Telegram.")
    print(f"  {_DIM}Waiting for your message (60s timeout)...{_RESET}")

    result = get_chat_id(bot_token, timeout=60.0)
    if not result["ok"]:
        print(_fail("No message received. Enter your chat ID manually:"))
        manual = _prompt("Chat ID")
        if manual:
            result = {"ok": True, "chat_id": int(manual), "username": "", "first_name": ""}
        else:
            return

    chat_id = result["chat_id"]
    username = result.get("username", "")
    first_name = result.get("first_name", "")

    # --- Identity verification ---
    print(f"\n  {_BOLD}{_YELLOW}SECURITY VERIFICATION{_RESET}")
    print("  Received message from:")
    print(f"    Name:     {_CYAN}{first_name}{_RESET}")
    if username:
        print(f"    Username: {_CYAN}@{username}{_RESET}")
    print(f"    Chat ID:  {_CYAN}{chat_id}{_RESET}")
    print()
    print(f"  {_BOLD}Only this account will be able to control Clanker.{_RESET}")
    print("  Messages from any other Telegram user will be ignored.")
    print()

    if not _confirm("  Is this you?", default=True):
        print(f"  {_DIM}Aborted. Try again with the correct account.{_RESET}")
        return

    answers["telegram_enabled"] = True
    answers["telegram_chat_ids"] = [chat_id]
    print(_ok("Telegram identity verified and locked"))


def _setup_sms(answers: dict[str, Any]) -> None:
    print(f"\n  {_BOLD}SMS Setup (Twilio){_RESET}")
    print(f"  {_DIM}Requires a Twilio account: https://www.twilio.com{_RESET}")
    print(f"  {_DIM}More complex than Telegram — needs account + phone number.{_RESET}\n")

    if not _confirm("  Set up SMS via Twilio?"):
        return

    sid = _prompt("Twilio Account SID")
    token = _secret("Twilio Auth Token")
    if not sid or not token:
        print(_fail("SID and token required"))
        return

    from clanker.remote.sms import SMSAdapter, test_twilio_credentials

    print("  Verifying credentials...")
    result = test_twilio_credentials(sid, token)
    if not result["ok"]:
        print(_fail(result.get("message", "Invalid credentials")))
        return

    print(_ok(f"Twilio account verified: {result.get('name', '')}"))
    answers["sms_account_sid"] = sid
    answers["sms_auth_token"] = token
    from_number = _prompt("Twilio phone number (E.164)", "+1")
    answers["sms_from"] = from_number
    to_number = _prompt("Your phone number (E.164)", "+1")

    if not to_number or to_number == "+1":
        return

    # --- SMS verification ---
    import random

    code = f"{random.randint(100000, 999999)}"

    print(f"\n  {_BOLD}{_YELLOW}SECURITY VERIFICATION{_RESET}")
    print(f"  Sending a 6-digit code to {_CYAN}{to_number}{_RESET}...")

    import asyncio

    async def _send_code() -> bool:
        adapter = SMSAdapter(
            account_sid=sid,
            auth_token=token,
            from_number=from_number,
            to_numbers=[to_number],
        )
        try:
            return await adapter.send(
                f"Clanker verification code: {code}\n"
                "Only this number will be able to control Clanker."
            )
        finally:
            await adapter.close()

    sent = asyncio.run(_send_code())

    if not sent:
        print(_fail("Failed to send verification SMS."))
        print(f"  {_DIM}Check your Twilio number and try again.{_RESET}")
        return

    print(_ok("Verification code sent!"))
    entered = _prompt("Enter the 6-digit code you received")

    if entered != code:
        print(_fail("Code does not match. Aborting SMS setup."))
        return

    print(
        f"\n  {_BOLD}Only {_CYAN}{to_number}{_RESET}"
        f"{_BOLD} will be able to control Clanker via SMS.{_RESET}"
    )
    print("  Messages from any other number will be ignored.")

    answers["sms_enabled"] = True
    answers["sms_to_numbers"] = [to_number]
    print(_ok("Phone number verified and locked"))


def _step_deploy(answers: dict[str, Any]) -> None:
    _header(8, "Deployment")
    print(f"  {_BOLD}Where should Clanker run?{_RESET}\n")
    print(f"  {_CYAN}1{_RESET}  Here (local machine)")
    print(f"  {_CYAN}2{_RESET}  On the HA server (via HA Add-on)")
    print(f"  {_CYAN}3{_RESET}  On a remote server (via SSH + Docker)")
    print()

    choice = _prompt("Deployment target", "1")

    if choice == "1":
        answers["deploy_mode"] = "local"
        print(_ok("Will save config locally. Run: python -m clanker.main"))

    elif choice == "2":
        answers["deploy_mode"] = "addon"
        print(f"\n  {_GREEN}HA Add-on installation:{_RESET}")
        print("  1. In HA, go to Settings -> Add-ons -> Add-on Store")
        print("  2. Click the 3 dots (top-right) -> Repositories")
        print(
            f"  3. Add: {_CYAN}https://github.com/nolankramer/clanker{_RESET}"
        )
        print("  4. Find 'Clanker' in the store and click Install")
        print("  5. Configure your API keys in the add-on settings")
        print("  6. Start the add-on\n")
        print(
            f"  {_DIM}The add-on auto-installs the custom component,"
        )
        print(
            f"  configures HA, and gets the token automatically.{_RESET}"
        )

    elif choice == "3":
        answers["deploy_mode"] = "ssh"
        ssh_host = _prompt("SSH target (e.g. user@192.168.1.50)")
        if ssh_host:
            answers["ssh_host"] = ssh_host
            from clanker.setup.remote import test_ssh

            print("  Testing SSH connection...")
            r = test_ssh(ssh_host)
            if r["ok"]:
                print(_ok(r["message"]))
                caps = r.get("capabilities", {})
                if caps.get("docker"):
                    print(_ok("Docker available"))
                if caps.get("ha_config"):
                    ha_path = caps.get("ha_config_path", "/config")
                    print(_ok(f"HA config found at {ha_path}"))
                    answers["remote_ha_config"] = ha_path

                if _confirm("Deploy now?", default=True):
                    from clanker.setup.remote import deploy_docker

                    print("  Deploying (this may take a few minutes)...")
                    dr = deploy_docker(
                        ssh_host,
                        ha_config_path=answers.get(
                            "remote_ha_config", "/config"
                        ),
                    )
                    if dr["ok"]:
                        print(_ok(dr["message"]))
                    else:
                        print(_fail(dr["message"]))
            else:
                print(_fail(r["message"]))


def _step_save(answers: dict[str, Any]) -> None:
    _header(9, "Save Configuration")

    # Validate before saving
    from clanker.setup.validate import validate_config

    issues = validate_config(answers)
    if issues:
        print(f"\n  {_YELLOW}{_BOLD}Warnings:{_RESET}")
        for issue in issues:
            print(f"  {_YELLOW}!{_RESET} {issue}")
        print()
        if not _confirm("Save anyway?", default=False):
            print("  Fix the issues above and re-run setup.")
            return

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
        _step_voice(answers)
        _step_notifications(answers)
        _step_deploy(answers)
        _step_save(answers)
    except KeyboardInterrupt:
        print(f"\n{_DIM}  Cancelled.{_RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
