/* Login-only enhancement. Do not bind menus or replace LMS event handlers. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  document.querySelectorAll("[data-vr-password-toggle]").forEach(button => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input || input.type !== "password") return;
    button.hidden = false;
    button.addEventListener("click", () => {
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.textContent = visible ? "숨기기" : "보기";
      button.setAttribute("aria-pressed", String(visible));
    });
  });
});
