"""Interrupteur de marche forcée."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EauChaudeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ForceSwitch(hass.data[DOMAIN]["controller"])])


class ForceSwitch(EauChaudeEntity, SwitchEntity):
    _attr_name = "Marche forcée"
    _attr_icon = "mdi:water-boiler-alert"

    def __init__(self, controller) -> None:
        super().__init__(controller, "force")

    @property
    def available(self) -> bool:
        return bool(self.snap) and self.snap.get("switch") is not None

    @property
    def is_on(self) -> bool:
        return bool(self.snap.get("forced"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._ctrl.async_force(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._ctrl.async_force(False)
