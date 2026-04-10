"""Typed helpers for common Home Assistant service calls.

Thin wrappers around HAClient.call_service that provide a friendlier
Python API for the most-used services. Every call goes through the
HA client — nothing talks to devices directly.

TODO:
- Add more service helpers as needed (climate, cover, media, etc.)
- Add response type models
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.ha.client import HAClient

logger = structlog.get_logger(__name__)


class HAServices:
    """Typed convenience wrappers for common HA service calls."""

    def __init__(self, client: HAClient) -> None:
        """Initialize with an HA client.

        Args:
            client: Connected HAClient instance.
        """
        self._client = client

    async def turn_on(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Turn on an entity.

        Args:
            entity_id: Target entity.
            **kwargs: Additional service data (brightness, color_temp, etc.).
        """
        domain = entity_id.split(".")[0]
        return await self._client.call_service(domain, "turn_on", entity_id=entity_id, data=kwargs)

    async def turn_off(self, entity_id: str) -> dict[str, Any]:
        """Turn off an entity.

        Args:
            entity_id: Target entity.
        """
        domain = entity_id.split(".")[0]
        return await self._client.call_service(domain, "turn_off", entity_id=entity_id)

    async def tts_speak(
        self,
        media_player: str,
        message: str,
        *,
        service: str = "tts.speak",
        language: str | None = None,
    ) -> dict[str, Any]:
        """Send a TTS announcement to a media player.

        Args:
            media_player: Target media_player entity ID.
            message: Text to speak.
            service: TTS service to use (default: tts.speak).
            language: Optional language code.
        """
        domain, svc = service.split(".", 1)
        data: dict[str, Any] = {"message": message}
        if language:
            data["language"] = language
        return await self._client.call_service(
            domain, svc, entity_id=media_player, data=data
        )

    async def notify(
        self,
        target: str,
        message: str,
        *,
        title: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a notification via HA notify service.

        Args:
            target: Notify service target (e.g. "mobile_app_my_phone").
            message: Notification body.
            title: Optional notification title.
            data: Optional extra data (actions, image, etc.).
        """
        svc_data: dict[str, Any] = {"message": message}
        if title:
            svc_data["title"] = title
        if data:
            svc_data["data"] = data

        # notify services use the format: notify.mobile_app_xxx
        domain, service_name = target.split(".", 1) if "." in target else ("notify", target)
        return await self._client.call_service(domain, service_name, data=svc_data)

    async def get_binary_sensor_state(self, entity_id: str) -> bool:
        """Get whether a binary sensor is on/off.

        Args:
            entity_id: Binary sensor entity ID.

        Returns:
            True if the sensor state is "on".
        """
        state = await self._client.get_state(entity_id)
        return state.get("state") == "on"
