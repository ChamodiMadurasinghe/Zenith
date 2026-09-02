(function () {
  var panel = document.getElementById("agent2-audit-panel");
  if (!panel) return;
  var chat = document.getElementById("agent2-chat");
  if (chat) {
    chat.scrollTop = chat.scrollHeight;
  }
  if (panel.classList.contains("audit-issue_detected")) {
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
})();
