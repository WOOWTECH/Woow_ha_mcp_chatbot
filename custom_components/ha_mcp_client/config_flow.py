"""Config flow for HA MCP Client integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_AI_SERVICE,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_BASE_URL,
    CONF_OLLAMA_HOST,
    CONF_ENABLE_MCP_SERVER,
    CONF_ENABLE_CONVERSATION,
    CONF_MCP_SERVER_PORT,
    CONF_ENABLE_CONVERSATION_HISTORY,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_SYSTEM_PROMPT,
    CONF_MAX_TOOL_CALLS,
    AI_SERVICE_ANTHROPIC,
    AI_SERVICE_OPENAI,
    AI_SERVICE_OLLAMA,
    AI_SERVICE_OPENAI_COMPATIBLE,
    AI_SERVICES,
    DEFAULT_MCP_SERVER_PORT,
    DEFAULT_HISTORY_RETENTION_DAYS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_SYSTEM_PROMPT,
)

_LOGGER = logging.getLogger(__name__)

# Model options for each service
ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]

OPENAI_MODELS = [
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
]

OLLAMA_MODELS = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "mixtral",
    "codellama",
    "phi3",
    "gemma2",
]


class HAMCPClientConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA MCP Client."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - feature selection."""
        # Check if already configured (singleton)
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self._data.update(user_input)

            # If MCP server enabled, go to server config
            if user_input.get(CONF_ENABLE_MCP_SERVER):
                return await self.async_step_mcp_server()

            # If conversation enabled, go to AI service config
            if user_input.get(CONF_ENABLE_CONVERSATION):
                return await self.async_step_ai_service()

            # Nothing enabled, show error
            return self.async_show_form(
                step_id="user",
                data_schema=self._get_feature_schema(),
                errors={"base": "no_features_selected"},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_feature_schema(),
        )

    async def async_step_mcp_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure MCP server settings."""
        if user_input is not None:
            self._data.update(user_input)

            # If conversation also enabled, go to AI service config
            if self._data.get(CONF_ENABLE_CONVERSATION):
                return await self.async_step_ai_service()

            # Otherwise, create entry
            return self.async_create_entry(
                title="HA MCP Client",
                data=self._data,
            )

        return self.async_show_form(
            step_id="mcp_server",
            data_schema=self._get_mcp_server_schema(),
        )

    async def async_step_ai_service(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure AI service settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # Validate the AI service configuration
            is_valid, error = await self._validate_ai_service(user_input)
            if is_valid:
                return await self.async_step_conversation_settings()
            errors["base"] = error

        return self.async_show_form(
            step_id="ai_service",
            data_schema=self._get_ai_service_schema(),
            errors=errors,
        )

    async def async_step_conversation_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure conversation settings."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="HA MCP Client",
                data=self._data,
            )

        return self.async_show_form(
            step_id="conversation_settings",
            data_schema=self._get_conversation_settings_schema(),
        )

    async def _validate_ai_service(
        self, config: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate AI service configuration."""
        ai_service = config.get(CONF_AI_SERVICE)
        api_key = config.get(CONF_API_KEY)

        if ai_service == AI_SERVICE_ANTHROPIC:
            if not api_key:
                return False, "invalid_api_key"
            # Could add actual API validation here
            return True, None

        elif ai_service == AI_SERVICE_OPENAI:
            if not api_key:
                return False, "invalid_api_key"
            return True, None

        elif ai_service == AI_SERVICE_OLLAMA:
            host = config.get(CONF_OLLAMA_HOST, DEFAULT_OLLAMA_HOST)
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{host}/api/tags", timeout=5.0)
                    if response.status_code != 200:
                        return False, "ollama_not_reachable"
            except Exception:
                return False, "ollama_not_reachable"
            return True, None

        elif ai_service == AI_SERVICE_OPENAI_COMPATIBLE:
            if not api_key or not config.get(CONF_BASE_URL):
                return False, "invalid_api_key"
            return True, None

        return False, "invalid_api_key"

    def _get_feature_schema(self) -> vol.Schema:
        """Get schema for feature selection."""
        return vol.Schema(
            {
                vol.Required(CONF_ENABLE_MCP_SERVER, default=True): BooleanSelector(),
                vol.Required(CONF_ENABLE_CONVERSATION, default=True): BooleanSelector(),
            }
        )

    def _get_mcp_server_schema(self) -> vol.Schema:
        """Get schema for MCP server configuration."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_MCP_SERVER_PORT, default=DEFAULT_MCP_SERVER_PORT
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1024,
                        max=65535,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    def _get_ai_service_schema(self) -> vol.Schema:
        """Get schema for AI service configuration."""
        return vol.Schema(
            {
                vol.Required(CONF_AI_SERVICE, default=AI_SERVICE_ANTHROPIC): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": AI_SERVICE_ANTHROPIC, "label": "Anthropic Claude"},
                            {"value": AI_SERVICE_OPENAI, "label": "OpenAI"},
                            {"value": AI_SERVICE_OLLAMA, "label": "Ollama (Local)"},
                            {"value": AI_SERVICE_OPENAI_COMPATIBLE, "label": "OpenAI Compatible"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_MODEL): SelectSelector(
                    SelectSelectorConfig(
                        options=ANTHROPIC_MODELS + OPENAI_MODELS + OLLAMA_MODELS,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(CONF_BASE_URL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Optional(
                    CONF_OLLAMA_HOST, default=DEFAULT_OLLAMA_HOST
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
            }
        )

    def _get_conversation_settings_schema(self) -> vol.Schema:
        """Get schema for conversation settings."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_CONVERSATION_HISTORY, default=True
                ): BooleanSelector(),
                vol.Required(
                    CONF_HISTORY_RETENTION_DAYS, default=DEFAULT_HISTORY_RETENTION_DAYS
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=365,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_SYSTEM_PROMPT, default=DEFAULT_SYSTEM_PROMPT
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
                ),
                vol.Required(
                    CONF_MAX_TOOL_CALLS, default=DEFAULT_MAX_TOOL_CALLS
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=50,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return HAMCPClientOptionsFlow()


class HAMCPClientOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for HA MCP Client."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - main menu."""
        if user_input is not None:
            next_step = user_input.get("menu_option")
            if next_step == "ai_service":
                return await self.async_step_ai_service()
            elif next_step == "conversation_settings":
                return await self.async_step_conversation_settings()
            elif next_step == "advanced":
                return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("menu_option"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {
                                    "value": "ai_service",
                                    "label": "🤖 AI Service Settings - Configure AI provider, API key, and model",
                                },
                                {
                                    "value": "conversation_settings",
                                    "label": "💬 Conversation Settings - History and retention options",
                                },
                                {
                                    "value": "advanced",
                                    "label": "⚙️ Advanced Settings - System prompt and tool limits",
                                },
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "current_ai": self.config_entry.data.get(CONF_AI_SERVICE, "Not configured"),
                "current_model": self.config_entry.data.get(CONF_MODEL, "Not configured"),
            },
        )

    async def async_step_ai_service(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure AI service settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing data and options
            new_data = {**self.config_entry.data}
            new_data.update(user_input)

            # Update config entry data
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        # Get current values
        current = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="ai_service",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AI_SERVICE,
                        default=current.get(CONF_AI_SERVICE, AI_SERVICE_ANTHROPIC),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": AI_SERVICE_ANTHROPIC, "label": "Anthropic Claude"},
                                {"value": AI_SERVICE_OPENAI, "label": "OpenAI"},
                                {"value": AI_SERVICE_OLLAMA, "label": "Ollama (Local)"},
                                {"value": AI_SERVICE_OPENAI_COMPATIBLE, "label": "OpenAI Compatible"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_API_KEY,
                        description={"suggested_value": current.get(CONF_API_KEY, "")},
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        CONF_MODEL,
                        description={"suggested_value": current.get(CONF_MODEL, "")},
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=ANTHROPIC_MODELS + OPENAI_MODELS + OLLAMA_MODELS,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                        )
                    ),
                    vol.Optional(
                        CONF_BASE_URL,
                        description={"suggested_value": current.get(CONF_BASE_URL, "")},
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Optional(
                        CONF_OLLAMA_HOST,
                        default=current.get(CONF_OLLAMA_HOST, DEFAULT_OLLAMA_HOST),
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_conversation_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure conversation settings."""
        if user_input is not None:
            # Merge with existing data
            new_data = {**self.config_entry.data}
            new_data.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        current = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="conversation_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_CONVERSATION_HISTORY,
                        default=current.get(CONF_ENABLE_CONVERSATION_HISTORY, True),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_HISTORY_RETENTION_DAYS,
                        default=current.get(
                            CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=365,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure advanced settings."""
        if user_input is not None:
            new_data = {**self.config_entry.data}
            new_data.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        current = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SYSTEM_PROMPT,
                        description={"suggested_value": current.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)},
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
                    ),
                    vol.Required(
                        CONF_MAX_TOOL_CALLS,
                        default=current.get(CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
