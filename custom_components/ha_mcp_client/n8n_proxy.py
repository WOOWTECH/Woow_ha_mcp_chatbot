"""Proxy to n8n Webhook node (non-streaming, single JSON response)."""

import logging

import aiohttp

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_N8N_BASE_URL,
    CONF_N8N_WEBHOOK_PATH,
    CONF_N8N_BASIC_USER,
    CONF_N8N_BASIC_PASS,
)

_LOGGER = logging.getLogger(__name__)


def _get_config(hass: HomeAssistant) -> dict | None:
    """Get n8n config from the first available config entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "config" in entry_data:
            return entry_data["config"]
    return None


async def send_chat(
    hass: HomeAssistant,
    chat_input: str,
    session_id: str,
) -> str:
    """Send a message to n8n Webhook node and return the AI response text.

    The Webhook node (responseMode=lastNode, responseData=firstEntryJson)
    returns a single JSON object from the last node in the workflow.
    """
    cfg = _get_config(hass)
    if not cfg:
        return "[error] n8n 連線尚未設定"

    base_url = cfg[CONF_N8N_BASE_URL].rstrip("/")
    webhook_path = cfg[CONF_N8N_WEBHOOK_PATH].lstrip("/")
    url = f"{base_url}/{webhook_path}"

    auth = aiohttp.BasicAuth(
        login=cfg[CONF_N8N_BASIC_USER],
        password=cfg[CONF_N8N_BASIC_PASS],
    )

    payload = {
        "chatInput": chat_input,
        "sessionId": session_id,
    }

    _LOGGER.debug("n8n proxy → %s  sessionId=%s", url, session_id)

    timeout = aiohttp.ClientTimeout(total=300)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, auth=auth) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.error("n8n webhook %s → %s", resp.status, body[:500])
                    return f"[error] n8n 回傳 HTTP {resp.status}"

                data = await resp.json()
                _LOGGER.debug("n8n response: %s", str(data)[:500])

                # Extract response text — try common field names
                if isinstance(data, dict):
                    return (
                        data.get("output")
                        or data.get("text")
                        or data.get("response")
                        or str(data)
                    )
                if isinstance(data, list) and data:
                    first = data[0]
                    if isinstance(first, dict):
                        return (
                            first.get("output")
                            or first.get("text")
                            or first.get("response")
                            or str(first)
                        )
                return str(data)

    except TimeoutError:
        _LOGGER.error("n8n proxy timeout for session %s", session_id)
        return "[error] n8n 回應逾時"
    except aiohttp.ClientError as exc:
        _LOGGER.error("n8n proxy connection error: %s", exc)
        return f"[error] 無法連線 n8n: {exc}"
