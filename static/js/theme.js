(function () {
  "use strict";

  var STORAGE_KEY = "zenith_theme";

  function getTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
    } catch (e) {
      return "light";
    }
  }

  function applyTheme(theme) {
    var root = document.documentElement;
    if (theme === "dark") {
      root.setAttribute("data-theme", "dark");
    } else {
      root.removeAttribute("data-theme");
    }
    updateToggle(theme);
  }

  function updateToggle(theme) {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    var isDark = theme === "dark";
    btn.setAttribute("aria-pressed", isDark ? "true" : "false");
    var labelEl = btn.querySelector(".theme-toggle-label");
    var lightLabel = (window.__i18n && window.__i18n.theme_light) || "Light mode";
    var darkLabel = (window.__i18n && window.__i18n.theme_dark) || "Dark mode";
    btn.title = isDark ? lightLabel : darkLabel;
    btn.setAttribute("aria-label", btn.title);
    if (labelEl) labelEl.textContent = isDark ? lightLabel : darkLabel;
  }

  function setTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {}
    applyTheme(theme);
  }

  function toggleTheme() {
    setTheme(getTheme() === "dark" ? "light" : "dark");
  }

  function init() {
    applyTheme(getTheme());
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.addEventListener("click", toggleTheme);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
