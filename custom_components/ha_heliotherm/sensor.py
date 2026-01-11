from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.input_number import *
import logging
from typing import Optional, Dict, Any

import homeassistant.util.dt as dt_util

from .const import (
    ATTR_MANUFACTURER,
    DOMAIN,
    SENSOR_TYPES,
    HaHeliothermSensorEntityDescription,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    hub_name = entry.data[CONF_NAME]
    hub = hass.data[DOMAIN][hub_name]["hub"]

    device_info = {
        "identifiers": {(DOMAIN, hub_name)},
        "name": hub_name,
        "manufacturer": ATTR_MANUFACTURER,
    }

    entities = []
    for sensor_description in SENSOR_TYPES.values():
        sensor = HaHeliothermModbusSensor(
            hub_name,
            hub,
            device_info,
            sensor_description,
        )
        entities.append(sensor)

    async_add_entities(entities)
    return True


class HaHeliothermModbusSensor(SensorEntity):
    """Representation of an Heliotherm Modbus sensor."""

    def __init__(
        self,
        platform_name,
        hub,
        device_info,
        description: HaHeliothermSensorEntityDescription,
    ):
        """Initialize the sensor."""
        self._platform_name = platform_name
        self._attr_device_info = device_info
        self._hub = hub
        self.entity_description: HaHeliothermSensorEntityDescription = description
        
        # Store last valid COP to handle spikes/defrost
        self._last_valid_cop = None

    async def async_added_to_hass(self):
        """Register callbacks."""
        self._hub.async_add_haheliotherm_modbus_sensor(self._modbus_data_updated)

    async def async_will_remove_from_hass(self) -> None:
        self._hub.async_remove_haheliotherm_modbus_sensor(self._modbus_data_updated)

    @callback
    def _modbus_data_updated(self):
        self.async_write_ha_state()

    @property
    def name(self):
        """Return the name."""
        return f"{self._platform_name} {self.entity_description.name}"

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self._platform_name}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        current_value = (
            self._hub.data[self.entity_description.key]
            if self.entity_description.key in self._hub.data
            else None
        )

        # --- COP Filtering Logic ---
        if self.entity_description.key == "cop":
            valve_state = self._hub.data.get("vierwegeventil_luft")
            is_defrost = str(valve_state) == "Abtaubetrieb" or str(valve_state) == "1"

            # 1. Defrost check: freeze last valid value
            if is_defrost:
                if self._last_valid_cop is not None:
                    return self._last_valid_cop
                return current_value

            # 2. Spike check: ignore unrealistic values (> 12)
            try:
                if current_value is not None and float(current_value) > 12.0:
                    if self._last_valid_cop is not None:
                        return self._last_valid_cop
                    return 0.0
            except (ValueError, TypeError):
                pass

            # 3. Store valid value
            if current_value is not None:
                self._last_valid_cop = current_value
        # ---------------------------

        return current_value
