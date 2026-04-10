"""Remote chat interface — conversational access from anywhere.

Placeholder for a Telegram, Signal, or custom chat bot that gives
the user a text-based interface to Clanker from outside the home.
Same brain, same tools, but with a configurable action allowlist
for safety (e.g. can check cameras, can't unlock doors remotely).

TODO:
- Choose chat platform (Telegram, Signal, or custom HTTP)
- Implement message receive/send loop
- Wire into brain with remote-specific system prompt
- Enforce remote action allowlist from config
- Add authentication/authorization
"""

from __future__ import annotations
