# Findings & Decisions — HA MCP Client v1.0 發佈前測試

## Requirements
- 全面性發佈前測試，覆蓋所有功能模塊
- 參考 nanobot 倉庫功能和議題，預防已知問題
- 現有 234 tests (A-R) 保持不變，新增 S-Z sections
- 目標: 300+ test cases, 0 failures
- 重點覆蓋: 對話隔離、Provider 切換、工具完整性、安全性

## Research Findings

### nanobot 倉庫功能對照分析

| nanobot 功能 | ha_mcp_client 對應 | 測試覆蓋 |
|-------------|-------------------|---------|
| Multi-provider LLM | Anthropic/OpenAI/Ollama/OpenAI-compatible | 新增 Section T |
| Session/conversation history | conversation.py + recorder | 新增 Section S |
| MCP tool integration | 77+ tools via SSE | 新增 Section U/X |
| Memory system (long-term) | SOUL/USER/MEMORY/HISTORY.md | 已有 K/O, 新增 Z |
| Scheduled tasks (cron) | cron_store.py + blueprints | 已有 J/N/Q/R |
| Skill system | skills.py + always-on/on-demand | 已有 L/M |
| Channel integrations | HA frontend panel + input_text | 已有 D/W |
| Access control | Token auth + user isolation | 新增 Section Y |
| Prompt caching | Not implemented (out of scope) | N/A |
| Agent swarm | Not implemented | N/A |

### nanobot 議題對照分析

| nanobot 議題 | 風險描述 | ha_mcp_client 預防措施 |
|-------------|---------|----------------------|
| #1709 Context model | 上下文結構不正確 | **已修復**: conversation_id 傳遞到 recorder |
| #1634 Session corruption | Provider 切換時 session 損壞 | Section T: 切換後驗證 |
| #1698 Memory consolidation | 整合後不持久化 | Section Z1: consolidation 安全測試 |
| #1487 JSON format error | tool call 參數 JSON 格式錯誤 | Section U: MCP 工具直接調用驗證 |
| #1739 Multiple instances | 多實例衝突 | Section V: 並發測試 |
| #1762 Cannot interrupt | 無法中斷工作中的 bot | Section V6: 快速連續訊息 |
| #1496 Cron list no details | Cron 列表缺少排程詳情 | 已在 Section J 覆蓋 |
| #1710 No answer generated | 未產生回答 | Section T3/T7: 切換後回應驗證 |
| #1526 API path compatibility | /chat/completions vs /v1/chat/completions | Section X: MCP 協議完整性 |
| #1615 History visibility | 歷史訊息不可見 | **已修復**: loadConversations + recorder |
| #1486 Provider routing | Provider 路由錯誤 | Section T: Provider 切換驗證 |

### 已修復的 Bug (本次 session)

| Bug | 檔案 | 修復內容 |
|-----|------|---------|
| 對話歷史消失 (tab 切換) | frontend/app.js | loadConversations() 後 re-select 當前對話 |
| Scene/Automation 刪除失敗 | mcp/tools/helpers.py | 使用 state.attributes.get("id") 匹配 YAML id |
| 對話歷史跨對話混雜 | conversation.py | _load_history_from_recorder 傳入 conversation_id |
| Model 列表過時 | config_flow.py | 更新為 GPT-5/Claude-4/Gemini-2.5/Llama-4 |

### 架構分析

**核心功能模塊:**
```
ha_mcp_client/
├── __init__.py          # 整合入口, 服務註冊
├── config_flow.py       # 設定流程, Provider/Model 選擇
├── const.py             # 常數, 預設值
├── conversation.py      # 對話 entity, AI 呼叫迴圈
├── conversation_recorder.py  # SQLAlchemy 歷史儲存
├── views.py             # 30+ REST API endpoints
├── sensor.py            # 9 種 sensor entities
├── select.py            # 2 種 select entities
├── switch.py            # 動態 switch entities
├── number.py            # 3 種 number entities
├── ai_services/         # 4 個 AI provider 實作
│   ├── anthropic.py
│   ├── openai.py
│   ├── ollama.py
│   └── openai_compatible.py
├── mcp/
│   ├── server.py        # MCP SSE server
│   └── tools/
│       ├── registry.py  # 77+ 工具註冊
│       └── helpers.py   # 工具實作函式
├── nanobot/
│   ├── memory.py        # 記憶系統 (SOUL/USER/MEMORY/HISTORY)
│   ├── skills.py        # 技能系統
│   ├── cron_store.py    # 排程系統
│   └── cron_automation_sync.py  # 雙向同步
└── frontend/
    ├── index.html       # 面板 UI
    ├── app.js           # 前端邏輯 (vanilla JS)
    └── styles.css       # 樣式
```

**測試基礎設施:**
```
tests/
├── test_all.sh          # 主要測試套件 (2,567 行, 18 sections A-R)
└── test_comprehensive.py # Python MCP 協議測試 (1,231 行)
```

**REST API 完整路由:**
- `/api/ha_mcp_client/conversations` (GET/POST)
- `/api/ha_mcp_client/conversations/{id}` (PATCH/DELETE)
- `/api/ha_mcp_client/conversations/{id}/messages` (GET/POST)
- `/api/ha_mcp_client/memory` (GET)
- `/api/ha_mcp_client/memory/{section}` (GET/PUT)
- `/api/ha_mcp_client/memory/search` (POST)
- `/api/ha_mcp_client/memory/consolidate` (POST)
- `/api/ha_mcp_client/skills` (GET/POST)
- `/api/ha_mcp_client/skills/{name}` (GET/PUT/DELETE)
- `/api/ha_mcp_client/cron/jobs` (GET/POST)
- `/api/ha_mcp_client/cron/jobs/{id}` (GET/PATCH/DELETE)
- `/api/ha_mcp_client/cron/jobs/{id}/trigger` (POST)
- `/api/ha_mcp_client/cron/jobs/{id}/to_automation` (POST)
- `/api/ha_mcp_client/blueprints` (GET)
- `/api/ha_mcp_client/blueprints/install` (POST)
- `/api/ha_mcp_client/llm_providers` (GET)
- `/api/ha_mcp_client/active_llm` (PATCH)
- `/api/ha_mcp_client/settings` (GET/PATCH)
- `/api/ha_mcp_client/sse` (GET - SSE)
- `/api/ha_mcp_client/sse/messages` (POST - JSON-RPC)

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 8 個新 sections (S-Z) | 覆蓋所有識別到的空缺 |
| bash curl 統一風格 | 與 A-R sections 一致, 降低維護成本 |
| MCP 工具直接測試 (非 AI) | 消除 AI 隨機性, 精準驗證工具功能 |
| 安全測試全部 hard assert | 安全問題必須 0 容忍 |
| 並發用 bash & + wait | 簡單, 無外部依賴 |
| 前端用 API 結構驗證 | 比 headless browser 快且穩定 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 舊 task_plan.md 存在 | 覆寫為新的發佈前測試計劃 |
| nanobot issues 411 個太多 | 聚焦前 3 頁最相關的 ~36 個 |

## Resources
- nanobot 倉庫: https://github.com/HKUDS/nanobot
- HA REST API: http://localhost:18123/api/
- MCP SSE: http://localhost:18123/api/ha_mcp_client/sse
- 原始碼: /var/tmp/vibe-kanban/worktrees/410d-codebase-and-cod/ha_mcp_client/
- HA config: /var/tmp/vibe-kanban/worktrees/8573-homeassistant-do/podman_docker_app/homeassistant/config/
- Auth Token: eyJhbGciOiJIUzI1NiIs...（見 test_all.sh）

## 測試覆蓋率目標

| 模塊 | 現有覆蓋 | 新增覆蓋 | 預期總數 |
|------|---------|---------|---------|
| 對話系統 | B5, C, P3 | S1-S6 | 15+ |
| Provider 管理 | A3 (select) | T1-T8 | 12+ |
| 工具調用 | test_comprehensive.py (65) | U1-U15 (via MCP) | 40+ |
| 並發/壓力 | (無) | V1-V6 | 10+ |
| 前端 | D1-D4 | W1-W7 | 12+ |
| MCP 協議 | E1-E2 | X1-X8 | 12+ |
| 安全 | H8 (1 test) | Y1-Y8 | 12+ |
| 資料完整 | K, O | Z1-Z7 | 10+ |
| **合計** | **234** | **~80** | **~314** |
