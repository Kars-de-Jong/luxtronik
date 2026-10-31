"""Test the communication with the heatpump."""
import logging
import threading
from unittest.mock import MagicMock

import pytest

from custom_components.luxtronik.luxtronik_device import LuxtronikDevice


@pytest.fixture
def device():
    """A device with a mocked library client and a short lock timeout."""
    device = LuxtronikDevice.__new__(LuxtronikDevice)
    device.lock = threading.Lock()
    device._lock_timeout_sec = 0.01
    device._luxtronik = MagicMock()
    return device


def test_read_lock_timeout(device, caplog):
    """A read that can't get the lock logs a warning and doesn't release the lock of another."""
    device.lock.acquire()
    with caplog.at_level(logging.WARNING):
        device.read()

    device._luxtronik.read.assert_not_called()
    assert "lock timeout" in caplog.text
    assert device.lock.locked()
    device.lock.release()


def test_write_lock_timeout(device, caplog):
    """A write that can't get the lock logs a warning and doesn't release the lock of another."""
    device.lock.acquire()
    with caplog.at_level(logging.WARNING):
        device.write("ID_Ba_Hz_akt", "Automatic", use_debounce=False)

    device._luxtronik.write.assert_not_called()
    assert "lock timeout" in caplog.text
    assert device.lock.locked()
    device.lock.release()


def test_read_and_write_release_the_lock(device):
    """The lock is free again after a read and a write."""
    device.read()
    device.write("ID_Ba_Hz_akt", "Automatic", use_debounce=False)

    device._luxtronik.read.assert_called_once()
    device._luxtronik.parameters.set.assert_called_once_with("ID_Ba_Hz_akt", "Automatic")
    device._luxtronik.write.assert_called_once()
    assert not device.lock.locked()
