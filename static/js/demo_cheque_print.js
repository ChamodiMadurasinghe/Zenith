(function () {
  var root = document.getElementById("demo-cheque-print");
  if (!root) return;

  var accountId = parseInt(root.getAttribute("data-account-id") || "0", 10);
  var statusEl = document.getElementById("demo-cheque-print-status");
  var btn = document.getElementById("demo-cheque-print-btn");

  function i18n(key) {
    if (typeof window.__ === "function") return window.__(key);
    return key;
  }

  function showStatus(message, isError) {
    if (!statusEl) return;
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("success-msg", !!message && !isError);
    statusEl.classList.toggle("preview-warning-banner", !!message && isError);
  }

  function openPdfBlob(blob) {
    var url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 60000);
  }

  btn?.addEventListener("click", function () {
    var payee = (document.getElementById("demo-cheque-payee")?.value || "").trim();
    var amountRaw = document.getElementById("demo-cheque-amount")?.value;
    var dateStr = (document.getElementById("demo-cheque-date")?.value || "").trim();
    var crossing = document.getElementById("demo-cheque-crossing")?.checked !== false;
    var amount = parseFloat(amountRaw);

    if (!payee) {
      showStatus(i18n("demo_cheque_payee_required"), true);
      return;
    }
    if (!Number.isFinite(amount) || amount < 0) {
      showStatus(i18n("demo_cheque_amount_invalid"), true);
      return;
    }
    if (!dateStr) {
      showStatus(i18n("demo_cheque_date_required"), true);
      return;
    }
    if (!accountId) {
      showStatus(i18n("demo_cheque_print_failed"), true);
      return;
    }

    if (btn) btn.disabled = true;
    showStatus(i18n("demo_cheque_printing"), false);

    fetch("/api/cheque/print", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/pdf" },
      credentials: "same-origin",
      body: JSON.stringify({
        user_bank_acc_id: accountId,
        payee_name: payee,
        amount: amount,
        date_str: dateStr,
        crossing: crossing,
      }),
    })
      .then(function (res) {
        var ctype = res.headers.get("content-type") || "";
        if (!res.ok) {
          if (ctype.indexOf("application/json") !== -1) {
            return res.json().then(function (data) {
              throw new Error(data.error || i18n("demo_cheque_print_failed"));
            });
          }
          throw new Error(i18n("demo_cheque_print_failed"));
        }
        return res.blob();
      })
      .then(function (blob) {
        openPdfBlob(blob);
        showStatus(i18n("demo_cheque_print_opened"), false);
      })
      .catch(function (err) {
        showStatus(err.message || i18n("demo_cheque_print_failed"), true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  });
})();
