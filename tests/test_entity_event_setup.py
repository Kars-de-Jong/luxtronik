"""Test that entities unsubscribe their event listeners when removed."""
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import DATA_DISPATCHER
from pytest_homeassistant_custom_component.common import (MockConfigEntry,
                                                          mock_restore_cache)

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)

SERIAL = "2311_1234_abcd"
DATA_UPDATED = f"{DOMAIN}_data_updated"

# Entities that subscribe to the data updated signal.
SUBSCRIBERS = {
    ("sensor", f"{SERIAL}_status"): "sensor.status",
    ("number", f"{SERIAL}_domestic_water_thermal_desinfection_target"): "number.thermal_desinfection",
}


def _dispatcher_count(hass) -> int:
    return len(hass.data.get(DATA_DISPATCHER, {}).get(DATA_UPDATED, {}))


def _add_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    return entry


async def _setup_and_unload(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    subscribed = _dispatcher_count(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    return subscribed


async def test_dispatcher_subscribed_without_restored_state(hass, luxtronik):
    """Entities subscribe even without a restored state and unsubscribe on unload."""
    entry = _add_entry(hass)

    assert await _setup_and_unload(hass, entry) == len(SUBSCRIBERS)
    assert _dispatcher_count(hass) == 0


async def test_dispatcher_unsubscribed_with_restored_state(hass, luxtronik):
    """Entities with a restored state unsubscribe from the dispatcher on unload."""
    entry = _add_entry(hass)
    ent_reg = er.async_get(hass)
    for (platform, unique_id), entity_id in SUBSCRIBERS.items():
        ent_reg.async_get_or_create(
            platform, DOMAIN, unique_id, config_entry=entry,
            suggested_object_id=entity_id.split(".")[1])
    mock_restore_cache(hass, [State(entity_id, "1") for entity_id in SUBSCRIBERS.values()])

    assert await _setup_and_unload(hass, entry) == len(SUBSCRIBERS)
    assert _dispatcher_count(hass) == 0


async def test_stop_listeners_removed_on_unload(hass, luxtronik):
    """No EVENT_HOMEASSISTANT_STOP listeners are left behind after unload."""
    entry = _add_entry(hass)
    # The first setup loads the entity platforms, which register their own stop listeners.
    await _setup_and_unload(hass, entry)
    before = hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0)

    await _setup_and_unload(hass, entry)
    assert hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0) == before
