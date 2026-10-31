"""Test the diagnostics."""
import threading
from unittest.mock import MagicMock, patch

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import DOMAIN
from custom_components.luxtronik.diagnostics import async_get_config_entry_diagnostics

from .conftest import SERIAL


def _client():
    client = MagicMock()
    serial = MagicMock()
    serial.name = "ID_WP_SerienNummer_HEX"
    software = MagicMock()
    software.name = "ID_WEB_SoftStand"
    client.parameters.parameters = {875: serial}
    client.calculations.calculations = {81: software}
    client.visibilities.visibilities = {}
    return client


async def test_diagnostics(hass):
    """Diagnostics read the heatpump in the executor and redact identifying data.

    Lux is patched with a function: the test harness runs Mock executor jobs inline.
    """
    loop_thread = threading.current_thread()
    client = _client()
    created_in = []

    def create_client(*args):
        created_in.append(threading.current_thread())
        return client

    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL, title=f"Alpha Innotec LWD {SERIAL}",
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889})
    entry.add_to_hass(hass)

    with patch("custom_components.luxtronik.diagnostics.Lux", new=create_client), \
            patch("custom_components.luxtronik.diagnostics.get_mac_address", return_value=None):
        diag = await async_get_config_entry_diagnostics(hass, entry)

    assert created_in and loop_thread not in created_in
    client.read.assert_not_called()
    assert diag["entry"]["data"][CONF_HOST] == REDACTED
    assert diag["entry"]["data"]["mac"] is None
    assert diag["entry"]["unique_id"] == REDACTED
    assert diag["entry"]["title"] == REDACTED
    assert list(diag["parameters"].values()) == [REDACTED]
    assert list(diag["calculations"].values()) != [REDACTED]
