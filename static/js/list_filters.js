(function () {
  document.querySelectorAll(".list-filter-bar").forEach((form) => {
    form.querySelectorAll("[data-filter-auto]").forEach((el) => {
      el.addEventListener("change", () => form.requestSubmit());
    });
  });
})();
