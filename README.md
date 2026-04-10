# Clanker

**LLM-powered smart home assistant on top of Home Assistant.**

Clanker is a self-hosted Python service that adds a brain, memory, vision reasoning, proactive announcements, and remote control surface on top of your existing Home Assistant setup. HA remains the source of truth for devices and automations — Clanker adds the intelligence layer.

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
│  │ Handlers  │  │          │  │        │  │          │             │
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

## Quickstart

### Prerequisites

- Python 3.12+
- Home Assistant with a long-lived access token
- (Optional) Ollama for local LLM inference
- (Optional) Frigate for camera/detection events

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env with your HA URL, token, and API keys

cp config/clanker.yaml.example config/clanker.yaml
# Edit config/clanker.yaml to match your room/speaker/sensor setup

docker compose up -d
```

### Bare metal

```bash
# Install uv if you haven't
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy and edit config
cp .env.example .env
cp config/clanker.yaml.example config/clanker.yaml

# Run
uv run clanker
```

## Configuration

All config lives in `config/clanker.yaml`. Secrets (API keys, HA token) go in `.env` or environment variables — never in the YAML file.

See `config/clanker.yaml.example` for the full schema with comments.

Key sections:
- **ha** — Home Assistant URL (token via `CLANKER_HA__TOKEN` env var)
- **anthropic/openai/ollama** — LLM provider settings
- **task_routes** — which provider handles which task type
- **memory** — database and markdown paths
- **announce** — room-to-speaker mapping, occupancy sensors, quiet hours
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
# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy clanker/
```

## Roadmap

- [x] Project scaffold and config system
- [x] LLM provider abstraction + Anthropic implementation
- [x] HA WebSocket/REST client with reconnect
- [x] Structured memory (SQLite)
- [x] Announcement router with occupancy + quiet hours
- [x] MCP tool server skeleton
- [ ] OpenAI provider implementation
- [ ] Ollama provider implementation
- [ ] Frigate event integration
- [ ] VLM vision pipeline
- [ ] Double Take face recognition
- [ ] Semantic memory embeddings (ChromaDB + Ollama)
- [ ] Proactive scheduler + morning briefing
- [ ] Event handlers (doorbell, appliance, critical, unknown person)
- [ ] Remote push notifications with action buttons
- [ ] HA custom conversation agent registration
- [ ] Remote chat bot (Telegram/Signal)
- [ ] Session management and multi-turn conversations

## License

MIT — see [LICENSE](LICENSE).
