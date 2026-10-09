"""Capteurs : état, énergie du jour, surplus solaire."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STATUS_LABELS
from .entity import EauChaudeEntity


@dataclass(frozen=True, kw_only=True)
class EauChaudeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[EauChaudeSensorDescription, ...] = (
    EauChaudeSensorDescription(
        key="state",
        name="État",
        icon="mdi:water-boiler",
        value_fn=lambda s: STATUS_LABELS.get(s.get("status", ""), None),
    ),
    EauChaudeSensorDescription(
        key="energy_today",
        name="Énergie du jour",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda s: round(s["energy"]["total"], 2),
    ),
    EauChaudeSensorDescription(
        key="energy_solar_today",
        name="Énergie solaire du jour",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda s: round(s["energy"]["solar"], 2),
    ),
    EauChaudeSensorDescription(
        key="energy_battery_today",
        name="Énergie batterie du jour",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda s: round(s["energy"]["battery"], 2),
    ),
    EauChaudeSensorDescription(
        key="energy_grid_today",
        name="Énergie réseau du jour",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda s: round(s["energy"]["grid"], 2),
    ),
    EauChaudeSensorDescription(
        key="energy_night_today",
        name="Énergie heures creuses du jour",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda s: round(s["energy"]["by_mode"]["night"], 2),
    ),
    EauChaudeSensorDescription(
        key="surplus",
        name="Surplus solaire",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: s["values"]["surplus_w"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = hass.data[DOMAIN]["controller"]
    async_add_entities(EauChaudeSensor(controller, desc) for desc in SENSORS)


class EauChaudeSensor(EauChaudeEntity, SensorEntity):
    entity_description: EauChaudeSensorDescription

    def __init__(self, controller, description: EauChaudeSensorDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if not self.snap:
            return None
        return self.entity_description.value_fn(self.snap)

    @property
    def last_reset(self) -> datetime | None:
        if self.entity_description.device_class == SensorDeviceClass.ENERGY:
            return dt_util.start_of_local_day()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "state" or not self.snap:
            return None
        return {
            "mode": self.snap.get("mode"),
            "cycle_termine": self.snap.get("cycle_done"),
            "verrou_restant_s": self.snap["lock"]["remaining_s"],
            "verrou_raison": self.snap["lock"]["reason"],
            "heures_creuses": self.snap.get("night_plan"),
        }
