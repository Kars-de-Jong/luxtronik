"""Data update coordinator for the Luxtronik heatpump."""
from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, SCAN_INTERVAL_DEVICE
from .luxtronik_device import LuxtronikDevice

if TYPE_CHECKING:
    from .model import LuxtronikConfigEntry

# The heatpump needs a moment to apply a write, so the refresh after a write is
# delayed. Refreshes requested within this time are combined.
REFRESH_DELAY_AFTER_WRITE = 3
# A debounced write waits this long for a newer value of the same parameter.
WRITE_DEBOUNCE_DELAY = 3


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
        # Debounced writes that are waiting, by parameter: value, refresh, cancel.
        self._pending_writes: dict[str, tuple[Any, bool, CALLBACK_TYPE]] = {}

    async def _async_update_data(self) -> None:
        """Read the heatpump in the executor."""
        try:
            await self.hass.async_add_executor_job(self.device.read)
        except OSError as err:
            raise UpdateFailed(f"Unable to read the heatpump: {err}") from err

    async def async_write(self, parameter: str, value: Any, refresh: bool = True) -> None:
        """Write a parameter, show the new value at once and read the heatpump later.

        Raises HomeAssistantError when the write fails.
        """
        try:
            written = await self.hass.async_add_executor_job(self.device.write, parameter, value)
        except OSError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"parameter": parameter, "error": str(err)},
            ) from err
        if not written:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"parameter": parameter, "value": str(value)},
            )
        self.async_update_listeners()
        if refresh:
            await self.async_request_refresh()

    @callback
    def async_write_debounced(self, parameter: str, value: Any, refresh: bool = True) -> None:
        """Write a parameter after a delay, unless a newer value for it comes first.

        Writes to other parameters don't affect each other.
        """
        if pending := self._pending_writes.pop(parameter, None):
            pending[2]()
        cancel = async_call_later(
            self.hass, WRITE_DEBOUNCE_DELAY, partial(self._async_write_pending, parameter)
        )
        self._pending_writes[parameter] = (value, refresh, cancel)

    async def _async_write_pending(self, parameter: str, _now: Any = None) -> None:
        """Write the pending value of a parameter."""
        value, refresh, cancel = self._pending_writes.pop(parameter)
        cancel()
        try:
            await self.async_write(parameter, value, refresh)
        except HomeAssistantError as err:
            # The action or entity call that scheduled the write has already returned.
            LOGGER.error("%s", err)

    async def async_shutdown(self) -> None:
        """Write the pending values before the coordinator stops."""
        for parameter in list(self._pending_writes):
            value, _, cancel = self._pending_writes[parameter]
            self._pending_writes[parameter] = (value, False, cancel)
            await self._async_write_pending(parameter)
        await super().async_shutdown()
