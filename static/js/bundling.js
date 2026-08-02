function getDealerId() {
  return String(
    window.__dealerId ||
      document.getElementById("bundle-workspace")?.dataset.dealer ||
      ""
  );
}

function formatLkr(n) {
  return Number(n).toLocaleString("en-LK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function i18n(key, vars) {
  if (typeof window.__ === "function") return window.__(key, vars);
  return key;
}

function getSelectedInvoiceIds() {
  return Array.from(document.querySelectorAll('input[name="invoice_ids"]:checked')).map((el) =>
    parseInt(el.value, 10)
  );
}

function getCeiling() {
  const el = document.querySelector('input[name="ceiling_lkr"]');
  return el ? parseFloat(el.value) : 500000;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderBundleCompleteBanner(count) {
  if (!count) return "";
  return `<div class="bundle-complete-banner" role="status">
    <span class="bundle-complete-icon" aria-hidden="true">✓</span>
    <strong>${i18n("bundling_complete", { count })}</strong>
  </div>`;
}

function renderBundleWarnings(issues) {
  if (!issues?.length) return "";
  const items = issues.map((issue) => `<li>${escapeHtml(issue)}</li>`).join("");
  return `<div class="bundle-warnings" role="alert">
    <div class="bundle-warnings-header">
      <span class="bundle-warnings-icon" aria-hidden="true">⚠</span>
      <strong>${i18n("bundle_warnings_title")}</strong>
    </div>
    <p>${i18n("bundle_warnings_intro")}</p>
    <ul class="bundle-warnings-list">${items}</ul>
  </div>`;
}

function renderPreviewForm(dealerId, issues) {
  const hasIssues = Boolean(issues?.length);
  const ack = hasIssues
    ? `<label class="bundle-warnings-ack confirm-label">
        <input type="checkbox" name="acknowledge_warnings" value="1" id="acknowledge-warnings">
        <strong>${i18n("bundle_warnings_ack")}</strong>
      </label>`
    : "";
  const btnLabel = hasIssues ? i18n("preview_anyway") : i18n("preview_cheques");
  const disabled = hasIssues ? " disabled" : "";
  return `<form method="post" action="/bundling/${dealerId}/preview" id="preview-bundles-form">
    ${ack}
    <button type="submit" class="btn btn-primary btn-lg" id="preview-bundles-btn"${disabled}>${btnLabel}</button>
  </form>`;
}

let previewReviewBound = false;

async function requestBundleReview(trigger) {
  const dealerId = getDealerId();
  if (!dealerId) return null;

  const thinking = window.appendChatMsg?.("assistant", i18n("js_reviewer_thinking"));
  thinking?.classList.add("chat-thinking");

  try {
    const res = await fetch(`/api/bundling/${dealerId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ trigger }),
    });
    thinking?.remove();

    const data = await res.json();
    if (!res.ok) {
      window.appendChatMsg?.("assistant", data.review || data.error || i18n("js_server_error", { status: res.status }));
      return null;
    }

    if (data.chat_history && window.renderChatHistory) {
      window.renderChatHistory(data.chat_history);
    } else if (data.review) {
      window.appendChatMsg?.("reviewer", data.review, {
        verdict: data.verdict,
        applied: false,
        reviewIndex: -1,
      });
      window.bindApplyReviewerButtons?.();
    }
    window.__pendingReview = null;
    return data;
  } catch (err) {
    thinking?.remove();
    window.appendChatMsg?.("assistant", i18n("js_unreachable"));
    return null;
  }
}

function bindPreviewWithReview() {
  const form = document.getElementById("preview-bundles-form");
  if (!form || previewReviewBound) return;
  previewReviewBound = true;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("preview-bundles-btn");
    if (btn) btn.disabled = true;
    await requestBundleReview("preview");
    if (btn) btn.disabled = false;
    form.submit();
  });
}

function bindWarningAcknowledgement() {
  const ack = document.getElementById("acknowledge-warnings");
  const btn = document.getElementById("preview-bundles-btn");
  if (!ack || !btn) return;
  const sync = () => {
    btn.disabled = !ack.checked;
  };
  ack.addEventListener("change", sync);
  sync();
}

function partKey(inv) {
  const id = inv.invoices_id;
  const count = parseInt(inv.part_count || 1, 10);
  const idx = inv.part_index;
  if (count > 1 && idx != null) return `${id}:${idx}`;
  return String(id);
}

function parsePartKey(key) {
  const s = String(key);
  if (s.includes(":")) {
    const [id, part] = s.split(":");
    return { invoiceId: parseInt(id, 10), partIndex: parseInt(part, 10) };
  }
  return { invoiceId: parseInt(s, 10), partIndex: null };
}

function displayInvoiceNo(inv) {
  if (inv.invoice_no_display) return inv.invoice_no_display;
  const base = inv.invoice_no || `#${inv.invoices_id}`;
  const count = parseInt(inv.part_count || 1, 10);
  if (count > 1 && inv.part_index != null) return `${base} · ${inv.part_index}`;
  return base;
}

function isSplitPart(inv) {
  return parseInt(inv.part_count || 1, 10) > 1 && inv.part_index != null;
}

function buildInvoicePartsPayload(bundles) {
  const parts = {};
  (bundles || []).forEach((b) => {
    (b.invoices || []).forEach((inv) => {
      if (isSplitPart(inv)) {
        parts[partKey(inv)] = {
          invoices_id: inv.invoices_id,
          total_amount: inv.total_amount,
          part_index: inv.part_index,
          part_count: inv.part_count,
          original_amount: inv.original_amount,
          invoice_no: inv.invoice_no,
        };
      }
    });
  });
  return parts;
}

function buildMoveOptions(bundles, currentGroup, invoiceId) {
  const groups = (bundles || []).map((b) => b.group);
  let html = `<option value="">${i18n("js_move_to")}</option>`;
  groups.forEach((g) => {
    if (g !== currentGroup) {
      html += `<option value="${g}">${i18n("col_cheque")} ${g}</option>`;
    }
  });
  html += `<option value="new">${i18n("js_move_new_cheque")}</option>`;
  return html;
}

function renderInvoiceChip(inv, bundles, currentGroup) {
  const key = partKey(inv);
  const moveOpts = buildMoveOptions(bundles, currentGroup, inv.invoices_id);
  const splitClass = isSplitPart(inv) ? " invoice-chip--split" : "";
  const labelClass = isSplitPart(inv) ? " invoice-chip-label--split" : "";
  return `<li class="invoice-chip${splitClass}" draggable="true"
      data-invoice-id="${inv.invoices_id}"
      data-part-key="${escapeHtml(key)}"
      data-part-index="${inv.part_index != null ? inv.part_index : ""}"
      data-part-count="${inv.part_count || 1}">
    <span class="invoice-chip-label${labelClass}">${escapeHtml(displayInvoiceNo(inv))} — Rs. ${formatLkr(inv.total_amount)}</span>
    <select class="move-invoice-select" data-part-key="${escapeHtml(key)}" data-invoice="${inv.invoices_id}" data-from-group="${currentGroup}" aria-label="${i18n("js_move_to")}">
      ${moveOpts}
    </select>
  </li>`;
}

function renderBundleCard(b, bundles) {
  const invoices = b.invoices || [];
  const interbankBadge = b.is_interbank
    ? `<span class="badge badge-pending">${i18n("interbank_badge")}</span>`
    : "";

  const chips = invoices.length
    ? invoices.map((inv) => renderInvoiceChip(inv, bundles, b.group)).join("")
    : `<li class="bundle-empty-hint">${i18n("bundle_editor_empty")}</li>`;

  return `<div class="bundle-card" data-group="${b.group}">
    <div class="bundle-card-header">
      <div class="bundle-card-meta">
        <strong>${i18n("col_cheque") || "Cheque"} ${b.group}</strong>
        <span class="bundle-card-total">Rs. ${formatLkr(b.total_lkr)}</span>
        ${interbankBadge}
      </div>
      <div class="bundle-card-dates">
        <label>${i18n("stated")}:
          <input type="date" class="bundle-date-input" data-group="${b.group}" value="${b.cheque_date}">
        </label>
        <span class="bundle-liquidity-meta">
          ${i18n("settlement")}: ${b.true_settlement_date || "—"}
          | ${i18n("fund_by")}: ${b.target_funding_date || b.predicted_clearance_date || "—"}
          | ${i18n("days_gained")}: ${b.days_gained_total ?? b.days_gained_by_holiday_lag ?? 0}
        </span>
      </div>
    </div>
    <ul class="bundle-invoice-list" data-drop-group="${b.group}">${chips}</ul>
  </div>`;
}

function renderBundleEditorToolbar() {
  return `<div class="bundle-editor-toolbar">
    <p class="bundle-editor-hint">${i18n("drag_invoice_hint")}</p>
    <button type="button" id="auto-review-btn" class="btn btn-secondary">Auto-optimize bundles</button>
    <button type="button" id="add-cheque-btn" class="btn btn-secondary">${i18n("add_cheque")}</button>
  </div>`;
}

function renderBundles(bundles, validationIssues) {
  const proposalsEl = document.getElementById("bundle-proposals");
  if (!proposalsEl || !bundles || bundles.length === 0) return;

  const issues = validationIssues || window.__bundleIssues || [];
  window.__currentBundles = bundles;
  window.__bundleCount = bundles.length;
  window.__bundleIssues = issues;

  let html = renderBundleCompleteBanner(bundles.length);
  html += renderBundleWarnings(issues);
  html += `<h3>${i18n("proposed_groups")}</h3>`;
  html += renderBundleEditorToolbar();
  bundles.forEach((b) => {
    html += renderBundleCard(b, bundles);
  });

  const dealerId = getDealerId();
  if (dealerId) {
    html += renderPreviewForm(dealerId, issues);
  }

  proposalsEl.innerHTML = html;
  previewReviewBound = false;
  bindBundleControls(bundles);
  bindWarningAcknowledgement();
  bindPreviewWithReview();
  bindDragDrop();
  bindMoveSelects();
  bindAddCheque();
  bindAutoReviewButton();
  bindInvoiceContextMenu();
}

function buildAssignmentsFromBundles(bundles) {
  const assignments = {};
  bundles.forEach((b) => {
    (b.invoices || []).forEach((inv) => {
      assignments[partKey(inv)] = b.group;
    });
  });
  return assignments;
}

function buildChequeDatesFromBundles(bundles) {
  const dates = {};
  bundles.forEach((b) => {
    dates[b.group] = b.cheque_date;
  });
  return dates;
}

function getEmptyGroups(bundles) {
  return (bundles || []).filter((b) => !(b.invoices || []).length).map((b) => b.group);
}

function resolveTargetGroup(bundles, target) {
  if (target === "new") {
    const maxGroup = bundles.reduce((m, b) => Math.max(m, b.group), 0);
    return maxGroup + 1;
  }
  return parseInt(target, 10);
}

function applyInvoiceMove(bundles, partKeyOrId, targetGroup) {
  const assignments = buildAssignmentsFromBundles(bundles);
  assignments[String(partKeyOrId)] = targetGroup;
  const emptyGroups = getEmptyGroups(bundles).filter((g) => g !== targetGroup);

  return {
    assignments,
    chequeDates: buildChequeDatesFromBundles(bundles),
    emptyGroups,
    invoiceParts: buildInvoicePartsPayload(bundles),
  };
}

async function postManualUpdate(assignments, chequeDates, onePerInvoice = false, emptyGroups = [], invoiceParts = null) {
  const dealerId = getDealerId();
  if (!dealerId) return;
  const current = window.__currentBundles || [];
  const res = await fetch(`/bundling/${dealerId}/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      invoice_assignments: assignments,
      cheque_dates: chequeDates,
      ceiling_lkr: getCeiling(),
      one_per_invoice: onePerInvoice,
      empty_groups: emptyGroups,
      invoice_parts: invoiceParts || buildInvoicePartsPayload(current),
    }),
  });
  const data = await res.json();
  if (data.error && !data.bundles) {
    alert(data.error);
    return;
  }
  if (data.bundles) {
    renderBundles(data.bundles, data.validation_issues);
  }
}

async function postManualActions(actions) {
  const dealerId = getDealerId();
  if (!dealerId) return;
  const res = await fetch(`/bundling/${dealerId}/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actions,
      ceiling_lkr: getCeiling(),
    }),
  });
  const data = await res.json();
  if (data.error && !data.bundles) {
    alert(data.error);
    return;
  }
  if (data.bundles) {
    renderBundles(data.bundles, data.validation_issues);
  }
}

function bindBundleControls(bundles) {
  document.querySelectorAll(".bundle-date-input").forEach((input) => {
    input.addEventListener("change", () => {
      const current = window.__currentBundles || bundles;
      const dates = buildChequeDatesFromBundles(current);
      dates[parseInt(input.dataset.group, 10)] = input.value;
      postManualUpdate(
        buildAssignmentsFromBundles(current),
        dates,
        false,
        getEmptyGroups(current)
      );
    });
  });
}

function bindDragDrop() {
  let draggedPartKey = null;

  document.querySelectorAll(".invoice-chip").forEach((chip) => {
    chip.addEventListener("dragstart", (e) => {
      draggedPartKey = chip.dataset.partKey || String(chip.dataset.invoiceId);
      chip.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", draggedPartKey);
    });
    chip.addEventListener("dragend", () => {
      chip.classList.remove("dragging");
      draggedPartKey = null;
      document.querySelectorAll(".bundle-invoice-list.drag-over").forEach((el) => {
        el.classList.remove("drag-over");
      });
    });
  });

  document.querySelectorAll(".bundle-invoice-list").forEach((list) => {
    list.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      list.classList.add("drag-over");
    });
    list.addEventListener("dragleave", (e) => {
      if (!list.contains(e.relatedTarget)) {
        list.classList.remove("drag-over");
      }
    });
    list.addEventListener("drop", (e) => {
      e.preventDefault();
      list.classList.remove("drag-over");
      const key = draggedPartKey || e.dataTransfer.getData("text/plain");
      const toGroup = parseInt(list.dataset.dropGroup, 10);
      if (!key || !toGroup) return;

      const current = window.__currentBundles || [];
      const fromGroup = parseInt(
        document.querySelector(`.invoice-chip[data-part-key="${String(key).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"]`)?.closest(".bundle-card")
          ?.dataset.group,
        10
      );
      if (fromGroup === toGroup) return;

      const parsed = parsePartKey(key);
      const actions = [
        {
          action: "move_invoice",
          invoice_id: parsed.invoiceId,
          to_group: toGroup,
          ...(parsed.partIndex != null ? { part_index: parsed.partIndex } : {}),
        },
      ];
      postManualActions(actions);
    });
  });
}

function bindMoveSelects() {
  document.querySelectorAll(".move-invoice-select").forEach((select) => {
    select.addEventListener("change", () => {
      const value = select.value;
      if (!value) return;

      const key = select.dataset.partKey || String(select.dataset.invoice);
      const current = window.__currentBundles || [];
      const targetGroup = resolveTargetGroup(current, value);
      const parsed = parsePartKey(key);
      postManualActions([
        {
          action: "move_invoice",
          invoice_id: parsed.invoiceId,
          to_group: targetGroup,
          ...(parsed.partIndex != null ? { part_index: parsed.partIndex } : {}),
        },
      ]);
      select.value = "";
    });
  });
}

function hideInvoiceContextMenu() {
  document.getElementById("invoice-context-menu")?.remove();
}

function bindInvoiceContextMenu() {
  hideInvoiceContextMenu();
  document.querySelectorAll(".invoice-chip").forEach((chip) => {
    chip.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      hideInvoiceContextMenu();
      const invoiceId = parseInt(chip.dataset.invoiceId, 10);
      const partCount = parseInt(chip.dataset.partCount || "1", 10);
      const menu = document.createElement("div");
      menu.id = "invoice-context-menu";
      menu.className = "invoice-context-menu";
      menu.style.left = `${e.clientX}px`;
      menu.style.top = `${e.clientY}px`;
      menu.innerHTML = `
        <button type="button" data-act="split">${i18n("js_split_invoice")}</button>
        <button type="button" data-act="split-keep">${i18n("js_split_same_cheque")}</button>
        ${partCount > 1 ? `<button type="button" data-act="unsplit">${i18n("js_unsplit_invoice")}</button>` : ""}
      `;
      document.body.appendChild(menu);

      menu.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const act = btn.dataset.act;
          hideInvoiceContextMenu();
          if (act === "unsplit") {
            // Re-merge by splitting into 1 is not supported — reload full via num_parts omit + assign alone
            // Recombine: split with num_parts of original into 1 cheque by using amounts = [full]
            // Use split with separate_cheques false after restoring — simplest: ask user to recompute.
            // Better: call split with amounts=[original] is invalid (<2). Emit move of all parts onto group 1 then...
            // For unsplit: apply action that reconstructs — use custom path via split with merging in guardrails
            // We'll send split_invoice num_parts: 1 meaning "put alone as whole" after removing parts —
            // Implement unsplit as: get original from first part and replace all parts with one full invoice via actions
            const current = window.__currentBundles || [];
            let original = null;
            let hostGroup = 1;
            current.forEach((b) => {
              (b.invoices || []).forEach((inv) => {
                if (inv.invoices_id === invoiceId && isSplitPart(inv)) {
                  original = inv.original_amount || inv.total_amount;
                  hostGroup = b.group;
                }
              });
            });
            if (original == null) return;
            // Remove parts by re-splitting to 2 then... hack: use assign rebuild
            // Prefer dedicated: split_invoice with amounts that is invalid.
            // Server: if num_parts==1 treat as unsplit — add quickly
            postManualActions([
              { action: "split_invoice", invoice_id: invoiceId, num_parts: 1 },
            ]);
            return;
          }
          const raw = window.prompt(i18n("js_split_how_many"), "2");
          if (raw == null) return;
          const n = parseInt(raw, 10);
          if (!n || n < 2) {
            alert(i18n("js_split_need_two"));
            return;
          }
          postManualActions([
            {
              action: "split_invoice",
              invoice_id: invoiceId,
              num_parts: n,
              separate_cheques: act !== "split-keep",
            },
          ]);
        });
      });
    });
  });

  document.addEventListener("click", hideInvoiceContextMenu, { once: true });
}

function bindAddCheque() {
  document.getElementById("add-cheque-btn")?.addEventListener("click", () => {
    const current = window.__currentBundles || [];
    const maxGroup = current.reduce((m, b) => Math.max(m, b.group), 0);
    const emptyGroups = [...getEmptyGroups(current), maxGroup + 1];
    postManualUpdate(
      buildAssignmentsFromBundles(current),
      buildChequeDatesFromBundles(current),
      false,
      emptyGroups
    );
  });
}

function bindAutoReviewButton() {
  document.getElementById("auto-review-btn")?.addEventListener("click", runAutoReview);
}

async function runAutoReview() {
  const dealerId = getDealerId();
  if (!dealerId) return;
  const btn = document.getElementById("auto-review-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Reviewer round 1/3...";
  }
  try {
    const res = await fetch(`/api/bundling/${dealerId}/auto-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ max_rounds: 3 }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Auto-review failed");
      return;
    }
    if (data.chat_history && window.renderChatHistory) {
      window.renderChatHistory(data.chat_history);
    }
    if (data.bundles) {
      renderBundles(data.bundles, data.validation_issues || []);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Auto-optimize bundles";
    }
  }
}

function bindSelectAllInvoices() {
  const selectAll = document.getElementById("select-all-invoices");
  const boxes = document.querySelectorAll('input[name="invoice_ids"]');
  if (!selectAll || !boxes.length) return;

  function syncSelectAllState() {
    const checked = document.querySelectorAll('input[name="invoice_ids"]:checked').length;
    selectAll.checked = checked === boxes.length;
    selectAll.indeterminate = checked > 0 && checked < boxes.length;
  }

  selectAll.addEventListener("change", () => {
    boxes.forEach((box) => {
      box.checked = selectAll.checked;
    });
    selectAll.indeterminate = false;
  });

  boxes.forEach((box) => box.addEventListener("change", syncSelectAllState));
  syncSelectAllState();
}

async function maybeRunPendingReview() {
  if (window.__pendingReview !== "compute" || !window.__currentBundles?.length) return;
  await requestBundleReview("compute");
}

function initBundling() {
  if (window.__currentBundles?.length) {
    renderBundles(window.__currentBundles, window.__bundleIssues);
    maybeRunPendingReview();
  }

  document.getElementById("one-per-invoice-btn")?.addEventListener("click", () => {
    const ids = getSelectedInvoiceIds();
    if (!ids.length) {
      alert(i18n("js_select_invoice"));
      return;
    }
    const assignments = {};
    ids.forEach((id, i) => {
      assignments[id] = i + 1;
    });
    postManualUpdate(assignments, {}, true);
  });

  bindSelectAllInvoices();
  bindWarningAcknowledgement();
  bindAutoReviewButton();
}

window.renderBundles = renderBundles;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initBundling);
} else {
  initBundling();
}
