"""Test the attributes the recorder doesn't store."""
import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.luxtronik.const import (ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY,
                                              ATTR_STATUS_TEXT, CONF_LOCK_TIMEOUT, CONF_SAFE,
                                              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, DOMAIN)
from custom_components.luxtronik.entity import UNRECORDED_ATTRIBUTES

from .conftest import SERIAL

STATUS = "sensor.heatpump_2311_1234_status"


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder):
    """Set up the recorder before Home Assistant, which the autouse fixtures start."""


async def test_exclude_attributes(recorder_mock: Recorder, hass, luxtronik):
    """The changing attributes of the sensors are not recorded."""
    now = dt_util.utcnow()
    entry = MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=SERIAL,
        data={CONF_HOST: "10.0.0.2", CONF_PORT: 8889, CONF_SAFE: True, CONF_LOCK_TIMEOUT: 30,
              CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ATTR_STATUS_TEXT in hass.states.get(STATUS).attributes
    await async_wait_recording_done(hass)

    states = await hass.async_add_executor_job(
        get_significant_states, hass, now, None, hass.states.async_entity_ids())

    assert STATUS in states
    for entity_states in states.values():
        for state in entity_states:
            assert not UNRECORDED_ATTRIBUTES & state.attributes.keys()
    assert ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY in states[STATUS][0].attributes
