"""Test config entry migration."""
import threading
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik import async_migrate_entry
from custom_components.luxtronik.const import (CONF_HA_SENSOR_INDOOR_TEMPERATURE, CONF_LOCK_TIMEOUT,
                                               CONF_SAFE, DOMAIN)

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

    assert (entry.version, entry.minor_version) == (3, 2)
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


LEGACY_INDOOR_SENSOR = f"sensor.{DOMAIN}_room_temperature"
ROOM_SENSOR = "sensor.heatpump_2311_1234_heating_room"


def _v3_1_entry(hass, indoor_sensor=LEGACY_INDOOR_SENSOR, minor_version=1):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, minor_version=minor_version, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: False, CONF_LOCK_TIMEOUT: 30,
              CONF_HA_SENSOR_INDOOR_TEMPERATURE: indoor_sensor},
        options={CONF_HA_SENSOR_INDOOR_TEMPERATURE: indoor_sensor})
    entry.add_to_hass(hass)
    return entry


def _register_room_sensor(hass, entry, entity_id=ROOM_SENSOR):
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_room_temperature",
        suggested_object_id=entity_id.partition(".")[2], config_entry=entry)


def _indoor_sensors(entry):
    return (entry.data[CONF_HA_SENSOR_INDOOR_TEMPERATURE],
            entry.options[CONF_HA_SENSOR_INDOOR_TEMPERATURE])


async def test_migrate_v3_1_replaces_legacy_indoor_sensor(hass):
    """The old default indoor temperature sensor is replaced by the room sensor of the heatpump."""
    entry = _v3_1_entry(hass)
    _register_room_sensor(hass, entry)

    assert await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (3, 2)
    assert _indoor_sensors(entry) == (ROOM_SENSOR, ROOM_SENSOR)


async def test_migrate_v3_1_clears_legacy_indoor_sensor_without_room_sensor(hass):
    """Without a room sensor, the old default indoor temperature sensor is cleared."""
    entry = _v3_1_entry(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.minor_version == 2
    assert _indoor_sensors(entry) == (None, None)


async def test_migrate_v3_1_keeps_existing_legacy_indoor_sensor(hass):
    """Older installations kept the legacy entity id, which still works."""
    entry = _v3_1_entry(hass)
    _register_room_sensor(hass, entry, LEGACY_INDOOR_SENSOR)

    assert await async_migrate_entry(hass, entry)

    assert entry.minor_version == 2
    assert _indoor_sensors(entry) == (LEGACY_INDOOR_SENSOR, LEGACY_INDOOR_SENSOR)


async def test_migrate_v3_1_keeps_chosen_indoor_sensor(hass):
    """An indoor temperature sensor the user chose is kept."""
    entry = _v3_1_entry(hass, "sensor.living_room")
    _register_room_sensor(hass, entry)

    assert await async_migrate_entry(hass, entry)

    assert entry.minor_version == 2
    assert _indoor_sensors(entry) == ("sensor.living_room", "sensor.living_room")


async def test_migrate_v3_1_without_indoor_sensor(hass):
    """An entry without an indoor temperature sensor gets none."""
    entry = MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data={CONF_HOST: "10.0.0.2"})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.minor_version == 2
    assert entry.data == {CONF_HOST: "10.0.0.2"}
    assert entry.options == {}


async def test_migrate_keeps_newer_minor_version(hass):
    """An entry from a newer minor version, left after a downgrade, is not changed."""
    entry = _v3_1_entry(hass, minor_version=3)

    assert await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (3, 3)
    assert _indoor_sensors(entry) == (LEGACY_INDOOR_SENSOR, LEGACY_INDOOR_SENSOR)


async def test_setup_migrates_v3_1(hass, luxtronik):
    """Setting up a version 3.1 entry runs the migration."""
    entry = _v3_1_entry(hass)
    _register_room_sensor(hass, entry)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert _indoor_sensors(entry) == (ROOM_SENSOR, ROOM_SENSOR)
