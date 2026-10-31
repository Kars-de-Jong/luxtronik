"""Test that the heatpump is not read inside the event loop."""
import threading
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)
from custom_components.luxtronik.luxtronik_device import LuxtronikDevice

from .conftest import SERIAL


async def test_setup_does_not_read_in_event_loop(hass, luxtronik):
    """Setting up the platforms doesn't read or update the device in the event loop."""
    loop_thread = threading.current_thread()
    calls_in_loop = []

    def record(name):
        def side_effect(*args, **kwargs):
            if threading.current_thread() is loop_thread:
                calls_in_loop.append(name)
        return side_effect

    luxtronik.read.side_effect = record("read")
    luxtronik.update.side_effect = record("update")
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert calls_in_loop == []


@pytest.mark.parametrize(
    ("prop", "key", "value", "expected"),
    [
        ("has_second_heat_generator", "parameters.ID_Einst_ZWE1Art_akt", 1, True),
        ("has_domestic_water_circulation_pump", "parameters.ID_Einst_BWZIP_akt", 0, True),
    ],
)
def test_detection_properties_do_not_read(prop, key, value, expected):
    """The detection properties use the values that were already read."""
    device = LuxtronikDevice.__new__(LuxtronikDevice)
    device._luxtronik = MagicMock()
    device.read = MagicMock()
    device.get_value = MagicMock(side_effect=lambda k: value if k == key else None)

    assert getattr(device, prop) is expected
    device.read.assert_not_called()
