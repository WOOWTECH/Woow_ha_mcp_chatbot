# PRD: Cron Job ↔ HA Automation 雙向同步系統

## 目標

每個 cron job 自動對應一個 HA native automation，雙向同步變更。
cron job 變更時自動更新 automation，automation 被修改時同步回 cron job。
所有排程結果統一送到 `notify.persistent_notification`。

## 設計決策（來自 brainstorming）

| # | 問題 | 決策 |
|---|------|------|
| 1 | 同步方向 | **真正雙向**：cron→automation 且 automation→cron |
| 2 | 變更偵測 | **混合模式**：事件監聽 + 啟動時全量比對 |
| 3 | ID 對映 | **統一 ID**：automation ID = `ha_mcp_cron_{job_id}` |
| 4 | Payload 處理 | **統一 persistent_notification**；反向同步只同步 schedule + message，不改 payload kind |

## 架構概覽

```
┌──────────────┐                        ┌──────────────────┐
│  CronService │  ── sync forward ──▶   │  automations.yaml│
│  (store.json)│  ◀── sync reverse ──   │  (HA automations)│
└──────┬───────┘                        └────────┬─────────┘
       │                                         │
       │  add/update/remove                      │  state_changed
       │                                         │  automation_reloaded
       ▼                                         ▼
┌──────────────────────────────────────────────────────────┐
│                   CronAutomationSync                     │
│  - forward sync: cron CRUD → create/update/delete auto   │
│  - reverse sync: HA events → update cron schedule/message │
│  - startup reconciliation: full compare on boot           │
└──────────────────────────────────────────────────────────┘
```

## 變更範圍

### 變更 1：新增 `CronAutomationSync` 類別

**新檔案**：`nanobot/cron_automation_sync.py`

負責 cron job 與 automation 的雙向同步。

#### 1.1 Forward Sync（Cron → Automation）

當 CronService 執行 `add_job`、`update_job`、`remove_job` 後，觸發同步：

```python
class CronAutomationSync:
    def __init__(self, hass: HomeAssistant, cron_service: CronService):
        self.hass = hass
        self.cron_service = cron_service
        self._syncing = False  # 防止迴圈同步

    def _automation_id(self, job_id: str) -> str:
        return f"ha_mcp_cron_{job_id}"

    async def on_job_added(self, job: CronJob) -> None:
        """Cron job 新增 → 建立對應 automation"""
        if self._syncing:
            return
        automation_id = self._automation_id(job.id)
        trigger = _schedule_to_trigger(job.schedule)
        action = self._build_notification_action(job)
        await self._upsert_automation(automation_id, job, trigger, action)

    async def on_job_updated(self, job: CronJob) -> None:
        """Cron job 更新 → 更新對應 automation"""
        if self._syncing:
            return
        automation_id = self._automation_id(job.id)
        trigger = _schedule_to_trigger(job.schedule)
        action = self._build_notification_action(job)
        await self._upsert_automation(automation_id, job, trigger, action)

    async def on_job_removed(self, job_id: str) -> None:
        """Cron job 刪除 → 刪除對應 automation"""
        if self._syncing:
            return
        automation_id = self._automation_id(job_id)
        await self._remove_automation(automation_id)
```

#### 1.2 Reverse Sync（Automation → Cron）

監聽 HA 事件，偵測 automation 變更：

```python
async def async_setup(self) -> None:
    """註冊事件監聽器"""
    # 監聽 automation reload 事件
    self.hass.bus.async_listen("automation_reloaded", self._on_automation_reloaded)
    # 啟動時全量比對
    await self._reconcile()

async def _on_automation_reloaded(self, event) -> None:
    """Automation 被 reload（可能從 UI 編輯）→ 掃描所有 ha_mcp_cron_* automation"""
    await self._reconcile()

async def _reconcile(self) -> None:
    """全量比對 cron jobs 與 automations"""
    if self._syncing:
        return
    self._syncing = True
    try:
        # 1. 取得所有 ha_mcp_cron_* automations
        automations = self._get_cron_automations()
        cron_jobs = {j.id: j for j in await self.cron_service.list_jobs()}

        # 2. Forward: cron job 有但 automation 沒有 → 建立
        for job_id, job in cron_jobs.items():
            auto_id = self._automation_id(job_id)
            if auto_id not in automations:
                await self._create_automation_for_job(job)

        # 3. Reverse: automation 有但 cron job 沒有 → 不建立（不反向創建）
        #    automation 有且 cron job 有 → 比較 schedule/message，如不同則更新 cron
        for auto_id, auto_config in automations.items():
            job_id = auto_id.replace("ha_mcp_cron_", "")
            if job_id in cron_jobs:
                await self._reverse_sync_job(cron_jobs[job_id], auto_config)

        # 4. Orphan cleanup: automation 有但 cron job 沒有 → 刪除 automation
        for auto_id in automations:
            job_id = auto_id.replace("ha_mcp_cron_", "")
            if job_id not in cron_jobs:
                await self._remove_automation(auto_id)
    finally:
        self._syncing = False
```

#### 1.3 Reverse Sync 範圍限制

反向同步只更新 cron job 的 **schedule** 和 **message**，不改 `payload.kind`：

```python
async def _reverse_sync_job(self, job: CronJob, auto_config: dict) -> None:
    """從 automation 設定反向同步到 cron job（只同步 schedule + message）"""
    updates = {}

    # 從 trigger 反解 schedule
    new_schedule = self._trigger_to_schedule(auto_config.get("trigger", []))
    if new_schedule and new_schedule != job.schedule.to_dict():
        updates["schedule"] = new_schedule

    # 從 action 提取 message（persistent_notification 的 message 欄位）
    new_message = self._extract_message_from_action(auto_config.get("action", []))
    if new_message and new_message != job.payload.message:
        updates["payload"] = {"kind": job.payload.kind, "message": new_message}

    if updates:
        await self.cron_service.update_job(job.id, updates)
```

#### 1.4 Automation 格式

所有同步產生的 automation 統一使用 `notify.persistent_notification`：

```yaml
# automations.yaml 中的每筆同步產生的 automation
- id: "ha_mcp_cron_a1b2c3d4"
  alias: "Cron: 每日溫度報告"
  description: "由 cron job [a1b2c3d4] 自動同步，請勿手動刪除"
  trigger:
    - platform: time
      at: "08:00:00"
  action:
    - service: notify.persistent_notification
      data:
        title: "🕐 排程通知：每日溫度報告"
        message: "檢查 sensor.living_room_temperature"
```

### 變更 2：CronService 加入同步 hook

**檔案**：`nanobot/cron_service.py`

在 `add_job`、`update_job`、`remove_job` 結尾加入同步呼叫：

```python
# add_job 結尾
async def add_job(self, ...) -> CronJob:
    ...existing code...
    # 同步到 automation
    if self._sync:
        await self._sync.on_job_added(job)
    return job

# update_job 結尾
async def update_job(self, job_id, updates) -> CronJob | None:
    ...existing code...
    if self._sync and job:
        await self._sync.on_job_updated(job)
    return job

# remove_job 結尾
async def remove_job(self, job_id) -> bool:
    ...existing code...
    if removed and self._sync:
        await self._sync.on_job_removed(job_id)
    return removed
```

`CronService.__init__` 新增 `self._sync: CronAutomationSync | None = None` 屬性，
在 `async_setup` 結尾初始化並啟動 sync：

```python
async def async_setup(self) -> None:
    ...existing code...
    from .cron_automation_sync import CronAutomationSync
    self._sync = CronAutomationSync(self.hass, self)
    await self._sync.async_setup()
```

### 變更 3：`_execute_agent_turn` 加送 persistent_notification

**檔案**：`nanobot/cron_service.py`

改為 `blocking=True, return_response=True`，取得 AI 回覆後送到側邊欄通知：

```python
async def _execute_agent_turn(self, job: CronJob) -> None:
    self.hass.bus.async_fire("ha_mcp_client_cron_agent_turn", {...})

    try:
        from ..const import DOMAIN
        agent_id = None
        for state in self.hass.states.async_all("conversation"):
            if DOMAIN in state.entity_id:
                agent_id = state.entity_id
                break

        if agent_id and job.payload.message:
            result = await self.hass.services.async_call(
                "conversation", "process",
                {"text": job.payload.message, "agent_id": agent_id},
                blocking=True,
                return_response=True,
            )

            # 解析 AI 回覆
            ai_response = ""
            if result and "response" in result:
                speech = result["response"].get("speech", {})
                if isinstance(speech, dict):
                    ai_response = speech.get("plain", {}).get("speech", "")
                elif isinstance(speech, str):
                    ai_response = speech

            # 送到 persistent_notification
            if ai_response:
                await self.hass.services.async_call(
                    "notify", "persistent_notification",
                    {
                        "title": f"🤖 AI 排程回覆：{job.name}",
                        "message": ai_response,
                    },
                    blocking=False,
                )
    except Exception as e:
        _LOGGER.warning("Could not trigger conversation for cron job: %s", e)
```

### 變更 4：5 個藍圖全部改為 `notify.persistent_notification`

**影響檔案**：

| 藍圖 | 改動 |
|------|------|
| `ai_daily_report.yaml` | ✅ 已完成 |
| `ai_periodic_check.yaml` | ✅ 已完成 |
| `scheduled_device_control.yaml` | 移除 `conversation_entity`，action 改為 persistent_notification |
| `interval_monitor.yaml` | 移除 `conversation_entity`，action 改為 persistent_notification |
| `cron_event_trigger.yaml` | 保留原 event 觸發 action，額外加 persistent_notification |

### 變更 5：`_payload_to_action` 統一使用 persistent_notification

**檔案**：`mcp/tools/helpers.py`

`agent_turn` 的 bridge 轉換也改為 persistent_notification（搭配 conversation.process）：

```python
if payload.kind == "agent_turn":
    return [
        {
            "service": "conversation.process",
            "data": {
                "text": payload.message,
                "agent_id": agent_id,
            },
        },
        {
            "service": "notify.persistent_notification",
            "data": {
                "title": "🤖 AI 排程通知",
                "message": payload.message,
            },
        },
    ]
```

### 變更 6：`create_automation` 支援指定 ID

**檔案**：`mcp/tools/helpers.py`

`create_automation()` 函數新增 `automation_id` 參數，讓 sync 可以指定統一 ID：

```python
async def create_automation(
    hass, alias, trigger, action,
    description=None, mode="single", condition=None,
    automation_id=None,  # 新增：允許指定 ID
) -> dict:
    automation_id = automation_id or str(uuid.uuid4()).replace("-", "")[:12]
    ...
```

同時新增 `update_automation()` 和 `remove_automation()` 函數：

```python
async def update_automation(
    hass, automation_id: str, trigger=None, action=None,
    alias=None, description=None,
) -> dict:
    """更新 automations.yaml 中指定 ID 的 automation"""

async def remove_automation(
    hass, automation_id: str,
) -> dict:
    """從 automations.yaml 中移除指定 ID 的 automation"""
```

## 同步生命週期

### 建立 Cron Job

```
User/AI → CronService.add_job()
  → store.json 寫入
  → sync.on_job_added(job)
    → create_automation(id="ha_mcp_cron_{job_id}", ...)
    → automations.yaml 寫入
    → automation.reload
```

### 更新 Cron Job

```
User/AI → CronService.update_job()
  → store.json 更新
  → sync.on_job_updated(job)
    → update_automation(id="ha_mcp_cron_{job_id}", ...)
    → automations.yaml 更新
    → automation.reload
```

### 刪除 Cron Job

```
User/AI → CronService.remove_job()
  → store.json 刪除
  → sync.on_job_removed(job_id)
    → remove_automation(id="ha_mcp_cron_{job_id}")
    → automations.yaml 移除
    → automation.reload
```

### 使用者從 HA UI 修改 Automation

```
HA UI 編輯 → automations.yaml 修改 → automation.reload
  → 事件: automation_reloaded
  → sync._reconcile()
    → 比對 ha_mcp_cron_* automations
    → 反向更新 cron job schedule/message（不改 payload.kind）
    → store.json 更新
```

### 啟動時

```
HA 重啟 → CronService.async_setup()
  → sync.async_setup()
    → sync._reconcile()
      → 缺少的 automation → 建立
      → 孤兒 automation → 刪除
      → 不一致的 schedule/message → 反向同步到 cron
```

## 防止迴圈同步

使用 `_syncing` flag：

```
CronService.add_job()
  → sync.on_job_added()           # _syncing = False → 執行
    → _upsert_automation()
      → automation.reload
        → _on_automation_reloaded()
          → _reconcile()          # _syncing = True → 跳過
```

反向同步觸發 `update_job` 時：
```
_reconcile() 中
  self._syncing = True
  → cron_service.update_job()
    → sync.on_job_updated()       # _syncing = True → 跳過
  self._syncing = False
```

## 檔案變更清單

| 檔案 | 動作 | 描述 |
|------|------|------|
| `nanobot/cron_automation_sync.py` | **新增** | 雙向同步管理器 |
| `nanobot/cron_service.py` | 修改 | 加入 sync hooks + agent_turn persistent_notification |
| `mcp/tools/helpers.py` | 修改 | create_automation 支援 ID，新增 update/remove_automation |
| `blueprints/automation/scheduled_device_control.yaml` | 修改 | 移除 conversation_entity |
| `blueprints/automation/interval_monitor.yaml` | 修改 | 移除 conversation_entity |
| `blueprints/automation/cron_event_trigger.yaml` | 修改 | 加 persistent_notification |
| `tests/test_all.sh` | 修改 | 更新 Section Q，加入同步測試 |

## 測試計畫

1. **Forward Sync 測試**
   - 建立 cron job → 驗證 automations.yaml 出現 `ha_mcp_cron_{id}`
   - 更新 cron job schedule → 驗證 automation trigger 同步更新
   - 刪除 cron job → 驗證 automation 被移除

2. **Reverse Sync 測試**
   - 修改 automation 的 trigger 時間 → 驗證 cron job schedule 更新
   - 修改 automation 的 message → 驗證 cron job payload.message 更新
   - 驗證 payload.kind 不被改動

3. **Persistent Notification 測試**
   - agent_turn cron job 觸發 → 驗證 AI 回覆出現在側邊欄通知
   - system_event cron job 觸發 → 驗證訊息出現在側邊欄通知
   - 藍圖自動化觸發 → 驗證通知出現

4. **迴圈防護測試**
   - 快速連續 add/update → 不產生無限迴圈
   - 驗證 `_syncing` flag 正確運作

5. **啟動 Reconciliation 測試**
   - 手動刪除 automation → 重啟 → 驗證自動重建
   - 手動修改 automation trigger → 重啟 → 驗證反向同步

6. **回歸測試**
   - Section A-Q 全通過

## 不在本次範圍

- 前端面板內嵌通知顯示（保留在 HA 原生通知面板）
- 推播到手機（需另行設定 mobile_app notify）
- 從 automation 反向建立新 cron job（只同步已存在的 cron job 對應的 automation）
- Blueprint-based automation 的反向同步（只針對直接寫入 automations.yaml 的 automation）
