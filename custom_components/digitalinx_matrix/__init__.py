"""DigitaLinx HDMI Matrix integration for Home Assistant.

Supports Liberty DigitaLinx DL-S42-H2 (and compatible) matrix switchers
via TCP/IP control on port 23.

Creates one media_player entity per HDMI output zone, allowing
source selection (input routing) from Home Assistant. State is tracked
from SET command confirmations (GET SW is not supported on firmware 3.6).
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .client import DigitaLinxClient
from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DigitaLinx HDMI Matrix from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    client = DigitaLinxClient(host, port)
    await client.connect()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client: DigitaLinxClient = hass.data[DOMAIN].pop(entry.entry_id)
        await client.disconnect()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
