"""Luxtronik Update platform."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from functools import cached_property
from typing import Final

from aiohttp import ClientError, ClientTimeout
from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.components.update.const import UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LuxtronikEntityDescription
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .model import LuxtronikConfigEntry
from .const import DOWNLOAD_PORTAL_URL, LOGGER
from .helpers.lux_helper import get_manufacturer_firmware_url_by_model

# The download portal is queried on every poll; firmware releases are rare.
SCAN_INTERVAL: Final = timedelta(hours=1)
PORTAL_TIMEOUT: Final = ClientTimeout(total=30)
# The entity can't install firmware, so its updates are not limited.
PARALLEL_UPDATES = 0


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
    description = LuxtronikUpdateEntityDescription(
        luxtronik_key="calculations.ID_WEB_SoftStand",
        key="firmware",
        entity_category=EntityCategory.CONFIG,
    )
    update_entity = LuxtronikUpdateEntity(
        coordinator=config_entry.runtime_data.coordinator, description=description,
        device_info=config_entry.runtime_data.device_info
    )
    entities = [update_entity]

    async_add_entities(entities)


class LuxtronikUpdateEntity(LuxtronikEntity, UpdateEntity):
    """The installed heatpump firmware, and the latest from the download portal.

    The installed version follows the coordinator. The download portal is polled.
    """

    _attr_title = "Luxtronik Firmware Version"
    _attr_supported_features: UpdateEntityFeature = UpdateEntityFeature.RELEASE_NOTES

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        description: LuxtronikUpdateEntityDescription,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the Luxtronik."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self.luxtronik_key = description.luxtronik_key
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{self._luxtronik.unique_id}_{description.key}"
        self._firmware_version_available: str | None = None
        self._portal_failed = False

    @cached_property
    def should_poll(self) -> bool:
        """Poll the download portal; the coordinator updates the installed version."""
        return True

    async def async_added_to_hass(self) -> None:
        """Query the download portal without delaying the setup."""
        await super().async_added_to_hass()
        self.async_schedule_update_ha_state(True)

    @property
    def installed_version(self) -> str:
        """Return the current app version."""
        return self._luxtronik.get_value(self.entity_description.luxtronik_key)

    @property
    def latest_version(self) -> str | None:
        """Return the latest version from the download portal, if known."""
        if self._firmware_version_available is None or self.installed_version is None:
            return None
        return self._firmware_version_available[:len(self.installed_version)]

    @property
    def release_url(self) -> str:
        """Return the manufacturer firmware download page."""
        return get_manufacturer_firmware_url_by_model(self._luxtronik.model)

    def release_notes(self) -> str | None:
        release_url = self.release_url
        download_id = self._get_firmware_download_id(self.installed_version)
        download_url = f"{DOWNLOAD_PORTAL_URL}{download_id}"
        return f'<a href="{release_url}" target="_blank" rel="noreferrer noopener">Firmware Download Portal</a>&emsp;<a href="{download_url}" target="_blank" rel="noreferrer noopener">Direct Download</a><br><br>alpha innotec doesn\'t provide a changelog.<br>Please contact support for more information.'

    def _get_firmware_download_id(self, installed_version: str | None) -> int | None:
        """Return the heatpump firmware id for the download portal."""
        if not isinstance(installed_version, str):
            return None
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

    async def async_update(self) -> None:
        """Query the download portal for the latest firmware version."""
        download_id = self._get_firmware_download_id(self.installed_version)
        if download_id is None:
            self._firmware_version_available = None
            return
        try:
            version = await self._async_fetch_latest_version(download_id)
        except (ClientError, TimeoutError, KeyError, IndexError) as err:
            if not self._portal_failed:
                LOGGER.warning("Could not request download portal firmware version: %s", err)
                self._portal_failed = True
            return
        if self._portal_failed:
            LOGGER.info("The firmware download portal is available again")
            self._portal_failed = False
        self._firmware_version_available = version

    async def _async_fetch_latest_version(self, download_id: int) -> str:
        """Return the latest firmware version from the file name of the download."""
        session = async_get_clientsession(self.hass)
        # Only the headers are needed, so the firmware itself is not downloaded.
        async with session.get(
            f"{DOWNLOAD_PORTAL_URL}{download_id}", timeout=PORTAL_TIMEOUT
        ) as response:
            content_disposition = response.headers["content-disposition"]
        # Filename e.g.: wp2reg-V2.88.1-9086
        # Extract 'V2.88.1' from 'wp2reg-V2.88.1-9086'
        filename = re.findall("filename=(.+)", content_disposition)[0]
        return filename.split("-", 1)[1]
