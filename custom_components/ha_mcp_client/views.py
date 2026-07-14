"""REST API views for HA MCP Client chat panel (n8n mode)."""

import logging
import uuid
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .n8n_proxy import send_chat

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


# ── Conversation CRUD ────────────────────────────────────────


class ConversationsListView(HomeAssistantView):
    """View to list or create conversations."""

    url = f"/api/{DOMAIN}/conversations"
    name = f"api:{DOMAIN}:conversations"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
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

        title = body.get("title", "\u65b0\u5c0d\u8a71")
        conversation_id = str(uuid.uuid4())

        result = await recorder.create_conversation(conversation_id, user_id, title)
        return self.json(result, status_code=201)


class ConversationDetailView(HomeAssistantView):
    """View for a single conversation (PATCH / DELETE)."""

    url = f"/api/{DOMAIN}/conversations/{{conversation_id}}"
    name = f"api:{DOMAIN}:conversation_detail"
    requires_auth = True

    async def patch(self, request: web.Request, conversation_id: str) -> web.Response:
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

        ok = await recorder.update_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=body.get("title"),
            is_archived=body.get("is_archived"),
        )
        if ok:
            return self.json({"success": True})
        return self.json_message("Not found", status_code=404)

    async def delete(self, request: web.Request, conversation_id: str) -> web.Response:
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
        if ok:
            return self.json({"success": True})
        return self.json_message("Not found", status_code=404)


class ConversationMessagesView(HomeAssistantView):
    """View to get messages or send a new message (streaming)."""

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
        """Send a message to n8n and return the AI response as JSON."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

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

        response_text = await send_chat(hass, message, conversation_id)

        # Record to local history — await to ensure persistence before responding
        await _record_exchange(recorder, user_id, conversation_id, message, response_text)

        return self.json({
            "user_message": message,
            "ai_response": response_text,
            "conversation_id": conversation_id,
        })


async def _record_exchange(
    recorder,
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """Record user+assistant messages to local history and update conversation metadata."""
    try:
        await recorder.record_message(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        # Auto-title on first message
        conv = await recorder.get_conversation(conversation_id, user_id)
        if conv and conv.get("title") == "\u65b0\u5c0d\u8a71" and user_message:
            await recorder.update_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                title=user_message[:50],
            )
        await recorder.touch_conversation(conversation_id)
    except Exception as exc:
        _LOGGER.error("Failed to record exchange: %s", exc)
