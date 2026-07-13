/* ===== HA MCP Client – Chat Panel (n8n webhook mode) ===== */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────
  const API_BASE = "/api/ha_mcp_client";
  let AUTH_TOKEN = "";
  let _hassObj = null;

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

  AUTH_TOKEN = _tryGetHassToken();
  if (!AUTH_TOKEN) {
    AUTH_TOKEN = localStorage.getItem("ha_token") || "";
  }

  // ── ThemeSync — follow HA dark/light theme ─────────────
  const ThemeSync = {
    HA_VARS: [
      "--primary-color",
      "--primary-text-color",
      "--secondary-text-color",
      "--text-primary-color",
      "--card-background-color",
      "--sidebar-background-color",
      "--divider-color",
      "--error-color",
      "--success-color",
    ],
    _prevDark: null,
    init: function () {
      this._syncTheme();
      this._observeParent();
    },
    _syncTheme: function () {
      try {
        var parentDoc = window.parent && window.parent.document;
        if (!parentDoc) return;
        var parentStyle = window.parent.getComputedStyle(parentDoc.documentElement);
        var root = document.documentElement;
        for (var i = 0; i < this.HA_VARS.length; i++) {
          var val = parentStyle.getPropertyValue(this.HA_VARS[i]).trim();
          if (val) root.style.setProperty(this.HA_VARS[i], val);
        }
        var rgbPrimary = parentStyle.getPropertyValue("--rgb-primary-color").trim();
        if (rgbPrimary) root.style.setProperty("--rgb-primary-color", rgbPrimary);
        var isDark = false;
        var haEl = parentDoc.querySelector("home-assistant");
        if (haEl && haEl.hass && haEl.hass.themes) {
          isDark = !!haEl.hass.themes.darkMode;
        } else {
          var bg = parentStyle.getPropertyValue("--card-background-color").trim();
          if (bg) isDark = this._isColorDark(bg);
        }
        root.setAttribute("data-theme", isDark ? "dark" : "light");
        if (this._prevDark !== isDark) {
          this._prevDark = isDark;
          root.style.colorScheme = isDark ? "dark" : "light";
        }
      } catch (e) {}
    },
    _observeParent: function () {
      var self = this;
      try {
        var parentHtml = window.parent && window.parent.document && window.parent.document.documentElement;
        if (!parentHtml) return;
        var observer = new MutationObserver(function () { self._syncTheme(); });
        observer.observe(parentHtml, { attributes: true, attributeFilter: ["style", "class"] });
        var haEl = window.parent.document.querySelector("home-assistant");
        if (haEl) {
          var haObs = new MutationObserver(function () { self._syncTheme(); });
          haObs.observe(haEl, { attributes: true, attributeFilter: ["style", "class"] });
        }
      } catch (e) {
        setInterval(function () { self._syncTheme(); }, 2000);
      }
    },
    _isColorDark: function (color) {
      var m = color.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
      if (m) return parseInt(m[1], 16) * 0.299 + parseInt(m[2], 16) * 0.587 + parseInt(m[3], 16) * 0.114 < 128;
      m = color.match(/rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
      if (m) return parseInt(m[1]) * 0.299 + parseInt(m[2]) * 0.587 + parseInt(m[3]) * 0.114 < 128;
      return false;
    },
  };

  // ── State ───────────────────────────────────────────────
  let conversations = [];
  let currentConvId = null;
  let isSending = false;

  // ── DOM refs ──────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

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

  // ── API helper (JSON) ─────────────────────────────────────
  async function api(method, path, body) {
    _refreshToken();
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (AUTH_TOKEN) opts.headers["Authorization"] = "Bearer " + AUTH_TOKEN;
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) {
      const text = await res.text();
      throw new Error("API " + res.status + ": " + text);
    }
    return res.json();
  }

  // ── Toast ──────────────────────────────────────────────────
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

  // ── Utilities ──────────────────────────────────────────────
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
      if (diff < 60000) return "\u525b\u624d";
      if (diff < 3600000) return Math.floor(diff / 60000) + " \u5206\u9418\u524d";
      if (diff < 86400000) return Math.floor(diff / 3600000) + " \u5c0f\u6642\u524d";
      if (d.getFullYear() === now.getFullYear()) {
        return (d.getMonth() + 1) + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      }
      return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate();
    } catch (e) { return String(isoStr); }
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function scrollToBottom() {
    requestAnimationFrame(() => { messageList.scrollTop = messageList.scrollHeight; });
  }

  function autoResize() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
  }

  // ══════════════════════════════════════════════════════════
  //  CONVERSATIONS
  // ══════════════════════════════════════════════════════════

  async function loadConversations() {
    try {
      conversations = await api("GET", "/conversations");
      renderConversationList();
      if (currentConvId && conversations.find((c) => c.id === currentConvId)) {
        selectConversation(currentConvId);
      }
    } catch (e) {
      showToast("\u8f09\u5165\u5c0d\u8a71\u5217\u8868\u5931\u6557: " + e.message, true);
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
        '<div style="padding:24px;text-align:center;color:var(--secondary-text-color)">\u6c92\u6709\u5c0d\u8a71</div>';
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
      const conv = await api("POST", "/conversations", { title: "\u65b0\u5c0d\u8a71" });
      conversations.unshift(conv);
      renderConversationList();
      selectConversation(conv.id);
      closeSidebarMobile();
    } catch (e) {
      showToast("\u5efa\u7acb\u5c0d\u8a71\u5931\u6557: " + e.message, true);
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
      showToast("\u8f09\u5165\u8a0a\u606f\u5931\u6557: " + e.message, true);
    }

    messageInput.focus();
    closeSidebarMobile();
  }

  // ══════════════════════════════════════════════════════════
  //  MESSAGES (streaming)
  // ══════════════════════════════════════════════════════════

  function renderMessages(messages) {
    messageList.innerHTML = "";
    if (messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "welcome-screen";
      empty.innerHTML =
        '<span class="mdi mdi-message-text-outline welcome-icon" style="font-size:48px"></span>' +
        '<p>\u958b\u59cb\u5c0d\u8a71\u5427\uff01</p>';
      messageList.appendChild(empty);
      return;
    }
    for (const msg of messages) appendMessage(msg);
    scrollToBottom();
  }

  function appendMessage(msg) {
    const div = document.createElement("div");
    div.className = "message " + msg.role;
    const time = msg.timestamp ? formatTime(msg.timestamp) : "";
    div.innerHTML =
      '<div>' +
        '<div class="message-bubble">' + escapeHtml(msg.content) + '</div>' +
        '<div class="message-time">' + time + '</div>' +
      '</div>';
    messageList.appendChild(div);
  }

  /** Create an empty assistant bubble and return its .message-bubble element. */
  function createStreamingBubble() {
    const div = document.createElement("div");
    div.className = "message assistant";
    div.innerHTML =
      '<div>' +
        '<div class="message-bubble streaming"></div>' +
        '<div class="message-time"></div>' +
      '</div>';
    messageList.appendChild(div);
    return div.querySelector(".message-bubble");
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
    requestAnimationFrame(() => { if (isSending) messageInput.value = ""; });

    // Show user bubble
    appendMessage({ role: "user", content: text, timestamp: new Date().toISOString() });
    scrollToBottom();
    showLoading();

    try {
      _refreshToken();
      const url = API_BASE + "/conversations/" + currentConvId + "/messages";
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(AUTH_TOKEN ? { Authorization: "Bearer " + AUTH_TOKEN } : {}),
        },
        body: JSON.stringify({ message: text }),
      });

      if (!res.ok) {
        hideLoading();
        const errText = await res.text();
        throw new Error("API " + res.status + ": " + errText);
      }

      const result = await res.json();
      hideLoading();

      if (result.ai_response) {
        appendMessage({ role: "assistant", content: result.ai_response, timestamp: new Date().toISOString() });
      }

      // Update conversation title if default
      const conv = conversations.find((c) => c.id === currentConvId);
      if (conv && conv.title === "\u65b0\u5c0d\u8a71") {
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
      showToast("\u9001\u51fa\u5931\u6557: " + e.message, true);
    } finally {
      isSending = false;
      sendBtn.disabled = !messageInput.value.trim();
      scrollToBottom();
    }
  }

  // ── Rename / Delete dialogs ─────────────────────────────────
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
      showToast("\u91cd\u65b0\u547d\u540d\u5931\u6557: " + e.message, true);
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
      chatTitle.textContent = "\u9078\u64c7\u6216\u5efa\u7acb\u5c0d\u8a71";
      messageList.innerHTML = "";
      messageList.appendChild(welcomeScreen);
      welcomeScreen.style.display = "flex";
      inputArea.style.display = "none";
      renameBtn.style.display = "none";
      deleteBtn.style.display = "none";
      renderConversationList();
      $("#delete-dialog").style.display = "none";
    } catch (e) {
      showToast("\u522a\u9664\u5931\u6557: " + e.message, true);
    }
  }

  // ── Sidebar toggle ─────────────────────────────────────────
  function toggleSidebar() { sidebar.classList.toggle("open"); }
  function closeSidebarMobile() {
    if (window.innerWidth < 768) sidebar.classList.remove("open");
  }

  // ══════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════

  function init() {
    ThemeSync.init();

    // Chat bindings
    $("#new-chat-btn").addEventListener("click", createConversation);
    $("#sidebar-toggle-btn").addEventListener("click", toggleSidebar);
    $("#sidebar-close-btn").addEventListener("click", () => sidebar.classList.remove("open"));

    $("#search-input").addEventListener("input", (e) => {
      renderConversationList(e.target.value);
    });

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
    $("#rename-cancel").addEventListener("click", () => { $("#rename-dialog").style.display = "none"; });
    $("#rename-confirm").addEventListener("click", confirmRename);
    $("#rename-input").addEventListener("keydown", (e) => { if (e.key === "Enter") confirmRename(); });

    // Delete
    deleteBtn.addEventListener("click", showDeleteDialog);
    $("#delete-cancel").addEventListener("click", () => { $("#delete-dialog").style.display = "none"; });
    $("#delete-confirm").addEventListener("click", confirmDelete);

    // Close dialogs on overlay click
    document.querySelectorAll(".dialog-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.style.display = "none";
      });
    });

    // Auth: retry getting HA token (parent may load late)
    if (!AUTH_TOKEN) {
      var retries = 0;
      var authInterval = setInterval(function () {
        _refreshToken();
        retries++;
        if (AUTH_TOKEN || retries >= 20) {
          clearInterval(authInterval);
          if (!AUTH_TOKEN) {
            var token = prompt("\u8acb\u8f38\u5165 Home Assistant Long-Lived Access Token:");
            if (token) {
              AUTH_TOKEN = token;
              localStorage.setItem("ha_token", token);
            }
          }
          loadConversations();
        }
      }, 250);
    } else {
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
