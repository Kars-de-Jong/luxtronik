"""Test the firmware update entity."""
from homeassistant.components.update import ATTR_RELEASE_URL
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)

SERIAL = "2311_1234_abcd"


async def test_release_url(hass, luxtronik):
    """The update entity links to the manufacturer firmware download page."""
    luxtronik.model = "LWP"
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("update", DOMAIN, f"{SERIAL}_firmware")
    assert hass.states.get(entity_id).attributes[ATTR_RELEASE_URL] == (
        "https://www.heatpump24.com/DownloadArea.php?layout=1")
