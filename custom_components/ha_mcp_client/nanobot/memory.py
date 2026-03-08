"""Memory system for persistent agent memory.

Adapted from nanobot's agent/memory.py to work within Home Assistant.
Two-layer architecture:
  - MEMORY.md: Long-term facts (always in system prompt context)
  - HISTORY.md: Append-only timestamped log (grep-searchable, NOT in context)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from ..ai_services.base import AIServiceProvider

_LOGGER = logging.getLogger(__name__)

# Tool schema for the memory consolidation LLM call
_SAVE_MEMORY_TOOL_SCHEMA = {
    "name": "save_memory",
    "description": "Save the memory consolidation result to persistent storage.",
    "input_schema": {
        "type": "object",
        "properties": {
            "history_entry": {
                "type": "string",
                "description": (
                    "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                    "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search."
                ),
            },
            "memory_update": {
                "type": "string",
                "description": (
                    "Full updated long-term memory as markdown. Include all existing "
                    "facts plus new ones. Return unchanged if nothing new."
                ),
            },
        },
        "required": ["history_entry", "memory_update"],
    },
}

_CONSOLIDATION_SYSTEM_PROMPT = (
    "You are a memory consolidation agent. "
    "Call the save_memory tool with your consolidation of the conversation."
)

# Default templates
DEFAULT_SOUL = """# Soul

I am a personal AI assistant integrated with Home Assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Proactive in smart home management

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions

## Communication Style

- Be clear and direct
- Explain reasoning when helpful
- Ask clarifying questions when needed
- Respond in the user's language
"""

DEFAULT_USER = """# User Profile

Information about the user to help personalize interactions.

## Basic Information

- **Name**: (your name)
- **Timezone**: (your timezone, e.g., UTC+8)
- **Language**: (preferred language)

## Preferences

- Communication style: Adaptive
- Response length: Concise but complete
- Technical level: Intermediate

## Work Context

- **Primary Use**: Smart home management
- **Main Interests**: Home automation, device control

## Special Instructions

(Edit this file to customize the assistant's behavior for your needs.)
"""


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log).

    All file I/O is performed via hass.async_add_executor_job to avoid
    blocking the HA event loop.
    """

    def __init__(self, hass: HomeAssistant, config_dir: Path) -> None:
        """Initialize the memory store.

        Args:
            hass: Home Assistant instance
            config_dir: Path to the nanobot config directory (e.g., config/nanobot)
        """
        self.hass = hass
        self._config_dir = config_dir
        self._memory_dir = config_dir / "memory"
        self._memory_file = self._memory_dir / "MEMORY.md"
        self._history_file = self._memory_dir / "HISTORY.md"
        self._soul_file = config_dir / "SOUL.md"
        self._user_file = config_dir / "USER.md"

        # Consolidation tracking (per conversation)
        self._last_consolidated: dict[str, int] = {}
        self._last_consolidation_time: datetime | None = None

    async def async_setup(self) -> None:
        """Initialize directories and default files."""
        await self.hass.async_add_executor_job(self._setup_files)
        _LOGGER.info("MemoryStore initialized at %s", self._config_dir)

    def _setup_files(self) -> None:
        """Create directories and default files if they don't exist (sync)."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        if not self._memory_file.exists():
            self._memory_file.write_text("", encoding="utf-8")

        if not self._history_file.exists():
            self._history_file.write_text("", encoding="utf-8")

        if not self._soul_file.exists():
            self._soul_file.write_text(DEFAULT_SOUL, encoding="utf-8")

        if not self._user_file.exists():
            self._user_file.write_text(DEFAULT_USER, encoding="utf-8")

    # ── File read/write (all async via executor) ──

    async def read_long_term(self) -> str:
        """Read MEMORY.md content."""
        return await self.hass.async_add_executor_job(self._read_file, self._memory_file)

    async def write_long_term(self, content: str) -> None:
        """Overwrite MEMORY.md with new content."""
        await self.hass.async_add_executor_job(self._write_file, self._memory_file, content)

    async def append_history(self, entry: str) -> None:
        """Append an entry to HISTORY.md."""
        await self.hass.async_add_executor_job(self._append_file, self._history_file, entry)

    async def read_history(self) -> str:
        """Read HISTORY.md content."""
        return await self.hass.async_add_executor_job(self._read_file, self._history_file)

    async def read_soul(self) -> str:
        """Read SOUL.md content."""
        return await self.hass.async_add_executor_job(self._read_file, self._soul_file)

    async def write_soul(self, content: str) -> None:
        """Write SOUL.md content."""
        await self.hass.async_add_executor_job(self._write_file, self._soul_file, content)

    async def read_user(self) -> str:
        """Read USER.md content."""
        return await self.hass.async_add_executor_job(self._read_file, self._user_file)

    async def write_user(self, content: str) -> None:
        """Write USER.md content."""
        await self.hass.async_add_executor_job(self._write_file, self._user_file, content)

    async def search_history(self, pattern: str) -> list[str]:
        """Search HISTORY.md for entries matching a regex pattern.

        Returns a list of matching lines.
        """
        return await self.hass.async_add_executor_job(self._search_history, pattern)

    # ── Context building ──

    async def get_memory_context(self) -> str:
        """Build the memory context string for injection into system prompt.

        Returns a formatted string containing MEMORY.md, SOUL.md, and USER.md content.
        """
        parts = []

        soul = await self.read_soul()
        if soul.strip():
            parts.append(soul.strip())

        user = await self.read_user()
        if user.strip():
            parts.append(user.strip())

        memory = await self.read_long_term()
        if memory.strip():
            parts.append(f"## Long-term Memory\n{memory.strip()}")

        return "\n\n---\n\n".join(parts) if parts else ""

    # ── Consolidation ──

    async def should_consolidate(
        self,
        conversation_id: str,
        message_count: int,
        memory_window: int = 50,
    ) -> bool:
        """Check if memory consolidation should be triggered.

        Args:
            conversation_id: Current conversation ID
            message_count: Current number of messages in the conversation
            memory_window: Threshold for triggering consolidation (default 50)
        """
        last = self._last_consolidated.get(conversation_id, 0)
        keep_count = memory_window // 2
        if message_count <= keep_count:
            return False
        unconsolidated = message_count - last
        return unconsolidated > keep_count

    async def consolidate(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
        ai_service: AIServiceProvider,
        memory_window: int = 50,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call.

        Args:
            conversation_id: Conversation ID for tracking
            messages: List of message dicts with role, content, timestamp, tool_calls
            ai_service: The AI service provider to use for consolidation
            memory_window: Window size for consolidation

        Returns True on success (including no-op), False on failure.
        """
        from ..ai_services import Message, MessageRole, Tool

        keep_count = memory_window // 2
        last = self._last_consolidated.get(conversation_id, 0)

        if len(messages) <= keep_count:
            return True

        old_messages = messages[last:-keep_count] if keep_count > 0 else messages[last:]
        if not old_messages:
            return True

        _LOGGER.info(
            "Memory consolidation: %d messages to consolidate, keeping %d",
            len(old_messages),
            keep_count,
        )

        # Format old messages as timestamped text
        lines = []
        for m in old_messages:
            role = m.get("role", "unknown").upper()
            content = m.get("content", "")
            if not content:
                continue
            ts = m.get("timestamp", "?")[:16]
            tools = ""
            if m.get("tool_calls"):
                tool_names = [tc.get("name", "?") for tc in m["tool_calls"]]
                tools = f" [tools: {', '.join(tool_names)}]"
            lines.append(f"[{ts}] {role}{tools}: {content}")

        if not lines:
            return True

        current_memory = await self.read_long_term()

        prompt = (
            "Process this conversation and call the save_memory tool "
            "with your consolidation.\n\n"
            f"## Current Long-term Memory\n{current_memory or '(empty)'}\n\n"
            f"## Conversation to Process\n" + "\n".join(lines)
        )

        # Build the tool and messages for the consolidation call
        save_tool = Tool(
            name="save_memory",
            description=_SAVE_MEMORY_TOOL_SCHEMA["description"],
            input_schema=_SAVE_MEMORY_TOOL_SCHEMA["input_schema"],
        )

        consolidation_messages = [
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = await ai_service.chat(
                messages=consolidation_messages,
                tools=[save_tool],
                system_prompt=_CONSOLIDATION_SYSTEM_PROMPT,
            )

            if not response.tool_calls:
                _LOGGER.warning(
                    "Memory consolidation: LLM did not call save_memory, skipping"
                )
                return False

            # Extract arguments from the first tool call
            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)

            history_entry = args.get("history_entry", "")
            memory_update = args.get("memory_update", "")

            if history_entry:
                if not isinstance(history_entry, str):
                    history_entry = json.dumps(history_entry, ensure_ascii=False)
                await self.append_history(history_entry)

            if memory_update:
                if not isinstance(memory_update, str):
                    memory_update = json.dumps(memory_update, ensure_ascii=False)
                if memory_update != current_memory:
                    await self.write_long_term(memory_update)

            # Update tracking
            self._last_consolidated[conversation_id] = (
                len(messages) - keep_count if keep_count > 0 else len(messages)
            )
            self._last_consolidation_time = datetime.now()

            _LOGGER.info(
                "Memory consolidation done for %s: last_consolidated=%d",
                conversation_id,
                self._last_consolidated[conversation_id],
            )
            return True

        except Exception:
            _LOGGER.exception("Memory consolidation failed")
            return False

    # ── Statistics ──

    async def get_stats(self) -> dict[str, Any]:
        """Get memory statistics for sensor entities."""
        memory = await self.read_long_term()
        history = await self.read_history()

        # Count memory entries (non-empty lines that look like content)
        memory_lines = [l for l in memory.split("\n") if l.strip() and not l.startswith("#")]
        memory_entries = len(memory_lines)

        # Count history entries (paragraphs starting with [YYYY-MM-DD])
        history_entries = len(re.findall(r"^\[20\d{2}-\d{2}-\d{2}", history, re.MULTILINE))

        return {
            "memory_entries": memory_entries,
            "history_entries": history_entries,
            "last_consolidation": (
                self._last_consolidation_time.isoformat()
                if self._last_consolidation_time
                else None
            ),
            "memory_file": str(self._memory_file),
            "history_file": str(self._history_file),
        }

    # ── Sync file helpers ──

    @staticmethod
    def _read_file(path: Path) -> str:
        """Read file content (sync, run via executor)."""
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _write_file(path: Path, content: str) -> None:
        """Write file content (sync, run via executor)."""
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _append_file(path: Path, entry: str) -> None:
        """Append entry to file (sync, run via executor)."""
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def _search_history(self, pattern: str) -> list[str]:
        """Search HISTORY.md with regex (sync, run via executor)."""
        if not self._history_file.exists():
            return []
        content = self._history_file.read_text(encoding="utf-8")
        try:
            return [
                line for line in content.split("\n")
                if line.strip() and re.search(pattern, line, re.IGNORECASE)
            ]
        except re.error as e:
            _LOGGER.warning("Invalid search pattern '%s': %s", pattern, e)
            return []
