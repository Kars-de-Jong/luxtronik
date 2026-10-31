"""Test writing to the heatpump from the entities."""
import threading
from datetime import timedelta

import pytest
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import SERVICE_SET_TEMPERATURE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_HOST, CONF_PORT,
                                 SERVICE_TURN_ON, STATE_OFF, STATE_ON)
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE,
                                              LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE_2,
                                              LUX_SENSOR_REMOTE_MAINTENANCE)
from .conftest import MODE_SENSORS, SERIAL

REMOTE_MAINTENANCE = "switch.heatpump_2311_1234_remote_maintenance"
DOMESTIC_WATER = "climate.heatpump_2311_1234_domestic_water"


@pytest.fixture
def values(luxtronik):
    """Values of the mocked heatpump; a write stores the value, like the device does."""
    values = {LUX_SENSOR_REMOTE_MAINTENANCE: False}
    luxtronik.get_value.side_effect = lambda key: values.get(
        key, "Automatic" if key in MODE_SENSORS else 1)
    luxtronik.writes = []

    def write(parameter, value, *args, **kwargs):
        luxtronik.writes.append((parameter, value, threading.get_ident()))
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
    return entry


async def test_switch_shows_new_state_at_once(hass, luxtronik, values):
    """The switch shows the written state right away; the heatpump is read 3 s later."""
    await _setup(hass)
    assert hass.states.get(REMOTE_MAINTENANCE).state == STATE_OFF
    luxtronik.read.reset_mock()

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: REMOTE_MAINTENANCE}, blocking=True)

    assert [w[:2] for w in luxtronik.writes] == [("ID_Einst_Fernwartung_akt", True)]
    assert hass.loop_thread_id != luxtronik.writes[0][2]
    assert hass.states.get(REMOTE_MAINTENANCE).state == STATE_ON
    luxtronik.read.assert_not_called()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    luxtronik.read.assert_called_once_with()


async def test_climate_writes_share_one_refresh(hass, luxtronik, values):
    """A target temperature written to two parameters leads to one read of the heatpump."""
    await _setup(hass)
    luxtronik.read.reset_mock()

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: DOMESTIC_WATER, ATTR_TEMPERATURE: 50}, blocking=True)

    assert [w[:2] for w in luxtronik.writes] == [
        (LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE_2.split(".")[1], 50),
        (LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE.split(".")[1], 50),
    ]
    assert hass.states.get(DOMESTIC_WATER).attributes[ATTR_TEMPERATURE] == 50

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    luxtronik.read.assert_called_once_with()
