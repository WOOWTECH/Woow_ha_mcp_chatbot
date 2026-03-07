"""Conversation Recorder for HA MCP Client."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.components.recorder import get_instance
from homeassistant.helpers.event import async_track_time_interval

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import declarative_base, Session

from .const import (
    DOMAIN,
    CONF_ENABLE_CONVERSATION_HISTORY,
    CONF_HISTORY_RETENTION_DAYS,
    DEFAULT_HISTORY_RETENTION_DAYS,
)

_LOGGER = logging.getLogger(__name__)

Base = declarative_base()


class ConversationMessage(Base):
    """Model for conversation messages."""

    __tablename__ = "ha_mcp_client_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=True, index=True)
    conversation_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, tool
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)  # JSON
    tool_results = Column(Text, nullable=True)  # JSON
    extra_data = Column(Text, nullable=True)  # JSON (renamed from metadata which is reserved)


class Conversation(Base):
    """Model for conversations (groups of messages)."""

    __tablename__ = "ha_mcp_client_conversations"

    id = Column(String(255), primary_key=True)  # UUID
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="新對話")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, index=True)
    is_archived = Column(Boolean, nullable=False, default=False)


class ConversationRecorder:
    """Handles recording conversation history."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
    ) -> None:
        """Initialize the conversation recorder."""
        self.hass = hass
        self._config = config
        self._enabled = config.get(CONF_ENABLE_CONVERSATION_HISTORY, True)
        self._retention_days = config.get(
            CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS
        )
        self._unsub_listener = None
        self._unsub_cleanup = None

    async def async_setup(self) -> None:
        """Set up the conversation recorder."""
        if not self._enabled:
            _LOGGER.debug("Conversation history is disabled")
            return

        # Create tables
        await self._create_tables()

        # Listen for conversation events
        self._unsub_listener = self.hass.bus.async_listen(
            f"{DOMAIN}_conversation_message",
            self._handle_conversation_event,
        )

        # Schedule periodic cleanup
        self._unsub_cleanup = async_track_time_interval(
            self.hass,
            self._cleanup_old_records,
            timedelta(hours=24),
        )

        _LOGGER.info("Conversation recorder initialized")

    async def async_unload(self) -> None:
        """Unload the conversation recorder."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

        if self._unsub_cleanup:
            self._unsub_cleanup()
            self._unsub_cleanup = None

    async def _create_tables(self) -> None:
        """Create database tables."""
        recorder = get_instance(self.hass)

        def _create():
            # Get engine from recorder and create tables
            engine = recorder.engine
            if engine is not None:
                Base.metadata.create_all(
                    engine,
                    tables=[
                        ConversationMessage.__table__,
                        Conversation.__table__,
                    ],
                    checkfirst=True,
                )

        await recorder.async_add_executor_job(_create)

    @callback
    def _handle_conversation_event(self, event: Event) -> None:
        """Handle conversation event."""
        self.hass.async_create_task(self._record_message(event.data))

    async def _record_message(self, data: dict[str, Any]) -> None:
        """Record a conversation message."""
        _LOGGER.debug("Recording message event received: user_id=%s", data.get("user_id"))

        if not self._enabled:
            _LOGGER.debug("Conversation history is disabled, skipping recording")
            return

        recorder = get_instance(self.hass)

        user_id = data.get("user_id")
        conversation_id = data.get("conversation_id")
        user_message = data.get("user_message")
        assistant_message = data.get("assistant_message")
        tool_calls = data.get("tool_calls")
        tool_results = data.get("tool_results")

        # Use UTC timestamp
        timestamp = datetime.now(timezone.utc)

        def _record():
            _LOGGER.debug("Executing database record operation")
            with Session(recorder.engine) as session:
                # Record user message
                if user_message:
                    user_msg = ConversationMessage(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        timestamp=timestamp,
                        role="user",
                        content=user_message,
                    )
                    session.add(user_msg)
                    _LOGGER.debug("Added user message to session")

                # Record assistant message with a slight offset to preserve ordering
                if assistant_message:
                    assistant_timestamp = timestamp + timedelta(microseconds=1)
                    assistant_msg = ConversationMessage(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        timestamp=assistant_timestamp,
                        role="assistant",
                        content=assistant_message,
                        tool_calls=json.dumps(tool_calls) if tool_calls else None,
                        tool_results=json.dumps(tool_results) if tool_results else None,
                    )
                    session.add(assistant_msg)
                    _LOGGER.debug("Added assistant message to session")

                session.commit()
                _LOGGER.debug("Successfully committed conversation to database")

        try:
            await recorder.async_add_executor_job(_record)
        except Exception as e:
            _LOGGER.error("Error recording conversation: %s", e, exc_info=True)

    # ── Conversation CRUD ──────────────────────────────────────

    async def list_conversations(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """List all non-archived conversations for a user, newest first."""
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
                        "created_at": r.created_at.isoformat(),
                        "updated_at": r.updated_at.isoformat(),
                    }
                    for r in rows
                ]

        try:
            return await recorder.async_add_executor_job(_list)
        except Exception as e:
            _LOGGER.error("Error listing conversations: %s", e)
            return []

    async def create_conversation(
        self,
        conversation_id: str,
        user_id: str,
        title: str = "新對話",
    ) -> dict[str, Any]:
        """Create a new conversation."""
        recorder = get_instance(self.hass)
        now = datetime.now(timezone.utc)

        def _create():
            with Session(recorder.engine) as session:
                conv = Conversation(
                    id=conversation_id,
                    user_id=user_id,
                    title=title,
                    created_at=now,
                    updated_at=now,
                )
                session.add(conv)
                session.commit()

        try:
            await recorder.async_add_executor_job(_create)
            return {
                "id": conversation_id,
                "title": title,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
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
        """Update a conversation's title or archive status."""
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
            return await recorder.async_add_executor_job(_update)
        except Exception as e:
            _LOGGER.error("Error updating conversation: %s", e)
            return False

    async def touch_conversation(
        self,
        conversation_id: str,
    ) -> None:
        """Update the updated_at timestamp for a conversation."""
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
            await recorder.async_add_executor_job(_touch)
        except Exception as e:
            _LOGGER.error("Error touching conversation: %s", e)

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Get a single conversation by ID, verifying ownership."""
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
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat(),
                    "is_archived": conv.is_archived,
                }

        try:
            return await recorder.async_add_executor_job(_get)
        except Exception as e:
            _LOGGER.error("Error getting conversation: %s", e)
            return None

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get messages for a specific conversation, oldest first."""
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

                results = []
                for msg in query.all():
                    parsed_tool_calls = None
                    if msg.tool_calls:
                        try:
                            parsed_tool_calls = json.loads(msg.tool_calls)
                        except (json.JSONDecodeError, TypeError):
                            pass

                    parsed_tool_results = None
                    if msg.tool_results:
                        try:
                            parsed_tool_results = json.loads(msg.tool_results)
                        except (json.JSONDecodeError, TypeError):
                            pass

                    results.append(
                        {
                            "id": msg.id,
                            "role": msg.role,
                            "content": msg.content,
                            "timestamp": msg.timestamp.isoformat(),
                            "tool_calls": parsed_tool_calls,
                            "tool_results": parsed_tool_results,
                        }
                    )
                return results

        try:
            return await recorder.async_add_executor_job(_get_msgs)
        except Exception as e:
            _LOGGER.error("Error getting conversation messages: %s", e)
            return []

    async def _cleanup_old_records(self, _now: datetime) -> None:
        """Clean up old conversation records."""
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
            deleted = await recorder.async_add_executor_job(_cleanup)
            if deleted:
                _LOGGER.info("Cleaned up %d old conversation records", deleted)
        except Exception as e:
            _LOGGER.error("Error cleaning up old records: %s", e)

    async def get_conversation_history(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get conversation history."""
        recorder = get_instance(self.hass)

        def _get_history():
            with Session(recorder.engine) as session:
                query = session.query(ConversationMessage)

                if user_id:
                    query = query.filter(ConversationMessage.user_id == user_id)
                if conversation_id:
                    query = query.filter(
                        ConversationMessage.conversation_id == conversation_id
                    )
                if start_time:
                    query = query.filter(ConversationMessage.timestamp >= start_time)
                if end_time:
                    query = query.filter(ConversationMessage.timestamp <= end_time)

                query = query.order_by(ConversationMessage.timestamp.desc())
                query = query.limit(limit)

                results = []
                for msg in query.all():
                    # Safely parse JSON fields
                    parsed_tool_calls = None
                    if msg.tool_calls:
                        try:
                            parsed_tool_calls = json.loads(msg.tool_calls)
                        except (json.JSONDecodeError, TypeError):
                            _LOGGER.warning("Corrupt tool_calls JSON in record %d", msg.id)

                    parsed_tool_results = None
                    if msg.tool_results:
                        try:
                            parsed_tool_results = json.loads(msg.tool_results)
                        except (json.JSONDecodeError, TypeError):
                            _LOGGER.warning("Corrupt tool_results JSON in record %d", msg.id)

                    results.append(
                        {
                            "id": msg.id,
                            "user_id": msg.user_id,
                            "conversation_id": msg.conversation_id,
                            "timestamp": msg.timestamp.isoformat(),
                            "role": msg.role,
                            "content": msg.content,
                            "tool_calls": parsed_tool_calls,
                            "tool_results": parsed_tool_results,
                        }
                    )

                return results

        try:
            return await recorder.async_add_executor_job(_get_history)
        except Exception as e:
            _LOGGER.error("Error getting conversation history: %s", e)
            return []

    async def clear_conversation_history(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> int:
        """Clear conversation history.

        At least one of user_id or conversation_id must be provided
        to prevent accidental deletion of all records.
        """
        if not user_id and not conversation_id:
            _LOGGER.error("clear_conversation_history called without user_id or conversation_id")
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
            return await recorder.async_add_executor_job(_clear)
        except Exception as e:
            _LOGGER.error("Error clearing conversation history: %s", e)
            return 0

    async def export_conversation_history(
        self,
        user_id: str | None = None,
        format: str = "json",
    ) -> str:
        """Export conversation history."""
        history = await self.get_conversation_history(
            user_id=user_id, limit=1000
        )

        if format == "json":
            return json.dumps(history, indent=2, default=str)

        elif format == "markdown":
            lines = ["# Conversation History\n"]

            current_conv = None
            for msg in reversed(history):
                if msg["conversation_id"] != current_conv:
                    current_conv = msg["conversation_id"]
                    lines.append(f"\n## Conversation: {current_conv}\n")

                role = msg["role"].capitalize()
                timestamp = msg["timestamp"]
                content = msg["content"]

                lines.append(f"**{role}** ({timestamp}):\n")
                lines.append(f"{content}\n")

                if msg.get("tool_calls"):
                    lines.append(f"*Tool calls: {json.dumps(msg['tool_calls'])}*\n")

            return "\n".join(lines)

        return ""
