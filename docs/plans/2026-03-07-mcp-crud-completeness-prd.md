# PRD: MCP 工具完整性 — 日曆/待辦 CRUD、藍圖、服務域覆蓋

**日期**: 2026-03-07
**狀態**: 設計中
**優先級**: P0 — 核心功能缺口

---

## 1. 問題摘要

目前 HA MCP Client 已註冊 29 個工具，但存在以下關鍵缺口：

1. **日曆 (Calendar)**: 僅有 `create_calendar_event`，缺少列表/讀取/更新/刪除功能
2. **待辦事項 (Todo)**: 完全沒有 MCP 工具，儘管 HA 提供 5 個 todo 服務
3. **藍圖 (Blueprints)**: 完全沒有 MCP 工具，使用者詢問藍圖時 AI 無法操作
4. **通知 (Notifications)**: 無法透過 AI 發送通知
5. **輸入輔助 (Input Helpers)**: `input_boolean`, `input_number`, `input_select` 等無專屬工具
6. **其他域覆蓋**: 28 個服務域目前未被 MCP 工具覆蓋

**使用者期望**: 所有在 HA 前端可以操作的功能，都應該能透過 MCP/AI 使用。

---

## 2. 目標

### 2.1 必須達成 (P0)
- 日曆事件完整 CRUD（列表、更新、刪除）
- 待辦事項完整 CRUD（新增、列表、更新、刪除、清除已完成）
- 藍圖操作（列表、從藍圖建立自動化/腳本）

### 2.2 應該達成 (P1)
- 通知功能（發送通知到裝置/服務）
- 輸入輔助控制（input_boolean, input_number, input_select, input_datetime, input_button, input_text）
- 計時器控制（timer start/pause/cancel/finish）
- 計數器控制（counter increment/decrement/reset）

### 2.3 可以考慮 (P2)
- 備份管理（backup create/list）
- 攝影機操作（camera snapshot/turn_on/off）
- TTS 語音播報
- 持久通知管理
- 排程管理 (schedule)
- 購物清單（已被 todo 取代但部分用戶仍在使用）

---

## 3. 現狀分析

### 3.1 已有工具清單（29 個）

| 類別 | 工具名稱 | 操作 |
|------|----------|------|
| Entity | `get_entity_state`, `search_entities`, `list_entities` | 查詢 |
| Service | `call_service`, `list_services` | 通用服務呼叫 |
| Area | `create_area`, `list_areas`, `delete_area`, `assign_entity_to_area` | CRUD |
| Label | `create_label`, `list_labels`, `delete_label`, `assign_entity_to_labels` | CRUD |
| Light | `control_light` | 控制 |
| Climate | `control_climate` | 控制 |
| Cover | `control_cover` | 控制 |
| Scene | `list_scenes`, `activate_scene`, `create_scene` | CRA |
| Automation | `list_automations`, `create_automation` | CR |
| Script | `list_scripts`, `run_script`, `create_script` | CRX |
| Calendar | `create_calendar_event` | C 僅建立 |
| History | `get_history` | 查詢 |

### 3.2 HA 服務域覆蓋分析

| 域 | 已覆蓋 | 缺少的關鍵服務 |
|----|--------|----------------|
| `calendar` | 部分 | `get_events` (REST API), `event/update`, `event/delete` (WebSocket) |
| `todo` | 無 | `add_item`, `get_items`, `update_item`, `remove_item`, `remove_completed_items` |
| `automation` | 部分 | `toggle`, `trigger` (handler 存在但未註冊), `delete` |
| `script` | 部分 | `delete` |
| `scene` | 部分 | `delete` |
| `notify` | 無 | `notify` (多種通知服務) |
| `input_boolean` | 無 | `turn_on`, `turn_off`, `toggle` |
| `input_number` | 無 | `set_value`, `increment`, `decrement` |
| `input_select` | 無 | `select_option`, `select_first`, `select_last`, `select_next`, `select_previous`, `set_options` |
| `input_datetime` | 無 | `set_datetime` |
| `input_button` | 無 | `press` |
| `input_text` | 無 | `set_value` |
| `timer` | 無 | `start`, `pause`, `cancel`, `finish`, `change` |
| `counter` | 無 | `increment`, `decrement`, `reset`, `set_value` |
| `fan` | 無 | `turn_on`, `turn_off`, `set_percentage`, `set_preset_mode`, `set_direction`, `oscillate` |
| `switch` | 無（可用 `call_service`）| `turn_on`, `turn_off`, `toggle` |
| `lock` | 無（可用 `call_service`）| `lock`, `unlock`, `open` |
| `media_player` | 無 | 完整媒體控制 |
| `camera` | 無 | `snapshot`, `turn_on`, `turn_off` |
| `tts` | 無 | `speak`, `clear_cache` |
| `backup` | 無 | `create` |
| `persistent_notification` | 無 | `create`, `dismiss` |

### 3.3 藍圖 API 可用性

已驗證的 WebSocket API：
- `blueprint/list` — `{type: "blueprint/list", domain: "automation"}` ✅
- `blueprint/list` — `{type: "blueprint/list", domain: "script"}` ✅
- `blueprint/import` — 需要 `url` 參數（從 GitHub 等來源匯入）

---

## 4. 設計方案

### 4.1 新增工具清單

#### Phase 1: P0 — 日曆 CRUD（3 個新工具）

**4.1.1 `list_calendar_events`**
```python
ToolDefinition(
    name="list_calendar_events",
    description="列出指定日曆在時間範圍內的事件",
    input_schema={
        "type": "object",
        "properties": {
            "calendar_entity_id": {
                "type": "string",
                "description": "日曆實體 ID，如 calendar.family"
            },
            "start": {
                "type": "string",
                "description": "開始時間 (ISO 8601 格式)，預設為今天 00:00"
            },
            "end": {
                "type": "string",
                "description": "結束時間 (ISO 8601 格式)，預設為 7 天後"
            }
        },
        "required": ["calendar_entity_id"]
    },
    category="calendar"
)
```
**實作方式**: 使用 REST API `GET /api/calendars/{entity_id}?start=...&end=...`，回傳事件列表含 `uid`、`summary`、`start`、`end`、`description`、`location`。

**4.1.2 `update_calendar_event`**
```python
ToolDefinition(
    name="update_calendar_event",
    description="更新日曆事件的摘要、時間、說明或地點",
    input_schema={
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string", "description": "日曆實體 ID"},
            "uid": {"type": "string", "description": "事件 UID（從 list_calendar_events 取得）"},
            "summary": {"type": "string", "description": "新的事件標題"},
            "start": {"type": "string", "description": "新的開始時間 (ISO 8601)"},
            "end": {"type": "string", "description": "新的結束時間 (ISO 8601)"},
            "description": {"type": "string", "description": "新的事件描述"},
            "location": {"type": "string", "description": "新的地點"},
            "recurrence_id": {"type": "string", "description": "重複事件的特定實例 ID"}
        },
        "required": ["calendar_entity_id", "uid"]
    },
    category="calendar"
)
```
**實作方式**: 使用 WebSocket API `calendar/event/update`，傳入 `entity_id`、`uid`、`event` 物件和可選 `recurrence_id`。

**4.1.3 `delete_calendar_event`**
```python
ToolDefinition(
    name="delete_calendar_event",
    description="刪除指定日曆事件",
    input_schema={
        "type": "object",
        "properties": {
            "calendar_entity_id": {"type": "string", "description": "日曆實體 ID"},
            "uid": {"type": "string", "description": "事件 UID（從 list_calendar_events 取得）"},
            "recurrence_id": {"type": "string", "description": "重複事件的特定實例 ID（刪除單一實例時使用）"}
        },
        "required": ["calendar_entity_id", "uid"]
    },
    category="calendar"
)
```
**實作方式**: 使用 WebSocket API `calendar/event/delete`。

#### Phase 1: P0 — 待辦事項 CRUD（5 個新工具）

**4.1.4 `list_todo_items`**
```python
ToolDefinition(
    name="list_todo_items",
    description="列出待辦事項清單中的項目",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "待辦事項實體 ID，如 todo.shopping_list"},
            "status": {
                "type": "string",
                "enum": ["needs_action", "completed"],
                "description": "篩選狀態：needs_action=未完成, completed=已完成"
            }
        },
        "required": ["entity_id"]
    },
    category="todo"
)
```
**實作方式**: 使用 `hass.services.async_call("todo", "get_items", ..., return_response=True)`。注意 `return_response=True` 是必須的，否則結果為空。

**4.1.5 `add_todo_item`**
```python
ToolDefinition(
    name="add_todo_item",
    description="在待辦事項清單中新增項目",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "待辦事項實體 ID"},
            "item": {"type": "string", "description": "項目名稱"},
            "due_date": {"type": "string", "description": "截止日期 (YYYY-MM-DD)"},
            "due_datetime": {"type": "string", "description": "截止時間 (ISO 8601)"},
            "description": {"type": "string", "description": "項目描述"}
        },
        "required": ["entity_id", "item"]
    },
    category="todo"
)
```

**4.1.6 `update_todo_item`**
```python
ToolDefinition(
    name="update_todo_item",
    description="更新待辦事項（重新命名、標記完成/未完成、修改截止日期等）",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "待辦事項實體 ID"},
            "item": {"type": "string", "description": "要更新的項目名稱"},
            "rename": {"type": "string", "description": "新的項目名稱"},
            "status": {
                "type": "string",
                "enum": ["needs_action", "completed"],
                "description": "新狀態"
            },
            "due_date": {"type": "string", "description": "新截止日期 (YYYY-MM-DD)"},
            "due_datetime": {"type": "string", "description": "新截止時間 (ISO 8601)"},
            "description": {"type": "string", "description": "新描述"}
        },
        "required": ["entity_id", "item"]
    },
    category="todo"
)
```

**4.1.7 `remove_todo_item`**
```python
ToolDefinition(
    name="remove_todo_item",
    description="從待辦事項清單中移除項目",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "待辦事項實體 ID"},
            "item": {"type": "string", "description": "要移除的項目名稱"}
        },
        "required": ["entity_id", "item"]
    },
    category="todo"
)
```

**4.1.8 `remove_completed_todo_items`**
```python
ToolDefinition(
    name="remove_completed_todo_items",
    description="清除待辦事項清單中所有已完成的項目",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "待辦事項實體 ID"}
        },
        "required": ["entity_id"]
    },
    category="todo"
)
```

#### Phase 1: P0 — 藍圖操作（2 個新工具）

**4.1.9 `list_blueprints`**
```python
ToolDefinition(
    name="list_blueprints",
    description="列出已安裝的自動化或腳本藍圖",
    input_schema={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": ["automation", "script"],
                "description": "藍圖域：automation 或 script"
            }
        },
        "required": ["domain"]
    },
    category="blueprint"
)
```
**實作方式**: 使用 WebSocket API `blueprint/list`，回傳藍圖列表含 `path`、`metadata`（`name`, `description`, `input`, `domain`）。

**4.1.10 `import_blueprint`**
```python
ToolDefinition(
    name="import_blueprint",
    description="從 URL 匯入藍圖（支援 GitHub、Home Assistant Community 等來源）",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "藍圖來源 URL（GitHub raw URL 或 HA Community 論壇連結）"
            }
        },
        "required": ["url"]
    },
    category="blueprint"
)
```
**實作方式**: 使用 WebSocket API `blueprint/import`，傳入 `url` 參數。

#### Phase 2: P1 — 通知與輸入輔助（4 個新工具）

**4.1.11 `send_notification`**
```python
ToolDefinition(
    name="send_notification",
    description="發送通知到裝置或通知服務",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "通知訊息內容"},
            "title": {"type": "string", "description": "通知標題"},
            "target": {"type": "string", "description": "通知目標服務，如 notify.mobile_app_phone"},
            "data": {"type": "object", "description": "額外資料（如圖片 URL、動作按鈕等）"}
        },
        "required": ["message"]
    },
    category="notification"
)
```
**實作方式**: 若未指定 `target`，使用 `notify.notify`（預設廣播）；否則呼叫指定的 notify 服務。

**4.1.12 `control_input_helper`**
```python
ToolDefinition(
    name="control_input_helper",
    description="控制輸入輔助實體（布林開關、數字、選擇、日期時間、按鈕、文字）",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "輸入輔助實體 ID"},
            "action": {
                "type": "string",
                "enum": ["turn_on", "turn_off", "toggle", "set_value", "increment", "decrement",
                         "select_option", "select_next", "select_previous", "set_datetime", "press"],
                "description": "操作動作"
            },
            "value": {
                "description": "設定值（數字的 value、選擇的 option、日期時間的 datetime 等）"
            }
        },
        "required": ["entity_id", "action"]
    },
    category="input_helper"
)
```
**實作方式**: 根據 `entity_id` 域前綴（`input_boolean`, `input_number` 等）自動路由到對應服務。

**4.1.13 `control_timer`**
```python
ToolDefinition(
    name="control_timer",
    description="控制計時器（開始、暫停、取消、完成、修改時間）",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "計時器實體 ID"},
            "action": {
                "type": "string",
                "enum": ["start", "pause", "cancel", "finish", "change"],
                "description": "操作動作"
            },
            "duration": {"type": "string", "description": "持續時間 (HH:MM:SS)，用於 start 和 change"}
        },
        "required": ["entity_id", "action"]
    },
    category="timer"
)
```

**4.1.14 `control_fan`**
```python
ToolDefinition(
    name="control_fan",
    description="控制風扇（開關、風速、擺動、方向）",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "風扇實體 ID"},
            "action": {
                "type": "string",
                "enum": ["turn_on", "turn_off", "toggle", "set_percentage", "set_preset_mode",
                         "set_direction", "oscillate"],
                "description": "操作動作"
            },
            "percentage": {"type": "integer", "description": "風速百分比 (0-100)"},
            "preset_mode": {"type": "string", "description": "預設模式"},
            "direction": {"type": "string", "enum": ["forward", "reverse"], "description": "風向"},
            "oscillating": {"type": "boolean", "description": "是否擺動"}
        },
        "required": ["entity_id", "action"]
    },
    category="fan"
)
```

#### Phase 2: P1 — 補齊已有類別缺口（3 個新工具）

**4.1.15 `delete_automation`**
```python
ToolDefinition(
    name="delete_automation",
    description="刪除自動化",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "自動化實體 ID"}
        },
        "required": ["entity_id"]
    },
    category="automation"
)
```
**實作方式**: 從 `automations.yaml` 移除對應項目後呼叫 `automation.reload`。

**4.1.16 `delete_script`**
```python
ToolDefinition(
    name="delete_script",
    description="刪除腳本",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "腳本實體 ID"}
        },
        "required": ["entity_id"]
    },
    category="script"
)
```

**4.1.17 `delete_scene`**
```python
ToolDefinition(
    name="delete_scene",
    description="刪除場景",
    input_schema={
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "場景實體 ID"}
        },
        "required": ["entity_id"]
    },
    category="scene"
)
```

---

## 5. 實作架構

### 5.1 檔案修改清單

| 檔案 | 修改內容 |
|------|----------|
| `mcp/tools/helpers.py` | 新增 13 個 helper 函數 |
| `mcp/tools/registry.py` | 新增 17 個工具定義 + handler 方法 |
| `tests/test_tools.py` | 新增對應單元測試 |

### 5.2 Helper 函數設計

#### Calendar helpers（新增 3 個函數）

```python
async def list_calendar_events(
    hass: HomeAssistant,
    calendar_entity_id: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """列出日曆事件。使用內部 calendar API。"""

async def update_calendar_event(
    hass: HomeAssistant,
    calendar_entity_id: str,
    uid: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    recurrence_id: str | None = None,
) -> dict[str, Any]:
    """更新日曆事件。使用 WebSocket API calendar/event/update。"""

async def delete_calendar_event(
    hass: HomeAssistant,
    calendar_entity_id: str,
    uid: str,
    recurrence_id: str | None = None,
) -> dict[str, Any]:
    """刪除日曆事件。使用 WebSocket API calendar/event/delete。"""
```

#### Todo helpers（新增 5 個函數）

```python
async def list_todo_items(
    hass: HomeAssistant,
    entity_id: str,
    status: str | None = None,
) -> dict[str, Any]:
    """列出待辦事項。使用 todo.get_items + return_response=True。"""

async def add_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
    due_date: str | None = None,
    due_datetime: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """新增待辦事項。"""

async def update_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
    rename: str | None = None,
    status: str | None = None,
    due_date: str | None = None,
    due_datetime: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """更新待辦事項。"""

async def remove_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
) -> dict[str, Any]:
    """移除待辦事項。"""

async def remove_completed_todo_items(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, Any]:
    """清除已完成的待辦事項。"""
```

#### Blueprint helpers（新增 2 個函數）

```python
async def list_blueprints(
    hass: HomeAssistant,
    domain: str,
) -> list[dict[str, Any]]:
    """列出藍圖。使用 WebSocket API blueprint/list。"""

async def import_blueprint(
    hass: HomeAssistant,
    url: str,
) -> dict[str, Any]:
    """匯入藍圖。使用 WebSocket API blueprint/import。"""
```

#### Other helpers（新增 3 個函數）

```python
async def send_notification(
    hass: HomeAssistant,
    message: str,
    title: str | None = None,
    target: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """發送通知。"""

async def control_input_helper(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    value: Any = None,
) -> dict[str, Any]:
    """控制輸入輔助實體。根據 entity_id 域自動路由。"""

async def delete_yaml_entity(
    hass: HomeAssistant,
    entity_id: str,
    yaml_file: str,
    reload_domain: str,
) -> dict[str, Any]:
    """從 YAML 檔案刪除實體配置並重載。
    通用函數用於刪除 automation/script/scene。"""
```

### 5.3 Calendar API 實作細節

**列出事件 — 使用 HA 內部 API**:
```python
from homeassistant.components.calendar import async_get_events

async def list_calendar_events(hass, calendar_entity_id, start=None, end=None):
    entity = hass.states.get(calendar_entity_id)
    if not entity:
        return {"error": f"找不到日曆: {calendar_entity_id}"}

    # 預設時間範圍：今天到 7 天後
    now = datetime.now(timezone.utc)
    start_dt = datetime.fromisoformat(start) if start else now.replace(hour=0, minute=0, second=0)
    end_dt = datetime.fromisoformat(end) if end else start_dt + timedelta(days=7)

    # 使用 HA calendar platform API
    calendar_component = hass.data.get("calendar")
    platform = hass.data["calendar"].get_entity(calendar_entity_id)
    events = await platform.async_get_events(hass, start_dt, end_dt)

    return [{"uid": e.uid, "summary": e.summary, "start": str(e.start), "end": str(e.end),
             "description": e.description, "location": e.location} for e in events]
```

**更新/刪除事件 — 使用 WebSocket commands**:
```python
from homeassistant.components.calendar import async_handle_calendar_event_update

async def update_calendar_event(hass, calendar_entity_id, uid, **kwargs):
    # 構建 event 物件（僅含有變更的欄位）
    event = {}
    for field in ["summary", "description", "location"]:
        if kwargs.get(field) is not None:
            event[field] = kwargs[field]
    if kwargs.get("start"):
        event["dtstart"] = kwargs["start"]
    if kwargs.get("end"):
        event["dtend"] = kwargs["end"]

    # 使用 hass.services 或直接呼叫 calendar platform
    connection = hass.data["websocket_api"]  # 需要確認正確路徑
    # 或者直接使用 calendar entity 的方法：
    entity = hass.data["calendar"].get_entity(calendar_entity_id)
    await entity.async_update_event(uid, event, recurrence_id=kwargs.get("recurrence_id"))
    return {"status": "updated", "uid": uid}
```

### 5.4 Todo API 實作細節

```python
async def list_todo_items(hass, entity_id, status=None):
    service_data = {}
    if status:
        service_data["status"] = status

    # 關鍵：必須使用 return_response=True
    result = await hass.services.async_call(
        "todo", "get_items",
        service_data=service_data,
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return result
```

### 5.5 Blueprint API 實作細節

```python
from homeassistant.components.blueprint import models as blueprint_models

async def list_blueprints(hass, domain):
    # 使用 HA 內部的 blueprint domain handler
    from homeassistant.components.blueprint.models import DomainBlueprints
    domain_blueprints = hass.data.get("blueprint", {}).get(domain)
    if not domain_blueprints:
        return {"error": f"無 {domain} 藍圖域", "available_domains": ["automation", "script"]}

    blueprints = await domain_blueprints.async_get_blueprints()
    result = []
    for path, bp in blueprints.items():
        if bp is not None:
            metadata = bp.metadata or {}
            result.append({
                "path": path,
                "name": metadata.get("name", path),
                "description": metadata.get("description", ""),
                "domain": metadata.get("domain", domain),
                "input": metadata.get("input", {}),
            })
    return result
```

---

## 6. 工具使用流程範例

### 6.1 日曆 CRUD 完整流程

```
使用者: 「這週有什麼行程？」
AI: [呼叫 list_calendar_events(calendar.family, start=本週一, end=本週日)]
AI: 「你這週有以下行程：
      1. 週二 3pm 團隊週會
      2. 週四 全天 家庭大掃除
      3. 週六 2pm 牙醫預約」

使用者: 「把團隊週會改到下午 4 點」
AI: [呼叫 update_calendar_event(calendar.family, uid=xxx, start=週二4pm, end=週二5pm)]
AI: 「已將團隊週會改到下午 4:00-5:00」

使用者: 「取消牙醫預約」
AI: [呼叫 delete_calendar_event(calendar.family, uid=yyy)]
AI: 「已刪除週六 2pm 的牙醫預約」
```

### 6.2 待辦事項完整流程

```
使用者: 「購物清單上有什麼？」
AI: [呼叫 list_todo_items(todo.shopping_list)]
AI: 「購物清單目前有：牛奶、雞蛋、麵包」

使用者: 「加上洗衣精和衛生紙」
AI: [呼叫 add_todo_item(todo.shopping_list, "洗衣精")]
    [呼叫 add_todo_item(todo.shopping_list, "衛生紙")]
AI: 「已新增洗衣精和衛生紙到購物清單」

使用者: 「牛奶已經買了」
AI: [呼叫 update_todo_item(todo.shopping_list, "牛奶", status="completed")]
AI: 「已標記牛奶為已完成」

使用者: 「把麵包改成全麥麵包」
AI: [呼叫 update_todo_item(todo.shopping_list, "麵包", rename="全麥麵包")]
AI: 「已將麵包重新命名為全麥麵包」

使用者: 「清掉所有買完的東西」
AI: [呼叫 remove_completed_todo_items(todo.shopping_list)]
AI: 「已清除所有已完成的項目」
```

### 6.3 藍圖操作流程

```
使用者: 「有什麼可用的自動化藍圖？」
AI: [呼叫 list_blueprints(domain="automation")]
AI: 「目前安裝了以下自動化藍圖：
      1. 動作感應燈 (Motion-activated Light)
      2. 確認通知 (Confirmable Notification)」

使用者: 「從 GitHub 匯入一個新藍圖」
AI: 「請提供藍圖的 URL」
使用者: 「https://github.com/home-assistant/...」
AI: [呼叫 import_blueprint(url="https://github.com/...")]
AI: 「藍圖已成功匯入」
```

---

## 7. 實作順序

### Phase 1（P0 — 核心 CRUD）

| 步驟 | 內容 | 新增工具數 |
|------|------|-----------|
| 1 | Todo CRUD helpers + registry 註冊 | 5 |
| 2 | Calendar list/update/delete helpers + registry 註冊 | 3 |
| 3 | Blueprint list/import helpers + registry 註冊 | 2 |
| 4 | 部署測試 | — |

**Phase 1 完成後**: 29 → 39 個工具

### Phase 2（P1 — 擴展覆蓋）

| 步驟 | 內容 | 新增工具數 |
|------|------|-----------|
| 5 | 通知工具 | 1 |
| 6 | 輸入輔助控制工具 | 1 |
| 7 | 計時器/計數器控制工具 | 1 |
| 8 | 風扇控制工具 | 1 |
| 9 | 刪除 automation/script/scene 工具 | 3 |
| 10 | 部署測試 | — |

**Phase 2 完成後**: 39 → 46 個工具

### 關於 `call_service` 的通用性說明

> `call_service` 工具已經可以呼叫任意 HA 服務。為什麼還需要專屬工具？

1. **AI 可發現性**: AI 模型需要知道有哪些可用工具。專屬工具的 schema 讓 AI 知道確切的參數格式。
2. **參數驗證**: 專屬工具在呼叫前驗證參數，避免錯誤的服務呼叫。
3. **特殊 API**: `list_calendar_events` 需要 REST API、`list_todo_items` 需要 `return_response=True`、`list_blueprints` 需要 WebSocket API — 這些都不是 `call_service` 能處理的。
4. **使用者體驗**: 「請使用 add_todo_item 工具」比「請呼叫 todo.add_item 服務並傳入 item 參數」更直覺。

---

## 8. 測試計畫

### 8.1 單元測試（每個新工具至少 2 個測試）

| 工具 | 測試場景 |
|------|----------|
| `list_calendar_events` | 正常列出 / 空日曆 / 無效實體 |
| `update_calendar_event` | 正常更新 / 部分欄位更新 / 不存在的 UID |
| `delete_calendar_event` | 正常刪除 / 不存在的 UID |
| `list_todo_items` | 正常列出 / 依狀態篩選 / 空清單 |
| `add_todo_item` | 正常新增 / 含截止日期 / 含描述 |
| `update_todo_item` | 重新命名 / 標記完成 / 修改截止日期 |
| `remove_todo_item` | 正常移除 / 不存在的項目 |
| `remove_completed_todo_items` | 正常清除 / 無已完成項目 |
| `list_blueprints` | automation 域 / script 域 / 無效域 |
| `import_blueprint` | 正常匯入 / 無效 URL |

### 8.2 整合測試（透過聊天面板）

使用 §6 的使用流程作為整合測試腳本，驗證 AI 能正確使用新工具完成對話式操作。

---

## 9. 風險與緩解

| 風險 | 影響 | 緩解方式 |
|------|------|----------|
| Calendar internal API 變更 | 無法列出/更新/刪除事件 | 使用 WebSocket API 作為備援 |
| `return_response=True` 行為 | todo.get_items 可能回傳格式變更 | 加入回傳值驗證和容錯 |
| Blueprint import 安全風險 | 使用者匯入惡意藍圖 | AI 提示使用者確認來源；限制僅官方和社群來源 |
| 工具數量爆增影響 AI 效能 | Token 使用量增加 | 使用工具分類篩選，僅發送相關類別的工具 |
| YAML 檔案寫入併發問題 | 刪除操作可能損壞檔案 | 使用 hass.async_add_executor_job 確保序列化 |

---

## 10. 成功指標

- [ ] Phase 1: 10 個新工具全部註冊且可透過聊天面板使用
- [ ] Phase 2: 額外 7 個新工具註冊
- [ ] 日曆 CRUD 完整流程可在對話中完成
- [ ] 待辦事項 CRUD 完整流程可在對話中完成
- [ ] 藍圖列表和匯入可透過 AI 操作
- [ ] 所有工具通過單元測試
- [ ] 使用者問「有什麼藍圖」時 AI 能正確回應
