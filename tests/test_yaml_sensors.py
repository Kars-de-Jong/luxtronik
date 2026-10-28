"""Test the sensors configured with the YAML platforms."""
from homeassistant.const import CONF_BINARY_SENSORS, CONF_HOST, CONF_PORT, CONF_SENSORS
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik import _async_sync_yaml_sensors
from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)

SERIAL = "2311_1234_abcd"
FLOW = f"sensor.{DOMAIN}_ID_WEB_Temperatur_TVL"
RETURN = f"sensor.{DOMAIN}_ID_WEB_Temperatur_TRL"
EVU = f"sensor.{DOMAIN}_ID_WEB_EVUin"

CONFIG = {
    "sensor": [{
        "platform": DOMAIN,
        "sensors": [
            {"id": "calculations.ID_WEB_Temperatur_TVL", "friendly_name": "Flow"},
            {"group": "calculations", "id": "ID_WEB_Temperatur_TRL", "friendly_name": "Return"},
        ],
    }],
    "binary_sensor": [{
        "platform": DOMAIN,
        "sensors": [{"id": "calculations.ID_WEB_EVUin", "friendly_name": "EVU", "invert": True}],
    }],
}


def _add_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    return entry


async def _restart(hass, entry, config):
    """Sync the YAML of a restart and set up the entry again."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    _async_sync_yaml_sensors(hass, config)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_yaml_sensors_belong_to_heatpump(hass, luxtronik, caplog):
    """Sensors configured in YAML are created by the config entry, on the heatpump device."""
    entry = _add_entry(hass)
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    assert await async_setup_component(hass, "sensor", CONFIG)
    assert await async_setup_component(hass, "binary_sensor", CONFIG)
    await hass.async_block_till_done()

    assert entry.options[CONF_SENSORS] == [
        {"id": "calculations.ID_WEB_Temperatur_TVL", "friendly_name": "Flow"},
        {"id": "calculations.ID_WEB_Temperatur_TRL", "friendly_name": "Return"},
    ]
    assert entry.options[CONF_BINARY_SENSORS] == [
        {"id": "calculations.ID_WEB_EVUin", "friendly_name": "EVU", "invert": True}]

    heatpump = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, f"{SERIAL}_heatpump"), entry.entry_id)
    ent_reg = er.async_get(hass)
    for domain, unique_id, name in [
        ("sensor", FLOW, "Flow"), ("sensor", RETURN, "Return"), ("binary_sensor", EVU, "EVU")
    ]:
        entity_id = ent_reg.async_get_entity_id(domain, DOMAIN, unique_id)
        # Home Assistant puts the device name in front of the name of the sensor.
        assert hass.states.get(entity_id).name == f"Heatpump 2311-1234 {name}"
        assert ent_reg.async_get(entity_id).device_id == heatpump.id
        assert ent_reg.async_get(entity_id).config_entry_id == entry.entry_id
    entity_id = ent_reg.async_get_entity_id("binary_sensor", DOMAIN, EVU)
    assert hass.states.get(entity_id).state == "off"
    assert "attach a device to an entity without a config entry" not in caplog.text


async def test_yaml_sensor_keeps_entity_id(hass, luxtronik):
    """A sensor created by the YAML platform keeps its entity_id and gets the device."""
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_or_create(
        "sensor", DOMAIN, FLOW, suggested_object_id="luxtronik_flow").entity_id
    entry = _add_entry(hass)
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, FLOW) == entity_id
    assert ent_reg.async_get(entity_id).config_entry_id == entry.entry_id
    assert ent_reg.async_get(entity_id).device_id is not None
    assert hass.states.get(entity_id).name == "Heatpump 2311-1234 Flow"


async def test_removed_yaml_sensors_are_removed(hass, luxtronik):
    """Sensors removed from the YAML are removed at the next start."""
    entry = _add_entry(hass)
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, RETURN) is not None

    config = {"sensor": [{"platform": DOMAIN, "sensors": [CONFIG["sensor"][0]["sensors"][0]]}]}
    await _restart(hass, entry, config)

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, FLOW) is not None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, RETURN) is None
    assert ent_reg.async_get_entity_id("binary_sensor", DOMAIN, EVU) is None
    assert CONF_BINARY_SENSORS not in entry.options

    await _restart(hass, entry, {})

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, FLOW) is None
    assert CONF_SENSORS not in entry.options


async def test_ignored_yaml_options(hass, luxtronik, caplog):
    """Invalid sensors and platform options that no longer apply are logged."""
    entry = _add_entry(hass)
    _async_sync_yaml_sensors(hass, {"sensor": [{
        "platform": DOMAIN,
        "scan_interval": 60,
        "sensors": [{"id": "ID_WEB_Temperatur_TVL"}, {"id": "calculations.ID_WEB_Temperatur_TRL", "bogus": 1}],
    }]})

    assert CONF_SENSORS not in entry.options
    assert "Option scan_interval of the luxtronik2 sensor platform is ignored" in caplog.text
    assert "ID_WEB_Temperatur_TVL has no group" in caplog.text
    assert "bogus" in caplog.text


async def test_yaml_platform_without_entry(hass, luxtronik, caplog):
    """Sensors configured in YAML are skipped when there is no config entry."""
    assert await async_setup_component(hass, "sensor", {"sensor": [{
        "platform": DOMAIN,
        "sensors": [{"id": "calculations.ID_WEB_Temperatur_TVL"}],
    }]})
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == []
    assert "no luxtronik" in caplog.text
