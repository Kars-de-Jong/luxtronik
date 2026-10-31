"""Test config entry migration."""
import threading
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
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
