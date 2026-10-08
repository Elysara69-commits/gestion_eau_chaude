"""Configuration de l'intégration Gestion eau chaude."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
)

INT_KEYS = (CONF_SOLAR_START_H, CONF_SOLAR_END_H, CONF_HC_START_H, CONF_HC_END_H)
FLOAT_KEYS = (
    CONF_START_SOLAR_W,
    CONF_START_SOC,
    CONF_STOP_SOC,
    CONF_MAX_GRID_IMPORT_W,
    CONF_MAX_HOUSE_POWER_W,
    CONF_HEATER_OFF_W,
    CONF_MIN_SURPLUS_W,
)


def _number(min_: float, max_: float, step: float, unit: str | None = None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_,
            max=max_,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _schema(values: dict[str, Any]) -> vol.Schema:
    sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    switch = selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))

    def d(key: str) -> Any:
        return values.get(key, DEFAULTS[key])

    return vol.Schema(
        {
            vol.Required(CONF_SOLAR_POWER, default=d(CONF_SOLAR_POWER)): sensor,
            vol.Required(CONF_BATTERY_SOC, default=d(CONF_BATTERY_SOC)): sensor,
            vol.Required(CONF_GRID_IMPORT, default=d(CONF_GRID_IMPORT)): sensor,
            vol.Required(CONF_HOUSE_POWER, default=d(CONF_HOUSE_POWER)): sensor,
            vol.Required(CONF_HEATER_POWER, default=d(CONF_HEATER_POWER)): sensor,
            vol.Required(CONF_HEATER_SWITCH, default=d(CONF_HEATER_SWITCH)): switch,
            vol.Required(CONF_START_SOLAR_W, default=d(CONF_START_SOLAR_W)): _number(0, 20000, 50, "W"),
            vol.Required(CONF_MIN_SURPLUS_W, default=d(CONF_MIN_SURPLUS_W)): _number(0, 20000, 50, "W"),
            vol.Required(CONF_START_SOC, default=d(CONF_START_SOC)): _number(0, 100, 1, "%"),
            vol.Required(CONF_STOP_SOC, default=d(CONF_STOP_SOC)): _number(0, 100, 1, "%"),
            vol.Required(CONF_MAX_GRID_IMPORT_W, default=d(CONF_MAX_GRID_IMPORT_W)): _number(0, 20000, 10, "W"),
            vol.Required(CONF_MAX_HOUSE_POWER_W, default=d(CONF_MAX_HOUSE_POWER_W)): _number(0, 30000, 50, "W"),
            vol.Required(CONF_HEATER_OFF_W, default=d(CONF_HEATER_OFF_W)): _number(0, 500, 1, "W"),
            vol.Required(CONF_SOLAR_START_H, default=d(CONF_SOLAR_START_H)): _number(0, 23, 1, "h"),
            vol.Required(CONF_SOLAR_END_H, default=d(CONF_SOLAR_END_H)): _number(1, 24, 1, "h"),
            vol.Required(CONF_HC_START_H, default=d(CONF_HC_START_H)): _number(0, 23, 1, "h"),
            vol.Required(CONF_HC_END_H, default=d(CONF_HC_END_H)): _number(1, 24, 1, "h"),
            vol.Optional(
                CONF_DISCORD, description={"suggested_value": values.get(CONF_DISCORD, "")}
            ): selector.TextSelector(),
        }
    )


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    for key in INT_KEYS:
        data[key] = int(data[key])
    for key in FLOAT_KEYS:
        data[key] = float(data[key])
    data[CONF_DISCORD] = (data.get(CONF_DISCORD) or "").strip()
    return data


def _validate(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if data[CONF_START_SOC] <= data[CONF_STOP_SOC]:
        errors["base"] = "soc_hysteresis"
    elif not 0 <= data[CONF_SOLAR_START_H] < data[CONF_SOLAR_END_H] <= 24:
        errors["base"] = "bad_hours"
    elif not 0 <= data[CONF_HC_START_H] < data[CONF_HC_END_H] <= 24:
        errors["base"] = "bad_hours"
    return errors


class GestionEauChaudeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flux de configuration (instance unique)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize(user_input)
            errors = _validate(data)
            if not errors:
                return self.async_create_entry(title="Gestion eau chaude", data=data)
            user_input = data

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or DEFAULTS),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GestionEauChaudeOptionsFlow()


class GestionEauChaudeOptionsFlow(OptionsFlow):
    """Modification des réglages (entités, seuils, plages horaires)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            data = _normalize(user_input)
            errors = _validate(data)
            if not errors:
                return self.async_create_entry(title="", data=data)
            current = data

        return self.async_show_form(step_id="init", data_schema=_schema(current), errors=errors)
