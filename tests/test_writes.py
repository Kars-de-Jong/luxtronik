"""Test writing to the heatpump from the entities."""
import threading
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import SERVICE_SET_TEMPERATURE
from homeassistant.components.number import ATTR_VALUE as NUMBER_ATTR_VALUE
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_HOST, CONF_PORT,
                                 SERVICE_TURN_ON, STATE_OFF, STATE_ON)
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.luxtronik.const import (ATTR_PARAMETER, ATTR_VALUE, CONF_LOCK_TIMEOUT,
                                              CONF_SAFE, CONF_UPDATE_IMMEDIATELY_AFTER_WRITE,
                                              DOMAIN, SERVICE_WRITE,
                                              LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE,
                                              LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE_2,
                                              LUX_SENSOR_REMOTE_MAINTENANCE)
from custom_components.luxtronik.coordinator import LuxtronikCoordinator
from .conftest import MODE_SENSORS, SERIAL

REMOTE_MAINTENANCE = "switch.heatpump_2311_1234_remote_maintenance"
DOMESTIC_WATER = "climate.heatpump_2311_1234_domestic_water"
THERMAL_DESINFECTION = "number.heatpump_2311_1234_domestic_water_thermal_disinfection_target"


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


async def _write_action(hass, parameter, value):
    await hass.services.async_call(
        DOMAIN, SERVICE_WRITE, {ATTR_PARAMETER: parameter, ATTR_VALUE: value}, blocking=True)


async def _wait(hass, seconds):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_write_action_keeps_writes_to_other_parameters(hass, luxtronik, values):
    """Writes to different parameters within 3 seconds are all written."""
    await _setup(hass)

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    await _write_action(hass, "ID_Ba_Bw_akt", "Off")
    assert luxtronik.writes == []

    await _wait(hass, 3)
    assert sorted(w[:2] for w in luxtronik.writes) == [
        ("ID_Ba_Bw_akt", "Off"), ("ID_Ba_Hz_akt", "Party")]
    assert hass.loop_thread_id not in {w[2] for w in luxtronik.writes}


async def test_write_action_debounces_the_same_parameter(hass, luxtronik, values):
    """Only the last of several writes to one parameter within 3 seconds is written."""
    await _setup(hass)

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    await _wait(hass, 2)
    await _write_action(hass, "ID_Ba_Hz_akt", "Off")
    await _wait(hass, 2)
    assert luxtronik.writes == []

    await _wait(hass, 3)
    assert [w[:2] for w in luxtronik.writes] == [("ID_Ba_Hz_akt", "Off")]


async def test_write_actions_of_two_heatpumps(hass, luxtronik, values):
    """Debounced writes to two heatpumps don't cancel each other."""
    entry = await _setup(hass)
    other = MagicMock()
    other.write.return_value = True
    coordinator = LuxtronikCoordinator(hass, entry, other)

    entry.runtime_data.coordinator.async_write_debounced("ID_Ba_Hz_akt", "Party")
    coordinator.async_write_debounced("ID_Ba_Hz_akt", "Off")
    await _wait(hass, 3)

    assert [w[:2] for w in luxtronik.writes] == [("ID_Ba_Hz_akt", "Party")]
    other.write.assert_called_once_with("ID_Ba_Hz_akt", "Off")


@pytest.mark.parametrize(("update_immediately", "reads"), [(True, 1), (False, 0)])
async def test_write_action_refresh_option(hass, luxtronik, values, update_immediately, reads):
    """The heatpump is read 3 seconds after the write only when the option is enabled."""
    entry = await _setup(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: update_immediately})
    await hass.async_block_till_done()
    luxtronik.read.reset_mock()

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    await _wait(hass, 3)
    await _wait(hass, 6)

    assert len(luxtronik.writes) == 1
    assert luxtronik.read.call_count == reads


async def test_number_write_is_debounced(hass, luxtronik, values):
    """A number writes only the last value set within 3 seconds, and shows it once written."""
    await _setup(hass)

    for value in (55, 56, 57):
        await hass.services.async_call(
            NUMBER_DOMAIN, SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: THERMAL_DESINFECTION, NUMBER_ATTR_VALUE: value}, blocking=True)
    assert luxtronik.writes == []

    await _wait(hass, 3)
    assert [w[:2] for w in luxtronik.writes] == [("ID_Einst_LGST_akt", 570)]
    assert float(hass.states.get(THERMAL_DESINFECTION).state) == 57


async def test_unload_writes_pending_values(hass, luxtronik, values):
    """A debounced write that is still pending is written when the entry is unloaded."""
    entry = await _setup(hass)

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert [w[:2] for w in luxtronik.writes] == [("ID_Ba_Hz_akt", "Party")]
    await _wait(hass, 3)
    assert len(luxtronik.writes) == 1
