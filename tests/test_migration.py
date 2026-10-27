"""Test config entry migration."""
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

    assert entry.version == 2
    assert entry.unique_id == SERIAL
    assert entry.title == "Alpha Innotec LWD 2311-1234"
