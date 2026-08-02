/**
 * Client-side validation for Zenith forms (required fields + uniqueness).
 * Mark forms with data-zenith-validate. Optional:
 *   data-check-dealer-exclude="<id>"
 *   data-check-invoice-exclude="<id>"
 */
(function () {
  function t(key) {
    return (window.__ && window.__(key)) || key;
  }

  function clearFieldError(el) {
    if (!el) return;
    el.classList.remove("field-invalid");
    el.removeAttribute("aria-invalid");
    const wrap = el.closest("label") || el.parentElement;
    if (!wrap) return;
    wrap.querySelectorAll(".field-error-msg").forEach((n) => n.remove());
  }

  function setFieldError(el, message) {
    if (!el) return;
    clearFieldError(el);
    el.classList.add("field-invalid");
    el.setAttribute("aria-invalid", "true");
    const wrap = el.closest("label") || el.parentElement;
    if (!wrap) return;
    const msg = document.createElement("span");
    msg.className = "field-error-msg";
    msg.textContent = message;
    wrap.appendChild(msg);
  }

  function isEmpty(el) {
    if (!el) return true;
    if (el.type === "checkbox" || el.type === "radio") return !el.checked;
    if (el.type === "file") return !(el.files && el.files.length);
    return !(el.value || "").toString().trim();
  }

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("check failed");
    return res.json();
  }

  async function checkDealerName(name, excludeId) {
    const base = (window.__zenithChecks && window.__zenithChecks.dealerName) || "";
    if (!base || !name) return true;
    const url = new URL(base, window.location.origin);
    url.searchParams.set("name", name);
    if (excludeId) url.searchParams.set("exclude_id", excludeId);
    const data = await fetchJson(url.toString());
    return !!data.available;
  }

  async function checkInvoiceNo(invoiceNo, dealerId, excludeId) {
    const base = (window.__zenithChecks && window.__zenithChecks.invoiceNo) || "";
    if (!base || !invoiceNo || !dealerId) return true;
    const url = new URL(base, window.location.origin);
    url.searchParams.set("invoice_no", invoiceNo);
    url.searchParams.set("dealer_id", dealerId);
    if (excludeId) url.searchParams.set("exclude_id", excludeId);
    const data = await fetchJson(url.toString());
    return !!data.available;
  }

  function validateRequired(form) {
    let ok = true;
    const fields = form.querySelectorAll(
      "input[required], select[required], textarea[required]"
    );
    fields.forEach((el) => {
      clearFieldError(el);
      if (el.disabled) return;
      if (isEmpty(el)) {
        ok = false;
        if (el.type === "checkbox") {
          setFieldError(el, t("js_confirm_required"));
        } else if (el.type === "file") {
          setFieldError(el, t("js_file_required"));
        } else if (el.name === "dealer_id") {
          setFieldError(el, t("js_select_dealer"));
        } else {
          setFieldError(el, t("js_required_field"));
        }
      }
    });
    return ok;
  }

  function validateNumbers(form) {
    let ok = true;
    const amount = form.querySelector('input[name="total_amount"], input[name="amount"]');
    if (amount && (amount.value || "").trim() !== "") {
      const n = Number(amount.value);
      if (!Number.isFinite(n) || n <= 0) {
        setFieldError(amount, t("js_invalid_amount"));
        ok = false;
      }
    }
    const credit = form.querySelector('input[name="credit_period_days"]');
    if (credit && (credit.value || "").trim() !== "") {
      const n = Number(credit.value);
      if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
        setFieldError(credit, t("js_invalid_number"));
        ok = false;
      }
    }
    const casual = form.querySelector('input[name="casual_days"]');
    if (casual && (casual.value || "").trim() !== "") {
      const n = Number(casual.value);
      if (!Number.isFinite(n) || n < 0) {
        setFieldError(casual, t("js_invalid_number"));
        ok = false;
      }
    }
    return ok;
  }

  async function validateUniqueness(form) {
    let ok = true;
    const dealerName = form.querySelector('input[name="dealer_name"]');
    const reuseExisting = form.getAttribute("data-reuse-existing-dealer") === "1";
    if (dealerName && (dealerName.value || "").trim() && !reuseExisting) {
      const exclude = form.getAttribute("data-check-dealer-exclude") || "";
      try {
        const available = await checkDealerName(dealerName.value.trim(), exclude);
        if (!available) {
          setFieldError(dealerName, t("js_dealer_duplicate"));
          ok = false;
        }
      } catch (_) {
        /* server will re-check */
      }
    }

    const invoiceNo = form.querySelector('input[name="invoice_no"]');
    const dealerIdEl = form.querySelector('select[name="dealer_id"]');
    if (invoiceNo && dealerIdEl && (invoiceNo.value || "").trim() && dealerIdEl.value) {
      const exclude = form.getAttribute("data-check-invoice-exclude") || "";
      try {
        const available = await checkInvoiceNo(
          invoiceNo.value.trim(),
          dealerIdEl.value,
          exclude
        );
        if (!available) {
          setFieldError(invoiceNo, t("js_invoice_duplicate"));
          ok = false;
        }
      } catch (_) {
        /* server will re-check */
      }
    }
    return ok;
  }

  function bindForm(form) {
    if (form.dataset.zenithBound === "1") return;
    form.dataset.zenithBound = "1";

    form.addEventListener("submit", async function (ev) {
      // Allow HTML5 first pass for browsers that support it, then our checks.
      if (typeof form.checkValidity === "function" && !form.checkValidity()) {
        // Let browser show native tooltips; still paint our messages for consistency.
        validateRequired(form);
        return;
      }

      ev.preventDefault();
      form.querySelectorAll(".field-invalid").forEach((el) => clearFieldError(el));

      const requiredOk = validateRequired(form);
      const numbersOk = validateNumbers(form);
      if (!requiredOk || !numbersOk) return;

      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      try {
        const uniqueOk = await validateUniqueness(form);
        if (!uniqueOk) return;
        form.submit();
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });

    // Live uniqueness for invoice_no / dealer when fields change
    const invoiceNo = form.querySelector('input[name="invoice_no"]');
    const dealerIdEl = form.querySelector('select[name="dealer_id"]');
    const dealerName = form.querySelector('input[name="dealer_name"]');

    let debounceTimer = null;
    function scheduleCheck(fn) {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(fn, 350);
    }

    if (invoiceNo && dealerIdEl) {
      const run = () =>
        scheduleCheck(async () => {
          clearFieldError(invoiceNo);
          if (!invoiceNo.value.trim() || !dealerIdEl.value) return;
          try {
            const available = await checkInvoiceNo(
              invoiceNo.value.trim(),
              dealerIdEl.value,
              form.getAttribute("data-check-invoice-exclude") || ""
            );
            if (!available) setFieldError(invoiceNo, t("js_invoice_duplicate"));
          } catch (_) {}
        });
      invoiceNo.addEventListener("blur", run);
      dealerIdEl.addEventListener("change", run);
    }

    if (dealerName && form.getAttribute("data-reuse-existing-dealer") !== "1") {
      dealerName.addEventListener("blur", () => {
        scheduleCheck(async () => {
          clearFieldError(dealerName);
          if (!dealerName.value.trim()) return;
          try {
            const available = await checkDealerName(
              dealerName.value.trim(),
              form.getAttribute("data-check-dealer-exclude") || ""
            );
            if (!available) setFieldError(dealerName, t("js_dealer_duplicate"));
          } catch (_) {}
        });
      });
    }
  }

  function init() {
    document.querySelectorAll("form[data-zenith-validate]").forEach(bindForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
