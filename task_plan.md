# Task Plan: ChatGPT 風格聊天面板 + input_text 整合

## Goal
為 ha_mcp_client 新增 ChatGPT 風格側邊面板、多對話管理、input_text 雙向整合

## PRD
`docs/plans/2026-03-07-chat-panel-design.md`

## Status: COMPLETED — 32/32 Tests PASS (100%)

## Phases

### Phase 1: 資料庫 + API（後端）— `completed`
- [x] 新增 conversations 資料表（SQLAlchemy model）
- [x] 新增 REST API 端點（views.py）
- [x] 修改 conversation.py 支援對話管理
- [x] 自動建表遷移

### Phase 2: input_text 整合 — `completed`
- [x] 建立 input_text.ha_mcp_client_user_input + ha_mcp_client_ai_response
- [x] 對話完成後自動同步到 input_text
- [x] 監聽 input_text 變更觸發對話
- [x] 防迴圈機制（_syncing flag）

### Phase 3: 前端面板 — `completed`
- [x] 建立 frontend/ 目錄（index.html, styles.css, app.js）
- [x] 面板註冊（iframe panel, StaticPathConfig）
- [x] 左側對話列表 UI（搜尋、排序、active 標記）
- [x] 右側聊天視窗 UI（氣泡、tool badge、loading dots）
- [x] 送出/載入/捲動互動（Enter 送出、Shift+Enter 換行、auto-resize）

### Phase 4: 完善 + 測試 — `completed`
- [x] RWD 響應式（768px 斷點，sidebar overlay）
- [x] HA theme vars 整合（深色/淺色自動跟隨）
- [x] 錯誤處理（400/401/404/500 + toast 通知）
- [x] 整合測試（32/32 PASS）

## Decisions
| Decision | Rationale |
|----------|-----------|
| 自訂 Panel (iframe) | ChatGPT 風格需全頁寬度 |
| Vanilla JS | 無需建置工具，HA 相容 |
| 軟刪除 | 資料安全，可恢復 |
| input_text 雙向 | 可作輸入介面 + 狀態顯示 |
| conversations 新表 | 不動現有 messages 表結構 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `register_static_path` AttributeError | HA 2026.1 已移除舊 API | 改用 `async_register_static_paths` + `StaticPathConfig` |
| `hass.components.frontend` 棄用 | 舊 API 呼叫方式 | 直接 import `async_register_built_in_panel` |
