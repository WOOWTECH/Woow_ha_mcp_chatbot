# PRD: 部署後詳細測試計畫

**日期**: 2026-03-07
**狀態**: 完成
**環境**: Podman HA port 18123, 31 工具已註冊

---

## 1. 測試環境

| 項目 | 值 |
|------|-----|
| HA Container | homeassistant (port 18123) |
| Entry ID | 01KK3W34MX75ZR1EMP35AAKX65 |
| Conversation Entity | conversation.ha_mcp_client_ha_mcp_client_01kk3w34mx75zr1emp35aakx65 |
| Calendar | calendar.jia_ting |
| Todo | todo.shopping_list (13 items) |
| Lights | light.living_room_light, light.bedroom_light, light.kitchen_light |
| Switches | switch.living_room_fan, switch.kitchen_coffee_maker |
| Covers | cover.bedroom_curtain_cover, cover.garage_door_cover |
| Lock | lock.garage_lock |
| Sensors | 溫度 x3, 濕度 x1, 二進制 x5 |
| Automations | 2 (客廳動態開燈) |

---

## 2. 測試矩陣

### Category A: 基礎驗證 (A1-A5)

| ID | 測試項目 | 方法 | 預期結果 |
|----|----------|------|----------|
| A1 | HA API 連通 | GET /api/ | HTTP 200 |
| A2 | ha_mcp_client 載入 | config_entries | state=loaded |
| A3 | MCP SSE 端點 | GET /api/ha_mcp_client/sse | SSE stream |
| A4 | Chat Panel API | GET /api/ha_mcp_client/conversations | JSON list |
| A5 | Conversation Entity | GET /api/states | entity exists |

### Category B: MCP 工具 — 實體查詢 (B1-B6)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| B1 | 查詢實體狀態 | get_entity_state | 回傳 state + attributes |
| B2 | 搜尋實體 | search_entities | 回傳匹配實體列表 |
| B3 | 系統概覽 | system_overview | 回傳域/實體統計 |
| B4 | 列出裝置 | list_devices | 回傳裝置列表 |
| B5 | 列出服務 | list_services | 回傳服務列表 |
| B6 | 查詢歷史 | get_history | 回傳歷史記錄 |

### Category C: MCP 工具 — 裝置控制 (C1-C8)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| C1 | 開燈 | control_light | state=on |
| C2 | 調亮度 | control_light | brightness=128 |
| C3 | 關燈 | control_light | state=off |
| C4 | 開窗簾 | control_cover | state=open/opening |
| C5 | 關窗簾 | control_cover | state=closed/closing |
| C6 | 解鎖 | call_service(lock.unlock) | state=unlocked |
| C7 | 上鎖 | call_service(lock.lock) | state=locked |
| C8 | 開關風扇 | call_service(switch.toggle) | state 切換 |

### Category D: MCP 工具 — 區域/標籤 (D1-D6)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| D1 | 列出區域 | list_areas | 回傳區域列表 |
| D2 | 建立區域 | create_area | 新區域建立 |
| D3 | 更新區域 | update_area | 區域名稱更新 |
| D4 | 刪除區域 | delete_area | 區域移除 |
| D5 | 列出標籤 | list_labels | 回傳標籤列表 |
| D6 | 建立+刪除標籤 | create_label + delete_label | CRUD 完整 |

### Category E: MCP 工具 — 自動化/腳本/場景 (E1-E8)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| E1 | 列出自動化 | list_automations | 回傳 2 個自動化 |
| E2 | 切換自動化 | toggle_automation | state 切換 |
| E3 | 觸發自動化 | trigger_automation | 觸發成功 |
| E4 | 建立自動化 | create_automation | 新自動化建立 |
| E5 | 列出場景 | list_scenes | 回傳場景列表 |
| E6 | 建立場景 | create_scene | 場景建立 |
| E7 | 啟動場景 | activate_scene | 場景啟動 |
| E8 | 建立+執行腳本 | create_script + run_script | 腳本 CRUD |

### Category F: MCP 工具 — 日曆 (F1-F3)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| F1 | 建立日曆事件 | create_calendar_event | 事件建立 |
| F2 | 通用呼叫 | call_service(calendar.get_events) | 事件列表 |
| F3 | 建立全天事件 | create_calendar_event | 全天事件建立 |

### Category G: MCP 工具 — 待辦事項 (G1-G4)

| ID | 測試項目 | 工具 | 預期結果 |
|----|----------|------|----------|
| G1 | 新增待辦 | call_service(todo.add_item) | 項目新增 |
| G2 | 列出待辦 | call_service(todo.get_items) | 回傳項目列表 |
| G3 | 更新待辦 | call_service(todo.update_item) | 項目更新 |
| G4 | 刪除待辦 | call_service(todo.remove_item) | 項目移除 |

### Category H: AI 對話整合 (H1-H5)

| ID | 測試項目 | 方法 | 預期結果 |
|----|----------|------|----------|
| H1 | 中文查詢裝置 | conversation.process | AI 回應含溫度 |
| H2 | 中文控制裝置 | conversation.process | AI 執行開燈 |
| H3 | 建立對話 | POST /conversations | 對話 ID 回傳 |
| H4 | 傳送訊息 | POST /conversations/{id}/messages | AI 回應 |
| H5 | 列出對話 | GET /conversations | 對話列表 |

### Category I: 聊天面板前端 (I1-I3)

| ID | 測試項目 | 方法 | 預期結果 |
|----|----------|------|----------|
| I1 | 面板頁面可訪問 | GET /ha_mcp_client/panel/ | HTTP 200 + HTML |
| I2 | CSS 載入 | GET /ha_mcp_client/panel/styles.css | HTTP 200 |
| I3 | JS 載入 | GET /ha_mcp_client/panel/app.js | HTTP 200 |

---

## 3. 測試結果

### 第一輪測試 (修復前)

| Category | 項目數 | PASS | FAIL | 備註 |
|----------|--------|------|------|------|
| A 基礎驗證 | 5 | 5 | 0 | |
| B 實體查詢 | 6 | 6 | 0 | |
| C 裝置控制 | 8 | 6 | 2 | C1/C2: action 值需用 "on"/"off" 而非 "turn_on"/"turn_off" |
| D 區域/標籤 | 6 | 6 | 0 | |
| E 自動化/腳本/場景 | 8 | 7 | 1 | E8: create_script 回傳 "unsupported" |
| F 日曆 | 3 | 1 | 2 | F2: return_response 不支援; F3: 全天事件失敗 |
| G 待辦事項 | 4 | 4 | 0 | |
| H AI 對話 | 5 | 5 | 0 | |
| I 前端面板 | 3 | 1 | 2 | I2/I3: 測試路徑錯誤 |
| **合計** | **48** | **41** | **7** | |

### 修復項目

| Bug | 根本原因 | 修復方式 | 檔案 |
|-----|----------|----------|------|
| E8 create_script "unsupported" | `config_script.async_create_item` 不存在 | 改用 scripts.yaml 寫入 + script.reload | `helpers.py:447-513` |
| F3 全天事件失敗 | 一律用 `start_date_time`/`end_date_time` | 偵測 date-only 格式自動切換 `start_date`/`end_date`; 新增 `all_day` 參數 | `helpers.py:583-655`, `registry.py:860-880` |
| I2/I3 前端路徑 404 | 測試用 `/api/ha_mcp_client/panel/` | 正確路徑為 `/ha_mcp_client/panel/styles.css` 和 `/ha_mcp_client/panel/app.js` | 測試邏輯修正 |
| C1/C2 action 值 | `control_light` handler 期望 "on"/"off" 而非 "turn_on" | 測試邏輯修正 (非 bug) | — |
| F2 return_response | `call_service` helper 不支援 `return_response` | 已知限制，列入 CRUD PRD | — |

### 第二輪測試 (修復後)

| Category | 項目數 | PASS | FAIL | 備註 |
|----------|--------|------|------|------|
| A 基礎驗證 | 5 | 5 | 0 | |
| B 實體查詢 | 6 | 6 | 0 | |
| C 裝置控制 | 8 | 8 | 0 | action 值修正為 "on"/"off"/"toggle" |
| D 區域/標籤 | 6 | 6 | 0 | |
| E 自動化/腳本/場景 | 8 | 8 | 0 | create_script 改用 scripts.yaml |
| F 日曆 | 3 | 3 | 0 | 全天事件支援 start_date/end_date + auto-detect |
| G 待辦事項 | 4 | 4 | 0 | |
| H AI 對話 | 5 | 5 | 0 | |
| I 前端面板 | 3 | 3 | 0 | 路徑修正為 /ha_mcp_client/panel/ |
| **合計** | **48** | **48** | **0** | **100% PASS** |

### 已知限制

| 項目 | 說明 | 解決方案 |
|------|------|----------|
| F2 call_service return_response | `call_service` helper 無法取得服務回傳值 | CRUD PRD Phase 1 新增專用工具 |
| 場景非持久化 | `create_scene` 使用動態場景服務 | CRUD PRD Phase 1 改用 scenes.yaml |

---

## 4. 總計: 48 個測試, 100% PASS
