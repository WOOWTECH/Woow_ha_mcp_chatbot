"""Constants for HA MCP Client integration."""

from typing import Final

DOMAIN: Final = "ha_mcp_client"

# Config Keys
CONF_AI_SERVICE: Final = "ai_service"
CONF_API_KEY: Final = "api_key"
CONF_MODEL: Final = "model"
CONF_BASE_URL: Final = "base_url"
CONF_OLLAMA_HOST: Final = "ollama_host"
CONF_ENABLE_MCP_SERVER: Final = "enable_mcp_server"
CONF_ENABLE_CONVERSATION: Final = "enable_conversation"
CONF_MCP_SERVER_PORT: Final = "mcp_server_port"
CONF_ENABLE_CONVERSATION_HISTORY: Final = "enable_conversation_history"
CONF_HISTORY_RETENTION_DAYS: Final = "history_retention_days"
CONF_SYSTEM_PROMPT: Final = "system_prompt"
CONF_MAX_TOOL_CALLS: Final = "max_tool_calls"

# Multi-LLM Provider Config Keys
CONF_LLM_PROVIDERS: Final = "llm_providers"
CONF_ACTIVE_LLM_PROVIDER: Final = "active_llm_provider"

# AI Service Types
AI_SERVICE_ANTHROPIC: Final = "anthropic"
AI_SERVICE_OPENAI: Final = "openai"
AI_SERVICE_OLLAMA: Final = "ollama"
AI_SERVICE_OPENAI_COMPATIBLE: Final = "openai_compatible"

AI_SERVICES: Final = [
    AI_SERVICE_ANTHROPIC,
    AI_SERVICE_OPENAI,
    AI_SERVICE_OLLAMA,
    AI_SERVICE_OPENAI_COMPATIBLE,
]

# Default Values
DEFAULT_MCP_SERVER_PORT: Final = 8087
DEFAULT_HISTORY_RETENTION_DAYS: Final = 30
DEFAULT_MAX_TOOL_CALLS: Final = 10
DEFAULT_ANTHROPIC_MODEL: Final = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL: Final = "gpt-5.4"
DEFAULT_OLLAMA_HOST: Final = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL: Final = "llama3.2"

# Default System Prompt (basic version)
DEFAULT_SYSTEM_PROMPT: Final = """You are a helpful Home Assistant AI assistant.
You can control smart home devices, create automations, check device states,
and help users manage their smart home.

When users ask you to do something:
1. First understand what they want to achieve
2. Use the available tools to accomplish the task
3. Provide clear feedback on what was done

Be concise but helpful. If you're unsure about something, ask for clarification."""

# Auto-appended system prompt addon for resource creation
# This is ALWAYS appended to any system prompt to ensure proper behavior
SYSTEM_PROMPT_ADDON: Final = """

## Creating Resources (Scenes, Automations, Scripts)

IMPORTANT: When user asks to create a scene, automation, or script, you MUST follow these steps:

### Step 1: Query Entities First
- ALWAYS use `search_entities` tool first to find relevant entities
- Filter by domain if user mentioned specific device types (e.g., lights, switches)
- Filter by area_id if user mentioned a specific area/room
- If user says "all" or doesn't specify scope, query without filters

### Step 2: Determine User Intent
- "全開/turn on all/open all": Set all queried entities to ON/OPEN state
- "全關/turn off all/close all": Set all queried entities to OFF/CLOSE state
- Specific settings: Use brightness, temperature, or other values mentioned

### Step 3: Build Complete Parameters

For create_scene (REQUIRED: name AND entities):
```json
{
  "name": "Scene Name",
  "entities": {
    "light.living_room": {"state": "on", "brightness": 255},
    "switch.fan": {"state": "on"},
    "cover.blinds": {"state": "open"}
  }
}
```

For create_automation (REQUIRED: alias AND trigger AND action):
```json
{
  "alias": "Automation Name",
  "trigger": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
  "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}]
}
```

For create_script (REQUIRED: name AND sequence):
```json
{
  "name": "Script Name",
  "sequence": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}]
}
```

### Example Workflow

User: "建立一個全開情境"
1. Call search_entities() to get all entities
2. Filter for controllable entities (light.*, switch.*, cover.*, fan.*, climate.*)
3. Build entities dict: {"light.xxx": {"state": "on"}, "switch.xxx": {"state": "on"}, ...}
4. Call create_scene(name="全開", entities={...})

User: "建立客廳燈光全關情境"
1. Call search_entities(domain="light") or search_entities(area_id="living_room")
2. Build entities dict with all matched lights set to "off"
3. Call create_scene(name="客廳燈光全關", entities={...})

User: "建立一個自動化，當有人移動時開燈"
1. Call search_entities(domain="binary_sensor") to find motion sensors
2. Call search_entities(domain="light") to find lights
3. Build trigger with motion sensor entity_id
4. Build action to turn on light
5. Call create_automation(alias="動作感應開燈", trigger=[...], action=[...])

NEVER call create_scene, create_automation, or create_script without the required parameters!"""

# Conversation Entity
CONVERSATION_ENTITY_ID: Final = f"conversation.{DOMAIN}"

# Events
EVENT_CONVERSATION_MESSAGE: Final = f"{DOMAIN}_conversation_message"

# Services
SERVICE_CLEAR_HISTORY: Final = "clear_conversation_history"
SERVICE_EXPORT_HISTORY: Final = "export_conversation_history"

# Attributes
ATTR_USER_ID: Final = "user_id"
ATTR_CONVERSATION_ID: Final = "conversation_id"
ATTR_MESSAGE: Final = "message"
ATTR_RESPONSE: Final = "response"
ATTR_TOOL_CALLS: Final = "tool_calls"
ATTR_TIMESTAMP: Final = "timestamp"

# Chat Panel
PANEL_URL: Final = "ha-mcp-chat"
PANEL_TITLE: Final = "AI 聊天"
PANEL_ICON: Final = "mdi:robot-happy-outline"
PANEL_FRONTEND_PATH: Final = f"/{DOMAIN}/panel"

# input_text entities
INPUT_TEXT_USER: Final = f"input_text.{DOMAIN}_user_input"
INPUT_TEXT_AI: Final = f"input_text.{DOMAIN}_ai_response"

# ── AI Model Parameters ──
CONF_TEMPERATURE: Final = "temperature"
CONF_MAX_TOKENS: Final = "max_tokens"
DEFAULT_TEMPERATURE: Final = 0.7
DEFAULT_MAX_TOKENS: Final = 4096

# ── Reasoning Effort ──
CONF_REASONING_EFFORT: Final = "reasoning_effort"
DEFAULT_REASONING_EFFORT: Final = "medium"
REASONING_EFFORTS: Final = ["low", "medium", "high"]

# ── Nanobot Memory ──
CONF_MEMORY_WINDOW: Final = "memory_window"
DEFAULT_MEMORY_WINDOW: Final = 50
NANOBOT_DIR_NAME: Final = "nanobot"
