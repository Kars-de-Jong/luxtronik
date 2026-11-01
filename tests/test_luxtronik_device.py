"""Test the communication with the heatpump."""
import threading
from unittest.mock import MagicMock, patch

import pytest
from luxtronik.calculations import Calculations
from luxtronik.parameters import Parameters
from luxtronik.visibilities import Visibilities

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


def test_write_lock_timeout(device):
    """A write that can't get the lock fails and doesn't release the lock of another."""
    device.lock.acquire()
    with pytest.raises(TimeoutError, match="lock timeout"):
        device.write("ID_Ba_Hz_akt", "Automatic")

    device._luxtronik.write.assert_not_called()
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


@pytest.mark.parametrize(("parameter", "value"), [
    ("ID_Ba_Hz_akt", "party"),
    ("ID_Einst_BWS_akt", "warm"),
    ("0", 1),
])
def test_write_rejected_value_writes_nothing(device, parameter, value):
    """Nothing is written or queued when the parameter doesn't accept the value."""
    device._luxtronik.parameters = Parameters(safe=False)

    assert device.write(parameter, value) is False

    device._luxtronik.write.assert_not_called()
    assert device._luxtronik.parameters.queue == {}


def test_write_read_only_parameter_in_safe_mode(device):
    """In safe mode a parameter the library doesn't mark as writeable is not written."""
    device._luxtronik.parameters = Parameters(safe=True)

    assert device.write("ID_Ba_Al_akt", 1) is False

    device._luxtronik.write.assert_not_called()


def test_failed_write_is_not_written_again(device):
    """A value that couldn't be sent is not sent again with the next write."""
    device._luxtronik.parameters = Parameters(safe=False)
    device._luxtronik.write.side_effect = OSError("unreachable")
    with pytest.raises(OSError):
        device.write("ID_Ba_Hz_akt", "Party")
    assert device._luxtronik.parameters.queue == {}

    sent = []
    device._luxtronik.write.side_effect = lambda: sent.append(
        dict(device._luxtronik.parameters.queue))
    assert device.write("ID_Ba_Bw_akt", "Off") is True
    assert sent == [{4: 4}]


@pytest.fixture
def read_device(device):
    """A device with the data vectors of the library, as after a read."""
    device._luxtronik.parameters = Parameters(safe=False)
    device._luxtronik.calculations = Calculations()
    device._luxtronik.visibilities = Visibilities()
    return device


def _set_values(device, values: dict) -> None:
    """Set values in the data vectors of the library, by "<group>.<name>"."""
    for key, value in values.items():
        device.get_sensor_by_id(key).value = value


@pytest.mark.parametrize(("key", "value"), [
    ("parameters.ID_Ba_Hz_akt", "Party"),
    ("parameters.3", "Party"),
    ("calculations.ID_WEB_Temperatur_TVL", 35.5),
    ("visibilities.ID_Visi_Solar", 1),
])
def test_get_value(read_device, key, value):
    """A value is found by its group and its name or index."""
    read_device.get_sensor_by_id(key).value = value

    assert read_device.get_value(key) == value


@pytest.mark.parametrize("key", [
    "parameters.ID_Does_Not_Exist",
    "unknown.ID_Ba_Hz_akt",
    "ID_Ba_Hz_akt",
])
def test_get_value_unknown(read_device, key):
    """An unknown name or group, or a key without a group, has no value."""
    assert read_device.get_value(key) is None


def test_identity(read_device):
    """The serial number, unique id and model come from the values read."""
    _set_values(read_device, {
        "parameters.ID_WP_SerienNummer_DATUM": 2311,
        "parameters.ID_WP_SerienNummer_HEX": 0xabcd,
        "calculations.ID_WEB_Code_WP_akt": "LWP 8",
    })

    assert read_device.serial_number == "2311-0abcd"
    assert read_device.unique_id == "2311_0abcd"
    assert read_device.model == "LWP 8"
    assert read_device.manufacturer == "Alpha Innotec"


@pytest.mark.parametrize(("model", "manufacturer"), [
    ("SWC 6", "Alpha Innotec"),
    ("LD 7", "Novelan"),
    ("CB 9", None),
    (None, None),
])
def test_manufacturer(read_device, model, manufacturer):
    """The manufacturer is known from the model prefix."""
    _set_values(read_device, {"calculations.ID_WEB_Code_WP_akt": model})

    assert read_device.manufacturer == manufacturer


@pytest.mark.parametrize(("version", "minor"), [
    ("V3.88.1", 88),
    ("V2.81", 81),
    (None, 0),
])
def test_firmware_version_minor(read_device, version, minor):
    """The minor version is the number after the first dot, or 0 when it is unknown."""
    _set_values(read_device, {"calculations.ID_WEB_SoftStand": version})

    assert read_device.firmware_version_minor == minor


@pytest.mark.parametrize(("value", "expected"), [(0, False), (1, True), (None, False)])
def test_has_second_heat_generator(read_device, value, expected):
    """A second heat generator is present when its type is set."""
    _set_values(read_device, {"parameters.ID_Einst_ZWE1Art_akt": value})

    assert read_device.has_second_heat_generator is expected


@pytest.mark.parametrize(("value", "expected"), [(0, True), (1, False), (None, False)])
def test_has_domestic_water_circulation_pump(read_device, value, expected):
    """The pump is a circulation pump unless it is set up as a charging pump."""
    _set_values(read_device, {"parameters.ID_Einst_BWZIP_akt": value})

    assert read_device.has_domestic_water_circulation_pump is expected


@pytest.mark.parametrize(("types", "present", "target"), [
    ((0, 1, 2), False, None),
    ((3, 0, 0), True, "parameters.ID_Sollwert_KuCft1_akt"),
    ((0, 4, 0), True, "parameters.ID_Sollwert_KuCft2_akt"),
    # With more than one cooling circuit the target temperature is ambiguous.
    ((3, 0, 4), True, None),
])
def test_detect_cooling(read_device, types, present, target):
    """Cooling is present when a mixing circuit cools."""
    _set_values(read_device, {
        f"parameters.ID_Einst_MK{index}Typ_akt": value
        for index, value in enumerate(types, start=1)
    })

    assert read_device.detect_cooling_present() is present
    assert read_device.detect_cooling_target_temperature_sensor() == target


SOLAR_ABSENT = {
    "visibilities.ID_Visi_Solar": 0,
    "parameters.ID_BSTD_Solar": 0,
    "visibilities.ID_Visi_Temp_Solarkoll": 0,
    "calculations.ID_WEB_Temperatur_TSK": 5.0,
    "visibilities.ID_Visi_Temp_Solarsp": 0,
    "calculations.ID_WEB_Temperatur_TSS": 150.0,
}


@pytest.mark.parametrize(("values", "present"), [
    ({}, False),
    ({"visibilities.ID_Visi_Solar": 1}, True),
    ({"parameters.ID_BSTD_Solar": 12}, True),
    # A visible sensor that shows its default temperature isn't connected.
    ({"visibilities.ID_Visi_Temp_Solarkoll": 1}, False),
    ({"visibilities.ID_Visi_Temp_Solarkoll": 1, "calculations.ID_WEB_Temperatur_TSK": 31.0}, True),
    ({"visibilities.ID_Visi_Temp_Solarsp": 1}, False),
    ({"visibilities.ID_Visi_Temp_Solarsp": 1, "calculations.ID_WEB_Temperatur_TSS": 48.0}, True),
])
def test_detect_solar_present(read_device, values, present):
    """Solar is present when it is visible, has run, or has a connected sensor."""
    _set_values(read_device, SOLAR_ABSENT | values)

    assert read_device.detect_solar_present() is present
