"""Test that the unique ids and entity ids of all entities stay the same."""
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)
from .conftest import SERIAL

YAML = {
    "sensor": [{"platform": DOMAIN, "sensors": [
        {"id": "calculations.ID_WEB_Temperatur_TVL", "friendly_name": "Flow"}]}],
    "binary_sensor": [{"platform": DOMAIN, "sensors": [
        {"id": "calculations.ID_WEB_EVUin", "friendly_name": "EVU"}]}],
}


async def test_entity_ids(hass, luxtronik, snapshot):
    """Every entity of the mocked heatpump, including the YAML sensors, keeps its ids."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    for component in (DOMAIN, "sensor", "binary_sensor"):
        assert await async_setup_component(hass, component, YAML)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert sorted((e.domain, e.unique_id, e.entity_id) for e in entries) == snapshot
