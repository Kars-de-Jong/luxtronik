"""Test the switches."""
import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (ATTR_ENTITY_ID, ATTR_ICON, CONF_HOST, CONF_PORT,
                                 SERVICE_TURN_OFF, STATE_OFF, STATE_ON)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              LUX_SENSOR_MODE_HEATING)

from .conftest import MODE_SENSORS, SERIAL

HEATING = "switch.heatpump_2311_1234_heating_automatic_mode"


@pytest.fixture
def values(luxtronik):
    """Values of the mocked heatpump; a write stores the value, like the device does."""
    values = {}
    luxtronik.get_value.side_effect = lambda key: values.get(
        key, "Automatic" if key in MODE_SENSORS else 1)
    luxtronik.writes = []

    def write(parameter, value):
        luxtronik.writes.append((parameter, value))
        values[f"parameters.{parameter}"] = value
        return True

    luxtronik.write = write
    return values


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_turn_off_mode(hass, luxtronik, values):
    """Turning off a mode switch writes the off mode, and shows the off icon."""
    await _setup(hass)
    assert hass.states.get(HEATING).state == STATE_ON
    assert hass.states.get(HEATING).attributes[ATTR_ICON] == "mdi:radiator"

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: HEATING}, blocking=True)

    assert luxtronik.writes == [(LUX_SENSOR_MODE_HEATING.split(".")[1], "Off")]
    assert hass.states.get(HEATING).state == STATE_OFF
    assert hass.states.get(HEATING).attributes[ATTR_ICON] == "mdi:radiator-off"
