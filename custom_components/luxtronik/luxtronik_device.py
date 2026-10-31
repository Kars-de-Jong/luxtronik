"""Luxtronik device."""
# region Imports
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from luxtronik import Luxtronik as Lux

from .const import (
    CONF_CALCULATIONS,
    CONF_PARAMETERS,
    CONF_VISIBILITIES,
    LOGGER,
    LUX_DETECT_SOLAR_SENSOR,
    LUX_MK_SENSORS,
    LuxMkTypes,
)
from .helpers.lux_helper import get_manufacturer_by_model

# endregion Imports

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


class LuxtronikDevice:
    """Handle all communication with Luxtronik."""

    def __init__(self, host: str, port: int, safe: bool, lock_timeout_sec: int) -> None:
        """Initialize the Luxtronik connection."""
        self.lock = threading.Lock()

        self._host = host
        self._port = port
        self._lock_timeout_sec = lock_timeout_sec
        # The library client reads the heatpump when it is created.
        self._luxtronik = Lux(host, port, safe)

    @staticmethod
    def connect(host: str, port: int):
        """Connect to heatpump."""
        return LuxtronikDevice(host, port, False, 30)

    def disconnect(self):
        """Disconnect from Luxtronik. - Nothing todo - disconnected after every read!"""
        pass

    def get_value(self, group_sensor_id: str):
        """Get a sensor value from Luxtronik."""
        sensor = self.get_sensor_by_id(group_sensor_id)
        if sensor is None:
            return None
        return sensor.value

    def get_sensor_by_id(self, group_sensor_id: str):
        """Get a sensor object by id from Luxtronik."""
        try:
            group = group_sensor_id.split(".")[0]
            sensor_id = group_sensor_id.split(".")[1]
            return self.get_sensor(group, sensor_id)
        except IndexError as error:
            LOGGER.critical(group_sensor_id, error, exc_info=True)

    def get_sensor(self, group, sensor_id):
        """Get sensor by configured sensor ID."""
        sensor = None
        try:
            if group == CONF_PARAMETERS:
                sensor = self._luxtronik.parameters.get(sensor_id)
            if group == CONF_CALCULATIONS:
                sensor = self._luxtronik.calculations.get(sensor_id)
            if group == CONF_VISIBILITIES:
                sensor = self._luxtronik.visibilities.get(sensor_id)
        except Exception as err:
            LOGGER.warning(f"Sensor id not found: {group}.{sensor_id}", err, exc_info=True)
        return sensor

    @property
    def serial_number(self) -> str:
        """Return the serial number."""
        serial_number_date = self.get_value("parameters.ID_WP_SerienNummer_DATUM")
        serial_number_hex = hex(
            int(self.get_value("parameters.ID_WP_SerienNummer_HEX"))
        )
        return f"{serial_number_date}-{serial_number_hex}".replace("x", "")

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self.serial_number.lower().replace("-", "_")

    @property
    def model(self) -> str:
        """Return the heatpump model."""
        return self.get_value("calculations.ID_WEB_Code_WP_akt")

    @property
    def manufacturer(self) -> str:
        """Return the heatpump manufacturer."""
        return get_manufacturer_by_model(self.model)

    @property
    def firmware_version(self) -> str:
        """Return the heatpump firmware version."""
        return str(self.get_value("calculations.ID_WEB_SoftStand"))

    @property
    def firmware_version_minor(self) -> int:
        """Return the heatpump firmware minor version."""
        ver = self.firmware_version
        if ver is None:
            return 0
        return int(re.search(r'\d+', ver.split('.')[1]).group(0))

    @property
    def has_second_heat_generator(self) -> bool:
        """Is second heat generator activated 1=electrical heater"""
        try:
            return int(self.get_value('parameters.ID_Einst_ZWE1Art_akt')) > 0
            # ID_Einst_ZWE1Fkt_akt = 1 --> Heating and domestic water
        except Exception:
            return False

    @property
    def has_domestic_water_circulation_pump(self) -> bool:
        """Exists a domestic water circulation pump. If not it is a domestic water charging pump"""
        try:
            return int(self.get_value('parameters.ID_Einst_BWZIP_akt')) != 1
        except Exception:
            return False

    def detect_cooling_Mk(self):
        """ returns list of parameters that are may show cooling is enabled """
        coolingMk = []
        for Mk in LUX_MK_SENSORS:
            sensor_value = self.get_value(Mk)
            # LOGGER.info(f"{Mk} = {sensor_value}")
            if sensor_value in [LuxMkTypes.cooling.value,
                                LuxMkTypes.heating_cooling.value]:
                coolingMk = coolingMk + [Mk]

        LOGGER.info(f"CoolingMk = {coolingMk}")
        return coolingMk

    def detect_solar_present(self) -> bool:
        """Detect and returns True if solar is present."""
        return (
            bool(self.get_value(LUX_DETECT_SOLAR_SENSOR))
            or self.get_value("parameters.ID_BSTD_Solar") > 0.01
            or
            (bool(self.get_value("visibilities.ID_Visi_Temp_Solarkoll"))
             and float(self.get_value("calculations.ID_WEB_Temperatur_TSK"))
             != 5.0
             )
            or
            (bool(self.get_value("visibilities.ID_Visi_Temp_Solarsp"))
             and float(self.get_value("calculations.ID_WEB_Temperatur_TSS"))
             != 150.0
             )
        )

    def detect_cooling_present(self):
        """ returns True if Cooling is present """
        CoolingPresent = (len(self.detect_cooling_Mk()) > 0)
        LOGGER.debug(f"CoolingPresent = {CoolingPresent}")
        return CoolingPresent

    def detect_cooling_target_temperature_sensor(self):
        """ if only 1 MK parameter related to cooling is returned
            return the corresponding colloing_target_temperature sensor"""
        Mk_param = self.detect_cooling_Mk()
        if len(Mk_param) == 1:
            Mk = re.findall('[0-9]+', Mk_param[0])[0]
            cooling_target_temperature_sensor = f"parameters.ID_Sollwert_KuCft{Mk}_akt"
        else:
            cooling_target_temperature_sensor = None
        LOGGER.debug(f"cooling_target_temperature_sensor = '{cooling_target_temperature_sensor}' ")
        return cooling_target_temperature_sensor

    def has_parameter(self, parameter: str) -> bool:
        """Return whether a parameter, given by its name or index, can be written."""
        return self._find_parameter(parameter) is not None

    def is_writable(self, parameter: str) -> bool:
        """Return whether safe mode allows writing a known parameter."""
        found = self._find_parameter(parameter)
        return found is not None and (found.writeable or not self._luxtronik.parameters.safe)

    def is_valid_value(self, parameter: str, value: Any) -> bool:
        """Return whether a known parameter accepts a value.

        The library writes a value only when it converts to an integer, and the heatpump
        protocol sends it as a signed 32-bit integer.
        """
        try:
            raw_value = self._find_parameter(parameter).to_heatpump(value)
        except (ArithmeticError, TypeError, ValueError):
            return False
        return isinstance(raw_value, int) and INT32_MIN <= raw_value <= INT32_MAX

    def _find_parameter(self, parameter: str):
        """Find a parameter by its name or index, like the library does.

        The library skips the parameter with index 0 when it writes (`if index:` in
        `Parameters.set`), so it is not found here either.
        """
        parameters = self._luxtronik.parameters.parameters
        try:
            index = int(parameter)
        except ValueError:
            index = next(
                (index for index, found in parameters.items() if found.name == parameter), None)
        if not index:
            return None
        return parameters.get(index)

    @contextmanager
    def _acquire_lock(self) -> Iterator[bool]:
        """Acquire the lock within the timeout, and release it only when it was acquired."""
        acquired = self.lock.acquire(blocking=True, timeout=self._lock_timeout_sec)
        try:
            yield acquired
        finally:
            if acquired:
                self.lock.release()

    def write(self, parameter, value) -> bool:
        """Write a parameter to the Luxtronik heatpump.

        Returns False when the parameter doesn't accept the value, and raises
        TimeoutError when the lock can't be acquired within the lock timeout. The
        coordinator reads the heatpump afterwards.
        """
        with self._acquire_lock() as acquired:
            if not acquired:
                raise TimeoutError(f"lock timeout of {self._lock_timeout_sec} s")
            if not (self.is_writable(parameter) and self.is_valid_value(parameter, value)):
                return False
            LOGGER.info('LuxtronikDevice.write %s value: "%s"', parameter, value)
            parameters = self._luxtronik.parameters
            # Don't send a value that is left over from a write that failed.
            parameters.queue = {}
            try:
                parameters.set(parameter, value)
                queued = dict(parameters.queue)
                self._luxtronik.write()
            finally:
                parameters.queue = {}
            self._store_written_values(queued)
            return True

    def _store_written_values(self, queued: dict) -> None:
        """Store the written values, so they show before the next read."""
        for index, raw_value in queued.items():
            # The library only writes integer indexes and values.
            if not isinstance(index, int) or not isinstance(raw_value, int):
                continue
            parameter = self._luxtronik.parameters.parameters.get(index)
            if parameter is not None:
                parameter.value = parameter.from_heatpump(raw_value)

    def read(self):
        """Get the data from Luxtronik.

        Raises TimeoutError when the lock can't be acquired within the lock timeout.
        """
        with self._acquire_lock() as acquired:
            if not acquired:
                raise TimeoutError(
                    f"Couldn't read luxtronik data because of lock timeout {self._lock_timeout_sec}"
                )
            self._luxtronik.read()
