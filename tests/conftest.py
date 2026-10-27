"""Fixtures for testing."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.luxtronik.const import (LUX_SENSOR_MODE_COOLING,
                                              LUX_SENSOR_MODE_DOMESTIC_WATER,
                                              LUX_SENSOR_MODE_HEATING)

MODE_SENSORS = {LUX_SENSOR_MODE_COOLING, LUX_SENSOR_MODE_DOMESTIC_WATER, LUX_SENSOR_MODE_HEATING}

SERIAL = "2311_1234_abcd"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def luxtronik():
    """Mock the heatpump connection."""
    device = MagicMock(
        unique_id=SERIAL, serial_number="2311-1234", manufacturer="Alpha Innotec",
        model="LWD", firmware_version_minor=99, has_domestic_water_circulation_pump=True)
    device.get_value.side_effect = lambda key: "Automatic" if key in MODE_SENSORS else 1
    device.detect_cooling_target_temperature_sensor.return_value = "parameters.ID_Sollwert_KuCft1_akt"
    with patch("custom_components.luxtronik.LuxtronikDevice", return_value=device), \
            patch("custom_components.luxtronik.update.LuxtronikUpdateEntity._request_available_firmware_version"):
        yield device
