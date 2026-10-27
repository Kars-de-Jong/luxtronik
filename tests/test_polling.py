"""Test that every polling platform sets an explicit polling interval."""
from datetime import datetime, timedelta, timezone
from importlib import import_module
from unittest.mock import patch

import pytest

from custom_components.luxtronik.update import LuxtronikUpdateEntity

HEATPUMP_PLATFORMS = ["sensor", "binary_sensor", "climate", "number", "switch"]


@pytest.mark.parametrize("platform", HEATPUMP_PLATFORMS)
def test_heatpump_platform_scan_interval(platform):
    """The heatpump platforms poll the controller every 30 seconds."""
    module = import_module(f"custom_components.luxtronik.{platform}")
    assert module.SCAN_INTERVAL == timedelta(seconds=30)


def test_device_throttle_is_shorter_than_scan_interval():
    """Every scan cycle reads fresh data from the controller."""
    from custom_components.luxtronik.const import MIN_TIME_BETWEEN_UPDATES, SCAN_INTERVAL_DEVICE
    assert MIN_TIME_BETWEEN_UPDATES < SCAN_INTERVAL_DEVICE


def test_update_platform_scan_interval():
    """The firmware update entity checks the download portal once per hour."""
    module = import_module("custom_components.luxtronik.update")
    assert module.SCAN_INTERVAL == timedelta(hours=1)


def test_update_entity_requests_firmware_version_on_every_poll():
    """The scan interval alone determines how often the download portal is queried."""
    entity = LuxtronikUpdateEntity.__new__(LuxtronikUpdateEntity)
    # A firmware version was just fetched; the next poll must not be skipped.
    entity._LuxtronikUpdateEntity__firmware_version_available_last_request = datetime.now(timezone.utc).timestamp()
    with patch.object(LuxtronikUpdateEntity, "_request_available_firmware_version") as request:
        entity.update()
        entity.update()
    assert request.call_count == 2
