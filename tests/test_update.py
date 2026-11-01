"""Test the firmware update entity."""
import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from aiohttp import ClientError
from homeassistant.components.update import ATTR_LATEST_VERSION, ATTR_RELEASE_URL
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              DOWNLOAD_PORTAL_URL)
from custom_components.luxtronik.update import LuxtronikUpdateEntity

from .conftest import MODE_SENSORS, SERIAL

FIRMWARE_KEY = "calculations.ID_WEB_SoftStand"
# The conftest fixture replaces the request; these tests use the real one.
FETCH = LuxtronikUpdateEntity._async_fetch_latest_version
PORTAL_URL = f"{DOWNLOAD_PORTAL_URL}1"
DISPOSITION = {"content-disposition": "attachment; filename=wp2reg-V2.88.1-9086"}


@pytest.fixture
def installed(luxtronik):
    """The installed firmware version of the mocked heatpump."""
    values = {FIRMWARE_KEY: "V2.88.0"}
    luxtronik.get_value.side_effect = lambda key: values.get(
        key, "Automatic" if key in MODE_SENSORS else 1)
    return values


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    with patch.object(LuxtronikUpdateEntity, "_async_fetch_latest_version", FETCH):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _state(hass):
    entity_id = er.async_get(hass).async_get_entity_id("update", DOMAIN, f"{SERIAL}_firmware")
    return hass.states.get(entity_id)


@pytest.mark.parametrize(("model", "layout"), [
    ("LWP", 1),
    ("LD 7", 2),
    ("CB 9", 3),
    ("XYZ", 0),
    (None, 0),
])
async def test_release_url(hass, luxtronik, installed, aioclient_mock, model, layout):
    """The update entity links to the firmware download page of the manufacturer."""
    luxtronik.model = model
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    await _setup(hass)

    assert _state(hass).attributes[ATTR_RELEASE_URL] == (
        f"https://www.heatpump24.com/DownloadArea.php?layout={layout}")


@pytest.mark.parametrize(("version", "download_id"), [
    ("V1.70", 0),
    ("V2.88.0", 1),
    ("V3.85.2", 2),
    ("V4.01", 3),
    ("F1.2.3", 4),
    ("WWB1.1", 5),
    ("smo 4.1", 6),
])
async def test_release_notes(
    hass, hass_ws_client, luxtronik, installed, aioclient_mock, version, download_id
):
    """The release notes link to the download page and to the firmware for the version."""
    luxtronik.model = "LWP"
    installed[FIRMWARE_KEY] = version
    aioclient_mock.get(f"{DOWNLOAD_PORTAL_URL}{download_id}", headers=DISPOSITION)
    await _setup(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "update/release_notes", "entity_id": _state(hass).entity_id})
    result = await client.receive_json()

    assert result["success"]
    notes = result["result"]
    assert 'href="https://www.heatpump24.com/DownloadArea.php?layout=1"' in notes
    assert f'href="{DOWNLOAD_PORTAL_URL}{download_id}"' in notes


async def test_latest_version_from_portal(hass, luxtronik, installed, aioclient_mock):
    """The latest version is read from the file name of the download portal, once at start."""
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    await _setup(hass)

    assert aioclient_mock.call_count == 1
    assert _state(hass).state == STATE_ON
    assert _state(hass).attributes[ATTR_LATEST_VERSION] == "V2.88.1"


async def test_latest_version_checked_every_hour(hass, luxtronik, installed, aioclient_mock):
    """The download portal is queried once per hour."""
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    await _setup(hass)

    with patch.object(LuxtronikUpdateEntity, "_async_fetch_latest_version", FETCH):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=30))
        await hass.async_block_till_done()
        assert aioclient_mock.call_count == 1
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1))
        await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2


async def test_up_to_date(hass, luxtronik, installed, aioclient_mock):
    """The entity is off when the installed version is the latest."""
    installed[FIRMWARE_KEY] = "V2.88.1"
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    await _setup(hass)

    assert _state(hass).state == STATE_OFF


@pytest.mark.parametrize("version", ["X9.1", None])
async def test_unknown_model(hass, luxtronik, installed, aioclient_mock, version):
    """Without a download portal for the firmware, the latest version is unknown."""
    installed[FIRMWARE_KEY] = version
    await _setup(hass)

    assert aioclient_mock.call_count == 0
    assert _state(hass).state == STATE_UNKNOWN
    assert _state(hass).attributes[ATTR_LATEST_VERSION] is None


async def test_portal_error_logged_once(hass, luxtronik, installed, aioclient_mock, caplog):
    """A failing download portal is logged once and keeps the last known version."""
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    entry = await _setup(hass)
    entity = next(
        e for e in hass.data["entity_components"]["update"].entities
        if e.unique_id == f"{SERIAL}_firmware")

    aioclient_mock.clear_requests()
    aioclient_mock.get(PORTAL_URL, exc=ClientError("portal down"))
    with patch.object(LuxtronikUpdateEntity, "_async_fetch_latest_version", FETCH), \
            caplog.at_level(logging.INFO):
        await entity.async_update()
        await entity.async_update()
    assert caplog.text.count("portal down") == 1
    assert entity.latest_version == "V2.88.1"

    caplog.clear()
    aioclient_mock.clear_requests()
    aioclient_mock.get(PORTAL_URL, headers=DISPOSITION)
    with patch.object(LuxtronikUpdateEntity, "_async_fetch_latest_version", FETCH), \
            caplog.at_level(logging.INFO):
        await entity.async_update()
        await entity.async_update()
    assert caplog.text.count("download portal is available again") == 1
    assert entry.runtime_data.coordinator.device is luxtronik


def test_no_requests_or_threads():
    """The update platform uses the aiohttp session of Home Assistant."""
    from custom_components.luxtronik import update
    assert not hasattr(update, "requests")
    assert not hasattr(update, "threading")
