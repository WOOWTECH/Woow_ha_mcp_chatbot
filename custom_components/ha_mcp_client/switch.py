"""Switch platform for HA MCP Client — skill and cron job toggles."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nanobot import SkillsLoader, CronService

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switch entities from a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return

    entities: list[SwitchEntity] = []

    skills_loader: SkillsLoader | None = data.get("skills_loader")
    if skills_loader:
        for name, meta in skills_loader._cache.items():
            entities.append(NanobotSkillSwitch(entry, skills_loader, name, meta))

    cron_service: CronService | None = data.get("cron_service")
    if cron_service:
        for job_id, job in cron_service._jobs.items():
            entities.append(NanobotCronJobSwitch(entry, cron_service, job))

    if entities:
        async_add_entities(entities)


class NanobotSkillSwitch(SwitchEntity):
    """Switch entity for toggling a skill's always-on status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:puzzle-outline"

    def __init__(
        self,
        entry: ConfigEntry,
        skills_loader: SkillsLoader,
        skill_name: str,
        meta: dict[str, Any],
    ) -> None:
        self._entry = entry
        self._skills_loader = skills_loader
        self._skill_name = skill_name
        self._attr_unique_id = f"{entry.entry_id}_skill_{skill_name}"
        desc = meta.get("description", skill_name)
        self._attr_name = f"Skill: {skill_name}"
        self._attr_extra_state_attributes = {"description": desc}

    @property
    def is_on(self) -> bool:
        meta = self._skills_loader._cache.get(self._skill_name, {})
        return meta.get("always", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._skills_loader.toggle_skill(self._skill_name, always=True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._skills_loader.toggle_skill(self._skill_name, always=False)
        self.async_write_ha_state()


class NanobotCronJobSwitch(SwitchEntity):
    """Switch entity for enabling/disabling a cron job."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        entry: ConfigEntry,
        cron_service: CronService,
        job: Any,
    ) -> None:
        self._entry = entry
        self._cron_service = cron_service
        self._job_id = job.id
        self._attr_unique_id = f"{entry.entry_id}_cron_{job.id}"
        self._attr_name = f"Cron: {job.name or job.id}"
        self._attr_extra_state_attributes = {
            "job_id": job.id,
            "schedule_kind": job.schedule.kind,
            "payload_kind": job.payload.kind,
        }

    @property
    def is_on(self) -> bool:
        job = self._cron_service._jobs.get(self._job_id)
        return job.enabled if job else False

    @property
    def available(self) -> bool:
        return self._job_id in self._cron_service._jobs

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._cron_service.update_job(self._job_id, {"enabled": True})
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._cron_service.update_job(self._job_id, {"enabled": False})
        self.async_write_ha_state()
