"""Luxtronik Update platform."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

import requests
from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.components.update.const import UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LuxtronikDevice, LuxtronikEntityDescription
from .model import LuxtronikConfigEntry
from .const import DOWNLOAD_PORTAL_URL, LOGGER
from .helpers.lux_helper import get_manufacturer_firmware_url_by_model

# The download portal is queried on every poll; firmware releases are rare.
SCAN_INTERVAL: Final = timedelta(hours=1)


@dataclass
class LuxtronikUpdateEntityDescription(
    LuxtronikEntityDescription, UpdateEntityDescription
):
    """Class describing Luxtronik update entities."""


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LuxtronikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Luxtronik update platform."""

    LOGGER.debug("Setting up Luxtronik update entity")
    luxtronik_device = config_entry.runtime_data.device
    luxtronik_device.read()

    description = LuxtronikUpdateEntityDescription(
        luxtronik_key="calculations.ID_WEB_SoftStand",
        key="firmware",
        entity_category=EntityCategory.CONFIG,
    )
    update_entity = LuxtronikUpdateEntity(
        entry=config_entry, luxtronik_device=luxtronik_device, description=description, device_info=config_entry.runtime_data.device_info
    )
    entities = [update_entity]

    async_add_entities(entities)


class LuxtronikUpdateEntity(UpdateEntity):
    """Representation of Luxtronik."""

    _attr_title = "Luxtronik Firmware Version"
    _attr_has_entity_name = True
    _attr_supported_features: UpdateEntityFeature = UpdateEntityFeature.RELEASE_NOTES
    __firmware_version_available = None

    def __init__(
        self,
        entry: ConfigEntry,
        luxtronik_device: LuxtronikDevice,
        description: LuxtronikUpdateEntityDescription,
        device_info
    ) -> None:
        """Initialize the Luxtronik."""
        super().__init__()
        self.entity_description = description
        self.luxtronik_device = luxtronik_device
        # self.coordinator = coordinator
        self._attr_device_info = device_info
        # self._attr_unique_id = f"tuya.{device.id}"
        self.luxtronik_key = description.luxtronik_key

        self._attr_translation_key = description.key
        luxtronik_device.read()
        # self._attr_state = luxtronik_device.get_value(description.luxtronik_key)
        self._attr_unique_id = f"{luxtronik_device.unique_id}_{description.key}"
        self._request_available_firmware_version()

    @property
    def installed_version(self) -> str:
        """Return the current app version."""
        # return self._attr_state
        return self.luxtronik_device.get_value(self.entity_description.luxtronik_key)

    @property
    def latest_version(self) -> str:
        """Return if there is an update."""
        if self.__firmware_version_available is None:
            self._request_available_firmware_version()
            return None
        return self.__firmware_version_available[:len(self.installed_version)]

    @property
    def release_url(self) -> str:
        """Return the manufacturer firmware download page."""
        return get_manufacturer_firmware_url_by_model(self.luxtronik_device.model)

    def release_notes(self) -> str | None:
        release_url = self.release_url
        download_id = self._get_firmware_download_id(self.installed_version)
        download_url = f"{DOWNLOAD_PORTAL_URL}{download_id}"
        return f'<a href="{release_url}" target="_blank" rel="noreferrer noopener">Firmware Download Portal</a>&emsp;<a href="{download_url}" target="_blank" rel="noreferrer noopener">Direct Download</a><br><br>alpha innotec doesn\'t provide a changelog.<br>Please contact support for more information.'

    def _get_firmware_download_id(self, installed_version: str) -> int | None:
        """Return the heatpump firmware id for the download portal."""
        if installed_version.startswith("V1."):
            return 0
        elif installed_version.startswith("V2."):
            return 1
        elif installed_version.startswith("V3."):
            return 2
        elif installed_version.startswith("V4."):
            return 3
        elif installed_version.startswith("F1."):
            return 4
        elif installed_version.startswith("WWB1."):
            return 5
        elif installed_version.startswith("smo"):
            return 6
        return None

    def update(self) -> None:
        """Update sensor values."""
        self._request_available_firmware_version()

    def _request_available_firmware_version(self) -> None:
        def do_request_available_firmware_version(self, download_id: int):
            if download_id is None:
                self.__firmware_version_available = STATE_UNAVAILABLE
                return
            try:
                response = requests.get(
                    f"{DOWNLOAD_PORTAL_URL}{download_id}", timeout=30
                )
                header_content_disposition = response.headers["content-disposition"]
                filename = re.findall("filename=(.+)", header_content_disposition)[0]
                # Filename e.g.: wp2reg-V2.88.1-9086
                # Extract 'V2.88.1' from 'wp2reg-V2.88.1-9086'
                self.__firmware_version_available = filename.split("-", 1)[1]
            except Exception:  # pylint: disable=broad-except
                LOGGER.warning(
                    "Could not request download portal firmware version.",
                    exc_info=True,
                )
                self.__firmware_version_available = STATE_UNAVAILABLE

        download_id = self._get_firmware_download_id(self.installed_version)
        threading.Thread(
            target=do_request_available_firmware_version, args=(self, download_id)
        ).start()
