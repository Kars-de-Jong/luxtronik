"""Luxtronik heatpump sensor."""
# region Imports
from datetime import datetime, time, timezone

from homeassistant.components.sensor import (ENTITY_ID_FORMAT,
                                             SensorDeviceClass, SensorEntity,
                                             SensorStateClass)
from homeassistant.const import (CONF_FRIENDLY_NAME, CONF_ICON, CONF_ID,
                                 CONF_SENSORS,
                                 STATE_UNAVAILABLE,
                                 UnitOfElectricPotential, UnitOfEnergy, UnitOfPower,
                                 UnitOfPressure, UnitOfTemperature, UnitOfTime)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import ChildDeviceInfo
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from .const import (ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY, ATTR_STATUS_TEXT,
                    CONF_GROUP,
                    DEFAULT_DEVICE_CLASS, DEVICE_CLASSES, DOMAIN, ICONS,
                    LOGGER, LUX_BINARY_SENSOR_ADDITIONAL_CIRCULATION_PUMP,
                    LUX_SENSOR_MODE_COOLING,
                    LUX_SENSOR_MODE_HEATING, LUX_SENSOR_STATUS,
                    LUX_SENSOR_STATUS1, LUX_SENSOR_STATUS3, LUX_STATE_ICON_MAP,
                    LUX_STATES_ON, LUX_STATUS1_HEATPUMP_COMING,
                    LUX_STATUS1_HEATPUMP_SHUTDOWN, LUX_STATUS1_WORKAROUND,
                    LUX_STATUS3_WORKAROUND, LUX_STATUS_DOMESTIC_WATER,
                    LUX_STATUS_EVU, LUX_STATUS_HEATING, LUX_STATUS_NO_REQUEST,
                    LUX_STATUS_COOLING,
                    LUX_STATUS_THERMAL_DESINFECTION, SCAN_INTERVAL_DEVICE,
                    SECOUND_TO_HOUR_FACTOR,
                    UNITS, LuxMode)
from .helpers.helper import get_sensor_text, get_sensor_value_text
from .luxtronik_device import LuxtronikDevice
from .model import LuxtronikConfigEntry, get_runtime_data

# endregion Imports

# region Constants
# The device read is throttled, so all entities share one controller read.
SCAN_INTERVAL = SCAN_INTERVAL_DEVICE
# endregion Constants

# region Setup


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Set up a Luxtronik sensor from yaml config."""
    LOGGER.info(
        f"{DOMAIN}.sensor.async_setup_platform ConfigType: %s - discovery_info: %s",
        config,
        discovery_info,
    )
    runtime_data = get_runtime_data(hass)
    if not runtime_data:
        LOGGER.warning("%s.sensor.async_setup_platform no luxtronik!", DOMAIN)
        return False
    luxtronik = runtime_data.device

    # use_legacy_sensor_ids = hass.data[f"{DOMAIN}_{CONF_USE_LEGACY_SENSOR_IDS}"]
    # LOGGER.info("sensor.async_setup_platform use_legacy_sensor_ids: '%s'",
    #             use_legacy_sensor_ids)

    sensors = config.get(CONF_SENSORS)
    entities = []
    if sensors:
        # region yaml sensors part:
        for sensor_cfg in sensors:
            sensor_id = sensor_cfg[CONF_ID]
            if "." in sensor_id:
                group = sensor_id.split(".")[0]
                sensor_id = sensor_id.split(".")[1]
            else:
                group = sensor_cfg[CONF_GROUP]
            sensor = luxtronik.get_sensor(group, sensor_id)
            if sensor:
                name = (
                    sensor.name
                    if not sensor_cfg.get(CONF_FRIENDLY_NAME)
                    else sensor_cfg.get(CONF_FRIENDLY_NAME)
                )
                icon = (
                    ICONS.get(sensor.measurement_type)
                    if not sensor_cfg.get(CONF_ICON)
                    else sensor_cfg.get(CONF_ICON)
                )
                entity = LuxtronikSensor(
                    luxtronik=luxtronik,
                    # YAML platforms have no config entry, so their entities can't belong to a device.
                    device_info=None,
                    sensor_key=f"{group}.{sensor_id}",
                    unique_id=sensor_id,
                    icon=icon,
                    device_class=DEVICE_CLASSES.get(
                        sensor.measurement_type, DEFAULT_DEVICE_CLASS
                    ),
                    state_class=None,
                    unit_of_measurement=UNITS.get(sensor.measurement_type),
                )
                # Keep the unique_id and name of sensors configured in YAML.
                entity._attr_has_entity_name = False
                entity._attr_translation_key = None
                entity._attr_name = name
                entity._attr_unique_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{sensor_id}")
                entities += [entity]
            else:
                LOGGER.warning(
                    "%s.sensor.async_setup_platform: Invalid Luxtronik ID %s in group %s",
                    DOMAIN,
                    sensor_id,
                    group,
                )
        # endregion yaml sensors part

    async_add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LuxtronikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Luxtronik sensor from ConfigEntry."""
    LOGGER.info(f"{DOMAIN}.sensor.async_setup_entry ConfigType: %s", config_entry)
    luxtronik = config_entry.runtime_data.device
    luxtronik.read()

    device_info = config_entry.runtime_data.device_info

    # entities: list[LuxtronikSensor] = [
    #     LuxtronikStatusSensor(hass, luxtronik, device_info, description)
    #     for description in GLOBAL_STATUS_SENSOR_TYPES
    #     # if description.key in MONITORED_CONDITIONS
    # ]
    # entities.extend(
    #     [
    #         LuxtronikSensor(hass, luxtronik, device_info, description)
    #         for description in GLOBAL_SENSOR_TYPES
    #     ]
    # )

    entities = [
        LuxtronikStatusSensor(
            luxtronik,
            device_info,
            LUX_SENSOR_STATUS,
            "status",
            LUX_STATE_ICON_MAP,
            f"{DOMAIN}__status",
            None,
            None,
            # entity_category=EntityCategory.DIAGNOSTIC,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_HauptMenuStatus_Zeit",
            "status_time",
            "mdi:timer-sand",
            device_class=None,
            state_class=None,
            unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_visible_default=False,
            extra_attributes={
                # Laufzeit seit dem WP aktiv ist
                'WP Seit (ID_WEB_Time_WPein_akt)': 'calculations.ID_WEB_Time_WPein_akt',
                'ZWE1 seit (ID_WEB_Time_ZWE1_akt)': 'calculations.ID_WEB_Time_ZWE1_akt',
                # 'ZWE2 seit (ID_WEB_Time_ZWE2_akt)': 'calculations.ID_WEB_Time_ZWE2_akt',
                'Netzeinschaltv. (ID_WEB_Timer_EinschVerz)': 'calculations.ID_WEB_Timer_EinschVerz',
                'Schaltspielsperre SSP-Aus-Zeit (ID_WEB_Time_SSPAUS_akt)': 'calculations.ID_WEB_Time_SSPAUS_akt',
                'Schaltspielsperre SSP-Ein-Zeit (ID_WEB_Time_SSPEIN_akt)': 'calculations.ID_WEB_Time_SSPEIN_akt',
                'VD-Stand (ID_WEB_Time_VDStd_akt)': 'calculations.ID_WEB_Time_VDStd_akt',
                'Heizungsregler Mehr-Zeit HRM-Zeit (ID_WEB_Time_HRM_akt)': 'calculations.ID_WEB_Time_HRM_akt',
                'Heizungsregler Weniger-Zeit HRW-Stand (ID_WEB_Time_HRW_akt)': 'calculations.ID_WEB_Time_HRW_akt',
                # TDI seti?
                'ID_WEB_Time_LGS_akt': 'calculations.ID_WEB_Time_LGS_akt',
                'Sperre WW? ID_WEB_Time_SBW_akt': 'calculations.ID_WEB_Time_SBW_akt',
                'Abtauen in ID_WEB_Time_AbtIn': 'calculations.ID_WEB_Time_AbtIn',
                'ID_WEB_Time_Heissgas': 'calculations.ID_WEB_Time_Heissgas'
            }
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            LUX_SENSOR_STATUS1,
            "status_line_1",
            "mdi:numeric-1-circle",
            f"{DOMAIN}__status_line_1",
            None,
            None,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_visible_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_HauptMenuStatus_Zeile2",
            "status_line_2",
            "mdi:numeric-2-circle",
            f"{DOMAIN}__status_line_2",
            None,
            None,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_visible_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            LUX_SENSOR_STATUS3,
            "status_line_3",
            "mdi:numeric-3-circle",
            f"{DOMAIN}__status_line_3",
            None,
            None,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_visible_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_Temperatur_TWE",
            "heat_source_input_temperature",
            entity_category=None,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_Temperatur_TA",
            "outdoor_temperature",
            entity_category=None,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_Mitteltemperatur",
            "outdoor_temperature_average",
            entity_category=None,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_Zaehler_BetrZeitImpVD1",
            unique_id="compressor_impulses",
            icon="mdi:pulse",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="Anzahl",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_Zaehler_BetrZeitVD1",
            unique_id="operation_hours_compressor1",
            icon="mdi:timer-sand",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.HOURS,
            entity_category=EntityCategory.DIAGNOSTIC,
            factor=SECOUND_TO_HOUR_FACTOR,
        ),
    ]
    has_second_compressor = luxtronik.get_value("calculations.ID_WEB_Zaehler_BetrZeitImpVD2") > 0
    if has_second_compressor:
        entities += [
            LuxtronikSensor(
                luxtronik,
                device_info,
                sensor_key="calculations.ID_WEB_Zaehler_BetrZeitVD2",
                unique_id="operation_hours_compressor2",
                icon="mdi:timer-sand",
                device_class=None,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfTime.HOURS,
                entity_category=EntityCategory.DIAGNOSTIC,
                factor=SECOUND_TO_HOUR_FACTOR,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info,
                sensor_key="calculations.ID_WEB_Zaehler_BetrZeitImpVD2",
                unique_id="compressor_impulses2",
                icon="mdi:pulse",
                device_class=None,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=None,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]

    entities += [
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_Zaehler_BetrZeitWP",
            unique_id="operation_hours",
            icon="mdi:timer-sand",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.HOURS,
            entity_category=EntityCategory.DIAGNOSTIC,
            factor=SECOUND_TO_HOUR_FACTOR,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_WMZ_Seit",
            unique_id="heat_amount_counter",
            icon="mdi:lightning-bolt-circle",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),

        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_Temperatur_THG",
            "hot_gas_temperature",
            entity_category=None,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_ANSAUG_VERDICHTER",
            "suction_compressor_temperature",
            entity_category=None,
            entity_registry_enabled_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_ANSAUG_VERDAMPFER",
            "suction_evaporator_temperature",
            entity_category=None,
            entity_registry_enabled_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_VDH",
            "compressor_heating_temperature",
            entity_category=None,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_UH",
            "overheating_temperature",
            device_class=None,
            entity_category=None,
            unit_of_measurement=UnitOfTemperature.KELVIN,
            entity_registry_enabled_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_UH_Soll",
            "overheating_target_temperature",
            entity_category=None,
            unit_of_measurement=UnitOfTemperature.KELVIN,
            entity_registry_enabled_default=False,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_HD",
            "high_pressure",
            entity_category=None,
            unit_of_measurement=UnitOfPressure.BAR,
            entity_registry_enabled_default=False,
            device_class=SensorDeviceClass.PRESSURE,
            icon="mdi:gauge-full",
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            "calculations.ID_WEB_LIN_ND",
            "low_pressure",
            entity_category=None,
            unit_of_measurement=UnitOfPressure.BAR,
            entity_registry_enabled_default=False,
            device_class=SensorDeviceClass.PRESSURE,
            icon="mdi:gauge-low",
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_Zaehler_BetrZeitZWE1",
            unique_id="operation_hours_additional_heat_generator",
            icon="mdi:timer-sand",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.HOURS,
            entity_category=EntityCategory.DIAGNOSTIC,
            factor=SECOUND_TO_HOUR_FACTOR,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_AnalogOut1",
            unique_id="analog_out1",
            icon="mdi:alpha-v-circle-outline",
            device_class=SensorDeviceClass.VOLTAGE,
            unit_of_measurement=UnitOfElectricPotential.VOLT,
            entity_registry_enabled_default=False,
            factor=0.1,
        ),
        LuxtronikSensor(
            luxtronik,
            device_info,
            sensor_key="calculations.ID_WEB_AnalogOut2",
            unique_id="analog_out2",
            icon="mdi:alpha-v-circle-outline",
            device_class=SensorDeviceClass.VOLTAGE,
            unit_of_measurement=UnitOfElectricPotential.VOLT,
            entity_registry_enabled_default=False,
            factor=0.1,
        ),
        LuxtronikIndexStatusSensor(
            key_index=None,
            key_timestamp_template=None,
            luxtronik=luxtronik,
            device_info=device_info,
            sensor_key="Switchoff",
            unique_id="switchoff_reason",
            icon="mdi:electric-switch",
            unit_of_measurement=None,
            state_class=None,
            device_class=None,
            extra_value_attributes=["code"],
        ),
        LuxtronikIndexStatusSensor(
            key_index="calculations.ID_WEB_AnzahlFehlerInSpeicher",
            key_timestamp_template="calculations.ID_WEB_ERROR_Time0",
            luxtronik=luxtronik,
            device_info=device_info,
            sensor_key="calculations.ID_WEB_ERROR_Nr0",
            unique_id="error_reason",
            icon="mdi:alert",
            unit_of_measurement=None,
            state_class=None,
            device_class=None,
            extra_value_attributes=["code", "cause", "remedy"],
        ),
    ]
    if luxtronik.get_value("calculations.Heat_Output") is not None:
        entities += [
            LuxtronikSensor(
                luxtronik,
                device_info,
                sensor_key="calculations.Heat_Output",
                unique_id="current_heat_output",
                icon="mdi:lightning-bolt-circle",
                device_class=SensorDeviceClass.POWER,
                unit_of_measurement=UnitOfPower.WATT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]
    add_sensor_if_active(luxtronik, entities, "visibilities.ID_Visi_Waermemenge_ZWE", LuxtronikSensor(
        luxtronik,
        device_info,
        sensor_key="parameters.ID_Waermemenge_ZWE",
        unique_id="additional_heat_generator_amount_counter",
        icon="mdi:lightning-bolt-circle",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        factor=0.1)
    )

    if device_info.get('model') != 'LD7':
        entities += [
            LuxtronikSensor(
                luxtronik,
                device_info,
                "calculations.ID_WEB_Freq_VD",
                "pump_frequency",
                entity_category=None,
                icon="mdi:sine-wave",
                unit_of_measurement='Hz',
                entity_registry_enabled_default=False,
                device_class=SensorDeviceClass.FREQUENCY,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info,
                "calculations.ID_WEB_Temperatur_TWA",
                "heat_source_output_temperature",
                entity_category=None,
                entity_registry_enabled_default=False,
            ),
        ]

    device_info_heating = config_entry.runtime_data.device_info_heating
    if device_info_heating is not None:
        has_room_temp = luxtronik.get_value("parameters.ID_Einst_RFVEinb_akt") != 0
        if has_room_temp:
            entities += [
                LuxtronikSensor(
                    luxtronik,
                    device_info_heating,
                    "calculations.ID_WEB_RBE_RT_Ist",
                    "room_temperature",
                    entity_category=None,
                ),
                LuxtronikSensor(
                    luxtronik,
                    device_info_heating,
                    "calculations.ID_WEB_RBE_RT_Soll",
                    "room_target_temperature",
                    entity_category=None,
                ),
            ]

        entities += [
            LuxtronikSensor(
                luxtronik,
                device_info_heating,
                "calculations.ID_WEB_Temperatur_TVL",
                "flow_in_temperature",
                "mdi:waves-arrow-right",
                entity_category=None,
                extra_attributes={
                    'max_allowed': 'parameters.ID_Einst_TVLmax_akt'
                }
            ),
            LuxtronikSensor(
                luxtronik,
                device_info_heating,
                "calculations.ID_WEB_Temperatur_TRL",
                "flow_out_temperature",
                "mdi:waves-arrow-left",
                entity_category=None,
            ),
            LuxtronikFlowOutStatusSensor(
                luxtronik,
                device_info_heating,
                "calculations.ID_WEB_Sollwert_TRL_HZ",
                "flow_out_temperature_target",
                entity_category=None,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info_heating,
                sensor_key="calculations.ID_WEB_Zaehler_BetrZeitHz",
                unique_id="operation_hours_heating",
                icon="mdi:timer-sand",
                device_class=None,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfTime.HOURS,
                entity_category=EntityCategory.DIAGNOSTIC,
                factor=SECOUND_TO_HOUR_FACTOR,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info_heating,
                sensor_key="calculations.ID_WEB_WMZ_Heizung",
                unique_id="heat_amount_heating",
                icon="mdi:lightning-bolt-circle",
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]
        add_sensor_if_min_minor_version(luxtronik, entities, 88, LuxtronikSensor(
            luxtronik,
            device_info_heating,
            sensor_key="parameters.Unknown_Parameter_1136",
            unique_id="heat_energy_input",
            icon="mdi:circle-slice-3",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            entity_category=EntityCategory.DIAGNOSTIC,
            factor=0.01,)
        )

    add_sensor_if_active(luxtronik, entities, "visibilities.ID_Visi_Temp_Rucklauf", LuxtronikSensor(
        luxtronik,
        device_info_heating,
        "calculations.ID_WEB_Temperatur_TRL_ext",
        "flow_out_temperature_external",
        "mdi:waves-arrow-right",
        entity_category=None)
    )

    device_info_domestic_water = config_entry.runtime_data.device_info_domestic_water
    if device_info_domestic_water is not None:

        entities += [
            LuxtronikSensor(
                luxtronik,
                device_info_domestic_water,
                "calculations.ID_WEB_Temperatur_TBW",
                "domestic_water_temperature",
                "mdi:coolant-temperature",
                entity_category=None,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info_domestic_water,
                sensor_key="calculations.ID_WEB_Zaehler_BetrZeitBW",
                unique_id="operation_hours_domestic_water",
                icon="mdi:timer-sand",
                device_class=None,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfTime.HOURS,
                entity_category=EntityCategory.DIAGNOSTIC,
                factor=SECOUND_TO_HOUR_FACTOR,
            ),
            LuxtronikSensor(
                luxtronik,
                device_info_domestic_water,
                sensor_key="calculations.ID_WEB_WMZ_Brauchwasser",
                unique_id="heat_amount_domestic_water",
                icon="mdi:lightning-bolt-circle",
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]
        add_sensor_if_min_minor_version(luxtronik, entities, 88, LuxtronikSensor(
            luxtronik,
            device_info_domestic_water,
            sensor_key="parameters.Unknown_Parameter_1137",
            unique_id="domestic_water_energy_input",
            icon="mdi:circle-slice-3",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            entity_category=EntityCategory.DIAGNOSTIC,
            factor=0.01)
        )

        # Temp. disabled:
        solar_present = luxtronik.detect_solar_present()
        if solar_present:
            # if luxtronik.get_value("visibilities.ID_Visi_Temp_Solarkoll") > 0:
            entities += [
                LuxtronikSensor(
                    luxtronik,
                    device_info_domestic_water,
                    "calculations.ID_WEB_Temperatur_TSK",
                    "solar_collector_temperature",
                    "mdi:solar-panel-large",
                    entity_category=None,
                ),
            ]
        # if luxtronik.get_value("visibilities.ID_Visi_Temp_Solarsp") > 0:
            entities += [
                LuxtronikSensor(
                    luxtronik,
                    device_info_domestic_water,
                    "calculations.ID_WEB_Temperatur_TSS",
                    "solar_buffer_temperature",
                    "mdi:propane-tank-outline",
                    entity_category=None,
                ),
            ]
        # if luxtronik.get_value("parameters.ID_BSTD_Solar") > 0:
            entities += [
                LuxtronikSensor(
                    luxtronik,
                    device_info_domestic_water,
                    sensor_key="parameters.ID_BSTD_Solar",
                    unique_id="operation_hours_solar",
                    icon="mdi:timer-sand",
                    device_class=None,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    unit_of_measurement=UnitOfTime.HOURS,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    factor=SECOUND_TO_HOUR_FACTOR,
                ),
            ]

    deviceInfoCooling = config_entry.runtime_data.device_info_cooling
    if deviceInfoCooling is not None:
        entities += [
            LuxtronikSensor(
                luxtronik,
                deviceInfoCooling,
                sensor_key="calculations.ID_WEB_Zaehler_BetrZeitKue",
                unique_id="operation_hours_cooling",
                icon="mdi:timer-sand",
                device_class=None,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit_of_measurement=UnitOfTime.HOURS,
                entity_category=EntityCategory.DIAGNOSTIC,
                factor=SECOUND_TO_HOUR_FACTOR,
            )
        ]

    async_add_entities(entities)

# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """Unloading the Luxtronik platforms."""
#     luxtronik = hass.data[DOMAIN]
#     if luxtronik is None:
#         return

#     await hass.async_add_executor_job(luxtronik.disconnect)

#     unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
#     if unload_ok:
#         hass.data[DOMAIN] = None

#     return unload_ok


# endregion Setup


class LuxtronikSensor(SensorEntity, RestoreEntity):
    """Representation of a Luxtronik Sensor."""
    _attr_is_on = True
    _attr_has_entity_name = True

    def __init__(
        self,
        luxtronik: LuxtronikDevice,
        device_info: DeviceInfo | ChildDeviceInfo | None,
        sensor_key: str,
        unique_id: str,
        icon: str = "mdi:thermometer",
        device_class: SensorDeviceClass = SensorDeviceClass.TEMPERATURE,
        state_class: SensorStateClass = SensorStateClass.MEASUREMENT,
        unit_of_measurement: str = UnitOfTemperature.CELSIUS,
        entity_category: EntityCategory = None,
        factor: float = None,
        entity_registry_visible_default: bool = True,
        entity_registry_enabled_default: bool = True,
        extra_attributes: dict = None,
        # *args: Any,
        # **kwargs: Any
    ) -> None:
        """Initialize the sensor."""
        # super().__init__(*args)
#        super(LuxtronikSensor, self).__init__(*args)
        self._luxtronik = luxtronik

        self._attr_unique_id = f"{luxtronik.unique_id}_{unique_id}"
        self._attr_translation_key = unique_id
        self._attr_device_class = device_class
        self._icon = icon
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._sensor_key = sensor_key
        self._attr_state_class = state_class

        self._attr_device_info = device_info
        self._attr_entity_category = entity_category
        self._factor = factor
        self._attr_entity_registry_visible_default = entity_registry_visible_default
        self._attr_entity_registry_enabled_default = entity_registry_enabled_default
        self._attr_extra_state_attributes = {ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY: sensor_key}
        self._extra_attributes = extra_attributes

    def disable_by_default(self):
        self._attr_entity_registry_enabled_default = False

    @property
    def icon(self):  # -> str | None:
        """Return the icon to be used for this entity."""
        if (
            self._icon is not None
            and isinstance(self._icon, dict)
            and not isinstance(self._icon, str)
        ):
            if self.native_value in self._icon:
                return self._icon[self.native_value]
            return None
        return self._icon

    @property
    def native_value(self):  # -> float | int | None:
        """Return the state of the sensor."""
        value = self._luxtronik.get_value(self._sensor_key)
        if value is not None and isinstance(value, datetime) and value.tzinfo is None:
            time_zone = dt_util.get_time_zone(self.hass.config.time_zone)
            value = value.replace(tzinfo=time_zone)

        if self._sensor_key == LUX_SENSOR_STATUS:
            status3 = self._luxtronik.get_value(LUX_SENSOR_STATUS3)
            if status3 == LUX_STATUS_THERMAL_DESINFECTION:
                # map thermal desinfection to Domestic Water iso Heating
                return LUX_STATUS_DOMESTIC_WATER

        # region Workaround Luxtronik Bug: Status shows heating but status 3 = no request!
        if self._sensor_key == LUX_SENSOR_STATUS and value == LUX_STATUS_HEATING:
            status1 = self._luxtronik.get_value(LUX_SENSOR_STATUS1)
            status3 = self._luxtronik.get_value(LUX_SENSOR_STATUS3)
            additional_circulation_pump = self._luxtronik.get_value(LUX_BINARY_SENSOR_ADDITIONAL_CIRCULATION_PUMP)
            if status1 in LUX_STATUS1_WORKAROUND and status3 in LUX_STATUS3_WORKAROUND and not additional_circulation_pump:
                # pump forerun
                return LUX_STATUS_NO_REQUEST
            # endregion Workaround Luxtronik Bug: Status shows heating but status 3 = no request!
        # region Workaround Luxtronik Bug: Line 1 shows 'heatpump coming' on shutdown!
        elif self._sensor_key == LUX_SENSOR_STATUS1 and value == LUX_STATUS1_HEATPUMP_COMING:
            if int(self._luxtronik.get_value('calculations.ID_WEB_Time_SSPEIN_akt')) < 10 and int(self._luxtronik.get_value('calculations.ID_WEB_Time_SSPAUS_akt')) > 0:
                return LUX_STATUS1_HEATPUMP_SHUTDOWN
            # endregion Workaround Luxtronik Bug: Line 1 shows 'heatpump coming' on shutdown!

        # workaround to detect (passive) cooling active
        if (self._sensor_key == LUX_SENSOR_STATUS) and (value == LUX_STATUS_NO_REQUEST):
            if self._luxtronik.detect_cooling_present():
                cooling_active = self._luxtronik.get_value(LUX_SENSOR_MODE_COOLING) == LuxMode.automatic.value
                pump_flow_active = self._luxtronik.get_value("calculations.ID_WEB_VBOout")
                temp_in = self._luxtronik.get_value("calculations.ID_WEB_Temperatur_TVL")
                temp_out = self._luxtronik.get_value("calculations.ID_WEB_Temperatur_TRL")
                temp_heat_in = self._luxtronik.get_value("calculations.ID_WEB_Temperatur_TWE")
                temp_heat_out = self._luxtronik.get_value("calculations.ID_WEB_Temperatur_TWA")
                flow_heat_source = self._luxtronik.get_value("calculations.ID_WEB_Durchfluss_WQ")

                if cooling_active and pump_flow_active and (temp_out > temp_in) and (temp_heat_out > temp_heat_in) and (flow_heat_source > 0):
                    return LUX_STATUS_COOLING

        return value if value is None or self._factor is None else round(value * self._factor, 2)

    @property
    def is_on(self) -> bool:
        """Return true if sensor is on."""
        return self.native_value in LUX_STATES_ON

    def update(self):
        """Get the latest status and use it to update our sensor state."""
        self._luxtronik.update()
        if self._sensor_key == "calculations.ID_WEB_HauptMenuStatus_Zeit":
            value = self.native_value
            if value is None:
                time_str = None
            else:
                (minutes, seconds) = divmod(int(value), 60)
                hours, minutes = divmod(minutes, 60)
                time_str = f"{hours:01.0f}:{minutes:02.0f} h"
            self._attr_extra_state_attributes[ATTR_STATUS_TEXT] = time_str
        if self._extra_attributes is not None:
            for key, value in self._extra_attributes.items():
                self._attr_extra_state_attributes[key] = self._luxtronik.get_value(value)


class LuxtronikIndexStatusSensor(LuxtronikSensor):
    # _min_index = 0
    # _max_index = 4

    def __init__(self, key_index: str, key_timestamp_template: str, extra_value_attributes: list = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._key_index = key_index
        self._key_timestamp_template = key_timestamp_template
        self._key_template = self._sensor_key
        self._extra_value_attributes = extra_value_attributes
        self._update_sensor_keys()

    def _update_sensor_keys(self):
        self._luxtronik.update()
        if self._key_index is None or self._key_index == "":
            index = max(self._luxtronik.get_value(f"parameters.ID_{self._key_template}_index") - 1, 0)
            self._sensor_key = f"parameters.ID_{self._key_template}_file_{index}_0"
            self._sensor_key_timestamp = f"parameters.ID_{self._key_template}_file_{index}_1"
        else:
            index = self._luxtronik.get_value(self._key_index)
            self._sensor_key = self._key_template.replace("%n", str(index))
            self._sensor_key_timestamp = self._key_timestamp_template.replace("%n", str(index))

    def update(self):
        """Get the latest status and use it to update our sensor state."""
        self._update_sensor_keys()

    @property
    def native_value(self) -> str:
        value = str(self._luxtronik.get_value(self._sensor_key))
        value_timestamp = self._luxtronik.get_value(self._sensor_key_timestamp)
        if value_timestamp is not None and isinstance(value_timestamp, int):
            value_timestamp = datetime.fromtimestamp(value_timestamp, timezone.utc)
        if value_timestamp is not None and isinstance(value_timestamp, datetime) and value_timestamp.tzinfo is None:
            time_zone = dt_util.get_time_zone(self.hass.config.time_zone)
            value_timestamp = value_timestamp.replace(tzinfo=time_zone)
        self._attr_extra_state_attributes["timestamp"] = value_timestamp
        self._attr_extra_state_attributes[ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY] = self._sensor_key
        if self._extra_value_attributes is not None:
            for attr in self._extra_value_attributes:
                self._attr_extra_state_attributes[attr] = value
        return value

        # um ID_Switchoff_file_n_1 /
        # weil ID_Switchoff_index --> ID_Switchoff_file_n_0 0 1 2 3 4
    #   "95   ID_WEB_ERROR_Time0                                          ": "2023-01-10 15:54:09",
    #   "96   ID_WEB_ERROR_Time1                                          ": "2022-07-19 14:58:53",
    #   "97   ID_WEB_ERROR_Time2                                          ": "2021-06-30 10:58:56",
    #   "98   ID_WEB_ERROR_Time3                                          ": "2021-06-30 10:57:49",
    #   "99   ID_WEB_ERROR_Time4                                          ": "2021-06-30 10:57:35",
    #   "100  ID_WEB_ERROR_Nr0                                            ": "717",
    #   "101  ID_WEB_ERROR_Nr1                                            ": "718",
    #   "102  ID_WEB_ERROR_Nr2                                            ": "761",
    #   "103  ID_WEB_ERROR_Nr3                                            ": "761",
    #   "104  ID_WEB_ERROR_Nr4                                            ": "761",

    #   "716  ID_Switchoff_file_0_0                                       ": "11",
    #   "717  ID_Switchoff_file_1_0                                       ": "11",
    #   "718  ID_Switchoff_file_2_0                                       ": "11",
    #   "719  ID_Switchoff_file_3_0                                       ": "11",
    #   "720  ID_Switchoff_file_4_0                                       ": "11",
    #   "721  ID_Switchoff_file_0_1                                       ": "1673360523",
    #   "722  ID_Switchoff_file_1_1                                       ": "1673360914",
    #   "723  ID_Switchoff_file_2_1                                       ": "1673361275",
    #   "724  ID_Switchoff_file_3_1                                       ": "1673361666",
    #   "725  ID_Switchoff_file_4_1                                       ": "1673362057",


class LuxtronikFlowOutStatusSensor(LuxtronikSensor, RestoreEntity):
    def _calc_switch_gap(self) -> float:
        flow_out_target = float(self._luxtronik.get_value("calculations.ID_WEB_Sollwert_TRL_HZ"))
        flow_out = float(self._luxtronik.get_value("calculations.ID_WEB_Temperatur_TRL"))
        hyst = float(self._luxtronik.get_value("parameters.ID_Einst_HRHyst_akt")) * 0.1

        if self._luxtronik.get_value(LUX_SENSOR_STATUS) == LUX_STATUS_HEATING:
            return flow_out + hyst - flow_out_target
        elif self._luxtronik.get_value(LUX_SENSOR_MODE_HEATING) != LuxMode.off.value:
            return flow_out - hyst - flow_out_target
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes of the device."""
        return {
            ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY: self._sensor_key,
            'switch_gap': self._calc_switch_gap(),
        }


class LuxtronikStatusSensor(LuxtronikSensor, RestoreEntity):
    """Luxtronik Status Sensor with extended attr."""

    _last_state: str = None

    _first_evu_start_time: time = None
    _first_evu_end_time: time = None
    _second_evu_start_time: time = None
    _second_evu_end_time: time = None

    def update(self):
        LuxtronikSensor.update(self)
        time_now = time(datetime.now().hour, datetime.now().minute)
        if self.native_value is not None and self._last_state is not None and self.native_value == LUX_STATUS_EVU and self._last_state != LUX_STATUS_EVU:
            # evu start
            if self._first_evu_start_time is None or time_now.hour <= self._first_evu_start_time.hour or (self._second_evu_start_time is not None and time_now.hour < self._second_evu_start_time.hour) or time_now.hour <= self._first_evu_end_time.hour:
                self._first_evu_start_time = time_now
            else:
                self._second_evu_start_time = time_now
        elif self.native_value is not None and self._last_state is not None and self.native_value != LUX_STATUS_EVU and self._last_state == LUX_STATUS_EVU:
            # evu end
            if self._first_evu_end_time is None or time_now.hour <= self._first_evu_end_time.hour or (self._second_evu_start_time is not None and time_now < self._second_evu_start_time):
                self._first_evu_end_time = time_now
            else:
                self._second_evu_end_time = time_now

        self._last_state = self.native_value

    def _get_sensor_value(self, sensor_name: str):
        sensor = self.hass.states.get(sensor_name)
        if sensor is not None:
            return sensor.state
        return None

    def _get_sensor_attr(self, sensor_name: str, attr: str):
        sensor = self.hass.states.get(sensor_name)
        if sensor is not None and attr in sensor.attributes:
            return sensor.attributes[attr]
        return None

    def _build_status_text(self) -> str:
        status_time = self._get_sensor_attr(
            f"sensor.{DOMAIN}_status_time", ATTR_STATUS_TEXT
        )
        line_1 = self._get_sensor_value(f"sensor.{DOMAIN}_status_line_1")
        line_2 = self._get_sensor_value(f"sensor.{DOMAIN}_status_line_2")
        if (
            status_time is None
            or status_time == STATE_UNAVAILABLE
            or line_1 is None
            or line_1 == STATE_UNAVAILABLE
            or line_2 is None
            or line_2 == STATE_UNAVAILABLE
        ):
            return ""
        lang = self.hass.config.language
        line_1 = get_sensor_value_text(lang, f"{DOMAIN}__status_line_1", line_1)
        line_2 = get_sensor_value_text(lang, f"{DOMAIN}__status_line_2", line_2)
        # Show evu end time if available
        evu_event_minutes = self._calc_next_evu_event_minutes()
        if evu_event_minutes is None:
            pass
        elif self.native_value == LUX_STATUS_EVU:
            evu_until = get_sensor_text(lang, 'evu_until').format(evu_time=evu_event_minutes)
            return f"{evu_until} {line_1} {line_2} {status_time}."
        elif evu_event_minutes <= 30:
            evu_in = get_sensor_text(lang, 'evu_in').format(evu_time=evu_event_minutes)
            return f"{line_1} {line_2} {status_time}. {evu_in}"
        return f"{line_1} {line_2} {status_time}."

    def _calc_next_evu_event_minutes_text(self) -> str:
        minutes = self._calc_next_evu_event_minutes()
        return '' if minutes is None else str(minutes)

    def _calc_next_evu_event_minutes(self) -> int:
        evu_time = self._get_next_evu_event_time()
        time_now = time(datetime.now().hour, datetime.now().minute)
        if evu_time is None:
            return None
        evu_hours = (24 if evu_time < time_now else 0) + evu_time.hour
        return (evu_hours - time_now.hour) * 60 + evu_time.minute - time_now.minute

    def _get_next_evu_event_time(self) -> time:
        event: time = None
        time_now = time(datetime.now().hour, datetime.now().minute)
        for evu_time in [self._first_evu_start_time, self._first_evu_end_time, self._second_evu_start_time, self._second_evu_end_time]:
            if evu_time is None:
                continue
            if evu_time > time_now and (event is None or evu_time < event):
                event = evu_time
        if event is None:
            for evu_time in [self._first_evu_start_time, self._first_evu_end_time, self._second_evu_start_time, self._second_evu_end_time]:
                if evu_time is None:
                    continue
                if event is None or evu_time < event:
                    event = evu_time
        return event

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes of the device."""
        return {
            ATTR_STATUS_TEXT: self._build_status_text(),
            ATTR_EXTRA_STATE_ATTRIBUTE_LUXTRONIK_KEY: self._sensor_key,
            'status raw': self._luxtronik.get_value(self._sensor_key),
            'EVU first start time': '' if self._first_evu_start_time is None else self._first_evu_start_time.strftime('%H:%M'),
            'EVU first end time': '' if self._first_evu_end_time is None else self._first_evu_end_time.strftime('%H:%M'),
            'EVU second start time': '' if self._second_evu_start_time is None else self._second_evu_start_time.strftime('%H:%M'),
            'EVU second end time': '' if self._second_evu_end_time is None else self._second_evu_end_time.strftime('%H:%M'),
            'EVU minutes until next event': self._calc_next_evu_event_minutes_text(),
        }

    def _restore_value(self, value: str) -> time:
        if value is None or ':' not in value:
            return None
        vals = value.split(':')
        return time(int(vals[0]), int(vals[1]))

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        DATA_UPDATED = f"{DOMAIN}_data_updated"
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, DATA_UPDATED, self._schedule_immediate_update
            )
        )
        state = await self.async_get_last_state()
        if not state:
            return
        self._state = state.state

        if 'EVU first start time' in state.attributes:
            self._first_evu_start_time = self._restore_value(state.attributes['EVU first start time'])
            self._first_evu_end_time = self._restore_value(state.attributes['EVU first end time'])
            self._second_evu_start_time = self._restore_value(state.attributes['EVU second start time'])
            self._second_evu_end_time = self._restore_value(state.attributes['EVU second end time'])

    @callback
    def _schedule_immediate_update(self):
        self.async_schedule_update_ha_state(True)


def add_sensor_if_active(luxtronik, entities, check_key: str, sensor: LuxtronikSensor):
    value = luxtronik.get_value(check_key)
    if value is None or value <= 0:
        sensor.disable_by_default()
    entities += [sensor]


def add_sensor_if_min_minor_version(luxtronik, entities, min_minor: int, sensor: LuxtronikSensor):
    if luxtronik.firmware_version_minor >= min_minor:
        entities += [sensor]
