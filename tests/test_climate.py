"""Test the climate platform setup."""
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_CONTROL_MODE_HOME_ASSISTANT,
                                              CONF_HA_SENSOR_INDOOR_TEMPERATURE,
                                              CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)

from .conftest import SERIAL

DATA = {CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: False, CONF_LOCK_TIMEOUT: 30,
        CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True, CONF_CONTROL_MODE_HOME_ASSISTANT: False}


async def _heating_temperature(hass, data, options):
    hass.states.async_set("sensor.from_data", "19.5")
    hass.states.async_set("sensor.from_options", "21.5")
    entry = MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data=data, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("climate", DOMAIN, f"{SERIAL}_heating")
    return hass.states.get(entity_id).attributes["current_temperature"]


async def test_indoor_temperature_sensor_from_data(hass, luxtronik):
    """The indoor temperature sensor chosen during setup is used before options are saved."""
    data = {**DATA, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_data"}

    assert await _heating_temperature(hass, data, {}) == 19.5


async def test_indoor_temperature_sensor_from_options(hass, luxtronik):
    """Options take precedence over the values stored during setup."""
    data = {**DATA, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_data"}
    options = {CONF_CONTROL_MODE_HOME_ASSISTANT: False, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_options"}

    assert await _heating_temperature(hass, data, options) == 21.5
