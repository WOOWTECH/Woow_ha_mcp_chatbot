"""OpenAI AI Service Provider."""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from .base import (
    AIServiceProvider,
    AIResponse,
    Message,
    MessageRole,
    Tool,
    ToolCall,
)

_LOGGER = logging.getLogger(__name__)


class OpenAIService(AIServiceProvider):
    """OpenAI AI service provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize OpenAI service."""
        super().__init__(config)
        self._client = None
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "gpt-4-turbo")
        self._base_url = config.get("base_url")

    @property
    def name(self) -> str:
        """Return the name of the AI service."""
        return "OpenAI"

    async def _get_client(self) -> AsyncOpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                kwargs: dict[str, Any] = {"api_key": self._api_key}
                if self._base_url:
                    kwargs["base_url"] = self._base_url

                self._client = AsyncOpenAI(**kwargs)
            except ImportError:
                _LOGGER.error("openai package not installed")
                raise
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
    ) -> AIResponse:
        """Send a chat request to OpenAI."""
        client = await self._get_client()

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages, system_prompt)

        # Debug logging
        _LOGGER.debug(
            "OpenAI request - model: %s, system_prompt_len: %d, messages: %d, tools: %d",
            self._model,
            len(system_prompt) if system_prompt else 0,
            len(openai_messages),
            len(tools) if tools else 0,
        )
        if system_prompt:
            _LOGGER.debug("System prompt preview: %s...", system_prompt[:500])

        # Build request parameters
        params: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }

        max_tokens = self.config.get("max_tokens")
        if max_tokens:
            # Newer OpenAI models (o1, o3, gpt-5, etc.) require
            # max_completion_tokens instead of max_tokens.
            if self._is_reasoning_model():
                params["max_completion_tokens"] = max_tokens
            else:
                params["max_tokens"] = max_tokens
        temperature = self.config.get("temperature")
        if temperature is not None:
            # Reasoning models only support temperature=1
            if not self._is_reasoning_model():
                params["temperature"] = temperature

        # Reasoning effort for reasoning models (o1, o3, gpt-5, etc.)
        if self._is_reasoning_model():
            reasoning_effort = self.config.get("reasoning_effort")
            if reasoning_effort and reasoning_effort in ("low", "medium", "high"):
                params["reasoning_effort"] = reasoning_effort

        if tools:
            params["tools"] = [self._convert_tool_to_openai(t) for t in tools]
            params["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**params)

            # Parse response
            choice = response.choices[0]
            message = choice.message

            content = message.content or ""
            tool_calls = []

            if message.tool_calls:
                for i, tc in enumerate(message.tool_calls):
                    try:
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError) as parse_err:
                        _LOGGER.warning(
                            "Failed to parse tool call arguments for %s: %s",
                            tc.function.name,
                            parse_err,
                        )
                        args = {}
                    # Guard against null tool_call.id (some OpenAI-compatible APIs)
                    tc_id = tc.id or f"call_{i}"
                    _LOGGER.debug(
                        "OpenAI tool call: %s (id=%s) with args: %s",
                        tc.function.name,
                        tc_id,
                        args,
                    )
                    tool_calls.append(
                        ToolCall(
                            id=tc_id,
                            name=tc.function.name,
                            arguments=args,
                        )
                    )

            return AIResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "stop",
                usage={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                }
                if response.usage
                else None,
            )

        except Exception as e:
            _LOGGER.error("Error calling OpenAI API: %s", e)
            raise

    async def validate_config(self) -> bool:
        """Validate the OpenAI configuration."""
        if not self._api_key:
            return False

        try:
            client = await self._get_client()
            # Make a minimal API call to validate
            validate_params: dict[str, Any] = {
                "model": self._model,
                "messages": [{"role": "user", "content": "test"}],
            }
            if self._is_reasoning_model():
                validate_params["max_completion_tokens"] = 10
            else:
                validate_params["max_tokens"] = 10
            await client.chat.completions.create(**validate_params)
            return True
        except Exception as e:
            _LOGGER.error("OpenAI validation failed: %s", e)
            return False

    async def close(self) -> None:
        """Close the OpenAI client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _is_reasoning_model(self) -> bool:
        """Check if the model is a reasoning model with restricted parameters."""
        model = self._model.lower()
        # Models that require max_completion_tokens:
        # o1, o3, gpt-5 series, and any future models
        for prefix in ("o1", "o3", "o4", "gpt-5", "gpt-6"):
            if model.startswith(prefix):
                return True
        return False

    def _convert_messages(
        self, messages: list[Message], system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """Convert messages to OpenAI format."""
        openai_messages = []

        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == MessageRole.USER:
                openai_messages.append({"role": "user", "content": msg.content})
            elif msg.role == MessageRole.ASSISTANT:
                openai_msg: dict[str, Any] = {
                    "role": "assistant",
                    # OpenAI-compatible APIs (e.g. Gemini) may reject empty
                    # string content when tool_calls are present; use None.
                    "content": msg.content or None,
                }
                if msg.tool_calls:
                    openai_msg["tool_calls"] = [
                        {
                            "id": tc.id or f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for i, tc in enumerate(msg.tool_calls)
                    ]
                openai_messages.append(openai_msg)
            elif msg.role == MessageRole.TOOL:
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return openai_messages

    def _convert_tool_to_openai(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool to OpenAI format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
