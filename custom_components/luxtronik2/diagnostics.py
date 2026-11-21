"""Diagnostics support for Luxtronik."""
from __future__ import annotations

import asyncio
from functools import partial
from ipaddress import IPv6Address, ip_address

from getmac import get_mac_address
from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_HOST, CONF_PASSWORD, CONF_PORT,
                                 CONF_USERNAME)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from luxtronik import Luxtronik as Lux

# The title and unique_id contain the serial number.
TO_REDACT = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD, "title", "unique_id"}
SERIAL_NUMBER_PREFIX = "ID_WP_SerienNummer"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    data: dict = entry.data
    # The client reads the heatpump when it is created.
    client = await hass.async_add_executor_job(Lux, data[CONF_HOST], data[CONF_PORT], True)

    async with asyncio.timeout(10):
        mac = await _async_get_mac_address(hass, data[CONF_HOST])
    if mac is not None:
        # Keep only the vendor part, which identifies the manufacturer.
        mac = mac[:9] + '*'

    entry_data = async_redact_data(entry.as_dict(), TO_REDACT)
    entry_data["data"]["mac"] = mac
    diag_data = {
        "entry": entry_data,
        "parameters": _dump_items(client.parameters.parameters),
        "calculations": _dump_items(client.calculations.calculations),
        "visibilities": _dump_items(client.visibilities.visibilities),
    }
    return diag_data


def _dump_items(items: dict) -> dict:
    dump = dict()
    for index, item in items.items():
        value = REDACTED if item.name.startswith(SERIAL_NUMBER_PREFIX) else f"{items.get(index)}"
        dump[f"{index:<4d} {item.name:<60}"] = value
    return dump


async def _async_get_mac_address(hass: HomeAssistant, host: str) -> str | None:
    """Get mac address from host name, IPv4 address, or IPv6 address."""
    # Help mypy, which has trouble with the async_add_executor_job + partial call
    mac_address: str | None
    # getmac has trouble using IPv6 addresses as the "hostname" parameter so
    # assume host is an IP address, then handle the case it's not.
    try:
        ip_addr = ip_address(host)
    except ValueError:
        mac_address = await hass.async_add_executor_job(
            partial(get_mac_address, hostname=host)
        )
    else:
        if ip_addr.version == 4:
            mac_address = await hass.async_add_executor_job(
                partial(get_mac_address, ip=host)
            )
        else:
            # Drop scope_id from IPv6 address by converting via int
            ip_addr = IPv6Address(int(ip_addr))
            mac_address = await hass.async_add_executor_job(
                partial(get_mac_address, ip6=str(ip_addr))
            )

    if not mac_address:
        return None

    return device_registry.format_mac(mac_address)
