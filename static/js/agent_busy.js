(function () {
  "use strict";

  var depth = 0;
  var banner = null;
  var textEl = null;

  function i18n(key) {
    if (typeof window.__ === "function") return window.__(key);
    return key;
  }

  function ensureBanner() {
    if (banner) return banner;
    banner = document.getElementById("agent-busy-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "agent-busy-banner";
      banner.className = "agent-busy-banner";
      banner.setAttribute("hidden", "");
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-live", "polite");
      banner.innerHTML =
        '<span class="agent-busy-spinner" aria-hidden="true"></span>' +
        '<span class="agent-busy-text"></span>';
      document.body.appendChild(banner);
    }
    textEl = banner.querySelector(".agent-busy-text");
    return banner;
  }

  function show(message) {
    depth += 1;
    var el = ensureBanner();
    if (textEl) {
      textEl.textContent = message || i18n("js_agent_busy");
    }
    el.removeAttribute("hidden");
    document.body.classList.add("agent-is-busy");
  }

  function hide() {
    depth = Math.max(0, depth - 1);
    if (depth > 0) return;
    var el = ensureBanner();
    el.setAttribute("hidden", "");
    document.body.classList.remove("agent-is-busy");
  }

  function forceHide() {
    depth = 0;
    hide();
  }

  /** Show busy UI for a full-page form submit that runs an agent. */
  function bindAgentForms() {
    document.querySelectorAll("form[data-agent-busy]").forEach(function (form) {
      if (form.dataset.agentBusyBound) return;
      form.dataset.agentBusyBound = "1";
      form.addEventListener("submit", function () {
        var key = form.getAttribute("data-agent-busy") || "js_agent_busy";
        var msg = i18n(key);
        if (msg === key) msg = i18n("js_agent_busy");
        show(msg);
        form.querySelectorAll("button[type='submit'], input[type='submit']").forEach(function (btn) {
          btn.disabled = true;
        });
      });
    });
  }

  window.zenithAgentBusy = {
    show: show,
    hide: hide,
    forceHide: forceHide,
    bindForms: bindAgentForms,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAgentForms);
  } else {
    bindAgentForms();
  }
})();
