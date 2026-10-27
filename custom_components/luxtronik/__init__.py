"""Support for Luxtronik heatpump controllers."""
# region Imports

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType
from luxtronik import LOGGER as LuxLogger

from .const import (
    ATTR_PARAMETER,
    ATTR_VALUE,
    CONF_LOCK_TIMEOUT,
    CONF_SAFE,
    CONF_UPDATE_IMMEDIATELY_AFTER_WRITE,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_WRITE,
    SERVICE_WRITE_SCHEMA,
)
from .const import CONFIG_SCHEMA  # noqa: F401
from .helpers.helper import get_sensor_text
from .helpers.lux_helper import get_manufacturer_firmware_url_by_model
from .luxtronik_device import LuxtronikDevice
from .model import LuxtronikConfigEntry, LuxtronikRuntimeData

# endregion Imports

# region Constants
LuxLogger.setLevel(level="WARNING")
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
        config_entry.runtime_data = await hass.async_add_executor_job(
            build_runtime_data, hass, config_entry.data
        )
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to heatpump at {config_entry.data[CONF_HOST]}"
        ) from err

    luxtronik = config_entry.runtime_data.device

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    def logout_luxtronik(event: Event) -> None:
        """Close connections to this heatpump."""
        luxtronik.disconnect()

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout_luxtronik)
    )
    await hass.async_add_executor_job(setup_hass_services, hass, config_entry)
    return True


def setup_hass_services(hass: HomeAssistant, config_entry: LuxtronikConfigEntry):
    """Home Assistant services."""

    def write_parameter(service):
        """Write a parameter to the Luxtronik heatpump."""
        parameter = service.data.get(ATTR_PARAMETER)
        value = service.data.get(ATTR_VALUE)
        luxtronik = config_entry.runtime_data.device
        update_immediately_after_write = config_entry.data.get(
            CONF_UPDATE_IMMEDIATELY_AFTER_WRITE, True
        )
        luxtronik.write(
            parameter,
            value,
            use_debounce=True,
            update_immediately_after_write=update_immediately_after_write,
        )

    hass.services.register(
        DOMAIN, SERVICE_WRITE, write_parameter, schema=SERVICE_WRITE_SCHEMA
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the luxtronik component."""
    return True


def build_runtime_data(hass: HomeAssistant, data) -> LuxtronikRuntimeData:
    """Connect to the heatpump and build the runtime data."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    safe = data[CONF_SAFE]
    lock_timeout = data[CONF_LOCK_TIMEOUT]
    # update_immediately_after_write = data[CONF_UPDATE_IMMEDIATELY_AFTER_WRITE]
    # use_legacy_sensor_ids = data[CONF_USE_LEGACY_SENSOR_IDS] if CONF_USE_LEGACY_SENSOR_IDS in data else False
    # LOGGER.info("setup_internal use_legacy_sensor_ids: '%s'",
    #             use_legacy_sensor_ids)

    # Build Sensor names with local language:
    lang = hass.config.language
    text_domestic_water = get_sensor_text(lang, "domestic_water")
    text_heating = get_sensor_text(lang, "heating")
    text_heatpump = get_sensor_text(lang, "heatpump")
    text_cooling = get_sensor_text(lang, "cooling")

    luxtronik = LuxtronikDevice(host, port, safe, lock_timeout)
    luxtronik.read()

    # Create DeviceInfos:
    device_info = build_device_info(luxtronik, text_heatpump, data[CONF_HOST])
    device_info_domestic_water = DeviceInfo(
        identifiers={(DOMAIN, f"{luxtronik.unique_id}_domestic_water")},
        configuration_url="https://www.heatpump24.com/",
        name=text_domestic_water,
        manufacturer=luxtronik.manufacturer,
        model=luxtronik.model,
        entry_type=None,
        hw_version=None,
        sw_version=None,
        connections=None,
        via_device=None,
    )
    device_info_heating = DeviceInfo(
        identifiers={(DOMAIN, f"{luxtronik.unique_id}_heating")},
        configuration_url=get_manufacturer_firmware_url_by_model(luxtronik.model),
        name=text_heating,
        manufacturer=luxtronik.manufacturer,
        model=luxtronik.model,
        entry_type=None,
        hw_version=None,
        sw_version=None,
        connections=None,
        via_device=None,
    )
    device_info_cooling = (
        DeviceInfo(
            identifiers={(DOMAIN, f"{luxtronik.unique_id}_cooling")},
            configuration_url=get_manufacturer_firmware_url_by_model(luxtronik.model),
            name=text_cooling,
            manufacturer=luxtronik.manufacturer,
            model=luxtronik.model,
            entry_type=None,
            hw_version=None,
            sw_version=None,
            connections=None,
            via_device=None,
        )
        if luxtronik.detect_cooling_present()
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
    hass.services.async_remove(DOMAIN, SERVICE_WRITE)

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

        via_device=None,
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
