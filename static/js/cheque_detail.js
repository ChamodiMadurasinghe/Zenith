/** Read-only cheque detail modal. Rows use data-cheque-id. */
(function () {
  var modal = document.getElementById("cheque-detail-modal");
  if (!modal) return;

  var body = document.getElementById("cheque-detail-body");
  var statusEl = document.getElementById("cheque-detail-status");
  var titleEl = document.getElementById("cheque-detail-title");
  var lastFocus = null;

  function t(key, vars) {
    return window.__ ? window.__(key, vars) : key;
  }

  function formatLkr(n) {
    var num = Number(n || 0);
    return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function lineItemSummary(items) {
    if (!items || !items.length) return "—";
    return items
      .map(function (it) {
        var name = it.item_name || it.item_code || "item";
        var qty = it.item_qty != null ? it.item_qty : "";
        return qty !== "" ? name + " × " + qty : name;
      })
      .join("; ");
  }

  function bankLabel(bank) {
    if (!bank) return "—";
    var nick = bank.nickname || bank.account_name || "";
    var name = bank.bank_name || "";
    if (nick && name) return nick + " — " + name;
    return nick || name || "—";
  }

  function setStatus(text, show) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.hidden = !show;
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  function openModal() {
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.remove("modal-open");
    document.body.classList.add("modal-open");
    var closeBtn = modal.querySelector(".modal-close");
    if (closeBtn) closeBtn.focus();
  }

  function renderDetail(data) {
    var dealer = data.dealer || {};
    var invoices = data.invoices || [];
    var creditDays = "";
    if (invoices.length && invoices[0].credit_period_days != null) {
      creditDays = String(invoices[0].credit_period_days);
    }
    var terms = [];
    if (dealer.casual_days != null) terms.push(t("casual_days") + ": " + dealer.casual_days);
    if (creditDays) terms.push(t("credit_period") + ": " + creditDays);

    var invoiceRows = invoices
      .map(function (inv) {
        var amount =
          inv.allocated_amount != null && inv.allocated_amount !== inv.total_amount
            ? formatLkr(inv.allocated_amount) + " / " + formatLkr(inv.total_amount)
            : formatLkr(inv.allocated_amount != null ? inv.allocated_amount : inv.total_amount);
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(inv.invoice_no) +
          "</td>" +
          "<td>" +
          escapeHtml(inv.invoiced_date || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(inv.due_date || "—") +
          "</td>" +
          "<td>Rs. " +
          amount +
          "</td>" +
          "<td>" +
          escapeHtml(lineItemSummary(inv.line_items)) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");

    body.innerHTML =
      '<div class="cheque-print card">' +
      '<div class="cheque-header">' +
      escapeHtml(t("cheque_header")) +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_number")) +
      ":</span> " +
      escapeHtml(data.cheque_no || "—") +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_date")) +
      ":</span> " +
      escapeHtml(data.cheque_date || "—") +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_pay")) +
      ":</span> " +
      escapeHtml(dealer.dealer_name || "—") +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_amount")) +
      ":</span> Rs. " +
      formatLkr(data.amount) +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_words")) +
      ":</span> " +
      escapeHtml(data.amount_in_words || "—") +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_detail_paying_bank")) +
      ":</span> " +
      escapeHtml(bankLabel(data.bank)) +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("col_clearance")) +
      ":</span> " +
      escapeHtml(data.expected_clearance_date || "—") +
      "</div>" +
      "</div>" +
      '<div class="card">' +
      "<h3>" +
      escapeHtml(t("cheque_detail_payee")) +
      "</h3>" +
      "<p><strong>" +
      escapeHtml(dealer.dealer_name || "—") +
      "</strong></p>" +
      "<p>" +
      escapeHtml(t("email")) +
      ": " +
      escapeHtml(dealer.dealer_email || "—") +
      "</p>" +
      "<p>" +
      escapeHtml(t("phone")) +
      ": " +
      escapeHtml(dealer.dealer_telno || "—") +
      "</p>" +
      "<p>" +
      escapeHtml(t("cheque_detail_terms")) +
      ": " +
      escapeHtml(terms.length ? terms.join(" · ") : "—") +
      "</p>" +
      "</div>" +
      "<h3>" +
      escapeHtml(t("cheque_detail_invoices")) +
      "</h3>" +
      (invoices.length
        ? '<div class="table-scroll"><table class="data-table"><thead><tr>' +
          "<th>" +
          escapeHtml(t("col_invoice_no")) +
          "</th>" +
          "<th>" +
          escapeHtml(t("col_date")) +
          "</th>" +
          "<th>" +
          escapeHtml(t("col_due_date")) +
          "</th>" +
          "<th>" +
          escapeHtml(t("col_amount")) +
          "</th>" +
          "<th>" +
          escapeHtml(t("cheque_detail_line_items")) +
          "</th>" +
          "</tr></thead><tbody>" +
          invoiceRows +
          "</tbody></table></div>"
        : "<p class='muted'>—</p>");

    if (titleEl) {
      titleEl.textContent = t("cheque_detail_title") + (data.cheque_no ? " #" + data.cheque_no : "");
    }
  }

  function loadCheque(id) {
    setStatus(t("cheque_detail_loading"), true);
    body.innerHTML = "";
    openModal();
    fetch("/api/cheques/" + encodeURIComponent(id) + "/detail", { credentials: "same-origin" })
      .then(function (res) {
        if (res.status === 401) throw new Error(t("js_session_expired"));
        if (!res.ok) throw new Error(t("cheque_detail_error"));
        return res.json();
      })
      .then(function (data) {
        setStatus("", false);
        renderDetail(data);
      })
      .catch(function (err) {
        setStatus(err.message || t("cheque_detail_error"), true);
      });
  }

  document.addEventListener("click", function (ev) {
    var closer = ev.target.closest("[data-cheque-detail-close]");
    if (closer && modal.contains(closer)) {
      ev.preventDefault();
      closeModal();
      return;
    }
    var row = ev.target.closest("[data-cheque-id]");
    if (!row) return;
    var id = row.getAttribute("data-cheque-id");
    if (!id || id === "0") return;
    ev.preventDefault();
    loadCheque(id);
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !modal.hidden) {
      closeModal();
      return;
    }
    if ((ev.key === "Enter" || ev.key === " ") && ev.target && ev.target.getAttribute("data-cheque-id")) {
      ev.preventDefault();
      var id = ev.target.getAttribute("data-cheque-id");
      if (id && id !== "0") loadCheque(id);
    }
  });
})();
