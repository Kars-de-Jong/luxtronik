"""Test the climate platform setup."""
import pytest
from homeassistant.components.climate import (ATTR_CURRENT_TEMPERATURE, ATTR_HVAC_ACTION,
                                              ATTR_HVAC_MODE, ATTR_PRESET_MODE,
                                              DOMAIN as CLIMATE_DOMAIN, PRESET_AWAY,
                                              PRESET_BOOST, PRESET_NONE, SERVICE_SET_HVAC_MODE,
                                              SERVICE_SET_PRESET_MODE, SERVICE_SET_TEMPERATURE,
                                              HVACAction, HVACMode)
from homeassistant.const import (ATTR_ENTITY_ID, ATTR_ICON, ATTR_TEMPERATURE, CONF_HOST,
                                 CONF_PORT)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (
    CONF_CONTROL_MODE_HOME_ASSISTANT, CONF_HA_SENSOR_INDOOR_TEMPERATURE, CONF_LOCK_TIMEOUT,
    CONF_SAFE, CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
    LUX_BINARY_SENSOR_CIRCULATION_PUMP_HEATING,
    LUX_BINARY_SENSOR_DOMESTIC_WATER_RECIRCULATION_PUMP, LUX_SENSOR_COOLING_THRESHOLD,
    LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE, LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE,
    LUX_SENSOR_HEATING_TARGET_CORRECTION, LUX_SENSOR_MODE_COOLING,
    LUX_SENSOR_MODE_DOMESTIC_WATER, LUX_SENSOR_MODE_HEATING, LUX_SENSOR_OUTDOOR_TEMPERATURE,
    LUX_SENSOR_STATUS, LUX_SENSOR_STATUS1, LUX_SENSOR_STATUS3, LUX_STATUS1_PUMP_FORERUN,
    LUX_STATUS_COOLING, LUX_STATUS_DEFROST, LUX_STATUS_DOMESTIC_WATER, LUX_STATUS_HEATING,
    LUX_STATUS_HEATING_EXTERNAL_SOURCE, LUX_STATUS_NO_REQUEST, LUX_STATUS_SWIMMING_POOL_SOLAR,
    PRESET_SECOND_HEATSOURCE)

from .conftest import MODE_SENSORS, SERIAL

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


@pytest.mark.parametrize("state", ["unavailable", "unknown", "not a number", "nan"])
async def test_indoor_temperature_sensor_without_number(hass, luxtronik, state):
    """A source sensor without a numeric state gives no current temperature."""
    hass.states.async_set("sensor.indoor", state)
    data = {**DATA, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.indoor"}
    entry = MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("climate", DOMAIN, f"{SERIAL}_heating")
    assert hass.states.get(entity_id).attributes["current_temperature"] is None


HEATING = "climate.heatpump_2311_1234_heating"
DOMESTIC_WATER = "climate.heatpump_2311_1234_domestic_water"
COOLING = "climate.heatpump_2311_1234_cooling"


@pytest.fixture
def values(luxtronik):
    """Values of the mocked heatpump; a write stores the value, like the device does."""
    values = {LUX_SENSOR_STATUS: LUX_STATUS_NO_REQUEST}
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
    entry = MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data=DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass, entry):
    entry.runtime_data.coordinator.async_update_listeners()
    await hass.async_block_till_done()


@pytest.mark.parametrize(("entity_id", "changes", "action"), [
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_HEATING}, HVACAction.HEATING),
    # The heatpump reports heating during the pump forerun, while nothing is requested.
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_HEATING, LUX_SENSOR_STATUS1: LUX_STATUS1_PUMP_FORERUN,
               LUX_SENSOR_STATUS3: LUX_STATUS_NO_REQUEST}, HVACAction.IDLE),
    (DOMESTIC_WATER, {LUX_SENSOR_STATUS: LUX_STATUS_HEATING}, HVACAction.IDLE),
    (DOMESTIC_WATER, {LUX_SENSOR_STATUS: LUX_STATUS_DOMESTIC_WATER}, HVACAction.HEATING),
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_SWIMMING_POOL_SOLAR}, HVACAction.HEATING),
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_HEATING_EXTERNAL_SOURCE}, HVACAction.HEATING),
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_COOLING}, HVACAction.COOLING),
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_DEFROST,
               LUX_BINARY_SENSOR_CIRCULATION_PUMP_HEATING: True}, HVACAction.HEATING),
    (HEATING, {LUX_SENSOR_STATUS: LUX_STATUS_DEFROST,
               LUX_BINARY_SENSOR_CIRCULATION_PUMP_HEATING: False}, HVACAction.IDLE),
    (DOMESTIC_WATER, {LUX_SENSOR_STATUS: LUX_STATUS_DEFROST,
                      LUX_BINARY_SENSOR_DOMESTIC_WATER_RECIRCULATION_PUMP: True}, HVACAction.HEATING),
    (DOMESTIC_WATER, {LUX_SENSOR_STATUS: LUX_STATUS_DEFROST,
                      LUX_BINARY_SENSOR_DOMESTIC_WATER_RECIRCULATION_PUMP: False}, HVACAction.IDLE),
    (HEATING, {LUX_SENSOR_MODE_HEATING: "Off"}, HVACAction.OFF),
    (HEATING, {LUX_SENSOR_MODE_HEATING: "Off", LUX_SENSOR_STATUS: LUX_STATUS_SWIMMING_POOL_SOLAR},
     HVACAction.OFF),
    (COOLING, {}, HVACAction.IDLE),
    (COOLING, {LUX_SENSOR_STATUS: LUX_STATUS_COOLING}, HVACAction.COOLING),
])
async def test_hvac_action(hass, values, entity_id, changes, action):
    """The action follows the status of the heatpump and the mode of the circuit."""
    entry = await _setup(hass)
    values.update(changes)
    await _refresh(hass, entry)

    assert hass.states.get(entity_id).attributes[ATTR_HVAC_ACTION] == action


@pytest.mark.parametrize(("mode", "state", "preset"), [
    ("Automatic", HVACMode.AUTO, PRESET_NONE),
    ("Off", HVACMode.OFF, PRESET_NONE),
    ("Party", HVACMode.AUTO, PRESET_BOOST),
    ("Holidays", HVACMode.AUTO, PRESET_AWAY),
    ("Second heatsource", HVACMode.AUTO, PRESET_SECOND_HEATSOURCE),
])
async def test_mode_and_preset(hass, values, mode, state, preset):
    """The mode of the heatpump circuit gives the HVAC mode and the preset."""
    entry = await _setup(hass)
    values[LUX_SENSOR_MODE_HEATING] = mode
    await _refresh(hass, entry)

    heating = hass.states.get(HEATING)
    assert heating.state == state
    assert heating.attributes[ATTR_PRESET_MODE] == preset


async def test_temperatures(hass, values):
    """The circuits show the temperatures of the heatpump."""
    values.update({
        LUX_SENSOR_HEATING_TARGET_CORRECTION: 1.5,
        LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE: 48.0,
        LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE: 45.5,
        LUX_SENSOR_COOLING_THRESHOLD: 24.0,
        LUX_SENSOR_OUTDOOR_TEMPERATURE: 26.5,
    })
    await _setup(hass)

    assert hass.states.get(HEATING).attributes[ATTR_TEMPERATURE] == 1.5
    assert hass.states.get(DOMESTIC_WATER).attributes[ATTR_TEMPERATURE] == 48.0
    assert hass.states.get(DOMESTIC_WATER).attributes[ATTR_CURRENT_TEMPERATURE] == 45.5
    assert hass.states.get(COOLING).attributes[ATTR_TEMPERATURE] == 24.0
    assert hass.states.get(COOLING).attributes[ATTR_CURRENT_TEMPERATURE] == 26.5


async def test_set_heating_temperature(hass, values):
    """The heating target temperature is written to the heating curve correction."""
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: HEATING, ATTR_TEMPERATURE: 2.5}, blocking=True)

    assert values.get(LUX_SENSOR_HEATING_TARGET_CORRECTION) == 2.5
    assert hass.states.get(HEATING).attributes[ATTR_TEMPERATURE] == 2.5


@pytest.mark.parametrize(("entity_id", "mode_sensor", "hvac_mode", "written"), [
    (HEATING, LUX_SENSOR_MODE_HEATING, HVACMode.OFF, "Off"),
    (DOMESTIC_WATER, LUX_SENSOR_MODE_DOMESTIC_WATER, HVACMode.OFF, "Off"),
    (COOLING, LUX_SENSOR_MODE_COOLING, HVACMode.OFF, "Off"),
])
async def test_set_hvac_mode(hass, luxtronik, values, entity_id, mode_sensor, hvac_mode, written):
    """Turning a circuit off writes its mode."""
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: hvac_mode}, blocking=True)

    assert luxtronik.writes == [(mode_sensor.split(".")[1], written)]
    assert hass.states.get(entity_id).state == hvac_mode


async def test_set_hvac_mode_auto_keeps_preset(hass, luxtronik, values):
    """Turning a circuit on writes the mode of its preset."""
    values[LUX_SENSOR_MODE_HEATING] = "Off"
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: HEATING, ATTR_HVAC_MODE: HVACMode.AUTO}, blocking=True)

    assert luxtronik.writes == [("ID_Ba_Hz_akt", "Automatic")]
    assert hass.states.get(HEATING).state == HVACMode.AUTO


async def test_set_same_hvac_mode_writes_nothing(hass, luxtronik, values):
    """Setting the mode a circuit already has writes nothing."""
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: HEATING, ATTR_HVAC_MODE: HVACMode.AUTO}, blocking=True)

    assert luxtronik.writes == []


@pytest.mark.parametrize(("preset", "written"), [
    (PRESET_AWAY, "Holidays"),
    (PRESET_BOOST, "Party"),
    (PRESET_SECOND_HEATSOURCE, "Second heatsource"),
    (PRESET_NONE, "Automatic"),
])
async def test_set_preset_mode(hass, luxtronik, values, preset, written):
    """A preset writes the matching mode of the circuit."""
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: DOMESTIC_WATER, ATTR_PRESET_MODE: preset}, blocking=True)

    assert luxtronik.writes == [("ID_Ba_Bw_akt", written)]
    assert hass.states.get(DOMESTIC_WATER).attributes[ATTR_PRESET_MODE] == preset


async def test_set_preset_mode_while_off(hass, luxtronik, values):
    """A circuit that is off stays off when a preset is chosen."""
    values[LUX_SENSOR_MODE_HEATING] = "Off"
    await _setup(hass)

    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: HEATING, ATTR_PRESET_MODE: PRESET_BOOST}, blocking=True)

    assert luxtronik.writes == [("ID_Ba_Hz_akt", "Off")]
    assert hass.states.get(HEATING).state == HVACMode.OFF


@pytest.mark.parametrize(("mode", "heating_icon", "domestic_water_icon"), [
    ("Automatic", "mdi:radiator", "mdi:water-boiler-auto"),
    ("Off", "mdi:radiator-off", "mdi:water-boiler-off"),
])
async def test_icons(hass, values, mode, heating_icon, domestic_water_icon):
    """The icons show whether a circuit is off."""
    values[LUX_SENSOR_MODE_HEATING] = mode
    values[LUX_SENSOR_MODE_DOMESTIC_WATER] = mode
    await _setup(hass)

    assert hass.states.get(HEATING).attributes[ATTR_ICON] == heating_icon
    assert hass.states.get(DOMESTIC_WATER).attributes[ATTR_ICON] == domestic_water_icon
    assert hass.states.get(COOLING).attributes[ATTR_ICON] == "mdi:snowflake"
