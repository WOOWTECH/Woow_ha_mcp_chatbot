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
        # Per-job sensors: next_run and last_status
        for job_id, job in cron_service._jobs.items():
            entities.append(NanobotCronJobNextRunSensor(entry, cron_service, job))
            entities.append(NanobotCronJobLastStatusSensor(entry, cron_service, job))

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


class NanobotCronJobNextRunSensor(SensorEntity):
    """Sensor showing the next run time for a specific cron job."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-fast"

    def __init__(self, entry: ConfigEntry, cron_service: Any, job: Any) -> None:
        self._entry = entry
        self._cron_service = cron_service
        self._job_id = job.id
        self._attr_unique_id = f"{entry.entry_id}_cron_{job.id}_next_run"
        self._attr_name = f"Cron {job.name or job.id} 下次執行"

    @property
    def available(self) -> bool:
        return self._job_id in self._cron_service._jobs

    @property
    def native_value(self) -> str | None:
        job = self._cron_service._jobs.get(self._job_id)
        if not job or job.state.next_run_at_ms <= 0:
            return "未排程"
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(job.state.next_run_at_ms / 1000, tz=timezone.utc)
        return dt.isoformat()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        job = self._cron_service._jobs.get(self._job_id)
        if not job:
            return {}
        return {
            "job_id": job.id,
            "schedule_kind": job.schedule.kind,
            "enabled": job.enabled,
            "next_run_at_ms": job.state.next_run_at_ms,
        }


class NanobotCronJobLastStatusSensor(SensorEntity):
    """Sensor showing the last execution status for a specific cron job."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, entry: ConfigEntry, cron_service: Any, job: Any) -> None:
        self._entry = entry
        self._cron_service = cron_service
        self._job_id = job.id
        self._attr_unique_id = f"{entry.entry_id}_cron_{job.id}_last_status"
        self._attr_name = f"Cron {job.name or job.id} 上次狀態"

    @property
    def available(self) -> bool:
        return self._job_id in self._cron_service._jobs

    @property
    def native_value(self) -> str:
        job = self._cron_service._jobs.get(self._job_id)
        if not job or not job.state.last_status:
            return "尚未執行"
        return job.state.last_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        job = self._cron_service._jobs.get(self._job_id)
        if not job:
            return {}
        attrs: dict[str, Any] = {
            "job_id": job.id,
            "last_run_at_ms": job.state.last_run_at_ms,
        }
        if job.state.last_error:
            attrs["last_error"] = job.state.last_error
        return attrs
