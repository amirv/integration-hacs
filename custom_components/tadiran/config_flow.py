"""Config flow for ac integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME

from .climate import BroadlinkTadiran, CannotConnect, InvalidAuth
from .const import CONF_RM_TYPE
from .const import DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Required(CONF_RM_TYPE): vol.In({0x2737: "rm3"}),
        vol.Optional(CONF_NAME, default="tadiran"): str,
    }
)


def tadiran_validate(ip, rm_type):
    dev = BroadlinkTadiran(ip, rm_type)
    if not dev.available:
        raise CannotConnect


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """

    await hass.async_add_executor_job(
        tadiran_validate, data[CONF_IP_ADDRESS], data[CONF_RM_TYPE]
    )

    return {"title": f"{data[CONF_NAME]}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ac."""

    VERSION = 1
    # TODO pick one of the available connection classes in homeassistant/config_entries.py
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
