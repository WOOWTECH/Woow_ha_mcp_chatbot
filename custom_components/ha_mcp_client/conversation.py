"""Conversation Entity for HA MCP Client."""

import json
import logging
from collections import OrderedDict
from typing import Any

from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationInput,
    ConversationResult,
)
from homeassistant.components.conversation.const import ConversationEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.intent import IntentResponse

from .const import (
    DOMAIN,
    CONF_AI_SERVICE,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_BASE_URL,
    CONF_OLLAMA_HOST,
    CONF_SYSTEM_PROMPT,
    CONF_MAX_TOOL_CALLS,
    CONF_ENABLE_CONVERSATION_HISTORY,
    CONF_MEMORY_WINDOW,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MEMORY_WINDOW,
    SYSTEM_PROMPT_ADDON,
    AI_SERVICE_ANTHROPIC,
    AI_SERVICE_OPENAI,
    AI_SERVICE_OLLAMA,
    AI_SERVICE_OPENAI_COMPATIBLE,
    INPUT_TEXT_USER,
    INPUT_TEXT_AI,
)
from .ai_services import (
    AIServiceProvider,
    AnthropicService,
    OpenAIService,
    OllamaService,
    OpenAICompatibleService,
    Message,
    MessageRole,
    Tool,
    ToolCall,
)
from .mcp.tools import ToolRegistry
from .nanobot import MemoryStore, SkillsLoader

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up conversation entity from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    if data.get("enable_conversation"):
        entity = HAMCPConversationEntity(
            hass=hass,
            config_entry=config_entry,
            tool_registry=data["tool_registry"],
            memory_store=data.get("memory_store"),
            skills_loader=data.get("skills_loader"),
        )
        async_add_entities([entity])


class HAMCPConversationEntity(ConversationEntity):
    """HA MCP Conversation Entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        skills_loader: SkillsLoader | None = None,
    ) -> None:
        """Initialize the conversation entity."""
        self.hass = hass
        self._config_entry = config_entry
        self._tool_registry = tool_registry
        self._memory_store = memory_store
        self._skills_loader = skills_loader
        self._ai_service: AIServiceProvider | None = None

        # Use OrderedDict with max size to prevent memory leak
        self._max_conversations = 100
        self._max_messages_per_conversation = 50
        self._conversation_history: OrderedDict[str, list[Message]] = OrderedDict()

        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"

        # Initialize AI service
        self._setup_ai_service()

    def _get_runtime_settings(self) -> dict[str, Any]:
        """Get runtime settings overrides from hass.data."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry.entry_id, {}
        )
        return entry_data.get("runtime_settings", {})

    def _setup_ai_service(self) -> None:
        """Setup the AI service based on config."""
        config = self._config_entry.data
        overrides = self._get_runtime_settings()

        # Prefer runtime_settings (populated from active LLM provider)
        ai_service_type = overrides.get("ai_service") or config.get(CONF_AI_SERVICE)

        service_config = {
            "api_key": overrides.get("api_key") or config.get(CONF_API_KEY),
            "model": overrides.get("model") or config.get(CONF_MODEL),
            "base_url": overrides.get("base_url") or config.get(CONF_BASE_URL),
            "ollama_host": overrides.get("base_url") or config.get(CONF_OLLAMA_HOST),
            "temperature": overrides.get("temperature", config.get("temperature")),
            "max_tokens": overrides.get("max_tokens", config.get("max_tokens")),
        }

        if ai_service_type == AI_SERVICE_ANTHROPIC:
            self._ai_service = AnthropicService(service_config)
        elif ai_service_type == AI_SERVICE_OPENAI:
            self._ai_service = OpenAIService(service_config)
        elif ai_service_type == AI_SERVICE_OLLAMA:
            self._ai_service = OllamaService(service_config)
        elif ai_service_type == AI_SERVICE_OPENAI_COMPATIBLE:
            self._ai_service = OpenAICompatibleService(service_config)
        else:
            _LOGGER.error("Unknown AI service type: %s", ai_service_type)

    @property
    def supported_languages(self) -> list[str] | str:
        """Return supported languages."""
        return "*"  # Support all languages

    @property
    def supported_features(self) -> ConversationEntityFeature:
        """Return supported features."""
        return ConversationEntityFeature.CONTROL

    # Map AI service type strings to their implementation classes
    _SERVICE_TYPE_MAP: dict[str, type] = {}

    @staticmethod
    def _get_service_type_map() -> dict[str, type]:
        """Lazy-load the service type map."""
        if not HAMCPConversationEntity._SERVICE_TYPE_MAP:
            from .ai_services.anthropic import AnthropicService
            from .ai_services.openai import OpenAIService
            from .ai_services.ollama import OllamaService
            from .ai_services.openai_compatible import OpenAICompatibleService

            HAMCPConversationEntity._SERVICE_TYPE_MAP = {
                AI_SERVICE_ANTHROPIC: AnthropicService,
                AI_SERVICE_OPENAI: OpenAIService,
                AI_SERVICE_OLLAMA: OllamaService,
                AI_SERVICE_OPENAI_COMPATIBLE: OpenAICompatibleService,
            }
        return HAMCPConversationEntity._SERVICE_TYPE_MAP

    def _refresh_ai_service_config(self) -> None:
        """Refresh AI service config from runtime settings, re-init if provider changed."""
        overrides = self._get_runtime_settings()
        new_service_type = overrides.get("ai_service")

        # Detect provider type change → full re-init
        if new_service_type and self._ai_service:
            type_map = self._get_service_type_map()
            expected_cls = type_map.get(new_service_type)
            if expected_cls and not isinstance(self._ai_service, expected_cls):
                _LOGGER.info(
                    "AI provider type changed to %s, re-initializing service",
                    new_service_type,
                )
                self._setup_ai_service()
                return

        if not self._ai_service:
            # Provider may have been set for the first time
            if new_service_type:
                self._setup_ai_service()
            return

        config = self._config_entry.data
        self._ai_service.config["temperature"] = overrides.get(
            "temperature", config.get("temperature")
        )
        self._ai_service.config["max_tokens"] = overrides.get(
            "max_tokens", config.get("max_tokens")
        )
        model = overrides.get("model")
        if model and hasattr(self._ai_service, "_model"):
            self._ai_service._model = model
        # Also update base_url for OpenAI-compatible services
        base_url = overrides.get("base_url")
        if base_url and hasattr(self._ai_service, "_base_url"):
            if self._ai_service._base_url != base_url:
                self._ai_service._base_url = base_url
                self._ai_service._client = None  # Force client re-creation
        # Update API key if changed
        api_key = overrides.get("api_key")
        if api_key and hasattr(self._ai_service, "_api_key"):
            if self._ai_service._api_key != api_key:
                self._ai_service._api_key = api_key
                self._ai_service._client = None  # Force client re-creation
        reasoning_effort = overrides.get("reasoning_effort")
        if reasoning_effort:
            self._ai_service.config["reasoning_effort"] = reasoning_effort

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a conversation input."""
        # Refresh AI params from runtime settings before each turn
        self._refresh_ai_service_config()

        if self._ai_service is None:
            response = IntentResponse(language=user_input.language)
            response.async_set_speech("AI service not configured.")
            return ConversationResult(
                response=response,
                conversation_id=user_input.conversation_id,
            )

        # Get user ID from context
        user_id = None
        if user_input.context and user_input.context.user_id:
            user_id = user_input.context.user_id

        # Use user-based conversation ID for persistent history
        # This ensures the same user always continues their conversation
        conversation_id = user_input.conversation_id or f"user_{user_id or 'default'}"

        # Check if we need to load history from recorder
        if conversation_id not in self._conversation_history:
            # Enforce max conversations limit (LRU eviction)
            while len(self._conversation_history) >= self._max_conversations:
                self._conversation_history.popitem(last=False)

            # Try to load history from recorder if enabled
            history_enabled = self._config_entry.data.get(CONF_ENABLE_CONVERSATION_HISTORY, True)
            if history_enabled and user_id:
                loaded_messages = await self._load_history_from_recorder(
                    user_id, conversation_id=conversation_id
                )
                self._conversation_history[conversation_id] = loaded_messages
            else:
                self._conversation_history[conversation_id] = []
        else:
            # Move to end (most recently used)
            self._conversation_history.move_to_end(conversation_id)

        messages = self._conversation_history[conversation_id]

        # Enforce max messages per conversation
        if len(messages) >= self._max_messages_per_conversation:
            # Trim to make room, but ensure we don't cut mid-tool-exchange.
            # Walk forward from the trim point until we find a safe boundary
            # (a USER or standalone ASSISTANT message without pending tool calls).
            target = self._max_messages_per_conversation - 1
            trim_start = len(messages) - target
            # Move trim_start forward to avoid orphaned TOOL / mid-exchange messages
            while trim_start < len(messages):
                msg = messages[trim_start]
                if msg.role == MessageRole.USER:
                    break  # Safe: starts with a user turn
                if msg.role == MessageRole.ASSISTANT and not msg.tool_calls:
                    break  # Safe: standalone assistant reply
                trim_start += 1
            if trim_start >= len(messages):
                trim_start = len(messages) - 1  # Keep at least the last message
            self._conversation_history[conversation_id] = messages[trim_start:]
            messages = self._conversation_history[conversation_id]

        # Add user message
        messages.append(Message(role=MessageRole.USER, content=user_input.text))

        # Get system prompt (runtime override takes priority)
        overrides = self._get_runtime_settings()
        base_system_prompt = overrides.get(
            "system_prompt",
            self._config_entry.data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
        )
        # Always append the resource creation addon to ensure proper behavior
        system_prompt = base_system_prompt + SYSTEM_PROMPT_ADDON

        # Inject memory context (SOUL.md + USER.md + MEMORY.md) into system prompt
        if self._memory_store:
            try:
                memory_context = await self._memory_store.get_memory_context()
                if memory_context:
                    system_prompt = memory_context + "\n\n---\n\n" + system_prompt
                    _LOGGER.debug(
                        "Memory context injected: %d chars", len(memory_context)
                    )
            except Exception as e:
                _LOGGER.warning("Failed to load memory context: %s", e)

        # Inject skills context (always-on bodies + XML summary of others)
        if self._skills_loader:
            try:
                skills_context = await self._skills_loader.get_skills_context()
                if skills_context:
                    system_prompt = system_prompt + "\n\n---\n\n" + skills_context
                    _LOGGER.debug(
                        "Skills context injected: %d chars", len(skills_context)
                    )
            except Exception as e:
                _LOGGER.warning("Failed to load skills context: %s", e)

        _LOGGER.debug("System prompt total length: %d", len(system_prompt))

        # Get max tool calls (runtime override takes priority)
        max_tool_calls = overrides.get(
            "max_tool_calls",
            self._config_entry.data.get(CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS),
        )

        # Convert tools to AI format
        tools = self._get_tools_for_ai()

        try:
            # Process with tool loop
            final_response = await self._process_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tool_calls=max_tool_calls,
            )

            # Record conversation for history
            await self._record_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=user_input.text,
                assistant_message=final_response,
            )

            # Check and trigger memory consolidation (non-blocking)
            if self._memory_store and self._ai_service:
                memory_window = self._config_entry.data.get(
                    CONF_MEMORY_WINDOW, DEFAULT_MEMORY_WINDOW
                )
                should = await self._memory_store.should_consolidate(
                    conversation_id=conversation_id,
                    message_count=len(messages),
                    memory_window=memory_window,
                )
                if should:
                    _LOGGER.info(
                        "Triggering memory consolidation for %s (%d messages)",
                        conversation_id,
                        len(messages),
                    )
                    # Build message dicts from the Message objects for consolidation
                    msg_dicts = [
                        {
                            "role": m.role.value,
                            "content": m.content or "",
                            "tool_calls": (
                                [{"name": tc.name, "arguments": tc.arguments}
                                 for tc in m.tool_calls]
                                if m.tool_calls else None
                            ),
                        }
                        for m in messages
                    ]
                    self.hass.async_create_task(
                        self._memory_store.consolidate(
                            conversation_id=conversation_id,
                            messages=msg_dicts,
                            ai_service=self._ai_service,
                            memory_window=memory_window,
                        )
                    )

            response = IntentResponse(language=user_input.language)
            response.async_set_speech(final_response)
            return ConversationResult(
                response=response,
                conversation_id=conversation_id,
            )

        except Exception as e:
            _LOGGER.error("Error processing conversation: %s", e, exc_info=True)
            response = IntentResponse(language=user_input.language)
            response.async_set_speech(
                "Sorry, an error occurred while processing your request. "
                "Please check the logs for details."
            )
            return ConversationResult(
                response=response,
                conversation_id=conversation_id,
            )

    async def _process_with_tools(
        self,
        messages: list[Message],
        tools: list[Tool],
        system_prompt: str,
        max_tool_calls: int,
    ) -> str:
        """Process conversation with tool calling loop."""
        tool_call_count = 0

        while tool_call_count < max_tool_calls:
            # Call AI service
            response = await self._ai_service.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
            )

            # If no tool calls, we're done
            if not response.tool_calls:
                # Add assistant message to history
                messages.append(
                    Message(role=MessageRole.ASSISTANT, content=response.content)
                )
                return response.content

            # Add assistant message with tool calls to history
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_call_count += 1
                _LOGGER.debug(
                    "Executing tool: %s with args: %s",
                    tool_call.name,
                    tool_call.arguments,
                )

                try:
                    result = await self._tool_registry.execute(
                        tool_call.name, tool_call.arguments
                    )
                    result_text = json.dumps(result, indent=2, default=str)
                except Exception as e:
                    _LOGGER.error("Tool execution error: %s", e)
                    result_text = f"Error executing tool: {str(e)}"

                # Add tool result to messages
                messages.append(
                    Message(
                        role=MessageRole.TOOL,
                        content=result_text,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )

        # Max tool calls reached, get final response
        response = await self._ai_service.chat(
            messages=messages,
            tools=None,  # No tools for final response
            system_prompt=system_prompt,
        )

        messages.append(
            Message(role=MessageRole.ASSISTANT, content=response.content)
        )
        return response.content

    def _get_tools_for_ai(self) -> list[Tool]:
        """Convert registry tools to AI tool format."""
        tools = []
        for tool_def in self._tool_registry.get_all():
            tools.append(
                Tool(
                    name=tool_def.name,
                    description=tool_def.description,
                    input_schema=tool_def.input_schema,
                )
            )
        return tools

    async def _record_conversation(
        self,
        user_id: str | None,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Record conversation to history."""
        # This will be handled by the conversation_recorder module
        # For now, just log
        _LOGGER.debug(
            "Recording conversation: user=%s, conv=%s",
            user_id,
            conversation_id,
        )

        # Fire event for recorder to pick up
        self.hass.bus.async_fire(
            f"{DOMAIN}_conversation_message",
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "user_message": user_message,
                "assistant_message": assistant_message,
            },
        )

        # Sync to input_text entities
        try:
            self.hass.states.async_set(
                INPUT_TEXT_USER,
                user_message[:255],
                {"friendly_name": "MCP 使用者輸入", "icon": "mdi:account-voice"},
            )
            self.hass.states.async_set(
                INPUT_TEXT_AI,
                assistant_message[:255],
                {"friendly_name": "MCP AI 回覆", "icon": "mdi:robot"},
            )
        except Exception as e:
            _LOGGER.warning("Failed to sync input_text: %s", e)

    async def _load_history_from_recorder(
        self, user_id: str, conversation_id: str | None = None
    ) -> list[Message]:
        """Load conversation history from recorder for a specific conversation."""
        try:
            # Get recorder instance
            _LOGGER.debug(
                "Loading history for user %s, conversation_id=%s, entry_id=%s",
                user_id,
                conversation_id,
                self._config_entry.entry_id,
            )
            _LOGGER.debug("hass.data[DOMAIN] keys: %s", list(self.hass.data.get(DOMAIN, {}).keys()))

            entry_data = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id, {})
            _LOGGER.debug("entry_data keys: %s", list(entry_data.keys()) if entry_data else "None")

            recorder = entry_data.get("recorder")

            if not recorder:
                _LOGGER.warning("Recorder not available for entry %s, starting with empty history", self._config_entry.entry_id)
                return []

            # Get recent history (last 20 messages to avoid context overflow)
            # Filter by conversation_id when available to avoid cross-conversation contamination
            history_records = await recorder.get_conversation_history(
                user_id=user_id,
                conversation_id=conversation_id,
                limit=20,
            )

            messages = []
            for record in history_records:
                role_str = record.get("role", "user")
                content = record.get("content", "")

                if role_str == "user":
                    role = MessageRole.USER
                elif role_str == "assistant":
                    role = MessageRole.ASSISTANT
                else:
                    continue  # Skip tool messages for now

                messages.append(Message(role=role, content=content))

            # IMPORTANT: Reverse the order since DB returns DESC (newest first)
            # We need chronological order (oldest first) for conversation context
            messages.reverse()

            _LOGGER.debug(
                "Loaded %d messages from history for user %s",
                len(messages),
                user_id,
            )
            return messages

        except Exception as e:
            _LOGGER.error("Failed to load history from recorder: %s", e, exc_info=True)
            return []

    async def async_prepare(self) -> None:
        """Prepare the conversation entity."""
        # Validate AI service connection
        if self._ai_service:
            try:
                is_valid = await self._ai_service.validate_config()
                if not is_valid:
                    _LOGGER.warning("AI service configuration validation failed")
            except Exception as e:
                _LOGGER.error("Error validating AI service: %s", e)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._ai_service:
            try:
                await self._ai_service.close()
            except Exception as e:
                _LOGGER.error("Error closing AI service: %s", e)

        # Clear conversation history
        self._conversation_history.clear()
