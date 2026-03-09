# PRD: Helper Entity CRUD（建立/讀取/更新/刪除）

## 背景

目前 ha_mcp_client 套件可以**控制**已存在的 Helper 實體（`control_input_helper`, `control_timer`, `control_counter`），但無法**建立、編輯、刪除** Helper。使用者在對話中要求「建立 helper」時，AI 只能回答「不支援」。

本功能補齊這個缺口，讓 AI 助理能夠透過 MCP 工具和 REST API 對所有 8 種 Helper 類型進行完整 CRUD 操作。

## 目標

- 支援 8 種 Helper 類型的建立、列出、更新、刪除
- 透過 REST API + MCP 工具雙介面暴露
- 使用 HA WebSocket API（storage collection），建立後即時生效，無需重啟
- 每種 Helper 類型有獨立的 MCP create/update 工具，schema 精確對應該類型的欄位

## 支援的 Helper 類型

| # | 類型 | Domain | 說明 |
|---|------|--------|------|
| 1 | Input Boolean | `input_boolean` | 布林開關 |
| 2 | Input Number | `input_number` | 數字輸入 |
| 3 | Input Select | `input_select` | 下拉選單 |
| 4 | Input Text | `input_text` | 文字輸入 |
| 5 | Input Datetime | `input_datetime` | 日期時間 |
| 6 | Input Button | `input_button` | 按鈕 |
| 7 | Timer | `timer` | 計時器 |
| 8 | Counter | `counter` | 計數器 |

---

## 架構設計

### 三層結構

```
views.py          → REST API 端點（統一端點，body 帶 type）
registry.py       → MCP 工具註冊（每種類型獨立工具）
nanobot/helpers.py → 業務邏輯（WebSocket API 呼叫）
```

### 實作方式：HA Storage Collection

每種 Helper 類型在 HA 內部有 storage collection：

```python
# 取得 collection
store = hass.data.get(f"{domain}_storage_collection")

# CRUD
item = await store.async_create_item({"name": "...", ...})
await store.async_update_item(item_id, {"name": "...", ...})
await store.async_delete_item(item_id)
```

- `item_id` 可透過 entity registry 的 `unique_id` 取得
- 建立後即時生效，不需 reload 或重啟
- 與 UI 建立的 Helper 完全相容

### Storage Collection Key 對照表

| Helper 類型 | `hass.data` key |
|---|---|
| input_boolean | `input_boolean_storage_collection` |
| input_number | `input_number_storage_collection` |
| input_select | `input_select_storage_collection` |
| input_text | `input_text_storage_collection` |
| input_datetime | `input_datetime_storage_collection` |
| input_button | `input_button_storage_collection` |
| timer | `timer_storage_collection` |
| counter | `counter_storage_collection` |

---

## REST API 規格

### 端點一：`GET /api/ha_mcp_client/helpers`

列出所有 Helper 實體。

**查詢參數：**
- `type`（選填）— 篩選特定類型，如 `?type=input_boolean`

**回應 200：**
```json
[
  {
    "entity_id": "input_boolean.living_room_occupied",
    "type": "input_boolean",
    "name": "客廳有人",
    "state": "off",
    "icon": "mdi:account",
    "attributes": {}
  }
]
```

### 端點二：`POST /api/ha_mcp_client/helpers`

建立新 Helper。

**Request Body：**
```json
{
  "type": "input_number",
  "name": "溫度閾值",
  "min": 0,
  "max": 100,
  "step": 0.5,
  "mode": "slider",
  "unit_of_measurement": "°C",
  "icon": "mdi:thermometer",
  "initial": 25
}
```

**回應 201：**
```json
{
  "entity_id": "input_number.temperature_threshold",
  "type": "input_number",
  "name": "溫度閾值",
  "id": "item_id_from_store"
}
```

**錯誤回應：**
- 400 — `type` 缺失或無效、必填欄位缺失
- 400 — 重複名稱

### 端點三：`GET /api/ha_mcp_client/helpers/{entity_id}`

取得單一 Helper 的詳細資訊。

**回應 200：**
```json
{
  "entity_id": "input_number.temperature_threshold",
  "type": "input_number",
  "name": "溫度閾值",
  "state": "25.0",
  "icon": "mdi:thermometer",
  "attributes": {
    "min": 0,
    "max": 100,
    "step": 0.5,
    "mode": "slider",
    "unit_of_measurement": "°C"
  }
}
```

**錯誤回應：**
- 404 — entity_id 不存在
- 400 — entity_id 不是 helper domain

### 端點四：`PATCH /api/ha_mcp_client/helpers/{entity_id}`

更新 Helper 設定。只需傳送要更新的欄位。

**Request Body（範例 — input_number）：**
```json
{
  "name": "溫度閾值（新）",
  "max": 200,
  "icon": "mdi:thermometer-alert"
}
```

**回應 200：**
```json
{
  "entity_id": "input_number.temperature_threshold",
  "type": "input_number",
  "name": "溫度閾值（新）",
  "updated_fields": ["name", "max", "icon"]
}
```

**錯誤回應：**
- 404 — entity_id 不存在
- 400 — 包含不屬於該類型的欄位

### 端點五：`DELETE /api/ha_mcp_client/helpers/{entity_id}`

刪除 Helper。

**回應 200：**
```json
{
  "success": true,
  "deleted": "input_number.temperature_threshold"
}
```

**錯誤回應：**
- 404 — entity_id 不存在

---

## MCP 工具規格

### 通用工具（2 個）

#### `list_helpers`
```json
{
  "name": "list_helpers",
  "description": "列出所有 Helper 實體。可選篩選特定類型。",
  "input_schema": {
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["input_boolean", "input_number", "input_select", "input_text", "input_datetime", "input_button", "timer", "counter"],
        "description": "篩選特定 Helper 類型"
      }
    }
  },
  "category": "helper"
}
```

#### `delete_helper`
```json
{
  "name": "delete_helper",
  "description": "刪除指定的 Helper 實體。",
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {
        "type": "string",
        "description": "Helper 的 entity_id，例如 input_boolean.my_switch"
      }
    },
    "required": ["entity_id"]
  },
  "category": "helper"
}
```

### 各類型建立工具（8 個）

#### `create_input_boolean`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "icon": {"type": "string", "description": "MDI 圖示，如 mdi:toggle-switch"},
      "initial": {"type": "boolean", "description": "初始值"}
    },
    "required": ["name"]
  }
}
```

#### `create_input_number`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "min": {"type": "number", "description": "最小值"},
      "max": {"type": "number", "description": "最大值"},
      "step": {"type": "number", "description": "步進值，預設 1"},
      "mode": {"type": "string", "enum": ["slider", "box"], "description": "顯示模式"},
      "unit_of_measurement": {"type": "string", "description": "單位，如 °C, %, kg"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "initial": {"type": "number", "description": "初始值"}
    },
    "required": ["name", "min", "max"]
  }
}
```

#### `create_input_select`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "options": {"type": "array", "items": {"type": "string"}, "description": "選項列表"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "initial": {"type": "string", "description": "初始選取值（必須在 options 中）"}
    },
    "required": ["name", "options"]
  }
}
```

#### `create_input_text`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "min": {"type": "integer", "description": "最小長度，預設 0"},
      "max": {"type": "integer", "description": "最大長度，預設 100"},
      "pattern": {"type": "string", "description": "正規表達式驗證"},
      "mode": {"type": "string", "enum": ["text", "password"], "description": "顯示模式"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "initial": {"type": "string", "description": "初始值"}
    },
    "required": ["name"]
  }
}
```

#### `create_input_datetime`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "has_date": {"type": "boolean", "description": "是否包含日期，預設 true"},
      "has_time": {"type": "boolean", "description": "是否包含時間，預設 true"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "initial": {"type": "string", "description": "初始值，格式 YYYY-MM-DD HH:MM:SS"}
    },
    "required": ["name"]
  }
}
```

#### `create_input_button`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "icon": {"type": "string", "description": "MDI 圖示"}
    },
    "required": ["name"]
  }
}
```

#### `create_timer`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "duration": {"type": "string", "description": "預設持續時間，格式 HH:MM:SS"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "restore": {"type": "boolean", "description": "重啟後恢復狀態"}
    },
    "required": ["name"]
  }
}
```

#### `create_counter`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "顯示名稱"},
      "initial": {"type": "integer", "description": "初始值，預設 0"},
      "step": {"type": "integer", "description": "步進值，預設 1"},
      "minimum": {"type": "integer", "description": "最小值"},
      "maximum": {"type": "integer", "description": "最大值"},
      "icon": {"type": "string", "description": "MDI 圖示"},
      "restore": {"type": "boolean", "description": "重啟後恢復狀態"}
    },
    "required": ["name"]
  }
}
```

### 各類型更新工具（8 個）

與建立工具相同的欄位，但 `entity_id` 為必填，其餘皆為選填（只傳要更新的欄位）。

#### `update_input_boolean`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string", "description": "entity_id，如 input_boolean.my_switch"},
      "name": {"type": "string"},
      "icon": {"type": "string"},
      "initial": {"type": "boolean"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_input_number`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "min": {"type": "number"},
      "max": {"type": "number"},
      "step": {"type": "number"},
      "mode": {"type": "string", "enum": ["slider", "box"]},
      "unit_of_measurement": {"type": "string"},
      "icon": {"type": "string"},
      "initial": {"type": "number"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_input_select`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "options": {"type": "array", "items": {"type": "string"}},
      "icon": {"type": "string"},
      "initial": {"type": "string"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_input_text`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "min": {"type": "integer"},
      "max": {"type": "integer"},
      "pattern": {"type": "string"},
      "mode": {"type": "string", "enum": ["text", "password"]},
      "icon": {"type": "string"},
      "initial": {"type": "string"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_input_datetime`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "has_date": {"type": "boolean"},
      "has_time": {"type": "boolean"},
      "icon": {"type": "string"},
      "initial": {"type": "string"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_input_button`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "icon": {"type": "string"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_timer`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "duration": {"type": "string"},
      "icon": {"type": "string"},
      "restore": {"type": "boolean"}
    },
    "required": ["entity_id"]
  }
}
```

#### `update_counter`
```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "initial": {"type": "integer"},
      "step": {"type": "integer"},
      "minimum": {"type": "integer"},
      "maximum": {"type": "integer"},
      "icon": {"type": "string"},
      "restore": {"type": "boolean"}
    },
    "required": ["entity_id"]
  }
}
```

---

## 安全機制

1. **Domain 驗證** — 只接受 8 種 helper domain 的 entity_id
2. **名稱 Sanitize** — 過濾特殊字元（與 skills 相同邏輯）
3. **類型欄位驗證** — 忽略不屬於該類型的欄位，不接受未知欄位
4. **刪除警告** — 如果 Helper 被自動化引用，回應中包含警告資訊

---

## 實作檔案清單

| 檔案 | 變更 |
|------|------|
| `nanobot/helpers_crud.py` | **新增** — Helper CRUD 業務邏輯 |
| `views.py` | **修改** — 新增 HelpersListView + HelperDetailView |
| `mcp/tools/registry.py` | **修改** — 註冊 18 個新 MCP 工具 |
| `mcp/tools/helpers.py` | **修改** — 新增 handler 函式（呼叫 nanobot/helpers_crud.py） |
| `__init__.py` | **修改** — 註冊新 views |
| `tests/test_all.sh` | **修改** — 新增 Helper CRUD 測試 section |

---

## 測試計畫

### REST API 測試
- 每種 Helper 類型完整 CRUD 循環（POST → GET → PATCH → GET → DELETE → GET 404）
- 必填欄位缺失 → 400
- 無效 type → 400
- 不存在的 entity_id → 404
- 非 helper domain 的 entity_id → 400

### MCP 工具測試
- 8 個 `create_*` 工具 — 建立後 entity 存在
- 8 個 `update_*` 工具 — 修改後屬性更新
- `list_helpers` — 含 type 篩選
- `delete_helper` — 刪除後 entity 消失

### AI 對話測試
- 自然語言建立：「建立一個布林開關叫客廳有人」
- 自然語言列出：「列出所有 helper」
- 自然語言刪除：「刪除客廳有人這個 helper」

### 邊界測試
- 重複名稱處理
- 超出範圍的數值（input_number 的 min > max）
- 空 options 列表（input_select）
- input_datetime 的 has_date 和 has_time 都為 false

---

## 工具總數統計

| 類別 | 數量 |
|------|------|
| 建立工具（create_*） | 8 |
| 更新工具（update_*） | 8 |
| 通用工具（list + delete） | 2 |
| **MCP 工具總計** | **18** |
| REST 端點 | 5（2 list/create + 3 detail） |
