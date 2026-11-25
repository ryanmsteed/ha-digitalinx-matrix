"""Media player platform for DigitaLinx HDMI Matrix.

Creates one media_player entity per HDMI output zone.
Source selection routes an HDMI input to this output.

State is assumed from SET SW command confirmations since
GET SW is not supported on firmware 3.6. The entity is
marked assumed_state so HA shows toggle-style controls.

Availability follows the shared client: it goes False only after a command
(or the periodic keepalive) fails even after a reconnect-and-retry, and goes
back to True by itself once the matrix answers again.
"""

from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import DigitaLinxClient, DigitaLinxConnectionError
from .const import (
    CONF_INPUT_NAMES,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DigitaLinx media player entities from a config entry."""
    client: DigitaLinxClient = hass.data[DOMAIN][entry.entry_id]

    num_inputs = entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)
    num_outputs = entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)

    # Merge input names from config data and options
    input_names_data = entry.data.get(CONF_INPUT_NAMES, {})
    input_names_opts = entry.options.get(CONF_INPUT_NAMES, {})
    input_names = {**input_names_data, **input_names_opts}

    # Build the source list: { "friendly_name": input_number }
    source_map: dict[str, int] = {}
    for i in range(1, num_inputs + 1):
        name = input_names.get(str(i), f"HDMI {i}")
        source_map[name] = i

    entities = [
        DigitaLinxOutputZone(
            client=client,
            entry=entry,
            output_num=out,
            source_map=source_map,
        )
        for out in range(1, num_outputs + 1)
    ]

    async_add_entities(entities)


class DigitaLinxOutputZone(MediaPlayerEntity):
    """A single HDMI output zone on the matrix.

    Source selection routes an HDMI input to this output.
    State is tracked locally from SET SW confirmations.
    """

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE
    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(
        self,
        client: DigitaLinxClient,
        entry: ConfigEntry,
        output_num: int,
        source_map: dict[str, int],
    ) -> None:
        """Initialize the output zone entity."""
        self._client = client
        self._output_num = output_num
        self._source_map = source_map
        self._reverse_source_map = {v: k for k, v in source_map.items()}
        self._entry = entry
        self._current_input: int | None = None

        self._attr_unique_id = f"{entry.entry_id}_output_{output_num}"
        self._attr_name = f"Output {output_num}"
        self._attr_source_list = list(source_map.keys())

    async def async_added_to_hass(self) -> None:
        """Refresh state whenever the matrix goes unavailable or comes back."""
        self.async_on_remove(self._client.add_listener(self.async_write_ha_state))

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the matrix switcher."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Liberty AV / DigitaLinx",
            model="DL-S42-H2",
        )

    @property
    def available(self) -> bool:
        """Return True if the matrix is reachable."""
        return self._client.available

    @property
    def state(self) -> MediaPlayerState:
        """Return ON when a source is routed, IDLE otherwise."""
        if self._current_input is not None:
            return MediaPlayerState.ON
        return MediaPlayerState.IDLE

    @property
    def source(self) -> str | None:
        """Return the currently selected source (routed input)."""
        if self._current_input is not None:
            return self._reverse_source_map.get(
                self._current_input, f"HDMI {self._current_input}"
            )
        return None

    async def async_select_source(self, source: str) -> None:
        """Route an HDMI input to this output."""
        input_num = self._source_map.get(source)
        if input_num is None:
            _LOGGER.error("Unknown source: %s", source)
            return

        _LOGGER.info(
            "Switching output %s to input %s (%s)",
            self._output_num,
            input_num,
            source,
        )
        try:
            response = await self._client.set_switch(input_num, self._output_num)
        except DigitaLinxConnectionError as err:
            # The client already retried once after reconnecting. Surface the
            # failure to the caller (UI toast / automation trace) and leave the
            # assumed source untouched.
            raise HomeAssistantError(
                f"Could not switch output {self._output_num} to {source}: {err}"
            ) from err

        # Confirmation format: "SW in{i} out{o}"
        # Parse to verify the switch was accepted
        confirmed_input = self._client.parse_switch_response(response)
        if confirmed_input is not None:
            self._current_input = confirmed_input
        else:
            # Trust the command even if we can't parse the response
            self._current_input = input_num

        self.async_write_ha_state()
