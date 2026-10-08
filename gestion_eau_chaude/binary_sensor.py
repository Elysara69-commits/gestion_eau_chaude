"""Capteurs binaires : chauffe solaire du jour, heures creuses prévues, cycle terminé."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EauChaudeEntity


@dataclass(frozen=True, kw_only=True)
class EauChaudeBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSORS: tuple[EauChaudeBinaryDescription, ...] = (
    EauChaudeBinaryDescription(
        key="ran_solar_today",
        name="A chauffé au solaire aujourd'hui",
        icon="mdi:white-balance-sunny",
        value_fn=lambda s: bool(s["ran_solar"]),
    ),
    EauChaudeBinaryDescription(
        key="night_planned",
        name="Chauffe heures creuses prévue",
        icon="mdi:weather-night",
        value_fn=lambda s: s["night_plan"] in ("planned", "running"),
    ),
    EauChaudeBinaryDescription(
        key="cycle_done",
        name="Cycle de chauffe terminé",
        icon="mdi:check-circle-outline",
        value_fn=lambda s: bool(s["cycle_done"]),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = hass.data[DOMAIN]["controller"]
    async_add_entities(EauChaudeBinary(controller, desc) for desc in BINARY_SENSORS)


class EauChaudeBinary(EauChaudeEntity, BinarySensorEntity):
    entity_description: EauChaudeBinaryDescription

    def __init__(self, controller, description: EauChaudeBinaryDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if not self.snap:
            return None
        return self.entity_description.value_fn(self.snap)
