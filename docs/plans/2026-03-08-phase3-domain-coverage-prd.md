# PRD: Phase 3 — P2 域覆蓋擴展

**日期**: 2026-03-08
**狀態**: 設計完成
**前提**: Phase 1 (12 工具, 21/21 PASS) + Phase 2 (6 工具, 17/17 PASS) 已完成，共 49 工具

---

## 1. 目標

將目前 49 個工具擴展至涵蓋 PRD 中 §2.3 列出的所有 P2 項目，以及實際 HA 實例中存在但尚未被專屬工具覆蓋的服務域。

**核心原則**：使用者在 HA 前端可以操作的功能，都應該能透過 MCP/AI 使用。

---

## 2. 新增工具清單 (8 個新工具)

### 2.1 `control_media_player` — 媒體播放器控制

控制音響、電視等媒體設備。

```
參數:
  entity_id: string (required) — 媒體播放器實體 ID
  action: enum (required) — media_play, media_pause, media_stop, media_next_track,
          media_previous_track, volume_up, volume_down, volume_set, volume_mute,
          turn_on, turn_off, toggle, select_source, play_media, shuffle_set, repeat_set
  volume_level: number — 音量 (0.0-1.0)，用於 volume_set
  is_volume_muted: boolean — 靜音狀態
  media_content_id: string — 媒體 ID，用於 play_media
  media_content_type: string — 媒體類型 (music, video, playlist 等)
  source: string — 輸入源名稱，用於 select_source
  shuffle: boolean — 隨機播放
  repeat: enum (off, all, one) — 重複模式
```

**實作方式**: 直接呼叫 `media_player.{action}` 服務，根據 action 帶入對應參數。

### 2.2 `control_lock` — 門鎖控制

控制智慧門鎖。

```
參數:
  entity_id: string (required) — 門鎖實體 ID
  action: enum (required) — lock, unlock, open
```

**實作方式**: 呼叫 `lock.{action}` 服務。

### 2.3 `speak_tts` — TTS 語音播報

透過 TTS 服務播放語音通知。

```
參數:
  entity_id: string (required) — 媒體播放器實體 ID（用於播放語音的設備）
  message: string (required) — 要播報的文字
  language: string — 語言代碼 (zh-TW, en-US 等)
  cache: boolean — 是否快取 (預設 true)
```

**實作方式**: 使用 `tts.speak` 服務，指定 `entity_id`（target media player）和 `message`。
若 HA 實例有 `tts.cloud_say`（Nabu Casa），也支援路由。

### 2.4 `control_persistent_notification` — 持久通知管理

建立和管理持久通知（在 HA 前端持續顯示，直到使用者手動關閉）。

```
參數:
  action: enum (required) — create, dismiss, dismiss_all
  message: string — 通知內容 (create 時必須)
  title: string — 通知標題
  notification_id: string — 通知 ID (dismiss 時必須; create 時可指定以便後續更新/關閉)
```

**實作方式**: 呼叫 `persistent_notification.{action}` 服務。

### 2.5 `control_counter` — 計數器控制

控制計數器實體。

```
參數:
  entity_id: string (required) — 計數器實體 ID
  action: enum (required) — increment, decrement, reset, set_value
  value: number — 用於 set_value
```

**實作方式**: 呼叫 `counter.{action}` 服務。

### 2.6 `manage_backup` — 備份管理

建立系統備份。

```
參數:
  action: enum (required) — create, create_automatic
```

**實作方式**: 呼叫 `backup.{action}` 服務。注意：備份操作可能耗時，使用 `blocking=True` 等待完成。

### 2.7 `control_camera` — 攝影機控制

攝影機截圖和開關控制。

```
參數:
  entity_id: string (required) — 攝影機實體 ID
  action: enum (required) — snapshot, turn_on, turn_off, enable_motion_detection,
          disable_motion_detection
  filename: string — 截圖儲存路徑 (snapshot 時使用)
```

**實作方式**: 呼叫 `camera.{action}` 服務。

### 2.8 `control_switch` — 開關控制

控制智慧開關。

```
參數:
  entity_id: string (required) — 開關實體 ID
  action: enum (required) — turn_on, turn_off, toggle
```

**實作方式**: 呼叫 `switch.{action}` 服務。雖然 `call_service` 可做同樣的事，但專屬工具讓 AI 更容易發現和使用。

---

## 3. 實作架構

### 3.1 檔案修改

| 檔案 | 修改內容 |
|------|----------|
| `mcp/tools/helpers.py` | 新增 8 個 helper 函數 |
| `mcp/tools/registry.py` | 新增 8 個 ToolDefinition + 8 個 handler 方法 |

### 3.2 實作順序

| 步驟 | 工具 | 新增數 |
|------|------|--------|
| 1 | control_media_player | 1 |
| 2 | control_lock | 1 |
| 3 | speak_tts | 1 |
| 4 | control_persistent_notification | 1 |
| 5 | control_counter | 1 |
| 6 | manage_backup | 1 |
| 7 | control_camera | 1 |
| 8 | control_switch | 1 |
| 9 | 部署測試 | — |

**Phase 3 完成後**: 49 → 57 個工具

### 3.3 排除項目說明

以下域不建立專屬工具，原因如下：

| 域 | 排除原因 |
|----|----------|
| `shopping_list` | 已被 `todo` 取代，5 個 todo 工具已覆蓋 |
| `schedule` | HA 的 schedule 僅提供 `get_schedule` + `reload`，無法透過服務 API 建立/修改排程，只能在 UI 操作 |
| `valve` | 與 cover 類似但更罕見；使用者可透過 `call_service` 操作 |
| `number` / `select` | 與 `input_number` / `input_select` 類似，已被 `control_input_helper` 的路由模式覆蓋概念，且可用 `call_service` |
| `device_tracker` | `see` 服務主要供整合內部使用 |
| `cloud` / `ffmpeg` / `frontend` / `logger` | 系統內部服務，不適合 AI 操作 |

---

## 4. 測試計畫

### 4.1 每工具測試項目

| 工具 | 測試場景 | 預計測試數 |
|------|----------|-----------|
| `control_media_player` | 無實體驗證 / 無效動作 / 無效實體 | 3 |
| `control_lock` | lock/unlock 正常 / 無效實體 | 3 |
| `speak_tts` | 正常播報 / 無效實體 | 2 |
| `control_persistent_notification` | create → dismiss / dismiss_all | 3 |
| `control_counter` | 無實體驗證 / 無效動作 | 2 |
| `manage_backup` | create 正常 | 1 |
| `control_camera` | 無實體驗證 / 無效動作 | 2 |
| `control_switch` | turn_on → turn_off → toggle / 無效實體 | 3 |
| **合計** | | **~19** |

### 4.2 測試策略

- 有實體的域（lock, switch, tts）：完整生命週期測試
- 無實體的域（media_player, camera, counter）：驗證邏輯正確回傳錯誤
- 特殊域（backup）：實際呼叫測試
- 持久通知：完整 create → dismiss 生命週期

---

## 5. 風險與緩解

| 風險 | 緩解 |
|------|------|
| media_player 參數複雜 | 根據 action 只帶入必要參數 |
| backup 耗時 | 使用 blocking=True，加 timeout |
| camera snapshot 需要寫入路徑 | 預設合理路徑或讓使用者指定 |
| 工具數量增至 57 個 | 使用工具分類篩選機制 |

---

## 6. 成功指標

- [ ] 8 個新工具全部註冊
- [ ] 部署測試全部通過
- [ ] 工具總數達到 57 個
- [ ] 所有 P2 項目已覆蓋或已說明排除原因
