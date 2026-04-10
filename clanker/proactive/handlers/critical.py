"""Critical event handler — smoke, CO, glass break, flood.

These events skip the brain for initial response (deterministic, fast).
Alerts go to ALL speakers and push targets immediately. Brain is called
afterward for situational awareness (camera summaries, context).

TODO:
- Subscribe to smoke/CO detector, glass break, and flood sensor events
- Implement deterministic alert pipeline (no LLM for initial response)
- Push to all targets with [Call 911, I'm safe, False alarm] actions
- If no "I'm safe" response within timeout, escalate with camera summary
- Log all critical events with full context
"""

from __future__ import annotations
