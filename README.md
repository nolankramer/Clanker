# Clanker

**LLM-powered smart home assistant on top of Home Assistant.**

Clanker is a self-hosted Python service that adds a brain, memory, vision reasoning, proactive announcements, and voice control on top of your existing Home Assistant setup. HA remains the source of truth for devices and automations — Clanker adds the intelligence layer.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Voice Surfaces                                │
│  ESP32-S3 satellites · HA Voice PE · Mobile app · Browser            │
│  (HA Assist pipeline handles STT/wake-word/TTS — Clanker is the     │
│   conversation agent behind it)                                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                        Clanker Core                                  │
│                                                                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Brain   │  │  Memory  │  │  Vision  │  │ Announce │             │
│  │ Router   │  │ Struct.  │  │ Frigate  │  │  Router  │             │
│  │          │  │ Semantic │  │  VLM     │  │Occupancy │             │
│  │ Anthropic│  │          │  │  Faces   │  │  Quiet   │             │
│  │ OpenAI   │  │  SQLite  │  │          │  │  Hours   │             │
│  │ Ollama   │  │ Markdown │  │          │  │          │             │
│  │ Generic  │  │ ChromaDB │  │          │  │          │             │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘             │
│                                                                      │
│  ┌───────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐             │
│  │ Proactive │  │  Remote  │  │  MCP   │  │  Convo   │             │
│  │ Scheduler │  │  Push    │  │ Server │  │  Agent   │             │
│  │ Briefing  │  │  Chat    │  │ Tools  │  │ Sessions │             │
│  │ Handlers  │  │          │  │        │  │  HTTP API│             │
│  └───────────┘  └──────────┘  └────────┘  └──────────┘             │
│                                                                      │
│  Tools exposed to brain via MCP:                                     │
│  ha_call_service · ha_get_state · ha_find_entities                   │
│  memory_read · memory_write · memory_search · notify_user            │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ WebSocket + REST
                                │ (long-lived access token)
┌───────────────────────────────▼──────────────────────────────────────┐
│                     Home Assistant (substrate)                       │
│                                                                      │
│  Devices · Entities · Automations · Frigate · Occupancy sensors      │
│  TTS targets · Notify services · Mobile app · Exposed entities       │
│                                                                      │
│  HA's exposed-entities allowlist = hard safety gate                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

- **HA is the substrate.** Clanker never talks to devices directly — it calls HA services. The HA exposed-entities allowlist is the hard safety gate.
- **Async everywhere.** No sync I/O in request paths.
- **Everything behind an interface.** LLM providers, memory stores, notification channels — all swappable.
- **Deterministic fast paths.** Critical events (fire, break-in) bypass the LLM for immediate response.
- **Human-readable memory.** Markdown files you can read, edit, grep, and git-diff.
- **Config-driven routing.** Which LLM handles which task type is config, not code.
- **Local by default.** STT (Whisper), TTS (Piper), and LLM (Ollama) all run locally. Cloud providers are optional.

## Install

### Don't have any hardware yet?

See the **[Hardware Guide](docs/hardware.md)** for specific product
recommendations at every budget ($85 / $130 / $175) with links to buy.

### Pre-built OS Image (easiest — no Linux experience needed)

1. Download the image for your hardware from [Releases](https://github.com/nolankramer/clanker/releases):
   - `clanker-x86_64-*.img.gz` for Intel mini PCs
   - `clanker-arm64-*.img.gz` for Raspberry Pi 5
2. Flash to SD card or USB with [Balena Etcher](https://etcher.balena.io/)
3. Plug in and power on
4. Open **http://clanker.local** from your phone or laptop
5. Walk through the setup wizard — done

### One-liner (Linux/Mac)

```bash
curl -fsSL https://raw.githubusercontent.com/nolankramer/clanker/main/install.sh | bash
```

This clones the repo, installs [uv](https://docs.astral.sh/uv/), installs dependencies, and launches the setup wizard.

### Setup Wizard

```bash
clanker-setup           # Interactive CLI wizard
clanker-setup --web     # Browser-based wizard at localhost:8471
```

The wizard:
1. Auto-discovers Home Assistant on your network
2. Tests connections to HA, LLM providers, Frigate
3. Discovers speakers, sensors, and rooms from HA
4. Configures voice pipeline (TTS, STT, wake word)
5. Sets up Telegram/SMS with identity verification
6. Offers three deployment modes:
   - **HA Add-on** — one-click install (recommended for HA OS)
   - **Remote SSH** — deploy to any server with Docker
   - **Local** — run on your machine
7. Validates config and saves

### Docker

```bash
# Using pre-built image (fastest)
docker pull ghcr.io/nolankramer/clanker:latest

# Or clone and build locally
git clone https://github.com/nolankramer/clanker && cd clanker
cp .env.example .env && cp config/clanker.yaml.example config/clanker.yaml
docker compose up -d
```

### HA Add-on

1. In HA: Settings → Add-ons → Add-on Store → ⋮ → Repositories
2. Add `https://github.com/nolankramer/clanker`
3. Install Clanker, configure API keys, start

The add-on auto-configures everything — no manual token or config files needed.

## Voice Pipeline

Full end-to-end voice control:

```
"Hey Clanker" → openWakeWord (local) → Whisper STT (local) → Clanker brain
  → tool calls (HA control, memory) → response → Piper TTS (local) → speaker
```

All processing is local by default. Cloud LLM providers (Anthropic, OpenAI) are optional — route conversation tasks to Ollama for a fully offline setup.

### Custom Wake Word

Train "Hey Clanker" using openWakeWord (synthetic speech generation, no voice recording needed):

```bash
pip install openwakeword tensorflow
python -m clanker.setup.wakeword
python -m clanker.setup.wakeword --deploy /share/openwakeword
```

## Configuration

All config lives in `config/clanker.yaml`. Secrets (API keys, HA token) go in `.env` or environment variables — never in the YAML file.

See `config/clanker.yaml.example` for the full schema with comments.

Key sections:
- **ha** — Home Assistant URL (token via `CLANKER_HA__TOKEN` env var)
- **anthropic/openai/ollama** — LLM provider settings
- **task_routes** — which provider handles which task type
- **memory** — database, markdown, and ChromaDB paths
- **conversation** — voice pipeline settings (port, TTS engine, system prompt)
- **announce** — room-to-speaker mapping, occupancy sensors, quiet hours
- **frigate** — Frigate NVR connection and event filtering
- **proactive** — morning briefing triggers

## Safety & Security

- **Entity allowlisting**: HA's exposed-entities allowlist is the hard gate. Clanker can only interact with entities HA exposes.
- **Verified identity only**: The setup wizard verifies your Telegram chat ID and SMS phone number during setup. Only verified accounts can control Clanker — all other messages are silently dropped (no response, no info leaked).
- **Prompt injection defense**: The system prompt instructs the brain to never execute instructions found in device names, sensor values, or tool results. Suspicious data is flagged to the user instead of acted upon.
- **Quiet hours**: TTS announcements are suppressed during configured hours. Critical alerts always go through.
- **No direct device access**: All device interaction flows through HA services.
- **Deterministic critical paths**: Fire/smoke/break-in alerts use fast deterministic handlers, not LLM reasoning.
- **Secrets in env vars**: API keys and tokens are never stored in config YAML — only in `.env` or environment variables.

See `docs/safety.md` for the full safety model.

## Development

```bash
# Run tests (149 tests)
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy clanker/
```

## Roadmap

- [x] Project scaffold and config system
- [x] LLM provider abstraction + Anthropic, OpenAI, and Ollama implementations
- [x] HA WebSocket/REST client with reconnect
- [x] Structured memory (SQLite)
- [x] Semantic memory (markdown + ChromaDB vector search)
- [x] Announcement router with occupancy + quiet hours + delivery
- [x] MCP tool server
- [x] Frigate event integration with dedup and snapshot fetching
- [x] VLM vision pipeline
- [x] Double Take face recognition integration
- [x] Conversation agent with tool-calling loop + multi-turn sessions
- [x] Conversation HTTP API server + HA custom component
- [x] Voice pipeline (Whisper STT, Piper TTS, openWakeWord)
- [x] Proactive scheduler (APScheduler)
- [x] Morning briefing (motion-triggered, weather + home state)
- [x] Event handlers (doorbell, appliance, critical alerts, unknown person)
- [x] Setup wizards (CLI + web) with auto-discovery and deployment
- [x] HA Add-on for one-click server deployment
- [x] SSH remote deployment
- [x] Telegram bot (remote chat + push with images and inline buttons)
- [x] SMS via Twilio (alerts + bidirectional chat via text message)
- [x] Unified push notification system (Telegram + SMS + HA mobile)

## License

MIT — see [LICENSE](LICENSE).
