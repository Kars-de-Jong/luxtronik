"""Test config entry migration."""
import threading
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik import async_migrate_entry
from custom_components.luxtronik.const import DOMAIN

SERIAL = "2311_1234_abcd"


async def test_migrate_v1(hass):
    """Version 1 entries get the heatpump serial as unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889})
    entry.add_to_hass(hass)
    luxtronik = MagicMock(
        unique_id=SERIAL, manufacturer="Alpha Innotec", model="LWD", serial_number="2311-1234")

    with patch("custom_components.luxtronik.LuxtronikDevice.connect", return_value=luxtronik):
        assert await async_migrate_entry(hass, entry)

    assert entry.version == 3
    assert entry.unique_id == SERIAL
    assert entry.title == "Alpha Innotec LWD 2311-1234"


async def test_migrate_v1_connects_in_executor(hass):
    """The v1 migration connects to the heatpump outside the event loop.

    connect is patched with a function: the test harness runs Mock executor jobs inline.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889})
    entry.add_to_hass(hass)
    loop_thread = threading.current_thread()
    connected_in = []

    def connect(host, port):
        connected_in.append(threading.current_thread())
        return MagicMock(
            unique_id=SERIAL, manufacturer="Alpha Innotec", model="LWD", serial_number="2311-1234")

    with patch("custom_components.luxtronik.LuxtronikDevice.connect", new=connect):
        assert await async_migrate_entry(hass, entry)

    assert connected_in and loop_thread not in connected_in


async def test_migrate_v1_heatpump_unreachable(hass, caplog):
    """The migration fails, and is retried later, when the heatpump is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889})
    entry.add_to_hass(hass)

    with patch("custom_components.luxtronik.LuxtronikDevice.connect", side_effect=OSError):
        assert not await async_migrate_entry(hass, entry)

    assert entry.version == 1
    assert "10.0.0.2" in caplog.text


async def test_migrate_v1_removes_legacy_devices(hass):
    """The v1 migration removes the devices that don't belong to the heatpump."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889})
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    kept = {
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{SERIAL}_{key}")}).id
        for key in ("heatpump", "domestic_water", "heating", "cooling")
    }
    dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "Heatpump")})
    luxtronik = MagicMock(
        unique_id=SERIAL, manufacturer="Alpha Innotec", model="LWD", serial_number="2311-1234")

    with patch("custom_components.luxtronik.LuxtronikDevice.connect", return_value=luxtronik):
        assert await async_migrate_entry(hass, entry)

    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert {device.id for device in devices} == kept


async def test_migrate_v2_keeps_unknown_unique_ids(hass, caplog):
    """Unique ids that aren't legacy ids, or would clash with an existing one, are kept."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id=SERIAL)
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    kept = {
        ("sensor", "sensor.other_flow_in_temperature"),
        ("sensor", "flow_in_temperature"),
        ("sensor", f"sensor.{DOMAIN}_outdoor_temperature"),
        ("sensor", f"{SERIAL}_outdoor_temperature"),
    }
    for platform, unique_id in kept:
        ent_reg.async_get_or_create(platform, DOMAIN, unique_id, config_entry=entry)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 3
    assert {
        (entity.domain, entity.unique_id)
        for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    } == kept
    assert "it already exists" in caplog.text
