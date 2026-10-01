(function () {
  "use strict";
  const root = document.querySelector("[data-request-board]");
  if (!root) return;
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const copy = {
    ko: {
      heading: "더 나은 캘린더를<br><em>함께 만들어가요.</em>", intro: "불편했던 점, 필요한 기능, 작은 아이디어까지. 여러분의 의견을 기다립니다.",
      write: "수정 요청 작성", received: "접수됨", inProgress: "검토·반영 예정", done: "완료", reviewing: "검토 중", planned: "반영 예정", closed: "보류·종료", noAccount: "회원가입 없이 작성할 수 있어요.", summary: "요청 처리 현황",
      all: "전체", bug: "오류 제보", feature: "기능 제안", ui: "UI / UX", other: "기타", categoryLabel: "요청 유형", search: "요청 검색", statusLabel: "처리 상태", allStatuses: "모든 상태", loading: "요청을 불러오고 있습니다.", previous: "이전", next: "다음", total: "{n}개의 요청",
      publicNote: "등록한 내용은 공개됩니다. 개인정보·비밀번호·인증 키는 본문에 넣지 마세요.", admin: "관리자", logout: "관리자 로그아웃", close: "닫기", nickname: "닉네임 (선택)", visitor: "방문자", titleLabel: "제목", titlePlaceholder: "어떤 점을 개선하면 좋을까요?", bodyLabel: "요청 내용", bodyPlaceholder: "불편한 상황과 원하는 개선 내용을 알려주세요. 오류라면 재현 방법도 함께 적어주세요.", version: "앱 버전 (선택)", platform: "사용 환경 (선택)", selectOptional: "선택하지 않음", editPassword: "수정·삭제 비밀번호", passwordHelp: "8자 이상으로 설정하세요. 글을 수정·삭제할 때 필요하며, 비밀번호는 복구할 수 없습니다.", passwordVerify: "등록할 때 정한 비밀번호를 입력하세요. 비밀번호는 변경되지 않습니다.",
      formNotice: "닉네임과 요청 내용은 게시판에 공개됩니다. 개인 일정이나 연락처를 포함하지 마세요.", cancel: "취소", submit: "요청 등록", save: "수정 저장", editHeading: "요청 수정", replyHeading: "개발자 답변", noReply: "아직 등록된 답변이 없습니다.", saveStatus: "상태·답변 저장", edit: "수정", delete: "삭제", deleteHeading: "요청을 삭제할까요?", deleteHelp: "삭제한 요청은 복구할 수 없습니다.", deleteConfirm: "삭제하기", adminLogin: "관리자 로그인", adminPassword: "관리자 비밀번호", login: "로그인", emptyTitle: "첫 번째 의견을 들려주세요.", emptyBody: "개선되었으면 하는 기능이나 불편했던 점을 남겨주세요.", noResults: "검색 결과가 없습니다.", noResultsBody: "검색어나 요청 유형, 처리 상태를 바꿔보세요.", offline: "게시판에 연결할 수 없습니다.", offlineBody: "연결을 확인한 후 다시 시도해주세요.", retry: "다시 시도", posted: "요청이 등록되었습니다.", edited: "수정 내용이 저장되었습니다.", deleted: "요청이 삭제되었습니다.", statusSaved: "상태와 답변이 저장되었습니다.", adminReady: "관리자로 로그인했습니다. 요청을 열어 상태와 답변을 관리하세요.", loggedOut: "관리자 로그아웃이 완료되었습니다.", busy: "처리 중…", updated: "수정됨", requestNumber: "요청 #{n}",
      wrong_password: "비밀번호가 일치하지 않습니다.", unauthorized: "관리자 비밀번호가 틀렸거나 세션이 만료되었습니다. 다시 로그인해주세요.", conflict: "등록 내용이 변경되었거나 이전 요청이 이미 처리되었습니다. 작성 내용을 복사해 둔 뒤 요청을 다시 열어주세요.", not_found: "이미 삭제되었거나 찾을 수 없는 요청입니다.", rate_limited: "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.", unavailable: "서버에 연결할 수 없습니다. 입력 내용은 유지됩니다. 잠시 후 다시 시도해주세요.", invalid_title: "제목은 3~100자로 입력하세요.", invalid_body: "내용은 10~5,000자로 입력하세요.", invalid_nickname: "닉네임은 30자 이내로 입력하세요.", invalid_password: "비밀번호는 8~128자로 입력하세요.", invalid_request: "입력 내용을 확인해주세요.", too_large: "입력 내용이 너무 큽니다.", invalid_version: "버전은 30자 이내로 입력하세요.", invalid_platform: "사용 환경은 60자 이내로 입력하세요.", invalid_reply: "답변은 3,000자 이내로 입력하세요."
    },
    en: {
      heading: "A better calendar,<br><em>shaped together.</em>", intro: "Report a problem, suggest a feature, or share a small idea. We'd love to hear from you.",
      write: "Submit a request", received: "Received", inProgress: "Reviewing · planned", done: "Completed", reviewing: "Under review", planned: "Planned", closed: "On hold · closed", noAccount: "No account needed.", summary: "Request progress",
      all: "All", bug: "Bug report", feature: "Feature idea", ui: "UI / UX", other: "Other", categoryLabel: "Request type", search: "Search requests", statusLabel: "Status", allStatuses: "All statuses", loading: "Loading requests…", previous: "Previous", next: "Next", total: "{n} requests",
      publicNote: "Posts are public. Do not include personal information, passwords, or access keys.", admin: "Admin", logout: "Sign out as admin", close: "Close", nickname: "Nickname (optional)", visitor: "Visitor", titleLabel: "Title", titlePlaceholder: "What would you like to improve?", bodyLabel: "Request details", bodyPlaceholder: "Describe the problem and your suggested improvement. For a bug, include steps to reproduce it.", version: "App version (optional)", platform: "Environment (optional)", selectOptional: "Not specified", editPassword: "Password to edit or delete", passwordHelp: "Use at least 8 characters. Keep this password to edit or delete your post; it cannot be recovered.", passwordVerify: "Enter the password set when you posted. Your password will stay the same.",
      formNotice: "Your nickname and request will be public. Do not include private schedules or contact details.", cancel: "Cancel", submit: "Post request", save: "Save changes", editHeading: "Edit request", replyHeading: "Developer reply", noReply: "No reply yet.", saveStatus: "Save status and reply", edit: "Edit", delete: "Delete", deleteHeading: "Delete this request?", deleteHelp: "A deleted request cannot be restored.", deleteConfirm: "Delete request", adminLogin: "Admin sign in", adminPassword: "Admin password", login: "Sign in", emptyTitle: "Share the first idea.", emptyBody: "Tell us about a feature you'd like or a problem you encountered.", noResults: "No matching requests.", noResultsBody: "Try a different search, type, or status.", offline: "Unable to connect to the board.", offlineBody: "Check your connection and try again.", retry: "Try again", posted: "Your request has been posted.", edited: "Your changes have been saved.", deleted: "The request has been deleted.", statusSaved: "Status and reply saved.", adminReady: "Signed in as admin. Open a request to manage its status and reply.", loggedOut: "Signed out as admin.", busy: "Saving…", updated: "Updated", requestNumber: "Request #{n}",
      wrong_password: "The password does not match.", unauthorized: "Incorrect admin password or expired session. Please sign in again.", conflict: "This request has changed or a previous submission was processed. Copy your draft, then reopen the request.", not_found: "This request was deleted or could not be found.", rate_limited: "Too many attempts. Please try again later.", unavailable: "Unable to reach the server. Your draft is preserved; please try again shortly.", invalid_title: "Use 3–100 characters for the title.", invalid_body: "Use 10–5,000 characters for the details.", invalid_nickname: "Use up to 30 characters for the nickname.", invalid_password: "Use 8–128 characters for the password.", invalid_request: "Check the information you entered.", too_large: "The request is too large.", invalid_version: "Use up to 30 characters for the version.", invalid_platform: "Use up to 60 characters for the environment.", invalid_reply: "Use up to 3,000 characters for the reply."
    },
    ja: {
      heading: "よりよいカレンダーを<br><em>一緒につくりましょう。</em>", intro: "不具合、ほしい機能、小さなアイデアまで。皆さまのご意見をお待ちしています。",
      write: "改善リクエストを書く", received: "受付済み", inProgress: "検討中・対応予定", done: "完了", reviewing: "検討中", planned: "対応予定", closed: "保留・終了", noAccount: "会員登録は不要です。", summary: "対応状況",
      all: "すべて", bug: "不具合報告", feature: "機能提案", ui: "UI / UX", other: "その他", categoryLabel: "種類", search: "リクエストを検索", statusLabel: "対応状況", allStatuses: "すべての状態", loading: "読み込み中…", previous: "前へ", next: "次へ", total: "{n}件のリクエスト",
      publicNote: "投稿内容は公開されます。個人情報、パスワード、認証キーを含めないでください。", admin: "管理者", logout: "管理者ログアウト", close: "閉じる", nickname: "ニックネーム（任意）", visitor: "訪問者", titleLabel: "タイトル", titlePlaceholder: "どのような改善を希望しますか？", bodyLabel: "内容", bodyPlaceholder: "問題と希望する改善を教えてください。不具合の場合は再現手順も記入してください。", version: "アプリのバージョン（任意）", platform: "使用環境（任意）", selectOptional: "指定なし", editPassword: "編集・削除用パスワード", passwordHelp: "8文字以上で設定してください。編集・削除に必要です。パスワードは復元できません。", passwordVerify: "投稿時に設定したパスワードを入力してください。パスワードは変更されません。",
      formNotice: "ニックネームと内容は公開されます。個人の予定や連絡先を含めないでください。", cancel: "キャンセル", submit: "投稿する", save: "変更を保存", editHeading: "リクエストを編集", replyHeading: "開発者の回答", noReply: "まだ回答はありません。", saveStatus: "状態・回答を保存", edit: "編集", delete: "削除", deleteHeading: "削除しますか？", deleteHelp: "削除したリクエストは復元できません。", deleteConfirm: "削除する", adminLogin: "管理者ログイン", adminPassword: "管理者パスワード", login: "ログイン", emptyTitle: "最初のご意見をお聞かせください。", emptyBody: "希望する機能や不便だった点を教えてください。", noResults: "該当するリクエストがありません。", noResultsBody: "検索語、種類、状態を変えてみてください。", offline: "掲示板に接続できません。", offlineBody: "接続を確認して再試行してください。", retry: "再試行", posted: "投稿しました。", edited: "変更を保存しました。", deleted: "削除しました。", statusSaved: "状態と回答を保存しました。", adminReady: "管理者としてログインしました。リクエストを開いて管理できます。", loggedOut: "ログアウトしました。", busy: "処理中…", updated: "更新済み", requestNumber: "リクエスト #{n}",
      wrong_password: "パスワードが一致しません。", unauthorized: "管理者パスワードが違うか、セッションが切れました。再度ログインしてください。", conflict: "内容が変更されたか、すでに投稿が処理されました。下書きをコピーして再度開いてください。", not_found: "削除済み、または見つからないリクエストです。", rate_limited: "試行回数が多すぎます。時間をおいて再試行してください。", unavailable: "サーバーに接続できません。入力内容は保持されます。再試行してください。", invalid_title: "タイトルは3〜100文字です。", invalid_body: "内容は10〜5,000文字です。", invalid_nickname: "ニックネームは30文字以内です。", invalid_password: "パスワードは8〜128文字です。", invalid_request: "入力内容を確認してください。", too_large: "入力内容が大きすぎます。", invalid_version: "バージョンは30文字以内です。", invalid_platform: "使用環境は60文字以内です。", invalid_reply: "回答は3,000文字以内です。"
    },
    zh: {
      heading: "更好的日历，<br><em>由我们共同打造。</em>", intro: "报告问题、建议功能或分享小想法。期待您的意见。",
      write: "提交改进请求", received: "已收到", inProgress: "评估中·已计划", done: "已完成", reviewing: "评估中", planned: "已计划", closed: "暂缓·已关闭", noAccount: "无需注册。", summary: "处理进度",
      all: "全部", bug: "错误报告", feature: "功能建议", ui: "UI / UX", other: "其他", categoryLabel: "请求类型", search: "搜索请求", statusLabel: "处理状态", allStatuses: "所有状态", loading: "正在加载…", previous: "上一页", next: "下一页", total: "{n}条请求",
      publicNote: "发布内容将公开。请勿包含个人信息、密码或认证密钥。", admin: "管理员", logout: "管理员退出", close: "关闭", nickname: "昵称（可选）", visitor: "访客", titleLabel: "标题", titlePlaceholder: "您希望改进什么？", bodyLabel: "请求内容", bodyPlaceholder: "请描述问题及希望的改进。报告错误时，请包含复现步骤。", version: "应用版本（可选）", platform: "使用环境（可选）", selectOptional: "未指定", editPassword: "编辑和删除密码", passwordHelp: "请设置至少8个字符的密码。编辑或删除时需要此密码，且无法找回。", passwordVerify: "请输入发布时设置的密码。密码不会改变。",
      formNotice: "昵称和请求内容将公开。请勿包含个人日程或联系方式。", cancel: "取消", submit: "发布请求", save: "保存修改", editHeading: "编辑请求", replyHeading: "开发者回复", noReply: "暂无回复。", saveStatus: "保存状态和回复", edit: "编辑", delete: "删除", deleteHeading: "删除此请求？", deleteHelp: "删除后无法恢复。", deleteConfirm: "确认删除", adminLogin: "管理员登录", adminPassword: "管理员密码", login: "登录", emptyTitle: "分享第一条建议。", emptyBody: "告诉我们您希望的功能或遇到的问题。", noResults: "没有匹配的请求。", noResultsBody: "请更换搜索词、类型或状态。", offline: "无法连接到留言板。", offlineBody: "请检查网络后重试。", retry: "重试", posted: "请求已发布。", edited: "修改已保存。", deleted: "请求已删除。", statusSaved: "状态和回复已保存。", adminReady: "已以管理员身份登录。打开请求即可管理状态和回复。", loggedOut: "已退出管理员登录。", busy: "处理中…", updated: "已修改", requestNumber: "请求 #{n}",
      wrong_password: "密码不匹配。", unauthorized: "管理员密码错误或会话已过期。请重新登录。", conflict: "内容已更改或此前的提交已处理。请先复制草稿，再重新打开请求。", not_found: "请求已删除或不存在。", rate_limited: "尝试次数过多，请稍后重试。", unavailable: "无法连接服务器。输入内容已保留，请稍后重试。", invalid_title: "标题应为3至100个字符。", invalid_body: "内容应为10至5,000个字符。", invalid_nickname: "昵称最多30个字符。", invalid_password: "密码应为8至128个字符。", invalid_request: "请检查输入内容。", too_large: "输入内容过大。", invalid_version: "版本最多30个字符。", invalid_platform: "使用环境最多60个字符。", invalid_reply: "回复最多3,000个字符。"
    }
  };
  const state = { api: root.dataset.api, language: "ko", version: "3.7.8", category: "all", status: "all", q: "", page: 1, data: null, ready: false, failed: false, detail: null, edit: null, key: null, token: null, expires: 0, notice: "" };
  const editor = $("[data-board-editor]"), form = $("[data-board-form]"), detail = $("[data-board-detail]"), adminForm = $("[data-board-admin-update]");
  let listController, searchTimer;
  const tr = (key, values = {}) => Object.entries(values).reduce((text, [name, value]) => text.replace(`{${name}}`, value), copy[state.language][key] || copy.en[key] || copy.ko.invalid_request);
  const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; };
  const date = (value) => new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : state.language, { year: "numeric", month: "short", day: "numeric" }).format(new Date(value));
  const badge = (value, status = false) => node("span", status ? `board-badge ${value}` : "board-row-category", tr(value));
  const message = (key) => { state.notice = key; $("[data-board-live]").textContent = key ? tr(key) : ""; };
  const error = (parent, exception) => { $("[data-board-error]", parent).textContent = tr(exception.code || "unavailable"); };
  function adminActive() { if (state.token && state.expires <= Date.now()) { state.token = null; state.expires = 0; } return Boolean(state.token); }
  async function api(path, options = {}) {
    const { admin, signal, ...request } = options;
    request.headers = { ...(request.body ? { "Content-Type": "application/json" } : {}), ...(admin && state.token ? { Authorization: `Bearer ${state.token}` } : {}) };
    request.signal = signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000);
    request.cache = "no-store";
    try {
      const result = await fetch(`${state.api}${path}`, request), data = await result.json();
      if (!result.ok) {
        if (admin && result.status === 401) { state.token = null; state.expires = 0; renderAdmin(); }
        throw Object.assign(new Error(data.error), { code: data.error || "unavailable" });
      }
      return data;
    } catch (exception) { if (!exception.code) exception.code = "unavailable"; throw exception; }
  }
  function localize() {
    const language = document.documentElement.lang.split("-")[0];
    state.language = copy[language] ? language : "en";
    document.querySelectorAll("[data-board-i18n]").forEach((el) => { if (el.dataset.boardI18n === "heading") el.innerHTML = tr("heading"); else el.textContent = tr(el.dataset.boardI18n); });
    document.querySelectorAll("[data-board-placeholder]").forEach((el) => { el.placeholder = tr(el.dataset.boardPlaceholder); });
    document.querySelectorAll("[data-board-aria]").forEach((el) => { el.setAttribute("aria-label", tr(el.dataset.boardAria)); });
    renderList(); renderEditor(); renderDetail(); renderAdmin(); message(state.notice);
  }
  function renderList() {
    const list = $("[data-board-list]"); list.replaceChildren();
    const data = state.data;
    if (!data || !data.items.length) {
      const empty = node("div", "board-empty"), filtered = state.category !== "all" || state.status !== "all" || state.q;
      const key = state.failed ? "offline" : !data ? "loading" : filtered ? "noResults" : "emptyTitle";
      empty.append(node("span", "board-empty-icon", state.failed ? "↻" : "↗"), node("h3", "", tr(key)));
      if (data || state.failed) empty.append(node("p", "", tr(state.failed ? "offlineBody" : filtered ? "noResultsBody" : "emptyBody")));
      if (state.failed || (data && !filtered)) {
        const button = node("button", "board-secondary", tr(state.failed ? "retry" : "write")); button.type = "button";
        button.addEventListener("click", state.failed ? loadList : compose); empty.append(button);
      }
      list.append(empty);
    } else {
      for (const item of data.items) {
        const button = node("button", "board-row"); button.type = "button";
        const content = node("span", "board-row-copy");
        content.append(node("strong", "board-row-title", item.title), node("span", "board-row-excerpt", item.body.replace(/\s+/gu, " ").slice(0, 100)));
        button.append(content, badge(item.category), badge(item.status, true), node("time", "board-row-date", date(item.created_at)), node("span", "board-row-arrow", "↗"));
        button.addEventListener("click", () => openDetail(item.id)); list.append(button);
      }
    }
    $("[data-board-total]").textContent = data ? tr("total", { n: data.total }) : "";
    const pages = Math.max(1, Math.ceil((data?.total || 0) / 12));
    $("[data-board-page]").textContent = `${state.page} / ${pages}`;
    $("[data-board-prev]").disabled = !state.ready || state.page <= 1;
    $("[data-board-next]").disabled = !state.ready || state.page >= pages;
    $("[data-board-compose]").disabled = !state.ready;
    for (const key of ["received", "progress", "done"]) $( `[data-board-count="${key}"]`).textContent = data ? key === "progress" ? data.stats.reviewing + data.stats.planned : data.stats[key] : "—";
  }
  async function loadList() {
    listController?.abort(); const controller = new AbortController(); listController = controller;
    $("[data-board-list]").setAttribute("aria-busy", "true");
    try {
      const query = new URLSearchParams({ category: state.category, status: state.status, q: state.q, page: state.page });
      const data = await api(`/api/requests?${query}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      const pages = Math.max(1, Math.ceil(data.total / 12));
      if (state.page > pages) { state.page = pages; return loadList(); }
      state.data = data; state.ready = true; state.failed = false; renderList();
    } catch (exception) {
      if (controller.signal.aborted) return;
      state.failed = true; state.ready = false; state.data = null; renderList();
    } finally { if (listController === controller) $("[data-board-list]").setAttribute("aria-busy", "false"); }
  }
  function renderEditor() {
    $("[data-board-editor-title]").textContent = tr(state.edit ? "editHeading" : "write");
    $("[data-board-submit]").textContent = tr(state.edit ? "save" : "submit");
    $("[data-board-i18n='passwordHelp']").textContent = tr(state.edit ? "passwordVerify" : "passwordHelp");
    form.elements.password.autocomplete = state.edit ? "current-password" : "new-password";
  }
  function compose() {
    if (!state.ready) return;
    state.edit = null; state.key = crypto.randomUUID(); form.reset(); $("[data-board-error]", form).textContent = "";
    form.elements.appVersion.placeholder = state.version; renderEditor(); editor.showModal(); form.elements.title.focus();
  }
  function renderDetail() {
    const item = state.detail; if (!item) return;
    $("[data-board-detail-number]").textContent = tr("requestNumber", { n: item.id });
    $("[data-board-detail-badges]").replaceChildren(badge(item.category), badge(item.status, true));
    $("#board-detail-title").textContent = item.title;
    $("[data-board-detail-meta]").textContent = `${item.nickname} · ${date(item.created_at)}${item.updated_at !== item.created_at ? ` · ${tr("updated")} ${date(item.updated_at)}` : ""}`;
    $("[data-board-detail-environment]").textContent = [item.app_version && `Air Calendar ${item.app_version}`, item.platform].filter(Boolean).join(" · ");
    $("[data-board-detail-body]").textContent = item.body; $("[data-board-detail-reply]").textContent = item.admin_reply || tr("noReply");
    adminForm.elements.status.value = item.status; adminForm.elements.reply.value = item.admin_reply; renderAdmin();
  }
  async function openDetail(id) {
    try {
      state.detail = (await api(`/api/requests/${id}`)).item; $("[data-board-error]", adminForm).textContent = ""; renderDetail();
      if (!detail.open) detail.showModal();
    } catch (exception) { message(exception.code || "unavailable"); }
  }
  function renderAdmin() {
    const active = adminActive(); $("[data-board-admin]").textContent = tr(active ? "logout" : "admin"); adminForm.hidden = !active;
  }
  async function submit(parent, operation) {
    if (parent.dataset.busy) return;
    parent.dataset.busy = "true"; $("[data-board-error]", parent).textContent = "";
    const buttons = Array.from(parent.querySelectorAll("button")); buttons.forEach((el) => { el.disabled = true; });
    try { await operation(); } catch (exception) { error(parent, exception); }
    finally { delete parent.dataset.busy; buttons.forEach((el) => { el.disabled = false; }); }
  }
  document.querySelectorAll(".board-dialog [data-board-close]").forEach((button) => button.addEventListener("click", () => { if (!button.closest("dialog").querySelector("[data-busy]")) button.closest("dialog").close(); }));
  document.querySelectorAll(".board-dialog").forEach((dialog) => {
    dialog.addEventListener("cancel", (event) => { if (dialog.querySelector("[data-busy]")) event.preventDefault(); });
    dialog.addEventListener("close", () => dialog.querySelectorAll("input[type=password]").forEach((input) => { input.value = ""; }));
  });
  $("[data-board-compose]").addEventListener("click", compose);
  root.querySelectorAll("[data-board-category]").forEach((button) => button.addEventListener("click", () => {
    state.category = button.dataset.boardCategory; state.page = 1;
    root.querySelectorAll("[data-board-category]").forEach((el) => { const active = el === button; el.classList.toggle("active", active); el.setAttribute("aria-pressed", String(active)); }); loadList();
  }));
  $("[data-board-search]").addEventListener("input", (event) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.q = event.target.value.trim(); state.page = 1; loadList(); }, 300); });
  $("[data-board-status]").addEventListener("change", (event) => { state.status = event.target.value; state.page = 1; loadList(); });
  for (const [selector, direction] of [["[data-board-prev]", -1], ["[data-board-next]", 1]]) $(selector).addEventListener("click", () => { state.page += direction; loadList(); });
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(form, async () => {
    const payload = Object.fromEntries(new FormData(form)); if (!payload.nickname.trim()) payload.nickname = tr("visitor");
    if (state.edit) payload.revision = state.edit.revision; else payload.idempotencyKey = state.key;
    const wasEdit = Boolean(state.edit), path = wasEdit ? `/api/requests/${state.edit.id}` : "/api/requests";
    const result = await api(path, { method: wasEdit ? "PATCH" : "POST", body: JSON.stringify(payload) });
    editor.close(); form.reset(); state.page = 1; state.detail = result.item; message(wasEdit ? "edited" : "posted");
    loadList(); renderDetail(); if (!detail.open) detail.showModal();
  }); });
  $("[data-board-edit]").addEventListener("click", () => {
    state.edit = { ...state.detail }; form.reset();
    for (const [key, value] of Object.entries({ title: state.edit.title, body: state.edit.body, nickname: state.edit.nickname, category: state.edit.category, appVersion: state.edit.app_version, platform: state.edit.platform })) form.elements[key].value = value;
    $("[data-board-error]", form).textContent = ""; detail.close(); renderEditor(); editor.showModal(); form.elements.title.focus();
  });
  $("[data-board-delete]").addEventListener("click", () => {
    const dialog = $("[data-board-delete-dialog]"), deletion = $("[data-board-delete-form]"); deletion.reset();
    const active = adminActive(); $("[data-board-delete-password-label]").hidden = active; deletion.elements.password.required = !active;
    $("[data-board-error]", deletion).textContent = ""; detail.close(); dialog.showModal();
  });
  $("[data-board-delete-form]").addEventListener("submit", (event) => { event.preventDefault(); const deletion = event.currentTarget; submit(deletion, async () => {
    const active = adminActive(); await api(`/api/${active ? "admin/" : ""}requests/${state.detail.id}`, { method: "DELETE", admin: active, body: JSON.stringify({ password: deletion.elements.password.value }) });
    $("[data-board-delete-dialog]").close(); state.detail = null; message("deleted"); loadList();
  }); });
  $("[data-board-admin]").addEventListener("click", async () => {
    if (adminActive()) {
      try { await api("/api/admin/logout", { method: "POST", admin: true }); state.token = null; state.expires = 0; renderAdmin(); message("loggedOut"); }
      catch (exception) { message(exception.code || "unavailable"); }
    } else { const login = $("[data-board-admin-form]"); login.reset(); $("[data-board-error]", login).textContent = ""; $("[data-board-admin-dialog]").showModal(); }
  });
  $("[data-board-admin-form]").addEventListener("submit", (event) => { event.preventDefault(); const login = event.currentTarget; submit(login, async () => {
    const result = await api("/api/admin/login", { method: "POST", body: JSON.stringify({ password: login.elements.password.value }) }); state.token = result.token; state.expires = result.expiresAt;
    $("[data-board-admin-dialog]").close(); renderAdmin(); message("adminReady");
  }); });
  adminForm.addEventListener("submit", (event) => { event.preventDefault(); submit(adminForm, async () => {
    const result = await api(`/api/admin/requests/${state.detail.id}`, { method: "PATCH", admin: true, body: JSON.stringify(Object.fromEntries(new FormData(adminForm))) });
    state.detail = result.item; renderDetail(); message("statusSaved"); loadList();
  }); });
  document.addEventListener("aircalendar:language", localize);
  document.addEventListener("aircalendar:config", (event) => {
    if (event.detail.appVersion) state.version = event.detail.appVersion;
    const endpoint = event.detail.requestBoardApi;
    if (endpoint && /^https:\/\//.test(endpoint) && endpoint.replace(/\/$/, "") !== state.api) { state.api = endpoint.replace(/\/$/, ""); loadList(); }
  });
  localize(); loadList();
})();
