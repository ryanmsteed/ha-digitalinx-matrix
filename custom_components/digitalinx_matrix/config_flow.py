"""Config flow for DigitaLinx HDMI Matrix integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import DigitaLinxClient, DigitaLinxConnectionError
from .const import (
    CONF_INPUT_NAMES,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    DEFAULT_NAME,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_NUM_INPUTS, default=DEFAULT_NUM_INPUTS): vol.In([2, 3, 4]),
        vol.Optional(CONF_NUM_OUTPUTS, default=DEFAULT_NUM_OUTPUTS): vol.In([1, 2]),
    }
)


class DigitaLinxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DigitaLinx HDMI Matrix."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured for this host
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            # Test the connection
            client = DigitaLinxClient(user_input[CONF_HOST], user_input[CONF_PORT])
            try:
                await client.connect()
                version = await client.get_version()
                await client.disconnect()
                _LOGGER.info(
                    "Connected to DigitaLinx matrix at %s — firmware: %s",
                    user_input[CONF_HOST],
                    version,
                )
            except DigitaLinxConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                self._user_input = user_input
                return await self.async_step_input_names()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_input_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the input naming step."""
        num_inputs = self._user_input.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)

        if user_input is not None:
            input_names = {
                str(i): user_input.get(f"input_{i}", f"HDMI {i}")
                for i in range(1, num_inputs + 1)
            }
            self._user_input[CONF_INPUT_NAMES] = input_names

            return self.async_create_entry(
                title=self._user_input.get(CONF_NAME, DEFAULT_NAME),
                data=self._user_input,
            )

        # Build dynamic schema based on number of inputs
        schema_dict: dict[vol.Marker, Any] = {}
        for i in range(1, num_inputs + 1):
            schema_dict[vol.Optional(f"input_{i}", default=f"HDMI {i}")] = str

        return self.async_show_form(
            step_id="input_names",
            data_schema=vol.Schema(schema_dict),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return DigitaLinxOptionsFlow(config_entry)


class DigitaLinxOptionsFlow(OptionsFlow):
    """Handle options for DigitaLinx HDMI Matrix."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Rebuild input_names from the form
            num_inputs = self._config_entry.data.get(
                CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS
            )
            input_names = {
                str(i): user_input.get(f"input_{i}", f"HDMI {i}")
                for i in range(1, num_inputs + 1)
            }
            return self.async_create_entry(
                title="",
                data={
                    CONF_INPUT_NAMES: input_names,
                },
            )

        num_inputs = self._config_entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)
        current_names = self._config_entry.data.get(CONF_INPUT_NAMES, {})

        schema_dict: dict[vol.Marker, Any] = {}
        for i in range(1, num_inputs + 1):
            default_name = current_names.get(str(i), f"HDMI {i}")
            schema_dict[vol.Optional(f"input_{i}", default=default_name)] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
