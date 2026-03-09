"""Bidirectional sync between CronService jobs and HA native automations.

Every cron job gets a corresponding automation in automations.yaml with
ID = ha_mcp_cron_{job_id}. Changes in either direction are synchronized:
  - Forward: cron CRUD → create/update/delete automation
  - Reverse: automation_reloaded event → update cron schedule/message (not payload kind)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant
    from .cron_service import CronService
    from .cron_types import CronJob

_LOGGER = logging.getLogger(__name__)

_AUTO_ID_PREFIX = "ha_mcp_cron_"


class CronAutomationSync:
    """Manages bidirectional sync between cron jobs and HA automations."""

    def __init__(self, hass: HomeAssistant, cron_service: CronService) -> None:
        self.hass = hass
        self.cron_service = cron_service
        self._syncing = False
        self._unsub_reload: Any = None

    # ── Lifecycle ──

    async def async_setup(self) -> None:
        """Register event listeners and run initial reconciliation."""
        self._unsub_reload = self.hass.bus.async_listen(
            "automation_reloaded", self._on_automation_reloaded
        )
        # Delay initial reconciliation to let HA finish loading automations
        self.hass.async_create_task(self._delayed_reconcile())

    async def _delayed_reconcile(self) -> None:
        """Wait a bit before initial reconciliation to let HA load automations."""
        import asyncio
        await asyncio.sleep(10)
        await self._reconcile()

    async def async_teardown(self) -> None:
        """Unregister event listeners."""
        if self._unsub_reload:
            self._unsub_reload()
            self._unsub_reload = None

    # ── Forward sync: Cron → Automation ──

    async def on_job_added(self, job: CronJob) -> None:
        """Cron job created → create matching automation."""
        if self._syncing:
            return
        auto_id = self._automation_id(job.id)
        trigger = _schedule_to_trigger(job.schedule)
        action = self._build_notification_action(job)
        alias = f"Cron: {job.name}"
        description = (
            f"由 cron job [{job.id}] '{job.name}' 自動同步。"
            f"排程：{job.schedule.kind}，動作：{job.payload.kind}"
        )
        await self._upsert_automation(auto_id, alias, description, trigger, action)

    async def on_job_updated(self, job: CronJob) -> None:
        """Cron job updated → update matching automation."""
        if self._syncing:
            return
        auto_id = self._automation_id(job.id)
        trigger = _schedule_to_trigger(job.schedule)
        action = self._build_notification_action(job)
        alias = f"Cron: {job.name}"
        description = (
            f"由 cron job [{job.id}] '{job.name}' 自動同步。"
            f"排程：{job.schedule.kind}，動作：{job.payload.kind}"
        )
        await self._upsert_automation(auto_id, alias, description, trigger, action)

    async def on_job_removed(self, job_id: str) -> None:
        """Cron job deleted → delete matching automation."""
        if self._syncing:
            return
        auto_id = self._automation_id(job_id)
        await self._remove_automation_by_id(auto_id)

    # ── Reverse sync: Automation → Cron ──

    async def _on_automation_reloaded(self, event: Event) -> None:
        """HA automations reloaded (could be from UI edit) → reconcile."""
        await self._reconcile()

    async def _reconcile(self) -> None:
        """Full comparison of cron jobs vs automations.yaml entries."""
        if self._syncing:
            return
        self._syncing = True
        try:
            automations = await self._read_cron_automations()
            cron_jobs = {j.id: j for j in await self.cron_service.list_jobs()}

            # Forward: cron job exists but automation missing → create
            for job_id, job in cron_jobs.items():
                auto_id = self._automation_id(job_id)
                if auto_id not in automations:
                    _LOGGER.info("Reconcile: creating missing automation for job %s", job_id)
                    trigger = _schedule_to_trigger(job.schedule)
                    action = self._build_notification_action(job)
                    alias = f"Cron: {job.name}"
                    description = (
                        f"由 cron job [{job.id}] '{job.name}' 自動同步。"
                        f"排程：{job.schedule.kind}，動作：{job.payload.kind}"
                    )
                    await self._upsert_automation(
                        auto_id, alias, description, trigger, action
                    )

            # Reverse: automation exists and cron job exists → sync schedule/message
            # Re-read after possible forward creates
            automations = await self._read_cron_automations()
            for auto_id, auto_config in automations.items():
                job_id = auto_id.replace(_AUTO_ID_PREFIX, "", 1)
                if job_id in cron_jobs:
                    await self._reverse_sync_job(cron_jobs[job_id], auto_config)

            # Orphan cleanup: automation exists but no matching cron job → remove
            for auto_id in list(automations.keys()):
                job_id = auto_id.replace(_AUTO_ID_PREFIX, "", 1)
                if job_id not in cron_jobs:
                    _LOGGER.info("Reconcile: removing orphan automation %s", auto_id)
                    await self._remove_automation_by_id(auto_id)

        except Exception as e:
            _LOGGER.error("Reconciliation failed: %s", e)
        finally:
            self._syncing = False

    async def _reverse_sync_job(self, job: CronJob, auto_config: dict) -> None:
        """Sync automation changes back to cron job (schedule + message only)."""
        updates: dict[str, Any] = {}

        # Extract schedule from automation trigger
        new_schedule = _trigger_to_schedule(auto_config.get("trigger", []))
        if new_schedule:
            current = job.schedule.to_dict()
            if new_schedule != current:
                updates["schedule"] = new_schedule

        # Extract message from automation action (persistent_notification message)
        new_message = _extract_message_from_action(auto_config.get("action", []))
        if new_message and new_message != job.payload.message:
            updates["payload"] = {"kind": job.payload.kind, "message": new_message}

        if updates:
            _LOGGER.info(
                "Reverse sync: updating cron job %s with %s",
                job.id, list(updates.keys()),
            )
            await self.cron_service.update_job(job.id, updates)

    # ── Helpers ──

    @staticmethod
    def _automation_id(job_id: str) -> str:
        return f"{_AUTO_ID_PREFIX}{job_id}"

    @staticmethod
    def _build_notification_action(job: CronJob) -> list[dict[str, Any]]:
        """Build persistent_notification action for a cron job."""
        return [{
            "service": "notify.persistent_notification",
            "data": {
                "title": f"🕐 排程通知：{job.name}",
                "message": job.payload.message,
            },
        }]

    async def _upsert_automation(
        self,
        auto_id: str,
        alias: str,
        description: str,
        trigger: list[dict[str, Any]],
        action: list[dict[str, Any]],
    ) -> None:
        """Create or update an automation in automations.yaml."""
        config_path = self.hass.config.path("automations.yaml")

        def _do_upsert():
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or []
            except FileNotFoundError:
                existing = []
            if not isinstance(existing, list):
                existing = []

            # Check if exists
            found = False
            for auto in existing:
                if auto.get("id") == auto_id:
                    auto["alias"] = alias
                    auto["description"] = description
                    auto["trigger"] = trigger
                    auto["action"] = action
                    found = True
                    break

            if not found:
                existing.append({
                    "id": auto_id,
                    "alias": alias,
                    "description": description,
                    "trigger": trigger,
                    "action": action,
                    "mode": "single",
                })

            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

            return found

        try:
            was_update = await self.hass.async_add_executor_job(_do_upsert)
            await self.hass.services.async_call("automation", "reload", blocking=True)
            action_word = "updated" if was_update else "created"
            _LOGGER.info("Automation %s %s for sync", auto_id, action_word)
        except Exception as e:
            _LOGGER.error("Failed to upsert automation %s: %s", auto_id, e)

    async def _remove_automation_by_id(self, auto_id: str) -> None:
        """Remove an automation from automations.yaml."""
        config_path = self.hass.config.path("automations.yaml")

        def _do_remove():
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or []
            except FileNotFoundError:
                return False
            if not isinstance(existing, list):
                return False

            original_len = len(existing)
            existing[:] = [a for a in existing if a.get("id") != auto_id]
            if len(existing) == original_len:
                return False

            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
            return True

        try:
            removed = await self.hass.async_add_executor_job(_do_remove)
            if removed:
                await self.hass.services.async_call("automation", "reload", blocking=True)
                _LOGGER.info("Automation %s removed for sync", auto_id)
        except Exception as e:
            _LOGGER.error("Failed to remove automation %s: %s", auto_id, e)

    async def _read_cron_automations(self) -> dict[str, dict]:
        """Read all ha_mcp_cron_* automations from automations.yaml."""
        config_path = self.hass.config.path("automations.yaml")

        def _read():
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or []
            except FileNotFoundError:
                return {}
            if not isinstance(existing, list):
                return {}

            result = {}
            for auto in existing:
                auto_id = auto.get("id", "")
                if isinstance(auto_id, str) and auto_id.startswith(_AUTO_ID_PREFIX):
                    result[auto_id] = auto
            return result

        return await self.hass.async_add_executor_job(_read)


# ── Schedule/trigger conversion utilities ──

def _schedule_to_trigger(schedule) -> list[dict[str, Any]]:
    """Convert CronSchedule → HA automation trigger."""
    if schedule.kind == "at":
        if not schedule.at_ms:
            return [{"platform": "time_pattern", "minutes": "/30"}]
        dt = datetime.fromtimestamp(schedule.at_ms / 1000, tz=timezone.utc)
        local_dt = dt.astimezone()
        return [{"platform": "time", "at": local_dt.strftime("%H:%M:%S")}]

    elif schedule.kind == "every":
        every_ms = schedule.every_ms or 0
        if every_ms <= 0:
            return [{"platform": "time_pattern", "minutes": "/30"}]
        total_seconds = every_ms // 1000
        if total_seconds >= 3600:
            hours = total_seconds // 3600
            return [{"platform": "time_pattern", "hours": f"/{hours}"}]
        elif total_seconds >= 60:
            minutes = total_seconds // 60
            return [{"platform": "time_pattern", "minutes": f"/{minutes}"}]
        else:
            seconds = max(total_seconds, 1)
            return [{"platform": "time_pattern", "seconds": f"/{seconds}"}]

    elif schedule.kind == "cron":
        parts = (schedule.cron or "* * * * *").split()
        if len(parts) < 2:
            return [{"platform": "time_pattern", "minutes": "/30"}]
        trigger: dict[str, Any] = {"platform": "time_pattern"}
        if parts[0] != "*":
            trigger["minutes"] = parts[0]
        if parts[1] != "*":
            trigger["hours"] = parts[1]
        return [trigger]

    return [{"platform": "time_pattern", "minutes": "/30"}]


def _trigger_to_schedule(triggers: list[dict]) -> dict[str, Any] | None:
    """Reverse-convert HA automation trigger → cron schedule dict.

    Returns a schedule dict compatible with CronSchedule.from_dict(),
    or None if the trigger format is unrecognized.
    """
    if not triggers:
        return None

    t = triggers[0]
    platform = t.get("platform", "")

    if platform == "time":
        # platform: time, at: "HH:MM:SS" → kind: at
        at_str = t.get("at", "")
        if not at_str:
            return None
        try:
            parts = at_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            # Build today's datetime at that time, convert to ms
            now = datetime.now()
            dt = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if dt < now:
                from datetime import timedelta
                dt += timedelta(days=1)
            at_ms = int(dt.timestamp() * 1000)
            return {"kind": "at", "at_ms": at_ms}
        except (ValueError, IndexError):
            return None

    elif platform == "time_pattern":
        # time_pattern with /N → kind: every
        for field in ("hours", "minutes", "seconds"):
            val = t.get(field, "")
            if isinstance(val, str) and val.startswith("/"):
                try:
                    n = int(val[1:])
                except ValueError:
                    continue
                if field == "hours":
                    return {"kind": "every", "every_ms": n * 3600_000}
                elif field == "minutes":
                    return {"kind": "every", "every_ms": n * 60_000}
                else:
                    return {"kind": "every", "every_ms": n * 1000}

        # time_pattern with fixed minutes/hours → kind: cron
        mins = t.get("minutes", "*")
        hours = t.get("hours", "*")
        return {"kind": "cron", "cron": f"{mins} {hours} * * *"}

    return None


def _extract_message_from_action(actions: list[dict]) -> str | None:
    """Extract message text from automation actions.

    Looks for notify.persistent_notification service calls first,
    then falls back to conversation.process text.
    """
    for act in actions:
        service = act.get("service", "")
        if service == "notify.persistent_notification":
            data = act.get("data", {})
            msg = data.get("message", "")
            if msg:
                return msg

    # Fallback: conversation.process text
    for act in actions:
        service = act.get("service", "")
        if service == "conversation.process":
            data = act.get("data", {})
            text = data.get("text", "")
            if text:
                return text

    # Fallback: event data message
    for act in actions:
        event_data = act.get("event_data", {})
        msg = event_data.get("message", "")
        if msg:
            return msg

    return None
