# HA MCP Client — Home Assistant AI Chatbot

**[English](#english) | [繁體中文](#繁體中文)**

---

## English

### Overview

HA MCP Client is a custom Home Assistant integration that adds a full-featured AI chatbot with deep smart home control capabilities. It connects to large language models (Anthropic Claude, OpenAI GPT, Ollama, or any OpenAI-compatible API) and exposes **62 tools** that let the AI query, control, and manage virtually every aspect of your Home Assistant installation through natural conversation.

### Key Features

- **AI Chat Panel** — A dedicated sidebar panel ("AI 聊天") with conversation history, search, and multi-conversation management
- **62 Smart Home Tools** — Full coverage of Home Assistant service domains including lights, covers, climate, locks, fans, switches, media players, cameras, valves, timers, counters, and more
- **CRUD Operations** — Create, read, update, and delete areas, labels, automations, scripts, scenes, calendar events, and todo items through conversation
- **4 AI Providers** — Anthropic Claude, OpenAI, Ollama (local), and OpenAI-compatible APIs (LM Studio, vLLM, etc.)
- **HA Assist Integration** — Works as a conversation agent in Home Assistant's built-in Assist pipeline
- **MCP Server** — Exposes tools via the Model Context Protocol (SSE) for external MCP clients
- **Persistent History** — Conversation history stored in a local database with configurable retention
- **Bilingual UI** — English and Traditional Chinese interface

### Architecture

```
┌─────────────────────────────────────────────────┐
│                  Home Assistant                  │
│                                                  │
│  ┌──────────┐  ┌────────────┐  ┌─────────────┐  │
│  │ Chat     │  │ HA Assist  │  │ MCP SSE     │  │
│  │ Panel    │  │ Pipeline   │  │ Server      │  │
│  │ (iframe) │  │            │  │ (external)  │  │
│  └────┬─────┘  └─────┬──────┘  └──────┬──────┘  │
│       │              │                │          │
│       └──────────────┼────────────────┘          │
│                      ▼                           │
│           ┌──────────────────┐                   │
│           │ Conversation     │                   │
│           │ Entity           │                   │
│           └────────┬─────────┘                   │
│                    ▼                             │
│  ┌─────────────────────────────────────────┐     │
│  │ AI Service (Anthropic/OpenAI/Ollama)    │     │
│  │ + Tool Calling Loop (max N iterations)  │     │
│  └─────────────────┬───────────────────────┘     │
│                    ▼                             │
│  ┌─────────────────────────────────────────┐     │
│  │ Tool Registry — 62 Tools                │     │
│  │ helpers.py (implementations)            │     │
│  │ registry.py (schemas + handlers)        │     │
│  └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

### Installation

#### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "HA MCP Client" and install
3. Restart Home Assistant
4. Go to **Settings > Devices & Services > Add Integration > HA MCP Client**

#### Manual

1. Copy the `custom_components/ha_mcp_client` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings > Devices & Services > Add Integration > HA MCP Client**

### Configuration

The setup wizard guides you through 4 steps:

| Step | Options |
|------|---------|
| **1. Features** | Enable MCP Server, Enable Conversation Agent |
| **2. MCP Server** | Server port (default: 8087) |
| **3. AI Service** | Provider selection, API key, Model, Base URL |
| **4. Conversation** | History on/off, Retention days, System prompt, Max tool calls |

**Supported AI Models:**

| Provider | Models |
|----------|--------|
| **Anthropic** | claude-sonnet-4-20250514, claude-opus-4-20250514, claude-3.5-sonnet, claude-3.5-haiku, claude-3-opus |
| **OpenAI** | gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-4, gpt-3.5-turbo |
| **Ollama** | llama3.2, llama3.1, mistral, mixtral, codellama, phi3, gemma2 |
| **OpenAI Compatible** | Any model via custom base URL (LM Studio, vLLM, etc.) |

### Tools (62 Total)

<details>
<summary><strong>Entity & Service (4)</strong></summary>

| Tool | Description |
|------|-------------|
| `get_entity_state` | Get current state and attributes of any entity |
| `search_entities` | Search entities by name, domain, area, or device |
| `call_service` | Call any Home Assistant service directly |
| `list_services` | List all available services and domains |

</details>

<details>
<summary><strong>Area & Label Management (8)</strong></summary>

| Tool | Description |
|------|-------------|
| `list_areas` | List all areas |
| `create_area` | Create a new area |
| `update_area` | Update area name, icon, aliases |
| `delete_area` | Delete an area |
| `list_labels` | List all labels |
| `create_label` | Create a new label |
| `update_label` | Update label properties |
| `delete_label` | Delete a label |

</details>

<details>
<summary><strong>Entity Assignment (3)</strong></summary>

| Tool | Description |
|------|-------------|
| `assign_entity_to_area` | Assign an entity to an area |
| `assign_entity_to_labels` | Assign labels to an entity |
| `list_devices` | List devices, optionally filtered by area |

</details>

<details>
<summary><strong>Automation (6)</strong></summary>

| Tool | Description |
|------|-------------|
| `list_automations` | List all automations with status |
| `create_automation` | Create a new automation (YAML) |
| `update_automation` | Update automation trigger/action/mode |
| `delete_automation` | Delete an automation |
| `toggle_automation` | Enable or disable an automation |
| `trigger_automation` | Manually trigger an automation |

</details>

<details>
<summary><strong>Script (5)</strong></summary>

| Tool | Description |
|------|-------------|
| `list_scripts` | List all scripts |
| `create_script` | Create a new script (YAML) |
| `update_script` | Update script sequence/mode/fields |
| `delete_script` | Delete a script |
| `run_script` | Execute a script |

</details>

<details>
<summary><strong>Scene (5)</strong></summary>

| Tool | Description |
|------|-------------|
| `list_scenes` | List all scenes |
| `create_scene` | Create a new scene (YAML) |
| `update_scene` | Update scene entities/states |
| `delete_scene` | Delete a scene |
| `activate_scene` | Activate a scene |

</details>

<details>
<summary><strong>Calendar (4)</strong></summary>

| Tool | Description |
|------|-------------|
| `create_calendar_event` | Create a calendar event |
| `list_calendar_events` | List events in a date range |
| `update_calendar_event` | Update an existing event |
| `delete_calendar_event` | Delete a calendar event |

</details>

<details>
<summary><strong>Todo (5)</strong></summary>

| Tool | Description |
|------|-------------|
| `add_todo_item` | Add a todo item |
| `list_todo_items` | List todo items |
| `update_todo_item` | Rename or change status of a todo |
| `remove_todo_item` | Remove a todo item |
| `remove_completed_todo_items` | Remove all completed items |

</details>

<details>
<summary><strong>Device Controls (14)</strong></summary>

| Tool | Description |
|------|-------------|
| `control_light` | On/off/toggle, brightness, color temp, RGB |
| `control_switch` | On/off/toggle switches |
| `control_cover` | Open/close/stop/toggle, position, tilt |
| `control_climate` | HVAC mode, temperature, fan/swing/preset mode, humidity |
| `control_fan` | On/off/toggle, speed, direction, oscillation |
| `control_lock` | Lock/unlock |
| `control_media_player` | Play/pause/stop, volume, source, seek, sound mode |
| `control_camera` | Snapshot, play stream, record |
| `control_timer` | Start/pause/cancel/finish timers |
| `control_counter` | Increment/decrement/reset counters |
| `control_input_helper` | Set input_boolean/number/text/select/datetime |
| `control_valve` | Open/close/stop/toggle, position |
| `control_number` | Set number entity value (with min/max validation) |
| `control_persistent_notification` | Create/dismiss persistent notifications |

</details>

<details>
<summary><strong>Utilities (8)</strong></summary>

| Tool | Description |
|------|-------------|
| `send_notification` | Send notifications via notify services |
| `speak_tts` | Text-to-speech output |
| `manage_backup` | Create Home Assistant backups |
| `list_blueprints` | List automation/script blueprints |
| `import_blueprint` | Import blueprint from URL |
| `control_shopping_list` | Add/remove/complete shopping list items |
| `get_history` | Get historical state changes |
| `system_overview` | Get system overview (entity count, domains, areas) |

</details>

### Usage Examples

**Through the Chat Panel:**

Open the "AI 聊天" sidebar item and start chatting in natural language:

- "Turn off all the lights in the living room"
- "What's the temperature in the bedroom?"
- "Create an automation that turns on the porch light at sunset"
- "Add milk to the shopping list"
- "What happened to the garage door in the last hour?"
- "Set the bedroom curtain to 50% open"

**Through HA Assist:**

Select "HA MCP Client" as the conversation agent in Assist settings, then use the Assist dialog or voice commands.

**Through MCP Protocol:**

Connect any MCP-compatible client to `http://your-ha:8087/sse` to use all 62 tools programmatically.

### Services

| Service | Description |
|---------|-------------|
| `ha_mcp_client.clear_conversation_history` | Clear all conversation history |
| `ha_mcp_client.export_conversation_history` | Export history as JSON or Markdown |

### Project Structure

```
custom_components/ha_mcp_client/
├── __init__.py              # Integration setup, services, panel registration
├── config_flow.py           # Multi-step configuration wizard
├── const.py                 # Constants and defaults
├── conversation.py          # Conversation entity + AI tool-calling loop
├── conversation_recorder.py # Persistent conversation history (SQLite)
├── views.py                 # REST API endpoints for chat panel
├── manifest.json            # Integration metadata
├── services.yaml            # Service definitions
├── frontend/                # Chat panel UI (HTML/JS/CSS)
├── translations/            # en.json, zh-Hant.json
├── ai_services/             # AI provider implementations
│   ├── anthropic.py         # Anthropic Claude
│   ├── openai.py            # OpenAI GPT
│   ├── ollama.py            # Ollama (local)
│   └── openai_compatible.py # OpenAI-compatible APIs
└── mcp/
    ├── server.py            # MCP SSE server for external clients
    └── tools/
        ├── registry.py      # 62 tool definitions + handlers
        └── helpers.py       # Tool implementation logic
```

### Requirements

- Home Assistant 2024.1+
- Python 3.11+
- One of the supported AI providers configured

### License

MIT License

---

## 繁體中文

### 概覽

HA MCP Client 是一個 Home Assistant 自訂整合元件，為你的智慧家庭加入功能完整的 AI 聊天機器人。它連接大型語言模型（Anthropic Claude、OpenAI GPT、Ollama 或任何 OpenAI 相容 API），並提供 **62 個工具**，讓 AI 透過自然對話查詢、控制及管理你的 Home Assistant 系統。

### 主要功能

- **AI 聊天面板** — 專屬的側邊欄面板（「AI 聊天」），支援對話歷史、搜尋與多對話管理
- **62 個智慧家庭工具** — 完整涵蓋 Home Assistant 服務域，包括燈光、窗簾、空調、門鎖、風扇、開關、媒體播放器、攝影機、閥門、計時器、計數器等
- **CRUD 操作** — 透過對話建立、讀取、更新和刪除區域、標籤、自動化、腳本、情境、日曆事件和待辦事項
- **4 種 AI 供應商** — Anthropic Claude、OpenAI、Ollama（本地）和 OpenAI 相容 API（LM Studio、vLLM 等）
- **HA Assist 整合** — 可作為 Home Assistant 內建 Assist 管道的對話代理使用
- **MCP 伺服器** — 透過 Model Context Protocol (SSE) 開放工具供外部 MCP 客戶端使用
- **持久化歷史** — 對話歷史儲存於本地資料庫，可設定保留天數
- **雙語介面** — 英文與繁體中文介面

### 架構

```
┌─────────────────────────────────────────────────┐
│                  Home Assistant                  │
│                                                  │
│  ┌──────────┐  ┌────────────┐  ┌─────────────┐  │
│  │ 聊天     │  │ HA Assist  │  │ MCP SSE     │  │
│  │ 面板     │  │ 管道       │  │ 伺服器      │  │
│  │ (iframe) │  │            │  │ (外部存取)  │  │
│  └────┬─────┘  └─────┬──────┘  └──────┬──────┘  │
│       │              │                │          │
│       └──────────────┼────────────────┘          │
│                      ▼                           │
│           ┌──────────────────┐                   │
│           │ 對話實體          │                   │
│           │ Conversation     │                   │
│           └────────┬─────────┘                   │
│                    ▼                             │
│  ┌─────────────────────────────────────────┐     │
│  │ AI 服務 (Anthropic/OpenAI/Ollama)       │     │
│  │ + 工具呼叫迴圈 (最多 N 次迭代)           │     │
│  └─────────────────┬───────────────────────┘     │
│                    ▼                             │
│  ┌─────────────────────────────────────────┐     │
│  │ 工具註冊表 — 62 個工具                    │     │
│  │ helpers.py (實作邏輯)                    │     │
│  │ registry.py (定義 + 處理器)              │     │
│  └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

### 安裝方式

#### HACS（建議）

1. 在 HACS 中新增此儲存庫為自訂儲存庫
2. 搜尋 "HA MCP Client" 並安裝
3. 重啟 Home Assistant
4. 前往 **設定 > 裝置與服務 > 新增整合 > HA MCP Client**

#### 手動安裝

1. 將 `custom_components/ha_mcp_client` 資料夾複製到 Home Assistant 的 `config/custom_components/` 目錄
2. 重啟 Home Assistant
3. 前往 **設定 > 裝置與服務 > 新增整合 > HA MCP Client**

### 設定

設定精靈會引導你完成 4 個步驟：

| 步驟 | 選項 |
|------|------|
| **1. 功能選擇** | 啟用 MCP 伺服器、啟用對話代理 |
| **2. MCP 伺服器** | 伺服器端口（預設：8087） |
| **3. AI 服務** | 供應商選擇、API 金鑰、模型、Base URL |
| **4. 對話設定** | 歷史開/關、保留天數、系統提示、最大工具呼叫次數 |

**支援的 AI 模型：**

| 供應商 | 模型 |
|--------|------|
| **Anthropic** | claude-sonnet-4-20250514, claude-opus-4-20250514, claude-3.5-sonnet, claude-3.5-haiku, claude-3-opus |
| **OpenAI** | gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-4, gpt-3.5-turbo |
| **Ollama** | llama3.2, llama3.1, mistral, mixtral, codellama, phi3, gemma2 |
| **OpenAI 相容** | 透過自訂 Base URL 使用任何模型（LM Studio、vLLM 等） |

### 工具（共 62 個）

<details>
<summary><strong>實體與服務 (4)</strong></summary>

| 工具 | 說明 |
|------|------|
| `get_entity_state` | 取得任意實體的狀態和屬性 |
| `search_entities` | 依名稱、域、區域或裝置搜尋實體 |
| `call_service` | 直接呼叫 Home Assistant 任意服務 |
| `list_services` | 列出所有可用服務與域 |

</details>

<details>
<summary><strong>區域與標籤管理 (8)</strong></summary>

| 工具 | 說明 |
|------|------|
| `list_areas` | 列出所有區域 |
| `create_area` | 建立新區域 |
| `update_area` | 更新區域名稱、圖示、別名 |
| `delete_area` | 刪除區域 |
| `list_labels` | 列出所有標籤 |
| `create_label` | 建立新標籤 |
| `update_label` | 更新標籤屬性 |
| `delete_label` | 刪除標籤 |

</details>

<details>
<summary><strong>實體指派 (3)</strong></summary>

| 工具 | 說明 |
|------|------|
| `assign_entity_to_area` | 將實體指派到區域 |
| `assign_entity_to_labels` | 為實體指派標籤 |
| `list_devices` | 列出裝置（可依區域篩選） |

</details>

<details>
<summary><strong>自動化 (6)</strong></summary>

| 工具 | 說明 |
|------|------|
| `list_automations` | 列出所有自動化及狀態 |
| `create_automation` | 建立新自動化（YAML） |
| `update_automation` | 更新自動化觸發器/動作/模式 |
| `delete_automation` | 刪除自動化 |
| `toggle_automation` | 啟用或停用自動化 |
| `trigger_automation` | 手動觸發自動化 |

</details>

<details>
<summary><strong>腳本 (5)</strong></summary>

| 工具 | 說明 |
|------|------|
| `list_scripts` | 列出所有腳本 |
| `create_script` | 建立新腳本（YAML） |
| `update_script` | 更新腳本序列/模式/欄位 |
| `delete_script` | 刪除腳本 |
| `run_script` | 執行腳本 |

</details>

<details>
<summary><strong>情境 (5)</strong></summary>

| 工具 | 說明 |
|------|------|
| `list_scenes` | 列出所有情境 |
| `create_scene` | 建立新情境（YAML） |
| `update_scene` | 更新情境實體/狀態 |
| `delete_scene` | 刪除情境 |
| `activate_scene` | 啟動情境 |

</details>

<details>
<summary><strong>日曆 (4)</strong></summary>

| 工具 | 說明 |
|------|------|
| `create_calendar_event` | 建立日曆事件 |
| `list_calendar_events` | 列出日期範圍內的事件 |
| `update_calendar_event` | 更新現有事件 |
| `delete_calendar_event` | 刪除日曆事件 |

</details>

<details>
<summary><strong>待辦事項 (5)</strong></summary>

| 工具 | 說明 |
|------|------|
| `add_todo_item` | 新增待辦事項 |
| `list_todo_items` | 列出待辦事項 |
| `update_todo_item` | 重新命名或更改待辦狀態 |
| `remove_todo_item` | 移除待辦事項 |
| `remove_completed_todo_items` | 移除所有已完成項目 |

</details>

<details>
<summary><strong>裝置控制 (14)</strong></summary>

| 工具 | 說明 |
|------|------|
| `control_light` | 開/關/切換、亮度、色溫、RGB |
| `control_switch` | 開/關/切換開關 |
| `control_cover` | 開/關/停/切換窗簾、位置、傾斜 |
| `control_climate` | HVAC 模式、溫度、風扇/擺動/預設模式、濕度 |
| `control_fan` | 開/關/切換、風速、方向、擺動 |
| `control_lock` | 上鎖/開鎖 |
| `control_media_player` | 播放/暫停/停止、音量、來源、快轉、音效模式 |
| `control_camera` | 快照、串流播放、錄影 |
| `control_timer` | 啟動/暫停/取消/完成計時器 |
| `control_counter` | 遞增/遞減/重設計數器 |
| `control_input_helper` | 設定 input_boolean/number/text/select/datetime |
| `control_valve` | 開/關/停/切換閥門、位置 |
| `control_number` | 設定數值實體值（含最小/最大驗證） |
| `control_persistent_notification` | 建立/關閉持久通知 |

</details>

<details>
<summary><strong>工具程式 (8)</strong></summary>

| 工具 | 說明 |
|------|------|
| `send_notification` | 透過 notify 服務發送通知 |
| `speak_tts` | 文字轉語音輸出 |
| `manage_backup` | 建立 Home Assistant 備份 |
| `list_blueprints` | 列出自動化/腳本藍圖 |
| `import_blueprint` | 從 URL 匯入藍圖 |
| `control_shopping_list` | 新增/移除/完成購物清單項目 |
| `get_history` | 取得歷史狀態變更 |
| `system_overview` | 取得系統概覽（實體數、域、區域） |

</details>

### 使用範例

**透過聊天面板：**

開啟側邊欄的「AI 聊天」項目，用自然語言開始對話：

- 「把客廳的燈全部關掉」
- 「臥室現在幾度？」
- 「建立一個在日落時開啟門廊燈的自動化」
- 「把牛奶加到購物清單」
- 「車庫門最近一小時發生了什麼？」
- 「把臥室窗簾設到 50% 開」

**透過 HA Assist：**

在 Assist 設定中選擇「HA MCP Client」作為對話代理，即可使用 Assist 對話框或語音指令。

**透過 MCP 協定：**

將任何 MCP 相容客戶端連接到 `http://your-ha:8087/sse`，即可程式化使用全部 62 個工具。

### 服務

| 服務 | 說明 |
|------|------|
| `ha_mcp_client.clear_conversation_history` | 清除所有對話歷史 |
| `ha_mcp_client.export_conversation_history` | 匯出歷史為 JSON 或 Markdown |

### 專案結構

```
custom_components/ha_mcp_client/
├── __init__.py              # 整合設定、服務、面板註冊
├── config_flow.py           # 多步驟設定精靈
├── const.py                 # 常數與預設值
├── conversation.py          # 對話實體 + AI 工具呼叫迴圈
├── conversation_recorder.py # 持久化對話歷史（SQLite）
├── views.py                 # 聊天面板 REST API 端點
├── manifest.json            # 整合元資料
├── services.yaml            # 服務定義
├── frontend/                # 聊天面板 UI（HTML/JS/CSS）
├── translations/            # en.json, zh-Hant.json
├── ai_services/             # AI 供應商實作
│   ├── anthropic.py         # Anthropic Claude
│   ├── openai.py            # OpenAI GPT
│   ├── ollama.py            # Ollama（本地）
│   └── openai_compatible.py # OpenAI 相容 API
└── mcp/
    ├── server.py            # MCP SSE 伺服器（供外部客戶端使用）
    └── tools/
        ├── registry.py      # 62 個工具定義 + 處理器
        └── helpers.py       # 工具實作邏輯
```

### 系統需求

- Home Assistant 2024.1+
- Python 3.11+
- 已設定其中一種支援的 AI 供應商

### 授權條款

MIT License
