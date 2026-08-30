document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("a.external").forEach((link) => {
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  });
});
