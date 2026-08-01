/** Max-liquidity timetable — highlight rows where holiday lag gained extra days. */
document.querySelectorAll("#liquidity-timetable tbody tr").forEach((row) => {
  const daysCell = row.cells[4];
  if (daysCell && parseInt(daysCell.textContent, 10) > 0) {
    row.classList.add("row-gain");
  }
});
