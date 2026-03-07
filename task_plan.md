# Task Plan: ChatGPT 風格聊天面板 + input_text 整合

## Goal
為 ha_mcp_client 新增 ChatGPT 風格側邊面板、多對話管理、input_text 雙向整合

## PRD
`docs/plans/2026-03-07-chat-panel-design.md`

## Phases

### Phase 1: 資料庫 + API（後端）— `pending`
- [ ] 新增 conversations 資料表（SQLAlchemy model）
- [ ] 新增 REST API 端點（views.py）
- [ ] 修改 conversation.py 支援對話管理
- [ ] 自動建表遷移

### Phase 2: input_text 整合 — `pending`
- [ ] 建立 input_text.mcp_user_input + mcp_ai_response
- [ ] 對話完成後自動同步到 input_text
- [ ] 監聽 input_text 變更觸發對話
- [ ] 防迴圈機制

### Phase 3: 前端面板 — `pending`
- [ ] 建立 frontend/ 目錄（index.html, styles.css, app.js）
- [ ] 面板註冊（iframe panel）
- [ ] 左側對話列表 UI
- [ ] 右側聊天視窗 UI
- [ ] 送出/載入/捲動互動

### Phase 4: 完善 + 測試 — `pending`
- [ ] RWD 響應式（手機/平板）
- [ ] 深色/淺色主題跟隨 HA
- [ ] 錯誤處理 + loading 狀態
- [ ] 整合測試

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
| (none yet) | | |
