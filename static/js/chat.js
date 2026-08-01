const AI_SPEAK_KEY = "zenith_ai_speak";
const CHAT_COLLAPSED_KEY = "zenith_chat_collapsed";

let recognition = null;
let isListening = false;
let chatBusy = false;
let applyBusy = false;

function i18n(key, vars) {
  if (typeof window.__ === "function") return window.__(key, vars);
  return key;
}

function chatEls() {
  return {
    sendBtn: document.getElementById("chat-send"),
    input: document.getElementById("chat-input"),
    messages: document.getElementById("chat-messages"),
    micBtn: document.getElementById("chat-mic"),
    speakToggle: document.getElementById("chat-speak-toggle"),
  };
}

function getDealerId() {
  const { sendBtn } = chatEls();
  return String(window.__dealerId || sendBtn?.dataset.dealer || "");
}

function appendReviewerActions(el, m, reviewIndex) {
  if (m.applied) {
    const applied = document.createElement("div");
    applied.className = "chat-reviewer-applied";
    applied.textContent = i18n("reviewer_applied");
    el.appendChild(applied);
    return;
  }
  if (m.verdict !== "suggest_changes") return;

  const actions = document.createElement("div");
  actions.className = "chat-reviewer-actions";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-secondary btn-sm apply-reviewer-btn";
  btn.textContent = i18n("apply_reviewer_suggestions");
  btn.dataset.reviewIndex = String(reviewIndex);
  btn.addEventListener("click", () => applyReviewerSuggestions(reviewIndex));
  actions.appendChild(btn);
  el.appendChild(actions);
}

function appendChatMsg(role, text, meta) {
  const { messages } = chatEls();
  if (!messages) return null;
  messages.querySelector(".chat-welcome")?.remove();
  const el = document.createElement("div");
  el.className = `chat-msg chat-${role}`;
  if (role === "reviewer") {
    const label = document.createElement("div");
    label.className = "chat-reviewer-label";
    label.textContent = i18n("reviewer_label");
    el.appendChild(label);
    const body = document.createElement("div");
    body.className = "chat-reviewer-body";
    body.textContent = text || "";
    el.appendChild(body);
    if (meta) {
      appendReviewerActions(el, meta, meta.reviewIndex ?? -1);
    }
  } else {
    el.textContent = text || "";
  }
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

function renderChatHistory(history) {
  const { messages } = chatEls();
  if (!messages || !Array.isArray(history)) return;
  messages.innerHTML = "";
  if (!history.length) {
    const welcome = document.createElement("p");
    welcome.className = "chat-welcome";
    welcome.textContent = i18n("chat_welcome");
    messages.appendChild(welcome);
    return;
  }
  history.forEach((m, index) => {
    const role = m.role || "assistant";
    if (role === "reviewer") {
      appendChatMsg(role, m.content || "", { ...m, reviewIndex: index });
    } else {
      appendChatMsg(role, m.content || "");
    }
  });
  bindApplyReviewerButtons();
}

async function applyReviewerSuggestions(reviewIndex) {
  if (applyBusy) return;
  const dealerId = getDealerId();
  if (!dealerId) return;

  applyBusy = true;
  const thinking = appendChatMsg("assistant", i18n("js_reviewer_applying"));
  thinking?.classList.add("chat-thinking");

  try {
    const res = await fetch(`/api/bundling/${dealerId}/review/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(reviewIndex >= 0 ? { review_index: reviewIndex } : {}),
    });
    thinking?.remove();

    const data = await res.json();
    if (!res.ok) {
      appendChatMsg("assistant", data.summary || data.error || i18n("js_server_error", { status: res.status }));
      return;
    }

    if (data.chat_history) {
      renderChatHistory(data.chat_history);
    } else if (data.summary) {
      appendChatMsg("assistant", data.summary);
    }

    if (data.bundles?.length && window.renderBundles) {
      window.renderBundles(data.bundles, data.validation_issues);
      document.getElementById("bundle-proposals")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    thinking?.remove();
    appendChatMsg("assistant", i18n("js_unreachable"));
  } finally {
    applyBusy = false;
  }
}

window.appendChatMsg = appendChatMsg;
window.renderChatHistory = renderChatHistory;
window.applyReviewerSuggestions = applyReviewerSuggestions;

async function sendChat() {
  if (chatBusy) return;

  const { input, sendBtn } = chatEls();
  const dealerId = getDealerId();
  const text = (input?.value || "").trim();

  if (!text) return;
  if (!dealerId) {
    appendChatMsg("assistant", i18n("js_chat_init_failed"));
    return;
  }

  chatBusy = true;
  appendChatMsg("user", text);
  if (input) input.value = "";
  if (sendBtn) sendBtn.disabled = true;

  const thinking = appendChatMsg("assistant", i18n("js_thinking"));
  thinking?.classList.add("chat-thinking");

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    const res = await fetch(`/api/chat/bundling/${dealerId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ message: text }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    thinking?.remove();

    const ctype = res.headers.get("content-type") || "";
    if (!ctype.includes("application/json")) {
      appendChatMsg("assistant", i18n("js_server_error", { status: res.status }));
      return;
    }

    const data = await res.json();
    if (res.status === 401) {
      appendChatMsg("assistant", data.reply || i18n("js_session_expired"));
      return;
    }

    const reply = (data.reply || data.error || "").trim() || i18n("js_empty_reply");
    appendChatMsg("assistant", reply);
    window.zenithAfterReply?.(reply);

    if ((data.bundling_complete || data.bundles?.length) && window.renderBundles) {
      window.renderBundles(data.bundles, data.validation_issues);
      document.getElementById("bundle-proposals")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    thinking?.remove();
    if (err?.name === "AbortError") {
      appendChatMsg("assistant", i18n("js_timeout"));
    } else {
      appendChatMsg("assistant", i18n("js_unreachable"));
    }
  } finally {
    chatBusy = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}

window.zenithSendChat = sendChat;

function isAiSpeakEnabled() {
  try {
    return localStorage.getItem(AI_SPEAK_KEY) === "1";
  } catch (e) {
    return false;
  }
}

function speakReply(text) {
  if (!isAiSpeakEnabled() || !text || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = window.__speechLang || "en-LK";
  window.speechSynthesis.speak(utterance);
}

window.zenithAfterReply = speakReply;

function initAiSpeak() {
  const toggle = document.getElementById("chat-speak-toggle");
  if (!toggle) return;
  toggle.checked = isAiSpeakEnabled();
  toggle.addEventListener("change", () => {
    try {
      localStorage.setItem(AI_SPEAK_KEY, toggle.checked ? "1" : "0");
    } catch (e) {
      /* ignore */
    }
  });
}

function initVoiceInput() {
  const micBtn = document.getElementById("chat-mic");
  const input = document.getElementById("chat-input");
  if (!micBtn || !input) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.title = i18n("js_voice_unsupported");
    micBtn.disabled = true;
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = window.__speechLang || "en-LK";

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add("listening");
    micBtn.title = i18n("js_voice_listening");
  };

  recognition.onend = () => {
    isListening = false;
    micBtn.classList.remove("listening");
    micBtn.title = i18n("voice_input");
  };

  recognition.onerror = () => {
    appendChatMsg("assistant", i18n("js_voice_failed"));
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    input.value = (input.value ? `${input.value} ` : "") + transcript;
  };

  micBtn.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      return;
    }
    try {
      recognition.start();
    } catch (e) {
      appendChatMsg("assistant", i18n("js_voice_start_failed"));
    }
  });
}

async function resetChat() {
  const dealerId = getDealerId();
  if (!dealerId) return;
  try {
    await fetch(`/api/chat/bundling/${dealerId}/reset`, { method: "POST", credentials: "same-origin" });
    const { messages } = chatEls();
    if (messages) {
      messages.innerHTML = `<p class="chat-welcome">${i18n("chat_welcome")}</p>`;
    }
  } catch (e) {
    /* ignore */
  }
}

function bindChatControls() {
  const { input, sendBtn } = chatEls();
  if (sendBtn && !sendBtn.dataset.chatBound) {
    sendBtn.dataset.chatBound = "1";
    sendBtn.addEventListener("click", (e) => {
      e.preventDefault();
      sendChat();
    });
  }
  if (input && !input.dataset.chatBound) {
    input.dataset.chatBound = "1";
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendChat();
      }
    });
  }
  document.getElementById("chat-reset")?.addEventListener("click", resetChat);
}

function setChatCollapsed(collapsed) {
  const layout = document.getElementById("cheques-layout");
  const expandBtn = document.getElementById("chat-expand-btn");
  if (!layout) return;

  layout.classList.toggle("chat-collapsed", collapsed);
  if (expandBtn) expandBtn.hidden = !collapsed;

  try {
    localStorage.setItem(CHAT_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch (e) {
    /* ignore */
  }
}

function initChatCollapse() {
  const layout = document.getElementById("cheques-layout");
  if (!layout) return;

  let collapsed = false;
  try {
    collapsed = localStorage.getItem(CHAT_COLLAPSED_KEY) === "1";
  } catch (e) {
    /* ignore */
  }
  setChatCollapsed(collapsed);

  document.getElementById("chat-collapse-btn")?.addEventListener("click", () => {
    setChatCollapsed(true);
  });
  document.getElementById("chat-expand-btn")?.addEventListener("click", () => {
    setChatCollapsed(false);
  });
}

function bindApplyReviewerButtons() {
  document.querySelectorAll(".apply-reviewer-btn").forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.dataset.reviewIndex, 10);
      applyReviewerSuggestions(Number.isNaN(idx) ? -1 : idx);
    });
  });
}

function initChat() {
  bindChatControls();
  initAiSpeak();
  initVoiceInput();
  initChatCollapse();
  if (window.__chatHistory?.length) {
    renderChatHistory(window.__chatHistory);
  } else {
    bindApplyReviewerButtons();
  }
}

window.bindApplyReviewerButtons = bindApplyReviewerButtons;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initChat);
} else {
  initChat();
}
