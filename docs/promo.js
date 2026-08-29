(function () {
  "use strict";

  const status = document.querySelector("[data-copy-status]");
  const linkStatus = document.querySelector("[data-link-status]");

  async function copyText(value) {
    try {
      await window.navigator.clipboard.writeText(value);
      return true;
    } catch (_error) {
      const helper = document.createElement("textarea");
      helper.value = value;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      const copied = document.execCommand("copy");
      helper.remove();
      return copied;
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
})();
