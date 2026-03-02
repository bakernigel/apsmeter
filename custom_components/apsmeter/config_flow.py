"""
Config flow for APS Meter integration.
Prompts for username (logon ID) and password, saves them securely.
"""
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, NAME
from .api import API, InvalidAuth, CannotConnect   # we'll update api.py next

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for APS Meter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (prompt for credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test the credentials immediately (great UX!)
            try:
                # Temporary API to validate login
                test_api = API(username=user_input[CONF_USERNAME], password=user_input[CONF_PASSWORD])
                await test_api.async_sign_in()
            except InvalidAuth:
                errors["base"] = "Invalid logon or password"
            except CannotConnect:
                errors["base"] = "Cannot connect"
#            except Exception:  # pylint: disable=broad-except
#                errors["base"] = "Unknown error - check logs"
            else:
                # Success! Save credentials
                return self.async_create_entry(
                    title=NAME,
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        # Show the form to the user
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