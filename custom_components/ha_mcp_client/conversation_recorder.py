"""Conversation Recorder for HA MCP Client (display-only log).

This recorder stores user/assistant messages in the HA recorder DB purely
for the chat panel to display history.  It is NOT the memory authority —
n8n's Simple Memory node owns that role.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.recorder import get_instance
from homeassistant.helpers.event import async_track_time_interval

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import declarative_base, Session

from .const import (
    CONF_ENABLE_CONVERSATION_HISTORY,
    CONF_HISTORY_RETENTION_DAYS,
    DEFAULT_HISTORY_RETENTION_DAYS,
)

_LOGGER = logging.getLogger(__name__)

Base = declarative_base()


def _utc_iso(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with 'Z' suffix.

    SQLAlchemy's DateTime column strips tzinfo, so naive datetimes from the DB
    are actually UTC.  Appending 'Z' tells JavaScript's ``new Date()`` to parse
    them as UTC instead of local time.
    """
    s = dt.isoformat()
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    elif not s.endswith("Z"):
        s += "Z"
    return s


class ConversationMessage(Base):
    """Model for conversation messages."""

    __tablename__ = "ha_mcp_client_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=True, index=True)
    conversation_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)
    tool_results = Column(Text, nullable=True)
    extra_data = Column(Text, nullable=True)


class Conversation(Base):
    """Model for conversations (groups of messages)."""

    __tablename__ = "ha_mcp_client_conversations"

    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="\u65b0\u5c0d\u8a71")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, index=True)
    is_archived = Column(Boolean, nullable=False, default=False)


class ConversationRecorder:
    """Handles recording conversation history (display-only)."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self._enabled = config.get(CONF_ENABLE_CONVERSATION_HISTORY, True)
        self._retention_days = config.get(
            CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS
        )
        self._unsub_cleanup = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="McpDb")

    async def _run_in_executor(self, func):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func)

    async def async_setup(self) -> None:
        if not self._enabled:
            return
        await self._create_tables()
        self._unsub_cleanup = async_track_time_interval(
            self.hass, self._cleanup_old_records, timedelta(hours=24)
        )

    async def async_unload(self) -> None:
        if self._unsub_cleanup:
            self._unsub_cleanup()
            self._unsub_cleanup = None
        self._executor.shutdown(wait=False)

    async def _create_tables(self) -> None:
        recorder = get_instance(self.hass)

        def _create():
            engine = recorder.engine
            if engine is not None:
                Base.metadata.create_all(
                    engine,
                    tables=[ConversationMessage.__table__, Conversation.__table__],
                    checkfirst=True,
                )

        await recorder.async_add_executor_job(_create)

    # ── Public API used by views.py ───────────────────────────

    async def record_message(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Record a user + assistant exchange."""
        if not self._enabled:
            return

        recorder = get_instance(self.hass)
        if recorder.engine is None:
            _LOGGER.warning("Recorder engine not available, message not persisted")
            return

        timestamp = datetime.now(timezone.utc)

        def _record():
            engine = recorder.engine
            if engine is None:
                _LOGGER.warning("Recorder engine disappeared during record")
                return
            with Session(engine) as session:
                if user_message:
                    session.add(
                        ConversationMessage(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            timestamp=timestamp,
                            role="user",
                            content=user_message,
                        )
                    )
                if assistant_message:
                    session.add(
                        ConversationMessage(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            timestamp=timestamp + timedelta(microseconds=1),
                            role="assistant",
                            content=assistant_message,
                        )
                    )
                session.commit()

        try:
            await self._run_in_executor(_record)
        except Exception as e:
            _LOGGER.error("Error recording conversation: %s", e, exc_info=True)

    async def record_single(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """Record a single message (user OR assistant)."""
        if not self._enabled or not content:
            return

        recorder = get_instance(self.hass)
        if recorder.engine is None:
            _LOGGER.warning("Recorder engine not available")
            return

        timestamp = datetime.now(timezone.utc)

        def _write():
            engine = recorder.engine
            if engine is None:
                return
            with Session(engine) as session:
                session.add(
                    ConversationMessage(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        timestamp=timestamp,
                        role=role,
                        content=content,
                    )
                )
                session.commit()

        try:
            await self._run_in_executor(_write)
        except Exception as e:
            _LOGGER.error("Error recording %s message: %s", role, e, exc_info=True)

    # ── Conversation CRUD ─────────────────────────────────────

    async def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        recorder = get_instance(self.hass)

        def _list():
            with Session(recorder.engine) as session:
                rows = (
                    session.query(Conversation)
                    .filter(
                        Conversation.user_id == user_id,
                        Conversation.is_archived == False,  # noqa: E712
                    )
                    .order_by(Conversation.updated_at.desc())
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "title": r.title,
                        "created_at": _utc_iso(r.created_at),
                        "updated_at": _utc_iso(r.updated_at),
                    }
                    for r in rows
                ]

        try:
            return await self._run_in_executor(_list)
        except Exception as e:
            _LOGGER.error("Error listing conversations: %s", e)
            return []

    async def create_conversation(
        self, conversation_id: str, user_id: str, title: str = "\u65b0\u5c0d\u8a71"
    ) -> dict[str, Any]:
        recorder = get_instance(self.hass)
        now = datetime.now(timezone.utc)

        def _create():
            with Session(recorder.engine) as session:
                session.add(
                    Conversation(
                        id=conversation_id,
                        user_id=user_id,
                        title=title,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.commit()

        try:
            await self._run_in_executor(_create)
            return {
                "id": conversation_id,
                "title": title,
                "created_at": _utc_iso(now),
                "updated_at": _utc_iso(now),
            }
        except Exception as e:
            _LOGGER.error("Error creating conversation: %s", e)
            return {}

    async def update_conversation(
        self,
        conversation_id: str,
        user_id: str,
        title: str | None = None,
        is_archived: bool | None = None,
    ) -> bool:
        recorder = get_instance(self.hass)

        def _update():
            with Session(recorder.engine) as session:
                conv = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .first()
                )
                if not conv:
                    return False
                if title is not None:
                    conv.title = title
                if is_archived is not None:
                    conv.is_archived = is_archived
                conv.updated_at = datetime.now(timezone.utc)
                session.commit()
                return True

        try:
            return await self._run_in_executor(_update)
        except Exception as e:
            _LOGGER.error("Error updating conversation: %s", e)
            return False

    async def touch_conversation(self, conversation_id: str) -> None:
        recorder = get_instance(self.hass)

        def _touch():
            with Session(recorder.engine) as session:
                conv = (
                    session.query(Conversation)
                    .filter(Conversation.id == conversation_id)
                    .first()
                )
                if conv:
                    conv.updated_at = datetime.now(timezone.utc)
                    session.commit()

        try:
            await self._run_in_executor(_touch)
        except Exception as e:
            _LOGGER.error("Error touching conversation: %s", e)

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> dict[str, Any] | None:
        recorder = get_instance(self.hass)

        def _get():
            with Session(recorder.engine) as session:
                conv = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .first()
                )
                if not conv:
                    return None
                return {
                    "id": conv.id,
                    "title": conv.title,
                    "created_at": _utc_iso(conv.created_at),
                    "updated_at": _utc_iso(conv.updated_at),
                    "is_archived": conv.is_archived,
                }

        try:
            return await self._run_in_executor(_get)
        except Exception as e:
            _LOGGER.error("Error getting conversation: %s", e)
            return None

    async def get_conversation_messages(
        self, conversation_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        recorder = get_instance(self.hass)

        def _get_msgs():
            with Session(recorder.engine) as session:
                query = (
                    session.query(ConversationMessage)
                    .filter(ConversationMessage.conversation_id == conversation_id)
                    .order_by(ConversationMessage.timestamp.asc())
                )
                if offset:
                    query = query.offset(offset)
                query = query.limit(limit)

                return [
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": _utc_iso(msg.timestamp),
                    }
                    for msg in query.all()
                ]

        try:
            return await self._run_in_executor(_get_msgs)
        except Exception as e:
            _LOGGER.error("Error getting conversation messages: %s", e)
            return []

    # ── History management ────────────────────────────────────

    async def clear_conversation_history(
        self, user_id: str | None = None, conversation_id: str | None = None
    ) -> int:
        if not user_id and not conversation_id:
            return 0
        recorder = get_instance(self.hass)

        def _clear():
            with Session(recorder.engine) as session:
                query = session.query(ConversationMessage)
                if user_id:
                    query = query.filter(ConversationMessage.user_id == user_id)
                if conversation_id:
                    query = query.filter(
                        ConversationMessage.conversation_id == conversation_id
                    )
                deleted = query.delete()
                session.commit()
                return deleted

        try:
            return await self._run_in_executor(_clear)
        except Exception as e:
            _LOGGER.error("Error clearing conversation history: %s", e)
            return 0

    async def export_conversation_history(
        self, user_id: str | None = None, format: str = "json"
    ) -> str:
        recorder = get_instance(self.hass)

        def _export():
            with Session(recorder.engine) as session:
                query = session.query(ConversationMessage)
                if user_id:
                    query = query.filter(ConversationMessage.user_id == user_id)
                query = query.order_by(ConversationMessage.timestamp.desc()).limit(1000)
                rows = query.all()
                return [
                    {
                        "conversation_id": m.conversation_id,
                        "timestamp": _utc_iso(m.timestamp),
                        "role": m.role,
                        "content": m.content,
                    }
                    for m in rows
                ]

        try:
            history = await self._run_in_executor(_export)
        except Exception as e:
            _LOGGER.error("Error exporting history: %s", e)
            return ""

        if format == "json":
            return json.dumps(history, indent=2, default=str)

        # Markdown
        lines = ["# Conversation History\n"]
        current_conv = None
        for msg in reversed(history):
            if msg["conversation_id"] != current_conv:
                current_conv = msg["conversation_id"]
                lines.append(f"\n## Conversation: {current_conv}\n")
            lines.append(f"**{msg['role'].capitalize()}** ({msg['timestamp']}):\n")
            lines.append(f"{msg['content']}\n")
        return "\n".join(lines)

    async def _cleanup_old_records(self, _now: datetime) -> None:
        if not self._enabled:
            return
        recorder = get_instance(self.hass)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)

        def _cleanup():
            with Session(recorder.engine) as session:
                deleted = (
                    session.query(ConversationMessage)
                    .filter(ConversationMessage.timestamp < cutoff)
                    .delete()
                )
                session.commit()
                return deleted

        try:
            deleted = await self._run_in_executor(_cleanup)
            if deleted:
                _LOGGER.info("Cleaned up %d old conversation records", deleted)
        except Exception as e:
            _LOGGER.error("Error cleaning up old records: %s", e)
