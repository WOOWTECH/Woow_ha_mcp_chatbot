# PRD: HA MCP Client - 部署、設定與測試

**版本**: 1.0
**日期**: 2026-03-07
**作者**: AI Coder
**狀態**: Draft

---

## 1. 概述 (Overview)

將已完成 Code Review 修復的 `ha_mcp_client` 自訂整合套件，部署到帶有 PostgreSQL 的 Home Assistant 容器 (`homeassistant`，port `18123`)，同時安裝 `hass-virtual` 整合套件建立模擬實體與分區，以提供完整的 MCP 功能測試環境。

### 1.1 目標

| 目標 | 衡量標準 |
|------|----------|
| 成功部署 ha_mcp_client 到 HA | 整合套件在 HA UI 中可見且可設定 |
| 安裝並設定 hass-virtual | 虛擬實體在 HA 中正常運作 |
| 建立測試用分區和實體 | 至少 4 個分區、15+ 個虛擬實體 |
| MCP SSE 端點可存取 | `/api/mcp/sse` 回應正確 SSE 串流 |
| AI 對話可使用 MCP 工具 | 透過對話介面成功控制虛擬實體 |

---

## 2. 環境架構 (Environment Architecture)

### 2.1 現有基礎設施

```
┌─────────────────────────────────────────────┐
│         Podman Network: homeassistant_default│
│                                             │
│  ┌──────────────────┐  ┌──────────────────┐ │
│  │  homeassistant   │  │ homeassistant-   │ │
│  │  (HA Stable)     │──│ postgres         │ │
│  │  Port: 18123     │  │ (pgvector:pg16)  │ │
│  │                  │  │                  │ │
│  │  Config Volume:  │  │  Data Volume:    │ │
│  │  .../config      │  │  .../postgres_data│ │
│  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────┘
```

### 2.2 目標架構

```
homeassistant container (port 18123)
├── custom_components/
│   ├── ha_mcp_client/          ← 我們的 MCP 整合
│   │   ├── __init__.py
│   │   ├── conversation.py
│   │   ├── config_flow.py
│   │   ├── mcp/server.py      ← SSE endpoint at /api/mcp/sse
│   │   ├── mcp/tools/         ← HA tool registry
│   │   ├── ai_services/       ← Anthropic/OpenAI/Ollama
│   │   └── conversation_recorder.py
│   │
│   └── virtual/                ← hass-virtual 虛擬實體
│
├── configuration.yaml          ← recorder: db_url postgres
├── virtual.yaml                ← 虛擬裝置定義
└── automations.yaml
```

---

## 3. 虛擬測試環境設計 (Virtual Test Environment)

### 3.1 分區規劃 (Areas)

| 分區名稱 | 英文 ID | 用途 |
|----------|---------|------|
| 客廳 | living_room | 主要控制場景：燈光、感測器、媒體 |
| 臥室 | bedroom | 睡眠場景：燈光、溫度、窗簾 |
| 廚房 | kitchen | 安全場景：煙霧偵測、開關 |
| 車庫 | garage | 進出場景：門、裝置追蹤 |

### 3.2 虛擬實體規劃 (Virtual Entities)

#### 客廳 (Living Room) — 6 個實體

| 實體類型 | 名稱 | Device Class | 初始值 | 功能 |
|---------|------|-------------|--------|------|
| light | Living Room Light | — | on | 亮度、色溫 |
| sensor | Living Room Temperature | temperature | 24 | 溫度感測 |
| sensor | Living Room Humidity | humidity | 55 | 濕度感測 |
| binary_sensor | Living Room Motion | motion | off | 動態偵測 |
| switch | Living Room Fan | — | off | 電扇開關 |
| binary_sensor | Living Room Window | window | off | 窗戶開關 |

#### 臥室 (Bedroom) — 4 個實體

| 實體類型 | 名稱 | Device Class | 初始值 | 功能 |
|---------|------|-------------|--------|------|
| light | Bedroom Light | — | off | 亮度控制 |
| sensor | Bedroom Temperature | temperature | 22 | 溫度感測 |
| cover | Bedroom Curtain | — | closed | 窗簾控制 |
| binary_sensor | Bedroom Door | door | off | 門偵測 |

#### 廚房 (Kitchen) — 4 個實體

| 實體類型 | 名稱 | Device Class | 初始值 | 功能 |
|---------|------|-------------|--------|------|
| light | Kitchen Light | — | off | 基本開關 |
| switch | Kitchen Coffee Maker | — | off | 咖啡機 |
| binary_sensor | Kitchen Smoke | smoke | off | 煙霧偵測 |
| sensor | Kitchen Temperature | temperature | 26 | 溫度感測 |

#### 車庫 (Garage) — 3 個實體

| 實體類型 | 名稱 | Device Class | 初始值 | 功能 |
|---------|------|-------------|--------|------|
| cover | Garage Door | garage | closed | 車庫門控制 |
| binary_sensor | Garage Motion | motion | off | 動態偵測 |
| lock | Garage Lock | — | locked | 門鎖控制 |

**共計**: 17 個虛擬實體，涵蓋 6 種平台類型

---

## 4. 部署步驟 (Deployment Steps)

### Phase 1: 準備 HA 容器環境

1. **啟動 PostgreSQL 容器** (`homeassistant-postgres`)
2. **啟動 Home Assistant 容器** (`homeassistant`)
3. **等待 HA 完成初始化** (首次啟動需建立 onboarding)
4. **設定 HA 的 `configuration.yaml`**:
   - 設定 `recorder` 使用 PostgreSQL
   - 設定 `default_config`

### Phase 2: 安裝 hass-virtual

1. **下載 hass-virtual** 到 `custom_components/virtual/`
2. **建立 `virtual.yaml`** 虛擬裝置定義檔
3. **在 `configuration.yaml` 中啟用** `virtual: yaml_config: true`
4. **重啟 HA** 載入新整合
5. **透過 UI 新增 Virtual 整合** (Settings → Integrations → Add)
6. **建立分區** (Settings → Areas → Add)
7. **將虛擬裝置分配到各分區**

### Phase 3: 部署 ha_mcp_client

1. **複製 ha_mcp_client** 到 `custom_components/ha_mcp_client/`
2. **安裝 Python 依賴** (anthropic, openai, httpx)
3. **重啟 HA** 載入 MCP 整合
4. **透過 UI 設定 MCP 整合**:
   - 啟用 MCP Server
   - 啟用 Conversation Entity
   - 設定 AI 服務 (Anthropic/OpenAI)
   - 設定對話歷史

### Phase 4: 驗證與測試

1. **驗證 MCP SSE 端點**: `GET /api/mcp/sse`
2. **驗證 MCP 工具列表**: 透過 SSE 送 `tools/list`
3. **測試工具功能**:
   - `get_entity_states` — 取得所有虛擬實體狀態
   - `call_ha_service` — 控制燈光/開關
   - `get_areas` — 取得分區列表
   - `get_history` — 取得實體歷史
4. **測試對話功能**:
   - "客廳的溫度是多少？"
   - "打開臥室的燈"
   - "關閉車庫門"
   - "列出所有分區"

---

## 5. 設定檔規格 (Configuration Specs)

### 5.1 configuration.yaml

```yaml
default_config:

recorder:
  db_url: "postgresql://homeassistant:ha_secure_password_change_me@homeassistant-postgres/homeassistant"
  purge_keep_days: 30
  commit_interval: 5

logger:
  default: info
  logs:
    custom_components.ha_mcp_client: debug
    custom_components.virtual: info

virtual:
  yaml_config: true
```

### 5.2 virtual.yaml

```yaml
version: 1
devices:
  Living Room Light:
    - platform: light
      initial_value: "on"
      support_brightness: true
      initial_brightness: 80
      support_color_temp: true
      initial_color_temp: 300

  Living Room Temperature:
    - platform: sensor
      initial_value: "24"
      class: temperature
      unit_of_measurement: "°C"

  Living Room Humidity:
    - platform: sensor
      initial_value: "55"
      class: humidity
      unit_of_measurement: "%"

  Living Room Motion:
    - platform: binary_sensor
      initial_value: "off"
      class: motion

  Living Room Fan:
    - platform: switch
      initial_value: "off"

  Living Room Window:
    - platform: binary_sensor
      initial_value: "off"
      class: window

  Bedroom Light:
    - platform: light
      initial_value: "off"
      support_brightness: true
      initial_brightness: 50

  Bedroom Temperature:
    - platform: sensor
      initial_value: "22"
      class: temperature
      unit_of_measurement: "°C"

  Bedroom Curtain:
    - platform: cover
      initial_value: "closed"
      open_close_duration: 10
      open_close_tick: 1

  Bedroom Door:
    - platform: binary_sensor
      initial_value: "off"
      class: door

  Kitchen Light:
    - platform: light
      initial_value: "off"

  Kitchen Coffee Maker:
    - platform: switch
      initial_value: "off"

  Kitchen Smoke:
    - platform: binary_sensor
      initial_value: "off"
      class: smoke

  Kitchen Temperature:
    - platform: sensor
      initial_value: "26"
      class: temperature
      unit_of_measurement: "°C"

  Garage Door:
    - platform: cover
      initial_value: "closed"
      open_close_duration: 15
      open_close_tick: 1

  Garage Motion:
    - platform: binary_sensor
      initial_value: "off"
      class: motion

  Garage Lock:
    - platform: lock
      initial_value: "locked"
      locking_time: 3
```

---

## 6. 測試計畫 (Test Plan)

### 6.1 基礎驗證

| # | 測試項目 | 預期結果 | 方法 |
|---|---------|---------|------|
| T1 | HA 啟動成功 | HTTP 200 at :18123 | `curl localhost:18123` |
| T2 | PostgreSQL 連線 | recorder 正常運作 | HA 日誌無 DB 錯誤 |
| T3 | hass-virtual 載入 | 整合出現在 Integrations | HA UI 確認 |
| T4 | 虛擬實體可見 | 17 個實體在 States 中 | Developer Tools → States |
| T5 | ha_mcp_client 載入 | 整合出現在 Integrations | HA UI 確認 |

### 6.2 MCP 功能測試

| # | 測試項目 | MCP 工具 | 預期結果 |
|---|---------|---------|---------|
| M1 | 取得實體狀態 | `get_entity_states` | 回傳 17 個實體 |
| M2 | 控制燈光 | `call_ha_service` | 燈光狀態改變 |
| M3 | 取得分區 | `get_areas` | 回傳 4 個分區 |
| M4 | 取得歷史 | `get_history` | 回傳實體歷史紀錄 |
| M5 | 建立自動化 | `create_automation` | 自動化出現在 HA |
| M6 | 服務黑名單 | `call_ha_service` | 拒絕 homeassistant.restart |
| M7 | SSE 連線 | `/api/mcp/sse` | 成功建立 SSE 串流 |

### 6.3 對話整合測試

| # | 使用者輸入 | 預期 AI 行為 | 使用的工具 |
|---|----------|------------|-----------|
| C1 | "列出所有分區" | 回傳 4 個分區名稱 | `get_areas` |
| C2 | "客廳的溫度是多少" | 回傳 24°C | `get_entity_states` |
| C3 | "打開臥室的燈" | 執行 light.turn_on | `call_ha_service` |
| C4 | "車庫門是開的還是關的" | 回傳 closed | `get_entity_states` |
| C5 | "幫我建立一個自動化：當客廳偵測到動作時打開客廳的燈" | 建立觸發自動化 | `create_automation` |

---

## 7. 風險與緩解 (Risks & Mitigations)

| 風險 | 影響 | 機率 | 緩解措施 |
|------|------|------|---------|
| HA 首次啟動需 onboarding | 阻塞自動化部署 | 高 | 透過瀏覽器完成 onboarding 流程 |
| pip 依賴安裝衝突 | MCP 套件無法載入 | 中 | 在容器內用 pip install 預裝 |
| PostgreSQL 連線失敗 | recorder 無法使用 | 低 | 確認網路和 .env 設定 |
| hass-virtual 版本相容性 | 實體建立失敗 | 低 | 使用 HACS 或指定穩定版本 |
| AI API Key 未設定 | 對話功能無法使用 | 中 | 可先測試 MCP SSE 端點，對話測試需要 API Key |

---

## 8. 成功標準 (Success Criteria)

- [ ] Home Assistant 容器正常運行在 port 18123
- [ ] PostgreSQL 作為 recorder 後端正常運作
- [ ] hass-virtual 整合已安裝，17 個虛擬實體可見
- [ ] 4 個分區已建立且實體已分配
- [ ] ha_mcp_client 整合已安裝且可透過 UI 設定
- [ ] MCP SSE 端點 `/api/mcp/sse` 可連線
- [ ] 至少完成 T1-T5 基礎驗證
- [ ] 至少完成 M1-M4 MCP 功能測試

---

## 9. 範圍外 (Out of Scope)

- 生產環境部署
- SSL/TLS 設定
- 多用戶測試
- 效能壓力測試
- CI/CD 管線設定
- HACS 發佈流程
