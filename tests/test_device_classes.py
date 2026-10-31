"""Test that entities only use device classes and units Home Assistant knows."""
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)
from homeassistant.helpers import entity_registry as er

from .conftest import SERIAL


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_device_classes(hass, luxtronik):
    """Climate entities have no device class, switches only switch device classes."""
    await _setup(hass)

    climates = hass.states.async_all("climate")
    switches = hass.states.async_all("switch")
    assert climates and switches
    for state in climates:
        assert ATTR_DEVICE_CLASS not in state.attributes, state.entity_id
    for state in switches:
        assert state.attributes.get(ATTR_DEVICE_CLASS) in (None, *SwitchDeviceClass), state.entity_id


async def test_compressor_impulses_have_no_unit(hass, luxtronik):
    """A count has no unit of measurement."""
    await _setup(hass)

    ent_reg = er.async_get(hass)
    for key in ("compressor_impulses", "compressor_impulses2"):
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{key}")
        assert entity_id, key
        assert ATTR_UNIT_OF_MEASUREMENT not in hass.states.get(entity_id).attributes, key
