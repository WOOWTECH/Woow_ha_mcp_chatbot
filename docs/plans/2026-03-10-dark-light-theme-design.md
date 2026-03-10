# 深淺色主題設計 — 跟隨 HA 主題變化

> 日期: 2026-03-10
> 狀態: 待審核

## 目標

面板跟隨 Home Assistant 的主題切換（深色/淺色），當使用者在 HA 中更換主題時，iframe 面板即時同步變化。面板本身不提供獨立的主題切換 UI。

## 設計決策

| 決策 | 選擇 |
|------|------|
| 主題跟隨策略 | 純跟隨 HA，無獨立切換按鈕 |
| 顏色來源 | HA CSS 變數優先 + 自訂 fallback |
| 偵測機制 | MutationObserver 監聽 parent document |

## 架構概覽

```
┌─────────────────────────────────────────────┐
│  Home Assistant (parent window)             │
│  <html style="--primary-color:#03a9f4; ...">│
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │  ha_mcp_client iframe                 │  │
│  │                                       │  │
│  │  1. MutationObserver 監聽 parent      │  │
│  │     <html> style 屬性變化             │  │
│  │  2. 讀取 parent CSS 變數              │  │
│  │  3. 同步到 iframe :root               │  │
│  │  4. hass.themes.darkMode 判斷深淺色   │  │
│  │     → 設定 data-theme="dark|light"    │  │
│  │  5. CSS 用 [data-theme="dark"] 選擇器 │  │
│  │     覆寫自訂顏色                      │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## 實作步驟

### Step 1: CSS — 新增深色主題變數

修改 `styles.css`：

- `:root` 保留目前的淺色值作為 fallback
- 新增 `html[data-theme="dark"]` 區塊，定義深色主題專用的衍生變數

```css
/* 淺色（預設 fallback） */
:root {
  --primary-color: #03a9f4;
  --primary-text-color: #212121;
  --secondary-text-color: #727272;
  --text-primary-color: #fff;
  --card-background-color: #fff;
  --sidebar-background-color: #f5f5f5;
  --divider-color: #e0e0e0;
  --error-color: #db4437;
  --success-color: #0f9d58;

  /* 面板專用衍生色 */
  --user-bubble-bg: var(--primary-color);
  --user-bubble-text: var(--text-primary-color);
  --ai-bubble-bg: var(--card-background-color);
  --ai-bubble-text: var(--primary-text-color);
  --sidebar-bg: var(--sidebar-background-color);
  --input-bg: var(--card-background-color);

  /* 新增：深色模式需要的額外變數 */
  --code-bg: #f5f5f5;
  --code-text: #333;
  --hover-bg: rgba(0, 0, 0, 0.04);
  --shadow-color: rgba(0, 0, 0, 0.1);
  --scrollbar-thumb: #c1c1c1;
  --scrollbar-track: transparent;
  --dialog-bg: var(--card-background-color);
  --input-border: var(--divider-color);
  --badge-bg: #e0e0e0;
  --badge-text: #333;
}

/* 深色主題覆寫 */
html[data-theme="dark"] {
  --user-bubble-bg: var(--primary-color);
  --user-bubble-text: #fff;
  --ai-bubble-bg: #2a2a2a;
  --ai-bubble-text: #e0e0e0;
  --sidebar-bg: #1a1a1a;
  --input-bg: #2a2a2a;
  --code-bg: #1e1e1e;
  --code-text: #d4d4d4;
  --hover-bg: rgba(255, 255, 255, 0.06);
  --shadow-color: rgba(0, 0, 0, 0.3);
  --scrollbar-thumb: #555;
  --scrollbar-track: #1a1a1a;
  --dialog-bg: #2a2a2a;
  --input-border: #444;
  --badge-bg: #444;
  --badge-text: #e0e0e0;
}
```

**重點**：HA 提供的核心變數（`--primary-color`、`--card-background-color` 等）會被 JS 從 parent 同步過來，所以 `html[data-theme="dark"]` 只需定義面板專屬的衍生色。

### Step 2: CSS — 更新元件引用新變數

掃描 `styles.css` 中所有硬編碼的顏色值，替換為 CSS 變數引用。主要涉及：

- Code block 背景/文字 → `var(--code-bg)` / `var(--code-text)`
- Hover 效果 → `var(--hover-bg)`
- 陰影 → `var(--shadow-color)`
- 滾動條 → `var(--scrollbar-thumb)` / `var(--scrollbar-track)`
- Dialog/Modal → `var(--dialog-bg)`
- Input border → `var(--input-border)`
- Badge → `var(--badge-bg)` / `var(--badge-text)`

### Step 3: JS — 主題同步邏輯

在 `app.js` 中新增 `ThemeSync` 模組：

```javascript
const ThemeSync = {
  /** 從 parent HA 同步的 CSS 變數清單 */
  HA_VARS: [
    '--primary-color',
    '--primary-text-color',
    '--secondary-text-color',
    '--text-primary-color',
    '--card-background-color',
    '--sidebar-background-color',
    '--divider-color',
    '--error-color',
    '--success-color',
  ],

  /** 初始化：同步一次 + 設定 MutationObserver */
  init() {
    this._syncTheme();
    this._observeParent();
  },

  /** 從 parent document 讀取 CSS 變數 + darkMode 並同步到 iframe */
  _syncTheme() {
    try {
      const parentDoc = window.parent?.document;
      if (!parentDoc) return;

      const parentStyle = window.parent.getComputedStyle(parentDoc.documentElement);

      // 同步 HA CSS 變數
      for (const v of this.HA_VARS) {
        const val = parentStyle.getPropertyValue(v).trim();
        if (val) {
          document.documentElement.style.setProperty(v, val);
        }
      }

      // 判斷深淺色模式
      const haEl = parentDoc.querySelector('home-assistant');
      const isDark = haEl?.hass?.themes?.darkMode ?? false;
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');

    } catch (e) {
      // cross-origin 或其他錯誤 — 保持預設淺色
      console.warn('ThemeSync: cannot access parent', e);
    }
  },

  /** 監聽 parent <html> style 屬性變化 */
  _observeParent() {
    try {
      const parentHtml = window.parent?.document?.documentElement;
      if (!parentHtml) return;

      const observer = new MutationObserver(() => this._syncTheme());
      observer.observe(parentHtml, {
        attributes: true,
        attributeFilter: ['style'],
      });
    } catch (e) {
      console.warn('ThemeSync: cannot observe parent', e);
    }
  },
};
```

在 `app.js` 的初始化流程中呼叫 `ThemeSync.init()`。

### Step 4: CSS — 特殊元件微調

以下元件在深色模式需要額外處理：

1. **Markdown code block** — `pre`/`code` 背景色
2. **Loading skeleton / spinner** — 動畫顏色
3. **Toast notification** — 確保深色背景上文字可讀
4. **Scrollbar** — WebKit 自訂滾動條顏色
5. **Input/Textarea focus ring** — 確保對比度

### Step 5: 測試驗證

新增測試項目到 `test_all.sh`（可選 — 建議手動驗證）：
- 確認 JS ThemeSync 初始化無 console error
- 切換 HA 主題後 iframe 內 `data-theme` 屬性正確更新
- 主要元件在深色模式下的可讀性

## 影響範圍

| 檔案 | 變更 |
|------|------|
| `frontend/styles.css` | 新增深色變數區塊 + 替換硬編碼顏色 |
| `frontend/app.js` | 新增 ThemeSync 模組 (~40 行) |
| `frontend/index.html` | 無變更 |
| `__init__.py` | 無變更 |

## 不做的事

- 面板不提供獨立主題切換 UI
- 不用 `@media (prefers-color-scheme)` — 只跟 HA
- 不用 localStorage 儲存主題偏好
- 不用 CSS `color-mix()` 動態計算顏色
