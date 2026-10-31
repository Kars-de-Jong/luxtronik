"""Test the communication with the heatpump."""
import logging
import threading
from unittest.mock import MagicMock, patch

import pytest
from luxtronik.parameters import Parameters

from custom_components.luxtronik.luxtronik_device import LuxtronikDevice


@pytest.fixture
def device():
    """A device with a mocked library client and a short lock timeout."""
    device = LuxtronikDevice.__new__(LuxtronikDevice)
    device.lock = threading.Lock()
    device._lock_timeout_sec = 0.01
    device._luxtronik = MagicMock()
    return device


def test_read_lock_timeout(device):
    """A read that can't get the lock fails and doesn't release the lock of another."""
    device.lock.acquire()
    with pytest.raises(TimeoutError, match="lock timeout"):
        device.read()

    device._luxtronik.read.assert_not_called()
    assert device.lock.locked()
    device.lock.release()


def test_connect_reads_once():
    """Creating the device reads the heatpump once, in the library client."""
    with patch("custom_components.luxtronik.luxtronik_device.Lux") as lux:
        LuxtronikDevice("10.0.0.2", 8889, True, 30)

    lux.assert_called_once_with("10.0.0.2", 8889, True)
    lux.return_value.read.assert_not_called()


def test_device_has_no_throttled_update():
    """The coordinator reads the heatpump, so the device has no throttled update."""
    assert not hasattr(LuxtronikDevice, "update")


def test_write_lock_timeout(device, caplog):
    """A write that can't get the lock logs a warning and doesn't release the lock of another."""
    device.lock.acquire()
    with caplog.at_level(logging.WARNING):
        device.write("ID_Ba_Hz_akt", "Automatic")

    device._luxtronik.write.assert_not_called()
    assert "lock timeout" in caplog.text
    assert device.lock.locked()
    device.lock.release()


def test_read_and_write_release_the_lock(device):
    """The lock is free again after a read and a write."""
    device._luxtronik.parameters = Parameters(safe=False)
    device.read()
    device.write("ID_Ba_Hz_akt", "Automatic")

    device._luxtronik.read.assert_called_once()
    device._luxtronik.write.assert_called_once()
    assert not device.lock.locked()


def test_write_stores_the_value_locally(device):
    """A written parameter shows its new value before the next read."""
    device._luxtronik.parameters = Parameters(safe=False)

    assert device.write("ID_Ba_Hz_akt", "Party") is True

    assert device.get_value("parameters.ID_Ba_Hz_akt") == "Party"
    device._luxtronik.read.assert_not_called()


def test_write_unknown_parameter_stores_nothing(device):
    """Nothing is written or stored when the library rejects the parameter."""
    device._luxtronik.parameters = Parameters(safe=False)

    assert device.write("ID_Does_Not_Exist", 1) is False

    device._luxtronik.write.assert_not_called()



@pytest.mark.parametrize(("parameter", "known"), [
    ("ID_Ba_Hz_akt", True),
    ("3", True),
    ("ID_Does_Not_Exist", False),
    ("5000", False),
    ("-1", False),
    # The library can't write the parameter with index 0.
    ("0", False),
    ("ID_Transfert_LuxNet", False),
])
def test_has_parameter(device, parameter, known):
    """A parameter is known by its name or its index, except the one with index 0."""
    device._luxtronik.parameters = Parameters(safe=False)

    assert device.has_parameter(parameter) is known


@pytest.mark.parametrize(("safe", "parameter", "writable"), [
    (True, "ID_Ba_Hz_akt", True),
    (True, "ID_Ba_Al_akt", False),
    (False, "ID_Ba_Al_akt", True),
])
def test_is_writable(device, safe, parameter, writable):
    """In safe mode only the parameters the library marks as writeable can be written."""
    device._luxtronik.parameters = Parameters(safe=safe)

    assert device.is_writable(parameter) is writable


@pytest.mark.parametrize(("parameter", "value", "valid"), [
    ("ID_Ba_Hz_akt", "Party", True),
    ("ID_Ba_Hz_akt", "party", False),
    ("ID_Ba_Hz_akt", 1, False),
    ("ID_Einst_BWS_akt", 19.5, True),
    ("ID_Einst_BWS_akt", "19.5", True),
    ("ID_Einst_BWS_akt", "warm", False),
    ("ID_Einst_BWS_akt", float("nan"), False),
    ("ID_Einst_BWS_akt", float("inf"), False),
    ("ID_Einst_BWS_akt", 1e12, False),
    ("ID_Ba_Al_akt", 5, True),
    ("ID_Ba_Al_akt", "5", False),
])
def test_is_valid_value(device, parameter, value, valid):
    """A value is valid when the library converts it to an integer the heatpump accepts."""
    device._luxtronik.parameters = Parameters(safe=False)

    assert device.is_valid_value(parameter, value) is valid
