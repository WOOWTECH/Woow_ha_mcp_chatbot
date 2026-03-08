"""Number platform for HA MCP Client — AI model parameters."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_TEMPERATURE,
    CONF_MAX_TOKENS,
    CONF_MEMORY_WINDOW,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MEMORY_WINDOW,
)

_LOGGER = logging.getLogger(__name__)


def _get_runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    """Get the runtime_settings dict for this entry."""
    data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    return data.get("runtime_settings", {})


def _set_runtime(hass: HomeAssistant, entry_id: str, key: str, value: Any) -> None:
    """Set a value in runtime_settings and persist to config_entry.data."""
    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None:
        return
    if "runtime_settings" not in data:
        data["runtime_settings"] = {}
    data["runtime_settings"][key] = value

    # Persist to config_entry.data so it survives restarts
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry:
        data["_skip_reload"] = True
        new_data = dict(entry.data)
        new_data[key] = value
        hass.config_entries.async_update_entry(entry, data=new_data)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number entities from a config entry."""
    async_add_entities(
        [
            NanobotTemperatureNumber(entry),
            NanobotMaxTokensNumber(entry),
            NanobotMemoryWindowNumber(entry),
        ]
    )


class NanobotTemperatureNumber(NumberEntity):
    """Number entity for AI temperature parameter."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer"
    _attr_name = "Nanobot Temperature"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 2.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_temperature"

    @property
    def native_value(self) -> float:
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        return overrides.get(
            CONF_TEMPERATURE,
            self._entry.data.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
        )

    async def async_set_native_value(self, value: float) -> None:
        _set_runtime(self.hass, self._entry.entry_id, CONF_TEMPERATURE, round(value, 1))
        self.async_write_ha_state()


class NanobotMaxTokensNumber(NumberEntity):
    """Number entity for AI max_tokens parameter."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"
    _attr_name = "Nanobot Max Tokens"
    _attr_native_min_value = 100
    _attr_native_max_value = 128000
    _attr_native_step = 100
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_max_tokens"

    @property
    def native_value(self) -> int:
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        return overrides.get(
            CONF_MAX_TOKENS,
            self._entry.data.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
        )

    async def async_set_native_value(self, value: float) -> None:
        _set_runtime(self.hass, self._entry.entry_id, CONF_MAX_TOKENS, int(value))
        self.async_write_ha_state()


class NanobotMemoryWindowNumber(NumberEntity):
    """Number entity for memory consolidation window threshold."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:memory"
    _attr_name = "Nanobot 記憶整合閾值"
    _attr_native_min_value = 10
    _attr_native_max_value = 500
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_memory_window"

    @property
    def native_value(self) -> int:
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        return overrides.get(
            CONF_MEMORY_WINDOW,
            self._entry.data.get(CONF_MEMORY_WINDOW, DEFAULT_MEMORY_WINDOW),
        )

    async def async_set_native_value(self, value: float) -> None:
        _set_runtime(self.hass, self._entry.entry_id, CONF_MEMORY_WINDOW, int(value))
        self.async_write_ha_state()
