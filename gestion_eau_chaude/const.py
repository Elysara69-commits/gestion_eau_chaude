"""Constantes de l'intégration Gestion eau chaude."""
from __future__ import annotations

DOMAIN = "gestion_eau_chaude"
VERSION = "1.2.0"

PANEL_URL = "gestion_eau_chaude"
PANEL_ELEMENT = "gestion-eau-chaude-panel"
STATIC_URL = "/gestion_eau_chaude_static"

STORAGE_VERSION = 1
MAX_EVENTS = 30

# --- Clés de configuration ---------------------------------------------------
CONF_SOLAR_POWER = "solar_power"
CONF_BATTERY_SOC = "battery_soc"
CONF_GRID_IMPORT = "grid_import"
CONF_HOUSE_POWER = "house_power"
CONF_HEATER_POWER = "heater_power"
CONF_HEATER_SWITCH = "heater_switch"
CONF_DISCORD = "discord_webhook_url"

CONF_START_SOLAR_W = "start_solar_w"
CONF_START_SOC = "start_soc"
CONF_STOP_SOC = "stop_soc"
CONF_MAX_GRID_IMPORT_W = "max_grid_import_w"
CONF_MAX_HOUSE_POWER_W = "max_house_power_w"
CONF_HEATER_NOMINAL_W = "heater_nominal_w"
CONF_HEATING_PRIORITY = "heating_priority_entity"
CONF_NIGHT_ALL_YEAR = "night_all_year"
CONF_HEATER_OFF_W = "heater_off_w"
CONF_MIN_SURPLUS_W = "min_surplus_w"

CONF_SOLAR_START_H = "solar_start_h"
CONF_SOLAR_END_H = "solar_end_h"
CONF_HC_START_H = "hc_start_h"
CONF_HC_END_H = "hc_end_h"

# Valeurs par défaut (celles du script d'origine)
DEFAULTS: dict[str, object] = {
    CONF_SOLAR_POWER: "sensor.solarnet_puissance_photovoltaique",
    CONF_BATTERY_SOC: "sensor.reserva_etat_de_charge",
    CONF_GRID_IMPORT: "sensor.solarnet_power_grid_import",
    CONF_HOUSE_POWER: "sensor.solarnet_power_load_consumed",
    CONF_HEATER_POWER: "sensor.interrupteur_wi_fi_sur_rail_din_avec_mesure_puissance",
    CONF_HEATER_SWITCH: "switch.interrupteur_wi_fi_sur_rail_din_avec_mesure_switch",
    CONF_DISCORD: "",
    CONF_START_SOLAR_W: 2200.0,      # démarrage si solaire > ce seuil...
    CONF_START_SOC: 85.0,            # ...et batterie >= ce seuil
    CONF_STOP_SOC: 80.0,             # coupure (mode solaire) si batterie < ce seuil
    CONF_MAX_GRID_IMPORT_W: 200.0,   # import réseau considéré comme anormal
    CONF_MAX_HOUSE_POWER_W: 8000.0,  # conso totale max (contrat 9 kW moins une marge) : au-delà, pause
    CONF_HEATER_NOMINAL_W: 3000.0,   # puissance du ballon : sert à vérifier qu'il « rentre » avant de (re)démarrer
    CONF_HEATING_PRIORITY: "",       # binary_sensor « le chauffage veut le solaire » (vide = pas de priorité)
    CONF_NIGHT_ALL_YEAR: True,       # chauffe en heures creuses toute l'année si pas de cycle solaire
    CONF_HEATER_OFF_W: 10.0,         # en dessous, le ballon ne chauffe plus
    CONF_MIN_SURPLUS_W: 2000.0,      # surplus requis au démarrage : solaire - conso maison
    CONF_SOLAR_START_H: 7,           # chauffe solaire autorisée de 07h...
    CONF_SOLAR_END_H: 19,            # ...à 19h
    CONF_HC_START_H: 3,              # heures creuses : 03h...
    CONF_HC_END_H: 6,                # ...06h
}

# --- Temporisations (secondes) -----------------------------------------------
TICK_S = 5              # période de la boucle de contrôle
SOLAR_HOLD_S = 300      # solaire + batterie OK pendant 5 min avant de démarrer
SOLAR_GRACE_S = 30      # micro-baisse tolérée (nuage passager) sans reset du timer
BATTERY_HOLD_S = 300    # batterie sous le seuil d'arrêt pendant 5 min avant de couper
BATTERY_LOCK_S = 1200   # interdiction de redémarrer après une coupure batterie
OVERLOAD_HOLD_S = 15    # surconso + import réseau pendant 15 s avant de couper
OVERLOAD_LOCK_S = 120   # verrou minimal après une pause surconso (la reprise exige en plus que le ballon « rentre »)
IDLE_HOLD_S = 1800      # ballon à ~0 W pendant 30 min = cycle de chauffe terminé
FAILSAFE_S = 120        # mesures batterie/réseau/maison indisponibles (mode solaire) -> on coupe
RETRY_DELAY_S = 30      # pause après un ordre échoué
RESUME_HOLD_S = 60      # le ballon doit « rentrer » sous la limite pendant 1 min avant de (re)démarrer
YIELD_HOLD_S = 120      # le chauffage réclame le solaire pendant 2 min avant de couper un ballon en marche solaire
YIELD_LOCK_S = 300      # verrou après une pause au profit du chauffage (anti-yoyo)
MANUAL_LOCK_S = 3600    # pas de redémarrage automatique pendant 1 h après un arrêt manuel
SWITCH_OVERRIDE_S = 10  # durée de validité de l'état « optimiste » après un ordre
MAX_DT_S = 120          # plafond du pas de temps pour l'intégration d'énergie
MIX_STALE_S = 300       # si les mesures manquent, on réutilise la dernière répartition de sources pendant 5 min

WINTER_MONTHS = {11, 12, 1, 2, 3}

STATUS_LABELS = {
    "unavailable": "Interrupteur indisponible",
    "heating_solar": "Chauffe solaire en cours",
    "heating_night": "Chauffe en heures creuses",
    "heating_manual": "Marche forcée",
    "thermostat": "Ballon chaud (thermostat atteint)",
    "locked": "Redémarrage verrouillé",
    "paused": "En pause (priorité chauffage)",
    "done": "Cycle terminé, ballon chaud",
    "waiting_solar": "En attente de surplus solaire",
    "standby": "Veille",
}
