"""Test the data update coordinator and the availability of the entities."""
import logging
import threading
from datetime import timedelta

from homeassistant.const import CONF_HOST, CONF_PORT, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)
from custom_components.luxtronik.coordinator import LuxtronikCoordinator
from custom_components.luxtronik.update import LuxtronikUpdateEntity
from .conftest import SERIAL

# One entity of every platform that follows the heatpump data.
ENTITIES = [
    ("sensor", f"{SERIAL}_status"),
    ("binary_sensor", f"{SERIAL}_compressor"),
    ("number", f"{SERIAL}_domestic_water_thermal_desinfection_target"),
    ("switch", f"{SERIAL}_heating"),
    ("climate", f"{SERIAL}_heating"),
    ("update", f"{SERIAL}_firmware"),
]


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _states(hass):
    ent_reg = er.async_get(hass)
    return {
        key: hass.states.get(ent_reg.async_get_entity_id(platform, DOMAIN, unique_id)).state
        for key in ENTITIES
        for platform, unique_id in [key]
    }


async def test_coordinator_in_runtime_data(hass, luxtronik):
    """The coordinator is stored in the runtime data and polls every 30 seconds."""
    entry = await _setup(hass)

    coordinator = entry.runtime_data.coordinator
    assert isinstance(coordinator, LuxtronikCoordinator)
    assert coordinator.device is luxtronik
    assert coordinator.update_interval == timedelta(seconds=30)


async def test_read_runs_in_executor(hass, luxtronik):
    """The coordinator reads the heatpump in the executor."""
    entry = await _setup(hass)
    threads = []
    luxtronik.read = lambda: threads.append(threading.get_ident())

    await entry.runtime_data.coordinator.async_refresh()

    assert threads
    assert hass.loop_thread_id not in threads


async def test_one_read_per_refresh(hass, luxtronik):
    """All entities share one read of the heatpump."""
    entry = await _setup(hass)
    luxtronik.read.reset_mock()

    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    luxtronik.read.assert_called_once_with()
    luxtronik.update.assert_not_called()


async def test_entities_unavailable_when_read_fails(hass, luxtronik, caplog):
    """Entities go unavailable when the heatpump can't be read, and come back after."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    assert STATE_UNAVAILABLE not in _states(hass).values()

    luxtronik.read.side_effect = OSError("Connection refused")
    with caplog.at_level(logging.INFO):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert set(_states(hass).values()) == {STATE_UNAVAILABLE}
    assert caplog.text.count("Connection refused") == 1

    caplog.clear()
    luxtronik.read.side_effect = None
    with caplog.at_level(logging.INFO):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert STATE_UNAVAILABLE not in _states(hass).values()
    assert caplog.text.count("recovered") == 1


async def test_entities_unavailable_on_lock_timeout(hass, luxtronik):
    """A read that times out on the lock fails the update as well."""
    entry = await _setup(hass)

    luxtronik.read.side_effect = TimeoutError("lock timeout")
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert set(_states(hass).values()) == {STATE_UNAVAILABLE}


async def test_unload_stops_reading(hass, luxtronik):
    """After unloading, the heatpump is no longer read and no listeners are left."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data.coordinator
    assert coordinator._listeners

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    luxtronik.read.reset_mock()
    # The conftest fixture replaces the request to the download portal with a mock.
    fetch = LuxtronikUpdateEntity._async_fetch_latest_version
    fetch.reset_mock()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done()

    luxtronik.read.assert_not_called()
    fetch.assert_not_called()
    assert not coordinator._listeners
    luxtronik.disconnect.assert_called_once_with()
