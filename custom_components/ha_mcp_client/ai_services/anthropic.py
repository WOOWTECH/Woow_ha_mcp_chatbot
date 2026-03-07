"""Anthropic Claude AI Service Provider."""

import logging
from typing import Any

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

    async def _get_client(self):
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
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,
                        )
                    )

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

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to Anthropic format."""
        anthropic_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # System messages are handled separately in Anthropic
                continue

            anthropic_msg: dict[str, Any] = {"role": msg.role.value}

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
                anthropic_msg["content"] = content
            elif msg.role == MessageRole.TOOL:
                # Tool result message
                anthropic_msg["role"] = "user"
                anthropic_msg["content"] = [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ]
            else:
                anthropic_msg["content"] = msg.content

            anthropic_messages.append(anthropic_msg)

        return anthropic_messages

    def _convert_tool_to_anthropic(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool to Anthropic format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
