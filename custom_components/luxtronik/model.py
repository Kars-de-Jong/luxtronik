"""Model for LuxtronikStatusExtraAttributes."""
from dataclasses import dataclass
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import ChildDeviceInfo
from homeassistant.helpers.entity import DeviceInfo

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
