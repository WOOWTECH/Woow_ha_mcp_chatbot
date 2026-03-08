"""Sensor platform for HA MCP Client — nanobot statistics."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities from a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return

    entities: list[SensorEntity] = []

    memory_store = data.get("memory_store")
    if memory_store:
        entities.extend(
            [
                NanobotMemoryEntriesSensor(entry, memory_store),
                NanobotHistoryEntriesSensor(entry, memory_store),
                NanobotLastConsolidationSensor(entry, memory_store),
            ]
        )

    skills_loader = data.get("skills_loader")
    if skills_loader:
        entities.append(NanobotSkillsCountSensor(entry, skills_loader))

    cron_service = data.get("cron_service")
    if cron_service:
        entities.append(NanobotCronJobsCountSensor(entry, cron_service))

    if entities:
        async_add_entities(entities, update_before_add=True)


class NanobotMemoryEntriesSensor(SensorEntity):
    """Sensor showing the number of long-term memory entries."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:brain"
    _attr_name = "Nanobot 記憶條目數"

    def __init__(self, entry: ConfigEntry, memory_store: Any) -> None:
        self._entry = entry
        self._memory_store = memory_store
        self._attr_unique_id = f"{entry.entry_id}_memory_entries"
        self._count = 0

    @property
    def native_value(self) -> int:
        return self._count

    async def async_update(self) -> None:
        stats = await self._memory_store.get_stats()
        self._count = stats.get("memory_entries", 0)


class NanobotHistoryEntriesSensor(SensorEntity):
    """Sensor showing the number of history entries."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:history"
    _attr_name = "Nanobot 歷史條目數"

    def __init__(self, entry: ConfigEntry, memory_store: Any) -> None:
        self._entry = entry
        self._memory_store = memory_store
        self._attr_unique_id = f"{entry.entry_id}_history_entries"
        self._count = 0

    @property
    def native_value(self) -> int:
        return self._count

    async def async_update(self) -> None:
        stats = await self._memory_store.get_stats()
        self._count = stats.get("history_entries", 0)


class NanobotLastConsolidationSensor(SensorEntity):
    """Sensor showing when memory was last consolidated."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-check-outline"
    _attr_name = "Nanobot 上次記憶整合"

    def __init__(self, entry: ConfigEntry, memory_store: Any) -> None:
        self._entry = entry
        self._memory_store = memory_store
        self._attr_unique_id = f"{entry.entry_id}_last_consolidation"
        self._value: str | None = None

    @property
    def native_value(self) -> str | None:
        return self._value or "尚未整合"

    async def async_update(self) -> None:
        stats = await self._memory_store.get_stats()
        self._value = stats.get("last_consolidation")


class NanobotSkillsCountSensor(SensorEntity):
    """Sensor showing the number of installed skills."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:puzzle-outline"
    _attr_name = "Nanobot 技能數量"

    def __init__(self, entry: ConfigEntry, skills_loader: Any) -> None:
        self._entry = entry
        self._skills_loader = skills_loader
        self._attr_unique_id = f"{entry.entry_id}_skills_count"

    @property
    def native_value(self) -> int:
        return len(self._skills_loader._cache)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cache = self._skills_loader._cache
        always_on = sum(1 for m in cache.values() if m.get("always"))
        return {"always_on": always_on, "on_demand": len(cache) - always_on}


class NanobotCronJobsCountSensor(SensorEntity):
    """Sensor showing the number of cron jobs."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"
    _attr_name = "Nanobot 排程數量"

    def __init__(self, entry: ConfigEntry, cron_service: Any) -> None:
        self._entry = entry
        self._cron_service = cron_service
        self._attr_unique_id = f"{entry.entry_id}_cron_jobs_count"

    @property
    def native_value(self) -> int:
        return len(self._cron_service._jobs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        jobs = self._cron_service._jobs
        enabled = sum(1 for j in jobs.values() if j.enabled)
        return {"enabled": enabled, "disabled": len(jobs) - enabled}
