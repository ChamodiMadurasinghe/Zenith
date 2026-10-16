// Zenith simple UI — small behaviours shared by every page. No framework.
(function () {
  "use strict";

  // Avatar menu
  document.querySelectorAll("[data-menu-toggle]").forEach(function (toggle) {
    var menu = document.getElementById(toggle.getAttribute("aria-controls"));
    if (!menu) return;

    function close() {
      menu.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      var open = menu.hidden;
      menu.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (event) {
      if (!menu.contains(event.target)) close();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") close();
    });
  });

  // Help dialog
  var help = document.getElementById("help-dialog");
  if (help && typeof help.showModal === "function") {
    document.querySelectorAll("[data-help-open]").forEach(function (button) {
      button.addEventListener("click", function () { help.showModal(); });
    });
    help.querySelectorAll("[data-help-close]").forEach(function (button) {
      button.addEventListener("click", function () { help.close(); });
    });
  }

  // Mobile language picker: each option's value is the switch URL.
  document.querySelectorAll("[data-lang-select]").forEach(function (select) {
    select.addEventListener("change", function () { window.location.href = select.value; });
  });

  // "Add a photo of an invoice": upload as soon as a photo is chosen.
  document.querySelectorAll("[data-photo-input]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (input.files && input.files.length) input.closest("form").submit();
    });
  });
})();
