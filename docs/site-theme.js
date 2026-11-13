(() => {
  "use strict";

  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const storageKey = "aircalendar-site-theme";
  let preference;
  try {
    preference = localStorage.getItem(storageKey);
  } catch {
    // The site can still use the system preference.
  }

  function applyTheme() {
    const dark = preference === "dark" || (preference !== "light" && systemDark.matches);
    root.dataset.siteTheme = dark ? "dark" : "light";
    return dark;
  }

  applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector("[data-site-theme-toggle]");
    const themeColor = document.querySelector('meta[name="theme-color"]');

    function renderTheme() {
      const dark = applyTheme();
      if (toggle) {
        toggle.setAttribute("aria-pressed", String(dark));
        toggle.title = toggle.getAttribute("aria-label");
      }
      if (themeColor) themeColor.content = getComputedStyle(root).getPropertyValue("--bg").trim();
    }

    toggle?.addEventListener("click", () => {
      preference = root.dataset.siteTheme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(storageKey, preference);
      } catch {
        // The selection remains active for this page visit.
      }
      renderTheme();
    });
    systemDark.addEventListener("change", renderTheme);
    document.addEventListener("aircalendar:language", renderTheme);
    renderTheme();
    if (toggle) toggle.hidden = false;
  });
})();
