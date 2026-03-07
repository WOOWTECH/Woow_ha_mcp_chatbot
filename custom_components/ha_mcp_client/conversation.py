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
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_MAX_TOOL_CALLS,
    SYSTEM_PROMPT_ADDON,
    AI_SERVICE_ANTHROPIC,
    AI_SERVICE_OPENAI,
    AI_SERVICE_OLLAMA,
    AI_SERVICE_OPENAI_COMPATIBLE,
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
    ) -> None:
        """Initialize the conversation entity."""
        self.hass = hass
        self._config_entry = config_entry
        self._tool_registry = tool_registry
        self._ai_service: AIServiceProvider | None = None

        # Use OrderedDict with max size to prevent memory leak
        self._max_conversations = 100
        self._max_messages_per_conversation = 50
        self._conversation_history: OrderedDict[str, list[Message]] = OrderedDict()

        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"

        # Initialize AI service
        self._setup_ai_service()

    def _setup_ai_service(self) -> None:
        """Setup the AI service based on config."""
        config = self._config_entry.data
        ai_service_type = config.get(CONF_AI_SERVICE)

        service_config = {
            "api_key": config.get(CONF_API_KEY),
            "model": config.get(CONF_MODEL),
            "base_url": config.get(CONF_BASE_URL),
            "ollama_host": config.get(CONF_OLLAMA_HOST),
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

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a conversation input."""
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
                loaded_messages = await self._load_history_from_recorder(user_id)
                self._conversation_history[conversation_id] = loaded_messages
            else:
                self._conversation_history[conversation_id] = []
        else:
            # Move to end (most recently used)
            self._conversation_history.move_to_end(conversation_id)

        messages = self._conversation_history[conversation_id]

        # Enforce max messages per conversation
        if len(messages) >= self._max_messages_per_conversation:
            # Keep last N-1 messages to make room for new one
            self._conversation_history[conversation_id] = messages[-(self._max_messages_per_conversation - 1):]
            messages = self._conversation_history[conversation_id]

        # Add user message
        messages.append(Message(role=MessageRole.USER, content=user_input.text))

        # Get system prompt and auto-append resource creation guidelines
        base_system_prompt = self._config_entry.data.get(
            CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT
        )
        # Always append the resource creation addon to ensure proper behavior
        system_prompt = base_system_prompt + SYSTEM_PROMPT_ADDON
        _LOGGER.debug(
            "System prompt length: base=%d, addon=%d, total=%d",
            len(base_system_prompt),
            len(SYSTEM_PROMPT_ADDON),
            len(system_prompt),
        )

        # Get max tool calls
        max_tool_calls = self._config_entry.data.get(
            CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS
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

    async def _load_history_from_recorder(self, user_id: str) -> list[Message]:
        """Load conversation history from recorder for a user."""
        try:
            # Get recorder instance
            _LOGGER.debug(
                "Loading history for user %s, entry_id=%s",
                user_id,
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
            history_records = await recorder.get_conversation_history(
                user_id=user_id,
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
