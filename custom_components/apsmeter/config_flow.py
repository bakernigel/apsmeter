"""
Config flow for APS Meter integration.
Supports initial setup + reconfigure (change username/password without deleting).
"""
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, NAME
from .api import API, InvalidAuth, CannotConnect

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for APS Meter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (prompt for credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                test_api = API(username=user_input[CONF_USERNAME], password=user_input[CONF_PASSWORD])
                await test_api.async_sign_in()
            except InvalidAuth:
                errors["base"] = "Invalid logon or password"
            except CannotConnect:
                errors["base"] = "Cannot connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "Unknown error - check logs"
            else:
                return self.async_create_entry(
                    title=NAME,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default="bakernigel@yahoo.com"): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration (change username/password)."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Test new credentials
                test_api = API(username=user_input[CONF_USERNAME], password=user_input[CONF_PASSWORD])
                await test_api.async_sign_in()
            except InvalidAuth:
                errors["base"] = "Invalid logon or password"
            except CannotConnect:
                errors["base"] = "Cannot Connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "Unknown error - check logs"
            else:
                # Update the existing entry with new credentials
                new_data = dict(reconfigure_entry.data)
                new_data.update(user_input)
                self.hass.config_entries.async_update_entry(
                    reconfigure_entry, data=new_data
                )

                # Reload the integration (this updates the singleton API)
                await self.hass.config_entries.async_reload(reconfigure_entry.entry_id)

                return self.async_abort(reason="reconfigure_successful")

        # Show form pre-filled with current username (password left blank for security)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=reconfigure_entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "name": NAME,
            },
        )