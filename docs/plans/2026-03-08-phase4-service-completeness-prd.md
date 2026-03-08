# Phase 4：服務完整性 — PRD

> 目標：以覆蓋 HA `call_service` 所有用戶向域為目標，補完 CRUD 缺口 + 增強現有工具 + 新增遺漏域

## 現狀（57 工具）

- Phase 1：12 工具（CRUD 完整性）
- Phase 2：6 工具（擴展覆蓋）
- Phase 3：8 工具（P2 域覆蓋）
- 原始工具：31

## Gap Analysis

### 部分覆蓋（需增強）

| 域 | 現有工具 | 缺口 |
|---|---------|------|
| automation | list/toggle/trigger/create/delete | **缺 update_automation** |
| script | list/run/create/delete | **缺 update_script + toggle(enable/disable)** |
| cover | control_cover (open/close/stop/set_position) | **缺 tilt 操作** (open_tilt, close_tilt, set_tilt_position, stop_tilt, toggle_tilt) |
| climate | control_climate (set_hvac_mode/set_temperature) | **缺 fan_mode, swing_mode, preset_mode, humidity, turn_on/off** |
| camera | control_camera (snapshot/on/off/motion_detection) | **缺 play_stream, record** |
| fan | control_fan | **缺 increase_speed, decrease_speed** |
| media_player | control_media_player | **缺 media_seek, select_sound_mode** |

### 未覆蓋的用戶向域

| 域 | 描述 |
|---|------|
| valve | 閥門控制 (open/close/stop/set_position/toggle) |
| number | 裝置整合的 number 實體 (set_value) |
| shopping_list | 購物清單管理 (add/remove/complete/incomplete/clear/sort) |

### 系統/內部域（不做）

homeassistant, frontend, logger, system_log, recorder, logbook, ffmpeg, cloud, person, zone, virtual, ha_mcp_client, conversation, device_tracker, file, schedule

理由：系統管理操作、調試工具、或透過 `call_service` 通用工具即可存取。

---

## Phase 4 實施計畫

### P4-A：CRUD 補完 + 增強（7 項）

#### 1. `update_automation` — 自動化更新
- 讀取 automations.yaml，定位 `id` 匹配項
- 可更新欄位：alias, description, trigger, condition, action, mode
- 寫回 yaml + reload automation 域

#### 2. `update_script` — 腳本更新
- 讀取 scripts.yaml，定位 key 匹配項
- 可更新欄位：alias, description, sequence, mode, icon
- 寫回 yaml + reload script 域
- 同時支援 enable/disable（toggle）

#### 3. 增強 `control_cover` — 加入 tilt
- 新增 actions：open_tilt, close_tilt, stop_tilt, set_tilt_position, toggle_tilt
- 新增參數：tilt_position (0-100)

#### 4. 增強 `control_climate` — 完整空調控制
- 新增 actions：turn_on, turn_off
- 新增參數：fan_mode, swing_mode, preset_mode, humidity

#### 5. 增強 `control_camera` — 串流與錄影
- 新增 actions：play_stream, record
- play_stream 參數：media_player (target), format
- record 參數：filename, duration, lookback

#### 6. 增強 `control_fan` — 速度步進
- 新增 actions：increase_speed, decrease_speed

#### 7. 增強 `control_media_player` — 搜尋與音效
- 新增 actions：media_seek (seek_position)
- 新增 actions：select_sound_mode (sound_mode)

### P4-B：新域覆蓋（3 項）

#### 8. `control_valve` — 閥門控制
- actions：open, close, stop, set_position, toggle
- 參數：entity_id, action, position (0-100)
- 結構類似 control_cover

#### 9. `control_number` — Number 域控制
- action：set_value
- 參數：entity_id, value
- 驗證 min/max 範圍（從 entity attributes 取得）

#### 10. `control_shopping_list` — 購物清單管理
- actions：add_item, remove_item, complete_item, incomplete_item, complete_all, incomplete_all, clear_completed, sort
- 參數：action, name (物品名稱)

---

## 測試策略

每個工具/增強項目各設計 2-4 個測試案例：
- 正常操作 (happy path)
- 錯誤實體 (entity_not_found)
- 無效操作 (invalid_action)
- 邊界條件 (如適用)

部署後統一跑測試，目標全 PASS。

## 預期結果

- 工具總數：57 → 60（新增 3 個工具）+ 7 個增強
- 覆蓋所有 HA 用戶向 service 域
- 所有域的 CRUD 閉環完成

## 排除項

- `conversation.process` — MCP 本身就是對話層，不需要再委派給 HA conversation
- `device_tracker.see` — 主要供整合用，非用戶直接操作
- `file.read_file` — 安全性考量
- `schedule.get_schedule` — 唯讀、價值低
- 所有 `reload` 服務 — 系統級，create/update/delete 已隱含觸發
