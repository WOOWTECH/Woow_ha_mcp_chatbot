"""HA MCP Client integration — n8n chat panel mode."""

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_N8N_BASE_URL,
    CONF_N8N_WEBHOOK_PATH,
    CONF_N8N_BASIC_USER,
    CONF_N8N_BASIC_PASS,
    SERVICE_CLEAR_HISTORY,
    SERVICE_EXPORT_HISTORY,
    ATTR_USER_ID,
    PANEL_URL,
    PANEL_TITLE,
    PANEL_ICON,
)
from .conversation_recorder import ConversationRecorder
from .views import (
    ConversationsListView,
    ConversationDetailView,
    ConversationMessagesView,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA MCP Client from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Expose n8n connection config for n8n_proxy.py
    config = dict(entry.data)

    # Setup Conversation Recorder (display-only log)
    recorder = ConversationRecorder(hass, config)
    await recorder.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "recorder": recorder,
    }

    # Register REST API views (idempotent — HA ignores duplicates)
    hass.http.register_view(ConversationsListView())
    hass.http.register_view(ConversationDetailView())
    hass.http.register_view(ConversationMessagesView())

    # Register static frontend path + sidebar panel
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/{DOMAIN}/panel", str(frontend_dir), False)]
    )
    async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL,
        config={"url": f"/{DOMAIN}/panel/index.html"},
        require_admin=False,
    )

    # Register services
    await _async_register_services(hass)

    # Listen for options updates → reload
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)

    if data:
        recorder = data.get("recorder")
        if recorder:
            await recorder.async_unload()

    # Remove services and panel if no more entries
    if not hass.data[DOMAIN]:
        for svc in (SERVICE_CLEAR_HISTORY, SERVICE_EXPORT_HISTORY):
            if hass.services.has_service(DOMAIN, svc):
                hass.services.async_remove(DOMAIN, svc)
        async_remove_panel(hass, PANEL_URL)

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _get_recorder(hass: HomeAssistant) -> ConversationRecorder:
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "recorder" in entry_data:
            return entry_data["recorder"]
    raise HomeAssistantError("No conversation recorder available")


async def _async_register_services(hass: HomeAssistant) -> None:
    async def handle_clear_history(call: ServiceCall) -> None:
        recorder = _get_recorder(hass)
        user_id = call.data.get(ATTR_USER_ID) or call.context.user_id
        if user_id:
            deleted = await recorder.clear_conversation_history(user_id=user_id)
            _LOGGER.info("Cleared %d conversation records for user %s", deleted, user_id)

    async def handle_export_history(call: ServiceCall) -> dict[str, Any]:
        recorder = _get_recorder(hass)
        user_id = call.data.get(ATTR_USER_ID) or call.context.user_id
        fmt = call.data.get("format", "json")
        export = await recorder.export_conversation_history(user_id=user_id, format=fmt)
        return {"export": export}

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_HISTORY,
            handle_clear_history,
            schema=vol.Schema({vol.Optional(ATTR_USER_ID): str}),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_HISTORY,
            handle_export_history,
            schema=vol.Schema(
                {
                    vol.Optional(ATTR_USER_ID): str,
                    vol.Optional("format", default="json"): vol.In(["json", "markdown"]),
                }
            ),
        )
