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

## Quickstart

### Setup Wizard (recommended)

```bash
pip install -e .
clanker-setup           # Interactive CLI wizard
clanker-setup --web     # Browser-based wizard at localhost:8471
```

The wizard auto-discovers Home Assistant, tests connections, discovers entities, configures voice pipeline, and offers three deployment modes:

1. **HA Add-on** — One-click install from HA's add-on store (recommended for HA OS)
2. **Remote SSH** — Deploy to any server with Docker
3. **Local** — Run on your machine

See `docs/quickstart.md` for the full guide.

### Docker

```bash
cp .env.example .env
cp config/clanker.yaml.example config/clanker.yaml
# Edit both files

docker compose up -d
```

### HA Add-on

1. In HA: Settings → Add-ons → Add-on Store → ⋮ → Repositories
2. Add `https://github.com/nolankramer/clanker`
3. Install Clanker, configure API keys, start

The add-on auto-installs the HA custom component, generates config, and gets the auth token from HA's Supervisor — no manual setup needed.

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

## Safety

- **Entity allowlisting**: HA's exposed-entities allowlist is the hard gate. Clanker can only interact with entities HA exposes.
- **Quiet hours**: TTS announcements are suppressed during configured hours. Critical alerts always go through.
- **Remote action limits**: The remote chat surface has a configurable allowlist of permitted actions.
- **No direct device access**: All device interaction flows through HA services.
- **Deterministic critical paths**: Fire/smoke/break-in alerts use fast deterministic handlers, not LLM reasoning.

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
