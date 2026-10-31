"""Data update coordinator for the Luxtronik heatpump."""
from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, SCAN_INTERVAL_DEVICE
from .luxtronik_device import LuxtronikDevice

if TYPE_CHECKING:
    from .model import LuxtronikConfigEntry

# The heatpump needs a moment to apply a write, so the refresh after a write is
# delayed. Refreshes requested within this time are combined.
REFRESH_DELAY_AFTER_WRITE = 3


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
            request_refresh_debouncer=Debouncer(
                hass, LOGGER, cooldown=REFRESH_DELAY_AFTER_WRITE, immediate=False
            ),
        )
        self.device = device

    async def _async_update_data(self) -> None:
        """Read the heatpump in the executor."""
        try:
            await self.hass.async_add_executor_job(self.device.read)
        except OSError as err:
            raise UpdateFailed(f"Unable to read the heatpump: {err}") from err

    async def async_write(self, parameter: str, value: Any) -> None:
        """Write a parameter, show the new value at once and read the heatpump later."""
        written = await self.hass.async_add_executor_job(
            partial(self.device.write, parameter, value, use_debounce=False)
        )
        if written:
            self.async_update_listeners()
        await self.async_request_refresh()
