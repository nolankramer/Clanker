# Clanker Architecture

## Three-Layer Model

### 1. Home Assistant (substrate)

HA owns devices, entities, Frigate integration, occupancy sensors, timers, notification services, and the mobile app. Clanker talks to HA exclusively via WebSocket and REST APIs using a long-lived access token. The exposed-entities allowlist in HA is the hard safety boundary.

### 2. Clanker Core (Python service)

A long-running async Python service with these modules:

- **Brain** — Pluggable LLM providers (Anthropic, OpenAI, Ollama, generic OpenAI-compatible). Config-driven task routing (vision → Claude, quick intents → local).
- **Memory** — Structured facts in SQLite, semantic recall via markdown files indexed with local embeddings into ChromaDB.
- **Vision** — Frigate event handling, VLM-based image description, Double Take face recognition integration.
- **Announce** — Routes messages to speakers by occupancy, quiet hours, and priority. Falls back to push when no one is home.
- **Proactive** — Cron-like scheduler plus event-driven handlers for morning briefings, appliance completion, doorbell, critical alerts.
- **Remote** — Mobile push with actionable buttons, conversational chat bot (Telegram/Signal).
- **MCP Server** — Exposes tools to the brain via Model Context Protocol for provider-agnostic tool use.
- **Conversation** — HA custom conversation agent so any Assist voice surface works with Clanker.

### 3. Memory System

Two tiers behind a common `MemoryStore` interface:

- **Structured** (SQLite) — typed schema for faces, people, rooms, appliances, preferences.
- **Semantic** (markdown + ChromaDB) — one file per topic, indexed with local embeddings. Human-readable, git-friendly, greppable.

## Event Flow

Events flow from HA → Clanker's event dispatcher → registered handlers → brain/announce/memory as needed. Critical events use deterministic fast paths; open-ended events escalate to the brain.

## Tool Surface

Tools are exposed via MCP so the same definitions work across all LLM providers:
`ha_call_service`, `ha_get_state`, `ha_find_entities`, `memory_read`, `memory_write`, `memory_search`, `notify_user`.
