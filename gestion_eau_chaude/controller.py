"""Contrôleur du chauffe-eau : surplus solaire le jour, heures creuses l'hiver.

Port du script gestion_eau_chaude.py : une seule boucle de contrôle évalue
toutes les règles toutes les TICK_S secondes. Les « timers » sont de simples
horodatages (Condition), sans tâche à annuler.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_HOLD_S,
    BATTERY_LOCK_S,
    CONF_BATTERY_SOC,
    CONF_DISCORD,
    CONF_GRID_IMPORT,
    CONF_HC_END_H,
    CONF_HC_START_H,
    CONF_HEATER_OFF_W,
    CONF_HEATER_POWER,
    CONF_HEATER_SWITCH,
    CONF_HOUSE_POWER,
    CONF_MAX_GRID_IMPORT_W,
    CONF_MAX_HOUSE_POWER_W,
    CONF_MIN_SURPLUS_W,
    CONF_SOLAR_END_H,
    CONF_SOLAR_POWER,
    CONF_SOLAR_START_H,
    CONF_START_SOC,
    CONF_START_SOLAR_W,
    CONF_STOP_SOC,
    DEFAULTS,
    DOMAIN,
    FAILSAFE_S,
    IDLE_HOLD_S,
    MANUAL_LOCK_S,
    MAX_DT_S,
    MAX_EVENTS,
    OVERLOAD_HOLD_S,
    OVERLOAD_LOCK_S,
    RETRY_DELAY_S,
    SOLAR_GRACE_S,
    SOLAR_HOLD_S,
    STORAGE_VERSION,
    SWITCH_OVERRIDE_S,
    TICK_S,
    WINTER_MONTHS,
)

_LOGGER = logging.getLogger(__name__)

DISCORD_TIMEOUT = aiohttp.ClientTimeout(total=5)


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class Settings:
    """Réglages (config entry : data + options, par-dessus les valeurs par défaut)."""

    solar_power: str
    battery_soc: str
    grid_import: str
    house_power: str
    heater_power: str
    heater_switch: str
    discord_webhook_url: str
    start_solar_w: float
    start_soc: float
    stop_soc: float
    max_grid_import_w: float
    max_house_power_w: float
    heater_off_w: float
    min_surplus_w: float
    solar_start_h: int
    solar_end_h: int
    hc_start_h: int
    hc_end_h: int

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Settings:
        raw = {**DEFAULTS, **entry.data, **entry.options}
        return cls(
            solar_power=str(raw[CONF_SOLAR_POWER]),
            battery_soc=str(raw[CONF_BATTERY_SOC]),
            grid_import=str(raw[CONF_GRID_IMPORT]),
            house_power=str(raw[CONF_HOUSE_POWER]),
            heater_power=str(raw[CONF_HEATER_POWER]),
            heater_switch=str(raw[CONF_HEATER_SWITCH]),
            discord_webhook_url=str(raw.get(CONF_DISCORD) or ""),
            start_solar_w=float(raw[CONF_START_SOLAR_W]),
            start_soc=float(raw[CONF_START_SOC]),
            stop_soc=float(raw[CONF_STOP_SOC]),
            max_grid_import_w=float(raw[CONF_MAX_GRID_IMPORT_W]),
            max_house_power_w=float(raw[CONF_MAX_HOUSE_POWER_W]),
            heater_off_w=float(raw[CONF_HEATER_OFF_W]),
            min_surplus_w=float(raw[CONF_MIN_SURPLUS_W]),
            solar_start_h=int(raw[CONF_SOLAR_START_H]),
            solar_end_h=int(raw[CONF_SOLAR_END_H]),
            hc_start_h=int(raw[CONF_HC_START_H]),
            hc_end_h=int(raw[CONF_HC_END_H]),
        )


# =============================================================================
# Condition temporisée
# =============================================================================
class Condition:
    """Vraie depuis N secondes. `grace` tolère de brèves interruptions."""

    def __init__(self, hold: float, grace: float = 0.0) -> None:
        self.hold, self.grace = hold, grace
        self.since: float | None = None
        self.false_since: float | None = None

    def update(self, active: bool, now: float) -> None:
        if active:
            self.false_since = None
            if self.since is None:
                self.since = now
        elif self.since is not None:
            if self.false_since is None:
                self.false_since = now
            if now - self.false_since >= self.grace:
                self.reset()

    def reset(self) -> None:
        self.since = self.false_since = None

    def ready(self, now: float) -> bool:
        return self.since is not None and now - self.since >= self.hold

    def view(self, now: float) -> dict[str, Any]:
        elapsed = (now - self.since) if self.since is not None else 0.0
        return {
            "active": self.since is not None,
            "elapsed": round(min(elapsed, self.hold)),
            "hold": self.hold,
            "ready": self.ready(now),
        }


def logical_day(now: datetime, hc_end_h: int) -> date:
    """Journée « chauffe-eau » : de la fin des heures creuses à la fin suivante."""
    return (now - timedelta(hours=hc_end_h)).date()


# =============================================================================
# Contrôleur
# =============================================================================
class Controller:
    """Toute la logique de décision est ici."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.s = Settings.from_entry(entry)
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.state")

        # État persisté
        self.mode: str | None = None          # "solar" | "night" | "manual" | None
        self.heated_day: date | None = None   # dernière journée logique avec cycle terminé
        self.lock_until = 0.0                 # horodatage epoch (anti-yoyo)
        self.lock_reason: str | None = None
        self.day: str | None = None           # jour calendaire des compteurs
        self.kwh: dict[str, float] = {"solar": 0.0, "night": 0.0, "manual": 0.0}
        self.ran_solar = False
        self.ran_night = False
        self.events: list[dict[str, str]] = []

        # État volatil
        self.retry_after = 0.0                # monotonic
        self._fail_alerted = False
        self._switch_override: tuple[str, float] | None = None
        self._last_mono: float | None = None
        self._ctx: dict[str, Any] = {}
        self.last: dict[str, Any] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()

        self.solar_start = Condition(SOLAR_HOLD_S, SOLAR_GRACE_S)
        self.battery_low = Condition(BATTERY_HOLD_S)
        self.overload = Condition(OVERLOAD_HOLD_S)
        self.heater_idle = Condition(IDLE_HOLD_S)
        self.data_lost = Condition(FAILSAFE_S)

        if self.s.start_soc <= self.s.stop_soc:
            _LOGGER.warning(
                "start_soc (%s) <= stop_soc (%s) : risque de démarrages/arrêts en boucle",
                self.s.start_soc,
                self.s.stop_soc,
            )

    # --- cycle de vie ---------------------------------------------------------
    async def async_start(self) -> None:
        self._load(await self._store.async_load() or {})
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.s.heater_switch], self._on_switch_change)
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_tick, timedelta(seconds=TICK_S))
        )
        _LOGGER.info(
            "Gestion eau chaude démarrée (solaire > %.0f W, surplus >= %.0f W, batterie >= %.0f %%, "
            "coupure batterie < %.0f %%).",
            self.s.start_solar_w,
            self.s.min_surplus_w,
            self.s.start_soc,
            self.s.stop_soc,
        )
        await self._async_tick()

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._store.async_save(self._payload())

    @callback
    def _on_switch_change(self, _event: Any) -> None:
        self.hass.async_create_task(self._async_tick())

    # --- abonnements (panneau, entités) --------------------------------------
    def subscribe(self, cb: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        @callback
        def _unsub() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _unsub

    @callback
    def _push(self) -> None:
        self.last = self.snapshot()
        for cb in list(self._listeners):
            try:
                cb(self.last)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Erreur dans un abonné")

    # --- persistance -----------------------------------------------------------
    def _load(self, data: dict[str, Any]) -> None:
        if data.get("mode") in ("solar", "night", "manual"):
            self.mode = data["mode"]
        if data.get("heated_day"):
            try:
                self.heated_day = date.fromisoformat(data["heated_day"])
            except ValueError:
                self.heated_day = None
        try:
            self.lock_until = float(data.get("lock_until", 0))
        except (TypeError, ValueError):
            self.lock_until = 0.0
        self.lock_reason = data.get("lock_reason")
        self.day = data.get("day")
        kwh = data.get("kwh") or {}
        for key in self.kwh:
            try:
                self.kwh[key] = float(kwh.get(key, 0.0))
            except (TypeError, ValueError):
                self.kwh[key] = 0.0
        self.ran_solar = bool(data.get("ran_solar", False))
        self.ran_night = bool(data.get("ran_night", False))
        self.events = list(data.get("events") or [])[-MAX_EVENTS:]

    def _payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "heated_day": self.heated_day.isoformat() if self.heated_day else None,
            "lock_until": self.lock_until,
            "lock_reason": self.lock_reason,
            "day": self.day,
            "kwh": self.kwh,
            "ran_solar": self.ran_solar,
            "ran_night": self.ran_night,
            "events": self.events,
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._payload, 5)

    # --- journal / notifications ----------------------------------------------
    def _event(self, message: str, kind: str = "info", notify: bool = True) -> None:
        _LOGGER.info(message)
        self.events.append(
            {"t": dt_util.now().isoformat(timespec="seconds"), "msg": message, "kind": kind}
        )
        del self.events[:-MAX_EVENTS]
        self._save()
        if notify:
            self._notify(message)

    def _notify(self, message: str) -> None:
        """Envoi Discord sans bloquer la boucle de contrôle."""
        if not self.s.discord_webhook_url:
            return
        self.entry.async_create_background_task(
            self.hass, self._send_discord(message), "gestion_eau_chaude_discord"
        )

    async def _send_discord(self, message: str) -> None:
        stamp = dt_util.now().strftime("%d/%m/%Y à %H:%M:%S")
        payload = {"content": f"⚡ **[GESTION EAU CHAUDE]** - *{stamp}*\n{message}"}
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                self.s.discord_webhook_url, json=payload, timeout=DISCORD_TIMEOUT
            ) as resp:
                if resp.status not in (200, 204):
                    _LOGGER.warning("Discord : HTTP %s", resp.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Discord : %s", err)

    # --- lecture des entités -----------------------------------------------------
    def _num(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _switch_state(self, mono: float) -> str | None:
        state = self.hass.states.get(self.s.heater_switch)
        real = state.state if state is not None and state.state in ("on", "off") else None
        if self._switch_override is not None:
            value, stamp = self._switch_override
            if real == value or mono - stamp > SWITCH_OVERRIDE_S:
                self._switch_override = None
            else:
                return value  # ordre tout juste envoyé, pas encore confirmé par l'entité
        return real

    # --- ordres ----------------------------------------------------------------------
    async def _set_switch(self, on: bool, attempts: int = 3) -> bool:
        service = "turn_on" if on else "turn_off"
        for attempt in range(1, attempts + 1):
            try:
                await self.hass.services.async_call(
                    "switch", service, {"entity_id": self.s.heater_switch}, blocking=True
                )
                return True
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("switch.%s : %s (essai %d/%d)", service, err, attempt, attempts)
            if attempt < attempts:
                await asyncio.sleep(2)
        return False

    async def _command(
        self,
        on: bool,
        mode: str | None,
        message: str,
        lock_s: float = 0.0,
        lock_reason: str | None = None,
        kind: str = "info",
        user: bool = False,
    ) -> bool:
        """Envoie l'ordre ; l'état interne n'est modifié que s'il a réussi."""
        mono = time.monotonic()
        if not user and mono < self.retry_after:
            return False
        if not await self._set_switch(on):
            self.retry_after = mono + RETRY_DELAY_S
            if not on and not self._fail_alerted:  # une seule alerte tant que ça échoue
                self._fail_alerted = True
                self._event("❌ ÉCHEC de la coupure du chauffe-eau, nouvel essai automatique.", "error")
            return False

        self._fail_alerted = False
        self._switch_override = ("on" if on else "off", mono)
        self.mode = mode
        if lock_s:
            self.lock_until = time.time() + lock_s
            self.lock_reason = lock_reason
        self._event(message, kind)
        self._save()
        return True

    async def _cut(
        self, message: str, lock_s: float = 0.0, lock_reason: str | None = None, kind: str = "stop"
    ) -> bool:
        return await self._command(False, None, message, lock_s, lock_reason, kind)

    async def async_force(self, on: bool) -> None:
        """Marche forcée / arrêt manuel demandés depuis le panneau ou l'entité switch."""
        async with self._lock:
            if on:
                ok = await self._command(
                    True,
                    "manual",
                    "🔧 Marche forcée activée depuis Home Assistant.",
                    kind="start",
                    user=True,
                )
            else:
                message = (
                    "🔧 Marche forcée désactivée : chauffe-eau coupé."
                    if self.mode == "manual"
                    else "🔧 Chauffe-eau coupé manuellement depuis Home Assistant."
                )
                ok = await self._command(
                    False,
                    None,
                    message,
                    lock_s=MANUAL_LOCK_S,
                    lock_reason="arrêt manuel",
                    kind="stop",
                    user=True,
                )
            self._push()
            if not ok:
                raise HomeAssistantError("Échec de la commande du chauffe-eau (voir les journaux).")

    def _sync_mode(self, sw: str | None) -> None:
        """Le mode doit suivre l'état réel du switch (coupure ou allumage externe)."""
        if sw == "off" and self.mode is not None:
            self.mode = None
            self._save()
        elif sw == "on" and self.mode is None:
            self.mode = "manual"  # allumé par autre chose que nous
            self._save()

    # --- énergie -------------------------------------------------------------------
    def _account_energy(self, now: datetime, mono: float, heater_w: float | None) -> None:
        today = now.date().isoformat()
        if self.day != today:
            self.day = today
            self.kwh = {"solar": 0.0, "night": 0.0, "manual": 0.0}
            self.ran_solar = False
            self.ran_night = False
            self._save()
        if self._last_mono is not None and heater_w is not None and heater_w > 0:
            dt = min(mono - self._last_mono, MAX_DT_S)
            key = self.mode if self.mode in self.kwh else "manual"
            self.kwh[key] += heater_w * dt / 3_600_000
            if heater_w > self.s.heater_off_w:
                if key == "solar":
                    self.ran_solar = True
                elif key == "night":
                    self.ran_night = True
        self._last_mono = mono

    # --- boucle -----------------------------------------------------------------------
    async def _async_tick(self, _now: datetime | None = None) -> None:
        async with self._lock:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Erreur dans le cycle de contrôle")
            self._push()

    async def _tick(self) -> None:
        s = self.s
        now = dt_util.now()
        mono = time.monotonic()
        solar = self._num(s.solar_power)
        soc = self._num(s.battery_soc)
        grid = self._num(s.grid_import)
        house = self._num(s.house_power)
        heater_w = self._num(s.heater_power)
        sw = self._switch_state(mono)

        self._account_energy(now, mono, heater_w)
        self._sync_mode(sw)

        on, off = sw == "on", sw == "off"
        locked = time.time() < self.lock_until
        in_solar = s.solar_start_h <= now.hour < s.solar_end_h
        in_hc = s.hc_start_h <= now.hour < s.hc_end_h
        winter = now.month in WINTER_MONTHS
        day = logical_day(now, s.hc_end_h)

        # Conditions instantanées (mises à jour à CHAQUE cycle, avant toute décision)
        overload = (
            on
            and grid is not None
            and house is not None
            and grid > s.max_grid_import_w
            and house > s.max_house_power_w
        )
        low_battery = on and self.mode == "solar" and soc is not None and soc < s.stop_soc
        idle = on and heater_w is not None and heater_w < s.heater_off_w
        can_start = off and self.mode is None and not locked
        # Cycle déjà terminé sur la journée logique en cours : ballon chaud,
        # inutile de le relancer (il ne consommerait rien et bouclerait toutes les 30 min).
        already_heated = self.heated_day == day
        # Surplus instantané = production - consommation de la maison. Ballon éteint,
        # la conso maison ne l'inclut pas : il faut que le surplus couvre le ballon,
        # sinon la batterie se viderait pour l'alimenter.
        surplus = solar - house if solar is not None and house is not None else None
        solar_gt = solar is not None and solar > s.start_solar_w
        soc_ge = soc is not None and soc >= s.start_soc
        surplus_ge = surplus is not None and surplus >= s.min_surplus_w
        solar_ok = (
            can_start and not already_heated and in_solar and solar_gt and soc_ge and surplus_ge
        )
        data_lost = on and self.mode == "solar" and (soc is None or grid is None or house is None)

        self.overload.update(overload, mono)
        self.battery_low.update(low_battery, mono)
        self.heater_idle.update(idle, mono)
        self.solar_start.update(solar_ok, mono)
        self.data_lost.update(data_lost, mono)

        self._ctx = {
            "now": now,
            "switch": sw,
            "solar": solar,
            "soc": soc,
            "grid": grid,
            "house": house,
            "heater_w": heater_w,
            "surplus": surplus,
            "in_solar": in_solar,
            "in_hc": in_hc,
            "winter": winter,
            "day": day,
            "checks": {
                "in_solar": in_solar,
                "not_done": not already_heated,
                "can_start": can_start,
                "solar": solar_gt,
                "soc": soc_ge,
                "surplus": surplus_ge,
            },
        }

        # 0. Fail-safe : plus de mesures fiables depuis trop longtemps (mode solaire)
        if on and self.data_lost.ready(mono):
            await self._cut(
                f"⚠️ Chauffe-eau interrompu (mesures batterie/réseau/maison indisponibles depuis "
                f"{FAILSAFE_S} s).",
                kind="warn",
            )
            return

        # 1. Sécurité surconsommation + import réseau (tous modes)
        if overload and self.overload.ready(mono):
            await self._cut(
                f"⚠️ Chauffe-eau interrompu (forte conso : {house:.0f} W et import réseau : {grid:.0f} W).",
                lock_s=OVERLOAD_LOCK_S,
                lock_reason="surconsommation",
                kind="warn",
            )
            return

        # 2. Sécurité batterie (chauffe solaire uniquement)
        if low_battery and self.battery_low.ready(mono):
            await self._cut(
                f"⚠️ Chauffe-eau interrompu (batterie à {soc:.0f} % < {s.stop_soc:.0f} %, "
                f"on préserve la nuit).",
                lock_s=BATTERY_LOCK_S,
                lock_reason="batterie basse",
                kind="warn",
            )
            return

        # 3. Fins de plage horaire
        if on and self.mode == "solar" and not in_solar:
            await self._cut(f"🛑 Chauffe-eau ARRÊTÉ (fin de plage solaire {s.solar_end_h:02d}h00).")
            return
        if on and self.mode == "night" and not in_hc:
            await self._cut(f"🛑 Chauffe-eau ARRÊTÉ (fin des heures creuses {s.hc_end_h:02d}h00).")
            return

        # 4. Fin de cycle de chauffe (thermostat du ballon coupé)
        if idle and self.heater_idle.ready(mono):
            self.heated_day = day
            self._save()
            await self._cut(
                f"✅ Chauffe-eau ARRÊTÉ (cycle terminé, conso ~0 W depuis {IDLE_HOLD_S // 60} min)."
            )
            return

        # 5. Démarrage solaire (seulement si aucun cycle n'est déjà terminé aujourd'hui)
        if solar_ok and self.solar_start.ready(mono):
            await self._command(
                True,
                "solar",
                f"🔥 Chauffe-eau DÉMARRÉ (solaire {solar:.0f} W, maison {house:.0f} W, "
                f"surplus {surplus:.0f} W et batterie {soc:.0f} % "
                f"stables depuis {SOLAR_HOLD_S // 60} min).",
                kind="start",
            )
            return

        # 6. Démarrage heures creuses hivernales (si pas de cycle terminé aujourd'hui)
        if can_start and not already_heated and winter and in_hc:
            await self._command(
                True,
                "night",
                "🌙 Chauffe-eau DÉMARRÉ (mode hiver : pas de cycle complet aujourd'hui, "
                "chauffe en heures creuses).",
                kind="start",
            )

    # --- instantané pour le panneau et les entités -------------------------------------
    def snapshot(self) -> dict[str, Any]:
        c = self._ctx
        if not c:
            return {}
        s = self.s
        mono = time.monotonic()
        now: datetime = c["now"]

        sw = self._switch_override[0] if self._switch_override else c["switch"]
        on = sw == "on"
        heater_w = c["heater_w"]
        locked_for = max(0.0, self.lock_until - time.time())
        locked = locked_for > 0
        cycle_done = self.heated_day == c["day"]
        forced = on and self.mode == "manual"

        # Statut global
        if sw is None:
            status = "unavailable"
        elif on:
            if heater_w is not None and heater_w < s.heater_off_w:
                status = "thermostat"
            else:
                status = f"heating_{self.mode or 'manual'}"
        elif locked:
            status = "locked"
        elif cycle_done:
            status = "done"
        elif c["in_solar"]:
            status = "waiting_solar"
        else:
            status = "standby"

        # Heures creuses : prévues cette nuit ?
        if on and self.mode == "night":
            night_plan = "running"
        elif not c["winter"]:
            night_plan = "off_season"
        elif cycle_done:
            night_plan = "not_needed"
        else:
            night_plan = "planned"

        total = sum(self.kwh.values())
        return {
            "ts": now.isoformat(timespec="seconds"),
            "hour": now.hour + now.minute / 60 + now.second / 3600,
            "status": status,
            "mode": self.mode,
            "switch": sw,
            "forced": forced,
            "values": {
                "solar_w": c["solar"],
                "soc": c["soc"],
                "grid_w": c["grid"],
                "house_w": c["house"],
                "heater_w": heater_w,
                "surplus_w": c["surplus"],
            },
            "settings": {
                "start_solar_w": s.start_solar_w,
                "start_soc": s.start_soc,
                "stop_soc": s.stop_soc,
                "max_grid_import_w": s.max_grid_import_w,
                "max_house_power_w": s.max_house_power_w,
                "heater_off_w": s.heater_off_w,
                "min_surplus_w": s.min_surplus_w,
            },
            "schedule": {
                "solar_start_h": s.solar_start_h,
                "solar_end_h": s.solar_end_h,
                "hc_start_h": s.hc_start_h,
                "hc_end_h": s.hc_end_h,
                "winter": c["winter"],
                "in_solar": c["in_solar"],
                "in_hc": c["in_hc"],
            },
            "cycle_done": cycle_done,
            "night_plan": night_plan,
            "energy": {
                "total": round(total, 3),
                "solar": round(self.kwh["solar"], 3),
                "night": round(self.kwh["night"], 3),
                "manual": round(self.kwh["manual"], 3),
            },
            "ran_solar": self.ran_solar,
            "ran_night": self.ran_night,
            "lock": {
                "remaining_s": round(locked_for),
                "reason": self.lock_reason if locked else None,
            },
            "start_checks": c["checks"],
            "timers": {
                "solar_start": self.solar_start.view(mono),
                "battery_low": self.battery_low.view(mono),
                "overload": self.overload.view(mono),
                "idle": self.heater_idle.view(mono),
                "data_lost": self.data_lost.view(mono),
            },
            "events": list(reversed(self.events)),
        }
