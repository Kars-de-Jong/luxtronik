"""Base entity for the Luxtronik heatpump."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LuxtronikCoordinator


class LuxtronikEntity(CoordinatorEntity[LuxtronikCoordinator]):
    """An entity that follows the data read by the coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._luxtronik = coordinator.device

    @callback
    def _handle_coordinator_update(self) -> None:
        """Compute the attributes from the new data and write the state."""
        self._update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _update_attrs(self) -> None:
        """Compute the values that depend on the data read; override in subclasses."""
