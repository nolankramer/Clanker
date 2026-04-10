"""Home Assistant custom conversation agent registration.

Registers Clanker as a conversation agent in HA so that any HA voice
surface (Assist pipeline, ESP32-S3 satellites, Voice PE, mobile app
voice button) automatically works with Clanker's brain.

TODO:
- Register with HA via the conversation/agent API
- Implement the HA conversation agent protocol (process method)
- Route user intents through Clanker's brain with tools
- Return responses in HA's expected format
- Handle multi-turn conversations via session state
"""

from __future__ import annotations
