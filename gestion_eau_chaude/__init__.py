"""Intégration Gestion eau chaude : pilotage solaire / heures creuses + panneau dédié."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import ws_force, ws_subscribe
from .const import DOMAIN, PANEL_ELEMENT, PANEL_URL, STATIC_URL, VERSION
from .controller import Controller

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_force)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})

    controller = Controller(hass, entry)
    await controller.async_start()
    domain_data["controller"] = controller

    # Fichiers du panneau (enregistrés une seule fois : une route ne peut pas être retirée)
    if not domain_data.get("static"):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL,
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                )
            ]
        )
        domain_data["static"] = True

    # Entrée dans la barre latérale
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_ELEMENT,
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/gestion-eau-chaude-panel.js?v={VERSION}",
        sidebar_title="Eau chaude",
        sidebar_icon="mdi:water-boiler",
        require_admin=False,
        config={},
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller: Controller | None = hass.data[DOMAIN].pop("controller", None)
        if controller is not None:
            await controller.async_stop()
        frontend.async_remove_panel(hass, PANEL_URL)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
