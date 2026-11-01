"""Test the sensors."""
from datetime import datetime

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.luxtronik.const import (ATTR_STATUS_TEXT, CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              LUX_BINARY_SENSOR_ADDITIONAL_CIRCULATION_PUMP,
                                              LUX_SENSOR_MODE_COOLING, LUX_SENSOR_STATUS,
                                              LUX_SENSOR_STATUS1, LUX_SENSOR_STATUS3,
                                              LUX_STATUS1_HEATPUMP_COMING,
                                              LUX_STATUS1_HEATPUMP_SHUTDOWN,
                                              LUX_STATUS1_PUMP_FORERUN, LUX_STATUS_COOLING,
                                              LUX_STATUS_DOMESTIC_WATER, LUX_STATUS_EVU,
                                              LUX_STATUS_HEATING, LUX_STATUS_NO_REQUEST,
                                              LUX_STATUS_THERMAL_DESINFECTION)

from .conftest import MODE_SENSORS, SERIAL

STATUS_TIME = "calculations.ID_WEB_HauptMenuStatus_Zeit"
COOLING_ACTIVE = {
    LUX_SENSOR_STATUS: LUX_STATUS_NO_REQUEST,
    LUX_SENSOR_MODE_COOLING: "Automatic",
    "calculations.ID_WEB_VBOout": True,
    "calculations.ID_WEB_Temperatur_TVL": 20.0,
    "calculations.ID_WEB_Temperatur_TRL": 22.0,
    "calculations.ID_WEB_Temperatur_TWE": 10.0,
    "calculations.ID_WEB_Temperatur_TWA": 12.0,
    "calculations.ID_WEB_Durchfluss_WQ": 1.5,
}
EVU_TIMES = ("EVU first start time", "EVU first end time",
             "EVU second start time", "EVU second end time")


@pytest.fixture
def values(luxtronik):
    """Values of the mocked heatpump."""
    values = {LUX_SENSOR_STATUS: LUX_STATUS_NO_REQUEST}
    luxtronik.get_value.side_effect = lambda key: values.get(
        key, "Automatic" if key in MODE_SENSORS else 1)
    return values


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    return entry


async def _setup(hass):
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass, entry):
    entry.runtime_data.coordinator.async_update_listeners()
    await hass.async_block_till_done()


def _state(hass, key):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{key}")
    return hass.states.get(entity_id)


@pytest.mark.parametrize(("changes", "status"), [
    ({}, LUX_STATUS_NO_REQUEST),
    # Thermal disinfection heats the domestic water.
    ({LUX_SENSOR_STATUS: LUX_STATUS_HEATING, LUX_SENSOR_STATUS3: LUX_STATUS_THERMAL_DESINFECTION},
     LUX_STATUS_DOMESTIC_WATER),
    # The heatpump reports heating during the pump forerun, while nothing is requested.
    ({LUX_SENSOR_STATUS: LUX_STATUS_HEATING, LUX_SENSOR_STATUS1: LUX_STATUS1_PUMP_FORERUN,
      LUX_SENSOR_STATUS3: LUX_STATUS_NO_REQUEST,
      LUX_BINARY_SENSOR_ADDITIONAL_CIRCULATION_PUMP: False}, LUX_STATUS_NO_REQUEST),
    ({LUX_SENSOR_STATUS: LUX_STATUS_HEATING, LUX_SENSOR_STATUS1: LUX_STATUS1_PUMP_FORERUN,
      LUX_SENSOR_STATUS3: LUX_STATUS_NO_REQUEST,
      LUX_BINARY_SENSOR_ADDITIONAL_CIRCULATION_PUMP: True}, LUX_STATUS_HEATING),
    # Passive cooling isn't reported by the heatpump, but shows in the temperatures.
    (COOLING_ACTIVE, LUX_STATUS_COOLING),
    (COOLING_ACTIVE | {"calculations.ID_WEB_Durchfluss_WQ": 0}, LUX_STATUS_NO_REQUEST),
    (COOLING_ACTIVE | {LUX_SENSOR_MODE_COOLING: "Off"}, LUX_STATUS_NO_REQUEST),
])
async def test_status(hass, values, changes, status):
    """The status corrects what the heatpump reports in some situations."""
    entry = await _setup(hass)
    values.update(changes)
    await _refresh(hass, entry)

    assert _state(hass, "status").state == status


@pytest.mark.parametrize(("switch_on_lock", "line_1"), [
    (5, LUX_STATUS1_HEATPUMP_SHUTDOWN),
    (20, LUX_STATUS1_HEATPUMP_COMING),
])
async def test_status_line_1_shutdown(hass, values, switch_on_lock, line_1):
    """Line 1 shows a shutdown that the heatpump reports as coming."""
    values.update({
        LUX_SENSOR_STATUS1: LUX_STATUS1_HEATPUMP_COMING,
        "calculations.ID_WEB_Time_SSPEIN_akt": switch_on_lock,
        "calculations.ID_WEB_Time_SSPAUS_akt": 30,
    })
    await _setup(hass)

    assert _state(hass, "status_line_1").state == line_1


@pytest.mark.parametrize(("seconds", "text"), [(3720, "1:02 h"), (None, None)])
async def test_status_time_text(hass, values, seconds, text):
    """The status time is also shown as hours and minutes."""
    entry = await _setup(hass)
    values[STATUS_TIME] = seconds
    await _refresh(hass, entry)

    assert _state(hass, "status_time").attributes[ATTR_STATUS_TEXT] == text


async def test_sensor_disabled_when_inactive(hass, values):
    """A sensor for a part that the heatpump doesn't show is disabled by default."""
    values["visibilities.ID_Visi_Waermemenge_ZWE"] = 0
    await _setup(hass)

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{SERIAL}_additional_heat_generator_amount_counter")
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_timestamps_in_local_time(hass, luxtronik, values):
    """Times without a time zone from the heatpump are in the time zone of Home Assistant."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    local = datetime(2026, 10, 1, 12, 0)
    expected = local.replace(tzinfo=dt_util.get_time_zone("Europe/Amsterdam"))
    values["calculations.ID_WEB_ERROR_Time0"] = local
    values["calculations.ID_WEB_ERROR_Time1"] = local
    luxtronik.get_sensor.return_value.measurement_type = "timestamp"
    _entry(hass)
    assert await async_setup_component(hass, DOMAIN, {"sensor": [{
        "platform": DOMAIN, "sensors": [{"id": "calculations.ID_WEB_ERROR_Time1", "friendly_name": "Error"}]}]})
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"sensor.{DOMAIN}_ID_WEB_ERROR_Time1")
    assert hass.states.get(entity_id).state == "2026-10-01T10:00:00+00:00"
    assert _state(hass, "error_reason").attributes["timestamp"] == expected


async def _status_at(hass, freezer, entry, values, at, status):
    freezer.move_to(at)
    values[LUX_SENSOR_STATUS] = status
    await _refresh(hass, entry)
    return _state(hass, "status").attributes


async def test_evu_lock_times(hass, values, freezer):
    """The status sensor learns the times of the two daily locks by the energy company."""
    freezer.move_to("2026-10-01 10:00:00+00:00")
    entry = await _setup(hass)
    await _refresh(hass, entry)

    for at, status in [
        ("2026-10-01 11:00:00+00:00", LUX_STATUS_EVU),
        ("2026-10-01 13:00:00+00:00", LUX_STATUS_NO_REQUEST),
        ("2026-10-01 17:00:00+00:00", LUX_STATUS_EVU),
    ]:
        await _status_at(hass, freezer, entry, values, at, status)
    attributes = await _status_at(
        hass, freezer, entry, values, "2026-10-01 19:00:00+00:00", LUX_STATUS_NO_REQUEST)

    assert [attributes[key] for key in EVU_TIMES] == ["11:00", "13:00", "17:00", "19:00"]
    # The next lock starts at 11:00 tomorrow.
    assert attributes["EVU minutes until next event"] == str(16 * 60)

    # The status text uses the status time, which is updated after the status.
    await _refresh(hass, entry)
    attributes = await _status_at(
        hass, freezer, entry, values, "2026-10-02 10:45:00+00:00", LUX_STATUS_NO_REQUEST)
    assert attributes[ATTR_STATUS_TEXT] == "1 1 0:00 h. Locktime in 15 minutes."

    attributes = await _status_at(
        hass, freezer, entry, values, "2026-10-02 11:00:00+00:00", LUX_STATUS_EVU)
    assert attributes["EVU first start time"] == "11:00"
    assert attributes[ATTR_STATUS_TEXT] == "120 minutes more locktime. 1 1 0:00 h."

    attributes = await _status_at(
        hass, freezer, entry, values, "2026-10-02 12:00:00+00:00", LUX_STATUS_EVU)
    assert attributes[ATTR_STATUS_TEXT] == "60 minutes more locktime. 1 1 0:00 h."


async def test_evu_lock_times_restored(hass, values):
    """The learned lock times are restored after a restart."""
    times = ["11:00", "13:00", "", ""]
    mock_restore_cache(hass, [State(
        "sensor.heatpump_2311_1234_status", LUX_STATUS_NO_REQUEST, dict(zip(EVU_TIMES, times)))])
    await _setup(hass)

    attributes = _state(hass, "status").attributes
    assert [attributes[key] for key in EVU_TIMES] == times


async def test_evu_lock_start_without_known_end(hass, values, freezer):
    """A lock that starts while the end of the first lock is unknown is stored.

    This happens when Home Assistant wasn't running when the first lock ended.
    """
    mock_restore_cache(hass, [State(
        "sensor.heatpump_2311_1234_status", LUX_STATUS_NO_REQUEST,
        dict(zip(EVU_TIMES, ["11:00", "", "", ""])))])
    freezer.move_to("2026-10-01 16:00:00+00:00")
    entry = await _setup(hass)
    await _refresh(hass, entry)

    attributes = await _status_at(
        hass, freezer, entry, values, "2026-10-01 17:00:00+00:00", LUX_STATUS_EVU)

    assert _state(hass, "status").state == LUX_STATUS_EVU
    assert attributes["EVU first start time"] == "17:00"
