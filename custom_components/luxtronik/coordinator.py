"""Data update coordinator for the Luxtronik heatpump."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, SCAN_INTERVAL_DEVICE
from .luxtronik_device import LuxtronikDevice

if TYPE_CHECKING:
    from .model import LuxtronikConfigEntry


class LuxtronikCoordinator(DataUpdateCoordinator[None]):
    """Read the heatpump for all entities of a config entry.

    The library client keeps the values it read, so the coordinator holds no data of
    its own. The entities read their values from the device.
    """

    config_entry: LuxtronikConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: LuxtronikConfigEntry, device: LuxtronikDevice
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL_DEVICE,
        )
        self.device = device

    async def _async_update_data(self) -> None:
        """Read the heatpump in the executor."""
        try:
            await self.hass.async_add_executor_job(self.device.read)
        except OSError as err:
            raise UpdateFailed(f"Unable to read the heatpump: {err}") from err
