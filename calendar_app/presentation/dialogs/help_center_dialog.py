"""Searchable F1 help center dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    get_shortcut_guide_entries,
    render_keycaps_html,
    search_shortcut_guide_entries,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


class HelpCenterDialog(QDialog):
    """Intuitive, searchable keyboard help center."""

    _PAGE_ORDER = (
        ("quickstart", "빠른 시작", "처음 찾는 기능과 가장 자주 쓰는 작업"),
        ("workflows", "자주 하는 작업", "상황별로 묶은 핵심 단축키"),
        ("recovery", "화면 복구", "잠금, 메뉴 숨김, 창 복구 관련 키"),
        ("reference", "전체 단축키", "분류별 전체 목록"),
    )
    _QUICKSTART_IDS = (
        "new_schedule",
        "today",
        "focus_mode",
        "topbar",
        "widget_mode",
        "help",
    )
    _RECOVERY_PRIMARY_IDS = (
        "topbar",
        "lock_mode",
        "force_unlock",
        "restore_pos",
    )
    _RECOVERY_SECONDARY_IDS = (
        "show_hide",
        "magnet_mode",
        "away_lock",
        "fullscreen",
        "opacity_up",
        "opacity_down",
    )
    _WORKFLOW_SECTIONS = (
        (
            "새로 만들기",
            "일정과 업무를 빠르게 시작할 때",
            ("new_schedule", "new_routine", "new_directive", "checklist"),
        ),
        (
            "이동과 탐색",
            "날짜 이동과 기능 검색을 빠르게 처리할 때",
            ("today", "prev_day", "next_day", "command_palette"),
        ),
        (
            "화면과 레이아웃",
            "보이는 방식과 패널 배치를 바꿀 때",
            (
                "topbar",
                "cal_toolbar",
                "fullscreen",
                "widget_mode",
                "save_layout",
                "layout_1",
                "layout_2",
                "layout_3",
                "layout_4",
                "layout_5",
            ),
        ),
        (
            "집중과 잠금",
            "집중 상태나 잠금 상태를 제어할 때",
            ("focus_mode", "focus_pause", "magnet_mode", "lock_mode", "away_lock"),
        ),
        (
            "창과 관리 도구",
            "창 상태 조절이나 관리 기능이 필요할 때",
            (
                "show_hide",
                "restore_pos",
                "monitor_left",
                "monitor_right",
                "routine_mgr",
                "color_assign",
            ),
        ),
    )

    def __init__(
        self, parent=None, *, app_version: str = "", app_author: str = "", app_email: str = ""
    ):
        super().__init__(parent)
        self._entries = get_shortcut_guide_entries()
        self._entry_by_id = {entry["id"]: entry for entry in self._entries}
        self._page_indexes: dict[str, int] = {}
        self._selected_page_id = "quickstart"
        self._app_version = str(app_version or "").strip()
        self._app_author = str(app_author or "").strip()
        self._app_email = str(app_email or "").strip()

        self._build_ui()
        self._populate_pages()
        self._select_default_page()

    def _build_ui(self) -> None:
        tokens = get_dialog_theme_tokens(apply_overrides=True)
        metrics = get_dialog_metric_tokens(apply_overrides=True)
        shell_radius = max(16, int(metrics.get("group_radius", 12)) + 4)
        sidebar_width = 214

        self.setObjectName("HelpCenterDialog")
        apply_dialog_title(self, t("shortcut.title", "Dark Calendar 도움말 센터"))
        self.setSizeGripEnabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        apply_common_dialog_style(
            self,
            minimum_width=1180,
            size=(1260, 860),
            extra_stylesheet=(
                f"QFrame#helpCenterHeader {{"
                f"background: rgba(10, 15, 25, 0.98);"
                f"border: 1px solid rgba(77, 166, 255, 0.16);"
                f"border-radius: {shell_radius + 2}px;"
                f"}}"
                f"QLabel#helpCenterEyebrow {{"
                f"color: #7db4ff;"
                f"font-size: 11px;"
                f"font-weight: 800;"
                f"letter-spacing: 1px;"
                f"}}"
                f"QLabel#helpCenterTitle {{"
                f"color: #f5f8ff;"
                f"font-size: 26px;"
                f"font-weight: 800;"
                f"}}"
                f"QLabel#helpCenterSubtitle {{"
                f"color: {tokens.get('text_faint', '#94a8c2')};"
                f"font-size: 12px;"
                f"}}"
                f"QFrame#helpCenterBadge, QFrame#helpCenterBadgeAccent {{"
                f"border-radius: 999px;"
                f"padding: 0px;"
                f"}}"
                f"QFrame#helpCenterBadge {{"
                f"background: rgba(255, 255, 255, 0.05);"
                f"border: 1px solid rgba(255, 255, 255, 0.08);"
                f"}}"
                f"QFrame#helpCenterBadgeAccent {{"
                f"background: rgba(77, 166, 255, 0.14);"
                f"border: 1px solid rgba(77, 166, 255, 0.24);"
                f"}}"
                f"QLabel#helpCenterBadgeText {{"
                f"color: #d7e5f7;"
                f"font-size: 10px;"
                f"font-weight: 700;"
                f"}}"
                f"QLabel#helpCenterBadgeTextAccent {{"
                f"color: #e6f1ff;"
                f"font-size: 10px;"
                f"font-weight: 800;"
                f"}}"
                f"QLineEdit#helpCenterSearch {{"
                f"padding: 11px 14px;"
                f"border-radius: {shell_radius - 2}px;"
                f"background: rgba(6, 10, 18, 0.92);"
                f"border: 1px solid rgba(77, 166, 255, 0.18);"
                f"color: #f5f8ff;"
                f"selection-background-color: rgba(77, 166, 255, 0.32);"
                f"}}"
                f"QLineEdit#helpCenterSearch:focus {{"
                f"border: 1px solid rgba(77, 166, 255, 0.42);"
                f"}}"
                f"QFrame#helpCenterSidebar {{"
                f"background: rgba(10, 16, 28, 0.92);"
                f"border: 1px solid rgba(255, 255, 255, 0.08);"
                f"border-radius: {shell_radius}px;"
                f"}}"
                f"QLabel#helpCenterSidebarTitle {{"
                f"color: #f5f8ff;"
                f"font-size: 14px;"
                f"font-weight: 800;"
                f"}}"
                f"QLabel#helpCenterSidebarHint {{"
                f"color: {tokens.get('text_faint', '#8da1bc')};"
                f"font-size: 11px;"
                f"}}"
                f"QListWidget#helpCenterNav {{"
                f"background: transparent;"
                f"border: none;"
                f"outline: none;"
                f"}}"
                f"QListWidget#helpCenterNav::item {{"
                f"margin: 0px 0px 6px 0px;"
                f"padding: 12px 14px;"
                f"border-radius: {shell_radius - 2}px;"
                f"color: #d8e5f5;"
                f"background: rgba(255, 255, 255, 0.02);"
                f"}}"
                f"QListWidget#helpCenterNav::item:selected {{"
                f"color: #f5f8ff;"
                f"background: rgba(77, 166, 255, 0.18);"
                f"border: 1px solid rgba(77, 166, 255, 0.30);"
                f"}}"
                f"QListWidget#helpCenterNav::item:hover {{"
                f"background: rgba(255, 255, 255, 0.05);"
                f"}}"
                f"QFrame#helpCenterContent {{"
                f"background: rgba(10, 16, 28, 0.76);"
                f"border: 1px solid rgba(255, 255, 255, 0.06);"
                f"border-radius: {shell_radius}px;"
                f"}}"
                f"QScrollArea#helpCenterScroll {{"
                f"background: transparent;"
                f"border: none;"
                f"}}"
                f"QWidget#helpCenterPageBody {{"
                f"background: transparent;"
                f"}}"
                f"QFrame#helpPageHero {{"
                f"background: rgba(10, 15, 25, 0.98);"
                f"border: 1px solid rgba(77, 166, 255, 0.14);"
                f"border-radius: {shell_radius}px;"
                f"}}"
                f"QLabel#helpPageEyebrow {{"
                f"color: #7db4ff;"
                f"font-size: 11px;"
                f"font-weight: 800;"
                f"letter-spacing: 1px;"
                f"}}"
                f"QLabel#helpPageTitle {{"
                f"color: #f5f8ff;"
                f"font-size: 22px;"
                f"font-weight: 800;"
                f"}}"
                f"QLabel#helpPageSubtitle {{"
                f"color: #9fb3d1;"
                f"font-size: 12px;"
                f"}}"
                f"QFrame#helpSectionSurface {{"
                f"background: rgba(255, 255, 255, 0.03);"
                f"border: 1px solid rgba(255, 255, 255, 0.06);"
                f"border-radius: {shell_radius - 2}px;"
                f"}}"
                f"QLabel#helpSectionTitle {{"
                f"color: #f5f8ff;"
                f"font-size: 16px;"
                f"font-weight: 800;"
                f"}}"
                f"QLabel#helpSectionDesc {{"
                f"color: #8fa6c5;"
                f"font-size: 11px;"
                f"}}"
                f"QFrame#helpShortcutCard, QFrame#helpShortcutCardAccent {{"
                f"border-radius: {shell_radius - 4}px;"
                f"}}"
                f"QFrame#helpShortcutCard {{"
                f"background: rgba(255, 255, 255, 0.03);"
                f"border: 1px solid rgba(255, 255, 255, 0.06);"
                f"}}"
                f"QFrame#helpShortcutCardAccent {{"
                f"background: rgba(11, 18, 30, 0.96);"
                f"border: 1px solid rgba(77, 166, 255, 0.18);"
                f"}}"
                f"QLabel#helpCardBadge {{"
                f"color: #7db4ff;"
                f"font-size: 10px;"
                f"font-weight: 800;"
                f"letter-spacing: 1px;"
                f"}}"
                f"QLabel#helpCardTitle {{"
                f"color: #f5f8ff;"
                f"font-size: 14px;"
                f"font-weight: 800;"
                f"}}"
                f"QLabel#helpCardDescription {{"
                f"color: #9fb3d1;"
                f"font-size: 11px;"
                f"}}"
                f"QLabel#helpCardMeta {{"
                f"color: #7f95b2;"
                f"font-size: 10px;"
                f"}}"
                f"QLabel#helpCardKeys {{"
                f"color: #e8f1ff;"
                f"font-size: 11px;"
                f"}}"
                f"QLabel#helpFooterText {{"
                f"color: {tokens.get('text_faint', '#8da1bc')};"
                f"font-size: 11px;"
                f"}}"
            ),
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("helpCenterHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 20, 22, 18)
        header_layout.setSpacing(18)

        header_left = QVBoxLayout()
        header_left.setSpacing(8)
        eyebrow = QLabel("F1 HELP CENTER")
        eyebrow.setObjectName("helpCenterEyebrow")
        title = QLabel("단축키와 기능을 바로 찾는 도움말 센터")
        title.setObjectName("helpCenterTitle")
        subtitle = QLabel(
            "기능 이름, 키 이름, 메뉴 위치로 검색하고 자주 하는 작업부터 빠르게 찾아보세요."
        )
        subtitle.setObjectName("helpCenterSubtitle")
        subtitle.setWordWrap(True)
        header_left.addWidget(eyebrow)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 4, 0, 0)
        badge_row.setSpacing(8)
        badge_row.addWidget(self._create_badge("핵심 복구 키 4개", accent=True))
        badge_row.addWidget(self._create_badge(f"전체 단축키 {len(self._entries)}개"))
        badge_row.addWidget(self._create_badge("검색 지원"))
        badge_row.addStretch(1)
        header_left.addLayout(badge_row)
        header_layout.addLayout(header_left, 1)

        header_right = QVBoxLayout()
        header_right.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("helpCenterSearch")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setPlaceholderText("예: 잠금, 위젯, F11, Ctrl+Shift+1")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        header_right.addWidget(self.search_input)

        search_hint = QLabel("검색 예시: 메뉴바, 캘린더, 루틴, 강제 잠금 해제")
        search_hint.setObjectName("helpCenterSubtitle")
        search_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_right.addWidget(search_hint)
        header_layout.addLayout(header_right)

        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        sidebar = QFrame()
        sidebar.setObjectName("helpCenterSidebar")
        sidebar.setFixedWidth(sidebar_width)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(10)

        sidebar_title = QLabel("탐색")
        sidebar_title.setObjectName("helpCenterSidebarTitle")
        sidebar_hint = QLabel("왼쪽에서 섹션을 고르고, 위 검색창으로 바로 찾을 수 있습니다.")
        sidebar_hint.setObjectName("helpCenterSidebarHint")
        sidebar_hint.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_title)
        sidebar_layout.addWidget(sidebar_hint)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("helpCenterNav")
        self.nav_list.currentItemChanged.connect(self._on_page_changed)
        sidebar_layout.addWidget(self.nav_list, 1)
        body.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("helpCenterContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        content_layout.addWidget(self.page_stack)
        body.addWidget(content, 1)
        root.addLayout(body, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 2, 2, 0)
        footer.setSpacing(10)
        footer_hint = QLabel(self._footer_text())
        footer_hint.setObjectName("helpFooterText")
        footer.addWidget(footer_hint, 1)

        close_btn = QPushButton(t("common.close", "닫기"))
        close_btn.setObjectName("primary_btn")
        close_btn.setFixedWidth(max(92, int(metrics.get("button_min_width", 45)) + 14))
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._find_shortcut.activated.connect(self._focus_search)

    def _populate_pages(self) -> None:
        self.page_stack.addWidget(self._build_search_page())
        self._page_indexes["search"] = 0

        for page_id, label, hint in self._PAGE_ORDER:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, page_id)
            item.setToolTip(hint)
            self.nav_list.addItem(item)

            if page_id == "quickstart":
                widget = self._build_quickstart_page()
            elif page_id == "workflows":
                widget = self._build_workflows_page()
            elif page_id == "recovery":
                widget = self._build_recovery_page()
            else:
                widget = self._build_reference_page()
            self.page_stack.addWidget(widget)
            self._page_indexes[page_id] = self.page_stack.count() - 1

    def _select_default_page(self) -> None:
        self.nav_list.setCurrentRow(0)
        self.search_input.setFocus()

    def _footer_text(self) -> str:
        parts = ["검색은 기능 이름, 단축키, 메뉴 위치 기준으로 동작합니다."]
        version_label = self._app_version
        if version_label:
            parts.append(version_label)
        author_bits = self._app_author
        if self._app_email:
            author_bits = f"{author_bits} ({self._app_email})" if author_bits else self._app_email
        if author_bits:
            parts.append(author_bits)
        return "  |  ".join(parts)

    def _create_badge(self, text: str, *, accent: bool = False) -> QWidget:
        frame = QFrame()
        frame.setObjectName("helpCenterBadgeAccent" if accent else "helpCenterBadge")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)
        label = QLabel(text)
        label.setObjectName("helpCenterBadgeTextAccent" if accent else "helpCenterBadgeText")
        layout.addWidget(label)
        return frame

    def _create_scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("helpCenterScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("helpCenterPageBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)
        scroll.setWidget(body)
        return scroll, layout

    def _create_page_hero(self, eyebrow: str, title: str, subtitle: str) -> QWidget:
        frame = QFrame()
        frame.setObjectName("helpPageHero")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(8)

        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("helpPageEyebrow")
        title_label = QLabel(title)
        title_label.setObjectName("helpPageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("helpPageSubtitle")
        subtitle_label.setWordWrap(True)

        layout.addWidget(eyebrow_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return frame

    def _create_section(self, title: str, description: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("helpSectionSurface")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("helpSectionTitle")
        desc_label = QLabel(description)
        desc_label.setObjectName("helpSectionDesc")
        desc_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        return frame, layout

    def _build_quickstart_page(self) -> QWidget:
        page, layout = self._create_scroll_page()
        layout.addWidget(
            self._create_page_hero(
                "QUICK START",
                "가장 자주 찾는 작업부터 바로 보이게",
                "처음 앱을 열었을 때 바로 쓰는 기능과, F1을 눌렀을 때 당장 찾게 되는 기능을 먼저 배치했습니다.",
            )
        )

        section, section_layout = self._create_section(
            "바로 시작하기",
            "처음 쓰는 사용자도 여기서 시작하면 바로 흐름을 잡을 수 있습니다.",
        )
        section_layout.addLayout(self._create_cards_grid(self._QUICKSTART_IDS))
        layout.addWidget(section)

        hint_section, hint_layout = self._create_section(
            "검색 팁",
            "도움말은 단축키뿐 아니라 메뉴 이름과 상황 키워드로도 검색됩니다.",
        )
        tips = (
            "잠금 상태가 풀리지 않을 때: `잠금`, `복구`, `강제`",
            "레이아웃을 바꾸고 싶을 때: `레이아웃`, `프리셋`, `Ctrl+Shift+1`",
            "위젯 관련 기능을 찾을 때: `위젯`, `F12`",
        )
        for tip in tips:
            label = QLabel(tip)
            label.setObjectName("helpCardMeta")
            label.setWordWrap(True)
            hint_layout.addWidget(label)
        layout.addWidget(hint_section)
        layout.addStretch(1)
        return page

    def _build_workflows_page(self) -> QWidget:
        page, layout = self._create_scroll_page()
        layout.addWidget(
            self._create_page_hero(
                "CORE FLOW",
                "상황별로 묶어서 더 빨리 찾기",
                "등록, 이동, 화면 전환처럼 실제 사용 흐름 중심으로 묶었습니다. 이름을 몰라도 상황만 떠올리면 찾을 수 있게 구성했습니다.",
            )
        )

        for title, desc, shortcut_ids in self._WORKFLOW_SECTIONS:
            section, section_layout = self._create_section(title, desc)
            for shortcut_id in shortcut_ids:
                entry = self._entry_by_id.get(shortcut_id)
                if entry is not None:
                    section_layout.addWidget(self._create_shortcut_card(entry, dense=True))
            layout.addWidget(section)
        layout.addStretch(1)
        return page

    def _build_recovery_page(self) -> QWidget:
        page, layout = self._create_scroll_page()
        layout.addWidget(
            self._create_page_hero(
                "RECOVERY",
                "막혔을 때 먼저 눌러볼 키",
                "메뉴가 사라졌거나 잠금 상태가 꼬였을 때 가장 먼저 봐야 하는 키만 따로 모았습니다.",
            )
        )

        primary, primary_layout = self._create_section(
            "우선 확인할 복구 키",
            "문제가 생겼을 때 가장 먼저 시도할 키입니다.",
        )
        primary_layout.addLayout(self._create_cards_grid(self._RECOVERY_PRIMARY_IDS, accent=True))
        layout.addWidget(primary)

        secondary, secondary_layout = self._create_section(
            "함께 기억하면 좋은 보조 키",
            "잠금이나 창 상태를 정리할 때 같이 자주 찾는 단축키입니다.",
        )
        for shortcut_id in self._RECOVERY_SECONDARY_IDS:
            entry = self._entry_by_id.get(shortcut_id)
            if entry is not None:
                secondary_layout.addWidget(self._create_shortcut_card(entry, dense=True))
        layout.addWidget(secondary)
        layout.addStretch(1)
        return page

    def _build_reference_page(self) -> QWidget:
        page, layout = self._create_scroll_page()
        layout.addWidget(
            self._create_page_hero(
                "REFERENCE",
                "전체 단축키를 분류별로 보기",
                "모든 단축키를 기능 그룹별로 정리했습니다. 검색 없이 훑어볼 때 적합합니다.",
            )
        )

        groups: list[str] = []
        for entry in self._entries:
            group = str(entry.get("group") or "")
            if group and group not in groups:
                groups.append(group)

        for group in groups:
            group_entries = [entry for entry in self._entries if entry.get("group") == group]
            if not group_entries:
                continue
            section, section_layout = self._create_section(
                str(group_entries[0].get("group_label_ko") or group),
                str(group_entries[0].get("group_description_ko") or ""),
            )
            for entry in group_entries:
                section_layout.addWidget(self._create_shortcut_card(entry, dense=True))
            layout.addWidget(section)
        layout.addStretch(1)
        return page

    def _build_search_page(self) -> QWidget:
        page, layout = self._create_scroll_page()
        layout.addWidget(
            self._create_page_hero(
                "SEARCH",
                "검색 결과",
                "키 이름이나 기능 이름을 입력하면 관련 단축키를 바로 보여줍니다.",
            )
        )
        self.search_results_section, self.search_results_layout = self._create_section(
            "검색 결과",
            "검색어를 입력하면 여기에서 바로 결과를 보여줍니다.",
        )
        self.search_results_count = QLabel("")
        self.search_results_count.setObjectName("helpCardMeta")
        self.search_results_layout.addWidget(self.search_results_count)

        self.search_results_container = QWidget()
        self.search_results_container_layout = QVBoxLayout(self.search_results_container)
        self.search_results_container_layout.setContentsMargins(0, 0, 0, 0)
        self.search_results_container_layout.setSpacing(10)
        self.search_results_layout.addWidget(self.search_results_container)

        layout.addWidget(self.search_results_section)
        layout.addStretch(1)
        return page

    def _create_cards_grid(
        self, shortcut_ids: tuple[str, ...] | list[str], *, accent: bool = False
    ) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        column_count = 2

        for index, shortcut_id in enumerate(shortcut_ids):
            entry = self._entry_by_id.get(shortcut_id)
            if entry is None:
                continue
            card = self._create_shortcut_card(entry, accent=accent)
            grid.addWidget(card, index // column_count, index % column_count)
        return grid

    def _create_shortcut_card(
        self, entry: dict, *, accent: bool = False, dense: bool = False
    ) -> QWidget:
        frame = QFrame()
        frame.setObjectName("helpShortcutCardAccent" if accent else "helpShortcutCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            14 if dense else 16, 13 if dense else 16, 14 if dense else 16, 12 if dense else 14
        )
        layout.setSpacing(8 if dense else 10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        badge_text = str(entry.get("priority_badge_ko") or entry.get("group_label_ko") or "")
        badge = QLabel(badge_text)
        badge.setObjectName("helpCardBadge")
        top_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        top_row.addStretch(1)

        key_label = QLabel(self._render_entry_keys_html(entry, accent=accent))
        key_label.setObjectName("helpCardKeys")
        key_label.setTextFormat(Qt.TextFormat.RichText)
        key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        key_label.setWordWrap(True)
        top_row.addWidget(key_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top_row)

        title_label = QLabel(str(entry.get("label_ko") or ""))
        title_label.setObjectName("helpCardTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        desc_label = QLabel(str(entry.get("description_ko") or ""))
        desc_label.setObjectName("helpCardDescription")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        meta_lines: list[str] = []
        menu_path = str(entry.get("menu_path_ko") or "").strip()
        if menu_path:
            meta_lines.append(f"메뉴 위치: {menu_path}")
        aliases = [str(alias).strip() for alias in entry.get("aliases", []) if str(alias).strip()]
        if aliases:
            meta_lines.append(f"추가 키: {', '.join(aliases)}")
        meta_lines.append(f"분류: {entry.get('group_label_ko', '')}")
        meta_label = QLabel("\n".join(meta_lines))
        meta_label.setObjectName("helpCardMeta")
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)
        return frame

    def _render_entry_keys_html(self, entry: dict, *, accent: bool = False) -> str:
        parts = [render_keycaps_html(str(entry.get("key") or ""), accent=accent)]
        aliases = [str(alias).strip() for alias in entry.get("aliases", []) if str(alias).strip()]
        for alias in aliases:
            parts.append(render_keycaps_html(alias, accent=accent))
        if len(parts) == 1:
            return parts[0]
        separator = "<span style='color:#6f86a3; font-size:10px; padding:0 4px;'>or</span>"
        return separator.join(parts)

    def _on_page_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        page_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        if not page_id:
            return
        self._selected_page_id = page_id
        if not self.search_input.text().strip():
            self.page_stack.setCurrentIndex(self._page_indexes.get(page_id, 0))

    def _on_search_text_changed(self, text: str) -> None:
        query = str(text or "").strip()
        if not query:
            self.page_stack.setCurrentIndex(self._page_indexes.get(self._selected_page_id, 0))
            return

        self._populate_search_results(query)
        self.page_stack.setCurrentIndex(self._page_indexes["search"])

    def _populate_search_results(self, query: str) -> None:
        while self.search_results_container_layout.count():
            item = self.search_results_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        results = search_shortcut_guide_entries(query)
        self.search_results_count.setText(f"'{query}' 검색 결과 {len(results)}개")

        if not results:
            empty = QLabel(
                "일치하는 결과가 없습니다.\n기능 이름, 키 이름, 메뉴 이름처럼 더 짧은 키워드로 다시 검색해 보세요."
            )
            empty.setObjectName("helpCardDescription")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.search_results_container_layout.addWidget(empty)
            self.search_results_container_layout.addStretch(1)
            return

        for entry in results:
            card = self._create_shortcut_card(entry, accent=bool(entry.get("recovery")), dense=True)
            self.search_results_container_layout.addWidget(card)
        self.search_results_container_layout.addStretch(1)

    def _focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()
