# PRD: 開發者部署工作流 — 自動化 Build / Deploy / Test

**日期**: 2026-03-07
**狀態**: 設計中
**優先級**: P0 — 開發效率基礎建設

---

## 1. 問題摘要

目前 ha_mcp_client 的開發→部署→測試流程完全靠手動操作：

1. 手動 `podman cp` 逐個檔案到容器
2. 手動 `podman restart homeassistant`
3. 手動執行測試腳本
4. Token 過期需手動重新取得
5. 沒有版本管理、沒有 HACS 支援
6. 每次修改 → 部署 → 測試要手動執行多個指令

**目標**: 建立 `make deploy`、`make test`、`make all` 等一行指令完成整個流程。

---

## 2. 環境資訊

| 項目 | 值 |
|------|-----|
| 容器引擎 | Podman |
| 容器名稱 | `homeassistant` |
| 映像 | `ghcr.io/home-assistant/home-assistant:stable` |
| HA 版本 | 2026.1.3 |
| 對外埠 | 18123 |
| Config mount | `/var/tmp/vibe-kanban/worktrees/8573-homeassistant-do/podman_docker_app/homeassistant/config` → `/config` |
| 原始碼 | `/var/tmp/vibe-kanban/worktrees/88d9-/ha_mcp_client/custom_components/ha_mcp_client/` |
| 容器內路徑 | `/config/custom_components/ha_mcp_client/` |
| 測試腳本 | `tests/test_comprehensive.py` |
| 其他自訂套件 | `virtual`（hass-virtual 虛擬實體） |

### 2.1 關鍵發現

由於 config 目錄是透過 volume mount 掛載的：
```
/var/tmp/.../homeassistant/config → /config
```
理論上直接操作 host 上的 mount 目錄就能更新檔案，**不需要 `podman cp`**。但目前原始碼與部署目錄不在同一個路徑，需要 rsync/cp 同步。

---

## 3. 設計方案

### 3.1 Makefile 指令設計

```makefile
# 核心指令
make deploy      # 同步原始碼 → 重啟 HA
make test        # 執行整合測試
make all         # deploy + 等待 HA ready + test
make watch       # 監控檔案變更自動 deploy
make logs        # 即時查看 HA 日誌
make token       # 取得/刷新 LLAT token

# 輔助指令
make status      # 檢查 HA 狀態 + 套件載入狀態
make clean       # 清除 __pycache__ 和暫存檔
make lint        # 程式碼檢查（ruff/flake8）
make validate    # 驗證 manifest.json + config flow
make version     # 顯示/設定版本號
make hacs        # 生成 HACS 所需檔案
```

### 3.2 檔案結構

```
ha_mcp_client/
├── Makefile                    ← 主要部署指令
├── scripts/
│   ├── deploy.sh               ← 同步 + 重啟邏輯
│   ├── wait-ha-ready.sh        ← 等待 HA 啟動完成
│   ├── get-token.sh            ← LLAT token 管理
│   └── run-tests.sh            ← 測試執行器（含 token 自動刷新）
├── hacs.json                   ← HACS 整合設定
├── custom_components/
│   └── ha_mcp_client/
│       └── ...
└── tests/
    └── test_comprehensive.py
```

### 3.3 各指令實作細節

#### `make deploy` — 同步原始碼到容器

```bash
#!/bin/bash
# scripts/deploy.sh

SRC="custom_components/ha_mcp_client"
CONTAINER="homeassistant"
DEST_BASE="/config/custom_components/ha_mcp_client"

echo "=== Syncing source to container ==="

# 方案 A：透過 volume mount 直接 rsync（快、不需 podman cp）
MOUNT_PATH=$(podman inspect $CONTAINER --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}')
if [ -n "$MOUNT_PATH" ]; then
    rsync -av --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        "$SRC/" "$MOUNT_PATH/custom_components/ha_mcp_client/"
    echo "✓ Synced via mount path: $MOUNT_PATH"
else
    # 方案 B：fallback 用 podman cp
    podman cp "$SRC/." "$CONTAINER:$DEST_BASE/"
    echo "✓ Synced via podman cp"
fi

echo "=== Restarting Home Assistant ==="
podman restart $CONTAINER

echo "=== Waiting for HA to be ready ==="
./scripts/wait-ha-ready.sh
```

#### `make test` — 執行測試（含 token 自動管理）

```bash
#!/bin/bash
# scripts/run-tests.sh

HA_URL="http://localhost:18123"
TOKEN_FILE=".ha_token"

# 嘗試用現有 token
if [ -f "$TOKEN_FILE" ]; then
    TOKEN=$(cat "$TOKEN_FILE")
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $TOKEN" "$HA_URL/api/")
    if [ "$HTTP_CODE" != "200" ]; then
        echo "Token expired, refreshing..."
        TOKEN=$(./scripts/get-token.sh)
    fi
else
    TOKEN=$(./scripts/get-token.sh)
fi

# 更新測試腳本中的 TOKEN
export HA_TOKEN="$TOKEN"
export HA_URL="$HA_URL"

python3 tests/test_comprehensive.py
```

#### `wait-ha-ready.sh` — 等待 HA 啟動

```bash
#!/bin/bash
# scripts/wait-ha-ready.sh

HA_URL="${HA_URL:-http://localhost:18123}"
MAX_WAIT=120
INTERVAL=3

echo "Waiting for HA at $HA_URL ..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$HA_URL/api/" \
        -H "Authorization: Bearer $(cat .ha_token 2>/dev/null)" 2>/dev/null)
    if [ "$STATUS" = "200" ]; then
        echo "✓ HA is ready (${elapsed}s)"

        # 確認 ha_mcp_client 已載入
        LOADED=$(curl -s "$HA_URL/api/config/config_entries/entry" \
            -H "Authorization: Bearer $(cat .ha_token)" | \
            python3 -c "import sys,json; entries=json.load(sys.stdin); print(any(e['domain']=='ha_mcp_client' for e in entries))" 2>/dev/null)
        if [ "$LOADED" = "True" ]; then
            echo "✓ ha_mcp_client is loaded"
            exit 0
        else
            echo "⚠ ha_mcp_client not yet loaded, waiting..."
        fi
    fi
    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
done

echo "✗ HA failed to start within ${MAX_WAIT}s"
exit 1
```

#### `get-token.sh` — Token 管理

```bash
#!/bin/bash
# scripts/get-token.sh
# 取得 Long-Lived Access Token 並存到 .ha_token

HA_URL="${HA_URL:-http://localhost:18123}"
HA_USER="${HA_USER:-admin}"
HA_PASS="${HA_PASS:-admin123}"
TOKEN_FILE=".ha_token"

# Step 1: Login 取得 auth code
FLOW_ID=$(curl -s "$HA_URL/auth/login_flow" \
    -H "Content-Type: application/json" \
    -d '{"client_id":"http://localhost:18123/","handler":["homeassistant",null],"redirect_uri":"http://localhost:18123/"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['flow_id'])")

AUTH_CODE=$(curl -s "$HA_URL/auth/login_flow/$FLOW_ID" \
    -H "Content-Type: application/json" \
    -d "{\"client_id\":\"http://localhost:18123/\",\"username\":\"$HA_USER\",\"password\":\"$HA_PASS\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))")

# Step 2: Exchange code for tokens
TOKENS=$(curl -s "$HA_URL/auth/token" \
    -d "grant_type=authorization_code&code=$AUTH_CODE&client_id=http://localhost:18123/")
ACCESS_TOKEN=$(echo "$TOKENS" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 3: Create LLAT via WebSocket
# 使用 python 腳本來建立 LLAT（WebSocket 操作較複雜）
LLAT=$(python3 -c "
import json, asyncio, websockets

async def get_llat():
    async with websockets.connect('ws://localhost:18123/api/websocket') as ws:
        msg = json.loads(await ws.recv())  # auth_required
        await ws.send(json.dumps({'type': 'auth', 'access_token': '$ACCESS_TOKEN'}))
        msg = json.loads(await ws.recv())  # auth_ok
        await ws.send(json.dumps({
            'id': 1, 'type': 'auth/long_lived_access_token',
            'client_name': 'dev-deploy-$(date +%s)',
            'lifespan': 365
        }))
        msg = json.loads(await ws.recv())
        print(msg['result'])

asyncio.run(get_llat())
" 2>/dev/null)

if [ -n "$LLAT" ] && [ "$LLAT" != "None" ]; then
    echo "$LLAT" > "$TOKEN_FILE"
    echo "$LLAT"
else
    # Fallback: 用 short-lived token
    echo "$ACCESS_TOKEN" > "$TOKEN_FILE"
    echo "$ACCESS_TOKEN"
fi
```

---

## 4. Makefile 完整設計

```makefile
# ── ha_mcp_client 開發部署 Makefile ──────────────────────────────

# 設定
CONTAINER     := homeassistant
HA_URL        := http://localhost:18123
HA_USER       := admin
HA_PASS       := admin123
SRC           := custom_components/ha_mcp_client
TOKEN_FILE    := .ha_token

# 自動偵測 mount path
MOUNT_PATH    := $(shell podman inspect $(CONTAINER) --format \
                 '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}' 2>/dev/null)
DEST          := $(MOUNT_PATH)/custom_components/ha_mcp_client

.PHONY: deploy test all status logs token clean lint watch help

# ── 主要指令 ────────────────────────────────────────────────────

help: ## 顯示所有可用指令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

deploy: ## 同步原始碼到容器並重啟 HA
	@echo "=== Deploying ha_mcp_client ==="
	@rsync -av --delete --exclude='__pycache__' --exclude='*.pyc' \
		$(SRC)/ $(DEST)/
	@echo "✓ Files synced"
	@podman restart $(CONTAINER)
	@echo "✓ Container restarted, waiting for HA..."
	@bash scripts/wait-ha-ready.sh

deploy-fast: ## 同步原始碼但不重啟（僅適用改前端 HTML/JS/CSS）
	@rsync -av --delete --exclude='__pycache__' --exclude='*.pyc' \
		$(SRC)/ $(DEST)/
	@echo "✓ Files synced (no restart)"

test: ## 執行整合測試
	@bash scripts/run-tests.sh

all: deploy test ## 部署 + 測試一條龍

status: ## 檢查 HA 和套件狀態
	@echo "=== Container ==="
	@podman ps --filter name=$(CONTAINER) --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@echo "=== HA Version ==="
	@podman exec $(CONTAINER) cat /config/.HA_VERSION 2>/dev/null || echo "N/A"
	@echo ""
	@echo "=== Integration Loaded ==="
	@curl -s $(HA_URL)/api/config/config_entries/entry \
		-H "Authorization: Bearer $$(cat $(TOKEN_FILE) 2>/dev/null)" 2>/dev/null | \
		python3 -c "import sys,json; entries=json.load(sys.stdin); \
		mcp=[e for e in entries if e['domain']=='ha_mcp_client']; \
		print(f'ha_mcp_client: {\"loaded\" if mcp else \"not found\"}'); \
		[print(f'  entry_id: {e[\"entry_id\"]}') for e in mcp]" 2>/dev/null || \
		echo "  Cannot connect (token expired?)"
	@echo ""
	@echo "=== Registered Tools ==="
	@podman logs $(CONTAINER) 2>&1 | grep "Registered tool:" | sort -u | wc -l | \
		xargs -I{} echo "  {} tools registered"

logs: ## 即時查看 HA 日誌（ha_mcp_client 相關）
	@podman logs -f $(CONTAINER) 2>&1 | grep -E "(ha_mcp_client|mcp|ERROR)"

logs-all: ## 即時查看所有 HA 日誌
	@podman logs -f $(CONTAINER)

token: ## 取得/刷新 LLAT token
	@bash scripts/get-token.sh
	@echo ""
	@echo "✓ Token saved to $(TOKEN_FILE)"

clean: ## 清除 __pycache__ 和暫存
	@find $(SRC) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find $(SRC) -name '*.pyc' -delete 2>/dev/null || true
	@echo "✓ Cleaned"

lint: ## 程式碼檢查
	@ruff check $(SRC) || true
	@echo "---"
	@python3 -c "import json; j=json.load(open('$(SRC)/manifest.json')); \
		print('✓ manifest.json valid'); \
		print(f'  version: {j[\"version\"]}'); \
		print(f'  domain: {j[\"domain\"]}')"

version: ## 顯示目前版本
	@python3 -c "import json; print(json.load(open('$(SRC)/manifest.json'))['version'])"

version-bump: ## 升版 (用法: make version-bump V=0.2.0)
	@python3 -c "import json; \
		f='$(SRC)/manifest.json'; \
		j=json.load(open(f)); \
		old=j['version']; \
		j['version']='$(V)'; \
		json.dump(j,open(f,'w'),indent=2); \
		print(f'✓ Version: {old} → $(V)')"

# ── HACS 支援 ──────────────────────────────────────────────────

hacs: ## 生成 HACS 所需檔案
	@echo '{"name": "HA MCP Client", "render_readme": true, "domains": ["conversation"], "homeassistant": "2024.1.0"}' | \
		python3 -m json.tool > hacs.json
	@echo "✓ hacs.json created"

# ── 監控模式 ────────────────────────────────────────────────────

watch: ## 監控原始碼變更自動 deploy-fast
	@echo "Watching $(SRC) for changes... (Ctrl+C to stop)"
	@while true; do \
		inotifywait -r -e modify,create,delete $(SRC) 2>/dev/null; \
		echo ""; \
		echo "=== Change detected, deploying... ==="; \
		$(MAKE) deploy-fast; \
	done
```

---

## 5. 測試腳本改進

### 5.1 環境變數化

目前 `test_comprehensive.py` 中 token 和 URL 是 hardcode。改為讀取環境變數：

```python
# tests/test_comprehensive.py 修改
import os

HA_URL = os.environ.get("HA_URL", "http://localhost:18123")
TOKEN = os.environ.get("HA_TOKEN", "")
if not TOKEN:
    token_file = os.path.join(os.path.dirname(__file__), "..", ".ha_token")
    if os.path.exists(token_file):
        TOKEN = open(token_file).read().strip()
```

### 5.2 run-tests.sh 自動管理 token

```bash
#!/bin/bash
# scripts/run-tests.sh

set -e

HA_URL="${HA_URL:-http://localhost:18123}"
TOKEN_FILE=".ha_token"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 讀取現有 token
if [ -f "$PROJECT_DIR/$TOKEN_FILE" ]; then
    TOKEN=$(cat "$PROJECT_DIR/$TOKEN_FILE")
else
    echo "No token found. Run 'make token' first."
    exit 1
fi

# 驗證 token 有效性
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $TOKEN" "$HA_URL/api/" 2>/dev/null)

if [ "$HTTP_CODE" != "200" ]; then
    echo "⚠ Token expired (HTTP $HTTP_CODE), refreshing..."
    TOKEN=$("$SCRIPT_DIR/get-token.sh")
fi

# 執行測試
echo "=== Running integration tests ==="
export HA_URL
export HA_TOKEN="$TOKEN"
cd "$PROJECT_DIR"
python3 tests/test_comprehensive.py
```

---

## 6. HACS 支援

### 6.1 hacs.json

```json
{
  "name": "HA MCP Client",
  "render_readme": true,
  "domains": ["conversation"],
  "homeassistant": "2024.1.0"
}
```

### 6.2 HACS 安裝要求

| 要求 | 現狀 | 需要做 |
|------|------|--------|
| `hacs.json` | 不存在 | `make hacs` 生成 |
| GitHub repo | 無公開 repo | 需推上 GitHub |
| `manifest.json` 格式 | ✅ 已符合 | — |
| `info.md` 或 README | README 過於簡略 | 需擴充 |
| 版本 tag | 無 | 需建立 release 流程 |

### 6.3 使用者安裝流程（HACS 完成後）

```
1. HACS → Integrations → + → 搜尋 "HA MCP Client" → 安裝
2. 重啟 HA
3. Settings → Integrations → Add → HA MCP Client
4. 依照 Config Flow 設定 AI 服務（OpenAI/Claude/Ollama）
5. 側邊欄出現「AI 聊天」面板 → 開始使用
```

---

## 7. .gitignore 更新

```gitignore
# Dev deploy
.ha_token
__pycache__/
*.pyc

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

---

## 8. 實作順序

| 步驟 | 內容 | 產出 |
|------|------|------|
| 1 | 建立 `scripts/` 目錄 + 4 個 shell 腳本 | `deploy.sh`, `wait-ha-ready.sh`, `get-token.sh`, `run-tests.sh` |
| 2 | 建立 `Makefile` | 所有 make 指令可用 |
| 3 | 修改 `test_comprehensive.py` 支援環境變數 | TOKEN/URL 不再 hardcode |
| 4 | 建立 `hacs.json` | HACS 可辨識 |
| 5 | 更新 `.gitignore` | 排除 token 和暫存 |
| 6 | 驗證：`make all` 一條龍測試 | deploy → wait → test 全自動 |

---

## 9. 指令使用範例

### 日常開發循環

```bash
# 第一次設定
make token              # 取得 LLAT
make status             # 確認環境正常

# 修改程式碼後
make all                # 部署 + 測試一條龍

# 只改前端 (HTML/JS/CSS)
make deploy-fast        # 不用重啟 HA

# 除錯
make logs               # 看 ha_mcp_client 相關日誌
make logs-all           # 看完整日誌

# 持續開發
make watch              # 檔案變更自動同步

# 升版
make version-bump V=0.2.0
```

### CI/CD 整合（未來）

```bash
# GitHub Actions workflow
make lint               # 程式碼檢查
make deploy             # 部署到測試環境
make test               # 執行整合測試
```

---

## 10. 成功指標

- [ ] `make deploy` 一行指令完成同步+重啟+等待就緒
- [ ] `make test` 自動管理 token 並執行測試
- [ ] `make all` 從修改到測試完成全自動
- [ ] `make status` 可快速確認環境狀態
- [ ] `make watch` 可監控檔案變更自動同步
- [ ] 測試腳本不再 hardcode token
- [ ] `.ha_token` 被 `.gitignore` 排除
- [ ] `hacs.json` 存在且格式正確
