# Helper CRUD 全面性測試計畫

## 概述

針對 Helper CRUD 功能設計全面性測試，主要透過 **AI 對話（MCP Tool 呼叫）** 驗證端到端行為，輔以 REST API 驗證副作用。

### 測試原則

- **AI-first**: 所有 CRUD 操作由 AI 透過 MCP tool 執行，驗證真實使用情境
- **副作用驗證**: AI 操作後，用 REST API 或 `ha_template` 確認實體狀態變更
- **非確定性處理**: AI 回應使用 `assert_soft` + retry 模式（最多 2 次重試）
- **自清理**: 每個測試建立的 Helper 在測試結束時刪除

### 測試區段

AA 區段重新設計為 5 個子區塊：

| 子區塊 | 範圍 | 測試數 | 說明 |
|--------|------|--------|------|
| AA1-AA12 | 基礎 REST API | 21 | 保留現有測試（已通過） |
| AA13-AA20 | 全類型 CRUD (AI) | ~24 | AI 對每種 Helper 類型做 create→verify→update→delete |
| AA21-AA24 | AI list + filter | ~6 | AI 使用 list_helpers 工具列出和過濾 |
| AA25-AA30 | 欄位驗證 (AI) | ~10 | AI 嘗試建立有完整欄位的 Helper，驗證欄位正確性 |
| AA31-AA36 | 錯誤處理 + 邊界 (AI) | ~8 | AI 嘗試無效操作，驗證錯誤回應 |

**預估總測試數**: ~69 項

---

## 子區塊一：基礎 REST API (AA1-AA12) — 保留現有

現有 21 項測試全部保留不動，已 100% 通過。

---

## 子區塊二：全類型 AI CRUD (AA13-AA20)

每種 Helper 類型一個完整的 AI 驅動 CRUD 循環。

### AA13. AI 建立 input_boolean

```
流程：
1. ai_chat("請使用 create_input_boolean 工具建立一個名為 'AI測試開關' 的布林開關")
2. 驗證 AI 回應包含 entity_id 或 success
3. ha_template 驗證 input_boolean.ai_ce_shi_kai_guan 存在
4. 清理：REST DELETE
```

### AA14. AI 建立 + 更新 + 刪除 input_number

```
流程：
1. ai_chat("使用 create_input_number 建立 'AI溫度' helper，最小值 0，最大值 50，步進 0.5，單位 °C")
2. 驗證實體存在 + state 屬性有 min/max
3. ai_chat("使用 update_input_number 更新 input_number.ai_wen_du，把最大值改為 100")
4. ha_template 驗證 max 屬性已更新
5. ai_chat("使用 delete_helper 刪除 input_number.ai_wen_du")
6. 驗證實體不存在
```

### AA15. AI 建立 input_select

```
流程：
1. ai_chat("使用 create_input_select 建立 'AI模式' helper，選項為 auto, manual, off")
2. 驗證實體存在 + options 屬性正確
3. 清理
```

### AA16. AI 建立 input_text

```
流程：
1. ai_chat("使用 create_input_text 建立 'AI備註' helper")
2. 驗證實體存在
3. 清理
```

### AA17. AI 建立 input_datetime

```
流程：
1. ai_chat("使用 create_input_datetime 建立 'AI排程時間' helper，包含日期和時間")
2. 驗證實體存在 + has_date/has_time 屬性
3. 清理
```

### AA18. AI 建立 input_button

```
流程：
1. ai_chat("使用 create_input_button 建立 'AI觸發按鈕' helper，圖示 mdi:play")
2. 驗證實體存在 + icon 屬性
3. 清理
```

### AA19. AI 建立 timer

```
流程：
1. ai_chat("使用 create_timer 建立 'AI計時器' helper，預設時間 00:05:00")
2. 驗證實體存在 + duration 屬性
3. 清理
```

### AA20. AI 建立 counter

```
流程：
1. ai_chat("使用 create_counter 建立 'AI計數器' helper，初始值 10，步進 5，最小值 0，最大值 100")
2. 驗證實體存在 + step/minimum/maximum 屬性
3. 清理
```

### 斷言策略

- AI 回應驗證：`assert_soft`（非確定性，允許 warn）
- 實體存在驗證：`assert_eq`（確定性，必須 pass）
- 屬性驗證：`assert_eq` 或 `assert_contains`（確定性）

---

## 子區塊三：AI list + filter (AA21-AA24)

### AA21. AI 列出所有 helpers

```
流程：
1. REST 建立 3 個不同類型 helper（input_boolean, timer, counter）
2. ai_chat("使用 list_helpers 工具列出所有 helpers")
3. 驗證回應包含 3 個測試 helper 名稱
4. 清理
```

### AA22. AI 用 type 過濾列出

```
流程：
1. 沿用 AA21 建立的 3 個 helper
2. ai_chat("使用 list_helpers 工具，只列出 timer 類型的 helpers")
3. 驗證回應包含 timer 但不包含 input_boolean
4. 清理
```

### AA23. AI 列出空結果

```
流程：
1. ai_chat("使用 list_helpers 工具，只列出 input_button 類型的 helpers")
2. 驗證 AI 回應表示沒有找到或 count=0
```

### AA24. AI 查詢特定 helper 詳情

```
流程：
1. REST 建立 input_number（帶完整屬性）
2. ai_chat("用 list_helpers 查詢 input_number 類型，告訴我 '查詢測試' 的 min 和 max 值")
3. 驗證 AI 回應包含正確的 min/max 值
4. 清理
```

---

## 子區塊四：欄位驗證 (AA25-AA30)

### AA25. input_number 完整欄位

```
流程：
1. ai_chat("使用 create_input_number 建立 'AI完整數字'，min=-10, max=200, step=2.5, mode=box, unit=kWh, icon=mdi:flash")
2. REST GET 驗證每個欄位值都正確
3. 清理
```

### AA26. input_select 更新選項

```
流程：
1. REST 建立 input_select（options: a, b, c）
2. ai_chat("使用 update_input_select 更新 input_select.xxx，把選項改成 x, y, z")
3. REST GET 驗證 options 已更新為 [x, y, z]
4. 清理
```

### AA27. timer 的 duration 格式

```
流程：
1. ai_chat("使用 create_timer 建立 'AI長計時器'，duration 為 01:30:00")
2. ha_template 驗證 duration 屬性為 1:30:00
3. 清理
```

### AA28. counter 的 minimum/maximum

```
流程：
1. ai_chat("使用 create_counter 建立 'AI範圍計數器'，minimum=5, maximum=50, step=3, initial=10")
2. ha_template 驗證 initial=10, step=3, min=5, max=50
3. 清理
```

### AA29. input_boolean icon 更新

```
流程：
1. REST 建立 input_boolean（無 icon）
2. ai_chat("使用 update_input_boolean 更新 input_boolean.xxx，設定 icon 為 mdi:lightbulb")
3. ha_template 驗證 icon 已更新
4. 清理
```

### AA30. input_text mode 和 pattern

```
流程：
1. ai_chat("使用 create_input_text 建立 'AI密碼欄位'，mode=password, min=8, max=64")
2. REST GET 驗證 mode=password, min=8, max=64
3. 清理
```

---

## 子區塊五：錯誤處理 + 邊界 (AA31-AA36)

### AA31. AI 刪除不存在的 helper

```
流程：
1. ai_chat("使用 delete_helper 刪除 input_boolean.nonexistent_entity_xyz")
2. 驗證 AI 回應包含 error 或 not found
```

### AA32. AI 更新不存在的 helper

```
流程：
1. ai_chat("使用 update_input_boolean 更新 input_boolean.nonexistent_xyz，name 改為 test")
2. 驗證 AI 回應包含 error 或 not found
```

### AA33. AI 建立後立即查詢（即時性驗證）

```
流程：
1. ai_chat("使用 create_input_boolean 建立 'AI即時測試'")
2. 不等待 — 立即 ha_template 查詢
3. 驗證實體立即可用
4. 清理
```

### AA34. AI 連續建立 + 刪除（快速操作）

```
流程：
1. ai_chat("建立一個叫 'AI快速1' 的 input_boolean，然後再建立一個叫 'AI快速2' 的 input_boolean")
2. 驗證兩個都存在
3. ai_chat("刪除 input_boolean.ai_kuai_su_1 和 input_boolean.ai_kuai_su_2")
4. 驗證兩個都已刪除
```

### AA35. AI 建立重複名稱

```
流程：
1. REST 建立 input_boolean name="AI重複測試"
2. ai_chat("使用 create_input_boolean 建立名稱為 'AI重複測試' 的 helper")
3. 驗證 AI 回應包含 error 或 already exists
4. 清理原始 entity
```

### AA36. AI 完整 CRUD 循環（多步驟對話）

```
流程：
1. ai_chat("建立一個名為 'AI生命週期' 的 counter helper，初始值 0，步進 1")
   → 驗證建立成功
2. ai_chat("用 list_helpers 列出 counter 類型的 helper")
   → 驗證包含 AI生命週期
3. ai_chat("把 counter.ai_sheng_ming_zhou_qi 的步進改為 5")
   → 驗證更新成功
4. ai_chat("刪除 counter.ai_sheng_ming_zhou_qi")
   → 驗證刪除成功
5. ha_template 驗證實體已不存在
```

---

## 測試基礎設施

### AI 呼叫模式

```bash
# 標準 AI tool 呼叫 + 重試
_ai_ok=false
for _attempt in 1 2; do
  speech=$(ai_chat "使用 create_input_boolean 工具建立名為 'AI測試' 的 helper")
  if echo "$speech" | grep -qi "success\|建立\|已建\|created\|entity_id"; then
    _pass "AAxx: AI created input_boolean"
    _ai_ok=true
    break
  fi
  [ "$_attempt" -lt 2 ] && sleep 3
done
if [ "$_ai_ok" = "false" ]; then
  assert_soft "AAxx: AI created input_boolean" "success\|建立" "$speech"
fi
```

### 副作用驗證模式

```bash
# 用 ha_template 確認實體存在
sleep 1
state=$(ha_template "{{ states('input_boolean.ai_ce_shi') }}")
if [ "$state" != "" ] && [ "$state" != "unknown" ] && [ "$state" != "unavailable" ]; then
  _pass "AAxx: entity exists after AI create"
else
  _fail "AAxx: entity not found after AI create (state=$state)"
fi
```

### 清理模式

```bash
# 每個測試結束後清理
http_delete "$API/helpers/input_boolean.ai_ce_shi" > /dev/null 2>&1
sleep 1
```

---

## 預估結果

| 類型 | 數量 | 斷言方式 | 預期通過率 |
|------|------|---------|-----------|
| REST API (AA1-12) | 21 | assert_eq | 100% |
| AI CRUD 全類型 (AA13-20) | ~24 | assert_soft + assert_eq | 90%+ (AI warn) |
| AI list/filter (AA21-24) | ~6 | assert_soft + assert_eq | 90%+ |
| AI 欄位驗證 (AA25-30) | ~10 | assert_soft + assert_eq | 85%+ |
| AI 錯誤/邊界 (AA31-36) | ~8 | assert_soft | 85%+ |
| **合計** | **~69** | | **95%+ pass, <5% warn** |

---

## 實作順序

1. 保留 AA1-AA12 不動
2. 實作 AA13-AA20（全類型 AI CRUD）
3. 實作 AA21-AA24（AI list/filter）
4. 實作 AA25-AA30（欄位驗證）
5. 實作 AA31-AA36（錯誤/邊界）
6. 執行完整 AA 測試
7. 執行完整 A-Z + AA 測試確認無回歸
