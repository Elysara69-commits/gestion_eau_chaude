"""Entité de base : se met à jour à chaque instantané du contrôleur."""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import Controller


class EauChaudeEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: Controller, key: str) -> None:
        self._ctrl = controller
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name="Gestion eau chaude",
            manufacturer="Maison",
            model="Chauffe-eau électrique piloté",
        )

    @property
    def snap(self) -> dict[str, Any]:
        return self._ctrl.last

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._ctrl.subscribe(self._handle_snapshot))

    @callback
    def _handle_snapshot(self, _snapshot: dict[str, Any]) -> None:
        self.async_write_ha_state()
