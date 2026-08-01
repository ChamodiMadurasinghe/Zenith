document.getElementById("add-item")?.addEventListener("click", () => {
  const tbody = document.querySelector("#items-table tbody");
  const template = document.querySelector(".item-template");
  if (!tbody || !template) return;
  const row = template.cloneNode(true);
  row.classList.remove("item-template");
  tbody.appendChild(row);
});
