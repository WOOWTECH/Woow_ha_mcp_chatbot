# PRD: Config Flow 精簡 + 多組 LLM 支援 + 前端即時切換

## 目標

1. 精簡 config flow，移除與 nanobot 重複的設定
2. 支援多組 LLM API（Anthropic/OpenAI/Ollama/OpenAI-compatible）
3. 前端聊天面板可在對話中即時切換 provider 和 model

## 設計決策

| # | 問題 | 決策 |
|---|------|------|
| 1 | Config flow 保留範圍 | B：保留結構性設定（API key 管理、history），其餘移前端 |
| 2 | 多組 API 資料結構 | B：單一 Config Entry + `llm_providers` 陣列 |
| 3 | API token entity 類型 | C：`sensor` 顯示狀態 + `select` 切換 active provider |
| 4 | 前端切換 UI | C：聊天輸入框旁加 model 選擇器，對話中即時切換 |
| 5 | Config flow 子選單 | A：線性子選單，「管理 LLM 提供者」集中 CRUD |

---

## 一、資料結構

### Config Entry Data

```python
{
    # 結構性設定（保留在 config flow）
    "enable_mcp_server": True,
    "enable_conversation": True,
    "mcp_server_port": 8087,
    "enable_conversation_history": True,
    "history_retention_days": 30,

    # 多組 LLM provider
    "llm_providers": [
        {
            "id": "anthropic_1",
            "name": "Anthropic",
            "provider": "anthropic",       # anthropic | openai | ollama | openai_compatible
            "api_key": "sk-ant-xxx",
            "model": "claude-sonnet-4-20250514",
            "base_url": None,
        },
        {
            "id": "openai_1",
            "name": "OpenAI",
            "provider": "openai",
            "api_key": "sk-xxx",
            "model": "gpt-4o",
            "base_url": None,
        },
        {
            "id": "ollama_1",
            "name": "Ollama Local",
            "provider": "ollama",
            "api_key": None,
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
        },
    ],

    # 目前使用的 provider ID
    "active_llm_provider": "anthropic_1",

    # Advanced Settings（初始預設值）
    "system_prompt": "...",
    "max_tool_calls": 10,
}
```

每個 provider 的 `id` 格式為 `{provider}_{序號}`，在前端和 HA entity 中作為唯一識別符。

---

## 二、HA Entity 設計

### 2.1 Per-Provider Sensor

每新增一組 LLM provider 自動建立：

```
sensor.ha_mcp_llm_anthropic_1
  state: "connected"              # connected | error | unconfigured
  attributes:
    provider: "anthropic"
    name: "Anthropic"
    model: "claude-sonnet-4-20250514"
    api_key_masked: "sk-ant-***a7x"   # 只顯示最後 3 碼
    base_url: null
    friendly_name: "LLM: Anthropic"
    icon: "mdi:robot"

sensor.ha_mcp_llm_openai_1
  state: "connected"
  attributes:
    provider: "openai"
    name: "OpenAI"
    model: "gpt-4o"
    api_key_masked: "sk-***f2k"
    ...

sensor.ha_mcp_llm_ollama_1
  state: "connected"
  attributes:
    provider: "ollama"
    name: "Ollama Local"
    model: "llama3.2"
    api_key_masked: null
    base_url: "http://localhost:11434"
    ...
```

### 2.2 Active Provider Select

全域切換 entity：

```
select.ha_mcp_active_llm
  state: "anthropic_1"
  attributes:
    options: ["anthropic_1", "openai_1", "ollama_1"]
    friendly_name: "目前使用的 LLM"
    icon: "mdi:swap-horizontal"
```

切換時自動：
1. 更新 `config_entry.data["active_llm_provider"]`
2. 更新 runtime_settings（`ai_service`、`model`、`api_key`）
3. 前端聊天面板 model selector 自動同步

### 2.3 保留現有 Entity

以下 entity 不變，繼續運作：

- `number.ha_mcp_client_nanobot_temperature` — 溫度（0.0-2.0）
- `number.ha_mcp_client_nanobot_max_tokens` — 最大 token（100-128000）
- `number.ha_mcp_client_nanobot_memory_window` — 記憶窗口（10-500）
- `select.ha_mcp_client_nanobot_reasoning_effort` — 推理強度（low/medium/high）
- `switch.ha_mcp_client_skill_*` — 技能開關
- `switch.ha_mcp_client_cron_*` — 排程開關

### 2.4 移除的 Entity

以下 entity 被新的多組 LLM 體系取代：

- `select.ha_mcp_client_nanobot_ai_provider` → 被 `select.ha_mcp_active_llm` 取代
- `select.ha_mcp_client_nanobot_ai_model` → 被前端 model selector + per-provider model 取代

---

## 三、Config Flow Options 子選單

### 3.1 主選單

```
┌─ HA MCP Client 設定 ──────────────────────────┐
│                                                │
│  🤖 管理 LLM 提供者                            │
│     Configure AI provider, API key, and model  │
│                                                │
│  💬 Conversation Settings                      │
│     History and retention options               │
│                                                │
│  ⚙️ Advanced Settings                          │
│     System prompt and tool limits               │
│                                                │
└────────────────────────────────────────────────┘
```

### 3.2 管理 LLM 提供者

```
┌─ LLM 提供者 ──────────────────────────────────┐
│                                                │
│  設定類別                                      │
│                                                │
│  ● ✅ Anthropic (claude-sonnet-4) [使用中]     │
│  ○ OpenAI (gpt-4o)                            │
│  ○ Ollama Local (llama3.2)                    │
│  ○ ➕ 新增 LLM 提供者                         │
│                                                │
│                                    [傳送]      │
└────────────────────────────────────────────────┘
```

選擇已有的 provider → 進入編輯/刪除頁面
選擇「新增 LLM 提供者」→ 進入新增表單

### 3.3 新增/編輯 LLM 表單

```
┌─ 新增 LLM 提供者 ────────────────────────────┐
│                                                │
│  名稱：     [Anthropic              ]          │
│  類型：     [anthropic ▼]                      │
│  API Key：  [••••••••••••           ]          │
│  模型：     [claude-sonnet-4-20250514 ▼]       │
│  Base URL： [                       ]          │
│             （僅 Ollama/OpenAI-compatible）     │
│                                                │
│                                    [傳送]      │
└────────────────────────────────────────────────┘
```

編輯模式額外顯示：
- 「刪除此 LLM」按鈕（checkbox）
- 「設為預設」按鈕（checkbox）

### 3.4 Options Flow Step 設計

```python
class HAMCPClientOptionsFlow:
    async_step_init()                    # 主選單（menu step）
    async_step_manage_llm()              # LLM 清單（select step）
    async_step_add_llm()                 # 新增表單（form step）
    async_step_edit_llm()                # 編輯表單（form step）
    async_step_conversation_settings()   # 保留原有
    async_step_advanced()                # 精簡：system_prompt + max_tool_calls
```

### 3.5 Conversation Settings（保留）

```
enable_conversation_history: boolean  (預設 True)
history_retention_days: number 1-365  (預設 30)
```

### 3.6 Advanced Settings（精簡）

```
system_prompt: multiline text         (初始系統提示詞)
max_tool_calls: number 1-50           (預設 10)
```

移除的項目（已由 HA entity / REST API / 前端管理）：
- `temperature` → `number.nanobot_temperature`
- `max_tokens` → `number.nanobot_max_tokens`
- `memory_window` → `number.nanobot_memory_window`

---

## 四、前端聊天面板 Model Selector

### 4.1 UI 位置

聊天輸入框上方，兩個下拉選單：

```
┌─────────────────────────────────────────────┐
│ (對話訊息區)                                 │
│                                              │
└─────────────────────────────────────────────┘

  ┌──────────────────┐  ┌────────────────────┐
  │ 🤖 Anthropic  ▼  │  │ claude-sonnet-4 ▼  │
  └──────────────────┘  └────────────────────┘
  ┌────────────────────────────────────┐ [送出]
  │ 輸入訊息...                        │
  └────────────────────────────────────┘
```

- Provider 下拉：列出所有已設定的 LLM，顯示連線狀態（綠/紅點）
- Model 下拉：選擇 provider 後自動更新為該 provider 的可用 model list
- 切換即時生效，下一條訊息用新 provider 處理

### 4.2 新增 REST API 端點

```
GET  /api/ha_mcp_client/llm_providers
  → 列出所有已設定的 provider（不含完整 API key）
  回應：
  {
    "providers": [
      {
        "id": "anthropic_1",
        "name": "Anthropic",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key_masked": "sk-ant-***a7x",
        "base_url": null,
        "status": "connected",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", ...]
      },
      ...
    ],
    "active": "anthropic_1"
  }

PATCH /api/ha_mcp_client/active_llm
  → 切換 active provider + 可選切換 model
  請求：
  {
    "provider_id": "openai_1",
    "model": "gpt-4o"          // 可選，不帶則使用該 provider 預設 model
  }
  回應：
  {
    "success": true,
    "active": "openai_1",
    "model": "gpt-4o"
  }
```

### 4.3 前端 JavaScript

```javascript
// 載入 provider 清單
async loadLLMProviders() {
    const resp = await fetch(`${this.apiBase}/llm_providers`, { headers: this.headers });
    const data = await resp.json();
    this.providers = data.providers;
    this.activeProvider = data.active;
    this.renderProviderSelector();
}

// 切換 provider
async switchProvider(providerId, model) {
    await fetch(`${this.apiBase}/active_llm`, {
        method: 'PATCH',
        headers: this.headers,
        body: JSON.stringify({ provider_id: providerId, model }),
    });
    this.activeProvider = providerId;
    this.updateModelDropdown();
}
```

---

## 五、遷移策略（向後相容）

已安裝的使用者升級時，`config_flow.py` 的 `async_migrate_entry` 處理：

```python
async def async_migrate_entry(hass, config_entry):
    if config_entry.version < 2:
        # 舊版：單一 ai_service + api_key + model
        old_data = dict(config_entry.data)
        provider = old_data.pop("ai_service", "openai")
        api_key = old_data.pop("api_key", "")
        model = old_data.pop("model", "")
        base_url = old_data.pop("base_url", None)
        ollama_host = old_data.pop("ollama_host", None)

        # 移除舊的 temperature（由 HA entity 管理）
        old_data.pop("temperature", None)

        # 轉換為新格式
        provider_id = f"{provider}_1"
        old_data["llm_providers"] = [{
            "id": provider_id,
            "name": provider.capitalize(),
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "base_url": base_url or ollama_host,
        }]
        old_data["active_llm_provider"] = provider_id

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=old_data)

    return True
```

---

## 六、移除/精簡項目

### Config Flow 移除

| 原 Config Flow 設定 | 處理方式 |
|---|---|
| `ai_service` (單選 provider) | 替換為「管理 LLM 提供者」子選單 |
| `api_key` (單一 key) | 併入 `llm_providers` per-provider |
| `model` (單一 model) | 併入 `llm_providers` + 前端切換 |
| `base_url` / `ollama_host` | 併入 `llm_providers` per-provider |
| `temperature` | 從 config flow 移除（HA entity 管理） |

### Entity 移除

| Entity | 取代方式 |
|---|---|
| `select.ha_mcp_client_nanobot_ai_provider` | `select.ha_mcp_active_llm` |
| `select.ha_mcp_client_nanobot_ai_model` | 前端 model selector + per-provider |

### Config Flow 保留

| 設定 | 分類 |
|---|---|
| `enable_mcp_server` | 首次安裝 |
| `enable_conversation` | 首次安裝 |
| `mcp_server_port` | 首次安裝 |
| `enable_conversation_history` | Conversation Settings |
| `history_retention_days` | Conversation Settings |
| `system_prompt` | Advanced Settings |
| `max_tool_calls` | Advanced Settings |
| `llm_providers[]` | 管理 LLM 提供者（新增） |
| `active_llm_provider` | 管理 LLM 提供者（新增） |

---

## 七、檔案變更清單

| 檔案 | 動作 | 描述 |
|------|------|------|
| `config_flow.py` | 重構 | 移除舊 AI service step，新增多組 LLM CRUD 子選單，加 `async_migrate_entry` |
| `const.py` | 修改 | 新增 `CONF_LLM_PROVIDERS`、`CONF_ACTIVE_LLM_PROVIDER` 常量 |
| `__init__.py` | 修改 | 更新 runtime_settings 初始化邏輯，讀取 active provider |
| `sensor.py` | 修改 | 新增 `LLMProviderSensor` 動態 entity |
| `select.py` | 修改 | 新增 `ActiveLLMSelect`，移除舊 `NanobotProviderSelect` + `NanobotModelSelect` |
| `views.py` | 修改 | 新增 `GET /llm_providers` + `PATCH /active_llm` 端點 |
| `frontend/app.js` | 修改 | 新增 provider/model selector UI |
| `frontend/index.html` | 修改 | 新增 selector HTML 結構 |
| `strings.json` | 修改 | 更新 config flow 翻譯字串 |
| `translations/zh-Hant.json` | 修改 | 更新中文翻譯 |

## 八、測試計畫

1. **Config flow 新裝**：首次安裝 → 新增第一組 LLM → 完成設定
2. **Config flow 遷移**：舊版升級 → 自動轉換為 `llm_providers[0]`
3. **Options flow CRUD**：新增/編輯/刪除 LLM provider
4. **HA Entity**：sensor 狀態正確、select 切換生效
5. **前端切換**：provider/model 下拉選單、即時切換
6. **REST API**：`GET /llm_providers`、`PATCH /active_llm`
7. **對話測試**：切換 provider 後 AI 回應來自新 provider
8. **回歸測試**：Section A-R 全通過
