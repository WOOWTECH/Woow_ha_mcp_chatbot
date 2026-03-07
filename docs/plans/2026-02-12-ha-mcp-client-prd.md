# HA MCP Client - 產品需求文件 (PRD)

## 1. 概述

### 1.1 專案名稱
**HA MCP Client** - Home Assistant MCP 整合套件

### 1.2 專案目標
建立一個 Home Assistant 自訂整合，整合 MCP (Model Context Protocol) 的 Client 和 Server 功能，提供：
1. **內建 MCP Server** - 整合 ha-mcp 的所有功能（97+ 工具）
2. **MCP Client** - 連接外部 AI 服務（Claude/OpenAI/Ollama 等）
3. **Conversation Entity** - 在 HA 內部提供智能對話機器人
4. **對話紀錄** - 使用 HA Recorder 記錄個別用戶的對話歷史

### 1.3 核心價值
- **一站式整合**：用戶無需額外安裝 ha-mcp，所有功能內建
- **智能對話**：支援多種 AI 服務，可透過自然語言控制智能家居
- **完整功能**：支援設備控制、自動化建議、歷史查詢等 97+ 工具
- **用戶隔離**：每個 HA 用戶有獨立的對話歷史

---

## 2. 系統架構

### 2.1 整體架構圖

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Home Assistant                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    HA MCP Client Integration                       │  │
│  │                                                                    │  │
│  │  ┌──────────────────┐         ┌────────────────────────────────┐ │  │
│  │  │  Conversation    │         │      MCP SSE Server            │ │  │
│  │  │    Entity        │         │   (對外提供 97+ tools)          │ │  │
│  │  │                  │         │   Port: 8087 (可配置)           │ │  │
│  │  └────────┬─────────┘         └────────────────────────────────┘ │  │
│  │           │                                                       │  │
│  │           ▼                                                       │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │                    MCP Core Engine                          │  │  │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │  │  │
│  │  │  │ MCP Client  │  │ AI Service  │  │    Tool Registry    │ │  │  │
│  │  │  │ (SSE連接)    │  │  Manager    │  │   (ha-mcp tools)    │ │  │  │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────┘ │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                              │                                    │  │
│  │           ┌──────────────────┴──────────────────┐                │  │
│  │           ▼                                     ▼                │  │
│  │  ┌─────────────────┐              ┌─────────────────────────┐   │  │
│  │  │   HA Recorder   │              │    AI Services          │   │  │
│  │  │  (對話紀錄)      │              │  • Anthropic Claude     │   │  │
│  │  │  • 用戶隔離     │              │  • OpenAI GPT           │   │  │
│  │  │  • 歷史查詢     │              │  • Ollama (本地)        │   │  │
│  │  └─────────────────┘              │  • 其他相容服務          │   │  │
│  │                                   └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Home Assistant Core                            │   │
│  │  • Entity Registry  • Service Registry  • User Management        │   │
│  │  • Automation       • Scripts           • Areas/Devices          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌──────────────────────┐
│  外部 AI 客戶端   │          │    HA 前端/App       │
│  (Claude Desktop │          │   (Conversation UI)  │
│   Cursor, etc.)  │          └──────────────────────┘
└──────────────────┘
```

### 2.2 模組說明

| 模組 | 功能 | 說明 |
|------|------|------|
| **Conversation Entity** | 對話介面 | 實作 HA ConversationEntity，支援自然語言對話 |
| **MCP SSE Server** | 對外服務 | 提供 SSE 端點讓外部 AI 客戶端連接 |
| **MCP Client** | AI 連接 | 透過 SSE/HTTP 連接外部 MCP Server（可選） |
| **AI Service Manager** | AI 管理 | 管理多種 AI 服務的連接和切換 |
| **Tool Registry** | 工具註冊 | 整合 ha-mcp 的 97+ 工具 |
| **Conversation Recorder** | 對話紀錄 | 使用 HA Recorder 儲存對話歷史 |

---

## 3. 功能規格

### 3.1 Conversation Entity

#### 3.1.1 基本對話功能
- 接收用戶自然語言輸入
- 呼叫配置的 AI 服務處理
- 根據 AI 回應執行 MCP Tools
- 回傳處理結果給用戶

#### 3.1.2 支援的功能（透過 MCP Tools）
參考 ha-mcp 的 97+ 工具，包括：

**搜尋與發現**
- `smart_search` - 模糊實體搜尋
- `deep_config_search` - 深層配置搜尋
- `system_overview` - 系統概覽

**設備控制**
- `call_service` - 服務呼叫
- `batch_control` - 批量設備控制
- `device_control` - 單一設備控制

**自動化管理**
- `automation_list` / `automation_create` / `automation_update`
- `script_list` / `script_create`
- `scene_list` / `scene_activate`

**監控與分析**
- `history_get` - 歷史數據
- `statistics_get` - 統計分析
- `camera_snapshot` - 攝像頭快照

**系統操作**
- `backup_create` / `backup_list`
- `update_check` / `update_install`
- `addon_list` / `addon_install`

#### 3.1.3 Conversation Entity 屬性
```python
class HAMCPConversationEntity(ConversationEntity):
    """HA MCP Conversation Entity."""

    @property
    def supported_languages(self) -> list[str] | str:
        return "*"  # 支援所有語言

    @property
    def supported_features(self) -> ConversationEntityFeature:
        return ConversationEntityFeature.CONTROL  # 支援設備控制
```

### 3.2 MCP SSE Server

#### 3.2.1 端點設計
```
GET  /api/ha_mcp_client/sse          - SSE 連接端點
POST /api/ha_mcp_client/sse/messages - 訊息發送端點
```

#### 3.2.2 認證方式
- 使用 HA Long-Lived Access Token
- 透過 HTTP Header: `Authorization: Bearer <token>`

#### 3.2.3 提供的 Tools
直接整合 ha-mcp 的所有工具，包括：
- 50+ 工具模組
- 完整的 HA API 存取能力
- 檔案系統操作（受限）

### 3.3 AI 服務整合

#### 3.3.1 支援的 AI 服務

| 服務 | 配置項目 | 說明 |
|------|---------|------|
| **Anthropic Claude** | API Key, Model | claude-3-opus, claude-3-sonnet, etc. |
| **OpenAI** | API Key, Model, Base URL | gpt-4, gpt-4-turbo, etc. |
| **Ollama** | Host, Model | 本地 LLM，支援各種模型 |
| **OpenAI 相容** | API Key, Base URL, Model | 支援任何 OpenAI API 相容服務 |

#### 3.3.2 AI 服務介面
```python
class AIServiceProvider(ABC):
    """AI 服務提供者介面."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool],
    ) -> AIResponse:
        """處理對話並返回回應."""
        pass

    @abstractmethod
    async def validate_config(self) -> bool:
        """驗證配置是否有效."""
        pass
```

### 3.4 對話紀錄

#### 3.4.1 資料模型
使用 HA Recorder 儲存以下資料：

```python
class ConversationRecord:
    """對話紀錄資料模型."""

    id: str                    # UUID
    user_id: str               # HA User ID
    conversation_id: str       # 對話 Session ID
    timestamp: datetime        # 時間戳記
    role: str                  # "user" | "assistant" | "tool"
    content: str               # 訊息內容
    tool_calls: list[dict]     # Tool 呼叫紀錄（可選）
    tool_results: list[dict]   # Tool 執行結果（可選）
    metadata: dict             # 額外元數據
```

#### 3.4.2 儲存機制
- 利用 HA Recorder 的 `StatisticsShortTerm` 或自訂 table
- 支援自動清理舊紀錄（可配置保留天數）
- 支援匯出對話歷史

#### 3.4.3 查詢功能
- 依用戶查詢對話歷史
- 依時間範圍查詢
- 依 conversation_id 查詢完整對話

---

## 4. Config Flow 設計

### 4.1 設定步驟

```
步驟 1: 選擇功能
├── [ ] 啟用 MCP Server (對外提供 tools)
├── [ ] 啟用 Conversation Entity (內建對話機器人)
└── [ ] 連接外部 MCP Server

步驟 2: MCP Server 設定 (如果啟用)
├── SSE 端口: [8087]
└── 認證方式: [HA Token]

步驟 3: AI 服務設定 (如果啟用 Conversation)
├── AI 服務: [Anthropic Claude ▼]
├── API Key: [••••••••••••]
├── Model: [claude-3-sonnet ▼]
└── [測試連接]

步驟 4: 對話紀錄設定
├── 啟用對話紀錄: [是]
└── 紀錄保留天數: [30]

步驟 5: 進階設定 (可選)
├── 系統提示詞: [自訂 AI 行為...]
└── 最大工具呼叫次數: [10]
```

### 4.2 選項流程（Options Flow）
支援在整合設定後修改：
- 切換 AI 服務
- 更新 API Key
- 調整進階設定

---

## 5. 目錄結構

```
custom_components/ha_mcp_client/
├── __init__.py              # 主要進入點
├── manifest.json            # HA 整合清單
├── config_flow.py           # Config Flow 實作
├── const.py                 # 常數定義
├── strings.json             # 國際化字串
├── services.yaml            # 服務定義
│
├── conversation.py          # Conversation Entity 實作
├── conversation_recorder.py # 對話紀錄功能
│
├── mcp/                     # MCP 核心
│   ├── __init__.py
│   ├── server.py            # MCP SSE Server
│   ├── client.py            # MCP Client
│   └── tools/               # 整合 ha-mcp tools
│       ├── __init__.py
│       ├── registry.py      # 工具註冊表
│       ├── smart_search.py
│       ├── device_control.py
│       ├── automation.py
│       ├── ... (其他工具模組)
│       └── helpers.py
│
├── ai_services/             # AI 服務整合
│   ├── __init__.py
│   ├── base.py              # 基礎介面
│   ├── anthropic.py         # Anthropic Claude
│   ├── openai.py            # OpenAI
│   ├── ollama.py            # Ollama
│   └── openai_compatible.py # OpenAI 相容服務
│
└── translations/            # 多語言支援
    ├── en.json
    └── zh-Hant.json
```

---

## 6. 依賴套件

### 6.1 Python 依賴
```toml
[project]
requires-python = ">=3.12"

dependencies = [
    "fastmcp>=2.11.0",
    "httpx>=0.27.0",
    "pydantic>=2.5.0",
    "anthropic>=0.40.0",      # Anthropic Claude
    "openai>=1.50.0",         # OpenAI
    "aiohttp>=3.9.0",         # Ollama HTTP client
]
```

### 6.2 Home Assistant 要求
- Home Assistant Core 2024.1.0+
- Python 3.12+

---

## 7. 安全考量

### 7.1 API Key 保護
- API Key 透過 Config Flow 輸入，存放在 HA 加密儲存
- 不在日誌中記錄 API Key
- 支援 API Key 輪換

### 7.2 MCP Server 安全
- 僅接受有效 HA Token 的連接
- 支援 IP 白名單（可選）
- 檔案系統操作受限於白名單目錄

### 7.3 對話紀錄隱私
- 對話紀錄僅限用戶本人和管理員存取
- 支援用戶刪除自己的對話紀錄
- 敏感資訊自動遮罩

---

## 8. 實作計畫

### Phase 1: 基礎架構 (Week 1-2)
- [ ] 建立專案結構
- [ ] 實作 Config Flow
- [ ] 整合 ha-mcp tools 核心

### Phase 2: MCP Server (Week 2-3)
- [ ] 實作 SSE Server
- [ ] 整合完整 tools
- [ ] 認證機制

### Phase 3: AI 服務整合 (Week 3-4)
- [ ] 實作 AI 服務介面
- [ ] 整合 Anthropic Claude
- [ ] 整合 OpenAI
- [ ] 整合 Ollama

### Phase 4: Conversation Entity (Week 4-5)
- [ ] 實作 ConversationEntity
- [ ] Tool 呼叫處理
- [ ] 多輪對話支援

### Phase 5: 對話紀錄 (Week 5-6)
- [ ] 實作 Recorder 整合
- [ ] 用戶隔離
- [ ] 歷史查詢功能

### Phase 6: 測試與優化 (Week 6-7)
- [ ] 單元測試
- [ ] 整合測試
- [ ] 效能優化
- [ ] 文件撰寫

---

## 9. 成功指標

1. **功能完整性**
   - 97+ MCP tools 全部可用
   - 支援至少 3 種 AI 服務
   - Conversation Entity 可正常運作

2. **效能指標**
   - 對話回應時間 < 5 秒（不含 AI 處理時間）
   - SSE 連接建立時間 < 1 秒
   - 記憶體使用 < 100MB

3. **可靠性**
   - 連接斷線自動重連
   - 錯誤處理完善
   - 日誌記錄完整

---

## 10. 技術實作細節

### 10.1 單例模式
- 此整合只允許建立一個實例
- 在 Config Flow 的 `async_step_user` 中使用 `async_set_unique_id(DOMAIN)` 和 `_abort_if_unique_id_configured()` 確保單例

### 10.2 MCP Server 端點
- MCP Server 使用 Home Assistant 內建的 HTTP 伺服器
- 端點位於 `/api/ha_mcp_client/sse` 和 `/api/ha_mcp_client/sse/messages`
- 配置中的 port 參數僅供文件參考，實際端點使用 HA 的 HTTP 埠口

### 10.3 資源管理
- 對話歷史使用 `OrderedDict` 實現 LRU (Least Recently Used) 機制
- 最大保留 100 個對話，每個對話最多 50 條訊息
- AI 服務客戶端在實體移除時自動清理

### 10.4 時間處理
- 所有時間戳使用 UTC (`datetime.now(timezone.utc)`)
- 避免時區相關問題

### 10.5 資料庫會話
- 使用 `recorder.engine.connect()` 直接取得連接
- 在 `with Session(conn)` 區塊內進行資料庫操作
- 確保每次操作後正確 commit

### 10.6 授權控制
- 對話紀錄的清除和匯出服務需要授權檢查
- 一般用戶只能操作自己的紀錄
- 管理員可以操作任何用戶的紀錄

### 10.7 共享元件
- `ToolRegistry` 實例在 MCP Server 和 Conversation Entity 之間共享
- 透過 `hass.data[DOMAIN][entry.entry_id]` 傳遞共享元件

---

## 11. 測試結果

### 11.1 測試環境
- Home Assistant 2026.1.3
- 運行於 Podman 容器
- AI 服務：OpenAI GPT-4o-mini

### 11.2 功能測試結果

| 測試項目 | 狀態 | 說明 |
|---------|------|------|
| Config Flow | ✅ 通過 | 多步驟設定流程正常運作 |
| Conversation Entity 建立 | ✅ 通過 | 實體自動建立並註冊 |
| 實體列表查詢 | ✅ 通過 | 成功列出所有實體和區域 |
| 實體狀態查詢 | ✅ 通過 | 成功查詢 sun.sun 狀態和日出日落時間 |
| 智能搜尋 | ✅ 通過 | 搜尋 "backup" 成功返回相關實體 |
| 系統概覽 | ✅ 通過 | 顯示實體數量、區域、自動化等統計 |
| 多語言支援 | ✅ 通過 | 中文和英文對話均正常回應 |
| Tool 呼叫迴圈 | ✅ 通過 | AI 成功使用 MCP tools 獲取資訊 |

### 11.3 測試對話範例

**查詢 1: 列出實體**
```
輸入: "What entities are available?"
輸出: 成功列出 Areas (Living Room, Kitchen, Bedroom), Devices, Scenes, Automations, Scripts
```

**查詢 2: 太陽狀態**
```
輸入: "What is the state of the sun? Show me sunrise and sunset times."
輸出: Sun 狀態為 above horizon，並顯示 Next Sunrise/Sunset 時間
```

**查詢 3: 搜尋功能**
```
輸入: "Search for anything related to backup in the system"
輸出: 列出 5 個 backup 相關實體及其狀態
```

**查詢 4: 系統概覽**
```
輸入: "Give me a system overview of my smart home"
輸出: Total Entities: 19, Areas: 3, 並按 domain 分類顯示
```

### 11.4 發現的問題與修復

| 問題 | 原因 | 修復方案 |
|------|------|----------|
| SQLAlchemy metadata 保留字衝突 | Column 名稱使用了 metadata | 改名為 extra_data |
| ConversationResult response 格式錯誤 | 使用 dict 而非 IntentResponse | 改用 IntentResponse 物件 |

---

## 12. 參考資料

- [ha-mcp GitHub](https://github.com/homeassistant-ai/ha-mcp)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Protocol Specification](https://modelcontextprotocol.io/docs)
- [Home Assistant Conversation Entity](https://developers.home-assistant.io/docs/core/entity/conversation)
- [Home Assistant Custom Integration](https://developers.home-assistant.io/docs/creating_integration_manifest)

---

## 13. 修訂紀錄

| 日期 | 版本 | 變更內容 |
|------|------|----------|
| 2026-02-12 | 1.0 | 初版建立 |
| 2026-02-12 | 1.1 | 加入技術實作細節章節、修復程式碼審查發現的問題 |
| 2026-02-12 | 1.2 | 加入測試結果章節、記錄測試對話和修復的問題 |
