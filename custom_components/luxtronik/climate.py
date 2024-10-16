"""Luxtronik heatpump climate thermostat."""
# region Imports
import math
from typing import Any, Final

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACAction, HVACMode, PRESET_AWAY, PRESET_BOOST, PRESET_NONE
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.components.water_heater import ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType

from . import LuxtronikDevice
from .const import (CONF_CALCULATIONS, CONF_CONTROL_MODE_HOME_ASSISTANT,
                    CONF_HA_SENSOR_INDOOR_TEMPERATURE,
                    CONF_PARAMETERS,
                    CONF_VISIBILITIES, DEFAULT_TOLERANCE, DOMAIN, LOGGER,
                    LUX_BINARY_SENSOR_DOMESTIC_WATER_RECIRCULATION_PUMP,
                    LUX_BINARY_SENSOR_CIRCULATION_PUMP_HEATING,
                    LUX_SENSOR_COOLING_THRESHOLD,
                    LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE,
                    LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE,
                    LUX_SENSOR_HEATING_TARGET_CORRECTION,
                    LUX_SENSOR_MODE_COOLING, LUX_SENSOR_MODE_DOMESTIC_WATER,
                    LUX_SENSOR_MODE_HEATING, LUX_SENSOR_OUTDOOR_TEMPERATURE,
                    LUX_SENSOR_STATUS, LUX_SENSOR_STATUS1, LUX_SENSOR_STATUS3,
                    LUX_STATUS1_WORKAROUND, LUX_STATUS3_WORKAROUND,
                    LUX_STATUS_COOLING, LUX_STATUS_DEFROST,
                    LUX_STATUS_DOMESTIC_WATER,
                    LUX_STATUS_HEATING, LUX_STATUS_HEATING_EXTERNAL_SOURCE,
                    LUX_STATUS_SWIMMING_POOL_SOLAR,
                    PRESET_SECOND_HEATSOURCE, LuxMode)
from .helpers.helper import get_sensor_text

# endregion Imports

# region Constants
SUPPORT_FLAGS: Final = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
OPERATION_LIST: Final = [HVACMode.AUTO, HVACMode.OFF]

MIN_TEMPERATURE: Final = 40
MAX_TEMPERATURE: Final = 48
# endregion Constants

# region Setup


async def async_setup_platform(
    hass: HomeAssistant, config: ConfigType, async_add_entities: AddEntitiesCallback, discovery_info: dict[str, Any] = None,
) -> None:
    pass


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a Luxtronik thermostat from ConfigEntry."""
    LOGGER.info("climate.async_setup_entry entry: '%s'", config_entry)
    control_mode_home_assistant = config_entry.options.get(
        CONF_CONTROL_MODE_HOME_ASSISTANT)
    ha_sensor_indoor_temperature = config_entry.options.get(
        CONF_HA_SENSOR_INDOOR_TEMPERATURE)

    luxtronik: LuxtronikDevice = hass.data.get(DOMAIN)
    if not luxtronik:
        LOGGER.warning("climate.async_setup_platform no luxtronik!")
        return False

    # Build Sensor names with local language:
    lang = hass.config.language
    entities = []

    deviceInfoHeating = hass.data[f"{DOMAIN}_DeviceInfo_Heating"]
    if deviceInfoHeating is not None:
        text_heating = get_sensor_text(lang, 'heating')
        entities += [
            LuxtronikHeatingThermostat(
                luxtronik, deviceInfoHeating, name=text_heating, control_mode_home_assistant=control_mode_home_assistant,
                current_temperature_sensor=ha_sensor_indoor_temperature)
        ]

    deviceInfoDomesticWater = hass.data[f"{DOMAIN}_DeviceInfo_Domestic_Water"]
    if deviceInfoDomesticWater is not None:
        text_domestic_water = get_sensor_text(lang, 'domestic_water')
        entities += [
            LuxtronikDomesticWaterThermostat(
                luxtronik, deviceInfoDomesticWater, name=text_domestic_water, control_mode_home_assistant=control_mode_home_assistant,
                current_temperature_sensor=LUX_SENSOR_DOMESTIC_WATER_CURRENT_TEMPERATURE)
        ]

    deviceInfoCooling = hass.data[f"{DOMAIN}_DeviceInfo_Cooling"]
    if deviceInfoCooling is not None:
        text_cooling = get_sensor_text(lang, 'cooling')
        entities += [
            LuxtronikCoolingThermostat(
                luxtronik, deviceInfoCooling, name=text_cooling, control_mode_home_assistant=control_mode_home_assistant,
                current_temperature_sensor=LUX_SENSOR_OUTDOOR_TEMPERATURE)
        ]

    async_add_entities(entities)
# endregion Setup


class LuxtronikThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Luxtronik Thermostat device."""
    # region Properties / Init
    _active = False

    _attr_target_temperature = None
    _attr_current_temperature = None
    _attr_supported_features = SUPPORT_FLAGS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = HVACMode.OFF
    _attr_hvac_modes = OPERATION_LIST
    _attr_hvac_action = HVACAction.IDLE
    _attr_preset_mode = PRESET_NONE
    _attr_preset_modes = [PRESET_NONE,
                          PRESET_SECOND_HEATSOURCE, PRESET_BOOST, PRESET_AWAY]
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE

    _status_sensor: Final = LUX_SENSOR_STATUS
    _target_temperature_sensor: str = None

    _heat_status = [LUX_STATUS_HEATING, LUX_STATUS_DOMESTIC_WATER, LUX_STATUS_COOLING]

    _cold_tolerance = DEFAULT_TOLERANCE
    _hot_tolerance = DEFAULT_TOLERANCE

    _last_lux_mode: LuxMode = None
    _last_hvac_action = None

    def __init__(self, luxtronik: LuxtronikDevice, deviceInfo: DeviceInfo, name: str, control_mode_home_assistant: bool, current_temperature_sensor: str):
        self._luxtronik = luxtronik
        self._attr_device_info = deviceInfo
        self._attr_name = name
        self._control_mode_home_assistant = control_mode_home_assistant
        self._current_temperature_sensor = current_temperature_sensor
        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{DOMAIN}_{self._attr_unique_id}")
    # endregion Properties / Init

    # region Temperatures
    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        if self._current_temperature_sensor is None:
            self._attr_current_temperature = None
        elif self.__is_luxtronik_sensor(self._current_temperature_sensor):
            self._attr_current_temperature = self._luxtronik.get_value(
                self._current_temperature_sensor)
        else:
            current_temperature_sensor = self.hass.states.get(
                self._current_temperature_sensor)
            if current_temperature_sensor is None or current_temperature_sensor.state is None or current_temperature_sensor.state == 'unknown':
                self._attr_current_temperature = None
            else:
                self._attr_current_temperature = float(current_temperature_sensor.state)
        return self._attr_current_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        if self._target_temperature_sensor is None:
            return self._attr_target_temperature
        elif self.__is_luxtronik_sensor(self._target_temperature_sensor):
            self._attr_target_temperature = self._luxtronik.get_value(
                self._target_temperature_sensor)
        else:
            self._attr_target_temperature = float(self.hass.states.get(
                self._target_temperature_sensor).state)
        return self._attr_target_temperature

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            cur_temp = float(state.state)
            if math.isnan(cur_temp) or math.isinf(cur_temp):
                raise ValueError(f"Sensor has illegal state {state.state}")
            self._attr_current_temperature = cur_temp
        except ValueError as ex:
            LOGGER.error("Unable to update from sensor: %s", ex)

    def set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        changed = False
        self._attr_target_temperature = kwargs[ATTR_TEMPERATURE]
        if self._target_temperature_sensor is not None:
            self._luxtronik.write(self._target_temperature_sensor.split('.')[1],
                                  self._attr_target_temperature, use_debounce=False,
                                  update_immediately_after_write=True)
            changed = True
        if changed:
            self.schedule_update_ha_state(force_refresh=True)
    # endregion Temperatures

    def _is_heating_on(self) -> bool:
        status = self._luxtronik.get_value(self._status_sensor)
        # region Workaround Luxtronik Bug: Status shows heating but status 3 = no request!
        if status == LUX_STATUS_HEATING:
            status1 = self._luxtronik.get_value(LUX_SENSOR_STATUS1)
            status3 = self._luxtronik.get_value(LUX_SENSOR_STATUS3)
            if status1 in LUX_STATUS1_WORKAROUND and status3 in LUX_STATUS3_WORKAROUND:
                # pump forerun
                # 211123 LOGGER.info("climate._is_heating_on1 %s self._heat_status: %s status: %s status1: %s status3: %s result: %s",
                #             self._attr_unique_id, self._heat_status, status, status1, status3, False)
                return False
            # return not status3 is None and not status3 in [None, LUX_STATUS_UNKNOWN, LUX_STATUS_NONE, LUX_STATUS_NO_REQUEST]
            # 211123 LOGGER.info("climate._is_heating_on1 %s self._heat_status: %s status: %s status1: %s status3: %s result: %s",
            #             self._attr_unique_id, self._heat_status, status, status1, status3, LUX_STATUS_HEATING in self._heat_status)
            return LUX_STATUS_HEATING in self._heat_status
            # endregion Workaround Luxtronik Bug: Status shows heating but status 3 = no request!
        # 211123 LOGGER.info("climate._is_heating_on2 %s self._heat_status: %s status: %s result: %s",
        #             self._attr_unique_id, self._heat_status, status, status in self._heat_status or status in [LUX_STATUS_DEFROST, LUX_STATUS_SWIMMING_POOL_SOLAR, LUX_STATUS_HEATING_EXTERNAL_SOURCE])
        if status in self._heat_status or (status in [LUX_STATUS_SWIMMING_POOL_SOLAR, LUX_STATUS_HEATING_EXTERNAL_SOURCE] and self._attr_hvac_mode != HVACMode.OFF):
            return True
        # if not result and status == LUX_STATUS_DEFROST and self._attr_hvac_mode != HVAC_MODE_OFF and self._last_status == self._heat_status:
        #     result = True
        return self._is__heating_on_special()

    def _is__heating_on_special(self) -> bool:
        return False

    @property
    def hvac_action(self):
        """Return the current mode."""
        new_hvac_action = self._attr_hvac_action
        status = self._luxtronik.get_value(self._status_sensor)
        if self._is_heating_on():
            new_hvac_action = HVACAction.HEATING
        elif status == LUX_STATUS_COOLING:
            new_hvac_action = HVACAction.COOLING
        elif self.__get_hvac_mode(HVACAction.IDLE) == HVACMode.OFF:
            new_hvac_action = HVACAction.OFF
        else:
            new_hvac_action = HVACAction.IDLE
        if new_hvac_action != self._attr_hvac_action:
            self._attr_hvac_action = new_hvac_action
        if self._last_hvac_action != new_hvac_action:
            self._last_hvac_action = new_hvac_action
            LOGGER.info("climate.hvac_action changed %s status: %s hvac_action: %s",
                        self._attr_unique_id, status, new_hvac_action)
        return new_hvac_action

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current operation mode."""
        self._attr_hvac_mode = self.__get_hvac_mode(self.hvac_action)
        return self._attr_hvac_mode

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new operation mode."""
        if self._attr_hvac_mode == hvac_mode:
            return
        LOGGER.info("climate.set_hvac_mode %s hvac_mode: %s",
                    self._attr_unique_id, hvac_mode)
        self._attr_hvac_mode = hvac_mode
        self._last_lux_mode = self.__get_luxmode(hvac_mode, self.preset_mode)
        self._luxtronik.write(self._heater_sensor.split('.')[1],
                              self._last_lux_mode.value, use_debounce=False,
                              update_immediately_after_write=True)
        self.schedule_update_ha_state(force_refresh=True)

    def __get_hvac_mode(self, hvac_action):
        luxmode = LuxMode[self._luxtronik.get_value(
            self._heater_sensor).lower().replace(' ', '_')]
        if luxmode != self._last_lux_mode:
            self._last_lux_mode = luxmode
        if luxmode in [LuxMode.holidays, LuxMode.party, LuxMode.second_heatsource]:
            return self._attr_hvac_mode
        elif luxmode == LuxMode.off:
            return HVACMode.OFF
        return HVACMode.AUTO

    def __get_luxmode(self, hvac_mode: HVACMode, preset_mode: str) -> LuxMode:
        if hvac_mode == HVACMode.OFF:
            return LuxMode.off
        # elif self._control_mode_home_assistant and self.hvac_action in [CURRENT_HVAC_OFF, CURRENT_HVAC_IDLE]:
        #     return LuxMode.off.value
        elif preset_mode == PRESET_AWAY:
            return LuxMode.holidays
        elif preset_mode == PRESET_BOOST:
            return LuxMode.party
        elif preset_mode == PRESET_SECOND_HEATSOURCE:
            return LuxMode.second_heatsource
        elif hvac_mode == HVACMode.AUTO:
            return LuxMode.automatic
        return LuxMode.automatic

    @property
    def preset_mode(self) -> str:  # | None:
        """Return current preset mode."""
        luxmode = LuxMode[self._luxtronik.get_value(
            self._heater_sensor).lower().replace(' ', '_')]
        if luxmode == LuxMode.off and self._control_mode_home_assistant and self.hvac_action == HVACAction.IDLE:
            return self._attr_preset_mode
        elif luxmode in [LuxMode.off, LuxMode.automatic]:
            return PRESET_NONE
        elif luxmode == LuxMode.second_heatsource:
            return PRESET_SECOND_HEATSOURCE
        elif luxmode == LuxMode.party:
            return PRESET_BOOST
        elif luxmode == LuxMode.holidays:
            return PRESET_AWAY
        return PRESET_NONE

    def set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        self._attr_preset_mode = preset_mode
        self._last_lux_mode = self.__get_luxmode(self.hvac_mode, preset_mode)
        self._luxtronik.write(self._heater_sensor.split('.')[1],
                              self._last_lux_mode.value,
                              use_debounce=False,
                              update_immediately_after_write=True)
        self.schedule_update_ha_state(force_refresh=True)

    # region Helper
    def __is_luxtronik_sensor(self, sensor: str) -> bool:
        return sensor.startswith(CONF_PARAMETERS + '.') or sensor.startswith(CONF_CALCULATIONS + '.') or sensor.startswith(CONF_VISIBILITIES + '.')
    # endregion Helper


class LuxtronikDomesticWaterThermostat(LuxtronikThermostat):
    _attr_unique_id: Final = 'domestic_water'
    _attr_device_class: Final = f"{DOMAIN}__{_attr_unique_id}"

    _attr_target_temperature_step = 1.0
    _attr_min_temp = 40.0
    _attr_max_temp = 58.0

    _target_temperature_sensor: Final = LUX_SENSOR_DOMESTIC_WATER_TARGET_TEMPERATURE
    _heater_sensor: Final = LUX_SENSOR_MODE_DOMESTIC_WATER
    _heat_status: Final = [LUX_STATUS_DOMESTIC_WATER]

    @property
    def icon(self):  # -> str | None:
        result_icon = 'mdi:water-boiler'
        if self.hvac_mode == HVACMode.OFF:
            result_icon += '-off'
        elif self.hvac_mode == HVACMode.AUTO:
            result_icon += '-auto'
        return result_icon

    def _is__heating_on_special(self) -> bool:
        return self._luxtronik.get_value(self._status_sensor) == LUX_STATUS_DEFROST and self._attr_hvac_mode != HVACMode.OFF and self._luxtronik.get_value(LUX_BINARY_SENSOR_DOMESTIC_WATER_RECIRCULATION_PUMP)


class LuxtronikHeatingThermostat(LuxtronikThermostat):
    _attr_unique_id = 'heating'
    _attr_device_class: Final = f"{DOMAIN}__{_attr_unique_id}"

    # _attr_target_temperature = 20.5
    _attr_target_temperature_step = 0.1
    _attr_min_temp = -5.0
    _attr_max_temp = +5.0

    _target_temperature_sensor: Final = LUX_SENSOR_HEATING_TARGET_CORRECTION
    _heater_sensor: Final = LUX_SENSOR_MODE_HEATING
    _heat_status: Final = [LUX_STATUS_HEATING]

    @property
    def icon(self):  # -> str | None:
        result_icon = 'mdi:radiator'
        if self.hvac_mode == HVACMode.OFF:
            result_icon += '-off'
        return result_icon

    def _is__heating_on_special(self) -> bool:
        return self._luxtronik.get_value(self._status_sensor) in [LUX_STATUS_DEFROST] and self._attr_hvac_mode != HVACMode.OFF and self._luxtronik.get_value(LUX_BINARY_SENSOR_CIRCULATION_PUMP_HEATING)


class LuxtronikCoolingThermostat(LuxtronikThermostat):
    _attr_unique_id = 'cooling'
    _attr_icon = 'mdi:snowflake'
    _attr_device_class: Final = f"{DOMAIN}__{_attr_unique_id}"

    _target_temperature_sensor = LUX_SENSOR_COOLING_THRESHOLD
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 18.0
    _attr_max_temp = 30.0
    _attr_preset_modes = [PRESET_NONE]

    # _heater_sensor: Final = LUX_SENSOR_MODE_HEATING

# temperature setpoint for cooling
# parameters.ID_Sollwert_KuCft2_akt
# 20.0

# parameters.ID_Einst_Kuhl_Zeit_Ein_akt
# start cooling after this timeout
# 12.0

# parameters.ID_Einst_Kuhl_Zeit_Aus_akt
# stop cooling after this timeout
# 12.0
    _heater_sensor = LUX_SENSOR_MODE_COOLING
    _heat_status = [LUX_STATUS_COOLING]
