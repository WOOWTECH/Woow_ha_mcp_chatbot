# PRD：HA MCP Client 聊天面板 + input_text 整合

**日期**: 2026-03-07
**狀態**: 已完成
**版本**: 0.2.0
**實作完成日**: 2026-03-07
**測試結果**: 32/32 PASS (100%)

---

## 1. 目標

為 ha_mcp_client 新增一個 ChatGPT 風格的自訂側邊面板，支援：
- 多對話管理（建立、切換、重新命名、刪除）
- 長期對話歷史儲存（不像目前每次開啟新內容）
- 兩個 input_text 實體同步最新對話（供自動化使用）

## 2. 使用者故事

1. **作為使用者**，我想在 HA 側邊欄看到一個聊天入口，點進去就能跟 AI 對話
2. **作為使用者**，我想像 ChatGPT 一樣管理多個對話主題，左側列表可切換
3. **作為使用者**，我想關閉面板再打開時，之前的對話還在
4. **作為使用者**，我想用 input_text 搭配自動化（語音助手觸發對話、TTS 播放回覆）

## 3. 系統架構

```
┌─────────────────────────────────────────────────────┐
│  Home Assistant                                      │
│                                                      │
│  ┌─────────────┐    REST API    ┌────────────────┐  │
│  │  前端面板     │ ◄──────────► │  API 端點        │  │
│  │  (JS/HTML)   │              │  (views.py)     │  │
│  └─────────────┘              └───────┬────────┘  │
│                                        │           │
│  ┌─────────────┐              ┌───────▼────────┐  │
│  │ input_text   │ ◄──同步────► │ conversation.py │  │
│  │ × 2 實體     │              └───────┬────────┘  │
│  └─────────────┘                       │           │
│                                ┌───────▼────────┐  │
│                                │ conversation    │  │
│                                │ _recorder.py    │  │
│                                │ (SQLite DB)     │  │
│                                └────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 4. 資料庫設計

### 4.1 新增資料表：`ha_mcp_client_conversations`

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | VARCHAR(255) PK | UUID，對話唯一識別碼 |
| `user_id` | VARCHAR(255), INDEX | HA 使用者 ID |
| `title` | VARCHAR(500) | 對話標題（預設取第一句話前 50 字） |
| `created_at` | DATETIME | 建立時間 |
| `updated_at` | DATETIME, INDEX | 最後訊息時間（排序用） |
| `is_archived` | BOOLEAN, DEFAULT FALSE | 軟刪除標記 |

### 4.2 現有資料表：`ha_mcp_client_messages`

不需修改結構。現有的 `conversation_id` 欄位將對應到新 `conversations` 表的 `id`。

### 4.3 運作邏輯

| 操作 | 行為 |
|------|------|
| 新增對話 | 建 conversations 記錄，`title` = 第一句話前 50 字元 |
| 發訊息 | messages 掛在 conversation_id 下，更新 conversations.updated_at |
| 改名 | 更新 conversations.title |
| 刪除 | 設 is_archived = true（軟刪除），訊息保留 |
| 列表 | 按 updated_at DESC 排序，排除 archived |

## 5. REST API 端點

### 5.1 對話管理

| 方法 | 路徑 | 說明 | 回傳 |
|------|------|------|------|
| `GET` | `/api/ha_mcp_client/conversations` | 列出使用者所有對話 | `[{id, title, updated_at}]` |
| `POST` | `/api/ha_mcp_client/conversations` | 建立新對話 | `{id, title, created_at}` |
| `PATCH` | `/api/ha_mcp_client/conversations/{id}` | 更新標題或封存 | `{success}` |
| `DELETE` | `/api/ha_mcp_client/conversations/{id}` | 刪除對話（軟刪除） | `{success}` |

### 5.2 訊息操作

| 方法 | 路徑 | 說明 | 回傳 |
|------|------|------|------|
| `GET` | `/api/ha_mcp_client/conversations/{id}/messages` | 取得對話訊息（分頁） | `[{role, content, timestamp}]` |
| `POST` | `/api/ha_mcp_client/conversations/{id}/messages` | 發送訊息 + 觸發 AI 回覆 | `{user_msg, ai_response}` |

### 5.3 認證

所有端點需要 Bearer Token（HA Long-Lived Access Token），自動從 token 解析 user_id，使用者只能存取自己的對話。

## 6. 前端面板設計

### 6.1 技術選擇

| 項目 | 選擇 | 原因 |
|------|------|------|
| 框架 | Vanilla JS + Web Components | 無需建置工具，HA 原生相容 |
| 樣式 | CSS Variables + HA theme vars | 自動跟隨深色/淺色主題 |
| 通訊 | Fetch API (REST) | 簡單可靠 |
| 圖示 | MDI (Material Design Icons) | HA 內建支援 |

### 6.2 面板註冊

```python
# __init__.py 中新增（HA 2026.1 API）
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig

await hass.http.async_register_static_paths(
    [StaticPathConfig(f"/{DOMAIN}/panel", str(frontend_dir), False)]
)
async_register_built_in_panel(
    hass,
    component_name="iframe",
    sidebar_title="AI 聊天",
    sidebar_icon="mdi:robot-happy-outline",
    frontend_url_path="ha-mcp-chat",
    config={"url": "/ha_mcp_client/panel/index.html"},
    require_admin=False,
)
```

### 6.3 UI 佈局

```
ha-mcp-panel (主容器, 100vw × 100vh)
├── sidebar (左側 280px, 可收合)
│   ├── header
│   │   └── new-chat-btn     「+ 新對話」按鈕
│   ├── search-input          搜尋過濾
│   └── conversation-list     對話列表
│       └── conversation-item × N
│           ├── title          對話標題
│           ├── updated_at     最後更新時間
│           └── actions        改名 / 刪除按鈕
│
└── chat-area (右側，自適應寬度)
    ├── chat-header
    │   ├── title             當前對話標題（可編輯）
    │   └── menu-btn          更多操作
    ├── message-list (可捲動，自動滾到底部)
    │   ├── user-message      使用者訊息（靠右、主色氣泡）
    │   ├── ai-message        AI 回覆（靠左、背景色氣泡）
    │   │   └── tool-badge    工具呼叫指示（可展開看詳情）
    │   └── loading-indicator 等待 AI 回覆動畫
    └── input-area (底部固定)
        ├── textarea          自動增高輸入框
        └── send-btn          送出按鈕（Enter 送出, Shift+Enter 換行）
```

### 6.4 樣式規格

```css
/* 跟隨 HA 主題 */
--user-bubble-bg: var(--primary-color);
--user-bubble-text: var(--text-primary-color);
--ai-bubble-bg: var(--card-background-color);
--ai-bubble-text: var(--primary-text-color);
--sidebar-bg: var(--sidebar-background-color);
--input-bg: var(--card-background-color);
```

### 6.5 RWD 響應式

| 視窗寬度 | 行為 |
|----------|------|
| >= 768px | 側邊欄 + 聊天區域並列 |
| < 768px | 側邊欄覆蓋模式（點選後隱藏） |

## 7. input_text 整合

### 7.1 新增兩個 input_text 實體

| Entity ID | 說明 | 最大長度 |
|-----------|------|----------|
| `input_text.mcp_user_input` | 使用者最新訊息 | 255 字元 |
| `input_text.mcp_ai_response` | AI 最新回覆 | 255 字元 |

### 7.2 同步機制

**對話完成後**（conversation.py）：
```python
# 每次 AI 回覆後自動更新
hass.states.async_set("input_text.mcp_user_input", user_message[:255])
hass.states.async_set("input_text.mcp_ai_response", ai_response[:255])
```

**input_text 被寫入時**：
```python
# 監聽 input_text.mcp_user_input 狀態變更
# 如果不是由本系統寫入的（避免迴圈），則觸發對話
async def _handle_input_text_change(event):
    new_state = event.data.get("new_state")
    if new_state and new_state.state:
        # 使用最近的對話或建立新對話
        await process_message(new_state.state)
        # AI 回覆寫入 mcp_ai_response
```

### 7.3 自動化範例

```yaml
# 語音助手 → AI 對話 → TTS 播放
automation:
  trigger:
    - platform: state
      entity_id: input_text.mcp_ai_response
  action:
    - service: tts.google_translate_say
      data:
        entity_id: media_player.living_room
        message: "{{ states('input_text.mcp_ai_response') }}"
```

## 8. 檔案結構

```
custom_components/ha_mcp_client/
├── __init__.py                    # 更新：註冊面板 + input_text
├── conversation.py                # 更新：input_text 同步 + 對話管理
├── conversation_recorder.py       # 更新：新增 conversations 表
├── views.py                       # 新增：REST API 端點
├── manifest.json                  # 更新：dependencies
├── const.py                       # 更新：新常數
│
└── frontend/                      # 新增：前端資源
    ├── index.html                 # 主頁面
    ├── styles.css                 # 樣式表
    └── app.js                     # 主要 JS 邏輯
```

## 9. 實作階段

### Phase 1：資料庫 + API（後端）
1. 新增 `ha_mcp_client_conversations` 資料表
2. 實作 REST API 端點（views.py）
3. 整合 conversation.py 支援對話管理
4. 資料庫遷移（自動建表）

### Phase 2：input_text 整合
5. 建立兩個 input_text 實體
6. 實作雙向同步（對話後寫入 + 監聽觸發）
7. 防迴圈機制

### Phase 3：前端面板
8. 建立 frontend/ 目錄和 HTML/CSS/JS
9. 面板註冊（__init__.py）
10. 對話列表 UI（左側邊欄）
11. 聊天視窗 UI（右側）
12. 即時互動（送出、載入、捲動）

### Phase 4：完善 + 測試
13. RWD 響應式
14. 深色/淺色主題
15. 錯誤處理 + loading 狀態
16. 整合測試

## 10. 向後相容

| 項目 | 影響 |
|------|------|
| 現有對話 | 不受影響，現有 messages 表不改動 |
| MCP Server | 不受影響，獨立功能 |
| conversation entity | 保留，面板是額外的 UI |
| config flow | 不需重新設定 |
| 舊 conversation_id | 自動歸類為「未命名對話」 |

## 11. 實作紀錄

### 11.1 實際修改檔案

| 檔案 | 類型 | 變更內容 |
|------|------|----------|
| `__init__.py` | 修改 | 新增 panel 註冊（`async_register_built_in_panel`）、靜態路徑（`StaticPathConfig`）、REST API views 註冊、input_text 狀態初始化 + state_changed 監聽器 |
| `const.py` | 修改 | 新增 `PANEL_URL`、`PANEL_TITLE`、`PANEL_ICON`、`PANEL_FRONTEND_PATH`、`INPUT_TEXT_USER`、`INPUT_TEXT_AI` 常數 |
| `conversation.py` | 修改 | 新增 `INPUT_TEXT_USER`/`INPUT_TEXT_AI` import、對話結束後自動同步 input_text 實體 |
| `conversation_recorder.py` | 修改 | 新增 `Conversation` SQLAlchemy model（`ha_mcp_client_conversations` 表）、`_create_tables` 新增第二張表、新增 6 個 CRUD 方法 |
| `manifest.json` | 修改 | `dependencies` 新增 `"frontend"` |
| `views.py` | 新增 | 3 個 `HomeAssistantView` 類別（`ConversationsListView`、`ConversationDetailView`、`ConversationMessagesView`）共 6 個 REST 端點 |
| `frontend/index.html` | 新增 | ChatGPT 風格主頁面、sidebar + chat area 佈局、重新命名/刪除對話框 |
| `frontend/styles.css` | 新增 | HA theme vars 整合、RWD（768px 斷點）、氣泡/動畫/對話框/toast 樣式 |
| `frontend/app.js` | 新增 | 完整前端邏輯：token 認證（自動從 HA iframe parent 取得）、對話 CRUD、訊息收發、搜尋、重新命名、刪除 |

### 11.2 部署中修正的問題

| 問題 | 原因 | 修正 |
|------|------|------|
| `register_static_path` AttributeError | HA 2026.1 已移除舊 API | 改用 `async_register_static_paths` + `StaticPathConfig` |
| `hass.components.frontend` 警告 | 已棄用的呼叫方式 | 改為直接 import `async_register_built_in_panel`、`async_remove_panel` |
| T3.1 test encoding | `requests` 預設 ISO-8859-1 | 測試中使用 `r.content.decode("utf-8")` |
| T4.3 test race condition | 多個測試共用 input_text 狀態 | 使用獨立對話 + 唯一 message |

### 11.3 測試報告

**測試套件**: `test_chat_panel_v2.py` — 32 項自動化測試
**執行時間**: 2026-03-07T19:58 UTC
**結果**: **32/32 PASS (100%)**

| 分類 | 測試項目 | 結果 |
|------|----------|------|
| **Phase 0: 認證** | | |
| T0.1 | 取得 fresh access token | PASS |
| **Phase 1: 對話 CRUD** | | |
| T1.1 | 列出對話 (GET) | PASS |
| T1.2 | 建立對話 (POST 201) | PASS |
| T1.3 | 建立第二個對話 | PASS |
| T1.4 | 列表包含新對話 | PASS |
| T1.5 | 重新命名 (PATCH) | PASS |
| T1.6 | 驗證重新命名結果 | PASS |
| T1.7 | 刪除對話 (DELETE) | PASS |
| T1.8 | 已刪除不在列表中 | PASS |
| T1.9 | 不存在的對話 → 404 | PASS |
| T1.10 | 無認證 → 401 | PASS |
| **Phase 2: 訊息** | | |
| T2.1 | 取得訊息（空） | PASS |
| T2.2 | 發送訊息 + AI 回覆 | PASS |
| T2.3 | 訊息持久化至 DB | PASS |
| T2.4 | 工具呼叫查詢（溫度） | PASS |
| T2.5 | 空訊息 → 400 | PASS |
| T2.6 | 不存在對話的訊息 → 404 | PASS |
| T2.7 | 第一則訊息自動命名 | PASS |
| **Phase 3: 前端面板** | | |
| T3.1 | index.html 正確提供 (UTF-8) | PASS |
| T3.2 | styles.css 含 RWD | PASS |
| T3.3 | app.js 含所有功能 | PASS |
| T3.4 | 面板已在側邊欄註冊 | PASS |
| **Phase 4: input_text** | | |
| T4.1 | 使用者輸入實體存在 | PASS |
| T4.2 | AI 回覆實體存在 | PASS |
| T4.3 | input_text 同步正常 | PASS |
| **Phase 5: 資料庫** | | |
| T5.1 | conversations 表結構正確 | PASS |
| T5.2 | messages 表結構正確 | PASS |
| T5.3 | 訊息按時間排序 | PASS |
| T5.4 | 分頁功能 (limit/offset) | PASS |
| **Phase 6: 錯誤處理** | | |
| T6.1 | 無效 JSON → 400 | PASS |
| T6.2 | 缺少 message 欄位 → 400 | PASS |
| T6.3 | 刪除不存在對話 → 404 | PASS |
