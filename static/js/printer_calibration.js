(function () {
  var root = document.getElementById("printer-calibration");
  if (!root) return;

  var accountId = parseInt(root.getAttribute("data-account-id") || "0", 10);
  var offsetX = parseFloat(root.getAttribute("data-offset-x") || "0");
  var offsetY = parseFloat(root.getAttribute("data-offset-y") || "0");
  var feedSelect = document.getElementById("printer-feed-orientation");
  var statusEl = document.getElementById("printer-calibration-status");

  function formatOffset(value) {
    var sign = value >= 0 ? "+" : "";
    return sign + value.toFixed(1);
  }

  function refreshReadout() {
    var xEl = document.getElementById("printer-offset-x-value");
    var yEl = document.getElementById("printer-offset-y-value");
    if (xEl) xEl.textContent = formatOffset(offsetX);
    if (yEl) yEl.textContent = formatOffset(offsetY);
  }

  function showStatus(message, isError) {
    if (!statusEl) return;
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("success-msg", !!message && !isError);
    statusEl.classList.toggle("preview-warning-banner", !!message && isError);
  }

  function nudge(dx, dy) {
    offsetX = Math.round((offsetX + dx) * 10) / 10;
    offsetY = Math.round((offsetY + dy) * 10) / 10;
    if (offsetX > 20) offsetX = 20;
    if (offsetX < -20) offsetX = -20;
    if (offsetY > 20) offsetY = 20;
    if (offsetY < -20) offsetY = -20;
    refreshReadout();
    showStatus("", false);
  }

  document.getElementById("printer-shift-left")?.addEventListener("click", function () {
    nudge(-1, 0);
  });
  document.getElementById("printer-shift-right")?.addEventListener("click", function () {
    nudge(1, 0);
  });
  document.getElementById("printer-shift-up")?.addEventListener("click", function () {
    nudge(0, 1);
  });
  document.getElementById("printer-shift-down")?.addEventListener("click", function () {
    nudge(0, -1);
  });
  document.getElementById("printer-reset-offsets")?.addEventListener("click", function () {
    offsetX = 0;
    offsetY = 0;
    refreshReadout();
    showStatus("", false);
  });

  function calibrationPayload() {
    return {
      user_bank_acc_id: accountId,
      offset_x_mm: offsetX,
      offset_y_mm: offsetY,
      feed_orientation: feedSelect ? feedSelect.value : "VERTICAL",
    };
  }

  document.getElementById("printer-test-print")?.addEventListener("click", function () {
    var btn = document.getElementById("printer-test-print");
    if (btn) btn.disabled = true;
    showStatus("", false);
    fetch("/api/cheque/print-test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(calibrationPayload()),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (data) {
            throw new Error(data.error || "Print failed");
          });
        }
        return res.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        window.open(url, "_blank");
        setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
      })
      .catch(function (err) {
        showStatus(err.message || "Could not print test cheque.", true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  });

  document.getElementById("printer-save-calibration")?.addEventListener("click", function () {
    var btn = document.getElementById("printer-save-calibration");
    if (btn) btn.disabled = true;
    fetch("/api/cheque/calibration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(calibrationPayload()),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.error || "Save failed");
          return data;
        });
      })
      .then(function () {
        var savedMsg = typeof window.__ === "function"
          ? window.__("flash_printer_calibration_saved")
          : "Printer calibration saved.";
        showStatus(savedMsg, false);
      })
      .catch(function (err) {
        showStatus(err.message || "Could not save calibration.", true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  });

  refreshReadout();
})();
