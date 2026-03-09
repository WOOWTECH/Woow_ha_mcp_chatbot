# Task Plan: HA MCP Client v1.0 發佈前全面性測試計劃

## Goal
設計並實施全面性測試套件，覆蓋 HA MCP Client 所有功能模塊，確保發佈上線品質。參考 nanobot 倉庫功能列表和已知議題，補足現有測試覆蓋空缺，目標 300+ test cases / 0 failures。

## Current Phase
Phase 1 — 規劃（完成中）

---

## 現有測試覆蓋分析 (A-R, 234 cases)

| Section | 測試範疇 | Cases | 品質 |
|---------|----------|-------|------|
| A | Entity Platform (sensor/number/select/switch) | 20+ | 完整 |
| B | REST API CRUD (settings/memory/skills/cron/conversations) | 26+ | 完整 |
| C | AI Conversation E2E (basic/tool/identity) | 4 | Soft |
| D | Frontend Static Resources | 4 | 基本 |
| E | MCP SSE Server | 2 | 基本 |
| F | Cron Execution | 5 | 基本 |
| G | Entity Persistence (restart) | 8 | 完整 |
| H | Error Handling & Boundary | 8 | 基本 |
| I | Restart Stability | 8 | 完整 |
| J | Cron Advanced Scheduling (at/every/cron) | 15+ | 完整 |
| K | Memory Advanced (read/write/search/stats) | 14+ | 完整 |
| L | Skills Advanced (CRUD/partial/sanitize) | 12+ | 完整 |
| M | Skill Runtime (always-on/on-demand) | 5 | Soft |
| N | Cron Runtime (execution verify) | 8+ | 完整 |
| O | Long-term Memory E2E | 10+ | Soft |
| P | Multi-turn & Reasoning | 10+ | Soft |
| Q | Cron-to-Automation Bridge | 10+ | 完整 |
| R | Cron-Automation Bidirectional Sync | 12+ | 完整 |

### 覆蓋空缺分析 (參考 nanobot 議題)

| 空缺區域 | 優先級 | 參考 nanobot 議題 |
|----------|--------|-------------------|
| S. 對話歷史隔離 | P0 | #1709 context model, #1615 history visibility |
| T. 多 LLM Provider 切換 | P0 | #1634 session corruption, #1486 provider routing |
| U. 工具調用完整性 (77+ tools) | P0 | #1487 JSON format, #1710 no answer generated |
| V. 並發與壓力測試 | P1 | #1739 multiple instances conflict, #1762 interruption |
| W. 前端功能完整性 | P1 | 前端 tab 切換歷史消失已修復，需驗證 |
| X. MCP SSE 協議完整性 | P1 | #1526 API path compatibility |
| Y. 安全與權限測試 | P0 | #1634 session poisoning |
| Z. 資料完整性與清理 | P1 | #1698 memory consolidation persist, #1496 cron list details |

---

## Phases

### Phase 1: 規劃與設計
- [x] 分析現有測試覆蓋 (A-R sections)
- [x] 研究 nanobot 議題作為測試參考
- [x] 識別覆蓋空缺 (S-Z)
- [x] 設計每個新 section 的測試規格
- [x] 撰寫完整測試計劃文件
- **Status:** complete

### Phase 2: Section S — 對話歷史隔離測試
- [ ] S1. 新對話不載入其他對話歷史
- [ ] S2. 同一對話多輪記憶保持
- [ ] S3. 切換對話後歷史正確恢復 (messages API)
- [ ] S4. 刪除對話後歷史不再載入
- [ ] S5. conversation_id 正確傳遞到 recorder
- [ ] S6. 大量對話後 LRU 淘汰正常
- **Status:** pending

### Phase 3: Section T — 多 LLM Provider 切換測試
- [ ] T1. 列出可用 providers 與 models
- [ ] T2. 切換 active provider (Anthropic/OpenAI/Ollama/OpenAI-compatible)
- [ ] T3. 切換後 AI 回應正常
- [ ] T4. 同 provider 內切換 model
- [ ] T5. 無效 provider/model 拒絕設定
- [ ] T6. Provider sensor 狀態更新
- [ ] T7. 切換後工具調用正常
- [ ] T8. 還原原始設定
- **Status:** pending

### Phase 4: Section U — 工具調用完整性測試
- [ ] U1. Entity 工具群 (get_entity_state, search_entities, call_service, list_services)
- [ ] U2. Area/Label 完整 CRUD 迴圈
- [ ] U3. Automation 完整 CRUD (create → update → trigger → toggle → delete)
- [ ] U4. Scene 完整 CRUD (create → activate → update → delete)
- [ ] U5. Script 完整 CRUD (create → run → update → delete)
- [ ] U6. Smart Home Control (light/climate/cover/switch/fan/lock/valve)
- [ ] U7. Calendar CRUD (create → list → update → delete)
- [ ] U8. Todo CRUD (add → list → update → remove → clear completed)
- [ ] U9. Notification (send_notification, persistent_notification, speak_tts)
- [ ] U10. System (system_overview, get_history, manage_backup)
- [ ] U11. Memory AI 工具 (memory_get/save/append_history/search/consolidate)
- [ ] U12. Skills AI 工具 (list/read/toggle/create/update/delete_skill)
- [ ] U13. Cron AI 工具 (cron_list/add/update/remove/trigger/to_automation)
- [ ] U14. Blueprint 工具 (list_blueprints, import_blueprint, install_cron_blueprints)
- [ ] U15. Bulk 操作 (bulk_delete_automations/scenes/scripts)
- **Status:** pending

### Phase 5: Section V — 並發與壓力測試
- [ ] V1. 3 個並發 AI 對話請求
- [ ] V2. 10x 快速 Skill CRUD
- [ ] V3. 10x 快速 Cron Job CRUD
- [ ] V4. 5 個並發 SSE session
- [ ] V5. 大型 payload (10KB skill body, 50KB memory)
- [ ] V6. 快速連續訊息 (同對話 5 條訊息)
- **Status:** pending

### Phase 6: Section W — 前端功能完整性
- [ ] W1. 前端資源載入 (index.html, app.js, styles.css)
- [ ] W2. 對話 API 資料結構驗證 (符合前端需求)
- [ ] W3. Messages API 格式驗證 (role, content, timestamp, tool_calls)
- [ ] W4. Settings API 格式驗證 (所有前端欄位)
- [ ] W5. LLM Providers API 格式驗證 (providers list, models)
- [ ] W6. Memory API 格式驗證 (sections, stats)
- [ ] W7. 頁面切換後對話保持 (已修復 loadConversations bug)
- **Status:** pending

### Phase 7: Section X — MCP SSE 協議完整性
- [ ] X1. SSE 連線建立與 session_id 取得
- [ ] X2. JSON-RPC initialize 握手
- [ ] X3. tools/list 回應完整 (77+ tools)
- [ ] X4. tool call 執行 (system_overview)
- [ ] X5. Session 隔離 (2 sessions 不互相干擾)
- [ ] X6. 無效 session_id 處理
- [ ] X7. JSON-RPC 錯誤格式 (invalid method → -32601)
- [ ] X8. Ping/Pong 心跳
- **Status:** pending

### Phase 8: Section Y — 安全與權限測試
- [ ] Y1. 未認證請求被拒絕 (所有主要 endpoint)
- [ ] Y2. 無效 token 被拒絕
- [ ] Y3. 不同用戶對話隔離
- [ ] Y4. API key 不在回應中洩露 (settings, llm_providers)
- [ ] Y5. XSS payload 不被執行 (skill body, memory)
- [ ] Y6. SQL injection 防護 (memory search)
- [ ] Y7. 路徑穿越防護 (skill name: ../../etc/passwd)
- [ ] Y8. 封鎖危險服務 (homeassistant.restart 等)
- **Status:** pending

### Phase 9: Section Z — 資料完整性與清理
- [ ] Z1. Memory consolidation 不損失資料
- [ ] Z2. Conversation retention 期限檢查
- [ ] Z3. Cron store.json 持久化一致性
- [ ] Z4. Skill 檔案與 metadata 一致性
- [ ] Z5. Entity-Config 雙向一致性 (number entity ↔ settings API)
- [ ] Z6. LRU 記憶體保護 (OrderedDict max 100 conversations)
- [ ] Z7. 歷史記錄清理 (retention policy)
- **Status:** pending

### Phase 10: 整合與最終驗證
- [ ] 將新測試整合到 test_all.sh
- [ ] 完整跑一次全套 (A-Z)
- [ ] 修復發現的問題
- [ ] 最終驗證：0 failures
- [ ] 產出測試覆蓋報告
- **Status:** pending

---

## 新增測試設計詳細規格

### Section S: 對話歷史隔離測試

```
S1. 新對話不載入其他對話歷史
  目的: 驗證 conversation_id 正確傳遞到 recorder，新對話不含舊訊息
  步驟:
  1. POST /conversations → 創建對話 A
  2. POST /conversations/A/messages {"message": "SECRET_A_<ts>"}
  3. POST /conversations → 創建對話 B
  4. GET /conversations/B/messages → 驗證為空 (不含 SECRET_A)
  預期: 對話 B 的 messages 列表不包含 SECRET_A
  類型: Hard assert

S2. 同對話多輪記憶
  目的: 驗證同一 conversation_id 的多輪訊息正確保持
  步驟:
  1. POST /conversations → 創建新對話
  2. POST messages: "記住代號 RECALL_<ts>"
  3. POST messages: "剛才的代號是什麼？"
  4. 驗證: 回覆包含 RECALL_<ts>
  預期: AI 能回憶同一對話中的前文
  類型: Soft assert (AI 回覆非確定性)

S3. Messages API 返回正確對話訊息
  目的: 驗證 GET messages 只返回該對話的訊息
  步驟:
  1. 創建對話 A, 發送 "MSG_A_<ts>"
  2. 創建對話 B, 發送 "MSG_B_<ts>"
  3. GET /conversations/A/messages → 包含 MSG_A, 不含 MSG_B
  4. GET /conversations/B/messages → 包含 MSG_B, 不含 MSG_A
  預期: 訊息隔離正確
  類型: Hard assert

S4. 刪除對話後歷史清除
  步驟:
  1. 創建對話, 發送訊息
  2. DELETE /conversations/{id}
  3. GET /conversations/{id}/messages → 404 或空
  類型: Hard assert

S5. Recorder conversation_id 查詢
  步驟:
  1. 創建 2 個對話各發 1 條訊息
  2. GET /conversations/A/messages → 只有 A 的 user+assistant
  3. GET /conversations/B/messages → 只有 B 的 user+assistant
  4. 驗證訊息數量正確 (各 2 條: user + assistant)
  類型: Hard assert

S6. LRU 淘汰驗證
  步驟:
  1. 快速創建 5 個對話各發 1 條訊息
  2. 全部 GET messages → 驗證所有對話有正確訊息
  3. 清理所有測試對話
  類型: Hard assert
```

### Section T: 多 LLM Provider 切換測試

```
T1. 列出 providers
  步驟: GET /llm_providers
  驗證: 回應包含 providers 陣列, 每個有 name, models, is_active 欄位
  類型: Hard assert

T2. 切換 provider
  步驟:
  1. 記錄當前 provider
  2. PATCH /active_llm {"provider": "<other_provider>"}
  3. GET /settings → 驗證 ai_service 已更新
  4. 還原
  類型: Hard assert
  注意: 只切換有效且已設定 API key 的 provider

T3. 切換後 AI 回應
  步驟:
  1. 切換到可用 provider
  2. POST /conversations/{id}/messages {"message": "1+1=?"}
  3. 驗證: 回覆 status 200, content 非空
  4. 還原 provider
  類型: Soft assert (不同 provider 回覆格式可能不同)

T4. Model 切換
  步驟:
  1. GET /llm_providers → 取得當前 provider 的 models
  2. PATCH /active_llm {"model": "<other_model>"}
  3. GET /settings → model 已更新
  4. 還原
  類型: Hard assert

T5. 無效設定拒絕
  步驟:
  1. PATCH /active_llm {"provider": "nonexistent_xyz"} → 400
  2. PATCH /active_llm {"model": ""} → 400 或被忽略
  類型: Hard assert

T6. Provider sensor
  步驟:
  1. 讀取所有 sensor.nanobot_llm_* entities
  2. 驗證: 已設定的 provider sensor 狀態為 "connected"
  3. 驗證: 未設定的 provider sensor 狀態為 "unconfigured"
  類型: Hard assert

T7. 切換後工具調用
  步驟:
  1. 切換到可用 provider
  2. POST message: "使用 system_overview 工具"
  3. 驗證: 回覆包含系統資訊 (非 error)
  4. 還原
  類型: Soft assert

T8. 還原驗證
  步驟: 確認所有 T1-T7 測試後 provider/model 已還原到原始值
  類型: Hard assert
```

### Section U: 工具調用完整性 (via MCP SSE)

```
測試策略:
- 使用 MCP SSE 直接調用工具 (不經過 AI)
- 驗證工具註冊、參數驗證、返回格式
- 每個工具群執行 CRUD 完整迴圈

U1. Entity 工具群
  - get_entity_state("sensor.nanobot_ji_yi_tiao_mu_shu") → state 存在
  - search_entities(query="light") → results 陣列
  - list_services(domain="light") → services 列表
  - call_service("light", "turn_on", entity_id="...") → 成功

U2. Area/Label CRUD
  - create_area(name="Test_U2_Area") → success
  - list_areas() → 包含 Test_U2_Area
  - update_area(area_id, name="Updated_U2") → success
  - list_labels() → 列表
  - create_label(name="test_u2_label") → success
  - update_label(label_id, name="updated_u2") → success
  - delete_label(label_id) → success
  - delete_area(area_id) → success

U3-U5. Automation/Scene/Script CRUD
  - create → list (verify exists) → update → trigger/activate/run → delete
  - bulk_delete 測試 (多筆刪除)

U6. Smart Home Control
  - 動態發現可用 entity (search_entities)
  - 有 light entity → control_light(on/off/brightness)
  - 有 switch entity → control_switch(on/off)
  - 其他 entity 依可用性測試

U7-U8. Calendar/Todo CRUD
  - 完整 CRUD 迴圈
  - 異常處理 (無 calendar entity → graceful error)

U9. Notification
  - persistent_notification(title, message) → 驗證通知出現
  - send_notification → 驗證不 error

U10. System
  - system_overview() → 包含 version, entity_count
  - get_history(entity_id, hours=1) → 回傳歷史
  - manage_backup(action="list") → 回傳 backup 列表

U11-U14. Memory/Skills/Cron/Blueprint AI 工具
  - 與 REST API 測試互補
  - 驗證通過 MCP tool call 的 CRUD 迴圈

U15. Bulk 操作
  - 創建 3 個 automations → bulk_delete → 驗證全部刪除
  - 創建 3 個 scenes → bulk_delete → 驗證全部刪除
```

### Section V: 並發與壓力測試

```
V1. 並發 AI 請求
  步驟:
  1. 創建 3 個對話
  2. 用 bash & 同時發送 3 個 POST messages
  3. wait 等所有完成
  4. 驗證: 所有 3 個返回 200 且回覆非空
  5. 清理 3 個對話

V2. 快速 Skill CRUD (10x)
  步驟:
  1. for i in 1..10: POST create → DELETE
  2. 每次驗證 status (201 → 200)
  3. 最終 GET /skills → 無殘留 test skill

V3. 快速 Cron CRUD (10x)
  步驟: 同 V2 但針對 cron jobs

V4. 多 SSE Session
  步驟:
  1. 同時開 5 個 SSE 連線 (timeout 3s)
  2. 驗證: 每個收到 event: endpoint
  3. 每個取得不同 session_id

V5. 大型 Payload
  步驟:
  1. 產生 10KB 文字 → POST /skills (body=10KB) → 201
  2. GET 該 skill → 內容完整 (長度 >= 10000)
  3. 產生 50KB 文字 → PUT /memory/memory → 200
  4. GET /memory/memory → 內容完整 (長度 >= 50000)
  5. 還原 memory, 刪除 skill

V6. 快速連續訊息
  步驟:
  1. 創建 1 個對話
  2. 連續發 5 條 "test message N" (不等回覆)
  3. 等最後一條完成
  4. GET messages → 驗證 >= 5 條 user 訊息存在
  5. 清理
```

### Section W: 前端功能完整性

```
W1. 前端資源載入
  - GET /ha_mcp_client/panel/index.html → 200, 包含 <html>
  - GET /ha_mcp_client/panel/app.js → 200, 包含 function
  - GET /ha_mcp_client/panel/styles.css → 200, 包含 css

W2. Conversations API 結構
  - GET /conversations → 陣列, 每項有 id, title, updated_at
  - POST /conversations → 返回 id

W3. Messages API 結構
  - GET /conversations/{id}/messages → 陣列
  - 每條 message 有: role, content, timestamp

W4. Settings API 結構
  - GET /settings → 包含:
    temperature, max_tokens, model, ai_service,
    system_prompt, memory_window, max_tool_calls,
    reasoning_effort

W5. LLM Providers API 結構
  - GET /llm_providers → 包含 providers 陣列
  - 每個 provider 有: name/type, models (陣列), is_active (bool)

W6. Memory API 結構
  - GET /memory → 包含: soul, user, memory, history, stats
  - stats 包含: memory_entries, history_entries

W7. Tab 切換歷史保持
  - 創建對話, 發送訊息
  - GET /conversations → 對話存在
  - GET messages → 訊息存在
  (驗證 loadConversations 修復生效)
```

### Section X: MCP SSE 協議完整性

```
X1. SSE 連線
  - GET /api/ha_mcp_client/sse → Content-Type: text/event-stream
  - 解析 event: endpoint → 取得 msg_url 和 session_id

X2. Initialize 握手
  - POST msg_url {"jsonrpc":"2.0","method":"initialize","id":1,
    "params":{"protocolVersion":"2024-11-05","capabilities":{}}}
  - 驗證: SSE 回應包含 serverInfo, protocolVersion

X3. tools/list 完整
  - POST {"method":"tools/list","id":2}
  - 驗證: tools 陣列長度 >= 70

X4. Tool call 執行
  - POST {"method":"tools/call","id":3,
    "params":{"name":"system_overview","arguments":{}}}
  - 驗證: result 包含系統資訊

X5. Session 隔離
  - 開 2 個 SSE session
  - Session 1 呼叫 tool → Session 2 不收到回應

X6. 無效 session
  - POST msg_url?sessionId=invalid_xxx → 400/404

X7. 錯誤格式
  - POST {"method":"nonexistent_method","id":4}
  - 驗證: error code = -32601

X8. Ping/Pong
  - POST {"method":"ping","id":5}
  - 驗證: 收到空 result 回應
```

### Section Y: 安全與權限測試

```
Y1. 未認證拒絕 (5 endpoints)
  無 Authorization header:
  - GET /conversations → 401
  - GET /memory → 401
  - GET /skills → 401
  - GET /cron/jobs → 401
  - GET /settings → 401

Y2. 無效 token
  Authorization: Bearer invalid_token_xyz
  - GET /settings → 401

Y3. 用戶對話隔離
  - 驗證 GET /conversations 返回的對話都屬於當前用戶

Y4. API key 不洩露
  - GET /settings → 回應中不含 "sk-" 或 api_key 欄位
  - GET /llm_providers → 回應中不含 api_key

Y5. XSS 防護
  - POST /skills body="<script>alert('xss')</script>"
  - GET skill → 內容為純文本, 不被瀏覽器執行

Y6. SQL injection 防護
  - POST /memory/search {"query": "'; DROP TABLE conversation_messages; --"}
  - 驗證: 回應 200 (正常搜尋結果或空), 不是 500

Y7. 路徑穿越防護
  - POST /skills name="../../etc/passwd" → 400 或被 sanitize
  - GET /skills/..%2F..%2Fetc%2Fpasswd → 404

Y8. 危險服務封鎖
  - 透過 MCP call_service("homeassistant", "restart") → 被封鎖
  - 透過 MCP call_service("persistent_notification", "dismiss_all") → 被封鎖
```

### Section Z: 資料完整性與清理

```
Z1. Consolidation 安全
  - GET /memory/memory → 記錄原始長度
  - POST /memory/consolidate
  - GET /memory/memory → 長度不異常縮小 (允許 ±20%)
  - GET /memory/history → 長度不縮小

Z2. Conversation retention
  - GET /conversations → 所有 updated_at 在保留期限內

Z3. Cron 持久化
  - 創建 job → 驗證 GET /cron/jobs 包含
  - 刪除 job → 驗證 GET /cron/jobs 不包含

Z4. Skill 一致性
  - GET /skills → 列出所有
  - 對每個: GET /skills/{name} → body 非空

Z5. Entity-Config 一致性
  - GET /settings → 記錄 temperature
  - 讀取 number.nanobot_temperature entity → 值一致
  - 設定 entity 為 0.5 → GET /settings → 驗證同步

Z6. LRU 保護
  - 創建 5 個對話各發訊息
  - 全部 GET messages → 正確
  - 清理

Z7. 歷史清理
  - 驗證 conversation_recorder 有 retention_days 設定
  - GET /settings → 確認 history_retention 欄位存在
```

---

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 新增 8 個 section (S-Z) | 覆蓋現有測試所有空缺 |
| 維持 bash curl 測試風格 | 與現有 A-R section 風格統一 |
| AI 回應測試用 soft assert | AI 回覆非確定性, 用 warning 不用 failure |
| 安全測試用 hard assert | 安全問題必須 0 failure |
| 並發測試用 bash background | 簡單有效, 不需額外依賴 |
| MCP 工具測試直接用 SSE | 比 AI 對話精準, 可驗證參數格式 |
| 參考 nanobot 議題設計測試 | 預防社群中已知類似問題 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (尚未開始實施) | | |

## Notes
- 現有測試: 234 cases (226 passed, 8 warnings, 0 failures)
- 預計新增: ~80 cases (S-Z sections)
- 目標: 300+ cases, 0 failures
- nanobot 參考議題: #1709 #1634 #1698 #1487 #1739 #1496 #1710 #1526 #1615
- 工具總數: 77+ (包含 CRUD 變體)
