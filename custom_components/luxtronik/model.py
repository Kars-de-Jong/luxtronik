"""Model for LuxtronikStatusExtraAttributes."""
from dataclasses import dataclass
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import ChildDeviceInfo
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .luxtronik_device import LuxtronikDevice


class LuxtronikStatusExtraAttributes(TypedDict):
    """TypedDict for sensors extra attributes."""
    status_text: str


@dataclass
class LuxtronikRuntimeData:
    """Runtime data of a Luxtronik config entry."""

    device: LuxtronikDevice
    device_info: DeviceInfo
    device_info_domestic_water: ChildDeviceInfo
    device_info_heating: ChildDeviceInfo
    device_info_cooling: ChildDeviceInfo | None


type LuxtronikConfigEntry = ConfigEntry[LuxtronikRuntimeData]


def get_runtime_data(hass: HomeAssistant) -> LuxtronikRuntimeData | None:
    """Return the runtime data of the first set up config entry, for YAML platforms."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if hasattr(entry, "runtime_data"):
            return entry.runtime_data
    return None
