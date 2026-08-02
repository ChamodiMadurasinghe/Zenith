(function () {
  const POS_KEY = "zenith_guide_pos";
  const COLLAPSED_KEY = "zenith_guide_collapsed";
  const DRAG_THRESHOLD = 6;

  let busy = false;
  let recognition = null;
  let listening = false;
  let drag = null;
  let fabWasDragged = false;

  function i18n(key, vars) {
    if (typeof window.__ === "function") return window.__(key, vars);
    return key;
  }

  function els() {
    return {
      root: document.getElementById("zenith-guide"),
      fab: document.getElementById("guide-fab"),
      messages: document.getElementById("guide-messages"),
      input: document.getElementById("guide-input"),
      send: document.getElementById("guide-send"),
      mic: document.getElementById("guide-mic"),
      reset: document.getElementById("guide-reset"),
      minimize: document.getElementById("guide-minimize"),
      handle: document.getElementById("guide-drag-handle"),
    };
  }

  function setCollapsed(collapsed) {
    const { root, fab } = els();
    if (!root) return;
    root.classList.toggle("guide-collapsed", collapsed);
    if (fab) fab.setAttribute("aria-expanded", collapsed ? "false" : "true");
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch (e) {}
  }

  function loadCollapsed() {
    try {
      return localStorage.getItem(COLLAPSED_KEY) !== "0";
    } catch (e) {
      return true;
    }
  }

  function applyPosition(left, top) {
    const { root } = els();
    if (!root) return;
    root.style.left = left + "px";
    root.style.top = top + "px";
    root.style.right = "auto";
    root.style.bottom = "auto";
  }

  function loadPosition() {
    try {
      const raw = localStorage.getItem(POS_KEY);
      if (!raw) return;
      const pos = JSON.parse(raw);
      if (typeof pos.left === "number" && typeof pos.top === "number") {
        applyPosition(pos.left, pos.top);
      }
    } catch (e) {}
  }

  function savePosition() {
    const { root } = els();
    if (!root) return;
    const rect = root.getBoundingClientRect();
    try {
      localStorage.setItem(POS_KEY, JSON.stringify({ left: rect.left, top: rect.top }));
    } catch (e) {}
  }

  function clampPosition() {
    const { root } = els();
    if (!root) return;
    const rect = root.getBoundingClientRect();
    const maxLeft = Math.max(0, window.innerWidth - rect.width);
    const maxTop = Math.max(0, window.innerHeight - rect.height);
    applyPosition(Math.min(Math.max(0, rect.left), maxLeft), Math.min(Math.max(0, rect.top), maxTop));
    savePosition();
  }

  const ACTION_DELAY_MS = 800;

  function executeGuideActions(actions) {
    if (!actions?.length) return;
    actions.forEach((item) => {
      if (item.action === "navigate" && item.url) {
        setTimeout(() => {
          window.location.href = item.url;
        }, ACTION_DELAY_MS);
      } else if (item.action === "logout") {
        setTimeout(() => {
          const form = document.getElementById("nav-logout-form");
          if (form) form.requestSubmit();
        }, ACTION_DELAY_MS);
      }
    });
  }

  function appendMsg(role, text) {
    const { messages } = els();
    if (!messages) return null;
    messages.querySelector(".guide-welcome")?.remove();
    const el = document.createElement("div");
    el.className = "guide-msg guide-msg-" + role;
    el.textContent = text || "";
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  async function sendGuide() {
    if (busy) return;
    const { input, send } = els();
    const text = (input?.value || "").trim();
    if (!text) return;

    busy = true;
    appendMsg("user", text);
    if (input) input.value = "";
    if (send) send.disabled = true;

    const thinking = appendMsg("assistant", i18n("guide_thinking"));
    thinking?.classList.add("chat-thinking");

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 90000);
      const res = await fetch("/api/guide/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ message: text, page_path: window.location.pathname }),
        signal: controller.signal,
      });
      clearTimeout(timer);
      thinking?.remove();

      const ctype = res.headers.get("content-type") || "";
      if (!ctype.includes("application/json")) {
        appendMsg("assistant", i18n("js_server_error", { status: res.status }));
        return;
      }

      const data = await res.json();
      if (res.status === 401) {
        appendMsg("assistant", data.reply || i18n("js_session_expired"));
        return;
      }

      const reply = (data.reply || data.error || "").trim() || i18n("js_empty_reply");
      appendMsg("assistant", reply);
      executeGuideActions(data.actions);
    } catch (err) {
      thinking?.remove();
      appendMsg("assistant", err?.name === "AbortError" ? i18n("js_timeout") : i18n("js_unreachable"));
    } finally {
      busy = false;
      if (send) send.disabled = false;
    }
  }

  async function resetGuide() {
    try {
      await fetch("/api/guide/chat/reset", { method: "POST", credentials: "same-origin" });
    } catch (e) {}
    const { messages } = els();
    if (!messages) return;
    const welcomeText = messages.querySelector(".guide-welcome")?.textContent || i18n("guide_welcome");
    messages.innerHTML = "";
    const el = document.createElement("div");
    el.className = "guide-welcome chat-welcome";
    el.textContent = welcomeText;
    messages.appendChild(el);
  }

  function attachDrag(handle, options) {
    const { root } = els();
    if (!root || !handle) return;

    const threshold = options?.threshold ?? 0;
    let localDrag = null;
    let moved = false;

    function onDown(clientX, clientY) {
      if (options?.skipIfButton && options.skipIfButton()) return;
      moved = false;
      fabWasDragged = false;
      const rect = root.getBoundingClientRect();
      localDrag = {
        offsetX: clientX - rect.left,
        offsetY: clientY - rect.top,
        startX: clientX,
        startY: clientY,
      };
      applyPosition(rect.left, rect.top);
      root.classList.add("guide-dragging");
    }

    function onMove(clientX, clientY) {
      if (!localDrag) return;
      if (threshold > 0 && !moved) {
        if (
          Math.abs(clientX - localDrag.startX) > threshold ||
          Math.abs(clientY - localDrag.startY) > threshold
        ) {
          moved = true;
        }
        if (!moved) return;
      }
      applyPosition(clientX - localDrag.offsetX, clientY - localDrag.offsetY);
    }

    function onUp() {
      if (!localDrag) return;
      localDrag = null;
      root.classList.remove("guide-dragging");
      clampPosition();
      if (options?.markFabDrag && moved) fabWasDragged = true;
      moved = false;
    }

    handle.addEventListener("mousedown", (e) => {
      if (e.target.closest("button") && handle !== e.currentTarget) return;
      e.preventDefault();
      onDown(e.clientX, e.clientY);
    });
    window.addEventListener("mousemove", (e) => onMove(e.clientX, e.clientY));
    window.addEventListener("mouseup", onUp);

    handle.addEventListener(
      "touchstart",
      (e) => {
        if (e.target.closest("button") && handle !== e.currentTarget) return;
        const t = e.touches[0];
        onDown(t.clientX, t.clientY);
      },
      { passive: true }
    );
    window.addEventListener(
      "touchmove",
      (e) => {
        if (!localDrag) return;
        const t = e.touches[0];
        onMove(t.clientX, t.clientY);
      },
      { passive: true }
    );
    window.addEventListener("touchend", onUp);
  }

  function initDrag() {
    const { handle, fab } = els();
    attachDrag(handle, { threshold: 0 });
    attachDrag(fab, { threshold: DRAG_THRESHOLD, markFabDrag: true });
  }

  function initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const { mic, input } = els();
    if (!mic) return;
    if (!SpeechRecognition) {
      mic.disabled = true;
      mic.title = i18n("js_voice_unsupported");
      return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = window.__speechLang || "en-LK";
    recognition.addEventListener("result", (e) => {
      if (input) input.value = e.results[0][0].transcript;
      sendGuide();
    });
    recognition.addEventListener("end", () => {
      listening = false;
      mic.textContent = "🎤";
    });
    recognition.addEventListener("error", () => {
      listening = false;
      mic.textContent = "🎤";
    });
    mic.addEventListener("click", () => {
      if (listening) return;
      try {
        listening = true;
        mic.textContent = "…";
        recognition.start();
      } catch (e) {
        listening = false;
        mic.textContent = "🎤";
      }
    });
  }

  function init() {
    const { root, fab, send, input, reset, minimize } = els();
    if (!root) return;
    setCollapsed(loadCollapsed());
    loadPosition();
    fab?.addEventListener("click", (e) => {
      if (fabWasDragged) {
        e.preventDefault();
        fabWasDragged = false;
        return;
      }
      setCollapsed(false);
    });
    minimize?.addEventListener("click", () => setCollapsed(true));
    reset?.addEventListener("click", resetGuide);
    send?.addEventListener("click", sendGuide);
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendGuide();
    });
    initDrag();
    initVoice();
    window.addEventListener("resize", clampPosition);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
