"""Clanker integration for Home Assistant.

Registers Clanker as a conversation agent so that any HA voice surface
(Assist pipeline, ESP32 satellites, Voice PE, mobile app) routes
through Clanker's brain.

Configuration in configuration.yaml::

    clanker:
      url: "http://localhost:8472"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import CONF_URL
from homeassistant.helpers import config_validation as cv

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "clanker"
DEFAULT_URL = "http://localhost:8472"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_URL, default=DEFAULT_URL): cv.url,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS = ["conversation"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Clanker integration from configuration.yaml."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = {"url": config[DOMAIN].get(CONF_URL, DEFAULT_URL)}

    hass.helpers.discovery.load_platform("conversation", DOMAIN, {}, config)
    _LOGGER.info("Clanker integration loaded, URL: %s", hass.data[DOMAIN]["url"])
    return True
