"""Test the binary sensors."""
import pytest
from homeassistant.const import ATTR_ICON, CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)

from .conftest import MODE_SENSORS, SERIAL

DEFROST_VALVE = "binary_sensor.heatpump_2311_1234_defrost_valve"


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(("circulation", "unique_id"), [
    (True, "domestic_water_circulation_pump"),
    (False, "domestic_water_charging_pump"),
])
async def test_domestic_water_pump(hass, luxtronik, circulation, unique_id):
    """The domestic water pump is a circulation pump or a charging pump, as set up."""
    luxtronik.has_domestic_water_circulation_pump = circulation
    await _setup(hass)

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{SERIAL}_{unique_id}")
    assert hass.states.get(entity_id) is not None


@pytest.mark.parametrize(("value", "state", "icon"), [
    (True, STATE_ON, "mdi:valve-open"),
    (False, STATE_OFF, "mdi:valve-closed"),
])
async def test_icon_off(hass, luxtronik, value, state, icon):
    """A binary sensor with an icon for off shows it when it is off."""
    luxtronik.get_value.side_effect = lambda key: (
        value if key == "calculations.ID_WEB_AVout"
        else "Automatic" if key in MODE_SENSORS else 1)
    await _setup(hass)

    assert hass.states.get(DEFROST_VALVE).state == state
    assert hass.states.get(DEFROST_VALVE).attributes[ATTR_ICON] == icon
