/* ===== HA MCP Client – Full SPA ===== */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────
  const API_BASE = "/api/ha_mcp_client";
  let AUTH_TOKEN = "";
  let _hassObj = null; // cached reference to parent hass object

  function _tryGetHassToken() {
    try {
      if (!_hassObj) {
        const haEl =
          window.parent &&
          window.parent.document &&
          window.parent.document.querySelector("home-assistant");
        if (haEl && haEl.hass) {
          _hassObj = haEl.hass;
        }
      }
      if (_hassObj && _hassObj.auth && _hassObj.auth.data) {
        return _hassObj.auth.data.access_token || "";
      }
    } catch (e) {
      // Cross-origin or no HA context
    }
    return "";
  }

  function _refreshToken() {
    var t = _tryGetHassToken();
    if (t) AUTH_TOKEN = t;
  }

  // Initial token acquisition
  AUTH_TOKEN = _tryGetHassToken();

  // Fallback: check localStorage (never use URL params for tokens)
  if (!AUTH_TOKEN) {
    AUTH_TOKEN = localStorage.getItem("ha_token") || "";
  }

  // ── State ───────────────────────────────────────────────
  let conversations = [];
  let currentConvId = null;
  let isSending = false;

  let currentMemSection = "soul";
  let memoryDirty = false;

  let skillsList = [];
  let editingSkillName = null; // null = new, string = editing existing

  let cronJobs = [];
  let editingCronId = null; // null = new, string = editing existing

  // ── DOM refs ────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // Chat DOM
  const sidebar = $("#sidebar");
  const convList = $("#conversation-list");
  const chatTitle = $("#chat-title");
  const messageList = $("#message-list");
  const welcomeScreen = $("#welcome-screen");
  const inputArea = $("#input-area");
  const messageInput = $("#message-input");
  const sendBtn = $("#send-btn");
  const renameBtn = $("#rename-btn");
  const deleteBtn = $("#delete-btn");

  // ── API helpers ─────────────────────────────────────────
  async function api(method, path, body) {
    // Refresh token from parent HA on every API call (tokens expire)
    _refreshToken();

    const opts = {
      method,
      headers: {
        "Content-Type": "application/json",
      },
    };
    if (AUTH_TOKEN) {
      opts.headers["Authorization"] = "Bearer " + AUTH_TOKEN;
    }
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error("API " + res.status + ": " + text);
    }
    return res.json();
  }

  // ── Toast ───────────────────────────────────────────────
  function showToast(msg, isError) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " toast-error" : "");
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
      el.classList.add("toast-fade");
      setTimeout(() => el.remove(), 300);
    }, 2700);
  }

  // ── Utilities ───────────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      const now = new Date();
      const diff = now - d;

      if (diff < 60000) return "剛才";
      if (diff < 3600000) return Math.floor(diff / 60000) + " 分鐘前";
      if (diff < 86400000) return Math.floor(diff / 3600000) + " 小時前";

      if (d.getFullYear() === now.getFullYear()) {
        return (d.getMonth() + 1) + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      }
      return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate();
    } catch (e) {
      return String(isoStr);
    }
  }

  function formatEpochMs(ms) {
    if (!ms) return "—";
    try {
      const d = new Date(ms);
      return d.getFullYear() + "/" + pad(d.getMonth() + 1) + "/" + pad(d.getDate()) +
        " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    } catch (e) {
      return "—";
    }
  }

  function pad(n) {
    return n < 10 ? "0" + n : "" + n;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messageList.scrollTop = messageList.scrollHeight;
    });
  }

  function autoResize() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
  }

  // ══════════════════════════════════════════════════════════
  //  TAB SWITCHING
  // ══════════════════════════════════════════════════════════
  function initTabs() {
    const tabBtns = $$(".tab-btn");
    tabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        // Update button active states
        tabBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        // Update panel visibility
        $$(".tab-panel").forEach((p) => p.classList.remove("active"));
        const panel = $("#panel-" + tab);
        if (panel) panel.classList.add("active");
        // Load data for the newly active tab
        onTabActivated(tab);
      });
    });
  }

  function onTabActivated(tab) {
    switch (tab) {
      case "chat":
        loadConversations();
        break;
      case "memory":
        loadMemorySection(currentMemSection);
        break;
      case "skills":
        loadSkills();
        break;
      case "cron":
        loadCronJobs();
        break;
      case "settings":
        loadSettings();
        break;
    }
  }

  // ══════════════════════════════════════════════════════════
  //  CHAT
  // ══════════════════════════════════════════════════════════

  // ── Conversations ─────────────────────────────────────────
  async function loadConversations() {
    try {
      conversations = await api("GET", "/conversations");
      renderConversationList();
    } catch (e) {
      showToast("載入對話列表失敗: " + e.message, true);
    }
  }

  function renderConversationList(filter) {
    convList.innerHTML = "";
    const term = (filter || "").toLowerCase();
    const filtered = term
      ? conversations.filter((c) => c.title.toLowerCase().includes(term))
      : conversations;

    if (filtered.length === 0) {
      convList.innerHTML =
        '<div style="padding:24px;text-align:center;color:var(--secondary-text-color)">沒有對話</div>';
      return;
    }

    for (const conv of filtered) {
      const el = document.createElement("div");
      el.className = "conversation-item" + (conv.id === currentConvId ? " active" : "");
      el.dataset.id = conv.id;

      const timeStr = formatTime(conv.updated_at);
      el.innerHTML =
        '<span class="mdi mdi-chat-outline conv-icon"></span>' +
        '<div class="conv-info">' +
          '<div class="conv-title">' + escapeHtml(conv.title) + '</div>' +
          '<div class="conv-time">' + timeStr + '</div>' +
        '</div>';
      el.addEventListener("click", () => selectConversation(conv.id));
      convList.appendChild(el);
    }
  }

  async function createConversation() {
    try {
      const conv = await api("POST", "/conversations", { title: "新對話" });
      conversations.unshift(conv);
      renderConversationList();
      selectConversation(conv.id);
      closeSidebarMobile();
    } catch (e) {
      showToast("建立對話失敗: " + e.message, true);
    }
  }

  async function selectConversation(id) {
    currentConvId = id;
    const conv = conversations.find((c) => c.id === id);
    if (!conv) return;

    chatTitle.textContent = conv.title;
    welcomeScreen.style.display = "none";
    inputArea.style.display = "block";
    renameBtn.style.display = "";
    deleteBtn.style.display = "";

    renderConversationList();

    try {
      const messages = await api("GET", "/conversations/" + id + "/messages");
      renderMessages(messages);
    } catch (e) {
      showToast("載入訊息失敗: " + e.message, true);
    }

    messageInput.focus();
    closeSidebarMobile();
  }

  // ── Messages ──────────────────────────────────────────────
  function renderMessages(messages) {
    messageList.innerHTML = "";

    if (messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "welcome-screen";
      empty.innerHTML =
        '<span class="mdi mdi-message-text-outline welcome-icon" style="font-size:48px"></span>' +
        '<p>開始對話吧！</p>';
      messageList.appendChild(empty);
      return;
    }

    for (const msg of messages) {
      appendMessage(msg);
    }
    scrollToBottom();
  }

  function appendMessage(msg) {
    const div = document.createElement("div");
    div.className = "message " + msg.role;

    var toolHtml = "";
    if (msg.tool_calls && msg.tool_calls.length > 0) {
      for (const tc of msg.tool_calls) {
        const name = typeof tc === "object" ? (tc.name || (tc.function && tc.function.name) || "tool") : tc;
        toolHtml +=
          '<div class="tool-badge" onclick="this.nextElementSibling.classList.toggle(\'open\')">' +
            '<span class="mdi mdi-wrench-outline"></span> ' + escapeHtml(name) +
          '</div>' +
          '<div class="tool-details">' + escapeHtml(JSON.stringify(tc, null, 2)) + '</div>';
      }
    }

    const time = msg.timestamp ? formatTime(msg.timestamp) : "";

    div.innerHTML =
      '<div>' +
        '<div class="message-bubble">' + escapeHtml(msg.content) + toolHtml + '</div>' +
        '<div class="message-time">' + time + '</div>' +
      '</div>';
    messageList.appendChild(div);
  }

  function showLoading() {
    const div = document.createElement("div");
    div.className = "loading-indicator";
    div.id = "loading";
    div.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    messageList.appendChild(div);
    scrollToBottom();
  }

  function hideLoading() {
    const el = document.getElementById("loading");
    if (el) el.remove();
  }

  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || !currentConvId || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    messageInput.value = "";
    autoResize();
    // Guard against IME compositionend restoring text after clear
    requestAnimationFrame(() => {
      if (isSending) messageInput.value = "";
    });

    appendMessage({ role: "user", content: text, timestamp: new Date().toISOString() });
    scrollToBottom();
    showLoading();

    try {
      const result = await api("POST", "/conversations/" + currentConvId + "/messages", {
        message: text,
      });

      hideLoading();

      if (result.ai_response) {
        appendMessage({
          role: "assistant",
          content: result.ai_response,
          tool_calls: result.tool_calls,
          timestamp: new Date().toISOString(),
        });
      }

      // Update conversation title in sidebar if it was default
      const conv = conversations.find((c) => c.id === currentConvId);
      if (conv && conv.title === "新對話") {
        conv.title = text.slice(0, 50);
        chatTitle.textContent = conv.title;
        renderConversationList();
      }

      // Move conversation to top
      const idx = conversations.findIndex((c) => c.id === currentConvId);
      if (idx > 0) {
        const moved = conversations.splice(idx, 1)[0];
        moved.updated_at = new Date().toISOString();
        conversations.unshift(moved);
        renderConversationList();
      }
    } catch (e) {
      hideLoading();
      showToast("送出失敗: " + e.message, true);
    } finally {
      isSending = false;
      sendBtn.disabled = !messageInput.value.trim();
      scrollToBottom();
    }
  }

  // ── Rename / Delete dialogs ───────────────────────────────
  function showRenameDialog() {
    const conv = conversations.find((c) => c.id === currentConvId);
    if (!conv) return;
    $("#rename-input").value = conv.title;
    $("#rename-dialog").style.display = "flex";
    $("#rename-input").focus();
  }

  async function confirmRename() {
    const newTitle = $("#rename-input").value.trim();
    if (!newTitle || !currentConvId) return;

    try {
      await api("PATCH", "/conversations/" + currentConvId, { title: newTitle });
      const conv = conversations.find((c) => c.id === currentConvId);
      if (conv) conv.title = newTitle;
      chatTitle.textContent = newTitle;
      renderConversationList();
      $("#rename-dialog").style.display = "none";
    } catch (e) {
      showToast("重新命名失敗: " + e.message, true);
    }
  }

  function showDeleteDialog() {
    if (!currentConvId) return;
    $("#delete-dialog").style.display = "flex";
  }

  async function confirmDelete() {
    if (!currentConvId) return;

    try {
      await api("DELETE", "/conversations/" + currentConvId);
      conversations = conversations.filter((c) => c.id !== currentConvId);
      currentConvId = null;
      chatTitle.textContent = "選擇或建立對話";
      messageList.innerHTML = "";
      messageList.appendChild(welcomeScreen);
      welcomeScreen.style.display = "flex";
      inputArea.style.display = "none";
      renameBtn.style.display = "none";
      deleteBtn.style.display = "none";
      renderConversationList();
      $("#delete-dialog").style.display = "none";
    } catch (e) {
      showToast("刪除失敗: " + e.message, true);
    }
  }

  // ── Sidebar toggle ────────────────────────────────────────
  function toggleSidebar() {
    sidebar.classList.toggle("open");
  }

  function closeSidebarMobile() {
    if (window.innerWidth < 768) {
      sidebar.classList.remove("open");
    }
  }

  // ══════════════════════════════════════════════════════════
  //  MEMORY
  // ══════════════════════════════════════════════════════════

  function initMemory() {
    // Sub-tab clicks
    $$(".sub-tab[data-mem]").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".sub-tab[data-mem]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentMemSection = btn.dataset.mem;
        loadMemorySection(currentMemSection);
      });
    });

    // Save button
    $("#memory-save-btn").addEventListener("click", saveMemory);
  }

  async function loadMemorySection(section) {
    const editor = $("#memory-editor");
    const saveBtn = $("#memory-save-btn");
    const status = $("#memory-status");

    editor.value = "";
    status.textContent = "載入中...";
    editor.disabled = true;

    try {
      const data = await api("GET", "/memory/" + section);
      editor.value = data.content || "";
      status.textContent = "";
      memoryDirty = false;

      // History is read-only
      if (section === "history") {
        editor.disabled = true;
        saveBtn.disabled = true;
        status.textContent = "唯讀 — 歷史記錄由系統自動管理";
      } else {
        editor.disabled = false;
        saveBtn.disabled = false;
      }
    } catch (e) {
      status.textContent = "";
      showToast("載入記憶失敗: " + e.message, true);
      editor.disabled = false;
      saveBtn.disabled = false;
    }
  }

  async function saveMemory() {
    if (currentMemSection === "history") return;

    const editor = $("#memory-editor");
    const status = $("#memory-status");
    const content = editor.value;

    status.textContent = "儲存中...";

    try {
      await api("PUT", "/memory/" + currentMemSection, { content: content });
      status.textContent = "已儲存";
      memoryDirty = false;
      showToast("記憶已儲存");
      setTimeout(() => {
        if (status.textContent === "已儲存") status.textContent = "";
      }, 3000);
    } catch (e) {
      status.textContent = "儲存失敗";
      showToast("儲存記憶失敗: " + e.message, true);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  SKILLS
  // ══════════════════════════════════════════════════════════

  function initSkills() {
    $("#skill-add-btn").addEventListener("click", () => openSkillEditor(null));
    $("#skill-cancel-btn").addEventListener("click", closeSkillEditor);
    $("#skill-save-btn").addEventListener("click", saveSkill);
  }

  async function loadSkills() {
    try {
      const data = await api("GET", "/skills");
      skillsList = data.skills || [];
      renderSkillsList();
    } catch (e) {
      showToast("載入技能列表失敗: " + e.message, true);
    }
  }

  function renderSkillsList() {
    const container = $("#skills-list");
    container.innerHTML = "";

    if (skillsList.length === 0) {
      container.innerHTML =
        '<div style="padding:24px;text-align:center;color:var(--secondary-text-color)">尚無技能，點擊「新增技能」開始</div>';
      return;
    }

    for (const skill of skillsList) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML =
        '<div class="card-body">' +
          '<div class="card-title">' + escapeHtml(skill.name) + '</div>' +
          '<div class="card-desc">' + escapeHtml(skill.description || "") + '</div>' +
        '</div>' +
        '<div class="card-actions">' +
          '<label class="toggle-label compact">' +
            '<input type="checkbox" class="skill-always-toggle" data-name="' + escapeHtml(skill.name) + '"' +
              (skill.always ? " checked" : "") + ' /> 常駐' +
          '</label>' +
          '<button class="btn-icon skill-edit-btn" data-name="' + escapeHtml(skill.name) + '" title="編輯">' +
            '<span class="mdi mdi-pencil-outline"></span>' +
          '</button>' +
          '<button class="btn-icon btn-danger skill-delete-btn" data-name="' + escapeHtml(skill.name) + '" title="刪除">' +
            '<span class="mdi mdi-delete-outline"></span>' +
          '</button>' +
        '</div>';
      container.appendChild(card);
    }

    // Bind events
    container.querySelectorAll(".skill-always-toggle").forEach((toggle) => {
      toggle.addEventListener("change", (e) => {
        toggleSkillAlways(e.target.dataset.name, e.target.checked);
      });
    });
    container.querySelectorAll(".skill-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => openSkillEditor(btn.dataset.name));
    });
    container.querySelectorAll(".skill-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteSkill(btn.dataset.name));
    });
  }

  async function toggleSkillAlways(name, always) {
    try {
      await api("PUT", "/skills/" + encodeURIComponent(name), { always: always });
      // Update local state
      const s = skillsList.find((sk) => sk.name === name);
      if (s) s.always = always;
      showToast(always ? "已設為常駐" : "已取消常駐");
    } catch (e) {
      showToast("更新技能失敗: " + e.message, true);
      loadSkills(); // reload to revert toggle
    }
  }

  async function openSkillEditor(name) {
    const panel = $("#skill-editor-panel");
    const nameInput = $("#skill-name-input");
    const descInput = $("#skill-desc-input");
    const editor = $("#skill-editor");
    const alwaysCheck = $("#skill-always-check");

    if (name) {
      // Editing existing skill
      editingSkillName = name;
      nameInput.value = name;
      nameInput.disabled = true;
      try {
        const data = await api("GET", "/skills/" + encodeURIComponent(name));
        descInput.value = (data.metadata && data.metadata.description) || data.description || "";
        editor.value = data.content || "";
        alwaysCheck.checked = (data.metadata && data.metadata.always) || data.always || false;
      } catch (e) {
        showToast("載入技能失敗: " + e.message, true);
        return;
      }
    } else {
      // New skill
      editingSkillName = null;
      nameInput.value = "";
      nameInput.disabled = false;
      descInput.value = "";
      editor.value = "";
      alwaysCheck.checked = false;
    }

    panel.style.display = "block";
    (name ? editor : nameInput).focus();
  }

  function closeSkillEditor() {
    $("#skill-editor-panel").style.display = "none";
    editingSkillName = null;
  }

  async function saveSkill() {
    const nameInput = $("#skill-name-input");
    const descInput = $("#skill-desc-input");
    const editor = $("#skill-editor");
    const alwaysCheck = $("#skill-always-check");

    const name = nameInput.value.trim();
    if (!name) {
      showToast("請輸入技能名稱", true);
      nameInput.focus();
      return;
    }

    const payload = {
      content: editor.value,
      description: descInput.value.trim(),
      always: alwaysCheck.checked,
    };

    try {
      if (editingSkillName) {
        // Update existing
        await api("PUT", "/skills/" + encodeURIComponent(editingSkillName), payload);
        showToast("技能已更新");
      } else {
        // Create new
        payload.name = name;
        await api("POST", "/skills", payload);
        showToast("技能已建立");
      }
      closeSkillEditor();
      loadSkills();
    } catch (e) {
      showToast("儲存技能失敗: " + e.message, true);
    }
  }

  async function deleteSkill(name) {
    if (!confirm("確定要刪除技能「" + name + "」嗎？")) return;

    try {
      await api("DELETE", "/skills/" + encodeURIComponent(name));
      showToast("技能已刪除");
      loadSkills();
    } catch (e) {
      showToast("刪除技能失敗: " + e.message, true);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  CRON
  // ══════════════════════════════════════════════════════════

  function initCron() {
    $("#cron-add-btn").addEventListener("click", () => openCronEditor(null));
    $("#cron-cancel-btn").addEventListener("click", closeCronEditor);
    $("#cron-save-btn").addEventListener("click", saveCronJob);

    // Kind selector toggles field visibility
    $("#cron-kind-select").addEventListener("change", updateCronKindFields);
  }

  function updateCronKindFields() {
    const kind = $("#cron-kind-select").value;

    // Every fields
    var showEvery = kind === "every";
    $("#cron-interval-label").style.display = showEvery ? "" : "none";
    $("#cron-interval-input").style.display = showEvery ? "" : "none";

    // Cron fields
    var showCron = kind === "cron";
    $("#cron-expr-label").style.display = showCron ? "" : "none";
    $("#cron-expr-input").style.display = showCron ? "" : "none";

    // At fields
    var showAt = kind === "at";
    $("#cron-at-label").style.display = showAt ? "" : "none";
    $("#cron-at-input").style.display = showAt ? "" : "none";
  }

  async function loadCronJobs() {
    try {
      const data = await api("GET", "/cron/jobs");
      cronJobs = data.jobs || [];
      renderCronList();
    } catch (e) {
      showToast("載入排程列表失敗: " + e.message, true);
    }
  }

  function renderCronList() {
    const container = $("#cron-list");
    container.innerHTML = "";

    if (cronJobs.length === 0) {
      container.innerHTML =
        '<div style="padding:24px;text-align:center;color:var(--secondary-text-color)">尚無排程，點擊「新增排程」開始</div>';
      return;
    }

    for (const job of cronJobs) {
      const card = document.createElement("div");
      card.className = "card";

      var scheduleDesc = "";
      if (job.schedule) {
        switch (job.schedule.kind) {
          case "every":
            var mins = Math.round((job.schedule.every_ms || 0) / 60000);
            scheduleDesc = "每 " + mins + " 分鐘";
            break;
          case "cron":
            scheduleDesc = "Cron: " + (job.schedule.cron || "—");
            break;
          case "at":
            scheduleDesc = "一次性: " + formatEpochMs(job.schedule.at_ms);
            break;
          default:
            scheduleDesc = job.schedule.kind || "—";
        }
      }

      var nextRunMs = job.state && job.state.next_run_at_ms;
      var nextRunStr = nextRunMs ? formatEpochMs(nextRunMs) : "—";

      card.innerHTML =
        '<div class="card-body">' +
          '<div class="card-title">' + escapeHtml(job.name || job.id) + '</div>' +
          '<div class="card-desc">' +
            '<span class="card-tag">' + escapeHtml(scheduleDesc) + '</span>' +
            ' <span class="card-meta">下次執行: ' + nextRunStr + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="card-actions">' +
          '<label class="toggle-label compact">' +
            '<input type="checkbox" class="cron-enabled-toggle" data-id="' + escapeHtml(job.id) + '"' +
              (job.enabled !== false ? " checked" : "") + ' /> 啟用' +
          '</label>' +
          '<button class="btn-icon cron-trigger-btn" data-id="' + escapeHtml(job.id) + '" title="立即觸發">' +
            '<span class="mdi mdi-play-outline"></span>' +
          '</button>' +
          '<button class="btn-icon cron-edit-btn" data-id="' + escapeHtml(job.id) + '" title="編輯">' +
            '<span class="mdi mdi-pencil-outline"></span>' +
          '</button>' +
          '<button class="btn-icon btn-danger cron-delete-btn" data-id="' + escapeHtml(job.id) + '" title="刪除">' +
            '<span class="mdi mdi-delete-outline"></span>' +
          '</button>' +
        '</div>';
      container.appendChild(card);
    }

    // Bind events
    container.querySelectorAll(".cron-enabled-toggle").forEach((toggle) => {
      toggle.addEventListener("change", (e) => {
        toggleCronEnabled(e.target.dataset.id, e.target.checked);
      });
    });
    container.querySelectorAll(".cron-trigger-btn").forEach((btn) => {
      btn.addEventListener("click", () => triggerCronJob(btn.dataset.id));
    });
    container.querySelectorAll(".cron-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => openCronEditor(btn.dataset.id));
    });
    container.querySelectorAll(".cron-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteCronJob(btn.dataset.id));
    });
  }

  async function toggleCronEnabled(id, enabled) {
    try {
      await api("PATCH", "/cron/jobs/" + encodeURIComponent(id), { enabled: enabled });
      var job = cronJobs.find((j) => j.id === id);
      if (job) job.enabled = enabled;
      showToast(enabled ? "排程已啟用" : "排程已停用");
    } catch (e) {
      showToast("更新排程失敗: " + e.message, true);
      loadCronJobs();
    }
  }

  async function triggerCronJob(id) {
    try {
      await api("POST", "/cron/jobs/" + encodeURIComponent(id) + "/trigger");
      showToast("排程已觸發");
    } catch (e) {
      showToast("觸發排程失敗: " + e.message, true);
    }
  }

  async function openCronEditor(id) {
    const panel = $("#cron-editor-panel");
    const nameInput = $("#cron-name-input");
    const kindSelect = $("#cron-kind-select");
    const intervalInput = $("#cron-interval-input");
    const exprInput = $("#cron-expr-input");
    const atInput = $("#cron-at-input");
    const tzInput = $("#cron-tz-input");
    const messageInput = $("#cron-message-input");
    const payloadKind = $("#cron-payload-kind");
    const deleteAfter = $("#cron-delete-after");

    if (id) {
      // Editing existing
      editingCronId = id;
      try {
        const job = await api("GET", "/cron/jobs/" + encodeURIComponent(id));
        nameInput.value = job.name || "";
        if (job.schedule) {
          kindSelect.value = job.schedule.kind || "every";
          if (job.schedule.kind === "every") {
            intervalInput.value = Math.round((job.schedule.every_ms || 0) / 60000);
          }
          if (job.schedule.kind === "cron") {
            exprInput.value = job.schedule.cron || "";
          }
          if (job.schedule.kind === "at" && job.schedule.at_ms) {
            // Convert epoch ms to datetime-local format
            var d = new Date(job.schedule.at_ms);
            atInput.value = toDatetimeLocal(d);
          }
          tzInput.value = job.schedule.tz || "Asia/Taipei";
        }
        if (job.payload) {
          messageInput.value = job.payload.message || "";
          payloadKind.value = job.payload.kind || "agent_turn";
        }
        deleteAfter.checked = !!job.delete_after_run;
      } catch (e) {
        showToast("載入排程失敗: " + e.message, true);
        return;
      }
    } else {
      // New
      editingCronId = null;
      nameInput.value = "";
      kindSelect.value = "every";
      intervalInput.value = "60";
      exprInput.value = "";
      atInput.value = "";
      tzInput.value = "Asia/Taipei";
      messageInput.value = "";
      payloadKind.value = "agent_turn";
      deleteAfter.checked = false;
    }

    updateCronKindFields();
    panel.style.display = "block";
    nameInput.focus();
  }

  function toDatetimeLocal(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function closeCronEditor() {
    $("#cron-editor-panel").style.display = "none";
    editingCronId = null;
  }

  async function saveCronJob() {
    const nameInput = $("#cron-name-input");
    const kindSelect = $("#cron-kind-select");
    const intervalInput = $("#cron-interval-input");
    const exprInput = $("#cron-expr-input");
    const atInput = $("#cron-at-input");
    const tzInput = $("#cron-tz-input");
    const msgInput = $("#cron-message-input");
    const payloadKind = $("#cron-payload-kind");
    const deleteAfter = $("#cron-delete-after");

    var name = nameInput.value.trim();
    if (!name) {
      showToast("請輸入排程名稱", true);
      nameInput.focus();
      return;
    }

    // Build schedule
    var kind = kindSelect.value;
    var schedule = { kind: kind, tz: tzInput.value.trim() || "Asia/Taipei" };

    if (kind === "every") {
      var mins = parseInt(intervalInput.value, 10);
      if (!mins || mins < 1) {
        showToast("間隔至少 1 分鐘", true);
        intervalInput.focus();
        return;
      }
      schedule.every_ms = mins * 60000;
    } else if (kind === "cron") {
      var expr = exprInput.value.trim();
      if (!expr) {
        showToast("請輸入 Cron 表達式", true);
        exprInput.focus();
        return;
      }
      schedule.cron = expr;
    } else if (kind === "at") {
      var atVal = atInput.value;
      if (!atVal) {
        showToast("請選擇執行時間", true);
        atInput.focus();
        return;
      }
      schedule.at_ms = new Date(atVal).getTime();
    }

    var payload = {
      kind: payloadKind.value,
      message: msgInput.value.trim(),
    };

    var body = {
      name: name,
      schedule: schedule,
      payload: payload,
      enabled: true,
      delete_after_run: deleteAfter.checked,
    };

    try {
      if (editingCronId) {
        await api("PATCH", "/cron/jobs/" + encodeURIComponent(editingCronId), body);
        showToast("排程已更新");
      } else {
        await api("POST", "/cron/jobs", body);
        showToast("排程已建立");
      }
      closeCronEditor();
      loadCronJobs();
    } catch (e) {
      showToast("儲存排程失敗: " + e.message, true);
    }
  }

  async function deleteCronJob(id) {
    if (!confirm("確定要刪除此排程嗎？")) return;

    try {
      await api("DELETE", "/cron/jobs/" + encodeURIComponent(id));
      showToast("排程已刪除");
      loadCronJobs();
    } catch (e) {
      showToast("刪除排程失敗: " + e.message, true);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  SETTINGS
  // ══════════════════════════════════════════════════════════

  function initSettings() {
    // Temperature slider sync
    var tempSlider = $("#set-temperature");
    var tempValue = $("#set-temp-value");
    tempSlider.addEventListener("input", () => {
      tempValue.textContent = tempSlider.value;
    });

    // Save button
    $("#settings-save-btn").addEventListener("click", saveSettings);
  }

  async function loadSettings() {
    var status = $("#settings-status");
    status.textContent = "載入中...";

    try {
      var data = await api("GET", "/settings");
      $("#set-ai-service").value = data.ai_service || "";
      $("#set-model").value = data.model || "";
      $("#set-temperature").value = data.temperature != null ? data.temperature : 0.7;
      $("#set-temp-value").textContent = data.temperature != null ? data.temperature : 0.7;
      $("#set-max-tokens").value = data.max_tokens || 4096;
      $("#set-max-tool-calls").value = data.max_tool_calls || 10;
      $("#set-memory-window").value = data.memory_window || 50;
      $("#set-system-prompt").value = data.system_prompt || "";
      status.textContent = "";
    } catch (e) {
      status.textContent = "";
      showToast("載入設定失敗: " + e.message, true);
    }
  }

  async function saveSettings() {
    var status = $("#settings-status");
    status.textContent = "儲存中...";

    var payload = {
      model: $("#set-model").value.trim(),
      temperature: parseFloat($("#set-temperature").value),
      max_tokens: parseInt($("#set-max-tokens").value, 10),
      max_tool_calls: parseInt($("#set-max-tool-calls").value, 10),
      memory_window: parseInt($("#set-memory-window").value, 10),
      system_prompt: $("#set-system-prompt").value,
    };

    try {
      await api("PATCH", "/settings", payload);
      status.textContent = "已套用";
      showToast("設定已儲存");
      setTimeout(() => {
        if (status.textContent === "已套用") status.textContent = "";
      }, 3000);
    } catch (e) {
      status.textContent = "儲存失敗";
      showToast("儲存設定失敗: " + e.message, true);
    }
  }

  // ══════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════

  function init() {
    // ── Tab system ──────────────────────────────────────────
    initTabs();

    // ── Chat bindings ───────────────────────────────────────
    $("#new-chat-btn").addEventListener("click", createConversation);
    $("#sidebar-toggle-btn").addEventListener("click", toggleSidebar);
    $("#sidebar-close-btn").addEventListener("click", () => sidebar.classList.remove("open"));

    // Search
    $("#search-input").addEventListener("input", (e) => {
      renderConversationList(e.target.value);
    });

    // Send message
    sendBtn.addEventListener("click", sendMessage);
    messageInput.addEventListener("input", () => {
      autoResize();
      sendBtn.disabled = !messageInput.value.trim();
    });
    messageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Rename
    renameBtn.addEventListener("click", showRenameDialog);
    $("#rename-cancel").addEventListener("click", () => {
      $("#rename-dialog").style.display = "none";
    });
    $("#rename-confirm").addEventListener("click", confirmRename);
    $("#rename-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") confirmRename();
    });

    // Delete
    deleteBtn.addEventListener("click", showDeleteDialog);
    $("#delete-cancel").addEventListener("click", () => {
      $("#delete-dialog").style.display = "none";
    });
    $("#delete-confirm").addEventListener("click", confirmDelete);

    // Close dialogs on overlay click
    document.querySelectorAll(".dialog-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.style.display = "none";
      });
    });

    // ── Memory bindings ─────────────────────────────────────
    initMemory();

    // ── Skills bindings ─────────────────────────────────────
    initSkills();

    // ── Cron bindings ───────────────────────────────────────
    initCron();

    // ── Settings bindings ───────────────────────────────────
    initSettings();

    // ── Auth: retry getting HA token (parent may load late) ─
    if (!AUTH_TOKEN) {
      var retries = 0;
      var authInterval = setInterval(function () {
        _refreshToken();
        retries++;
        if (AUTH_TOKEN || retries >= 20) {
          clearInterval(authInterval);
          if (!AUTH_TOKEN) {
            // Last resort: prompt for long-lived token
            var token = prompt("請輸入 Home Assistant Long-Lived Access Token:");
            if (token) {
              AUTH_TOKEN = token;
              localStorage.setItem("ha_token", token);
            }
          }
          loadConversations();
        }
      }, 250);
    } else {
      // ── Initial load (chat is the default active tab) ─────
      loadConversations();
    }
  }

  // Boot
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
