(() => {
  "use strict";

  const routes = {
    ko: "sync-guide.html",
    en: "sync-guide-en.html",
    ja: "sync-guide-ja.html",
    zh: "sync-guide-zh.html"
  };
  const preferenceKey = "dark-calendar-language";
  const url = new URL(window.location.href);
  const pageLanguage = document.documentElement.dataset.guideLocale || "ko";

  function normalize(value) {
    const language = String(value || "").toLowerCase().replaceAll("_", "-");
    return Object.keys(routes).find((code) => language === code || language.startsWith(`${code}-`));
  }

  let savedLanguage;
  try {
    savedLanguage = normalize(window.localStorage.getItem(preferenceKey));
  } catch (_error) {
    // Direct language links also work when browser storage is unavailable.
  }
  const explicitLanguage = normalize(url.searchParams.get("lang"));
  const language = explicitLanguage || (pageLanguage === "ko"
    ? savedLanguage || normalize(window.navigator.language) || "ko"
    : pageLanguage);

  if (language !== pageLanguage) {
    const target = new URL(routes[language], url);
    target.search = url.search;
    if (language === "ko") target.searchParams.set("lang", "ko");
    else target.searchParams.delete("lang");
    target.hash = url.hash;
    window.location.replace(target.href);
    return;
  }

  try {
    window.localStorage.setItem(preferenceKey, language);
  } catch (_error) {
    // Persistence is optional; native links provide all four complete guides.
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-guide-language]").forEach((link) => {
      link.addEventListener("click", () => {
        const target = new URL(link.href);
        target.hash = window.location.hash;
        link.href = target.href;
      });
    });
  });
})();
