"""Config flow for HA MCP Client integration (n8n chat panel mode)."""

import logging
from typing import Any

import aiohttp
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
    CONF_N8N_BASE_URL,
    CONF_N8N_API_KEY,
    CONF_N8N_WEBHOOK_PATH,
    CONF_N8N_BASIC_USER,
    CONF_N8N_BASIC_PASS,
    CONF_ENABLE_CONVERSATION_HISTORY,
    CONF_HISTORY_RETENTION_DAYS,
    DEFAULT_HISTORY_RETENTION_DAYS,
)

_LOGGER = logging.getLogger(__name__)


async def _discover_chat_workflows(
    base_url: str, api_key: str
) -> list[dict[str, str]]:
    """Use the n8n REST API to find workflows containing a Chat Trigger node.

    Returns a list of {name, webhookPath} dicts.
    """
    url = f"{base_url.rstrip('/')}/api/v1/workflows"
    headers = {"X-N8N-API-KEY": api_key}
    results: list[dict[str, str]] = []

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # n8n API paginates; fetch first page (limit=100 is usually enough)
            async with session.get(
                url, headers=headers, params={"limit": 100, "active": "true"}
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("n8n API returned %s", resp.status)
                    return results
                data = await resp.json()

            workflows = data.get("data", [])
            for wf in workflows:
                nodes = wf.get("nodes", [])
                for node in nodes:
                    if node.get("type") == "@n8n/n8n-nodes-langchain.chatTrigger":
                        webhook_id = node.get("webhookId", "")
                        if webhook_id:
                            results.append(
                                {
                                    "name": wf.get("name", "Unnamed"),
                                    "webhookPath": f"webhook/{webhook_id}/chat",
                                }
                            )
                        break  # one chat trigger per workflow
    except Exception as exc:
        _LOGGER.warning("Failed to discover n8n chat workflows: %s", exc)

    return results


class HAMCPClientConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA MCP Client (n8n mode)."""

    VERSION = 3

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._discovered_workflows: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1 — n8n connection: base URL + API key."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_N8N_BASE_URL].rstrip("/")
            api_key = user_input.get(CONF_N8N_API_KEY, "").strip()

            self._data[CONF_N8N_BASE_URL] = base_url

            if api_key:
                self._data[CONF_N8N_API_KEY] = api_key
                self._discovered_workflows = await _discover_chat_workflows(
                    base_url, api_key
                )
                if self._discovered_workflows:
                    return await self.async_step_select_workflow()
                errors["base"] = "no_chat_workflows"
            else:
                # No API key — go straight to manual webhook entry
                return await self.async_step_webhook()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_N8N_BASE_URL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Optional(CONF_N8N_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_workflow(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a — pick a discovered chat workflow."""
        if user_input is not None:
            selected = user_input["workflow"]
            if selected == "__manual__":
                return await self.async_step_webhook()
            self._data[CONF_N8N_WEBHOOK_PATH] = selected
            return await self.async_step_auth()

        options = [
            {"value": w["webhookPath"], "label": f"{w['name']}"}
            for w in self._discovered_workflows
        ]
        options.append({"value": "__manual__", "label": "手動輸入 Webhook 路徑"})

        return self.async_show_form(
            step_id="select_workflow",
            data_schema=vol.Schema(
                {
                    vol.Required("workflow"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_webhook(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2b — manually enter the webhook path."""
        if user_input is not None:
            path = user_input[CONF_N8N_WEBHOOK_PATH].strip().lstrip("/")
            self._data[CONF_N8N_WEBHOOK_PATH] = path
            return await self.async_step_auth()

        return self.async_show_form(
            step_id="webhook",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_N8N_WEBHOOK_PATH): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3 — Basic Auth credentials for the webhook."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_N8N_BASIC_USER, "").strip()
            password = user_input.get(CONF_N8N_BASIC_PASS, "").strip()

            if not username or not password:
                errors["base"] = "auth_required"
            else:
                self._data[CONF_N8N_BASIC_USER] = username
                self._data[CONF_N8N_BASIC_PASS] = password

                # Quick connectivity check
                ok = await self._test_webhook(
                    self._data[CONF_N8N_BASE_URL],
                    self._data[CONF_N8N_WEBHOOK_PATH],
                    username,
                    password,
                )
                if ok:
                    # Set defaults for conversation history
                    self._data.setdefault(CONF_ENABLE_CONVERSATION_HISTORY, True)
                    self._data.setdefault(
                        CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS
                    )
                    return self.async_create_entry(
                        title="AI \u804a\u5929 (n8n)",
                        data=self._data,
                    )
                errors["base"] = "webhook_unreachable"

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_N8N_BASIC_USER): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_N8N_BASIC_PASS): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    async def _test_webhook(
        base_url: str, webhook_path: str, user: str, password: str
    ) -> bool:
        """Quick health check — POST a minimal payload to the webhook.

        Sends a simple ping message. A working endpoint returns 200.
        Any non-401 response proves connectivity; 401 = bad creds.
        """
        url = f"{base_url.rstrip('/')}/{webhook_path.lstrip('/')}"
        auth = aiohttp.BasicAuth(login=user, password=password)
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={"chatInput": "ping", "sessionId": "__healthcheck__"},
                    auth=auth,
                ) as resp:
                    return resp.status == 200
        except Exception as exc:
            _LOGGER.warning("Webhook test failed: %s", exc)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return HAMCPClientOptionsFlow()


class HAMCPClientOptionsFlow(config_entries.OptionsFlow):
    """Options flow — allows updating credentials and history settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        current = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_N8N_BASE_URL,
                        default=current.get(CONF_N8N_BASE_URL, ""),
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Required(
                        CONF_N8N_WEBHOOK_PATH,
                        default=current.get(CONF_N8N_WEBHOOK_PATH, ""),
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        CONF_N8N_BASIC_USER,
                        default=current.get(CONF_N8N_BASIC_USER, ""),
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_N8N_BASIC_PASS): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
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
                            min=1, max=365, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )
