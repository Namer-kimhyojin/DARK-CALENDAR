(() => {
  "use strict";

  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const imageDirectory = "assets/screenshots/interactive/";
  const themeStorageKey = "aircalendar-site-theme";

  function setupSiteTheme() {
    const toggle = document.querySelector("[data-site-theme-toggle]");
    const themeColor = document.querySelector('meta[name="theme-color"]');
    let preference;
    try {
      preference = localStorage.getItem(themeStorageKey);
    } catch {
      // The theme still works when the browser blocks storage.
    }

    function renderTheme() {
      const dark = preference === "dark" || (preference !== "light" && systemDark.matches);
      root.dataset.siteTheme = dark ? "dark" : "light";
      toggle.setAttribute("aria-pressed", String(dark));
      toggle.title = toggle.getAttribute("aria-label");
      themeColor.content = dark ? "#0c1324" : "#ffffff";
    }

    toggle.addEventListener("click", () => {
      preference = root.dataset.siteTheme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(themeStorageKey, preference);
      } catch {
        // The selection remains active for this page visit.
      }
      renderTheme();
    });
    systemDark.addEventListener("change", renderTheme);
    document.addEventListener("aircalendar:language", renderTheme);
    renderTheme();
    toggle.hidden = false;
  }

  function setupWidgetDemo() {
    const demo = document.querySelector("[data-widget-demo]");
    const stage = demo.querySelector("[data-widget-stage]");
    const background = demo.querySelector("[data-widget-back]");
    const ink = demo.querySelector("[data-widget-ink]");
    const slider = demo.querySelector("[data-widget-opacity]");
    const value = demo.querySelector("[data-widget-opacity-value]");
    const inputs = demo.querySelector("[data-widget-inputs]");
    const settings = document.querySelector("[data-demo-settings]");
    const modeInputs = demo.querySelectorAll('input[name="widget-mode"]');
    const colorInputs = demo.querySelectorAll('input[name="widget-color"]');

    function renderWidget() {
      const mode = demo.querySelector('input[name="widget-mode"]:checked').value;
      const color = demo.querySelector('input[name="widget-color"]:checked').value;
      stage.dataset.mode = mode;
      background.src = `${imageDirectory}${mode}-${color}.webp`;
      ink.src = `${imageDirectory}${mode}-ink.webp`;
      settings.src = `${imageDirectory}appearance-${mode}.webp`;
    }

    function renderOpacity() {
      const percent = `${slider.value}%`;
      stage.style.setProperty("--widget-opacity", String(slider.valueAsNumber / 100));
      slider.setAttribute("aria-valuetext", percent);
      value.textContent = percent;
    }

    for (const input of modeInputs) input.checked = input.value === root.dataset.siteTheme;
    for (const input of [...modeInputs, ...colorInputs]) input.addEventListener("change", renderWidget);
    slider.addEventListener("input", renderOpacity);
    renderWidget();
    renderOpacity();
    inputs.hidden = false;

    // Load the small native layers as the visitor approaches the demo.
    if ("IntersectionObserver" in window) {
      const loader = new IntersectionObserver(([entry]) => {
        if (!entry.isIntersecting) return;
        loader.disconnect();
        for (const { value: mode } of modeInputs) {
          const layers = [...Array.from(colorInputs, input => input.value), "ink"];
          for (const layer of layers) new Image().src = `${imageDirectory}${mode}-${layer}.webp`;
        }
      }, { rootMargin: "320px" });
      loader.observe(demo);
    }
  }

  function setupGif(demo) {
    const image = demo.querySelector("[data-motion-image]");
    const button = demo.querySelector("[data-motion-toggle]");
    const poster = image.getAttribute("src");
    const animation = image.dataset.animation;
    let enabled = !reducedMotion.matches;
    let visible = !("IntersectionObserver" in window);

    function renderPlayback() {
      const source = enabled && visible && !document.hidden ? animation : poster;
      if (image.getAttribute("src") !== source) image.src = source;
      const key = enabled ? "motionStop" : "motionPlay";
      const language = root.lang.split("-")[0];
      const copy = window.AirCalendarHomepage;
      button.dataset.i18n = key;
      button.textContent = (copy[language] || copy.ko)[key];
    }

    button.addEventListener("click", () => {
      enabled = !enabled;
      renderPlayback();
    });
    image.addEventListener("error", () => {
      if (image.getAttribute("src") !== animation) return;
      enabled = false;
      renderPlayback();
    });
    reducedMotion.addEventListener("change", () => {
      enabled = !reducedMotion.matches;
      renderPlayback();
    });
    document.addEventListener("visibilitychange", renderPlayback);
    document.addEventListener("aircalendar:language", renderPlayback);
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting && entry.intersectionRatio >= .25;
        renderPlayback();
      }, { threshold: .25 });
      observer.observe(image);
    }
    renderPlayback();
    button.hidden = false;
  }

  function setupEntranceMotion() {
    if (!("IntersectionObserver" in window) || reducedMotion.matches) return;
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("home-entered");
        observer.unobserve(entry.target);
      }
    }, { threshold: .12 });
    document.querySelectorAll(".hero-copy, .hero-product, .section-heading, .appearance-lab, .workspace-screens, .widget-showcase-grid, .sync-overview").forEach(node => observer.observe(node));
  }

  setupSiteTheme();
  setupWidgetDemo();
  document.querySelectorAll("[data-gif-demo]").forEach(setupGif);
  setupEntranceMotion();
})();
