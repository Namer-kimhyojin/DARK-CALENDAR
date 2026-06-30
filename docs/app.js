(function () {
  const fallbackConfig = {
    microsoftStoreUrl: "https://apps.microsoft.com/detail/9mxq08rf22k8?hl=ko-KR&gl=KR&ocid=pdpshare",
    freeInstallUrl: "http://go.microsoft.com/fwlink/?LinkId=532540&mstoken=FXJK9-Y7MKP-KX97V-CTHRK-X2MMZ",
    event: {
      enabled: true,
      label: "선착순 무료 설치 이벤트",
      title: "무료 설치 이벤트 진행 중",
      description: "선착순 전용 링크가 열려 있습니다.",
      buttonText: "무료 설치 링크 열기",
      note: "수량 또는 기간에 따라 조기 종료될 수 있습니다."
    }
  };

  const storageKeys = {
    adminPassword: "dc-admin-pw",
    promoUrl: "dc-promo-url",
    storeUrl: "dc-store-url",
    promoEnabled: "dc-promo-on",
    hideUntil: "dc-promo-hide-until"
  };

  const defaultAdminPassword = "dark2025";
  let activeConfig = fallbackConfig;

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      if (value === null) {
        window.localStorage.removeItem(key);
      } else {
        window.localStorage.setItem(key, value);
      }
    } catch (error) {
      // Local storage may be unavailable in a strict browser mode.
    }
  }

  function promoUrlFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const encoded = params.get("p");
    if (!encoded) {
      return "";
    }

    try {
      return window.atob(encoded);
    } catch (error) {
      return "";
    }
  }

  function withLocalOverrides(config) {
    const storedStoreUrl = readStorage(storageKeys.storeUrl);
    const storedPromoUrl = readStorage(storageKeys.promoUrl);
    const storedPromoEnabled = readStorage(storageKeys.promoEnabled);
    const queryPromoUrl = promoUrlFromQuery();

    return {
      ...config,
      microsoftStoreUrl: storedStoreUrl || config.microsoftStoreUrl,
      freeInstallUrl: queryPromoUrl || storedPromoUrl || config.freeInstallUrl,
      event: {
        ...config.event,
        enabled: storedPromoEnabled === null ? config.event.enabled : storedPromoEnabled === "1"
      }
    };
  }

  function applyConfig(config, options) {
    const merged = withLocalOverrides({
      ...fallbackConfig,
      ...config,
      event: {
        ...fallbackConfig.event,
        ...(config.event || {})
      }
    });

    activeConfig = merged;

    document.querySelectorAll("[data-config-link]").forEach((node) => {
      const key = node.getAttribute("data-config-link");
      if (merged[key]) {
        node.setAttribute("href", merged[key]);
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

    setupEventModal(merged, options || {});
    populateAdminFields();
  }

  function dismissedForToday() {
    const raw = readStorage(storageKeys.hideUntil);
    if (!raw) {
      return false;
    }

    const until = Number(raw);
    return Number.isFinite(until) && Date.now() < until;
  }

  function setupEventModal(config, options) {
    const modal = document.querySelector("[data-event-modal]");
    if (!modal) {
      return;
    }

    if (config.event.enabled === false) {
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      return;
    }

    const closeButtons = modal.querySelectorAll("[data-event-close]");
    const firstAction = modal.querySelector("[data-event-button]");
    const dismissToday = modal.querySelector("[data-event-dismiss-today]");

    function closeModal() {
      if (dismissToday && dismissToday.checked) {
        writeStorage(storageKeys.hideUntil, String(Date.now() + 86400000));
      }
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      document.removeEventListener("keydown", onKeydown);
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        closeModal();
      }
    }

    closeButtons.forEach((button) => {
      if (!button.dataset.boundEventClose) {
        button.dataset.boundEventClose = "true";
        button.addEventListener("click", closeModal);
      }
    });

    if (options.skipAutoOpen || dismissedForToday()) {
      return;
    }

    window.setTimeout(() => {
      modal.hidden = false;
      document.body.classList.add("modal-open");
      document.addEventListener("keydown", onKeydown);
      if (firstAction) {
        firstAction.focus({ preventScroll: true });
      }
    }, 500);
  }

  function openEventModalNow() {
    const modal = document.querySelector("[data-event-modal]");
    const firstAction = modal ? modal.querySelector("[data-event-button]") : null;
    if (!modal || activeConfig.event.enabled === false) {
      return;
    }

    modal.hidden = false;
    document.body.classList.add("modal-open");
    if (firstAction) {
      firstAction.focus({ preventScroll: true });
    }
  }

  function setupScreenshotPlaceholders() {
    document.querySelectorAll("[data-screenshot]").forEach((image) => {
      const placeholder = image.nextElementSibling;

      function showPlaceholder() {
        image.classList.add("is-missing");
        if (placeholder) {
          placeholder.classList.add("is-visible");
        }
      }

      function showImage() {
        image.classList.remove("is-missing");
        if (placeholder) {
          placeholder.classList.remove("is-visible");
        }
      }

      image.addEventListener("load", showImage);
      image.addEventListener("error", showPlaceholder);

      if (image.complete && image.naturalWidth > 0) {
        showImage();
      } else if (image.complete) {
        showPlaceholder();
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

    function closeLightbox() {
      lightbox.hidden = true;
      lightboxImage.removeAttribute("src");
      lightboxImage.setAttribute("alt", "");
      document.body.classList.remove("modal-open");
      document.removeEventListener("keydown", onKeydown);
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        closeLightbox();
      }
    }

    function openLightbox(image) {
      if (!image || image.classList.contains("is-missing")) {
        return;
      }

      const frame = image.closest(".screenshot-frame");
      const title = frame ? frame.querySelector("figcaption strong") : null;
      const description = frame ? frame.querySelector("figcaption span") : null;

      lightboxImage.src = image.currentSrc || image.src;
      lightboxImage.alt = image.alt || "";
      lightboxTitle.textContent = title ? title.textContent : "Dark Calendar 스크린샷";
      lightboxDescription.textContent = description ? description.textContent : "";
      lightbox.hidden = false;
      document.body.classList.add("modal-open");
      document.addEventListener("keydown", onKeydown);
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

  function showAdminMessage(selector, message, type) {
    const node = document.querySelector(selector);
    if (!node) {
      return;
    }

    node.textContent = message;
    node.classList.remove("is-success", "is-error");
    if (type) {
      node.classList.add(type === "success" ? "is-success" : "is-error");
    }
  }

  function getAdminPassword() {
    return readStorage(storageKeys.adminPassword) || defaultAdminPassword;
  }

  function openAdminPanel() {
    const modal = document.querySelector("[data-admin-modal]");
    const auth = document.querySelector("[data-admin-auth]");
    const main = document.querySelector("[data-admin-main]");
    const passwordInput = document.querySelector("#admin-password");

    if (!modal || !auth || !main) {
      return;
    }

    auth.hidden = false;
    main.hidden = true;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    showAdminMessage("[data-admin-auth-message]", "", "");
    showAdminMessage("[data-admin-message]", "", "");

    if (passwordInput) {
      passwordInput.value = "";
      window.setTimeout(() => passwordInput.focus(), 80);
    }
  }

  function closeAdminPanel() {
    const modal = document.querySelector("[data-admin-modal]");
    if (modal) {
      modal.hidden = true;
    }
    document.body.classList.remove("modal-open");
  }

  function unlockAdminPanel() {
    const passwordInput = document.querySelector("#admin-password");
    const auth = document.querySelector("[data-admin-auth]");
    const main = document.querySelector("[data-admin-main]");

    if (!passwordInput || !auth || !main) {
      return;
    }

    if (passwordInput.value !== getAdminPassword()) {
      showAdminMessage("[data-admin-auth-message]", "비밀번호가 올바르지 않습니다.", "error");
      return;
    }

    auth.hidden = true;
    main.hidden = false;
    populateAdminFields();
  }

  function populateAdminFields() {
    const promoInput = document.querySelector("#admin-promo-url");
    const storeInput = document.querySelector("#admin-store-url");
    const enabledInput = document.querySelector("#admin-promo-enabled");

    if (promoInput) {
      promoInput.value = activeConfig.freeInstallUrl || fallbackConfig.freeInstallUrl;
    }
    if (storeInput) {
      storeInput.value = activeConfig.microsoftStoreUrl || fallbackConfig.microsoftStoreUrl;
    }
    if (enabledInput) {
      enabledInput.checked = activeConfig.event ? activeConfig.event.enabled !== false : true;
    }
  }

  function validUrl(value) {
    return /^https?:\/\//i.test(value);
  }

  function saveAdminSettings() {
    const promoInput = document.querySelector("#admin-promo-url");
    const storeInput = document.querySelector("#admin-store-url");
    const enabledInput = document.querySelector("#admin-promo-enabled");

    const promoUrl = promoInput ? promoInput.value.trim() : "";
    const storeUrl = storeInput ? storeInput.value.trim() : "";
    const promoEnabled = enabledInput ? enabledInput.checked : true;

    if (!validUrl(promoUrl)) {
      showAdminMessage("[data-admin-message]", "무료 설치 링크는 http:// 또는 https://로 시작해야 합니다.", "error");
      return;
    }
    if (!validUrl(storeUrl)) {
      showAdminMessage("[data-admin-message]", "Store 링크는 http:// 또는 https://로 시작해야 합니다.", "error");
      return;
    }

    writeStorage(storageKeys.promoUrl, promoUrl);
    writeStorage(storageKeys.storeUrl, storeUrl);
    writeStorage(storageKeys.promoEnabled, promoEnabled ? "1" : "0");
    writeStorage(storageKeys.hideUntil, null);

    applyConfig(activeConfig, { skipAutoOpen: true });
    showAdminMessage("[data-admin-message]", "저장되었습니다. 현재 브라우저에서 즉시 반영됩니다.", "success");
  }

  function generateShareLink() {
    const promoInput = document.querySelector("#admin-promo-url");
    const shareBox = document.querySelector("[data-admin-share-box]");
    const shareUrl = document.querySelector("[data-admin-share-url]");
    const promoUrl = promoInput ? promoInput.value.trim() : activeConfig.freeInstallUrl;

    if (!validUrl(promoUrl)) {
      showAdminMessage("[data-admin-message]", "공유 링크를 만들려면 올바른 프로모션 URL이 필요합니다.", "error");
      return;
    }

    const encoded = window.btoa(promoUrl);
    const url = `${window.location.origin}${window.location.pathname}?p=${encoded}`;
    if (shareUrl) {
      shareUrl.textContent = url;
    }
    if (shareBox) {
      shareBox.hidden = false;
    }
  }

  function copyShareLink() {
    const shareUrl = document.querySelector("[data-admin-share-url]");
    if (!shareUrl || !shareUrl.textContent) {
      return;
    }

    navigator.clipboard.writeText(shareUrl.textContent)
      .then(() => showAdminMessage("[data-admin-message]", "공유 링크가 복사되었습니다.", "success"))
      .catch(() => showAdminMessage("[data-admin-message]", "복사에 실패했습니다. 링크를 직접 선택해 주세요.", "error"));
  }

  function changeAdminPassword() {
    const input = document.querySelector("#admin-new-password");
    const value = input ? input.value.trim() : "";

    if (value.length < 4) {
      showAdminMessage("[data-admin-message]", "비밀번호는 4자 이상이어야 합니다.", "error");
      return;
    }

    writeStorage(storageKeys.adminPassword, value);
    input.value = "";
    showAdminMessage("[data-admin-message]", "관리자 비밀번호가 변경되었습니다.", "success");
  }

  function setupAdminPanel() {
    let triggerCount = 0;
    let triggerTimer = 0;

    const trigger = document.querySelector("[data-admin-trigger]");
    const hint = document.querySelector("[data-admin-hint]");

    function showHint(message) {
      if (!hint) {
        return;
      }
      hint.textContent = message;
      hint.classList.add("is-visible");
      window.clearTimeout(triggerTimer);
      triggerTimer = window.setTimeout(() => {
        hint.classList.remove("is-visible");
      }, 1800);
    }

    if (trigger) {
      trigger.addEventListener("click", () => {
        triggerCount += 1;
        if (triggerCount >= 5) {
          triggerCount = 0;
          showHint("관리자 모드를 엽니다.");
          openAdminPanel();
          return;
        }
        showHint(`관리자 모드 ${5 - triggerCount}번 더 클릭`);
      });
    }

    document.querySelectorAll("[data-admin-close]").forEach((node) => {
      node.addEventListener("click", closeAdminPanel);
    });
    document.querySelector("[data-admin-unlock]")?.addEventListener("click", unlockAdminPanel);
    document.querySelector("#admin-password")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        unlockAdminPanel();
      }
    });
    document.querySelector("[data-admin-save]")?.addEventListener("click", saveAdminSettings);
    document.querySelector("[data-admin-preview]")?.addEventListener("click", openEventModalNow);
    document.querySelector("[data-admin-share]")?.addEventListener("click", generateShareLink);
    document.querySelector("[data-admin-copy]")?.addEventListener("click", copyShareLink);
    document.querySelector("[data-admin-change-password]")?.addEventListener("click", changeAdminPassword);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAdminPanel();
      }
    });
  }

  setupScreenshotPlaceholders();
  setupScreenshotLightbox();
  setupAdminPanel();

  fetch("site-config.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("config request failed");
      }
      return response.json();
    })
    .then((config) => applyConfig(config))
    .catch(() => applyConfig(fallbackConfig));
})();
