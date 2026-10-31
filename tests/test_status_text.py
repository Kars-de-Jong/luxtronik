"""Test the status text of the status sensor."""
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN,
                                              LUX_SENSOR_STATUS1)

from .conftest import MODE_SENSORS, SERIAL

VALUES = {
    LUX_SENSOR_STATUS1: "heatpump running",
    "calculations.ID_WEB_HauptMenuStatus_Zeile2": "since",
    "calculations.ID_WEB_HauptMenuStatus_Zeit": 3720,
}


def _get_value(key):
    if key in MODE_SENSORS:
        return "Automatic"
    return VALUES.get(key, 1)


async def test_status_text_uses_generated_entity_ids(hass, luxtronik):
    """The status text is built when the entity IDs are not 'sensor.luxtronik2_*'."""
    luxtronik.get_value.side_effect = _get_value
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    status_time = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_status_time")
    status = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_status")
    assert status_time != f"sensor.{DOMAIN}_status_time"

    # The status sensor reads the status time sensor, which is updated after it.
    await entry.runtime_data.coordinator.async_refresh()
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    status_text = hass.states.get(status).attributes["status_text"]
    assert status_text.endswith("1:02 h.")
