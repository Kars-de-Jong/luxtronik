"""Test the polling intervals of the heatpump coordinator and the update platform."""
from datetime import timedelta
from importlib import import_module

import pytest

HEATPUMP_PLATFORMS = ["sensor", "binary_sensor", "climate", "number", "switch"]


@pytest.mark.parametrize("platform", HEATPUMP_PLATFORMS)
def test_heatpump_platforms_do_not_poll(platform):
    """The heatpump platforms don't poll; the coordinator reads the controller."""
    module = import_module(f"custom_components.luxtronik.{platform}")
    assert not hasattr(module, "SCAN_INTERVAL")


def test_coordinator_interval():
    """The coordinator reads the controller every 30 seconds."""
    from custom_components.luxtronik.const import SCAN_INTERVAL_DEVICE
    assert SCAN_INTERVAL_DEVICE == timedelta(seconds=30)


def test_update_platform_scan_interval():
    """The firmware update entity checks the download portal once per hour."""
    module = import_module("custom_components.luxtronik.update")
    assert module.SCAN_INTERVAL == timedelta(hours=1)


@pytest.mark.parametrize(
    ("platform", "parallel_updates"),
    [
        ("sensor", 0),
        ("binary_sensor", 0),
        ("update", 0),
        ("number", 1),
        ("switch", 1),
        ("climate", 1),
    ],
)
def test_parallel_updates(platform, parallel_updates):
    """Read-only platforms don't limit updates; writing platforms send one write at a time."""
    module = import_module(f"custom_components.luxtronik.{platform}")
    assert module.PARALLEL_UPDATES == parallel_updates
