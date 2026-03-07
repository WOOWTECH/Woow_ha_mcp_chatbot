"""REST API views for HA MCP Client chat panel."""

import logging
import uuid
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_recorder(hass: HomeAssistant):
    """Get the first available recorder from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "recorder" in entry_data:
            return entry_data["recorder"]
    return None


def _get_user_id(request: web.Request) -> str | None:
    """Extract user_id from the authenticated request."""
    user = request.get("hass_user")
    if user:
        return user.id
    return None


class ConversationsListView(HomeAssistantView):
    """View to list or create conversations."""

    url = f"/api/{DOMAIN}/conversations"
    name = f"api:{DOMAIN}:conversations"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """List all conversations for the current user."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        conversations = await recorder.list_conversations(user_id)
        return self.json(conversations)

    async def post(self, request: web.Request) -> web.Response:
        """Create a new conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            body = {}

        title = body.get("title", "新對話")
        conv_id = str(uuid.uuid4())

        result = await recorder.create_conversation(
            conversation_id=conv_id,
            user_id=user_id,
            title=title,
        )
        if not result:
            return self.json_message("Failed to create conversation", status_code=500)

        return self.json(result, status_code=201)


class ConversationDetailView(HomeAssistantView):
    """View to update or delete a single conversation."""

    url = f"/api/{DOMAIN}/conversations/{{conversation_id}}"
    name = f"api:{DOMAIN}:conversation_detail"
    requires_auth = True

    async def patch(self, request: web.Request, conversation_id: str) -> web.Response:
        """Update conversation title or archive it."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        title = body.get("title")
        is_archived = body.get("is_archived")

        ok = await recorder.update_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            is_archived=is_archived,
        )
        if not ok:
            return self.json_message("Conversation not found", status_code=404)
        return self.json({"success": True})

    async def delete(self, request: web.Request, conversation_id: str) -> web.Response:
        """Soft-delete a conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        ok = await recorder.update_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            is_archived=True,
        )
        if not ok:
            return self.json_message("Conversation not found", status_code=404)
        return self.json({"success": True})


class ConversationMessagesView(HomeAssistantView):
    """View to get or send messages in a conversation."""

    url = f"/api/{DOMAIN}/conversations/{{conversation_id}}/messages"
    name = f"api:{DOMAIN}:conversation_messages"
    requires_auth = True

    async def get(self, request: web.Request, conversation_id: str) -> web.Response:
        """Get messages for a conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        # Verify ownership
        conv = await recorder.get_conversation(conversation_id, user_id)
        if not conv:
            return self.json_message("Conversation not found", status_code=404)

        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))

        messages = await recorder.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
        )
        return self.json(messages)

    async def post(self, request: web.Request, conversation_id: str) -> web.Response:
        """Send a message and get AI response."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        # Verify ownership
        conv = await recorder.get_conversation(conversation_id, user_id)
        if not conv:
            return self.json_message("Conversation not found", status_code=404)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        message = body.get("message", "").strip()
        if not message:
            return self.json_message("Message is required", status_code=400)

        # Use HA conversation API to process the message
        try:
            result = await hass.services.async_call(
                "conversation",
                "process",
                {
                    "text": message,
                    "agent_id": _get_agent_id(hass),
                    "conversation_id": conversation_id,
                },
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

            # Update conversation title if it's the first message
            if conv.get("title") == "新對話" and message:
                new_title = message[:50]
                await recorder.update_conversation(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    title=new_title,
                )

            # Touch updated_at
            await recorder.touch_conversation(conversation_id)

            # Update input_text entities
            await _sync_input_text(hass, message, ai_response)

            return self.json({
                "user_message": message,
                "ai_response": ai_response,
                "conversation_id": conversation_id,
            })

        except Exception as e:
            _LOGGER.error("Error processing message: %s", e, exc_info=True)
            return self.json_message(
                f"Error processing message: {str(e)}", status_code=500
            )


def _get_agent_id(hass: HomeAssistant) -> str | None:
    """Get the HA MCP Client conversation agent ID."""
    for state in hass.states.async_all("conversation"):
        if DOMAIN in state.entity_id:
            return state.entity_id
    return None


async def _sync_input_text(
    hass: HomeAssistant, user_message: str, ai_response: str
) -> None:
    """Sync latest messages to input_text entities."""
    from .const import INPUT_TEXT_USER, INPUT_TEXT_AI

    try:
        # Set state directly — the entities may not exist via input_text component,
        # but we can set state for any entity_id
        hass.states.async_set(
            INPUT_TEXT_USER,
            user_message[:255],
            {"friendly_name": "MCP 使用者輸入", "icon": "mdi:account-voice"},
        )
        hass.states.async_set(
            INPUT_TEXT_AI,
            ai_response[:255],
            {"friendly_name": "MCP AI 回覆", "icon": "mdi:robot"},
        )
    except Exception as e:
        _LOGGER.warning("Failed to sync input_text: %s", e)
