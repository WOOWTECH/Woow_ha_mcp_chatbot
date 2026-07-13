"""Constants for HA MCP Client integration (n8n chat panel mode)."""

from typing import Final

DOMAIN: Final = "ha_mcp_client"

# ── n8n connection config keys ──
CONF_N8N_BASE_URL: Final = "n8n_base_url"
CONF_N8N_API_KEY: Final = "n8n_api_key"
CONF_N8N_WEBHOOK_PATH: Final = "n8n_webhook_path"
CONF_N8N_BASIC_USER: Final = "n8n_basic_user"
CONF_N8N_BASIC_PASS: Final = "n8n_basic_pass"

# ── Conversation history ──
CONF_ENABLE_CONVERSATION_HISTORY: Final = "enable_conversation_history"
CONF_HISTORY_RETENTION_DAYS: Final = "history_retention_days"
DEFAULT_HISTORY_RETENTION_DAYS: Final = 30

# ── Services ──
SERVICE_CLEAR_HISTORY: Final = "clear_conversation_history"
SERVICE_EXPORT_HISTORY: Final = "export_conversation_history"

# ── Attributes ──
ATTR_USER_ID: Final = "user_id"

# ── Chat Panel ──
PANEL_URL: Final = "ha-mcp-chat"
PANEL_TITLE: Final = "AI \u804a\u5929"
PANEL_ICON: Final = "mdi:robot-happy-outline"
