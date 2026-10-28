"""Test component setup."""
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
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


@pytest.mark.parametrize("cooling_present", [True, False])
async def test_sub_devices_are_children_of_the_heatpump(hass, luxtronik, cooling_present):
    """Heating, domestic water and cooling are child devices of the heatpump."""
    luxtronik.detect_cooling_present.return_value = cooling_present
    entry = await _setup_entry(hass)

    dev_reg = dr.async_get(hass)
    heatpump = dev_reg.async_get_device_by_identifier((DOMAIN, "2311_1234_abcd_heatpump"), entry.entry_id)
    assert heatpump is not None
    for part in ("heating", "domestic_water"):
        child = dev_reg.async_get_child_device_by_identifier((DOMAIN, f"2311_1234_abcd_{part}"), entry.entry_id)
        assert child is not None
        assert child.parent_device_id == heatpump.id
    cooling = dev_reg.async_get_child_device_by_identifier((DOMAIN, "2311_1234_abcd_cooling"), entry.entry_id)
    if cooling_present:
        assert cooling.parent_device_id == heatpump.id
    else:
        assert cooling is None
        assert dev_reg.async_get_device_by_identifier((DOMAIN, "2311_1234_abcd_cooling"), entry.entry_id) is None


async def test_existing_sub_device_is_converted_to_child(hass, luxtronik):
    """An existing heating device becomes a child device and keeps its id."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id="2311_1234_abcd",
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    old = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "2311_1234_abcd_heating")},
        name="Heating", manufacturer="Alpha Innotec", model="LWD")
    # The device was registered by an earlier version, in an earlier session.
    dev_reg.async_config_entry_unloaded(entry.entry_id)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    child = dev_reg.async_get_child_device_by_identifier(
        (DOMAIN, "2311_1234_abcd_heating"), entry.entry_id)
    assert child.id == old.id
    assert dev_reg.async_get_device_by_identifier((DOMAIN, "2311_1234_abcd_heating"), entry.entry_id) is None
