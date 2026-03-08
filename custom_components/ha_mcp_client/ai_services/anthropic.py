"""Anthropic Claude AI Service Provider."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

from .base import (
    AIServiceProvider,
    AIResponse,
    Message,
    MessageRole,
    Tool,
    ToolCall,
)

_LOGGER = logging.getLogger(__name__)


class AnthropicService(AIServiceProvider):
    """Anthropic Claude AI service provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Anthropic service."""
        super().__init__(config)
        self._client = None
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "claude-sonnet-4-20250514")

    @property
    def name(self) -> str:
        """Return the name of the AI service."""
        return "Anthropic Claude"

    async def _get_client(self) -> AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                _LOGGER.error("anthropic package not installed")
                raise
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
    ) -> AIResponse:
        """Send a chat request to Anthropic Claude."""
        client = await self._get_client()

        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages(messages)

        # Build request parameters
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
        }

        if system_prompt:
            params["system"] = system_prompt

        if tools:
            params["tools"] = [self._convert_tool_to_anthropic(t) for t in tools]

        try:
            response = await client.messages.create(**params)

            # Parse response
            text_parts = []
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,
                        )
                    )

            content = "\n".join(text_parts)

            return AIResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=response.stop_reason or "stop",
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        except Exception as e:
            _LOGGER.error("Error calling Anthropic API: %s", e)
            raise

    async def validate_config(self) -> bool:
        """Validate the Anthropic configuration."""
        if not self._api_key:
            return False

        try:
            client = await self._get_client()
            # Make a minimal API call to validate
            await client.messages.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except Exception as e:
            _LOGGER.error("Anthropic validation failed: %s", e)
            return False

    async def close(self) -> None:
        """Close the Anthropic client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to Anthropic format.

        Anthropic requires strict user/assistant alternation.
        Consecutive TOOL messages must be merged into a single user message
        with multiple tool_result content blocks.
        """
        anthropic_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # System messages are handled separately in Anthropic
                continue

            if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                # Assistant message with tool calls
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
            elif msg.role == MessageRole.TOOL:
                # Tool result — merge consecutive tool results into one user message
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }
                # Check if the previous message is already a user message with tool_results
                if (
                    anthropic_messages
                    and anthropic_messages[-1]["role"] == "user"
                    and isinstance(anthropic_messages[-1]["content"], list)
                    and anthropic_messages[-1]["content"]
                    and anthropic_messages[-1]["content"][0].get("type") == "tool_result"
                ):
                    # Merge into existing user message
                    anthropic_messages[-1]["content"].append(tool_result_block)
                else:
                    # Start new user message with tool_result
                    anthropic_messages.append({
                        "role": "user",
                        "content": [tool_result_block],
                    })
            elif msg.role == MessageRole.ASSISTANT:
                anthropic_messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                })
            else:
                anthropic_messages.append({
                    "role": msg.role.value,
                    "content": msg.content or "",
                })

        return anthropic_messages

    def _convert_tool_to_anthropic(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool to Anthropic format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
