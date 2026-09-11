(function () {
  "use strict";

  function t(key, vars) {
    if (typeof window.__ === "function") {
      return window.__(key, vars);
    }
    return (window.__i18n && window.__i18n[key]) || key;
  }

  function setStatus(el, text, kind) {
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || "";
    el.classList.remove("is-ok", "is-warn", "is-error");
    if (kind) el.classList.add(kind);
  }

  async function checkForUpdates(btn, statusEl) {
    btn.disabled = true;
    setStatus(statusEl, t("update_checking"), null);
    try {
      var resp = await fetch("/api/admin/check-update", {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      var data = await resp.json();
      if (data.error || data.message === "System is offline or central server unreachable") {
        setStatus(
          statusEl,
          data.message || t("update_offline"),
          "is-warn"
        );
        return;
      }
      if (!data.update_available) {
        setStatus(
          statusEl,
          t("update_up_to_date", { version: data.current_version || "" }),
          "is-ok"
        );
        return;
      }
      var latest = data.latest_version || "";
      var changelog = (data.changelog || "").trim();
      var confirmMsg = t("update_confirm", { version: latest });
      if (changelog) {
        confirmMsg += "\n\n" + changelog;
      }
      if (!window.confirm(confirmMsg)) {
        setStatus(statusEl, t("update_available_hint", { version: latest }), "is-warn");
        return;
      }
      await applyUpdate(btn, statusEl, data);
    } catch (err) {
      setStatus(statusEl, t("update_check_failed"), "is-error");
    } finally {
      btn.disabled = false;
    }
  }

  async function applyUpdate(btn, statusEl, manifest) {
    btn.disabled = true;
    setStatus(statusEl, t("update_installing"), null);
    try {
      var resp = await fetch("/api/admin/apply-update", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(manifest || {}),
      });
      var data = await resp.json();
      if (!resp.ok || data.status === "error") {
        setStatus(statusEl, data.message || t("update_failed"), "is-error");
        return;
      }
      setStatus(statusEl, data.message || t("update_restarting"), "is-ok");
    } catch (err) {
      setStatus(statusEl, t("update_failed"), "is-error");
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("check-update-btn");
    if (!btn) return;
    var statusEl = document.getElementById("update-status");
    btn.addEventListener("click", function () {
      checkForUpdates(btn, statusEl);
    });
  });
})();
