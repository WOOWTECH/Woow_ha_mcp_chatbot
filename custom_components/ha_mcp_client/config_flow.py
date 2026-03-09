"""Config flow for HA MCP Client integration."""

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
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
    CONF_LLM_PROVIDERS,
    CONF_ACTIVE_LLM_PROVIDER,
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
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-4-20250514",
]

OPENAI_MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "o3",
    "o3-mini",
    "o4-mini",
]

GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
]

OLLAMA_MODELS = [
    "llama4:scout",
    "llama3.2",
    "llama3.1",
    "qwen3",
    "qwen3:30b",
    "deepseek-r1",
    "mistral",
    "gemma2",
    "phi3",
]

_DEFAULT_MODEL_FOR_PROVIDER = {
    AI_SERVICE_ANTHROPIC: DEFAULT_ANTHROPIC_MODEL,
    AI_SERVICE_OPENAI: DEFAULT_OPENAI_MODEL,
    AI_SERVICE_OLLAMA: DEFAULT_OLLAMA_MODEL,
    AI_SERVICE_OPENAI_COMPATIBLE: DEFAULT_OPENAI_MODEL,
}

_MODELS_FOR_PROVIDER = {
    AI_SERVICE_ANTHROPIC: ANTHROPIC_MODELS,
    AI_SERVICE_OPENAI: OPENAI_MODELS,
    AI_SERVICE_OLLAMA: OLLAMA_MODELS,
    AI_SERVICE_OPENAI_COMPATIBLE: GEMINI_MODELS + OPENAI_MODELS,
}

ALL_MODELS = ANTHROPIC_MODELS + OPENAI_MODELS + GEMINI_MODELS + OLLAMA_MODELS

_PROVIDER_LABELS = [
    {"value": AI_SERVICE_ANTHROPIC, "label": "Anthropic Claude"},
    {"value": AI_SERVICE_OPENAI, "label": "OpenAI"},
    {"value": AI_SERVICE_OLLAMA, "label": "Ollama (Local)"},
    {"value": AI_SERVICE_OPENAI_COMPATIBLE, "label": "OpenAI Compatible"},
]


def _next_provider_id(providers: list[dict], provider_type: str) -> str:
    """Generate the next provider ID like 'anthropic_1', 'anthropic_2', etc."""
    existing = [
        p["id"] for p in providers
        if p["id"].startswith(f"{provider_type}_")
    ]
    idx = 1
    while f"{provider_type}_{idx}" in existing:
        idx += 1
    return f"{provider_type}_{idx}"


def _mask_api_key(key: str | None) -> str | None:
    """Mask API key for display, showing last 3 characters."""
    if not key:
        return None
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}***{key[-3:]}"


async def _validate_provider_config(
    hass: HomeAssistant, provider: str, api_key: str | None, base_url: str | None
) -> tuple[bool, str | None]:
    """Validate a single LLM provider configuration."""
    if provider == AI_SERVICE_ANTHROPIC:
        if not api_key:
            return False, "invalid_api_key"
        return True, None

    elif provider == AI_SERVICE_OPENAI:
        if not api_key:
            return False, "invalid_api_key"
        return True, None

    elif provider == AI_SERVICE_OLLAMA:
        host = base_url or DEFAULT_OLLAMA_HOST
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{host}/api/tags", timeout=5.0)
                if response.status_code != 200:
                    return False, "ollama_not_reachable"
        except Exception:
            return False, "ollama_not_reachable"
        return True, None

    elif provider == AI_SERVICE_OPENAI_COMPATIBLE:
        if not api_key or not base_url:
            return False, "invalid_api_key"
        return True, None

    return False, "invalid_api_key"


async def async_migrate_entry(hass: HomeAssistant, config_entry: config_entries.ConfigEntry) -> bool:
    """Migrate config entry from version 1 to 2."""
    if config_entry.version < 2:
        _LOGGER.info("Migrating config entry from version %s to 2", config_entry.version)
        old_data = dict(config_entry.data)

        # Extract old single-provider fields
        provider = old_data.pop(CONF_AI_SERVICE, AI_SERVICE_OPENAI)
        api_key = old_data.pop(CONF_API_KEY, "")
        model = old_data.pop(CONF_MODEL, "")
        base_url = old_data.pop(CONF_BASE_URL, None)
        ollama_host = old_data.pop(CONF_OLLAMA_HOST, None)

        # Remove temperature (managed by HA entity)
        old_data.pop("temperature", None)

        # Build new llm_providers list
        provider_id = f"{provider}_1"
        provider_name = {
            AI_SERVICE_ANTHROPIC: "Anthropic",
            AI_SERVICE_OPENAI: "OpenAI",
            AI_SERVICE_OLLAMA: "Ollama Local",
            AI_SERVICE_OPENAI_COMPATIBLE: "OpenAI Compatible",
        }.get(provider, provider.capitalize())

        # Only carry base_url for providers that actually need it
        effective_base_url = None
        if provider in (AI_SERVICE_OLLAMA,):
            effective_base_url = ollama_host or base_url
        elif provider in (AI_SERVICE_OPENAI_COMPATIBLE,):
            effective_base_url = base_url
        # Standard OpenAI and Anthropic don't use base_url

        old_data[CONF_LLM_PROVIDERS] = [{
            "id": provider_id,
            "name": provider_name,
            "provider": provider,
            "api_key": api_key,
            "model": model or _DEFAULT_MODEL_FOR_PROVIDER.get(provider, ""),
            "base_url": effective_base_url,
        }]
        old_data[CONF_ACTIVE_LLM_PROVIDER] = provider_id

        hass.config_entries.async_update_entry(
            config_entry, data=old_data, version=2
        )
        _LOGGER.info("Migration to version 2 complete: provider=%s", provider_id)

    return True


class HAMCPClientConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA MCP Client."""

    VERSION = 2

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

            # Otherwise, create entry with empty providers
            self._data[CONF_LLM_PROVIDERS] = []
            self._data[CONF_ACTIVE_LLM_PROVIDER] = ""
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
        """Configure initial AI service (first LLM provider)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            provider_type = user_input.get(CONF_AI_SERVICE, AI_SERVICE_ANTHROPIC)
            api_key = user_input.get(CONF_API_KEY, "")
            model = user_input.get(CONF_MODEL, "")
            base_url = user_input.get(CONF_BASE_URL, "") or user_input.get(CONF_OLLAMA_HOST, "")

            # Validate
            is_valid, error = await _validate_provider_config(
                self.hass, provider_type, api_key, base_url
            )
            if is_valid:
                # Create the first provider entry
                provider_id = f"{provider_type}_1"
                provider_name = {
                    AI_SERVICE_ANTHROPIC: "Anthropic",
                    AI_SERVICE_OPENAI: "OpenAI",
                    AI_SERVICE_OLLAMA: "Ollama Local",
                    AI_SERVICE_OPENAI_COMPATIBLE: "OpenAI Compatible",
                }.get(provider_type, provider_type.capitalize())

                self._data[CONF_LLM_PROVIDERS] = [{
                    "id": provider_id,
                    "name": provider_name,
                    "provider": provider_type,
                    "api_key": api_key,
                    "model": model or _DEFAULT_MODEL_FOR_PROVIDER.get(provider_type, ""),
                    "base_url": base_url or None,
                }]
                self._data[CONF_ACTIVE_LLM_PROVIDER] = provider_id

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
                        options=_PROVIDER_LABELS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_MODEL): SelectSelector(
                    SelectSelectorConfig(
                        options=ALL_MODELS,
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

    def __init__(self) -> None:
        """Initialize options flow."""
        self._editing_provider_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - main menu."""
        if user_input is not None:
            next_step = user_input.get("menu_option")
            if next_step == "manage_llm":
                return await self.async_step_manage_llm()
            elif next_step == "conversation_settings":
                return await self.async_step_conversation_settings()
            elif next_step == "advanced":
                return await self.async_step_advanced()

        providers = self.config_entry.data.get(CONF_LLM_PROVIDERS, [])
        active = self.config_entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")
        provider_count = len(providers)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("menu_option"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {
                                    "value": "manage_llm",
                                    "label": f"🤖 管理 LLM 提供者 ({provider_count} 組設定)",
                                },
                                {
                                    "value": "conversation_settings",
                                    "label": "💬 Conversation Settings",
                                },
                                {
                                    "value": "advanced",
                                    "label": "⚙️ Advanced Settings",
                                },
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_manage_llm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show list of LLM providers for management."""
        if user_input is not None:
            selected = user_input.get("provider_action", "")
            if selected == "__add_new__":
                return await self.async_step_add_llm()
            elif selected:
                # Edit existing provider
                self._editing_provider_id = selected
                return await self.async_step_edit_llm()

        providers = self.config_entry.data.get(CONF_LLM_PROVIDERS, [])
        active = self.config_entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")

        options = []
        for p in providers:
            is_active = "✅ " if p["id"] == active else ""
            active_tag = " [使用中]" if p["id"] == active else ""
            label = f"{is_active}{p['name']} ({p['model']}){active_tag}"
            options.append({"value": p["id"], "label": label})

        options.append({"value": "__add_new__", "label": "➕ 新增 LLM 提供者"})

        return self.async_show_form(
            step_id="manage_llm",
            data_schema=vol.Schema(
                {
                    vol.Required("provider_action"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_add_llm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new LLM provider."""
        errors: dict[str, str] = {}

        if user_input is not None:
            provider_type = user_input.get("provider", AI_SERVICE_ANTHROPIC)
            name = user_input.get("name", "").strip()
            api_key = user_input.get("api_key", "")
            model = user_input.get("model", "")
            base_url = user_input.get("base_url", "")

            if not name:
                name = {
                    AI_SERVICE_ANTHROPIC: "Anthropic",
                    AI_SERVICE_OPENAI: "OpenAI",
                    AI_SERVICE_OLLAMA: "Ollama Local",
                    AI_SERVICE_OPENAI_COMPATIBLE: "OpenAI Compatible",
                }.get(provider_type, provider_type.capitalize())

            # Validate
            is_valid, error = await _validate_provider_config(
                self.hass, provider_type, api_key, base_url or None
            )
            if is_valid:
                new_data = dict(self.config_entry.data)
                providers = list(new_data.get(CONF_LLM_PROVIDERS, []))
                provider_id = _next_provider_id(providers, provider_type)

                providers.append({
                    "id": provider_id,
                    "name": name,
                    "provider": provider_type,
                    "api_key": api_key,
                    "model": model or _DEFAULT_MODEL_FOR_PROVIDER.get(provider_type, ""),
                    "base_url": base_url or None,
                })
                new_data[CONF_LLM_PROVIDERS] = providers

                # If first provider, set as active
                if not new_data.get(CONF_ACTIVE_LLM_PROVIDER):
                    new_data[CONF_ACTIVE_LLM_PROVIDER] = provider_id

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})
            errors["base"] = error

        return self.async_show_form(
            step_id="add_llm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required("provider", default=AI_SERVICE_ANTHROPIC): SelectSelector(
                        SelectSelectorConfig(
                            options=_PROVIDER_LABELS,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional("api_key"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional("model"): SelectSelector(
                        SelectSelectorConfig(
                            options=ALL_MODELS,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                        )
                    ),
                    vol.Optional("base_url"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_llm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit an existing LLM provider."""
        errors: dict[str, str] = {}
        provider_id = self._editing_provider_id

        providers = list(self.config_entry.data.get(CONF_LLM_PROVIDERS, []))
        current_provider = None
        for p in providers:
            if p["id"] == provider_id:
                current_provider = p
                break

        if not current_provider:
            return self.async_create_entry(title="", data={})

        if user_input is not None:
            # Handle delete
            if user_input.get("delete_provider", False):
                new_data = dict(self.config_entry.data)
                new_providers = [p for p in providers if p["id"] != provider_id]
                new_data[CONF_LLM_PROVIDERS] = new_providers
                # If we deleted the active provider, switch to first remaining
                if new_data.get(CONF_ACTIVE_LLM_PROVIDER) == provider_id:
                    new_data[CONF_ACTIVE_LLM_PROVIDER] = (
                        new_providers[0]["id"] if new_providers else ""
                    )
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

            # Handle update
            provider_type = user_input.get("provider", current_provider["provider"])
            name = user_input.get("name", "").strip() or current_provider["name"]
            api_key = user_input.get("api_key", "")
            model = user_input.get("model", "") or current_provider["model"]
            base_url = user_input.get("base_url", "")
            set_active = user_input.get("set_active", False)

            # Keep old API key if not provided
            if not api_key:
                api_key = current_provider.get("api_key", "")

            # Validate
            is_valid, error = await _validate_provider_config(
                self.hass, provider_type, api_key, base_url or current_provider.get("base_url")
            )
            if is_valid:
                new_data = dict(self.config_entry.data)
                new_providers = []
                for p in providers:
                    if p["id"] == provider_id:
                        new_providers.append({
                            "id": provider_id,
                            "name": name,
                            "provider": provider_type,
                            "api_key": api_key,
                            "model": model,
                            "base_url": base_url or None,
                        })
                    else:
                        new_providers.append(p)
                new_data[CONF_LLM_PROVIDERS] = new_providers

                if set_active:
                    new_data[CONF_ACTIVE_LLM_PROVIDER] = provider_id

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})
            errors["base"] = error

        active = self.config_entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")
        is_active = provider_id == active

        return self.async_show_form(
            step_id="edit_llm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=current_provider["name"]
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        "provider", default=current_provider["provider"]
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=_PROVIDER_LABELS,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "api_key",
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        "model",
                        description={"suggested_value": current_provider.get("model", "")},
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=ALL_MODELS,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                        )
                    ),
                    vol.Optional(
                        "base_url",
                        description={"suggested_value": current_provider.get("base_url", "")},
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Optional(
                        "set_active", default=False
                    ): BooleanSelector(),
                    vol.Optional(
                        "delete_provider", default=False
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "provider_name": current_provider["name"],
                "api_key_masked": _mask_api_key(current_provider.get("api_key")) or "Not set",
                "is_active": "Yes" if is_active else "No",
            },
        )

    async def async_step_conversation_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure conversation settings."""
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
