(function () {
  "use strict";

  window.OrkavynShell = {
    init() {
      const toggle = document.querySelector("[data-sidebar-toggle]");
      const shell = document.querySelector(".ork-shell");
      if (!toggle || !shell) return;

      toggle.addEventListener("click", () => {
        const open = shell.classList.toggle("is-sidebar-open");
        toggle.setAttribute("aria-expanded", String(open));
      });
    },
  };

  document.addEventListener("DOMContentLoaded", () => window.OrkavynShell.init());
})();
