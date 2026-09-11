(function () {
  "use strict";

  var DRIVE_SEARCH = "https://drive.google.com/drive/search?q=Zenith_Backup";

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

  function passphraseMissing(message) {
    return /passphrase is required/i.test(message || "");
  }

  async function postBackup(passphrase) {
    var body = {};
    if (passphrase) body.passphrase = passphrase;
    var resp = await fetch("/api/backup/now", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    var data = await resp.json().catch(function () {
      return {};
    });
    return { resp: resp, data: data };
  }

  async function runBackup(btn, statusEl, driveLink) {
    btn.disabled = true;
    if (driveLink) driveLink.hidden = true;
    setStatus(statusEl, t("backup_in_progress"), null);
    try {
      var result = await postBackup("");
      var resp = result.resp;
      var data = result.data;
      if (passphraseMissing(data.message)) {
        var typed = window.prompt(t("backup_passphrase_prompt"), "");
        if (typed == null || !String(typed).trim()) {
          setStatus(statusEl, t("backup_passphrase_needed"), "is-error");
          return;
        }
        setStatus(statusEl, t("backup_in_progress"), null);
        result = await postBackup(String(typed).trim());
        resp = result.resp;
        data = result.data;
      }
      if (data.status === "warning") {
        setStatus(statusEl, data.message || t("backup_offline"), "is-warn");
        return;
      }
      if (!resp.ok || data.status === "error") {
        setStatus(statusEl, data.message || t("backup_failed"), "is-error");
        return;
      }
      var fileName = data.file_name || "";
      var message = data.message || t("backup_success", { file_name: fileName });
      setStatus(statusEl, message, "is-ok");
      if (driveLink) {
        driveLink.href = fileName
          ? "https://drive.google.com/drive/search?q=" + encodeURIComponent(fileName)
          : DRIVE_SEARCH;
        driveLink.hidden = false;
      }
    } catch (err) {
      setStatus(statusEl, t("backup_failed"), "is-error");
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("backup-now-btn");
    if (!btn) return;
    var statusEl = document.getElementById("backup-status");
    var driveLink = document.getElementById("backup-drive-link");
    btn.addEventListener("click", function () {
      runBackup(btn, statusEl, driveLink);
    });
  });
})();
