# Safety & Security Model

Clanker interacts with real-world devices in your home. Safety is layered and defense-in-depth.

## Identity Verification

Only verified users can control Clanker. During setup, each notification channel is explicitly verified:

- **Telegram**: The setup wizard detects your chat ID when you message the bot. You confirm "Is this you?" with your name, username, and chat ID displayed. Only that chat ID is trusted.
- **SMS**: A 6-digit verification code is sent to your phone. You must enter it correctly. Only verified numbers are trusted.
- **Unverified messages are silently dropped** — no response is sent, preventing attackers from confirming the bot/number is active.

## Prompt Injection Defense

The conversation agent's system prompt includes explicit defenses:

- **Tool result data is treated as data, not instructions.** The brain will not execute text found in device names, entity attributes, sensor values, or any tool return values.
- **Suspicious content is flagged** to the user rather than acted upon.
- **System prompt, tool definitions, and config are never disclosed** in conversation.

This doesn't make prompt injection impossible, but it adds a meaningful layer of defense against attacks via manipulated device names, calendar entries, or other HA data.

## Entity Allowlisting

Home Assistant's **exposed entities** feature is the hard safety gate. Clanker can only see and interact with entities that HA has been configured to expose. This means:

- Sensitive entities (locks, alarms, garage doors) can be excluded from Clanker's reach at the HA level.
- You control what the LLM can touch, independent of what prompts or tools it has access to.

## Quiet Hours

TTS announcements are suppressed during quiet hours (default: 22:00-07:00). Priority levels:

| Priority | Quiet Hours Behavior |
|----------|---------------------|
| LOW | Fully suppressed |
| NORMAL | TTS suppressed, falls back to push (Telegram/SMS/mobile) |
| HIGH | Always delivered (TTS + push) |
| CRITICAL | All speakers + all push targets |

## Critical Event Fast Path

Events like smoke/CO detection, glass break, and flooding use **deterministic handlers** that bypass the LLM entirely. This ensures:

- Sub-second response time (no LLM latency)
- No risk of hallucinated responses during emergencies
- Guaranteed delivery to all targets
- Actionable push notifications (Call 911 / I'm Safe / False Alarm)

The LLM is only called *after* the initial alert for supplementary information (camera summaries, context).

## Remote Action Limits

The remote chat surfaces (Telegram, SMS) enforce a configurable allowlist of permitted actions. By default:

- **Allowed**: Check cameras, get entity state, send notifications
- **Blocked**: Unlock doors, disable alarms, control sensitive devices

This is configured in `config/clanker.yaml` under `remote.allowed_actions`.

## No Direct Device Access

Clanker **never** communicates with devices directly. All interactions go through HA's service call API. This means HA's existing safety mechanisms (entity exposure, automation conditions, device permissions) all apply.

## Secrets Management

- API keys and tokens are **only** set via environment variables or `.env` file
- The YAML config file never contains secrets
- The `.gitignore` excludes `.env`, database files, and key files
- The setup wizard validates config before saving and warns about missing secrets
