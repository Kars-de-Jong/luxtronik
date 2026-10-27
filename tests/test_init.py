"""Test component setup."""
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              SERVICE_WRITE)

async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_setup_entry_not_ready(hass):
    """Setup is retried when the heatpump is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id="2311_1234_abcd",
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)

    with patch("custom_components.luxtronik.LuxtronikDevice", side_effect=OSError):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_async_setup_ignores_yaml_connection(hass):
    """The heatpump connection can only be configured from the UI."""
    with patch("custom_components.luxtronik.LuxtronikDevice") as device:
        assert await async_setup_component(
            hass, DOMAIN, {DOMAIN: {CONF_HOST: "10.0.0.2", CONF_PORT: 8889}}) is True
    device.assert_not_called()
    assert DOMAIN not in hass.data


async def _setup_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id="2311_1234_abcd",
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_write_action_without_entry(hass):
    """The write action is registered in async_setup and fails without a loaded entry."""
    assert await async_setup_component(hass, DOMAIN, {})
    assert hass.services.has_service(DOMAIN, SERVICE_WRITE)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_WRITE, {"parameter": "ID_Ba_Hz_akt", "value": "Automatic"},
            blocking=True)


async def test_write_action(hass, luxtronik):
    """The write action writes the parameter to the heatpump of the loaded entry."""
    await _setup_entry(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_WRITE, {"parameter": "ID_Ba_Hz_akt", "value": "Automatic"},
        blocking=True)

    luxtronik.write.assert_called_once_with(
        "ID_Ba_Hz_akt", "Automatic", use_debounce=True, update_immediately_after_write=True)


async def test_write_action_after_unload(hass, luxtronik):
    """The write action stays registered after the entry is unloaded."""
    entry = await _setup_entry(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_WRITE)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_WRITE, {"parameter": "ID_Ba_Hz_akt", "value": "Automatic"},
            blocking=True)
