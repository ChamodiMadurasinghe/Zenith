/** Cheque detail modal with Edit/Save/Cancel for cheque_no + cheque_date. Rows use data-cheque-id. */
(function () {
  var modal = document.getElementById("cheque-detail-modal");
  if (!modal) return;

  var body = document.getElementById("cheque-detail-body");
  var actions = document.getElementById("cheque-detail-actions");
  var statusEl = document.getElementById("cheque-detail-status");
  var titleEl = document.getElementById("cheque-detail-title");
  var lastFocus = null;
  var currentId = null;
  var currentData = null;
  var editMode = false;
  var saving = false;

  function t(key, vars) {
    return window.__ ? window.__(key, vars) : key;
  }

  function label(key, fallback) {
    var v = t(key);
    return !v || v === key ? fallback : v;
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
    editMode = false;
    saving = false;
    currentId = null;
    currentData = null;
    if (actions) {
      actions.hidden = true;
      actions.innerHTML = "";
    }
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

  function dealerContextId(data) {
    var d = (data && data.dealer) || {};
    if (d.dealer_id != null) return String(d.dealer_id);
    var hub = document.querySelector("[data-dealer]");
    return hub ? hub.getAttribute("data-dealer") : "";
  }

  function refreshTableRow(data) {
    if (!data || data.cheque_id == null) return;
    var row = document.querySelector('[data-cheque-id="' + String(data.cheque_id) + '"]');
    if (!row) return;
    var cells = row.querySelectorAll("td");
    // dealer_cheques.html: no, date, clearance, days_gained, amount, dealer
    if (cells.length >= 1) cells[0].textContent = data.cheque_no || "";
    if (cells.length >= 2) cells[1].textContent = data.cheque_date || "";
    if (cells.length >= 3) {
      var clearance = data.expected_clearance_date || "—";
      cells[2].innerHTML = "<strong>" + escapeHtml(clearance) + "</strong>";
    }
    if (cells.length >= 4) {
      cells[3].textContent = data.days_gained != null ? String(data.days_gained) : "—";
    }
  }

  function renderActions() {
    if (!actions) return;
    if (!currentData) {
      actions.hidden = true;
      actions.innerHTML = "";
      return;
    }
    actions.hidden = false;
    if (editMode) {
      actions.innerHTML =
        '<button type="button" class="btn btn-primary" data-cheque-save>' +
        escapeHtml(label("save", "Save")) +
        "</button> " +
        '<button type="button" class="btn btn-secondary" data-cheque-cancel>' +
        escapeHtml(label("cancel", "Cancel")) +
        "</button>";
    } else {
      actions.innerHTML =
        '<button type="button" class="btn btn-secondary" data-cheque-edit>' +
        escapeHtml(label("edit", "Edit")) +
        "</button>";
    }
  }

  function renderDetail(data) {
    currentData = data;
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

    var noCell;
    var dateCell;
    if (editMode) {
      noCell =
        '<input type="text" id="cheque-edit-no" class="input" value="' +
        escapeHtml(data.cheque_no || "") +
        '" autocomplete="off" />';
      dateCell =
        '<input type="date" id="cheque-edit-date" class="input" value="' +
        escapeHtml(data.cheque_date || "") +
        '" />';
    } else {
      noCell = escapeHtml(data.cheque_no || "—");
      dateCell = escapeHtml(data.cheque_date || "—");
    }

    body.innerHTML =
      '<div class="cheque-print card">' +
      '<div class="cheque-header">' +
      escapeHtml(t("cheque_header")) +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_number")) +
      ":</span> " +
      noCell +
      "</div>" +
      '<div class="cheque-row"><span>' +
      escapeHtml(t("cheque_date")) +
      ":</span> " +
      dateCell +
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
    renderActions();
    if (editMode) {
      var noInput = document.getElementById("cheque-edit-no");
      if (noInput) noInput.focus();
    }
  }

  function loadCheque(id) {
    editMode = false;
    saving = false;
    currentId = id;
    currentData = null;
    setStatus(t("cheque_detail_loading"), true);
    body.innerHTML = "";
    if (actions) {
      actions.hidden = true;
      actions.innerHTML = "";
    }
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

  function enterEdit() {
    if (!currentData || saving) return;
    editMode = true;
    renderDetail(currentData);
  }

  function cancelEdit() {
    if (saving) return;
    editMode = false;
    if (currentData) renderDetail(currentData);
  }

  function saveEdit() {
    if (!currentId || saving) return;
    var noInput = document.getElementById("cheque-edit-no");
    var dateInput = document.getElementById("cheque-edit-date");
    var chequeNo = noInput ? String(noInput.value || "").trim() : "";
    var chequeDate = dateInput ? String(dateInput.value || "").trim() : "";

    if (!chequeNo) {
      setStatus(label("cheque_no_required", "Cheque number is required."), true);
      if (noInput) noInput.focus();
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(chequeDate)) {
      setStatus(label("invalid_cheque_date", "Cheque date must be YYYY-MM-DD."), true);
      if (dateInput) dateInput.focus();
      return;
    }

    var confirmMsg = label(
      "cheque_edit_confirm",
      "Save changes to cheque number and date? Clearance will be recalculated if the date changed."
    );
    if (!window.confirm(confirmMsg)) return;

    saving = true;
    setStatus(label("cheque_edit_saving", "Saving…"), true);
    var payload = { cheque_no: chequeNo, cheque_date: chequeDate };
    var dealerId = dealerContextId(currentData);
    if (dealerId) payload.dealer_id = dealerId;

    fetch("/dealers/cheques/" + encodeURIComponent(currentId) + "/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (res.status === 401) throw new Error(t("js_session_expired"));
        return res.json().then(function (data) {
          return { res: res, data: data };
        });
      })
      .then(function (pair) {
        saving = false;
        if (!pair.res.ok || !pair.data || !pair.data.ok) {
          var err =
            (pair.data && pair.data.error) ||
            label("cheque_edit_error", "Could not save cheque changes.");
          setStatus(String(err), true);
          return;
        }
        editMode = false;
        setStatus("", false);
        renderDetail(pair.data.cheque);
        refreshTableRow(pair.data.cheque);
      })
      .catch(function (err) {
        saving = false;
        setStatus(err.message || label("cheque_edit_error", "Could not save cheque changes."), true);
      });
  }

  document.addEventListener("click", function (ev) {
    if (actions && actions.contains(ev.target)) {
      if (ev.target.closest("[data-cheque-edit]")) {
        ev.preventDefault();
        enterEdit();
        return;
      }
      if (ev.target.closest("[data-cheque-cancel]")) {
        ev.preventDefault();
        cancelEdit();
        return;
      }
      if (ev.target.closest("[data-cheque-save]")) {
        ev.preventDefault();
        saveEdit();
        return;
      }
    }

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
      if (editMode) {
        ev.preventDefault();
        cancelEdit();
        return;
      }
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
