# Safety Model

Clanker interacts with real-world devices in your home. Safety is layered and defense-in-depth.

## Entity Allowlisting

Home Assistant's **exposed entities** feature is the hard safety gate. Clanker can only see and interact with entities that HA has been configured to expose. This means:

- Sensitive entities (locks, alarms, garage doors) can be excluded from Clanker's reach at the HA level.
- You control what the LLM can touch, independent of what prompts or tools it has access to.

## Quiet Hours

TTS announcements are suppressed during quiet hours (default: 22:00–07:00). Priority levels:

| Priority | Quiet Hours Behavior |
|----------|---------------------|
| LOW | Fully suppressed |
| NORMAL | TTS suppressed, falls back to mobile push |
| HIGH | Always delivered (TTS + push) |
| CRITICAL | All speakers + all push targets |

## Critical Event Fast Path

Events like smoke/CO detection, glass break, and flooding use **deterministic handlers** that bypass the LLM entirely. This ensures:

- Sub-second response time (no LLM latency)
- No risk of hallucinated responses during emergencies
- Guaranteed delivery to all targets

The LLM is only called *after* the initial alert for supplementary information (camera summaries, context).

## Remote Action Limits

The remote chat surface (Telegram/Signal) enforces a configurable allowlist of permitted actions. By default:

- **Allowed**: Check cameras, get entity state, send notifications
- **Blocked**: Unlock doors, disable alarms, control sensitive devices

This is configured in `config/clanker.yaml` under `remote.allowed_actions`.

## No Direct Device Access

Clanker **never** communicates with devices directly. All interactions go through HA's service call API. This means HA's existing safety mechanisms (entity exposure, automation conditions, device permissions) all apply.

## Secrets Management

- API keys and tokens are **only** set via environment variables or `.env` file
- The YAML config file never contains secrets
- The `.gitignore` excludes `.env` and database files
