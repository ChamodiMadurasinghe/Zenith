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
