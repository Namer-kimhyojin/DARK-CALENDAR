(function () {
  "use strict";

  const status = document.querySelector("[data-copy-status]");
  const linkStatus = document.querySelector("[data-link-status]");

  async function copyText(value) {
    try {
      await window.navigator.clipboard.writeText(value);
      return true;
    } catch (_error) {
      const previousFocus = document.activeElement;
      const helper = document.createElement("textarea");
      helper.value = value;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      try {
        return document.execCommand("copy");
      } catch (_fallbackError) {
        return false;
      } finally {
        helper.remove();
        previousFocus?.focus({ preventScroll: true });
      }
    }
  }

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const source = document.getElementById(button.dataset.copyTarget);
      if (!source || !status) return;
      const copied = await copyText(source.value);
      status.textContent = copied ? "홍보 문구를 복사했습니다." : "문구를 선택해 직접 복사해 주세요.";
    });
  });

  document.querySelectorAll("[data-copy-value]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!linkStatus) return;
      const copied = await copyText(button.dataset.copyValue || "");
      linkStatus.textContent = copied ? "채널 전용 추적 링크를 복사했습니다." : "링크를 선택해 직접 복사해 주세요.";
    });
  });

  const motion = document.querySelector("[data-promo-motion]");
  const play = document.querySelector("[data-promo-play]");
  if (motion && play) {
    const poster = motion.getAttribute("src");
    const animation = motion.dataset.animatedSrc;
    const setPlaying = (playing) => {
      motion.src = playing ? animation : poster;
      play.textContent = playing ? "GIF 정지" : "GIF 재생";
    };
    play.hidden = false;
    play.addEventListener("click", () => setPlaying(motion.getAttribute("src") !== animation));
    motion.addEventListener("error", () => {
      if (motion.getAttribute("src") === animation) setPlaying(false);
    });
  }
})();
