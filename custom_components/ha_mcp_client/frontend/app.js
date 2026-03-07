/* ===== HA MCP Client – Chat Panel ===== */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────
  const API_BASE = "/api/ha_mcp_client";
  let AUTH_TOKEN = "";

  // Try to get token from parent window (iframe in HA)
  try {
    const hassAuth =
      window.parent &&
      window.parent.document.querySelector("home-assistant") &&
      window.parent.document.querySelector("home-assistant").hass;
    if (hassAuth && hassAuth.auth && hassAuth.auth.data) {
      AUTH_TOKEN = hassAuth.auth.data.access_token;
    }
  } catch (e) {
    // Cross-origin or no HA context — will prompt for token
  }

  // Fallback: check URL params or localStorage
  if (!AUTH_TOKEN) {
    const params = new URLSearchParams(window.location.search);
    AUTH_TOKEN = params.get("token") || localStorage.getItem("ha_token") || "";
  }

  // ── State ───────────────────────────────────────────────
  let conversations = [];
  let currentConvId = null;
  let isSending = false;

  // ── DOM refs ────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
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
    const opts = {
      method,
      headers: {
        "Content-Type": "application/json",
      },
    };
    if (AUTH_TOKEN) {
      opts.headers["Authorization"] = "Bearer " + AUTH_TOKEN;
    }
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API ${res.status}: ${text}`);
    }
    return res.json();
  }

  // ── Toast ───────────────────────────────────────────────
  function showToast(msg) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }

  // ── Conversations ───────────────────────────────────────
  async function loadConversations() {
    try {
      conversations = await api("GET", "/conversations");
      renderConversationList();
    } catch (e) {
      showToast("載入對話列表失敗: " + e.message);
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
      el.innerHTML = `
        <span class="mdi mdi-chat-outline conv-icon"></span>
        <div class="conv-info">
          <div class="conv-title">${escapeHtml(conv.title)}</div>
          <div class="conv-time">${timeStr}</div>
        </div>
      `;
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
      showToast("建立對話失敗: " + e.message);
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

    renderConversationList(); // Update active state

    // Load messages
    try {
      const messages = await api("GET", `/conversations/${id}/messages`);
      renderMessages(messages);
    } catch (e) {
      showToast("載入訊息失敗: " + e.message);
    }

    messageInput.focus();
    closeSidebarMobile();
  }

  // ── Messages ────────────────────────────────────────────
  function renderMessages(messages) {
    // Clear everything except welcome screen
    messageList.innerHTML = "";

    if (messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "welcome-screen";
      empty.innerHTML = `
        <span class="mdi mdi-message-text-outline welcome-icon" style="font-size:48px"></span>
        <p>開始對話吧！</p>
      `;
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

    let toolHtml = "";
    if (msg.tool_calls && msg.tool_calls.length > 0) {
      for (const tc of msg.tool_calls) {
        const name = typeof tc === "object" ? tc.name || tc.function?.name || "tool" : tc;
        toolHtml += `
          <div class="tool-badge" onclick="this.nextElementSibling.classList.toggle('open')">
            <span class="mdi mdi-wrench-outline"></span> ${escapeHtml(name)}
          </div>
          <div class="tool-details">${escapeHtml(JSON.stringify(tc, null, 2))}</div>
        `;
      }
    }

    const time = msg.timestamp ? formatTime(msg.timestamp) : "";

    div.innerHTML = `
      <div>
        <div class="message-bubble">${escapeHtml(msg.content)}${toolHtml}</div>
        <div class="message-time">${time}</div>
      </div>
    `;
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

    // Show user message immediately
    appendMessage({ role: "user", content: text, timestamp: new Date().toISOString() });
    scrollToBottom();
    showLoading();

    try {
      const result = await api("POST", `/conversations/${currentConvId}/messages`, {
        message: text,
      });

      hideLoading();

      // Show AI response
      if (result.ai_response) {
        appendMessage({
          role: "assistant",
          content: result.ai_response,
          timestamp: new Date().toISOString(),
        });
      }

      // Update conversation title in sidebar if it changed
      const conv = conversations.find((c) => c.id === currentConvId);
      if (conv && conv.title === "新對話") {
        conv.title = text.slice(0, 50);
        chatTitle.textContent = conv.title;
        renderConversationList();
      }

      // Move conversation to top of list
      const idx = conversations.findIndex((c) => c.id === currentConvId);
      if (idx > 0) {
        const [c] = conversations.splice(idx, 1);
        c.updated_at = new Date().toISOString();
        conversations.unshift(c);
        renderConversationList();
      }
    } catch (e) {
      hideLoading();
      showToast("送出失敗: " + e.message);
    } finally {
      isSending = false;
      sendBtn.disabled = !messageInput.value.trim();
      scrollToBottom();
    }
  }

  // ── Rename / Delete ─────────────────────────────────────
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
      await api("PATCH", `/conversations/${currentConvId}`, { title: newTitle });
      const conv = conversations.find((c) => c.id === currentConvId);
      if (conv) conv.title = newTitle;
      chatTitle.textContent = newTitle;
      renderConversationList();
      $("#rename-dialog").style.display = "none";
    } catch (e) {
      showToast("重新命名失敗: " + e.message);
    }
  }

  function showDeleteDialog() {
    if (!currentConvId) return;
    $("#delete-dialog").style.display = "flex";
  }

  async function confirmDelete() {
    if (!currentConvId) return;

    try {
      await api("DELETE", `/conversations/${currentConvId}`);
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
      showToast("刪除失敗: " + e.message);
    }
  }

  // ── Sidebar toggle ──────────────────────────────────────
  function toggleSidebar() {
    sidebar.classList.toggle("open");
  }

  function closeSidebarMobile() {
    if (window.innerWidth < 768) {
      sidebar.classList.remove("open");
    }
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

      // Same year: show MM/DD HH:mm
      if (d.getFullYear() === now.getFullYear()) {
        return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
      }
      return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
    } catch {
      return isoStr;
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

  // ── Event Bindings ──────────────────────────────────────
  function init() {
    // Sidebar
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
      if (e.key === "Enter" && !e.shiftKey) {
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
    for (const overlay of document.querySelectorAll(".dialog-overlay")) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.style.display = "none";
      });
    }

    // If no auth token, prompt
    if (!AUTH_TOKEN) {
      const token = prompt("請輸入 Home Assistant Long-Lived Access Token:");
      if (token) {
        AUTH_TOKEN = token;
        localStorage.setItem("ha_token", token);
      }
    }

    // Initial load
    loadConversations();
  }

  // Boot
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
