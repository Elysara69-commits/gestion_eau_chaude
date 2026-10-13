"""Commandes WebSocket du panneau : abonnement à l'état, marche forcée, arrêt manuel, pilotage automatique."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


def _controller(hass: HomeAssistant):
    return hass.data.get(DOMAIN, {}).get("controller")


@websocket_api.websocket_command({vol.Required("type"): "gestion_eau_chaude/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Envoie l'instantané courant puis chaque mise à jour du contrôleur."""
    controller = _controller(hass)
    if controller is None:
        connection.send_error(msg["id"], "not_loaded", "Intégration non chargée")
        return

    @callback
    def _forward(snapshot: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], snapshot))

    connection.subscriptions[msg["id"]] = controller.subscribe(_forward)
    connection.send_result(msg["id"])
    _forward(controller.last)


@websocket_api.websocket_command(
    {vol.Required("type"): "gestion_eau_chaude/force", vol.Required("on"): bool}
)
@websocket_api.async_response
async def ws_force(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Active la marche forcée (on=True) ou coupe le chauffe-eau (on=False)."""
    controller = _controller(hass)
    if controller is None:
        connection.send_error(msg["id"], "not_loaded", "Intégration non chargée")
        return
    await controller.async_force(msg["on"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "gestion_eau_chaude/stop"})
@websocket_api.async_response
async def ws_stop(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Arrêt manuel : coupe le chauffe-eau et suspend le démarrage automatique."""
    controller = _controller(hass)
    if controller is None:
        connection.send_error(msg["id"], "not_loaded", "Intégration non chargée")
        return
    await controller.async_stop_and_suspend()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): "gestion_eau_chaude/auto", vol.Required("on"): bool}
)
@websocket_api.async_response
async def ws_auto(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Réactive (on=True) ou suspend (on=False) le pilotage automatique."""
    controller = _controller(hass)
    if controller is None:
        connection.send_error(msg["id"], "not_loaded", "Intégration non chargée")
        return
    await controller.async_set_auto(msg["on"])
    connection.send_result(msg["id"])
