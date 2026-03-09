"""HA MCP Client integration for Home Assistant."""

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, Event, callback
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_ENABLE_MCP_SERVER,
    CONF_ENABLE_CONVERSATION,
    CONF_LLM_PROVIDERS,
    CONF_ACTIVE_LLM_PROVIDER,
    SERVICE_CLEAR_HISTORY,
    SERVICE_EXPORT_HISTORY,
    ATTR_USER_ID,
    PANEL_URL,
    PANEL_TITLE,
    PANEL_ICON,
    INPUT_TEXT_USER,
    INPUT_TEXT_AI,
    NANOBOT_DIR_NAME,
)
from .config_flow import async_migrate_entry  # noqa: F401 — HA discovers this
from .mcp.server import MCPServer
from .mcp.tools import ToolRegistry
from .conversation_recorder import ConversationRecorder
from .nanobot import MemoryStore, SkillsLoader, CronService
from .views import (
    ConversationsListView,
    ConversationDetailView,
    ConversationMessagesView,
    MemoryView,
    MemorySectionView,
    MemorySearchView,
    MemoryConsolidateView,
    SkillsListView,
    SkillDetailView,
    CronJobsListView,
    CronJobDetailView,
    CronJobTriggerView,
    CronToAutomationView,
    CronBlueprintsListView,
    CronBlueprintsInstallView,
    LLMProvidersView,
    ActiveLLMView,
    SettingsView,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CONVERSATION,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]
# Platforms that should always be set up, even if conversation is disabled
ALWAYS_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA MCP Client from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create tool registry
    tool_registry = ToolRegistry(hass)

    # Initialize nanobot modules
    nanobot_dir = Path(hass.config.path(NANOBOT_DIR_NAME))
    memory_store = MemoryStore(hass, nanobot_dir)
    await memory_store.async_setup()
    skills_loader = SkillsLoader(hass, nanobot_dir / "skills")
    await skills_loader.async_setup()
    cron_service = CronService(hass, nanobot_dir / "cron")
    await cron_service.async_setup()

    # Initialize runtime_settings from active LLM provider
    runtime_settings: dict[str, Any] = {}
    providers = entry.data.get(CONF_LLM_PROVIDERS, [])
    active_id = entry.data.get(CONF_ACTIVE_LLM_PROVIDER, "")
    active_provider = None
    for p in providers:
        if p.get("id") == active_id:
            active_provider = p
            break
    if not active_provider and providers:
        active_provider = providers[0]
    if active_provider:
        runtime_settings["ai_service"] = active_provider.get("provider", "openai")
        runtime_settings["model"] = active_provider.get("model", "")
        runtime_settings["api_key"] = active_provider.get("api_key", "")
        runtime_settings["base_url"] = active_provider.get("base_url")

    # Store data for this entry
    data: dict[str, Any] = {
        "tool_registry": tool_registry,
        "memory_store": memory_store,
        "skills_loader": skills_loader,
        "cron_service": cron_service,
        "enable_mcp_server": entry.data.get(CONF_ENABLE_MCP_SERVER, True),
        "enable_conversation": entry.data.get(CONF_ENABLE_CONVERSATION, True),
        "runtime_settings": runtime_settings,
    }

    try:
        # Setup MCP Server if enabled (shares tool_registry)
        if data["enable_mcp_server"]:
            mcp_server = MCPServer(hass, tool_registry=tool_registry)
            await mcp_server.start()
            data["mcp_server"] = mcp_server

        # Setup Conversation Recorder
        _LOGGER.debug("Setting up Conversation Recorder for entry %s", entry.entry_id)
        recorder = ConversationRecorder(hass, entry.data)
        await recorder.async_setup()
        data["recorder"] = recorder

        hass.data[DOMAIN][entry.entry_id] = data

        # Setup platforms
        platforms_to_setup = list(ALWAYS_PLATFORMS)
        if data["enable_conversation"]:
            platforms_to_setup.append(Platform.CONVERSATION)
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)

        # Register services
        await _async_register_services(hass)

        # Register REST API views (idempotent – HA ignores duplicates)
        hass.http.register_view(ConversationsListView())
        hass.http.register_view(ConversationDetailView())
        hass.http.register_view(ConversationMessagesView())
        hass.http.register_view(MemoryView())
        hass.http.register_view(MemorySearchView())
        hass.http.register_view(MemoryConsolidateView())
        hass.http.register_view(MemorySectionView())
        hass.http.register_view(SkillsListView())
        hass.http.register_view(SkillDetailView())
        hass.http.register_view(CronJobsListView())
        hass.http.register_view(CronJobTriggerView())
        hass.http.register_view(CronJobDetailView())
        hass.http.register_view(CronToAutomationView())
        hass.http.register_view(CronBlueprintsListView())
        hass.http.register_view(CronBlueprintsInstallView())
        hass.http.register_view(LLMProvidersView())
        hass.http.register_view(ActiveLLMView())
        hass.http.register_view(SettingsView())

        # Register static frontend path + sidebar panel
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(f"/{DOMAIN}/panel", str(frontend_dir), False)]
        )
        # Use built-in iframe panel
        async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL,
            config={"url": f"/{DOMAIN}/panel/index.html"},
            require_admin=False,
        )

        # Setup input_text state listener for bidirectional sync
        await _async_setup_input_text_listener(hass, data)

        # Listen for options updates
        entry.async_on_unload(entry.add_update_listener(async_update_options))

        return True

    except Exception:
        # Clean up anything that was already started
        if "mcp_server" in data:
            await data["mcp_server"].stop()
        if "recorder" in data:
            await data["recorder"].async_unload()
        if "cron_service" in data:
            await data["cron_service"].async_stop()
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)

    if data:
        # Stop MCP Server
        if "mcp_server" in data:
            await data["mcp_server"].stop()

        # Unload recorder
        if "recorder" in data:
            await data["recorder"].async_unload()

        # Stop cron service
        if "cron_service" in data:
            await data["cron_service"].async_stop()

        # Unload platforms
        platforms_to_unload = list(ALWAYS_PLATFORMS)
        if data.get("enable_conversation"):
            platforms_to_unload.append(Platform.CONVERSATION)
        await hass.config_entries.async_unload_platforms(entry, platforms_to_unload)

    hass.data[DOMAIN].pop(entry.entry_id, None)

    # Remove services and panel if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_HISTORY)
        hass.services.async_remove(DOMAIN, SERVICE_EXPORT_HISTORY)
        async_remove_panel(hass, PANEL_URL)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Skip reload if the update was from runtime entity persistence
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if isinstance(data, dict) and data.pop("_skip_reload", False):
        return
    await hass.config_entries.async_reload(entry.entry_id)


def _get_recorder(hass: HomeAssistant) -> ConversationRecorder:
    """Get the first available recorder from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "recorder" in entry_data:
            return entry_data["recorder"]
    raise HomeAssistantError("No conversation recorder available")


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_clear_history(call: ServiceCall) -> None:
        """Handle clear history service call."""
        recorder = _get_recorder(hass)
        user_id = call.data.get(ATTR_USER_ID)
        caller_user_id = call.context.user_id

        # If no user_id provided, try to get from context
        if not user_id and caller_user_id:
            user_id = caller_user_id

        # Authorization check: only allow clearing own history or if admin
        if user_id and caller_user_id and user_id != caller_user_id:
            user = await hass.auth.async_get_user(caller_user_id)
            if not user or not user.is_admin:
                _LOGGER.warning(
                    "User %s attempted to clear history for user %s without permission",
                    caller_user_id,
                    user_id,
                )
                raise HomeAssistantError("Not authorized to clear other user's history")

        deleted = await recorder.clear_conversation_history(user_id=user_id)
        _LOGGER.info("Cleared %d conversation records for user %s", deleted, user_id)

    async def handle_export_history(call: ServiceCall) -> dict[str, Any]:
        """Handle export history service call."""
        recorder = _get_recorder(hass)
        user_id = call.data.get(ATTR_USER_ID)
        format_type = call.data.get("format", "json")
        caller_user_id = call.context.user_id

        # If no user_id provided, try to get from context
        if not user_id and caller_user_id:
            user_id = caller_user_id

        # Authorization check: only allow exporting own history or if admin
        if user_id and caller_user_id and user_id != caller_user_id:
            user = await hass.auth.async_get_user(caller_user_id)
            if not user or not user.is_admin:
                _LOGGER.warning(
                    "User %s attempted to export history for user %s without permission",
                    caller_user_id,
                    user_id,
                )
                raise HomeAssistantError("Not authorized to export other user's history")

        export = await recorder.export_conversation_history(
            user_id=user_id, format=format_type
        )

        return {"export": export}

    # Register services if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_HISTORY,
            handle_clear_history,
            schema=vol.Schema(
                {
                    vol.Optional(ATTR_USER_ID): str,
                }
            ),
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


async def _async_setup_input_text_listener(
    hass: HomeAssistant, data: dict[str, Any]
) -> None:
    """Listen for input_text.mcp_user_input changes and trigger AI conversation."""
    # Flag to prevent infinite loop (we write → triggers event → we write again)
    _syncing = {"active": False}

    @callback
    def _on_input_text_change(event: Event) -> None:
        """Handle input_text state change."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or not new_state.state:
            return

        entity_id = new_state.entity_id
        if entity_id != INPUT_TEXT_USER:
            return

        # Skip if we triggered this change ourselves
        if _syncing["active"]:
            return

        # Skip if state hasn't actually changed
        if old_state and old_state.state == new_state.state:
            return

        user_text = new_state.state.strip()
        if not user_text:
            return

        hass.async_create_task(_process_input_text_message(hass, user_text, _syncing))

    hass.bus.async_listen("state_changed", _on_input_text_change)

    # Initialize input_text states so they appear in HA
    hass.states.async_set(
        INPUT_TEXT_USER,
        "",
        {"friendly_name": "MCP 使用者輸入", "icon": "mdi:account-voice"},
    )
    hass.states.async_set(
        INPUT_TEXT_AI,
        "",
        {"friendly_name": "MCP AI 回覆", "icon": "mdi:robot"},
    )


async def _process_input_text_message(
    hass: HomeAssistant, text: str, syncing: dict
) -> None:
    """Process a message received from input_text and send to AI."""
    from .views import _get_agent_id

    agent_id = _get_agent_id(hass)
    if not agent_id:
        _LOGGER.warning("No conversation agent found for input_text processing")
        return

    try:
        result = await hass.services.async_call(
            "conversation",
            "process",
            {"text": text, "agent_id": agent_id},
            blocking=True,
            return_response=True,
        )

        ai_response = ""
        if result and "response" in result:
            speech = result["response"].get("speech", {})
            if isinstance(speech, dict):
                ai_response = speech.get("plain", {}).get("speech", "")
            elif isinstance(speech, str):
                ai_response = speech

        # Update AI response entity (with loop prevention)
        syncing["active"] = True
        try:
            hass.states.async_set(
                INPUT_TEXT_AI,
                ai_response[:255],
                {"friendly_name": "MCP AI 回覆", "icon": "mdi:robot"},
            )
        finally:
            syncing["active"] = False

    except Exception as e:
        _LOGGER.error("Error processing input_text message: %s", e)
