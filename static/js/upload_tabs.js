(function () {
  "use strict";

  var root = document.querySelector(".intake-tabs");
  if (!root) return;

  var tabs = root.querySelectorAll(".tab-btn");
  var panels = root.querySelectorAll(".tab-panel");
  var fileInput = document.getElementById("invoice_image");
  var fileLabel = document.getElementById("upload-filename");

  function showTab(name) {
    tabs.forEach(function (tab) {
      var active = tab.dataset.tab === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach(function (panel) {
      var active = panel.dataset.panel === name;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      showTab(tab.dataset.tab);
    });
  });

  if (fileInput && fileLabel) {
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      fileLabel.textContent = file ? file.name : "";
    });
  }

  showTab("upload");
})();
