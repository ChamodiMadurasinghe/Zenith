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

  const STORAGE_KEY = "zenith-items-table-col-widths-v3";
  const MIN_BY_INDEX = [130, 180, 64, 72, 100, 88, 100];
  const DEFAULTS = [168, 260, 72, 80, 118, 96, 110];

  table.classList.add("items-table-resizable");
  table.style.tableLayout = "fixed";
  table.style.width = "max-content";
  table.style.minWidth = "100%";

  const headRow = table.querySelector("thead tr");
  const heads = Array.from(table.querySelectorAll("thead th"));
  if (!headRow || !heads.length) return;

  // Visible drag grips on every header
  heads.forEach((th, i) => {
    th.classList.add("items-col-head");
    if (th.querySelector(".col-resize-handle")) return;
    const handle = document.createElement("span");
    handle.className = "col-resize-handle";
    handle.title = "Drag to resize column";
    handle.dataset.colIndex = String(i);
    th.appendChild(handle);
  });

  // Prefer <colgroup> so body cells follow header widths
  let colgroup = table.querySelector("colgroup");
  if (!colgroup) {
    colgroup = document.createElement("colgroup");
    heads.forEach(() => colgroup.appendChild(document.createElement("col")));
    table.insertBefore(colgroup, table.firstChild);
  }
  const cols = Array.from(colgroup.querySelectorAll("col"));

  function loadWidths() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (!Array.isArray(parsed) || parsed.length !== heads.length) return null;
      return parsed.map((w, i) => Math.max(MIN_BY_INDEX[i] || 72, Number(w) || DEFAULTS[i]));
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
    let total = 0;
    widths.forEach((w, i) => {
      const px = Math.max(MIN_BY_INDEX[i] || 72, w) + "px";
      if (cols[i]) {
        cols[i].style.width = px;
        cols[i].style.minWidth = px;
      }
      if (heads[i]) {
        heads[i].style.width = px;
        heads[i].style.minWidth = px;
        heads[i].style.maxWidth = px;
      }
      total += Math.max(MIN_BY_INDEX[i] || 72, w);
    });
    table.style.width = total + "px";
  }

  const initial = loadWidths() || DEFAULTS.slice(0, heads.length);
  applyWidths(initial);

  let drag = null;

  function onMove(event) {
    if (!drag) return;
    const dx = event.clientX - drag.startX;
    const next = Math.max(drag.minW, drag.startW + dx);
    const widths = cols.map((col, i) => {
      if (i === drag.index) return next;
      return Math.max(MIN_BY_INDEX[i] || 72, parseFloat(col.style.width) || DEFAULTS[i]);
    });
    applyWidths(widths);
    drag.currentW = next;
  }

  function onUp() {
    if (!drag) return;
    document.body.classList.remove("col-resizing");
    const widths = cols.map((col, i) =>
      Math.max(MIN_BY_INDEX[i] || 72, parseFloat(col.style.width) || DEFAULTS[i])
    );
    saveWidths(widths);
    drag = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  }

  table.querySelectorAll(".col-resize-handle").forEach((handle) => {
    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const index = Number(handle.dataset.colIndex);
      const startW = Math.max(
        MIN_BY_INDEX[index] || 72,
        parseFloat(cols[index]?.style.width) || heads[index].getBoundingClientRect().width
      );
      drag = {
        index,
        startX: event.clientX,
        startW,
        minW: MIN_BY_INDEX[index] || 72,
        currentW: startW,
      };
      document.body.classList.add("col-resizing");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  });
})();
