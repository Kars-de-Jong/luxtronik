"""Test the last thermal disinfection of the domestic water target temperature."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from homeassistant.core import State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.luxtronik.const import (ATTR_EXTRA_STATE_ATTRIBUTE_LAST_THERMAL_DESINFECTION,
                                              LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE)
from custom_components.luxtronik.number import LuxtronikNumberThermalDesinfection

TARGET_KEY = "parameters.ID_Einst_LGST_akt"
ENTITY_ID = "number.thermal_desinfection"
LAST = ATTR_EXTRA_STATE_ATTRIBUTE_LAST_THERMAL_DESINFECTION


def _entity(hass, water_temperature):
    luxtronik = MagicMock(unique_id="serial")
    values = {TARGET_KEY: 650, LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE: water_temperature}
    luxtronik.get_value.side_effect = values.get
    entity = LuxtronikNumberThermalDesinfection(
        MagicMock(device=luxtronik), None, number_key=TARGET_KEY, unique_id="thermal", factor=0.1)
    entity.hass = hass
    entity.entity_id = ENTITY_ID
    return entity, values


async def test_last_thermal_desinfection_updates_once_per_day(hass, freezer):
    """The first time the target is reached each day is stored."""
    entity, values = _entity(hass, 66.0)
    freezer.move_to("2026-10-01 10:00:00+00:00")
    entity._update_attrs()
    first = entity.extra_state_attributes[LAST]

    freezer.tick(timedelta(hours=1))
    entity._update_attrs()
    assert entity.extra_state_attributes[LAST] == first

    freezer.move_to("2026-10-02 10:00:00+00:00")
    entity._update_attrs()
    assert entity.extra_state_attributes[LAST] == dt_util.now()

    values[LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE] = 50.0
    freezer.move_to("2026-10-03 10:00:00+00:00")
    entity._update_attrs()
    assert entity.extra_state_attributes[LAST] == datetime.fromisoformat("2026-10-02 10:00:00+00:00")


async def test_last_thermal_desinfection_is_restored(hass, freezer):
    """The restored value is a date again, so the next disinfection is stored."""
    mock_restore_cache(hass, [State(ENTITY_ID, "65.0", {LAST: "2026-10-01T10:00:00+00:00"})])
    entity, _ = _entity(hass, 66.0)
    freezer.move_to("2026-10-01 12:00:00+00:00")
    await entity.async_added_to_hass()
    restored = entity.extra_state_attributes[LAST]
    assert restored == datetime.fromisoformat("2026-10-01 10:00:00+00:00")

    entity._update_attrs()
    assert entity.extra_state_attributes[LAST] == restored

    freezer.move_to("2026-10-02 10:00:00+00:00")
    entity._update_attrs()
    assert entity.extra_state_attributes[LAST] == dt_util.now()


async def test_last_thermal_desinfection_restored_without_time_zone(hass):
    """Older versions stored the local time without a time zone."""
    mock_restore_cache(hass, [State(ENTITY_ID, "65.0", {LAST: "2026-10-01T10:00:00"})])
    entity, _ = _entity(hass, 50.0)
    await entity.async_added_to_hass()

    assert entity.extra_state_attributes[LAST] == datetime(
        2026, 10, 1, 10, 0, tzinfo=dt_util.get_default_time_zone())
