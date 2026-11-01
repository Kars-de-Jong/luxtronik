"""Test writing to the heatpump from the entities."""
import threading
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import (ATTR_HVAC_MODE, SERVICE_SET_HVAC_MODE,
                                              SERVICE_SET_TEMPERATURE,
                                              HVACMode)
from homeassistant.components.number import ATTR_VALUE as NUMBER_ATTR_VALUE
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (ATTR_CONFIG_ENTRY_ID, ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_HOST, CONF_PORT,
                                 SERVICE_TURN_ON, STATE_OFF, STATE_ON)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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


OTHER_SERIAL = "2311_5678_abcd"


@pytest.fixture
def other_luxtronik(luxtronik):
    """A second heatpump; the first config entry gets `luxtronik`, the second this one."""
    other = MagicMock(
        unique_id=OTHER_SERIAL, serial_number="2311-5678", manufacturer="Alpha Innotec",
        model="LWD", firmware_version_minor=99, has_domestic_water_circulation_pump=True)
    other.get_value.side_effect = lambda key: "Automatic" if key in MODE_SENSORS else 1
    other.detect_cooling_target_temperature_sensor.return_value = None
    other.write.return_value = True
    with patch("custom_components.luxtronik.LuxtronikDevice", side_effect=[luxtronik, other]):
        yield other


async def _setup_other(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=OTHER_SERIAL,
        data={CONF_HOST: "10.0.0.3", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_write_action_to_chosen_heatpump(hass, luxtronik, values, other_luxtronik):
    """The write action writes to the heatpump of the config entry it is given."""
    await _setup(hass)
    other = await _setup_other(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_WRITE,
        {ATTR_CONFIG_ENTRY_ID: other.entry_id, ATTR_PARAMETER: "ID_Ba_Hz_akt",
         ATTR_VALUE: "Party"},
        blocking=True)
    await _wait(hass, 3)

    assert luxtronik.writes == []
    other_luxtronik.write.assert_called_once_with("ID_Ba_Hz_akt", "Party")


async def test_write_action_defaults_to_first_heatpump(hass, luxtronik, values, other_luxtronik):
    """Without a config entry the write action writes to the first loaded heatpump."""
    await _setup(hass)
    await _setup_other(hass)

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    await _wait(hass, 3)

    assert [w[:2] for w in luxtronik.writes] == [("ID_Ba_Hz_akt", "Party")]
    other_luxtronik.write.assert_not_called()


async def test_write_action_unknown_config_entry(hass, luxtronik, values):
    """The write action fails for a config entry that doesn't exist."""
    await _setup(hass)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_WRITE,
            {ATTR_CONFIG_ENTRY_ID: "does_not_exist", ATTR_PARAMETER: "ID_Ba_Hz_akt",
             ATTR_VALUE: "Party"},
            blocking=True)

    assert err.value.translation_key == "service_config_entry_not_found"
    await _wait(hass, 3)
    assert luxtronik.writes == []


async def test_write_action_config_entry_of_other_integration(hass, luxtronik, values):
    """The write action fails for a config entry of another integration."""
    await _setup(hass)
    entry = MockConfigEntry(domain="other_domain")
    entry.add_to_hass(hass)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_WRITE,
            {ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_PARAMETER: "ID_Ba_Hz_akt",
             ATTR_VALUE: "Party"},
            blocking=True)

    assert err.value.translation_key == "service_config_entry_wrong_domain"


async def test_write_action_unloaded_config_entry(hass, luxtronik, values, other_luxtronik):
    """The write action fails for a config entry that isn't loaded."""
    await _setup(hass)
    other = await _setup_other(hass)
    assert await hass.config_entries.async_unload(other.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_WRITE,
            {ATTR_CONFIG_ENTRY_ID: other.entry_id, ATTR_PARAMETER: "ID_Ba_Hz_akt",
             ATTR_VALUE: "Party"},
            blocking=True)

    assert err.value.translation_key == "service_config_entry_not_loaded"
    await _wait(hass, 3)
    assert luxtronik.writes == []
    other_luxtronik.write.assert_not_called()


async def test_write_action_without_loaded_heatpump(hass, luxtronik, values):
    """Without a config entry the write action fails when no heatpump is loaded."""
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await _write_action(hass, "ID_Ba_Hz_akt", "Party")

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "no_loaded_entry"


async def test_write_action_unknown_parameter(hass, luxtronik, values):
    """The write action fails for an unknown parameter and writes nothing."""
    await _setup(hass)
    luxtronik.has_parameter.side_effect = lambda parameter: parameter != "ID_Does_Not_Exist"

    with pytest.raises(ServiceValidationError) as err:
        await _write_action(hass, "ID_Does_Not_Exist", "1")

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "unknown_parameter"
    assert err.value.translation_placeholders == {"parameter": "ID_Does_Not_Exist"}
    await _wait(hass, 3)
    assert luxtronik.writes == []


async def test_write_action_read_only_parameter(hass, luxtronik, values):
    """The write action fails for a parameter that safe mode doesn't allow to write."""
    await _setup(hass)
    luxtronik.is_writable.return_value = False

    with pytest.raises(ServiceValidationError) as err:
        await _write_action(hass, "ID_Ba_Al_akt", "1")

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "read_only_parameter"
    assert err.value.translation_placeholders == {"parameter": "ID_Ba_Al_akt"}
    await _wait(hass, 3)
    assert luxtronik.writes == []


async def test_write_action_invalid_value(hass, luxtronik, values):
    """The write action fails for a value the parameter doesn't accept and writes nothing."""
    await _setup(hass)
    luxtronik.is_valid_value.return_value = False

    with pytest.raises(ServiceValidationError) as err:
        await _write_action(hass, "ID_Ba_Hz_akt", "party")

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "invalid_value"
    assert err.value.translation_placeholders == {"parameter": "ID_Ba_Hz_akt", "value": "party"}
    luxtronik.is_valid_value.assert_called_once_with("ID_Ba_Hz_akt", "party")
    await _wait(hass, 3)
    assert luxtronik.writes == []


@pytest.mark.parametrize(("value", "written"), [
    ("19.0", 19), ("19", 19), ("19.5", 19.5), (" 19 ", 19), (20, 20), ("Automatic", "Automatic"),
    ("nan", "nan"), ("inf", "inf"),
])
async def test_write_action_converts_numbers(hass, luxtronik, values, value, written):
    """The text field sends numbers as text; they are written as numbers."""
    await _setup(hass)

    await _write_action(hass, "ID_Ba_Hz_akt", value)
    await _wait(hass, 3)

    assert luxtronik.writes[0][:2] == ("ID_Ba_Hz_akt", written)
    assert type(luxtronik.writes[0][1]) is type(written)
    luxtronik.is_valid_value.assert_called_once_with("ID_Ba_Hz_akt", written)


def _fail_writes(luxtronik, error=None):
    """Let the writes fail: raise `error`, or reject the value when it is None."""
    def write(parameter, value, *args, **kwargs):
        luxtronik.writes.append((parameter, value, threading.get_ident()))
        if error is not None:
            raise error
        return False

    luxtronik.write = write


@pytest.mark.parametrize(("error", "translation_key", "placeholders"), [
    (None, "invalid_value", {"parameter": "ID_Einst_Fernwartung_akt", "value": "True"}),
    (TimeoutError("lock timeout 30"), "write_failed",
     {"parameter": "ID_Einst_Fernwartung_akt", "error": "lock timeout 30"}),
    (ConnectionRefusedError("refused"), "write_failed",
     {"parameter": "ID_Einst_Fernwartung_akt", "error": "refused"}),
])
async def test_switch_write_fails(hass, luxtronik, values, error, translation_key, placeholders):
    """A failed write raises an error; the switch keeps its state and the heatpump isn't read."""
    await _setup(hass)
    luxtronik.read.reset_mock()
    _fail_writes(luxtronik, error)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: REMOTE_MAINTENANCE}, blocking=True)

    assert not isinstance(err.value, ServiceValidationError)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == placeholders
    assert hass.states.get(REMOTE_MAINTENANCE).state == STATE_OFF
    await _wait(hass, 3)
    luxtronik.read.assert_not_called()


async def test_climate_hvac_mode_not_kept_when_write_fails(hass, luxtronik, values):
    """After a failed write the same HVAC mode can be set again."""
    await _setup(hass)
    _fail_writes(luxtronik, TimeoutError("lock timeout 30"))

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: DOMESTIC_WATER, ATTR_HVAC_MODE: HVACMode.OFF}, blocking=True)
    assert hass.states.get(DOMESTIC_WATER).state == HVACMode.AUTO

    luxtronik.write = lambda parameter, value: luxtronik.writes.append((parameter, value)) or True
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: DOMESTIC_WATER, ATTR_HVAC_MODE: HVACMode.OFF}, blocking=True)
    assert [w[:2] for w in luxtronik.writes] == [("ID_Ba_Bw_akt", "Off"), ("ID_Ba_Bw_akt", "Off")]


async def test_debounced_write_failure_is_logged(hass, luxtronik, values, caplog):
    """A debounced write fails after the action returned, so the error is logged."""
    await _setup(hass)
    _fail_writes(luxtronik, TimeoutError("lock timeout 30"))

    await _write_action(hass, "ID_Ba_Hz_akt", "Party")
    await _wait(hass, 3)

    assert len(luxtronik.writes) == 1
    assert "Couldn't write parameter ID_Ba_Hz_akt: lock timeout 30" in caplog.text


async def test_number_without_value(hass, luxtronik, values):
    """A number the heatpump has no value for is unknown."""
    values["parameters.ID_Einst_LGST_akt"] = None
    await _setup(hass)

    assert hass.states.get(THERMAL_DESINFECTION).state == "unknown"
