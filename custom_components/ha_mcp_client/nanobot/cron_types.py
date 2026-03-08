"""Data types for the cron scheduling system."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.time() * 1000)


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""

    kind: str  # "at" | "every" | "cron"
    at_ms: int | None = None       # For kind="at": Unix timestamp ms
    every_ms: int | None = None    # For kind="every": interval in ms
    cron: str | None = None        # For kind="cron": cron expression
    tz: str | None = None          # For kind="cron": timezone

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.kind == "at" and self.at_ms is not None:
            d["at_ms"] = self.at_ms
        elif self.kind == "every" and self.every_ms is not None:
            d["every_ms"] = self.every_ms
        elif self.kind == "cron":
            d["cron"] = self.cron
            if self.tz:
                d["tz"] = self.tz
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronSchedule:
        return cls(
            kind=data.get("kind", "at"),
            at_ms=data.get("at_ms"),
            every_ms=data.get("every_ms"),
            cron=data.get("cron"),
            tz=data.get("tz"),
        )


@dataclass
class CronPayload:
    """Payload defining what a cron job does when triggered."""

    kind: str = "agent_turn"    # "agent_turn" | "system_event"
    message: str = ""           # Message text for agent_turn or event data

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronPayload:
        return cls(
            kind=data.get("kind", "agent_turn"),
            message=data.get("message", ""),
        )


@dataclass
class CronJobState:
    """Runtime state of a cron job."""

    next_run_at_ms: int = 0
    last_run_at_ms: int = 0
    last_status: str = ""        # "ok" | "error" | "skipped"
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_run_at_ms": self.next_run_at_ms,
            "last_run_at_ms": self.last_run_at_ms,
            "last_status": self.last_status,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronJobState:
        return cls(
            next_run_at_ms=data.get("next_run_at_ms", 0),
            last_run_at_ms=data.get("last_run_at_ms", 0),
            last_status=data.get("last_status", ""),
            last_error=data.get("last_error", ""),
        )


@dataclass
class CronJob:
    """A scheduled job."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    enabled: bool = True
    delete_after_run: bool = False
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="at"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = field(default_factory=_now_ms)
    updated_at_ms: int = field(default_factory=_now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "delete_after_run": self.delete_after_run,
            "schedule": self.schedule.to_dict(),
            "payload": self.payload.to_dict(),
            "state": self.state.to_dict(),
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronJob:
        return cls(
            id=data.get("id", uuid.uuid4().hex[:8]),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            delete_after_run=data.get("delete_after_run", False),
            schedule=CronSchedule.from_dict(data.get("schedule", {})),
            payload=CronPayload.from_dict(data.get("payload", {})),
            state=CronJobState.from_dict(data.get("state", {})),
            created_at_ms=data.get("created_at_ms", _now_ms()),
            updated_at_ms=data.get("updated_at_ms", _now_ms()),
        )

    def to_summary(self) -> dict[str, Any]:
        """Summary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "schedule_kind": self.schedule.kind,
            "payload_kind": self.payload.kind,
            "next_run_at_ms": self.state.next_run_at_ms,
            "last_status": self.state.last_status,
        }
