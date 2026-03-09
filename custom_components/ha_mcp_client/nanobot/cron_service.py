"""Cron scheduling service for HA MCP Client.

Adapted from nanobot's cron service for Home Assistant.
Supports three schedule types: at (one-time), every (interval), cron (expression).
Two payload types: agent_turn (trigger AI conversation), system_event (fire HA event).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .cron_types import CronJob, CronSchedule, CronPayload, CronJobState, _now_ms

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Minimum tick interval (1 second)
_MIN_TICK_MS = 1000
# Maximum sleep time (60 seconds) to avoid missing jobs due to clock drift
_MAX_SLEEP_MS = 60_000


class CronService:
    """Cron scheduling service that runs as an asyncio background task.

    Persists jobs to store.json. Executes jobs by firing HA events
    or triggering AI conversation.
    """

    def __init__(self, hass: HomeAssistant, store_dir: Path) -> None:
        self.hass = hass
        self._store_dir = store_dir
        self._store_file = store_dir / "store.json"
        self._jobs: dict[str, CronJob] = {}
        self._timer_task: asyncio.Task | None = None
        self._running = False

    async def async_setup(self) -> None:
        """Initialize the cron service: load store and start tick loop."""
        await self.hass.async_add_executor_job(self._ensure_dir)
        await self._load_store()
        self._compute_all_next_runs()
        self._running = True
        self._arm_timer()
        _LOGGER.info(
            "CronService started: %d jobs (%d enabled)",
            len(self._jobs),
            sum(1 for j in self._jobs.values() if j.enabled),
        )

    async def async_stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
        self._timer_task = None
        _LOGGER.info("CronService stopped")

    def _ensure_dir(self) -> None:
        self._store_dir.mkdir(parents=True, exist_ok=True)

    # ── Timer loop ──

    def _arm_timer(self) -> None:
        """Schedule the next timer tick."""
        if not self._running:
            return

        delay_ms = self._compute_delay()
        delay_s = max(delay_ms / 1000, 0.1)  # At least 100ms

        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        self._timer_task = self.hass.async_create_task(self._timer_loop(delay_s))

    async def _timer_loop(self, delay_s: float) -> None:
        """Sleep then execute overdue jobs."""
        cancelled = False
        try:
            await asyncio.sleep(delay_s)
            if self._running:
                await self._on_tick()
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            _LOGGER.exception("Cron timer loop error")
        finally:
            # Only re-arm if still running AND not cancelled by _arm_timer replacement
            if self._running and not cancelled:
                self._arm_timer()

    def _compute_delay(self) -> int:
        """Compute ms until next job should fire."""
        now = _now_ms()
        min_delay = _MAX_SLEEP_MS

        for job in self._jobs.values():
            if not job.enabled or job.state.next_run_at_ms <= 0:
                continue
            delta = job.state.next_run_at_ms - now
            if delta <= 0:
                return _MIN_TICK_MS  # Overdue, tick immediately
            min_delay = min(min_delay, delta)

        return min_delay

    async def _on_tick(self) -> None:
        """Execute all overdue jobs."""
        now = _now_ms()
        jobs_to_run = [
            j for j in self._jobs.values()
            if j.enabled and 0 < j.state.next_run_at_ms <= now
        ]

        for job in jobs_to_run:
            await self._execute_job(job)

        if jobs_to_run:
            await self._save_store()

    async def _execute_job(self, job: CronJob) -> None:
        """Execute a single cron job."""
        _LOGGER.info("Executing cron job: %s (%s)", job.name, job.id)

        try:
            if job.payload.kind == "agent_turn":
                await self._execute_agent_turn(job)
            elif job.payload.kind == "system_event":
                await self._execute_system_event(job)
            else:
                _LOGGER.warning("Unknown payload kind: %s", job.payload.kind)
                job.state.last_status = "error"
                job.state.last_error = f"Unknown payload kind: {job.payload.kind}"
                return

            job.state.last_run_at_ms = _now_ms()
            job.state.last_status = "ok"
            job.state.last_error = ""

        except Exception as e:
            _LOGGER.error("Cron job %s failed: %s", job.id, e)
            job.state.last_run_at_ms = _now_ms()
            job.state.last_status = "error"
            job.state.last_error = str(e)

        # Reschedule or clean up
        if job.schedule.kind == "at":
            if job.delete_after_run:
                del self._jobs[job.id]
                _LOGGER.info("One-shot job %s deleted after run", job.id)
            else:
                job.enabled = False
                job.state.next_run_at_ms = 0
        else:
            self._compute_next_run(job)

        job.updated_at_ms = _now_ms()

    async def _execute_agent_turn(self, job: CronJob) -> None:
        """Trigger an AI conversation turn."""
        from .cron_types import _now_ms  # noqa: already imported at top

        self.hass.bus.async_fire(
            "ha_mcp_client_cron_agent_turn",
            {
                "job_id": job.id,
                "job_name": job.name,
                "message": job.payload.message,
            },
        )

        # Also try to call conversation.process directly
        try:
            from ..const import DOMAIN
            agent_id = None
            for state in self.hass.states.async_all("conversation"):
                if DOMAIN in state.entity_id:
                    agent_id = state.entity_id
                    break

            if agent_id and job.payload.message:
                await self.hass.services.async_call(
                    "conversation",
                    "process",
                    {
                        "text": job.payload.message,
                        "agent_id": agent_id,
                    },
                    blocking=False,
                )
        except Exception as e:
            _LOGGER.warning("Could not trigger conversation for cron job: %s", e)

    async def _execute_system_event(self, job: CronJob) -> None:
        """Fire a HA event and send persistent notification."""
        self.hass.bus.async_fire(
            "ha_mcp_client_cron_system_event",
            {
                "job_id": job.id,
                "job_name": job.name,
                "message": job.payload.message,
            },
        )

        # Send persistent notification to HA sidebar
        try:
            await self.hass.services.async_call(
                "notify",
                "persistent_notification",
                {
                    "title": f"🕐 排程事件：{job.name}",
                    "message": job.payload.message,
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.warning(
                "Could not send persistent notification for cron job %s: %s",
                job.id, e,
            )

    # ── Next-run computation ──

    def _compute_all_next_runs(self) -> None:
        """Compute next_run_at_ms for all enabled jobs."""
        for job in self._jobs.values():
            if job.enabled:
                self._compute_next_run(job)

    def _compute_next_run(self, job: CronJob) -> None:
        """Compute the next run time for a job."""
        now = _now_ms()

        if job.schedule.kind == "at":
            if job.schedule.at_ms and job.schedule.at_ms > now:
                job.state.next_run_at_ms = job.schedule.at_ms
            else:
                job.state.next_run_at_ms = 0  # Already past

        elif job.schedule.kind == "every":
            interval = job.schedule.every_ms or 0
            if interval <= 0:
                job.state.next_run_at_ms = 0
                return
            last = job.state.last_run_at_ms or now
            next_run = last + interval
            if next_run <= now:
                next_run = now + interval
            job.state.next_run_at_ms = next_run

        elif job.schedule.kind == "cron":
            job.state.next_run_at_ms = self._next_cron_run(
                job.schedule.cron or "* * * * *",
                job.schedule.tz,
            )

    def _next_cron_run(self, expression: str, tz_name: str | None) -> int:
        """Compute next run time from a cron expression."""
        try:
            from croniter import croniter
            from zoneinfo import ZoneInfo

            if tz_name:
                tz = ZoneInfo(tz_name)
                now = datetime.now(tz)
            else:
                now = datetime.now()

            cron = croniter(expression, now)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)

        except ImportError:
            _LOGGER.warning(
                "croniter not installed; cron expressions won't work. "
                "Add 'croniter' to manifest.json requirements."
            )
            return 0
        except Exception as e:
            _LOGGER.error("Invalid cron expression '%s': %s", expression, e)
            return 0

    # ── CRUD API ──

    async def add_job(
        self,
        name: str,
        schedule: dict[str, Any],
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
        delete_after_run: bool = False,
    ) -> CronJob:
        """Add a new cron job."""
        job = CronJob(
            name=name,
            enabled=enabled,
            delete_after_run=delete_after_run,
            schedule=CronSchedule.from_dict(schedule),
            payload=CronPayload.from_dict(payload or {}),
        )
        if enabled:
            self._compute_next_run(job)

        self._jobs[job.id] = job
        await self._save_store()
        self._arm_timer()

        _LOGGER.info("Added cron job: %s (%s)", job.name, job.id)
        return job

    async def remove_job(self, job_id: str) -> bool:
        """Remove a cron job."""
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        await self._save_store()
        self._arm_timer()
        return True

    async def update_job(self, job_id: str, updates: dict[str, Any]) -> CronJob | None:
        """Update a cron job's fields."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        if "name" in updates:
            job.name = updates["name"]
        if "enabled" in updates:
            job.enabled = updates["enabled"]
        if "delete_after_run" in updates:
            job.delete_after_run = updates["delete_after_run"]
        if "schedule" in updates:
            job.schedule = CronSchedule.from_dict(updates["schedule"])
        if "payload" in updates:
            job.payload = CronPayload.from_dict(updates["payload"])

        job.updated_at_ms = _now_ms()

        if job.enabled:
            self._compute_next_run(job)
        else:
            job.state.next_run_at_ms = 0

        await self._save_store()
        self._arm_timer()
        return job

    async def get_job(self, job_id: str) -> CronJob | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self) -> list[CronJob]:
        """List all jobs."""
        return list(self._jobs.values())

    async def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job execution."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        await self._execute_job(job)
        await self._save_store()
        return True

    async def get_stats(self) -> dict[str, Any]:
        """Get cron service statistics."""
        total = len(self._jobs)
        enabled = sum(1 for j in self._jobs.values() if j.enabled)
        return {
            "total_jobs": total,
            "enabled_jobs": enabled,
            "disabled_jobs": total - enabled,
            "store_file": str(self._store_file),
        }

    # ── Persistence ──

    async def _load_store(self) -> None:
        """Load jobs from store.json."""
        data = await self.hass.async_add_executor_job(self._read_store)
        if data:
            for job_data in data.get("jobs", []):
                try:
                    job = CronJob.from_dict(job_data)
                    self._jobs[job.id] = job
                except Exception as e:
                    _LOGGER.warning("Failed to load cron job: %s", e)

    async def _save_store(self) -> None:
        """Save jobs to store.json."""
        data = {
            "version": 1,
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }
        await self.hass.async_add_executor_job(self._write_store, data)

    def _read_store(self) -> dict[str, Any] | None:
        """Read store.json (sync)."""
        if not self._store_file.exists():
            return None
        try:
            return json.loads(self._store_file.read_text(encoding="utf-8"))
        except Exception as e:
            _LOGGER.error("Failed to read cron store: %s", e)
            return None

    def _write_store(self, data: dict[str, Any]) -> None:
        """Write store.json (sync)."""
        try:
            self._store_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            _LOGGER.error("Failed to write cron store: %s", e)
