# Cron Job Automation Bridge — 產品需求文件 (PRD)

## 1. 概述

### 1.1 專案名稱
**Cron Automation Bridge** — 將 Nanobot 排程任務橋接為 HA 原生自動化與藍圖

### 1.2 專案目標
將現有的 Nanobot Cron Job 系統橋接到 Home Assistant 原生的 Automation 與 Blueprint 機制，讓使用者可以：
1. **一鍵轉換** — 從 cron job 生成 HA 原生 automation
2. **Blueprint 模板** — 5 個預建藍圖覆蓋常見 AI 排程場景
3. **雙向可見** — 在 HA Dashboard 中管理由 cron job 產生的 automation
4. **保留 AI 能力** — `agent_turn` 透過 `conversation.process` 服務呼叫實現

### 1.3 核心價值
- **Bridge, not Replace** — 保留 cron 系統的靈活性（agent_turn 是 HA 原生無法做到的），同時讓使用者享受 HA 自動化 UI 的便利
- **藍圖化** — 常見的 AI 排程模式打包為可分享的 Blueprint，降低設定門檻
- **可發現性** — cron job 產生的 automation 出現在 HA 的自動化面板中，而非隱藏在自訂 JSON

### 1.4 設計原則
- **A (Bridge Approach)**: Cron job 保持為模板/工廠，生成原生 automation
- **A1 (conversation.process)**: `agent_turn` 透過直接 service call 實現，在 HA UI 中透明可見

---

## 2. 系統架構

### 2.1 架構圖

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HA MCP Client Integration                      │
│                                                                       │
│  ┌─────────────────────┐        ┌──────────────────────────────┐    │
│  │   Nanobot Cron       │        │     HA Native Automation      │    │
│  │   System             │  ───▶  │     System                    │    │
│  │                      │ Bridge │                                │    │
│  │  • agent_turn        │        │  • automations.yaml            │    │
│  │  • system_event      │        │  • HA Automation UI            │    │
│  │  • at/every/cron     │        │  • Blueprint Templates         │    │
│  │  • store.json        │        │                                │    │
│  └─────────────────────┘        └──────────────────────────────┘    │
│           │                                  │                        │
│           ▼                                  ▼                        │
│  ┌─────────────────────┐        ┌──────────────────────────────┐    │
│  │  Bridge Layer        │        │     Blueprint Store            │    │
│  │                      │        │                                │    │
│  │  • schedule→trigger  │        │  • ai_daily_report.yaml        │    │
│  │  • payload→action    │        │  • ai_periodic_check.yaml      │    │
│  │  • metadata mapping  │        │  • scheduled_device_control    │    │
│  │  • REST API          │        │  • interval_monitor.yaml       │    │
│  │  • MCP Tool          │        │  • cron_event_trigger.yaml     │    │
│  └─────────────────────┘        └──────────────────────────────┘    │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                  conversation.process                           │  │
│  │  AI conversation service call — agent_turn 的執行方式            │  │
│  │  action:                                                        │  │
│  │    - service: conversation.process                              │  │
│  │      data:                                                      │  │
│  │        text: "{cron_job.payload.message}"                       │  │
│  │        agent_id: conversation.ha_mcp_client_...                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 排程映射表

| Cron Schedule Kind | HA Trigger Platform | 轉換邏輯 |
|---|---|---|
| `at` (一次性, Unix ms) | `platform: time` | 將 Unix timestamp 轉為 `HH:MM:SS` |
| `every` (間隔, ms) | `platform: time_pattern` | 轉為 hours/minutes/seconds pattern |
| `cron` (cron 表達式) | `platform: time_pattern` | 解析 cron 表達式為 hour/minute pattern |

### 2.3 Payload 映射表

| Cron Payload Kind | HA Automation Action | 說明 |
|---|---|---|
| `agent_turn` | `conversation.process` | 直接呼叫 AI 對話服務，message 作為 text 參數 |
| `system_event` | `event: ...` + `ha_mcp_client_cron_system_event` | 觸發 HA 自訂事件 |

---

## 3. 功能規格

### 3.1 Bridge API — 從 Cron Job 生成 Automation

#### 3.1.1 REST Endpoint

```
POST /api/ha_mcp_client/cron/jobs/{job_id}/to_automation
```

**Request Body (optional overrides):**
```json
{
  "alias": "Custom automation name",
  "description": "Optional description",
  "mode": "single"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "automation_id": "abc123def456",
  "entity_id": "automation.cron_hourly_temp_check",
  "source_job_id": "1f734cc3",
  "trigger": [{"platform": "time_pattern", "minutes": "/30"}],
  "action": [{"service": "conversation.process", "data": {"text": "...", "agent_id": "..."}}],
  "message": "已從 cron job 'hourly-temp-check' 建立 HA automation"
}
```

#### 3.1.2 MCP Tool

```python
ToolDefinition(
    name="cron_to_automation",
    description="Convert a cron job to a native HA automation. The automation will appear in HA's automation UI.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Cron job ID to convert"},
            "alias": {"type": "string", "description": "Optional custom name for the automation"},
            "keep_cron_job": {"type": "boolean", "description": "Keep the original cron job (default: true)"},
        },
        "required": ["job_id"],
    },
)
```

#### 3.1.3 轉換邏輯

```python
async def cron_to_automation(hass, cron_job, alias=None, keep_cron_job=True):
    """Convert a CronJob to a native HA automation."""

    # 1. Map schedule → trigger
    trigger = _schedule_to_trigger(cron_job.schedule)

    # 2. Map payload → action
    action = _payload_to_action(hass, cron_job.payload)

    # 3. Build automation config
    automation_alias = alias or f"Cron: {cron_job.name}"
    description = (
        f"Auto-generated from cron job [{cron_job.id}] '{cron_job.name}'. "
        f"Schedule: {cron_job.schedule.kind}, Payload: {cron_job.payload.kind}"
    )

    # 4. Create via existing create_automation()
    result = await create_automation(
        hass,
        alias=automation_alias,
        trigger=trigger,
        action=action,
        description=description,
    )

    # 5. Optionally disable original cron job
    if not keep_cron_job:
        cron_job.enabled = False

    return result
```

### 3.2 Schedule 轉換函式

```python
def _schedule_to_trigger(schedule: CronSchedule) -> list[dict]:
    """Convert CronSchedule to HA automation trigger list."""

    if schedule.kind == "at":
        # One-time: convert Unix ms → datetime → time string
        dt = datetime.fromtimestamp(schedule.at_ms / 1000, tz=timezone.utc)
        local_dt = dt.astimezone()
        return [{"platform": "time", "at": local_dt.strftime("%H:%M:%S")}]

    elif schedule.kind == "every":
        # Interval: convert ms → time_pattern
        total_seconds = schedule.every_ms // 1000
        if total_seconds >= 3600:
            hours = total_seconds // 3600
            return [{"platform": "time_pattern", "hours": f"/{hours}"}]
        elif total_seconds >= 60:
            minutes = total_seconds // 60
            return [{"platform": "time_pattern", "minutes": f"/{minutes}"}]
        else:
            return [{"platform": "time_pattern", "seconds": f"/{total_seconds}"}]

    elif schedule.kind == "cron":
        # Parse cron expression → time_pattern
        # Format: "minute hour day month weekday"
        parts = (schedule.cron or "* * * * *").split()
        trigger = {"platform": "time_pattern"}
        if len(parts) >= 1 and parts[0] != "*":
            trigger["minutes"] = parts[0]  # e.g., "0", "*/30"
        if len(parts) >= 2 and parts[1] != "*":
            trigger["hours"] = parts[1]    # e.g., "7", "*/2"
        return [trigger]

    return [{"platform": "time_pattern", "minutes": "/30"}]  # fallback
```

### 3.3 Payload 轉換函式

```python
def _payload_to_action(hass: HomeAssistant, payload: CronPayload) -> list[dict]:
    """Convert CronPayload to HA automation action list."""

    if payload.kind == "agent_turn":
        # Find the conversation entity for this integration
        agent_id = _find_mcp_conversation_entity(hass)
        return [{
            "service": "conversation.process",
            "data": {
                "text": payload.message,
                "agent_id": agent_id,
            },
        }]

    elif payload.kind == "system_event":
        return [{
            "event": "ha_mcp_client_cron_system_event",
            "event_data": {
                "message": payload.message,
                "source": "cron_bridge",
            },
        }]

    return []
```

---

## 4. Blueprint 模板規格

### 4.1 Blueprint 格式

每個 Blueprint 遵循 HA Blueprint YAML 格式：

```yaml
blueprint:
  name: "Blueprint Name"
  description: "What this blueprint does"
  domain: automation
  source_url: "https://github.com/..."
  input:
    input_name:
      name: "Human readable name"
      description: "What this input does"
      selector:
        type: ...

trigger: ...
condition: ...
action: ...
```

### 4.2 Blueprint 1: AI 每日報告 (`ai_daily_report`)

**用途**: 每天固定時間讓 AI 檢查所有感測器並產生智慧家居摘要報告

```yaml
blueprint:
  name: "AI 每日智慧家居報告"
  description: >
    每天在指定時間觸發 AI 助手，自動檢查所有感測器狀態並產生
    智慧家居摘要報告。可自訂報告內容和通知方式。
  domain: automation
  input:
    report_time:
      name: "報告時間"
      description: "每天產生報告的時間"
      default: "08:00:00"
      selector:
        time:
    report_prompt:
      name: "報告指令"
      description: "給 AI 的報告指令"
      default: >
        請檢查所有感測器狀態，包含溫度、濕度、門窗狀態等，
        並產生一份簡潔的智慧家居狀態摘要。如有異常請特別標註。
      selector:
        text:
          multiline: true
    conversation_entity:
      name: "AI 對話實體"
      description: "選擇 HA MCP Client 的對話實體"
      selector:
        entity:
          filter:
            domain: conversation

trigger:
  - platform: time
    at: !input report_time

action:
  - service: conversation.process
    data:
      text: !input report_prompt
      agent_id: !input conversation_entity
```

### 4.3 Blueprint 2: AI 定期狀態檢查 (`ai_periodic_check`)

**用途**: 每隔 N 分鐘讓 AI 檢查特定裝置並在異常時通知

```yaml
blueprint:
  name: "AI 定期裝置檢查"
  description: >
    定期讓 AI 助手檢查指定裝置的狀態。適合監控重要感測器，
    如伺服器室溫度、水管漏水偵測等。
  domain: automation
  input:
    check_interval:
      name: "檢查間隔 (分鐘)"
      description: "多久檢查一次"
      default: 30
      selector:
        number:
          min: 5
          max: 1440
          unit_of_measurement: "分鐘"
    check_prompt:
      name: "檢查指令"
      description: "給 AI 的檢查指令，包含要監控的裝置"
      default: "檢查 sensor.living_room_temperature，如果溫度超過 30 度請通知我"
      selector:
        text:
          multiline: true
    conversation_entity:
      name: "AI 對話實體"
      selector:
        entity:
          filter:
            domain: conversation

trigger:
  - platform: time_pattern
    minutes: !input check_interval

action:
  - service: conversation.process
    data:
      text: !input check_prompt
      agent_id: !input conversation_entity
```

### 4.4 Blueprint 3: 排程裝置控制 (`scheduled_device_control`)

**用途**: 定時透過 AI 語意理解來控制裝置（比原生 automation 更靈活）

```yaml
blueprint:
  name: "AI 排程裝置控制"
  description: >
    在指定時間讓 AI 助手執行裝置控制指令。AI 會理解語意並
    呼叫適當的服務。適合需要條件判斷的排程控制。
  domain: automation
  input:
    schedule_time:
      name: "執行時間"
      default: "22:00:00"
      selector:
        time:
    control_prompt:
      name: "控制指令"
      description: "用自然語言描述要執行的操作"
      default: "關閉所有燈光，除了臥室的夜燈"
      selector:
        text:
          multiline: true
    conversation_entity:
      name: "AI 對話實體"
      selector:
        entity:
          filter:
            domain: conversation

trigger:
  - platform: time
    at: !input schedule_time

action:
  - service: conversation.process
    data:
      text: !input control_prompt
      agent_id: !input conversation_entity
```

### 4.5 Blueprint 4: 間隔監控警報 (`interval_monitor`)

**用途**: 定期檢查條件，超過閾值時透過 AI 分析並發送通知

```yaml
blueprint:
  name: "AI 間隔監控與警報"
  description: >
    每隔指定時間讓 AI 檢查特定條件，如溫度、能源用量等，
    超過閾值時由 AI 分析原因並發送通知。
  domain: automation
  input:
    monitor_interval:
      name: "監控間隔 (分鐘)"
      default: 15
      selector:
        number:
          min: 1
          max: 1440
          unit_of_measurement: "分鐘"
    monitor_prompt:
      name: "監控指令"
      description: "給 AI 的監控與通知指令"
      default: >
        檢查以下感測器：
        1. sensor.living_room_temperature — 如果超過 28°C 通知我
        2. sensor.humidity — 如果低於 30% 通知我
        如果所有數值正常，不需要通知。
      selector:
        text:
          multiline: true
    conversation_entity:
      name: "AI 對話實體"
      selector:
        entity:
          filter:
            domain: conversation

trigger:
  - platform: time_pattern
    minutes: !input monitor_interval

action:
  - service: conversation.process
    data:
      text: !input monitor_prompt
      agent_id: !input conversation_entity
```

### 4.6 Blueprint 5: 定時事件觸發 (`cron_event_trigger`)

**用途**: 定時觸發 HA 自訂事件，供其他 automation 串接使用

```yaml
blueprint:
  name: "定時事件觸發器"
  description: >
    在指定的排程時間觸發 ha_mcp_client_cron_system_event 事件，
    其他 automation 可以監聽此事件作為觸發條件。
    適合建立事件驅動的自動化鏈。
  domain: automation
  input:
    trigger_time:
      name: "觸發時間"
      default: "00:00:00"
      selector:
        time:
    event_message:
      name: "事件訊息"
      description: "附加在事件中的訊息內容"
      default: "scheduled_trigger"
      selector:
        text:
    event_name:
      name: "事件名稱 (選填)"
      description: "自訂事件名稱，預設使用 ha_mcp_client_cron_system_event"
      default: "ha_mcp_client_cron_system_event"
      selector:
        text:

trigger:
  - platform: time
    at: !input trigger_time

action:
  - event: !input event_name
    event_data:
      message: !input event_message
      source: "blueprint_cron_event_trigger"
      triggered_at: "{{ now().isoformat() }}"
```

---

## 5. API 規格

### 5.1 新增 REST Endpoints

| Endpoint | Method | 說明 |
|---|---|---|
| `/api/ha_mcp_client/cron/jobs/{id}/to_automation` | POST | 將 cron job 轉為 HA automation |
| `/api/ha_mcp_client/blueprints` | GET | 列出所有已安裝的 bridge blueprints |
| `/api/ha_mcp_client/blueprints/install` | POST | 安裝內建 blueprint 到 HA |

### 5.2 新增 MCP Tools

| Tool Name | 說明 |
|---|---|
| `cron_to_automation` | 將指定 cron job 轉換為 HA 原生 automation |
| `install_cron_blueprints` | 安裝所有內建的 cron blueprint 模板到 HA |
| `list_cron_blueprints` | 列出可用的 cron blueprint 模板 |

---

## 6. 測試計畫

### 6.1 Cron Job 情境測試 (新增 Section Q)

#### Q1. Schedule 轉換正確性

| # | 測試案例 | 輸入 | 預期輸出 |
|---|---|---|---|
| 1 | at → time trigger | `at_ms=1773019200000` | `platform: time, at: "08:00:00"` |
| 2 | every 30min → time_pattern | `every_ms=1800000` | `platform: time_pattern, minutes: "/30"` |
| 3 | every 2hr → time_pattern | `every_ms=7200000` | `platform: time_pattern, hours: "/2"` |
| 4 | every 15s → time_pattern | `every_ms=15000` | `platform: time_pattern, seconds: "/15"` |
| 5 | cron daily 7am → time_pattern | `cron="0 7 * * *"` | `platform: time_pattern, hours: "7", minutes: "0"` |
| 6 | cron every 30min → time_pattern | `cron="*/30 * * * *"` | `platform: time_pattern, minutes: "*/30"` |
| 7 | cron weekday 9am → time_pattern | `cron="0 9 * * 1-5"` | `platform: time_pattern, hours: "9", minutes: "0"` |

#### Q2. Payload 轉換正確性

| # | 測試案例 | 預期 action |
|---|---|---|
| 1 | agent_turn → conversation.process | `service: conversation.process, data.text: message` |
| 2 | system_event → event fire | `event: ha_mcp_client_cron_system_event` |
| 3 | agent_turn 含中文 message | message 完整保留，無截斷 |

#### Q3. Bridge API 端對端

| # | 測試案例 | 預期結果 |
|---|---|---|
| 1 | POST to_automation → 201 | automation 建立成功 |
| 2 | 生成的 automation 出現在 HA | `automation.cron_*` entity 存在 |
| 3 | 手動觸發 automation 可執行 | `automation.trigger` 服務成功 |
| 4 | keep_cron_job=false 停用原 job | cron job enabled=false |
| 5 | 重複轉換不產生重複 automation | 回傳錯誤或跳過 |
| 6 | 不存在的 job_id → 404 | 回傳 404 |

#### Q4. Blueprint 安裝測試

| # | 測試案例 | 預期結果 |
|---|---|---|
| 1 | install_cron_blueprints → 200 | 5 個 blueprint 安裝成功 |
| 2 | list_blueprints domain=automation | 包含 5 個 cron blueprint |
| 3 | Blueprint 結構驗證 | 每個有 name/description/input/trigger/action |

#### Q5. 邊界條件

| # | 測試案例 | 預期結果 |
|---|---|---|
| 1 | at schedule 已過期 | 仍可轉換，trigger time 為過去時間 |
| 2 | every_ms < 60000 (< 1 min) | 轉為秒級 time_pattern |
| 3 | cron 表達式無效 | 回傳錯誤，不建立 automation |
| 4 | disabled cron job 轉換 | 可轉換，automation 也設為 disabled |
| 5 | payload.message 為空 | 回傳錯誤 |
| 6 | 無 conversation entity | agent_turn 回傳明確錯誤 |

---

## 7. 實作計畫

### Phase 1: Bridge Core (核心轉換)
1. 在 `helpers.py` 新增 `cron_to_automation()`, `_schedule_to_trigger()`, `_payload_to_action()`
2. 在 `views.py` 新增 `CronToAutomationView` endpoint
3. 在 `registry.py` 新增 `cron_to_automation` MCP tool
4. 新增測試 Section Q (Q1-Q3)

### Phase 2: Blueprints (藍圖模板)
5. 在 `custom_components/ha_mcp_client/blueprints/automation/` 建立 5 個 YAML
6. 在 `__init__.py` 中自動註冊 blueprints
7. 新增 blueprint API endpoints
8. 新增測試 Section Q4

### Phase 3: Polish (收尾)
9. 邊界條件處理和錯誤訊息
10. 前端 app.js 新增 "轉為 Automation" 按鈕 (if applicable)
11. 完整測試 Q5
12. 部署驗證

---

## 8. RICE 優先級分析

| Feature | Reach | Impact | Confidence | Effort | RICE Score |
|---|---|---|---|---|---|
| Bridge Core (cron→automation) | 500 | High (2x) | High (100%) | S (0.5) | **2000** |
| 5 Blueprint Templates | 500 | Medium (1x) | High (100%) | S (0.5) | **1000** |
| Bridge REST API | 300 | Medium (1x) | High (100%) | XS (0.25) | **1200** |
| Bridge MCP Tool | 300 | Medium (1x) | High (100%) | XS (0.25) | **1200** |
| Frontend "Convert" Button | 200 | Low (0.5x) | Medium (80%) | S (0.5) | **160** |

**Priority Order**: Bridge Core → REST API / MCP Tool → Blueprints → Frontend

---

## 9. 成功指標

| 指標 | 目標 |
|---|---|
| 所有 3 種 schedule 正確轉換為 HA trigger | 100% |
| 所有 2 種 payload 正確轉換為 HA action | 100% |
| 5 個 Blueprint 可成功安裝到 HA | 100% |
| 生成的 automation 可在 HA UI 中管理 | 100% |
| 新增測試 (Section Q) 通過率 | ≥ 95% |
| 轉換 API 回應時間 | < 2 秒 |

---

## 10. 風險與緩解

| 風險 | 影響 | 緩解方案 |
|---|---|---|
| cron 表達式無法 1:1 對應 HA time_pattern | Medium | 複雜 cron 表達式退化為 best-effort 轉換 + 警告訊息 |
| conversation.process 服務不可用 | High | 轉換時檢查 entity 是否存在，缺少時回傳明確錯誤 |
| Blueprint 格式在 HA 版本間變更 | Low | 使用穩定的 blueprint schema，標註最低支援版本 |
| 使用者同時運行 cron job 和生成的 automation | Medium | 文件說明，keep_cron_job 參數預設 true + 提示 |

---

## 11. 非範圍 (Out of Scope)

- **取代 cron 系統** — Bridge 是補充，不是替代
- **雙向同步** — 修改 automation 不會反向更新 cron job
- **複雜 cron 表達式** — 不支援 day-of-month 或 month 限制的精確轉換
- **Blueprint Exchange** — 不包含上傳到 HA Community 的功能
- **自動化 Editor UI** — 不在前端新增完整的 automation 編輯器
