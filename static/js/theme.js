(function () {
  "use strict";

  var THEME_KEY = "zenith_theme";
  var FONT_KEY = "zenith_font_size";
  var FONT_SIZES = { normal: true, large: true, xlarge: true };

  function getTheme() {
    try {
      return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
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
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {}
    applyTheme(theme);
  }

  function toggleTheme() {
    setTheme(getTheme() === "dark" ? "light" : "dark");
  }

  function getFontSize() {
    try {
      var value = localStorage.getItem(FONT_KEY) || "normal";
      return FONT_SIZES[value] ? value : "normal";
    } catch (e) {
      return "normal";
    }
  }

  function applyFontSize(size) {
    var root = document.documentElement;
    if (size === "large" || size === "xlarge") {
      root.setAttribute("data-font-size", size);
    } else {
      root.removeAttribute("data-font-size");
      size = "normal";
    }
    updateFontButtons(size);
    if (typeof window.__zenithSyncChromeOffset === "function") {
      window.__zenithSyncChromeOffset();
    }
  }

  function updateFontButtons(size) {
    document.querySelectorAll("[data-font-size]").forEach(function (btn) {
      var active = btn.getAttribute("data-font-size") === size;
      btn.classList.toggle("active", active);
      if (active) {
        btn.setAttribute("aria-current", "true");
      } else {
        btn.removeAttribute("aria-current");
      }
    });
  }

  function setFontSize(size) {
    if (!FONT_SIZES[size]) size = "normal";
    try {
      localStorage.setItem(FONT_KEY, size);
    } catch (e) {}
    applyFontSize(size);
  }

  function closeFlyout(btn, flyout) {
    if (!btn || !flyout) return;
    flyout.setAttribute("hidden", "");
    btn.setAttribute("aria-expanded", "false");
  }

  function closeSettings(settingsBtn, panel, flyouts) {
    if (!settingsBtn || !panel) return;
    panel.setAttribute("hidden", "");
    settingsBtn.setAttribute("aria-expanded", "false");
    (flyouts || []).forEach(function (entry) {
      closeFlyout(entry.btn, entry.flyout);
    });
  }

  function wireFlyout(btn, flyout, others) {
    if (!btn || !flyout) return;
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      var open = flyout.hasAttribute("hidden");
      (others || []).forEach(function (entry) {
        closeFlyout(entry.btn, entry.flyout);
      });
      if (open) {
        flyout.removeAttribute("hidden");
        btn.setAttribute("aria-expanded", "true");
      } else {
        closeFlyout(btn, flyout);
      }
    });
  }

  function init() {
    applyTheme(getTheme());
    applyFontSize(getFontSize());

    var btn = document.getElementById("theme-toggle");
    if (btn) btn.addEventListener("click", toggleTheme);

    var settingsBtn = document.getElementById("settings-toggle");
    var panel = document.getElementById("settings-panel");
    var langBtn = document.getElementById("settings-lang-toggle");
    var langFlyout = document.getElementById("settings-lang-flyout");
    var fontBtn = document.getElementById("settings-font-toggle");
    var fontFlyout = document.getElementById("settings-font-flyout");
    var flyouts = [
      { btn: langBtn, flyout: langFlyout },
      { btn: fontBtn, flyout: fontFlyout },
    ];

    if (settingsBtn && panel) {
      settingsBtn.addEventListener("click", function (event) {
        event.stopPropagation();
        var open = panel.hasAttribute("hidden");
        if (open) {
          panel.removeAttribute("hidden");
          settingsBtn.setAttribute("aria-expanded", "true");
        } else {
          closeSettings(settingsBtn, panel, flyouts);
        }
      });

      wireFlyout(langBtn, langFlyout, [{ btn: fontBtn, flyout: fontFlyout }]);
      wireFlyout(fontBtn, fontFlyout, [{ btn: langBtn, flyout: langFlyout }]);

      if (fontFlyout) {
        fontFlyout.addEventListener("click", function (event) {
          var choice = event.target.closest("[data-font-size]");
          if (!choice) return;
          event.preventDefault();
          event.stopPropagation();
          setFontSize(choice.getAttribute("data-font-size"));
          closeFlyout(fontBtn, fontFlyout);
        });
      }

      document.addEventListener("click", function (event) {
        if (panel.hasAttribute("hidden")) return;
        if (event.target.closest(".settings-menu")) return;
        closeSettings(settingsBtn, panel, flyouts);
      });

      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        if (panel.hasAttribute("hidden")) return;
        closeSettings(settingsBtn, panel, flyouts);
        settingsBtn.focus();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
