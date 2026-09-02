/** Bank account tabs — swap detail panel without full page reload (keeps scroll position). */

function highlightLiquidityRows(root) {
  (root || document).querySelectorAll("#liquidity-timetable tbody tr").forEach((row) => {
    const daysCell = row.cells[4];
    if (daysCell && parseInt(daysCell.textContent, 10) > 0) {
      row.classList.add("row-gain");
    }
  });
}

function setActiveAccountCard(switcher, accountId) {
  switcher.querySelectorAll(".account-card").forEach((card) => {
    const id = card.dataset.accountId;
    const active = id === String(accountId);
    card.classList.toggle("active", active);
    card.setAttribute("aria-selected", active ? "true" : "false");
  });
}

async function loadAccountPanel(accountId, card, switcher, panel, pushUrl) {
  if (card?.classList.contains("active")) return;

  switcher?.classList.add("is-switching");
  if (card) card.classList.add("is-loading");

  try {
    const res = await fetch(`/api/cash-flow/${accountId}/panel`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error("panel fetch failed");
    const data = await res.json();
    panel.innerHTML = data.html;
    setActiveAccountCard(switcher, accountId);
    if (pushUrl && card?.href) {
      history.pushState({ accountId }, "", card.href);
    }
    highlightLiquidityRows(panel);
    if (typeof window.zenithBindForms === "function") {
      window.zenithBindForms(panel);
    }
  } catch (err) {
    if (card?.href) {
      window.location.href = card.href;
    }
  } finally {
    switcher?.classList.remove("is-switching");
    if (card) card.classList.remove("is-loading");
  }
}

function initAccountSwitcher() {
  const switcher = document.querySelector(".account-switcher");
  const panel = document.getElementById("cash-flow-account-panel");
  if (!switcher || !panel) return;

  highlightLiquidityRows(panel);

  switcher.addEventListener("click", (e) => {
    const card = e.target.closest(".account-card");
    if (!card || !card.dataset.accountId) return;
    if (card.classList.contains("active")) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    loadAccountPanel(card.dataset.accountId, card, switcher, panel, true);
  });

  window.addEventListener("popstate", (e) => {
    const accountId = e.state?.accountId;
    if (!accountId) return;
    const card = switcher.querySelector(`.account-card[data-account-id="${accountId}"]`);
    loadAccountPanel(String(accountId), card, switcher, panel, false);
  });

  const active = switcher.querySelector(".account-card.active");
  if (active?.dataset.accountId) {
    history.replaceState(
      { accountId: active.dataset.accountId },
      "",
      window.location.href
    );
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAccountSwitcher);
} else {
  initAccountSwitcher();
}
