"""Support for Tadiran AC using broadlink IR."""

import logging

import broadlink
from broadlink.exceptions import DeviceOfflineError
import voluptuous as vol

from homeassistant import exceptions
from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_DRY,
    CURRENT_HVAC_FAN,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_OFF,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SWING_OFF,
    SWING_VERTICAL,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_IP_ADDRESS,
    CONF_NAME,
    TEMP_CELSIUS,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify
from homeassistant.util.temperature import convert as convert_temperature

from .const import CONF_RM_TYPE, CONF_TEMP_ENTITY_ID, CONF_HUMIDITY_ENTITY_ID

_LOGGER = logging.getLogger(__name__)

MIN_TEMP = 16
MAX_TEMP = 30

DEFAULT_RM_TYPE = 0x2737

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default="tadiran"): cv.string,
        vol.Optional(CONF_RM_TYPE, default=DEFAULT_RM_TYPE): cv.positive_int,
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Optional(CONF_TEMP_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_HUMIDITY_ENTITY_ID): cv.entity_id,
    }
)


@callback
async def create_tadiran_entities(hass, config_entry, async_add_entities):
    """Create entities from a BleBox product's features."""

    config = config_entry.data
    entities = [
        TadiranClimate(
            hass,
            config[CONF_NAME],
            config[CONF_IP_ADDRESS],
            config[CONF_RM_TYPE],
            config[CONF_TEMP_ENTITY_ID],
            config[CONF_HUMIDITY_ENTITY_ID]
            )
    ]

    async_add_entities(entities, True)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Tadiran devices."""
    devices = [
        TadiranClimate(config[CONF_NAME], config[CONF_IP_ADDRESS], config[CONF_RM_TYPE])
    ]

    async_add_entities(devices)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up a BleBox climate entity."""

    await create_tadiran_entities(hass, config_entry, async_add_entities)


class TadiranClimate(ClimateEntity):
    """Implementation of a Tadiran climate device."""

    def __init__(self, hass, name, ip, rm_type, temp_entity, humidity_entity):
        """Initialization of a Tadiran climate device."""
        self._name = name
        self._ip = ip
        self._id = slugify(ip)
        self._state = False
        self._target_temp = 24
        self._hvac_mode = HVAC_MODE_OFF
        self._last_hvac_mode = HVAC_MODE_COOL
        self._fan_mode = FAN_AUTO
        self._swing_mode = SWING_OFF
        self._temp_entity = temp_entity
        self._humidity_entity = humidity_entity

        self.remote = BroadlinkTadiran(ip, rm_type)

        self.hass = hass

    def get_entity_val(self, entity):
        if not entity:
            return None

        sensor_state = self.hass.states.get(entity)

        if sensor_state == None:
            return None

        if sensor_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        return float(sensor_state.state)

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self.get_entity_val(self._humidity_entity)


    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self.get_entity_val(self._temp_entity)

    @property
    def name(self):
        """Device name"""
        return self._name

    @property
    def supported_features(self) -> int:
        """Bitmask of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE | SUPPORT_SWING_MODE

    @property
    def temperature_unit(self):
        """Temperature units"""
        return TEMP_CELSIUS

    @property
    def hvac_mode(self):
        """Current configured HVAC mode"""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Supported HVAC modes"""
        return [
            HVAC_MODE_COOL,
            HVAC_MODE_DRY,
            HVAC_MODE_FAN_ONLY,
            HVAC_MODE_HEAT,
            HVAC_MODE_OFF,
        ]

    @property
    def hvac_action(self):
        """Currently HVAC state"""
        hvac_action = {
            HVAC_MODE_COOL: CURRENT_HVAC_COOL,
            HVAC_MODE_DRY: CURRENT_HVAC_DRY,
            HVAC_MODE_FAN_ONLY: CURRENT_HVAC_FAN,
            HVAC_MODE_HEAT: CURRENT_HVAC_HEAT,
        }.get(self._hvac_mode, CURRENT_HVAC_OFF)

        return hvac_action

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def target_temperature_step(self):
        return 1

    @property
    def available(self):
        """Return True if entity is available."""
        return self.remote.available

    @property
    def fan_mode(self):
        return self._fan_mode

    @property
    def fan_modes(self):
        return [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]

    @property
    def swing_mode(self):
        return self._swing_mode

    @property
    def swing_modes(self):
        return [SWING_OFF, SWING_VERTICAL]

    def set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        self._target_temp = temp
        self.send_state()

    def set_fan_mode(self, fan_mode: str) -> None:
        self._fan_mode = fan_mode
        self.send_state()

    def set_hvac_mode(self, hvac_mode: str) -> None:
        if hvac_mode == HVAC_MODE_OFF:
            self._last_hvac_mode = hvac_mode

        self._hvac_mode = hvac_mode
        self.send_state()

    def set_swing_mode(self, swing_mode: str) -> None:
        self._swing_mode = swing_mode
        self.send_state()

    def send_state(self):
        _LOGGER.debug(
            f"Sending new state: {self._hvac_mode} {self._fan_mode} {self._swing_mode} {self._target_temp}"
        )
        args_vars = {
            "temp": int(self._target_temp),
            "fan": {FAN_AUTO: 0, FAN_LOW: 1, FAN_MEDIUM: 2, FAN_HIGH: 3}.get(
                self._fan_mode, 0
            ),
            "swing": 1 if self._swing_mode != SWING_OFF else 0,
            "on": 1 if self._hvac_mode != HVAC_MODE_OFF else 0,
            "mode": {
                HVAC_MODE_OFF: 0,
                HVAC_MODE_FAN_ONLY: 0,  # XXX 0 seems to be auto and not fan
                HVAC_MODE_COOL: 1,
                HVAC_MODE_DRY: 2,
                HVAC_MODE_HEAT_COOL: 3,
                HVAC_MODE_HEAT: 4,
            }.get(self._hvac_mode, 1),
        }
        self.remote.send(args_vars)

    @property
    def min_temp(self) -> float:
        return convert_temperature(MIN_TEMP, TEMP_CELSIUS, self.temperature_unit)

    @property
    def max_temp(self) -> float:
        return convert_temperature(MAX_TEMP, TEMP_CELSIUS, self.temperature_unit)

    @property
    def unique_id(self):
        """Return unique ID based on Tadiran ID."""
        return self._id

    async def async_turn_on(self):
        """Turn the entity on."""
        await self.async_set_hvac_mode(self._last_hvac_mode)

PREFIX = "26004e0000012793"
SUFFIX = "14000d0500000000000000000000"

unpack = [
    {"name": "unknown2", "shift": 27, "bits": 8, "default": 0x4A},
    {"name": "blow", "shift": 23, "bits": 1, "default": 0},
    {"name": "light", "shift": 21, "bits": 1, "default": 1},
    {"name": "turbo", "shift": 20, "bits": 1, "default": 0},
    {"name": "temp", "shift": 8, "bits": 4, "default": 20},
    {"name": "swing", "shift": 6, "bits": 2, "default": 0},
    {"name": "fan", "shift": 4, "bits": 2, "default": 1},
    {"name": "on", "shift": 3, "bits": 1, "default": 1},
    {"name": "mode", "shift": 0, "bits": 3, "default": 1},
]


def pack(vals):
    bits = list("0" * (35))

    for descr in unpack:
        start = descr["shift"]

        i = vals.get(descr["name"], descr["default"])
        v = ("{0:0%d" % descr["bits"] + "b}").format(i)[::-1]

        for i in range(descr["bits"]):
            bits[start + i] = v[i]

    data = bytearray.fromhex(PREFIX)
    for x in bits:
        data.append(0x16)
        data.append(19 if x == "0" else 55)

    data = data + bytearray.fromhex(SUFFIX)

    return data


class BroadlinkTadiran:
    def __init__(self, ip, rmtype):
        mac = "000000000000"
        try:
            self.dev = broadlink.gendevice(rmtype, (ip, 80), mac)
        except broadlink.exceptions.DeviceOfflineError:
            raise CannotConnect

        try:
            self._available = self.dev.auth()
        except broadlink.exceptions.DeviceOfflineError:
            raise InvalidAuth

    @property
    def available(self):
        return self._available

    def send(self, args_vars):
        data = {}

        for k in unpack:
            arg = k["name"]
            val = args_vars.get(arg, None)
            if val != None:
                data[arg] = val

        if args_vars.get("on") == 0:
            _LOGGER.info("Turning OFF the AC")

        bytes = pack(data)
        self.dev.send_data(bytes)

    def is_alive(self):
        # XXX XXX XXX should set timeout - if not connected will hang for more
        # than 10 seconds
        _LOGGER.warning("testing connectivity")
        try:
            self.dev.send_packet(0x6A, bytes())
        except DeviceOfflineError:
            _LOGGER.warning("Failed to connect to Broadlink device")
            return False

        _LOGGER.warning("connectivity OK")
        return True


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
