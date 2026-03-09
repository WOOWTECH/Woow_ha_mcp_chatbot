# PRD: Cron Job 全面整合 persistent_notification

## 目標

將所有 cron job 的執行結果統一送到 HA 側邊欄通知面板（`notify.persistent_notification`），讓用戶不需開啟 AI 聊天介面即可看到排程執行結果。

## 背景

目前的問題：
1. **藍圖**：4 個藍圖使用 `conversation.process`，要求用戶手動選擇「AI 對話實體」，體驗不佳
2. **agent_turn cron job**：AI 回覆只出現在對話紀錄中，用戶不會在通知面板看到
3. **system_event cron job**：已經有送 `persistent_notification`（上一次改動），但藍圖的 action 仍未統一

## 改動範圍

### 變更 1：5 個藍圖 YAML 全部改為 `notify.persistent_notification`

移除 `conversation_entity` input，action 改為 `notify.persistent_notification`。

**影響檔案**：
- `blueprints/automation/ai_daily_report.yaml`
- `blueprints/automation/ai_periodic_check.yaml`
- `blueprints/automation/scheduled_device_control.yaml`
- `blueprints/automation/interval_monitor.yaml`
- `blueprints/automation/cron_event_trigger.yaml`

**改動模式**（以 ai_daily_report 為例）：

```yaml
# 移除 conversation_entity input
# 新增 notification_title input

input:
  report_time:
    name: "報告時間"
    ...
  report_prompt:
    name: "通知訊息"
    description: "通知內容"
    ...
  notification_title:
    name: "通知標題"
    default: "🕐 AI 每日報告"
    selector:
      text:

action:
  - service: notify.persistent_notification
    data:
      title: !input notification_title
      message: !input report_prompt
```

### 變更 2：`_execute_agent_turn` 加送 persistent_notification

在 `cron_service.py` 中，`_execute_agent_turn` 改為 `blocking=True, return_response=True`，取得 AI 回覆後送到 `persistent_notification`。

```python
# 改為 blocking=True + return_response=True
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
```

### 變更 3：`_payload_to_action` bridge helper 同步更新

`helpers.py` 中 `agent_turn` 的 action 也加上 persistent_notification，讓透過 bridge 轉換的自動化同樣會送通知。

由於藍圖模式下無法用 `response_variable`，bridge 轉出的 `agent_turn` 自動化仍保留 `conversation.process`（自動偵測 entity），並額外加一步 `notify.persistent_notification` 送原始 prompt（非 AI 回覆）作為通知提示。

## 測試計畫

1. 建立 `system_event` cron job → 觸發 → 檢查側邊欄通知
2. 建立 `agent_turn` cron job → 觸發 → 檢查 AI 回覆出現在側邊欄通知
3. 透過前端「立即觸發」按鈕測試
4. 安裝藍圖 → 建立自動化 → 確認不需選對話實體
5. 回歸測試 Section Q

## 不在本次範圍

- 前端面板內嵌通知顯示（保留在 HA 原生通知面板）
- 推播到手機（需另行設定 mobile_app notify）
