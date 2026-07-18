(function () {
  "use strict";

  const fallbackConfig = {
    appVersion: "3.6.1",
    microsoftStoreUrl: "https://apps.microsoft.com/detail/9mxq08rf22k8?hl=ko-KR&gl=KR&ocid=pdpshare",
    sourceCodeUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR",
    releaseSourceUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v3.6.1",
    licenseUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/blob/v3.6.1/LICENSE",
    thirdPartyNoticesUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/blob/v3.6.1/THIRD_PARTY_NOTICES.md",
    eventUrl: "https://account.microsoft.com/billing/redeem?mstoken=FXJK9-Y7MKP-KX97V-CTHRK-X2MMZ",
    event: {
      enabled: true,
      label: "기간 한정 이벤트",
      title: "Dark Calendar 이벤트 안내",
      description: "이벤트 코드를 Microsoft 계정에 등록할 수 있습니다.",
      buttonText: "이벤트 코드 등록하기",
      note: "이벤트 종료 후에는 코드 등록 링크가 제공되지 않습니다."
    }
  };

  const focusableSelector = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  function focusableElements(container) {
    return Array.from(container.querySelectorAll(focusableSelector))
      .filter((node) => !node.hidden && node.getAttribute("aria-hidden") !== "true");
  }

  function trapFocus(event, container) {
    if (event.key !== "Tab") {
      return;
    }

    const focusable = focusableElements(container);
    if (!focusable.length) {
      event.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function setPageInert(value) {
    document.querySelectorAll(".site-header, main, .site-footer").forEach((node) => {
      if (value) {
        node.setAttribute("inert", "");
      } else {
        node.removeAttribute("inert");
      }
    });
  }

  function applyConfig(config) {
    const merged = {
      ...fallbackConfig,
      ...config,
      event: {
        ...fallbackConfig.event,
        ...(config.event || {})
      }
    };

    document.querySelectorAll("[data-config-link]").forEach((node) => {
      const key = node.getAttribute("data-config-link");
      if (merged[key]) {
        node.setAttribute("href", merged[key]);
      }
    });

    document.querySelectorAll("[data-config-text]").forEach((node) => {
      const key = node.getAttribute("data-config-text");
      if (merged[key]) {
        node.textContent = merged[key];
      }
    });

    const eventText = {
      "[data-event-label]": merged.event.label,
      "[data-event-title]": merged.event.title,
      "[data-event-description]": merged.event.description,
      "[data-event-note]": merged.event.note,
      "[data-event-button]": merged.event.buttonText
    };

    Object.entries(eventText).forEach(([selector, value]) => {
      document.querySelectorAll(selector).forEach((node) => {
        if (value) {
          node.textContent = value;
        }
      });
    });

    const eventBand = document.querySelector("[data-event-band]");
    const eventActive = merged.event.enabled !== false && Boolean(merged.eventUrl);
    if (eventBand) {
      eventBand.hidden = !eventActive;
    }
  }

  function setupScreenshotPlaceholders() {
    document.querySelectorAll("[data-screenshot]").forEach((image) => {
      const placeholder = image.nextElementSibling;

      function showPlaceholder() {
        image.classList.add("is-missing");
        placeholder?.classList.add("is-visible");
      }

      function showImage() {
        image.classList.remove("is-missing");
        placeholder?.classList.remove("is-visible");
      }

      image.addEventListener("load", showImage);
      image.addEventListener("error", showPlaceholder);
      if (image.complete) {
        image.naturalWidth > 0 ? showImage() : showPlaceholder();
      }
    });
  }

  function setupScreenshotLightbox() {
    const lightbox = document.querySelector("[data-screenshot-lightbox]");
    const lightboxImage = document.querySelector("[data-screenshot-lightbox-image]");
    const lightboxTitle = document.querySelector("[data-screenshot-lightbox-title]");
    const lightboxDescription = document.querySelector("[data-screenshot-lightbox-description]");

    if (!lightbox || !lightboxImage || !lightboxTitle || !lightboxDescription) {
      return;
    }

    let previousFocus = null;

    function closeLightbox() {
      lightbox.hidden = true;
      lightboxImage.removeAttribute("src");
      lightboxImage.setAttribute("alt", "");
      document.body.classList.remove("modal-open");
      setPageInert(false);
      document.removeEventListener("keydown", onKeydown);
      if (previousFocus && document.contains(previousFocus)) {
        previousFocus.focus({ preventScroll: true });
      }
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        closeLightbox();
        return;
      }
      trapFocus(event, lightbox);
    }

    function openLightbox(image) {
      if (!image || image.classList.contains("is-missing")) {
        return;
      }

      const frame = image.closest(".screenshot-frame");
      const title = frame?.querySelector("figcaption strong");
      const description = frame?.querySelector("figcaption span");
      lightboxImage.src = image.currentSrc || image.src;
      lightboxImage.alt = image.alt || "";
      lightboxTitle.textContent = title?.textContent || "Dark Calendar 스크린샷";
      lightboxDescription.textContent = description?.textContent || "";
      previousFocus = document.activeElement;
      lightbox.hidden = false;
      document.body.classList.add("modal-open");
      setPageInert(true);
      document.addEventListener("keydown", onKeydown);
      lightbox.querySelector(".screenshot-lightbox-close")?.focus({ preventScroll: true });
    }

    document.querySelectorAll(".screenshot-frame").forEach((frame) => {
      const image = frame.querySelector("[data-screenshot]");
      if (!image) {
        return;
      }

      frame.setAttribute("tabindex", "0");
      frame.setAttribute("role", "button");
      frame.setAttribute("aria-label", `${image.alt || "스크린샷"} 확대 보기`);
      frame.addEventListener("click", () => openLightbox(image));
      frame.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openLightbox(image);
        }
      });
    });

    lightbox.querySelectorAll("[data-screenshot-lightbox-close]").forEach((node) => {
      node.addEventListener("click", closeLightbox);
    });
  }

  function setupMobileNavigation() {
    const navigation = document.querySelector(".mobile-nav");
    if (!navigation) {
      return;
    }

    navigation.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => navigation.removeAttribute("open"));
    });
  }

  setupScreenshotPlaceholders();
  setupScreenshotLightbox();
  setupMobileNavigation();

  fetch("site-config.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("config request failed");
      }
      return response.json();
    })
    .then(applyConfig)
    .catch(() => applyConfig(fallbackConfig));
})();
