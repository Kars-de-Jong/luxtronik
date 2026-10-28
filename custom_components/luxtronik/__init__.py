"""Support for Luxtronik heatpump controllers."""
# region Imports

from dataclasses import dataclass
from functools import partial

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config import config_per_platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_BINARY_SENSORS, CONF_ENTITY_NAMESPACE, CONF_HOST, CONF_ID,
                                 CONF_PORT, CONF_SCAN_INTERVAL, CONF_SENSORS,
                                 EVENT_HOMEASSISTANT_STOP, Platform)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import ChildDeviceInfo
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType
from luxtronik import LOGGER as LuxLogger

from .const import (
    ATTR_PARAMETER,
    ATTR_VALUE,
    CONF_GROUP,
    CONF_LOCK_TIMEOUT,
    CONF_SAFE,
    CONF_UPDATE_IMMEDIATELY_AFTER_WRITE,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_WRITE,
    SERVICE_WRITE_SCHEMA,
    YAML_BINARY_SENSOR_SCHEMA,
    YAML_SENSOR_SCHEMA,
)
from .const import CONFIG_SCHEMA  # noqa: F401
from .helpers.helper import get_sensor_text, get_yaml_unique_id, load_texts
from .luxtronik_device import LuxtronikDevice
from .model import LuxtronikConfigEntry, LuxtronikRuntimeData

# endregion Imports

# region Constants
LuxLogger.setLevel(level="WARNING")
# The YAML platforms, with the config entry option that stores their sensors.
YAML_PLATFORMS = {
    Platform.SENSOR: (CONF_SENSORS, YAML_SENSOR_SCHEMA),
    Platform.BINARY_SENSOR: (CONF_BINARY_SENSORS, YAML_BINARY_SENSOR_SCHEMA),
}
# endregion Constants


@dataclass
class LuxtronikEntityDescription(EntityDescription):
    """Class describing Luxtronik entities."""

    luxtronik_key: str = ""


async def async_setup_entry(hass: HomeAssistant, config_entry: LuxtronikConfigEntry) -> bool:
    """Set up from config entry."""
    LOGGER.info(
        "%s.async_setup_entry options: '%s' data:'%s'",
        DOMAIN,
        config_entry.options,
        config_entry.data,
    )
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    try:
        luxtronik, cooling_present = await hass.async_add_executor_job(
            connect_luxtronik, config_entry.data
        )
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to heatpump at {config_entry.data[CONF_HOST]}"
        ) from err

    await hass.async_add_executor_job(load_texts, hass.config.language)
    config_entry.runtime_data = build_runtime_data(
        hass, config_entry, luxtronik, cooling_present
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    def logout_luxtronik(event: Event) -> None:
        """Close connections to this heatpump."""
        luxtronik.disconnect()

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout_luxtronik)
    )
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the luxtronik component."""
    _async_sync_yaml_sensors(hass, config)

    async def write_parameter(service: ServiceCall) -> None:
        """Write a parameter to the Luxtronik heatpump."""
        config_entries: list[LuxtronikConfigEntry] = (
            hass.config_entries.async_loaded_entries(DOMAIN)
        )
        if not config_entries:
            raise ServiceValidationError("No Luxtronik heatpump is loaded")
        config_entry = config_entries[0]
        parameter = service.data.get(ATTR_PARAMETER)
        value = service.data.get(ATTR_VALUE)
        luxtronik = config_entry.runtime_data.device
        update_immediately_after_write = config_entry.data.get(
            CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, True
        )
        await hass.async_add_executor_job(
            partial(
                luxtronik.write,
                parameter,
                value,
                use_debounce=True,
                update_immediately_after_write=update_immediately_after_write,
            )
        )

    hass.services.async_register(
        DOMAIN, SERVICE_WRITE, write_parameter, schema=SERVICE_WRITE_SCHEMA
    )
    return True


@callback
def _async_sync_yaml_sensors(hass: HomeAssistant, config: ConfigType) -> None:
    """Store the sensors of the YAML platforms in the config entry, which creates them.

    Entities without a config entry can't belong to a device. The YAML stays the source of
    truth: it is synced at every start, and sensors removed from it are removed.
    """
    options = {}
    for domain, (key, schema) in YAML_PLATFORMS.items():
        sensors = []
        for platform, platform_config in config_per_platform(config, domain):
            if platform != DOMAIN:
                continue
            for option in (CONF_SCAN_INTERVAL, CONF_ENTITY_NAMESPACE):
                if option in platform_config:
                    LOGGER.warning("Option %s of the %s %s platform is ignored", option, DOMAIN, domain)
            for sensor_cfg in cv.ensure_list(platform_config.get(CONF_SENSORS)):
                try:
                    sensor_cfg = schema(sensor_cfg)
                except vol.Invalid as err:
                    LOGGER.error("Invalid %s %s %s: %s", DOMAIN, domain, sensor_cfg, err)
                    continue
                sensor_key = sensor_cfg.pop(CONF_ID)
                group = sensor_cfg.pop(CONF_GROUP, None)
                if "." not in sensor_key:
                    if group is None:
                        LOGGER.error("%s %s %s has no group", DOMAIN, domain, sensor_key)
                        continue
                    sensor_key = f"{group}.{sensor_key}"
                sensors.append({CONF_ID: sensor_key, **sensor_cfg})
        if sensors:
            options[key] = sensors

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return
    config_entry = entries[0]

    ent_reg = er.async_get(hass)
    for domain, (key, _) in YAML_PLATFORMS.items():
        kept = {get_yaml_unique_id(sensor[CONF_ID]) for sensor in options.get(key, [])}
        for sensor in config_entry.options.get(key, []):
            unique_id = get_yaml_unique_id(sensor[CONF_ID])
            if unique_id not in kept and (
                entity_id := ent_reg.async_get_entity_id(domain, DOMAIN, unique_id)
            ):
                ent_reg.async_remove(entity_id)

    new_options = {
        key: value for key, value in config_entry.options.items()
        if key not in (CONF_SENSORS, CONF_BINARY_SENSORS)
    } | options
    if new_options != config_entry.options:
        hass.config_entries.async_update_entry(config_entry, options=new_options)


def connect_luxtronik(data) -> tuple[LuxtronikDevice, bool]:
    """Connect to the heatpump and detect whether cooling is present."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    safe = data[CONF_SAFE]
    lock_timeout = data[CONF_LOCK_TIMEOUT]
    # update_immediately_after_write = data[CONF_UPDATE_IMMEDIATELY_AFTER_WRITE]
    # use_legacy_sensor_ids = data[CONF_USE_LEGACY_SENSOR_IDS] if CONF_USE_LEGACY_SENSOR_IDS in data else False
    # LOGGER.info("setup_internal use_legacy_sensor_ids: '%s'",
    #             use_legacy_sensor_ids)

    luxtronik = LuxtronikDevice(host, port, safe, lock_timeout)
    luxtronik.read()

    return luxtronik, luxtronik.detect_cooling_present()


def build_runtime_data(
    hass: HomeAssistant, config_entry: LuxtronikConfigEntry,
    luxtronik: LuxtronikDevice, cooling_present: bool
) -> LuxtronikRuntimeData:
    """Register the heatpump device and build the runtime data."""
    # Build Sensor names with local language:
    lang = hass.config.language
    text_domestic_water = get_sensor_text(lang, "domestic_water")
    text_heating = get_sensor_text(lang, "heating")
    text_heatpump = get_sensor_text(lang, "heatpump")
    text_cooling = get_sensor_text(lang, "cooling")

    # Create DeviceInfos. The heatpump must be registered before its child devices:
    device_info = build_device_info(luxtronik, text_heatpump, config_entry.data[CONF_HOST])
    heatpump = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, **device_info
    )
    device_info_domestic_water = ChildDeviceInfo(
        identifiers={(DOMAIN, f"{luxtronik.unique_id}_domestic_water")},
        name=text_domestic_water,
        parent_device_id=heatpump.id,
    )
    device_info_heating = ChildDeviceInfo(
        identifiers={(DOMAIN, f"{luxtronik.unique_id}_heating")},
        name=text_heating,
        parent_device_id=heatpump.id,
    )
    device_info_cooling = (
        ChildDeviceInfo(
            identifiers={(DOMAIN, f"{luxtronik.unique_id}_cooling")},
            name=text_cooling,
            parent_device_id=heatpump.id,
        )
        if cooling_present
        else None
    )
    return LuxtronikRuntimeData(
        device=luxtronik,
        device_info=device_info,
        device_info_domestic_water=device_info_domestic_water,
        device_info_heating=device_info_heating,
        device_info_cooling=device_info_cooling,
    )


async def async_reload_entry(hass: HomeAssistant, config_entry: LuxtronikConfigEntry) -> None:
    """Reload the HACS config entry."""
    LOGGER.info("async_reload_entry '%s'", config_entry)
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: LuxtronikConfigEntry) -> bool:
    """Unloading the Luxtronik platforms."""
    LOGGER.info("async_unload_entry '%s'", config_entry)

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        await hass.async_add_executor_job(config_entry.runtime_data.device.disconnect)
    return unload_ok


def build_device_info(
    luxtronik: LuxtronikDevice, name: str, ip_host: str
) -> DeviceInfo:
    """Build luxtronik device info."""
    device_info = DeviceInfo(
        configuration_url=f"http://{ip_host}/",
        connections=None,

        # default_manufacturer="Alpha Innotec",
        # default_model="",
        # default_name=name,

        entry_type=None,
        hw_version=None,
        identifiers={
            (DOMAIN, f"{luxtronik.unique_id}_heatpump")
        },
        manufacturer=luxtronik.manufacturer,
        model=luxtronik.model,
        name=f"{name} {luxtronik.serial_number}",

        sw_version=luxtronik.get_value("calculations.ID_WEB_SoftStand"),

    )
    LOGGER.debug("build_device_info '%s'", device_info)
    LOGGER.debug("set_device_info '%s'", set(device_info))
    return device_info


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new = {**config_entry.data}
        luxtronik = LuxtronikDevice.connect(new[CONF_HOST], new[CONF_PORT])

        _delete_legacy_devices(hass, config_entry, luxtronik.unique_id)
        hass.config_entries.async_update_entry(
            config_entry,
            data=new,
            unique_id=luxtronik.unique_id,
            title=f"{luxtronik.manufacturer} {luxtronik.model} {luxtronik.serial_number}",
            version=2,
        )

    if config_entry.version == 2:
        await _async_migrate_unique_ids(hass, config_entry)
        hass.config_entries.async_update_entry(config_entry, version=3)

    LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


def _identifiers_exists(
    identifiers_list: list[set[tuple[str, str]]], identifiers: set[tuple[str, str]]
) -> bool:
    for ident in identifiers_list:
        if ident == identifiers:
            return True
    return False


def _delete_legacy_devices(hass: HomeAssistant, config_entry: ConfigEntry, unique_id: str):
    dr_instance = dr.async_get(hass)
    devices: list[dr.DeviceEntry] = dr.async_entries_for_config_entry(
        dr_instance, config_entry.entry_id
    )
    identifiers_list = list()
    identifiers_list.append({(DOMAIN, f"{unique_id}_heatpump")})
    identifiers_list.append({(DOMAIN, f"{unique_id}_domestic_water")})
    identifiers_list.append({(DOMAIN, f"{unique_id}_heating")})
    identifiers_list.append({(DOMAIN, f"{unique_id}_cooling")})
    for device in devices:
        if not _identifiers_exists(identifiers_list, device.identifiers):
            dr_instance.async_remove_device(device.id)


async def _async_migrate_unique_ids(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate legacy unique ids to "<serial>_<key>".

    Legacy unique ids were derived from the entity_id ("sensor.luxtronik2_<key>",
    "update.luxtronik2_firmware"), or were the bare key for climate entities.
    The entity_id is kept, so existing automations and dashboards keep working.
    """
    ent_reg = er.async_get(hass)

    def _migrate(entity_entry: er.RegistryEntry) -> dict | None:
        old_unique_id = entity_entry.unique_id
        if "." in old_unique_id:
            key = old_unique_id.partition(f".{DOMAIN}_")[2]
            if not key:
                return None
        elif entity_entry.domain == "climate":
            key = old_unique_id
        else:
            return None
        new_unique_id = f"{config_entry.unique_id}_{key.replace(' ', '_')}"
        if ent_reg.async_get_entity_id(entity_entry.domain, DOMAIN, new_unique_id):
            LOGGER.warning(
                "Cannot migrate %s to unique_id '%s', it already exists",
                entity_entry.entity_id, new_unique_id)
            return None
        LOGGER.debug("Migrating %s unique_id '%s' -> '%s'",
                     entity_entry.entity_id, old_unique_id, new_unique_id)
        return {"new_unique_id": new_unique_id}

    await er.async_migrate_entries(hass, config_entry.entry_id, _migrate)
