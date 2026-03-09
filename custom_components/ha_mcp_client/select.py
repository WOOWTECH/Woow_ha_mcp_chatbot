"""Select platform for HA MCP Client — active LLM provider and reasoning effort."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_LLM_PROVIDERS,
    CONF_ACTIVE_LLM_PROVIDER,
    CONF_REASONING_EFFORT,
    DEFAULT_REASONING_EFFORT,
    REASONING_EFFORTS,
)

_LOGGER = logging.getLogger(__name__)


def _get_runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
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
    """Set up select entities from a config entry."""
    async_add_entities(
        [
            ActiveLLMSelect(entry),
            NanobotReasoningEffortSelect(entry),
        ]
    )


class ActiveLLMSelect(SelectEntity):
    """Select entity for choosing the active LLM provider."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:swap-horizontal"
    _attr_name = "Active LLM Provider"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_active_llm"

    @property
    def options(self) -> list[str]:
        providers = self._entry.data.get(CONF_LLM_PROVIDERS, [])
        return [p["id"] for p in providers] if providers else ["none"]

    @property
    def current_option(self) -> str | None:
        return self._entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")

    async def async_select_option(self, option: str) -> None:
        """Switch active LLM provider and update runtime_settings."""
        providers = self._entry.data.get(CONF_LLM_PROVIDERS, [])
        target = None
        for p in providers:
            if p["id"] == option:
                target = p
                break

        if not target:
            _LOGGER.warning("Provider %s not found in llm_providers", option)
            return

        # Update runtime_settings
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data:
            rt = data.setdefault("runtime_settings", {})
            rt["ai_service"] = target.get("provider", "openai")
            rt["model"] = target.get("model", "")
            rt["api_key"] = target.get("api_key", "")
            rt["base_url"] = target.get("base_url")

        # Persist active_llm_provider to config_entry.data
        entry = self.hass.config_entries.async_get_entry(self._entry.entry_id)
        if entry:
            if data:
                data["_skip_reload"] = True
            new_data = dict(entry.data)
            new_data[CONF_ACTIVE_LLM_PROVIDER] = option
            self.hass.config_entries.async_update_entry(entry, data=new_data)

        self.async_write_ha_state()
        _LOGGER.info("Active LLM switched to %s (%s / %s)",
                      option, target.get("provider"), target.get("model"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show current provider details."""
        active_id = self._entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")
        providers = self._entry.data.get(CONF_LLM_PROVIDERS, [])
        for p in providers:
            if p["id"] == active_id:
                key = p.get("api_key", "")
                masked = f"{key[:3]}***{key[-3:]}" if key and len(key) > 6 else ("***" if key else None)
                return {
                    "provider": p.get("provider"),
                    "name": p.get("name"),
                    "model": p.get("model"),
                    "api_key_masked": masked,
                    "base_url": p.get("base_url"),
                }
        return {}


class NanobotReasoningEffortSelect(SelectEntity):
    """Select entity for choosing the reasoning effort level."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:head-lightbulb-outline"
    _attr_name = "Nanobot Reasoning Effort"
    _attr_options = REASONING_EFFORTS

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_reasoning_effort"

    @property
    def current_option(self) -> str | None:
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        return overrides.get(
            CONF_REASONING_EFFORT,
            self._entry.data.get(CONF_REASONING_EFFORT, DEFAULT_REASONING_EFFORT),
        )

    async def async_select_option(self, option: str) -> None:
        _set_runtime(self.hass, self._entry.entry_id, CONF_REASONING_EFFORT, option)
        self.async_write_ha_state()
