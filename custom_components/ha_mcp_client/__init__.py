"""HA MCP Client integration for Home Assistant."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_ENABLE_MCP_SERVER,
    CONF_ENABLE_CONVERSATION,
    SERVICE_CLEAR_HISTORY,
    SERVICE_EXPORT_HISTORY,
    ATTR_USER_ID,
)
from .mcp.server import MCPServer
from .mcp.tools import ToolRegistry
from .conversation_recorder import ConversationRecorder

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA MCP Client from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create tool registry
    tool_registry = ToolRegistry(hass)

    # Store data for this entry
    data: dict[str, Any] = {
        "tool_registry": tool_registry,
        "enable_mcp_server": entry.data.get(CONF_ENABLE_MCP_SERVER, True),
        "enable_conversation": entry.data.get(CONF_ENABLE_CONVERSATION, True),
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
        if data["enable_conversation"]:
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register services
        await _async_register_services(hass)

        # Listen for options updates
        entry.async_on_unload(entry.add_update_listener(async_update_options))

        return True

    except Exception:
        # Clean up anything that was already started
        if "mcp_server" in data:
            await data["mcp_server"].stop()
        if "recorder" in data:
            await data["recorder"].async_unload()
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

        # Unload platforms
        if data.get("enable_conversation"):
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    hass.data[DOMAIN].pop(entry.entry_id, None)

    # Remove services if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_HISTORY)
        hass.services.async_remove(DOMAIN, SERVICE_EXPORT_HISTORY)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
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
