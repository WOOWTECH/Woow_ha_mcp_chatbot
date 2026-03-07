# HA MCP Client - 建立 Automation/Script 功能設計

## 問題描述

用戶透過 Conversation Entity 要求 AI 建立自動化或腳本時，AI 會說「已建立」但實際上沒有任何效果。

**根本原因**：目前的工具只支援：
- `list_automations` / `list_scripts` - 列出
- `toggle_automation` / `trigger_automation` - 開關/觸發
- `run_script` - 執行

缺少 **建立** 功能。

## 需求

| 項目 | 決定 |
|------|------|
| 功能範圍 | 建立 Automation 和 Script |
| 建立方式 | 透過 HA REST API |
| 用戶確認 | 不需要，直接建立 |
| 錯誤處理 | 回報錯誤，讓用戶決定 |
| 額外需求 | AI 要能使用所有 HA Services |

## 技術設計

### 1. 新增工具

#### 1.1 `create_automation`

建立 Home Assistant 自動化。

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "alias": {
      "type": "string",
      "description": "自動化名稱（必填）"
    },
    "description": {
      "type": "string",
      "description": "自動化描述"
    },
    "mode": {
      "type": "string",
      "enum": ["single", "restart", "queued", "parallel"],
      "description": "執行模式，預設 single"
    },
    "trigger": {
      "type": "array",
      "description": "觸發器列表（必填）",
      "items": {
        "type": "object"
      }
    },
    "condition": {
      "type": "array",
      "description": "條件列表（選填）",
      "items": {
        "type": "object"
      }
    },
    "action": {
      "type": "array",
      "description": "動作列表（必填）",
      "items": {
        "type": "object"
      }
    }
  },
  "required": ["alias", "trigger", "action"]
}
```

**常用觸發器範例：**
```yaml
# 時間觸發
- platform: time
  at: "07:00:00"

# 日落觸發
- platform: sun
  event: sunset
  offset: "-00:30:00"

# 狀態變化觸發
- platform: state
  entity_id: binary_sensor.motion
  to: "on"

# 數值觸發
- platform: numeric_state
  entity_id: sensor.temperature
  above: 25
```

**常用動作範例：**
```yaml
# 呼叫服務
- service: light.turn_on
  target:
    entity_id: light.living_room
  data:
    brightness: 255

# 延遲
- delay: "00:05:00"

# 條件執行
- if:
    - condition: state
      entity_id: sun.sun
      state: "below_horizon"
  then:
    - service: light.turn_on
      target:
        entity_id: light.porch
```

**API 實作：**
```python
async def _handle_create_automation(
    self,
    alias: str,
    trigger: list[dict],
    action: list[dict],
    description: str | None = None,
    mode: str = "single",
    condition: list[dict] | None = None,
) -> dict[str, Any]:
    """建立自動化"""
    import uuid

    automation_id = str(uuid.uuid4())

    config = {
        "id": automation_id,
        "alias": alias,
        "trigger": trigger,
        "action": action,
        "mode": mode,
    }

    if description:
        config["description"] = description
    if condition:
        config["condition"] = condition

    # 使用 HA 的 config API
    await self.hass.services.async_call(
        "automation",
        "reload",
    )

    # 透過 websocket 或 REST API 建立
    result = await self.hass.config_entries.flow.async_configure(...)

    return {
        "success": True,
        "automation_id": automation_id,
        "entity_id": f"automation.{alias.lower().replace(' ', '_')}",
    }
```

#### 1.2 `create_script`

建立 Home Assistant 腳本。

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "腳本名稱（必填）"
    },
    "description": {
      "type": "string",
      "description": "腳本描述"
    },
    "mode": {
      "type": "string",
      "enum": ["single", "restart", "queued", "parallel"],
      "description": "執行模式，預設 single"
    },
    "fields": {
      "type": "object",
      "description": "腳本參數定義"
    },
    "sequence": {
      "type": "array",
      "description": "動作序列（必填）",
      "items": {
        "type": "object"
      }
    }
  },
  "required": ["name", "sequence"]
}
```

**範例：**
```json
{
  "name": "離家模式",
  "description": "關閉所有燈光和電器",
  "sequence": [
    {
      "service": "light.turn_off",
      "target": {
        "entity_id": "all"
      }
    },
    {
      "service": "climate.turn_off",
      "target": {
        "entity_id": "climate.living_room"
      }
    }
  ]
}
```

#### 1.3 `get_service_schema`

取得特定服務的完整參數 schema，讓 AI 知道如何正確呼叫服務。

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "domain": {
      "type": "string",
      "description": "服務 domain（例如：light, climate, automation）"
    },
    "service": {
      "type": "string",
      "description": "服務名稱（例如：turn_on, set_temperature）"
    }
  },
  "required": ["domain", "service"]
}
```

**回傳範例：**
```json
{
  "domain": "light",
  "service": "turn_on",
  "description": "Turn on a light",
  "fields": {
    "brightness": {
      "description": "Brightness (0-255)",
      "example": 255,
      "required": false
    },
    "color_temp": {
      "description": "Color temperature in mireds",
      "required": false
    },
    "rgb_color": {
      "description": "RGB color [r, g, b]",
      "example": [255, 100, 100],
      "required": false
    }
  },
  "target": {
    "entity": ["light"],
    "device": true,
    "area": true
  }
}
```

### 2. API 實作方式

Home Assistant 提供兩種方式建立 Automation/Script：

#### 方式 A：透過 Config API（推薦）

```python
from homeassistant.components.automation.config import async_create_automation
from homeassistant.components.script.config import async_create_script

# 建立 Automation
await async_create_automation(hass, config)

# 建立 Script
await async_create_script(hass, script_id, config)
```

#### 方式 B：透過 WebSocket API

```python
# 建立 Automation
await hass.services.async_call(
    "config",
    "automation/create",
    {"config": automation_config}
)
```

### 3. 錯誤處理

```python
try:
    result = await create_automation(config)
    return {
        "success": True,
        "automation_id": result["id"],
        "message": f"已建立自動化「{config['alias']}」"
    }
except vol.Invalid as e:
    return {
        "success": False,
        "error": "invalid_config",
        "message": f"設定格式錯誤：{str(e)}"
    }
except HomeAssistantError as e:
    return {
        "success": False,
        "error": "ha_error",
        "message": f"Home Assistant 錯誤：{str(e)}"
    }
```

### 4. 修改檔案清單

| 檔案 | 變更 |
|------|------|
| `mcp/tools/registry.py` | 新增 3 個工具定義和處理器 |
| `mcp/tools/helpers.py` | 新增 `create_automation`, `create_script`, `get_service_schema` 函數 |

### 5. 測試案例

1. **建立日落自動化**
   - 輸入：「當太陽下山時開啟客廳燈」
   - 預期：建立含 sun trigger 和 light.turn_on action 的自動化

2. **建立定時腳本**
   - 輸入：「建立一個早安腳本，開燈並播放音樂」
   - 預期：建立含多個 action 的腳本

3. **錯誤處理**
   - 輸入：「建立自動化但不給觸發器」
   - 預期：回傳錯誤訊息說明缺少 trigger

## 實作順序

1. 新增 `get_service_schema` 工具（讓 AI 了解服務參數）
2. 新增 `create_automation` 工具
3. 新增 `create_script` 工具
4. 測試各種建立情境
5. 部署到容器驗證
