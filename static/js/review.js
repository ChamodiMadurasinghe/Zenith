function fillLineTotal(row) {
  const qty = Number(row.querySelector('[name="item_qty"]')?.value || 0);
  const price = Number(row.querySelector('[name="item_price"]')?.value || 0);
  const disc = Number(row.querySelector('[name="item_discount"]')?.value || 0);
  const totalInput = row.querySelector('[name="item_line_total"]');
  if (!totalInput) return;
  const total = qty * price * Math.max(0, 1 - disc / 100);
  totalInput.value = total.toFixed(2);
}

document.getElementById("add-item")?.addEventListener("click", () => {
  const tbody = document.querySelector("#items-table tbody");
  const template = document.querySelector(".item-template");
  if (!tbody || !template) return;
  const row = template.cloneNode(true);
  row.classList.remove("item-template");
  tbody.appendChild(row);
  fillLineTotal(row);
});

document.getElementById("items-table")?.addEventListener("input", (event) => {
  const name = event.target?.name;
  if (!["item_qty", "item_price", "item_discount"].includes(name)) return;
  const row = event.target.closest("tr");
  if (row) fillLineTotal(row);
});


/* Excel-style column resize for #items-table */
(function initItemsTableColumnResize() {
  const table = document.getElementById("items-table");
  if (!table) return;

  const STORAGE_KEY = "zenith-items-table-col-widths";
  const EDGE_PX = 8;
  const MIN_COL = 56;

  table.classList.add("items-table-resizable");
  // Prefer fixed layout while resizing so widths stick
  table.style.tableLayout = "fixed";

  const heads = Array.from(table.querySelectorAll("thead th"));
  if (!heads.length) return;

  function loadWidths() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function saveWidths(widths) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
    } catch (_) {}
  }

  function applyWidths(widths) {
    heads.forEach((th, i) => {
      const w = widths[i];
      if (!w) return;
      th.style.width = w + "px";
      th.style.minWidth = w + "px";
    });
  }

  const saved = loadWidths();
  if (saved && Array.isArray(saved) && saved.length === heads.length) {
    applyWidths(saved);
  }

  let drag = null;

  function onMove(event) {
    if (!drag) return;
    const dx = event.clientX - drag.startX;
    const next = Math.max(MIN_COL, drag.startW + dx);
    drag.th.style.width = next + "px";
    drag.th.style.minWidth = next + "px";
    drag.currentW = next;
  }

  function onUp() {
    if (!drag) return;
    document.body.classList.remove("col-resizing");
    const widths = heads.map((th) => Math.round(th.getBoundingClientRect().width));
    saveWidths(widths);
    drag = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  }

  heads.forEach((th) => {
    th.addEventListener("mousemove", (event) => {
      if (drag) return;
      const rect = th.getBoundingClientRect();
      const nearEdge = event.clientX >= rect.right - EDGE_PX;
      th.classList.toggle("col-resize-hover", nearEdge);
      th.style.cursor = nearEdge ? "col-resize" : "";
    });
    th.addEventListener("mouseleave", () => {
      if (drag) return;
      th.classList.remove("col-resize-hover");
      th.style.cursor = "";
    });
    th.addEventListener("mousedown", (event) => {
      const rect = th.getBoundingClientRect();
      if (event.clientX < rect.right - EDGE_PX) return;
      event.preventDefault();
      drag = {
        th,
        startX: event.clientX,
        startW: rect.width,
        currentW: rect.width,
      };
      document.body.classList.add("col-resizing");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  });
})();
