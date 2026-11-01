"""Base entity for the Luxtronik heatpump."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_EXTRA_STATE_ATTRIBUTE_LAST_THERMAL_DESINFECTION, ATTR_STATUS_TEXT
from .coordinator import LuxtronikCoordinator

# Attributes that change often, or only describe the state, are not recorded.
UNRECORDED_ATTRIBUTES = frozenset({
    ATTR_STATUS_TEXT,
    ATTR_EXTRA_STATE_ATTRIBUTE_LAST_THERMAL_DESINFECTION,
    'WP Seit (ID_WEB_Time_WPein_akt)',
    'ZWE1 seit (ID_WEB_Time_ZWE1_akt)',
    'ZWE2 seit (ID_WEB_Time_ZWE2_akt)',
    'Netzeinschaltv. (ID_WEB_Timer_EinschVerz)',
    'Schaltspielsperre SSP-Aus-Zeit (ID_WEB_Time_SSPAUS_akt)',
    'Schaltspielsperre SSP-Ein-Zeit (ID_WEB_Time_SSPEIN_akt)',
    'VD-Stand (ID_WEB_Time_VDStd_akt)',
    'Heizungsregler Mehr-Zeit HRM-Zeit (ID_WEB_Time_HRM_akt)',
    'Heizungsregler Weniger-Zeit HRW-Stand (ID_WEB_Time_HRW_akt)',
    'ID_WEB_Time_LGS_akt',
    'Sperre WW? ID_WEB_Time_SBW_akt',
    'Abtauen in ID_WEB_Time_AbtIn',
    'ID_WEB_Time_Heissgas',
    'switch_gap',
    'status raw',
    'EVU first start time',
    'EVU first end time',
    'EVU second start time',
    'EVU second end time',
    'EVU minutes until next event',
    'timestamp',
    'code',
    'cause',
    'remedy',
    'max_allowed',
})


class LuxtronikEntity(CoordinatorEntity[LuxtronikCoordinator]):
    """An entity that follows the data read by the coordinator."""

    _attr_has_entity_name = True
    _unrecorded_attributes = UNRECORDED_ATTRIBUTES

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
