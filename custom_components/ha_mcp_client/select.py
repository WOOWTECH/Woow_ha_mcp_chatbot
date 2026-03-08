"""Select platform for HA MCP Client — AI provider and model selection."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_AI_SERVICE,
    CONF_MODEL,
    AI_SERVICES,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OLLAMA_MODEL,
)

_LOGGER = logging.getLogger(__name__)

# Common models per provider
_MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-haiku-20241022",
    ],
    "openai": [
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5-mini",
        "o3-mini",
    ],
    "ollama": [
        "llama3.2",
        "llama3.1",
        "mistral",
        "gemma2",
        "qwen2.5",
    ],
    "openai_compatible": [
        "custom-model",
    ],
}

_DEFAULT_MODEL: dict[str, str] = {
    "anthropic": DEFAULT_ANTHROPIC_MODEL,
    "openai": DEFAULT_OPENAI_MODEL,
    "ollama": DEFAULT_OLLAMA_MODEL,
    "openai_compatible": "custom-model",
}


def _get_runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    return data.get("runtime_settings", {})


def _set_runtime(hass: HomeAssistant, entry_id: str, key: str, value: Any) -> None:
    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None:
        return
    if "runtime_settings" not in data:
        data["runtime_settings"] = {}
    data["runtime_settings"][key] = value


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up select entities from a config entry."""
    async_add_entities(
        [
            NanobotProviderSelect(entry),
            NanobotModelSelect(entry),
        ]
    )


class NanobotProviderSelect(SelectEntity):
    """Select entity for choosing the AI provider."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cloud-outline"
    _attr_name = "Nanobot AI Provider"
    _attr_options = AI_SERVICES

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_ai_provider"

    @property
    def current_option(self) -> str | None:
        return self._entry.data.get(CONF_AI_SERVICE, "openai")

    async def async_select_option(self, option: str) -> None:
        # Provider change requires config entry reload — store as runtime hint
        _set_runtime(self.hass, self._entry.entry_id, CONF_AI_SERVICE, option)
        self.async_write_ha_state()
        _LOGGER.info("AI provider changed to %s (requires reload to take effect)", option)


class NanobotModelSelect(SelectEntity):
    """Select entity for choosing the AI model."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:head-cog-outline"
    _attr_name = "Nanobot AI Model"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_ai_model"

    @property
    def options(self) -> list[str]:
        provider = self._entry.data.get(CONF_AI_SERVICE, "openai")
        provider_models = _MODELS_BY_PROVIDER.get(provider, [])
        # Always include the currently configured model
        current = self._entry.data.get(CONF_MODEL, "")
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        runtime_model = overrides.get("model", "")
        all_models = list(provider_models)
        for m in [current, runtime_model]:
            if m and m not in all_models:
                all_models.append(m)
        return all_models if all_models else ["default"]

    @property
    def current_option(self) -> str | None:
        overrides = _get_runtime(self.hass, self._entry.entry_id)
        return overrides.get("model", self._entry.data.get(CONF_MODEL, ""))

    async def async_select_option(self, option: str) -> None:
        _set_runtime(self.hass, self._entry.entry_id, "model", option)
        self.async_write_ha_state()
