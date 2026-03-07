"""Base AI Service Provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    """Message role enumeration."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Represents a tool call from the AI."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Represents a tool execution result."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """Represents a conversation message."""

    role: MessageRole
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class Tool:
    """Represents a tool definition for AI."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class AIResponse:
    """Response from AI service."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] | None = None


class AIServiceProvider(ABC):
    """Abstract base class for AI service providers."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the AI service provider."""
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the AI service."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
    ) -> AIResponse:
        """
        Send a chat request to the AI service.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            system_prompt: Optional system prompt

        Returns:
            AIResponse with the AI's response
        """
        pass

    @abstractmethod
    async def validate_config(self) -> bool:
        """
        Validate the service configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        pass

    def _convert_tool_to_dict(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool object to provider-specific format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
