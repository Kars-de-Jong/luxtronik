"""Support for Luxtronik heatpump binary states."""
# region Imports
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import LuxtronikDevice
from .model import LuxtronikConfigEntry
from .const import (ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY, LOGGER,
                    LUX_SENSOR_EFFICIENCY_PUMP, LUX_SENSOR_HEATING_THRESHOLD,
                    LUX_SENSOR_MODE_COOLING, LUX_SENSOR_MODE_DOMESTIC_WATER,
                    LUX_SENSOR_MODE_HEATING, LUX_SENSOR_PUMP_OPTIMIZATION,
                    LUX_SENSOR_REMOTE_MAINTENANCE, SCAN_INTERVAL_DEVICE, LuxMode)

# endregion Imports

# region Constants
# The device read is throttled, so all entities share one controller read.
SCAN_INTERVAL = SCAN_INTERVAL_DEVICE
# endregion Constants

# region Setup


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LuxtronikConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a Luxtronik sensor from ConfigEntry."""
    LOGGER.info(
        "luxtronik2.switch.async_setup_entry ConfigType: %s", config_entry)
    luxtronik = config_entry.runtime_data.device

    entities = []

    device_info = config_entry.runtime_data.device_info
    entities += [
        LuxtronikSwitch(
            hass=hass, luxtronik=luxtronik, device_info=device_info,
            sensor_key=LUX_SENSOR_REMOTE_MAINTENANCE, unique_id='remote_maintenance', icon='mdi:remote-desktop',
            device_class=BinarySensorDeviceClass.HEAT, entity_category=EntityCategory.CONFIG),
        LuxtronikSwitch(
            hass=hass, luxtronik=luxtronik, device_info=device_info,
            sensor_key=LUX_SENSOR_EFFICIENCY_PUMP, unique_id='efficiency_pump', icon='mdi:leaf-circle',
            device_class=BinarySensorDeviceClass.HEAT, entity_category=EntityCategory.CONFIG),
        LuxtronikSwitch(
            hass=hass, luxtronik=luxtronik, device_info=device_info,
            sensor_key='parameters.ID_Einst_P155_PumpHeatCtrl', unique_id='pump_heat_control', icon='mdi:pump',
            device_class=BinarySensorDeviceClass.HEAT, entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False),
    ]

    deviceInfoHeating = config_entry.runtime_data.device_info_heating
    if deviceInfoHeating is not None:
        entities += [
            LuxtronikSwitch(
                hass=hass, luxtronik=luxtronik, device_info=deviceInfoHeating,
                sensor_key=LUX_SENSOR_PUMP_OPTIMIZATION, unique_id='pump_optimization', icon='mdi:tune',
                device_class=BinarySensorDeviceClass.HEAT, entity_category=EntityCategory.CONFIG),
            LuxtronikSwitch(
                on_state=LuxMode.automatic.value, off_state=LuxMode.off.value,
                hass=hass, luxtronik=luxtronik, device_info=deviceInfoHeating,
                sensor_key=LUX_SENSOR_MODE_HEATING, unique_id='heating', icon='mdi:radiator', icon_off='mdi:radiator-off',
                device_class=BinarySensorDeviceClass.HEAT),
            LuxtronikSwitch(
                hass=hass, luxtronik=luxtronik, device_info=deviceInfoHeating,
                sensor_key=LUX_SENSOR_HEATING_THRESHOLD, unique_id='heating_threshold', icon='mdi:download-outline',
                device_class=BinarySensorDeviceClass.HEAT, entity_category=EntityCategory.CONFIG)
        ]

    deviceInfoDomesticWater = config_entry.runtime_data.device_info_domestic_water
    if deviceInfoDomesticWater is not None:
        entities += [
            LuxtronikSwitch(
                on_state=LuxMode.automatic.value, off_state=LuxMode.off.value,
                hass=hass, luxtronik=luxtronik,
                device_info=deviceInfoDomesticWater,
                sensor_key=LUX_SENSOR_MODE_DOMESTIC_WATER,
                unique_id='domestic_water', icon='mdi:water-boiler-auto', icon_off='mdi:water-boiler-off',
                device_class=BinarySensorDeviceClass.HEAT),
        ]

    deviceInfoCooling = config_entry.runtime_data.device_info_cooling
    if deviceInfoCooling is not None:
        entities += [
            LuxtronikSwitch(
                on_state=LuxMode.automatic.value, off_state=LuxMode.off.value,
                hass=hass, luxtronik=luxtronik,
                device_info=deviceInfoCooling,
                sensor_key=LUX_SENSOR_MODE_COOLING,
                unique_id='cooling', icon='mdi:snowflake',
                device_class=BinarySensorDeviceClass.HEAT)
        ]

    async_add_entities(entities)
# endregion Setup


class LuxtronikSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Luxtronik switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        luxtronik: LuxtronikDevice,
        device_info: DeviceInfo,
        sensor_key: str,
        unique_id: str,
        icon: str,
        device_class: str,
        entity_category: EntityCategory = None,
        icon_off: str = None,
        on_state: str = True,
        off_state: str = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize a new Luxtronik switch."""
        self._luxtronik = luxtronik
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{luxtronik.unique_id}_{unique_id}"
        self._attr_translation_key = unique_id
        self._attr_device_info = device_info
        self._attr_icon = icon
        self._icon_off = icon_off
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._on_state = on_state
        self._off_state = off_state
        self._attr_extra_state_attributes = {ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY: sensor_key}

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._luxtronik.write(self._sensor_key.split(
            '.')[1], self._on_state, use_debounce=False,
            update_immediately_after_write=True)
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._luxtronik.write(self._sensor_key.split(
            '.')[1], self._off_state, use_debounce=False,
            update_immediately_after_write=True)
        self.schedule_update_ha_state()

    @property
    def is_on(self):
        """Return true if binary sensor is on."""
        value = self._luxtronik.get_value(self._sensor_key) == self._on_state
        return value

    @property
    def icon(self):  # -> str | None:
        """Return the icon to be used for this entity."""
        if not self.is_on and self._icon_off is not None:
            return self._icon_off
        if self._attr_icon is None:
            super().icon
        return self._attr_icon

    def update(self):
        """Get the latest status and use it to update our sensor state."""
        self._luxtronik.update()
