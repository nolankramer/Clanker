"""Per-user conversation session state.

Maintains short-term context for ongoing conversations across
different surfaces (voice, push callback, chat). Long-term context
is persisted via the memory system.

TODO:
- Implement session store (in-memory with TTL)
- Track message history per user per surface
- Implement context window management (summarize/truncate old messages)
- Wire session state into brain calls
- Add session persistence for crash recovery
"""

from __future__ import annotations
