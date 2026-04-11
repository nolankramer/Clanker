# Clanker

**LLM-powered smart home assistant on top of Home Assistant.**

Clanker is a self-hosted Python service that adds a brain, memory, vision reasoning, proactive announcements, and voice control on top of your existing Home Assistant setup. HA remains the source of truth for devices and automations — Clanker adds the intelligence layer.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Voice Surfaces                                │
│  ESP32-S3 satellites · HA Voice PE · Mobile app · Browser            │
│  (HA Assist pipeline handles STT/wake-word/TTS — Clanker is the      │
│   conversation agent behind it)                                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                        Clanker Core                                  │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  Brain   │  │  Memory  │  │  Vision  │  │ Announce │              │
│  │ Router   │  │ Struct.  │  │ Frigate  │  │  Router  │              │
│  │          │  │ Semantic │  │  VLM     │  │Occupancy │              │
│  │ Anthropic│  │          │  │  Faces   │  │  Quiet   │              │
│  │ OpenAI   │  │  SQLite  │  │          │  │  Hours   │              │
│  │ Ollama   │  │ Markdown │  │          │  │          │              │
│  │ Generic  │  │ ChromaDB │  │          │  │          │              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │
│                                                                      │
│  ┌───────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐               │
│  │ Proactive │  │  Remote  │  │  MCP   │  │  Convo   │               │
│  │ Scheduler │  │ Telegram │  │ Server │  │  Agent   │               │
│  │ Briefing  │  │  SMS     │  │ Tools  │  │ Sessions │               │
│  │ Handlers  │  │  Push    │  │        │  │  HTTP API│               │
│  └───────────┘  └──────────┘  └────────┘  └──────────┘               │
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
│  HA's exposed-entities allowlist = hard safety gate                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Features

### Brain
- **Pluggable LLM providers** — Anthropic (Claude), OpenAI, Ollama, and any OpenAI-compatible endpoint. Config-driven task routing (vision → Claude, quick intents → local Ollama).
- **Conversation agent** — Tool-calling loop with HA device control, memory search, and entity discovery. Multi-turn sessions with persistence (SQLite).
- **Intent fast-path** — Simple commands (turn on/off, brightness, weather, timers) handled by HA's built-in intent matcher in <50ms, bypassing the LLM entirely.
- **Streaming TTS** — Sentence-by-sentence delivery while the LLM is still generating. First sentence speaks ~0.3s after generation begins.
- **Context compaction** — Token-aware summarization of old messages via the LLM. Keeps context bounded without losing continuity.
- **Auto-RAG** — Relevant memory is automatically injected into the system prompt before each brain call. No explicit tool call needed.

### Voice
- **Full voice pipeline** — "Hey Clanker" wake word → Whisper STT → brain → Piper TTS. All local by default.
- **Custom wake word** — Train "Hey Clanker" via openWakeWord (synthetic speech, no recording needed).
- **HA custom component** — Registers Clanker as a conversation agent in HA so all voice surfaces (Assist, ESP32 satellites, mobile app) work automatically.

### Vision
- **Frigate integration** — Event subscription, snapshot fetching, deduplication with configurable cooldown.
- **VLM pipeline** — Camera snapshots described by vision-capable LLMs (Claude, GPT-4o, LLaVA).
- **Face recognition** — Double Take integration with structured memory lookup. Unknown faces described via VLM.

### Proactive Automation
- **Morning briefing** — Motion-triggered daily summary (weather, home state) delivered via TTS.
- **Critical alerts** — Smoke, CO, flood, glass break → deterministic fast path (no LLM), all speakers + push with 911/Safe/False Alarm actions.
- **Doorbell** — Person detected → snapshot → VLM description → face lookup → contextual announcement + push with Talk/Ignore.
- **Appliance completion** — Washer/dryer/dishwasher done → announces to occupied rooms.
- **Unknown person** — VLM description + time/location threat assessment.

### Memory
- **Structured** (SQLite) — Faces, people, rooms, appliances, preferences.
- **Semantic** (Markdown + ChromaDB) — Human-readable files with vector search via Ollama embeddings.
- **Session persistence** — Conversations survive restarts. Stale sessions evicted by TTL.

### Notifications
- **Telegram** — Bidirectional chat, image attachments, inline keyboard actions.
- **SMS via Twilio** — Text alerts + inbound commands. MMS for images.
- **HA mobile push** — Fallback via HA notify services.
- **Announcement router** — Occupancy-aware TTS delivery, quiet hours, priority-based routing.

### Setup & Deployment
- **Setup wizards** — CLI and browser-based, with HA auto-discovery, connection testing, entity discovery, and config validation.
- **Ollama auto-setup** — Detects/installs Ollama, pulls recommended models, applies TTFT optimizations (flash attention, keep_alive, KV cache quantization).
- **Three deployment modes** — HA Add-on (one-click), remote SSH + Docker, or local.
- **Pre-built OS images** — Flash to SD/USB for mini PCs and Raspberry Pi 5. First boot launches the web wizard.
- **CI/CD** — GitHub Actions: test matrix (3.11/3.12/3.13), lint, Docker image published to GHCR.
- **Identity verification** — Telegram chat ID confirmation + SMS code verification. Unverified messages silently dropped.

### Security
- **Entity allowlisting** — HA's exposed-entities feature is the hard safety gate.
- **Prompt injection defense** — System prompt instructs the brain to treat tool results as data, not instructions.
- **Deterministic critical paths** — Life-safety events bypass the LLM for immediate, reliable response.
- **Secrets in env vars** — API keys never stored in config YAML.

See `docs/safety.md` for the full safety model.

## Install

### Pre-built OS Image (easiest — no Linux experience needed)

> See the **[Hardware Guide](docs/hardware.md)** for reference
> configurations if you need to pick hardware. (Still untested —
> contributions welcome.)

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

### One-liner (Windows PowerShell)

```powershell
irm https://raw.githubusercontent.com/nolankramer/clanker/main/install.ps1 | iex
```

Both install scripts clone the repo, install [uv](https://docs.astral.sh/uv/), install dependencies, and launch the setup wizard. The wizard handles everything — API keys, config files, Ollama setup, voice pipeline. No manual file editing needed.

### Setup Wizard

```bash
clanker-setup           # Interactive CLI wizard
clanker-setup --web     # Browser-based wizard at localhost:8471
```

The wizard auto-discovers HA, tests connections, discovers entities, installs and configures Ollama, sets up voice pipeline and notifications, and validates everything before saving.

### Docker

```bash
docker pull ghcr.io/nolankramer/clanker:latest
```

Or build locally:

```bash
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

Two speed tiers for voice responses:

```
"Turn off the kitchen lights"
  → openWakeWord → Whisper STT → HA intent fast-path (~50ms) → Piper TTS

"Set the house to movie mode"
  → openWakeWord → Whisper STT → LLM brain (streaming TTS)
  → first sentence spoken in ~0.3s → rest streams while speaking
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

All config lives in `config/clanker.yaml`. Secrets go in `.env` or environment variables.

See `config/clanker.yaml.example` for the full schema with comments.

## Development

```bash
# Run tests (180 tests)
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy clanker/
```

## License

MIT — see [LICENSE](LICENSE).
