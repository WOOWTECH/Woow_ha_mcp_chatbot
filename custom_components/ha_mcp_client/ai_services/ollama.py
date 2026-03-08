"""Ollama AI Service Provider."""

import json
import logging
from typing import Any

import httpx

from .base import (
    AIServiceProvider,
    AIResponse,
    Message,
    MessageRole,
    Tool,
    ToolCall,
)

_LOGGER = logging.getLogger(__name__)


class OllamaService(AIServiceProvider):
    """Ollama AI service provider for local LLMs."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Ollama service."""
        super().__init__(config)
        self._host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.2")
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """Return the name of the AI service."""
        return "Ollama"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._host,
                timeout=httpx.Timeout(120.0),  # Ollama can be slow
            )
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
    ) -> AIResponse:
        """Send a chat request to Ollama."""
        client = await self._get_client()

        # Convert messages to Ollama format
        ollama_messages = self._convert_messages(messages, system_prompt)

        # Build request payload
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
        }

        # Ollama uses "options" for model parameters
        options: dict[str, Any] = {}
        temperature = self.config.get("temperature")
        if temperature is not None:
            options["temperature"] = temperature
        max_tokens = self.config.get("max_tokens")
        if max_tokens:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        if tools:
            payload["tools"] = [self._convert_tool_to_ollama(t) for t in tools]

        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()

            data = response.json()

            # Parse response
            message = data.get("message", {})
            content = message.get("content", "")
            tool_calls = []

            # Parse tool calls if present
            if message.get("tool_calls"):
                for i, tc in enumerate(message["tool_calls"]):
                    function = tc.get("function", {})
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{i}",
                            name=function.get("name", ""),
                            arguments=function.get("arguments", {}),
                        )
                    )

            return AIResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason="stop",
                usage=None,  # Ollama doesn't provide detailed usage
            )

        except httpx.HTTPStatusError as e:
            _LOGGER.error("Ollama HTTP error: %s", e)
            raise
        except Exception as e:
            _LOGGER.error("Error calling Ollama API: %s", e)
            raise

    async def validate_config(self) -> bool:
        """Validate the Ollama configuration."""
        try:
            client = await self._get_client()

            # Check if Ollama is reachable
            response = await client.get("/api/tags")
            response.raise_for_status()

            # Check if the model is available
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]

            # Model names might include version tags like :latest
            model_base = self._model.split(":")[0]
            for m in models:
                if m.startswith(model_base):
                    return True

            _LOGGER.warning(
                "Model %s not found in Ollama. Available models: %s",
                self._model,
                models,
            )
            # Return True anyway - user might pull the model later
            return True

        except Exception as e:
            _LOGGER.error("Ollama validation failed: %s", e)
            return False

    def _convert_messages(
        self, messages: list[Message], system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """Convert messages to Ollama format."""
        ollama_messages = []

        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                ollama_messages.append({"role": "system", "content": msg.content})
            elif msg.role == MessageRole.USER:
                ollama_messages.append({"role": "user", "content": msg.content})
            elif msg.role == MessageRole.ASSISTANT:
                ollama_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }
                if msg.tool_calls:
                    ollama_msg["tool_calls"] = [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                ollama_messages.append(ollama_msg)
            elif msg.role == MessageRole.TOOL:
                ollama_messages.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                    }
                )

        return ollama_messages

    def _convert_tool_to_ollama(self, tool: Tool) -> dict[str, Any]:
        """Convert a Tool to Ollama format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
