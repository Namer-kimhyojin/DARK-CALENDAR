import contextlib
from datetime import datetime
import os
import shutil
import webbrowser
from zoneinfo import available_timezones

from PyQt6.QtCore import QSettings, QSize, Qt, QTimeZone
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.app_paths import APP_NAME, APP_VENDOR, CREDENTIALS_PATH, TOKEN_PATH
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_settings_dialog_stylesheet,
    build_settings_style_bundle,
    build_settings_swatch_style,
    build_task_editor_stylesheet,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR
from calendar_app.shared.datetime_utils import timezone_offset_for_name
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

_COMMON_TIMEZONES = [
    "UTC",
    "Asia/Seoul",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Asia/Bangkok",
    "Asia/Dubai",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "Australia/Sydney",
    "Pacific/Auckland",
]


class GCalSettingsDialog(QDialog):
    def __init__(self, parent=None, initial_tab: str | None = None):
        super().__init__(parent)
        self.parent_app = parent
        self._initial_tab = initial_tab
        self.settings = (
            parent.settings
            if parent is not None and hasattr(parent, "settings")
            else QSettings(APP_VENDOR, APP_NAME)
        )
        apply_dialog_title(self, t("gcal_settings.title", "캘린더 및 동기화 설정"))
        self.setMinimumSize(900, 580)
        self.resize(1020, 680)
        self._all_timezones = self._build_timezone_list()
        self._calendar_choices = []
        self._browse_creds_open = False
        self._nav_btns = []
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = build_settings_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        self._load_state()
        self._refresh_status()
        # initial_tab으로 직접 이동
        if initial_tab == "calendar":
            self._switch_section(1)

    # ──────────────────────────────────────────────
    # UI 초기화
    # ──────────────────────────────────────────────

    def _init_ui(self):
        # Rebuild stylesheet on each dialog creation so token changes apply immediately.
        self.setStyleSheet(build_settings_dialog_stylesheet(self._ui_tokens))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 상태 헤더 (compact 한 줄) ──────────────
        root.addWidget(self._build_status_bar())

        # ── 사이드바 + 콘텐츠 영역 ──────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content_area(), 1)
        root.addLayout(body, 1)

        # ── 푸터 ────────────────────────────────────
        root.addWidget(self._build_footer())

        # 첫 섹션 활성화
        self._switch_section(0)

    # ──────────────────────────────────────────────
    # 상태 헤더 (compact bar)
    # ──────────────────────────────────────────────

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setStyleSheet(self._style_bundle["status_bar"])
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(12)

        # 상태 아이콘 + 텍스트
        self.status_title = QLabel()
        self.status_title.setProperty("role", "statusLabel")
        self.status_title.setStyleSheet(self._style_bundle["status_title_pending"])
        layout.addWidget(self.status_title)

        self.status_pill = QLabel()
        self.status_pill.setProperty("role", "pill")
        self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
        layout.addWidget(self.status_pill)

        layout.addSpacing(8)

        # 구분선
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(self._style_bundle["status_separator"])
        layout.addWidget(sep1)

        layout.addSpacing(8)

        # 계정 메타
        lbl_acc = QLabel(t("gcal_settings.meta_account", "계정"))
        lbl_acc.setProperty("role", "statusBarMeta")
        lbl_acc.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_acc)
        self.account_meta = (None, QLabel("-"))
        self.account_meta[1].setProperty("role", "statusBarMetaVal")
        self.account_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        self.account_meta[1].setMaximumWidth(180)
        self.account_meta[1].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.account_meta[1])

        layout.addSpacing(12)

        lbl_cal = QLabel(t("gcal_settings.meta_calendar", "캘린더"))
        lbl_cal.setProperty("role", "statusBarMeta")
        lbl_cal.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_cal)
        self.calendar_meta = (None, QLabel("-"))
        self.calendar_meta[1].setProperty("role", "statusBarMetaVal")
        self.calendar_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        self.calendar_meta[1].setMaximumWidth(200)
        self.calendar_meta[1].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.calendar_meta[1])

        layout.addSpacing(12)

        lbl_sync = QLabel(t("gcal_settings.meta_last_sync", "마지막 동기화"))
        lbl_sync.setProperty("role", "statusBarMeta")
        lbl_sync.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_sync)
        self.last_sync_meta = (None, QLabel("-"))
        self.last_sync_meta[1].setProperty("role", "statusBarMetaVal")
        self.last_sync_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        layout.addWidget(self.last_sync_meta[1])

        layout.addStretch(1)
        return bar

    # ──────────────────────────────────────────────
    # 사이드바
    # ──────────────────────────────────────────────

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(self._style_bundle["sidebar_shell"])
        sidebar.setFixedWidth(152)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        nav_items = [
            (t("gcal_settings.nav_connection", "연결"), _ic(ICON.LINK)),
            (t("gcal_settings.nav_calendar", "캘린더"), _ic(ICON.VIEW_CALENDAR)),
            (t("gcal_settings.nav_subscription", "구독"), _ic(ICON.GCAL)),
            (t("gcal_settings.nav_sync", "동기화"), _ic(ICON.SYNC)),
            (t("gcal_settings.nav_diagnostics", "진단"), _ic(ICON.SEARCH)),
            (t("gcal_settings.nav_guide", "가이드"), _ic(ICON.DOCS)),
        ]

        for idx, (label, nav_icon) in enumerate(nav_items):
            btn = QPushButton(_se(label))
            btn.setIcon(nav_icon)
            btn.setCheckable(False)
            btn.setStyleSheet(self._style_bundle["nav_button"])
            btn.clicked.connect(lambda _, i=idx: self._switch_section(i))
            self._nav_btns.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        return sidebar

    def _switch_section(self, idx: int):
        for i, btn in enumerate(self._nav_btns):
            btn.setStyleSheet(self._style_bundle["nav_button_active" if i == idx else "nav_button"])
        self._stack.setCurrentIndex(idx)

    # ──────────────────────────────────────────────
    # 콘텐츠 영역 (QStackedWidget)
    # ──────────────────────────────────────────────

    def _build_content_area(self) -> QWidget:
        container = QWidget()
        container.setObjectName("contentArea")
        container.setStyleSheet(self._style_bundle["content_area"])
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._wrap_scroll(self._build_connection_section()))  # 0
        self._stack.addWidget(self._wrap_scroll(self._build_calendar_section()))  # 1
        self._stack.addWidget(self._wrap_scroll(self._build_subscription_section()))  # 2
        self._stack.addWidget(self._wrap_scroll(self._build_sync_section()))  # 3
        self._stack.addWidget(self._wrap_scroll(self._build_diagnostics_section()))  # 4
        self._stack.addWidget(self._wrap_scroll(self._build_guide_section()))  # 5

        layout.addWidget(self._stack)
        return container

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setStyleSheet(self._style_bundle["scroll_shell"])
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ──────────────────────────────────────────────
    # 섹션 0: 연결
    # ──────────────────────────────────────────────

    def _build_connection_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.sync_title", "연결 설정"))
        cl = card.layout()

        # Enable toggle
        enable_row = QHBoxLayout()
        self.enable_cb = QCheckBox(t("gcal_settings.enable", "Google Calendar 동기화 사용"))
        self.enable_cb.setStyleSheet(self._style_bundle["check_toggle"])
        enable_row.addWidget(self.enable_cb)
        enable_row.addStretch(1)
        cl.addLayout(enable_row)
        cl.addWidget(self._make_divider())

        # Credentials
        cl.addWidget(self._field_label(t("gcal_settings.creds_label", "OAuth 인증 파일")))
        creds_row = QHBoxLayout()
        creds_row.setSpacing(8)
        self.creds_path_edit = QLineEdit()
        self._apply_input_style(self.creds_path_edit, "line")
        self.creds_path_edit.setPlaceholderText(
            t("gcal_settings.creds_placeholder", "credentials.json 경로")
        )
        browse_btn = QPushButton(t("gcal_settings.browse", "파일 선택"))
        self._apply_section_button_style(browse_btn, "secondary")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self.browse_creds)
        creds_row.addWidget(self.creds_path_edit, 1)
        creds_row.addWidget(browse_btn)
        cl.addLayout(creds_row)
        cl.addWidget(
            self._help_label(
                t("gcal_settings.creds_help", "Desktop OAuth 클라이언트 JSON만 지원합니다.")
            )
        )

        cl.addSpacing(8)
        cl.addWidget(self._make_divider())
        cl.addSpacing(4)

        # Test access
        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.test_access_btn = QPushButton(t("gcal_settings.test_access", "캘린더 접근 테스트"))
        self.test_access_btn.setIcon(_ic(ICON.SEARCH))
        self._apply_section_button_style(self.test_access_btn, "accent")
        self.test_access_btn.clicked.connect(self._test_calendar_access)
        self.test_access_result = QLabel(
            t("gcal_settings.test_access_idle", "아직 테스트하지 않았습니다.")
        )
        self.test_access_result.setProperty("role", "help")
        self.test_access_result.setStyleSheet(self._style_bundle["help"])
        self.test_access_result.setWordWrap(True)
        test_row.addWidget(self.test_access_btn, 0)
        test_row.addWidget(self.test_access_result, 1)
        cl.addLayout(test_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 섹션 1: 캘린더
    # ──────────────────────────────────────────────

    # ── 캘린더 카드 아이템 (테이블 대체) ──────────────────────────────────

    def _make_color_swatch(self, color_str: str, size: int = 18) -> QPushButton:
        """클릭 가능한 색상 스와치 버튼."""
        btn = QPushButton()
        btn.setFixedSize(size, size)
        btn.setToolTip(t("gcal_settings.color_swatch_tip", "색상 변경"))
        self._apply_swatch_color(btn, color_str)
        return btn

    def _apply_swatch_color(self, btn: QPushButton, color_str: str):
        c = QColor(color_str) if color_str else QColor("#4da6ff")
        if not c.isValid():
            c = QColor("#4da6ff")
        hex_c = c.name()
        btn.setStyleSheet(build_settings_swatch_style(hex_c, self._ui_tokens))
        btn.setProperty("_color", hex_c)

    def _calendar_name_style(self) -> str:
        color = self._ui_tokens.get("text_primary", "#f4f7fb")
        return f"color: {color}; font-size: 13px; font-weight: 600; background: transparent;"

    def _calendar_row_action_button_style(self, tone: str = "neutral") -> str:
        tone_key = str(tone or "neutral").lower()
        style_map = {
            "neutral": {
                "bg": "#1e2536",
                "border": "#34425d",
                "hover_bg": "#26304a",
                "hover_border": "#45608a",
            },
            "accent": {
                "bg": "rgba(77, 166, 255, 0.16)",
                "border": "rgba(77, 166, 255, 0.42)",
                "hover_bg": "rgba(77, 166, 255, 0.24)",
                "hover_border": "rgba(77, 166, 255, 0.68)",
            },
            "warning": {
                "bg": "rgba(255, 196, 74, 0.16)",
                "border": "rgba(255, 196, 74, 0.42)",
                "hover_bg": "rgba(255, 196, 74, 0.24)",
                "hover_border": "rgba(255, 196, 74, 0.68)",
            },
            "danger": {
                "bg": "rgba(210, 90, 102, 0.16)",
                "border": "rgba(210, 90, 102, 0.42)",
                "hover_bg": "rgba(210, 90, 102, 0.24)",
                "hover_border": "rgba(210, 90, 102, 0.68)",
            },
        }
        palette = style_map.get(tone_key, style_map["neutral"])
        return (
            "QPushButton {"
            f"background-color: {palette['bg']};"
            "color: #f4f7fb;"
            f"border: 1px solid {palette['border']};"
            "border-radius: 7px;"
            "padding: 0px;"
            "min-width: 26px; max-width: 26px;"
            "min-height: 26px; max-height: 26px;"
            "}"
            "QPushButton:hover {"
            f"background-color: {palette['hover_bg']};"
            f"border: 1px solid {palette['hover_border']};"
            "}"
            "QPushButton:pressed {"
            f"background-color: {palette['hover_bg']};"
            f"border: 1px solid {palette['hover_border']};"
            "}"
        )

    def _calendar_action_separator_style(self) -> str:
        return "background: rgba(255,255,255,0.12); margin: 8px 4px;"

    def _make_calendar_row_widget(self, cal: dict, is_sub: bool = False) -> QFrame:
        """캘린더 1개를 나타내는 카드 행 위젯."""
        from PyQt6.QtWidgets import QSizePolicy

        row_frame = QFrame()
        row_frame.setObjectName("calRow")
        row_frame.setStyleSheet(self._style_bundle["calendar_row"])
        row_frame.setFixedHeight(54)
        row_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        h = QHBoxLayout(row_frame)
        h.setContentsMargins(16, 6, 16, 6)
        h.setSpacing(8)

        # ① 색상 스와치
        cal_color = str(cal.get("color") or "").strip()
        swatch = self._make_color_swatch(cal_color or "#4da6ff", size=18)
        swatch.setFixedWidth(30)  # Pill-like width
        cal_id = cal["id"]
        cal_type = cal.get("type", "local")

        def _on_swatch_click(_=None, cid=cal_id, sw=swatch):
            self._pick_calendar_color(cid, sw)

        swatch.clicked.connect(_on_swatch_click)
        h.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)

        # ② 이름 및 타입 정보 (유연한 레이아웃)
        _TYPE_LABEL = {
            "gcal": t("gcal_settings.type_gcal", "Google Calendar"),
            "ics": t("gcal_settings.type_ics", "ICS 구독"),
            "local": t("gcal_settings.type_local", "로컬"),
        }
        type_label_str = _TYPE_LABEL.get(cal_type, cal_type)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setContentsMargins(0, 0, 0, 0)

        clean_name = str(cal.get("name") or "Untitled").strip()
        name_lbl = QLabel(clean_name)
        name_lbl.setObjectName("calendarNameLabel")
        name_lbl.setStyleSheet(self._calendar_name_style())
        name_lbl.setToolTip(clean_name)
        name_lbl.setWordWrap(False)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        type_lbl = QLabel()
        type_lbl.setStyleSheet(self._style_bundle["calendar_meta"])
        type_lbl.setWordWrap(False)
        type_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        ics_url = str(cal.get("ics_url") or "").strip()
        gcal_id_str = str(cal.get("gcal_calendar_id") or "").strip()
        if ics_url:
            url_display = ics_url if len(ics_url) <= 55 else ics_url[:52] + "…"
            type_lbl.setText(f"{type_label_str}  ·  {url_display}")
            type_lbl.setToolTip(ics_url)
        elif gcal_id_str:
            id_display = gcal_id_str if len(gcal_id_str) <= 45 else gcal_id_str[:42] + "…"
            type_lbl.setText(f"{type_label_str}  ·  {id_display}")
            type_lbl.setToolTip(gcal_id_str)
        else:
            type_lbl.setText(type_label_str)

        info_layout.addWidget(name_lbl)
        info_layout.addWidget(type_lbl)
        h.addLayout(info_layout, 1)

        # ③ ICS: 마지막 동기화 시간
        if cal_type == "ics":
            last_fetched = str(cal.get("ics_last_fetched") or "").strip()
            if last_fetched:
                try:
                    dt = datetime.fromisoformat(last_fetched)
                    fetch_str = dt.strftime("%m/%d %H:%M")
                except Exception:
                    fetch_str = last_fetched[:16]
                sync_lbl = QLabel(f"{fetch_str}")
                sync_lbl.setToolTip(t("gcal_settings.ics_last_synced", "마지막 동기화"))
            else:
                sync_lbl = QLabel(t("gcal_settings.ics_never_synced", "미동기화"))
            sync_lbl.setStyleSheet(self._style_bundle["calendar_meta"])

        # ④ 기본 배지 / 기본 지정 버튼 (구독 탭 아닌 경우만)
        if not is_sub:
            is_default = bool(cal.get("is_default"))
            default_btn = QPushButton()
            default_btn.setObjectName("calendarDefaultButton")
            default_btn.setFixedSize(26, 26)
            default_btn.setIconSize(QSize(14, 14))
            default_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            if is_default:
                default_btn.setIcon(_ic(ICON.STAR))
                default_btn.setToolTip(t("gcal_settings.badge_default", "기본 캘린더"))
                default_btn.setStyleSheet(self._calendar_row_action_button_style("warning"))
            else:
                default_btn.setIcon(_ic(ICON.STAR_EMPTY))
                default_btn.setToolTip(t("gcal_settings.set_default", "기본으로 지정"))
                default_btn.setStyleSheet(self._calendar_row_action_button_style("neutral"))

                def _on_set_default(_=None, cid=cal_id):
                    self._set_default_calendar(cid)

                default_btn.clicked.connect(_on_set_default)

        # ⑤ 보기 토글
        vis_btn = QPushButton()
        vis_btn.setObjectName("calendarVisibilityButton")
        is_vis = bool(cal.get("is_visible", 1))
        vis_btn.setCheckable(True)
        vis_btn.setChecked(is_vis)
        vis_btn.setFixedSize(26, 26)
        vis_btn.setIconSize(QSize(14, 14))
        vis_btn.setToolTip(t("gcal_settings.col_visible_tip", "표시/숨김"))
        self._apply_vis_btn_style(vis_btn, is_vis)

        def _on_vis_toggle(checked, cid=cal_id, vb=vis_btn):
            from calendar_app.infrastructure.db.calendar_repo import set_calendar_visible
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            set_calendar_visible(cid, checked)
            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
            self._apply_vis_btn_style(vb, checked)
            if self.parent_app and hasattr(self.parent_app, "_gcal_subscription_events_cache"):
                self.parent_app._gcal_subscription_events_cache = {}
            if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
                self.parent_app.schedule_panel_refresh(center=True)

        vis_btn.toggled.connect(_on_vis_toggle)

        # ③ 우측 액션 그룹 (공간 확보를 위한 컨테이너)
        actions = QWidget()
        actions.setContentsMargins(0, 0, 0, 0)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)

        # ICS: 마지막 동기화 시간
        if cal_type == "ics":
            last_fetched = str(cal.get("ics_last_fetched") or "").strip()
            if last_fetched:
                try:
                    dt = datetime.fromisoformat(last_fetched)
                    fetch_str = dt.strftime("%m/%d %H:%M")
                except Exception:
                    fetch_str = last_fetched[:16]
                sync_lbl = QLabel(f"{fetch_str}")
                sync_lbl.setToolTip(t("gcal_settings.ics_last_synced", "마지막 동기화"))
            else:
                sync_lbl = QLabel(t("gcal_settings.ics_never_synced", "미동기화"))
            sync_lbl.setStyleSheet(self._style_bundle["calendar_meta_compact"])
            al.addWidget(sync_lbl)

        # 기본 배지 위치 조정 (아이콘으로 처리됨)
        if not is_sub:
            al.addWidget(default_btn)

        al.addWidget(vis_btn)

        # 구분선 (액션 앞)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setMaximumHeight(20)
        sep.setStyleSheet(self._calendar_action_separator_style())
        al.addWidget(sep)

        # 공통 버튼 아이콘 스타일

        # ICS 새로고침
        if cal_type == "ics" and ics_url:
            refresh_btn = QPushButton()
            refresh_btn.setObjectName("calendarRefreshButton")
            refresh_btn.setIcon(_ic(ICON.REFRESH))
            refresh_btn.setFixedSize(26, 26)
            refresh_btn.setIconSize(QSize(14, 14))
            refresh_btn.setToolTip(t("gcal_settings.ics_refresh", "지금 소식 가져오기"))
            refresh_btn.setStyleSheet(self._calendar_row_action_button_style("neutral"))

            def _on_ics_refresh(_=None, cid=cal_id, url=ics_url):
                self._refresh_ics_now(cid, url)

            refresh_btn.clicked.connect(_on_ics_refresh)
            al.addWidget(refresh_btn)

        # 편집
        edit_btn = QPushButton()
        edit_btn.setObjectName("calendarEditButton")
        edit_btn.setIcon(_ic(ICON.EDIT))
        edit_btn.setFixedSize(26, 26)
        edit_btn.setIconSize(QSize(14, 14))
        edit_btn.setToolTip(t("gcal_settings.col_edit", "편집"))
        edit_btn.setStyleSheet(self._calendar_row_action_button_style("neutral"))

        def _on_edit(_=None, cid=cal_id, cname=cal["name"], ctype=cal_type):
            self._edit_calendar(cid, cname, ctype)

        edit_btn.clicked.connect(_on_edit)
        al.addWidget(edit_btn)

        # 삭제
        del_btn = QPushButton()
        del_btn.setObjectName("calendarDeleteButton")
        del_btn.setIcon(_ic(ICON.DELETE))
        del_btn.setFixedSize(26, 26)
        del_btn.setIconSize(QSize(14, 14))
        del_btn.setToolTip(t("gcal_settings.col_delete", "삭제"))
        del_btn.setStyleSheet(self._calendar_row_action_button_style("danger"))

        def _on_del(_=None, cid=cal_id, cname=cal["name"]):
            self._delete_calendar(cid, cname)

        del_btn.clicked.connect(_on_del)
        al.addWidget(del_btn)

        h.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
        return row_frame

    def _apply_vis_btn_style(self, btn: QPushButton, is_visible: bool):
        btn.setText("")
        btn.setIcon(_ic(ICON.OPACITY) if is_visible else _ic(ICON.STATUS_CANCELED))
        btn.setStyleSheet(
            self._calendar_row_action_button_style("accent" if is_visible else "neutral")
        )

    def _pick_calendar_color(self, cal_id: str, swatch_btn: QPushButton):
        from PyQt6.QtWidgets import QColorDialog

        current = swatch_btn.property("_color") or "#4da6ff"
        color = QColorDialog.getColor(
            QColor(current), self, t("gcal_settings.color_pick_title", "캘린더 색상 선택")
        )
        if color.isValid():
            hex_c = color.name()
            try:
                from calendar_app.infrastructure.db.calendar_repo import set_calendar_color

                set_calendar_color(cal_id, hex_c)
                self._apply_swatch_color(swatch_btn, hex_c)
                from calendar_app.presentation.calendar.month_renderer import (
                    invalidate_calendar_meta_cache,
                )
                from calendar_app.presentation.panels.side_panel_renderer import (
                    invalidate_panel_calendar_cache,
                )

                invalidate_calendar_meta_cache()
                invalidate_panel_calendar_cache()
                if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
                    self.parent_app.schedule_panel_refresh(center=True)
            except Exception:
                pass

    def _set_default_calendar(self, cal_id: str):
        import logging as _logging

        _log = _logging.getLogger(__name__)
        try:
            from calendar_app.infrastructure.db.calendar_repo import (
                get_calendar,
                set_calendar_default,
            )

            _log.info("set_calendar_default called: %s", cal_id)
            ok = set_calendar_default(cal_id)
            _log.info("set_calendar_default result: %s (cal_id=%s)", ok, cal_id)
            if not ok:
                QMessageBox.warning(
                    self,
                    t("common.error", "오류"),
                    t("gcal_settings.default_set_failed", "기본 캘린더를 지정하지 못했습니다."),
                )
                return
            selected = get_calendar(cal_id) or {}
            gcal_id = str(selected.get("gcal_calendar_id") or "").strip()
            if selected.get("type") == "gcal" and gcal_id and hasattr(self, "cal_id_edit"):
                self.cal_id_edit.setText(gcal_id)
            self._refresh_calendar_table()
            self._refresh_subscription_table()
        except Exception as exc:
            _log.exception("_set_default_calendar exception for %s", cal_id)
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t(
                    "gcal_settings.default_set_error",
                    "기본 캘린더 지정 중 오류가 발생했습니다.\n{error}",
                    error=str(exc),
                ),
            )

    def _refresh_ics_now(self, cal_id: str, ics_url: str):
        from PyQt6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from calendar_app.infrastructure.ics.ics_fetcher import fetch_and_sync

            upserted, _deleted, err = fetch_and_sync(cal_id, ics_url)
        except Exception as e:
            upserted, _deleted, err = 0, 0, str(e)
        finally:
            QApplication.restoreOverrideCursor()
        if err:
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.ics_fetch_err", "ICS 일정 가져오기 실패:\n{err}").replace(
                    "{err}", str(err)
                ),
            )
        else:
            QMessageBox.information(
                self,
                t("common.success", "완료"),
                t("gcal_settings.ics_refresh_ok", "동기화 완료: {count}개 일정 업데이트").replace(
                    "{count}", str(upserted)
                ),
            )
        self._refresh_subscription_table()
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

    def _build_calendar_section(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        list_card = self._make_card(t("gcal_settings.calendar_list_title", "내 캘린더"))
        ll = list_card.layout()

        # 설명 + 버튼 행
        desc = QLabel(
            t(
                "gcal_settings.calendar_desc",
                "일정을 저장할 캘린더를 추가하고 관리합니다. 색상 원을 클릭하면 색상을 바꿀 수 있습니다.",
            )
        )
        desc.setProperty("role", "help")
        desc.setStyleSheet(self._style_bundle["help"])
        desc.setWordWrap(True)
        ll.addWidget(desc)
        ll.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        add_local_btn = QPushButton(t("gcal_settings.add_local", "로컬 추가"))
        add_local_btn.setIcon(_ic(ICON.ADD))
        load_gcal_btn = QPushButton(t("gcal_settings.load_calendars", "Google 캘린더 가져오기"))
        load_gcal_btn.setIcon(_ic(ICON.GCAL))
        refresh_cal_list_btn = QPushButton(
            t("gcal_settings.refresh_cal_list", "캘린더 목록 새로고침")
        )
        refresh_cal_list_btn.setIcon(_ic(ICON.REFRESH))
        self._apply_section_button_style(add_local_btn, "secondary")
        self._apply_section_button_style(load_gcal_btn, "accent")
        self._apply_section_button_style(refresh_cal_list_btn, "secondary")
        for b in (add_local_btn, load_gcal_btn, refresh_cal_list_btn):
            b.setMinimumWidth(80)
        btn_row.addWidget(add_local_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(refresh_cal_list_btn)
        btn_row.addWidget(load_gcal_btn)
        ll.addLayout(btn_row)
        ll.addSpacing(4)

        # 캘린더 목록 컨테이너 (스크롤 가능한 카드 리스트)
        self._cal_list_container = QWidget()
        self._cal_list_layout = QVBoxLayout(self._cal_list_container)
        self._cal_list_layout.setContentsMargins(8, 12, 16, 12)
        self._cal_list_layout.setSpacing(8)
        ll.addWidget(self._cal_list_container)

        add_local_btn.clicked.connect(self._add_local_calendar)
        load_gcal_btn.clicked.connect(self._refresh_google_calendar_list)
        refresh_cal_list_btn.clicked.connect(self._on_manual_refresh_calendar_list)

        layout.addWidget(list_card)

        # ── 숨겨진 GCal ID 필드 (기존 로직 유지) ─────────────────────────
        cal_card = self._make_card(t("gcal_settings.calendar_id_label", "GCal 쓰기 대상 캘린더 ID"))
        cl = cal_card.layout()

        self.cal_id_edit = QLineEdit()
        self._apply_input_style(self.cal_id_edit, "line")
        self.cal_id_edit.setPlaceholderText("primary")
        self.cal_id_edit.textChanged.connect(self._sync_edit_to_combo)
        cl.addWidget(self.cal_id_edit)

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        self.calendar_choice_combo = QComboBox()
        self.calendar_choice_combo.view().setAutoFillBackground(True)
        self._apply_combo_input_style(self.calendar_choice_combo)
        self.calendar_choice_combo.currentIndexChanged.connect(self._on_calendar_choice_changed)
        picker_row.addWidget(self.calendar_choice_combo, 1)
        self.load_calendars_btn = QPushButton(
            t("gcal_settings.load_calendars", "내 캘린더 불러오기")
        )
        self._apply_section_button_style(self.load_calendars_btn, "accent")
        self.load_calendars_btn.clicked.connect(self._load_accessible_calendars)
        picker_row.addWidget(self.load_calendars_btn)
        cl.addLayout(picker_row)

        self.calendar_choice_hint = self._help_label(
            t(
                "gcal_settings.calendar_choice_hint",
                "인증 완료 후 내 계정에서 사용 가능한 캘린더 목록을 불러올 수 있습니다.",
            )
        )
        cl.addWidget(self.calendar_choice_hint)

        self.go_to_auth_btn = QPushButton(t("gcal_settings.go_to_auth", "인증 설정으로 이동"))
        self._apply_section_button_style(self.go_to_auth_btn, "secondary")
        self.go_to_auth_btn.setFixedWidth(140)
        self.go_to_auth_btn.clicked.connect(lambda: self._switch_section(0))
        self.go_to_auth_btn.hide()
        cl.addWidget(self.go_to_auth_btn)

        cal_card.hide()
        layout.addWidget(cal_card)
        layout.addStretch(1)

        self._refresh_calendar_table()
        return page

    def _build_subscription_section(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        list_card = self._make_card(t("gcal_settings.subscription_list_title", "ICS 구독 캘린더"))
        ll = list_card.layout()

        # 설명
        desc = QLabel(
            t(
                "gcal_settings.subscription_desc",
                "외부 캘린더(iCal/ICS URL)를 읽기 전용으로 구독합니다. "
                "Apple Calendar, Outlook, Naver Calendar 등의 공개 URL을 사용하세요.",
            )
        )
        desc.setProperty("role", "help")
        desc.setStyleSheet(self._style_bundle["help"])
        desc.setWordWrap(True)
        ll.addWidget(desc)
        ll.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        add_ics_btn = QPushButton(t("gcal_settings.add_ics", "구독 추가"))
        add_ics_btn.setIcon(_ic(ICON.ADD))
        self._apply_section_button_style(add_ics_btn, "accent")
        refresh_all_btn = QPushButton(t("gcal_settings.refresh_all_ics", "전체 새로고침"))
        refresh_all_btn.setIcon(_ic(ICON.REFRESH))
        self._apply_section_button_style(refresh_all_btn, "secondary")
        btn_row.addWidget(add_ics_btn)
        btn_row.addWidget(refresh_all_btn)
        btn_row.addStretch(1)
        ll.addLayout(btn_row)
        ll.addSpacing(4)

        # 구독 목록 컨테이너
        self._sub_list_container = QWidget()
        self._sub_list_layout = QVBoxLayout(self._sub_list_container)
        self._sub_list_layout.setContentsMargins(2, 6, 12, 6)  # 우측 여백 추가
        self._sub_list_layout.setSpacing(8)
        ll.addWidget(self._sub_list_container)

        add_ics_btn.clicked.connect(self._add_ics_calendar)
        refresh_all_btn.clicked.connect(self._refresh_all_ics)

        layout.addWidget(list_card)
        layout.addStretch(1)
        self._refresh_subscription_table()
        return page

    # ── 캘린더 관리 테이블 헬퍼 ─────────────────────────────────────────

    def _refresh_calendar_table(self):
        self._refresh_cal_list(self._cal_list_layout, ("local", "gcal"), is_sub=False)

    def _refresh_subscription_table(self):
        self._refresh_cal_list(self._sub_list_layout, ("ics",), is_sub=True)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _refresh_cal_list(self, list_layout, type_filter, is_sub: bool):
        self._clear_layout(list_layout)
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            all_cals = list_calendars(include_inactive=True)
            calendars = [c for c in all_cals if c.get("type") in type_filter]
            gcal_enabled = str(self.settings.value("gcal_enabled", "true")).lower() == "true"
            if not gcal_enabled and "gcal" in type_filter:
                calendars = [c for c in calendars if c.get("type") != "gcal"]
        except Exception:
            calendars = []

        if not calendars:
            empty = QLabel(
                t(
                    "gcal_settings.cal_list_empty_sub",
                    "구독 중인 ICS 캘린더가 없습니다.\n위 버튼으로 ICS URL을 추가하세요.",
                )
                if is_sub
                else t("gcal_settings.cal_list_empty", "캘린더가 없습니다. 위 버튼으로 추가하세요.")
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setProperty("role", "help")
            empty.setWordWrap(True)
            empty.setStyleSheet(self._style_bundle["empty_state"])
            list_layout.addWidget(empty)
            return

        for cal in calendars:
            row_widget = self._make_calendar_row_widget(cal, is_sub=is_sub)
            list_layout.addWidget(row_widget)

    def _add_local_calendar(self):
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            t("gcal_settings.add_local_title", "로컬 캘린더 추가"),
            t("gcal_settings.cal_name_prompt", "캘린더 이름:"),
        )
        if ok and name.strip():
            from calendar_app.infrastructure.db.calendar_repo import make_local_id, upsert_calendar

            cal_id = make_local_id(name.strip())
            upsert_calendar(cal_id, "local", name.strip())
            self._refresh_calendar_table()

    def _add_ics_calendar(self):
        """ICS URL 구독 추가 — 이름 + URL을 하나의 다이얼로그에서 입력."""
        from PyQt6.QtWidgets import QApplication

        dlg = QDialog(self)
        apply_dialog_title(dlg, t("gcal_settings.add_ics_title", "ICS URL 구독 추가"))
        dlg.setObjectName("TaskEditorDialog")
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet(build_task_editor_stylesheet(self._ui_tokens, self._dialog_metrics))

        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)

        # 설명
        info_lbl = QLabel(
            t(
                "gcal_settings.add_ics_desc",
                "ICS URL을 입력하면 외부 캘린더 일정을 읽기 전용으로 가져옵니다.\n"
                "Apple Calendar · Outlook · Naver Calendar 등에서 공개 URL을 복사하세요.",
            )
        )
        info_lbl.setProperty("role", "help")
        info_lbl.setStyleSheet(self._style_bundle["help"])
        info_lbl.setWordWrap(True)
        v.addWidget(info_lbl)

        v.addWidget(self._make_divider())

        # 이름 입력
        name_lbl = QLabel(t("gcal_settings.cal_name_prompt", "캘린더 이름"))
        name_lbl.setObjectName("TaskDialogFieldLabel")
        v.addWidget(name_lbl)
        name_edit = QLineEdit()
        name_edit.setObjectName("TaskTitleEdit")
        name_edit.setPlaceholderText(
            t("gcal_settings.ics_name_placeholder", "예: 회사 일정, 공휴일 등")
        )
        v.addWidget(name_edit)

        # URL 입력
        url_lbl = QLabel(t("gcal_settings.ics_url_label", "ICS URL"))
        url_lbl.setObjectName("TaskDialogFieldLabel")
        v.addWidget(url_lbl)
        url_edit = QLineEdit()
        url_edit.setPlaceholderText(
            t("gcal_settings.ics_url_placeholder", "https://calendar.example.com/feed.ics")
        )
        v.addWidget(url_edit)

        url_hint = QLabel(
            t("gcal_settings.ics_url_hint", "http:// 또는 webcal:// 형식을 지원합니다.")
        )
        url_hint.setProperty("role", "help")
        url_hint.setStyleSheet(self._style_bundle["help"])
        v.addWidget(url_hint)

        v.addSpacing(4)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        cancel_btn = QPushButton(t("common.cancel", "취소"))
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.setMinimumWidth(80)
        add_btn = QPushButton(t("gcal_settings.ics_add_btn", "구독 추가"))
        add_btn.setObjectName("primary_btn")
        add_btn.setMinimumWidth(100)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(add_btn)
        v.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        add_btn.clicked.connect(dlg.accept)

        # Enter 키 동작
        name_edit.returnPressed.connect(url_edit.setFocus)
        url_edit.returnPressed.connect(dlg.accept)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        url = url_edit.text().strip()
        name = name_edit.text().strip()

        if not url:
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.ics_url_required", "ICS URL을 입력해 주세요."),
            )
            return
        if not name:
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.cal_name_required", "캘린더 이름을 입력해 주세요."),
            )
            return

        # webcal:// → https:// 변환
        if url.lower().startswith("webcal://"):
            url = "https://" + url[9:]

        from calendar_app.infrastructure.db.calendar_repo import make_ics_id, upsert_calendar

        cal_id = make_ics_id(url)
        upsert_calendar(cal_id, "ics", name, ics_url=url)

        # 즉시 동기화
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from calendar_app.infrastructure.ics.ics_fetcher import fetch_and_sync

            upserted, _deleted, err = fetch_and_sync(cal_id, url)
        except Exception as e:
            upserted, _deleted, err = 0, 0, str(e)
        finally:
            QApplication.restoreOverrideCursor()

        if err:
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.ics_fetch_err", "ICS 일정 가져오기 실패:\n{err}").replace(
                    "{err}", str(err)
                ),
            )
        else:
            QMessageBox.information(
                self,
                t("common.success", "구독 완료"),
                t("gcal_settings.ics_fetch_ok", "'{name}' 구독 완료!\n가져온 일정: {count}개")
                .replace("{name}", name)
                .replace("{count}", str(upserted)),
            )

        self._refresh_subscription_table()
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

    def _refresh_all_ics(self):
        """구독 중인 모든 ICS를 일괄 새로고침."""
        from PyQt6.QtWidgets import QApplication

        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            ics_cals = [c for c in list_calendars(include_inactive=True) if c.get("type") == "ics"]
        except Exception:
            ics_cals = []

        if not ics_cals:
            QMessageBox.information(
                self,
                t("gcal_settings.refresh_all_ics", "전체 새로고침"),
                t("gcal_settings.ics_no_subscriptions", "구독 중인 ICS 캘린더가 없습니다."),
            )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        total_upserted = 0
        errors = []
        try:
            from calendar_app.infrastructure.ics.ics_fetcher import fetch_and_sync

            for cal in ics_cals:
                url = str(cal.get("ics_url") or "").strip()
                if not url:
                    continue
                try:
                    upserted, deleted, err = fetch_and_sync(cal["id"], url)
                    if err:
                        errors.append(f"{cal['name']}: {err}")
                    else:
                        total_upserted += upserted
                except Exception as e:
                    errors.append(f"{cal['name']}: {e}")
        finally:
            QApplication.restoreOverrideCursor()

        self._refresh_subscription_table()
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

        if errors:
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.ics_refresh_partial", "일부 구독 새로고침 실패:\n")
                + "\n".join(errors),
            )
        else:
            QMessageBox.information(
                self,
                t("common.success", "완료"),
                t(
                    "gcal_settings.ics_refresh_all_ok", "전체 {count}개 캘린더 새로고침 완료!"
                ).replace("{count}", str(len(ics_cals))),
            )

    def _edit_calendar(self, cal_id: str, name: str, _cal_type: str):
        """이름 + 색상을 하나의 다이얼로그에서 편집."""
        try:
            from calendar_app.infrastructure.db.calendar_repo import get_calendar

            cal_data = get_calendar(cal_id) or {}
        except Exception:
            cal_data = {}

        is_gcal = _cal_type == "gcal"

        dlg = QDialog(self)
        apply_dialog_title(dlg, t("gcal_settings.edit_calendar_title", "캘린더 편집"))
        dlg.setObjectName("TaskEditorDialog")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(build_task_editor_stylesheet(self._ui_tokens, self._dialog_metrics))

        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)

        # BUG A: gcal 캘린더는 Google에서 이름이 관리됨 → 이름 필드 비활성화 + 안내 표시
        if is_gcal:
            gcal_notice = QLabel(
                t(
                    "gcal_settings.edit_gcal_name_notice",
                    "Google Calendar 이름은 Google에서 관리됩니다.\n"
                    "이름은 표시 전용이며 다음 동기화 시 Google 이름으로 갱신됩니다.",
                )
            )
            gcal_notice.setWordWrap(True)
            gcal_notice.setStyleSheet(self._style_bundle["notice_warning"])
            v.addWidget(gcal_notice)
            v.addWidget(self._make_divider())

        name_lbl = QLabel(t("gcal_settings.cal_name_prompt", "캘린더 이름"))
        name_lbl.setObjectName("TaskDialogFieldLabel")
        v.addWidget(name_lbl)
        name_edit = QLineEdit(name)
        name_edit.setObjectName("TaskTitleEdit")
        if is_gcal:
            name_edit.setEnabled(False)
            name_edit.setToolTip(
                t(
                    "gcal_settings.edit_gcal_name_tooltip",
                    "Google Calendar 이름은 Google에서만 변경할 수 있습니다.",
                )
            )
        v.addWidget(name_edit)

        color_lbl = QLabel(t("gcal_settings.cal_color_prompt", "색상"))
        color_lbl.setObjectName("TaskDialogFieldLabel")
        v.addWidget(color_lbl)

        color_row = QHBoxLayout()
        color_row.setSpacing(10)
        current_color = str(cal_data.get("color") or "#4da6ff").strip()
        swatch_btn = self._make_color_swatch(current_color, size=28)
        swatch_btn.setToolTip(t("gcal_settings.color_pick_title", "클릭해서 색상 선택"))

        color_hex_edit = QLineEdit(current_color)
        color_hex_edit.setPlaceholderText("#4da6ff")
        color_hex_edit.setMaximumWidth(110)

        def _pick_color_inline():
            from PyQt6.QtWidgets import QColorDialog

            c = QColorDialog.getColor(QColor(color_hex_edit.text().strip() or current_color), dlg)
            if c.isValid():
                color_hex_edit.setText(c.name())
                self._apply_swatch_color(swatch_btn, c.name())

        def _on_hex_changed(text):
            c = QColor(text.strip())
            if c.isValid():
                self._apply_swatch_color(swatch_btn, c.name())

        swatch_btn.clicked.connect(_pick_color_inline)
        color_hex_edit.textChanged.connect(_on_hex_changed)
        color_row.addWidget(swatch_btn)
        color_row.addWidget(color_hex_edit)
        color_row.addStretch(1)
        v.addLayout(color_row)

        v.addSpacing(8)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton(t("common.cancel", "취소"))
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.setMinimumWidth(80)
        save_btn = QPushButton(t("common.save", "저장"))
        save_btn.setObjectName("primary_btn")
        save_btn.setMinimumWidth(80)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        v.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        save_btn.clicked.connect(dlg.accept)
        name_edit.returnPressed.connect(dlg.accept)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = name_edit.text().strip()
        new_color = color_hex_edit.text().strip()
        if not new_name:
            return

        from calendar_app.infrastructure.db.calendar_repo import rename_calendar, set_calendar_color

        # gcal 캘린더는 이름이 비활성화되어 있으므로 건너뜀 (Google에서 관리)
        if not is_gcal:
            rename_calendar(cal_id, new_name)
        if new_color and QColor(new_color).isValid():
            set_calendar_color(cal_id, new_color)

        try:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
        except Exception:
            pass
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

        self._refresh_calendar_table()
        self._refresh_subscription_table()

    def _delete_calendar(self, cal_id: str, name: str):
        reply = QMessageBox.question(
            self,
            t("gcal_settings.col_delete", "삭제"),
            t(
                "gcal_settings.delete_confirm",
                "'{name}' 캘린더를 삭제하시겠습니까?\n해당 캘린더의 태스크는 미분류 상태가 됩니다.",
            ).format(name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from calendar_app.infrastructure.db.calendar_repo import delete_calendar

            delete_calendar(cal_id)
            self._refresh_calendar_table()
            self._refresh_subscription_table()
            # BUG C: 삭제 후 월간 뷰 + 사이드 패널 캐시 무효화 및 새로고침
            try:
                from calendar_app.presentation.calendar.month_renderer import (
                    invalidate_calendar_meta_cache,
                )
                from calendar_app.presentation.panels.side_panel_renderer import (
                    invalidate_panel_calendar_cache,
                )

                invalidate_calendar_meta_cache()
                invalidate_panel_calendar_cache()
            except Exception:
                pass
            if self.parent_app and hasattr(self.parent_app, "_gcal_subscription_events_cache"):
                self.parent_app._gcal_subscription_events_cache = {}
            if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
                self.parent_app.schedule_panel_refresh(center=True)

    # ──────────────────────────────────────────────
    # 섹션 2: 동기화
    # ──────────────────────────────────────────────

    def _build_sync_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.advanced_title", "동기화 동작"))
        cl = card.layout()

        cl.addWidget(
            self._help_label(
                t("gcal_settings.advanced_summary", "대부분의 경우 기본값으로도 충분합니다.")
            )
        )
        cl.addWidget(self._make_divider())

        cl.addWidget(self._field_label(t("gcal_settings.sync_interval_label", "정기 동기화 간격")))
        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        self.interval_spin = QSpinBox()
        self._apply_input_style(self.interval_spin, "spin")
        self.interval_spin.setRange(1, 240)
        self.interval_spin.setSuffix(t("gcal_settings.minutes_suffix", " 분"))
        self.interval_spin.setFixedWidth(110)
        interval_row.addWidget(self.interval_spin)
        interval_row.addWidget(
            self._help_label(t("gcal_settings.sync_interval_hint", "1 ~ 240분 사이로 설정하세요.")),
            1,
        )
        cl.addLayout(interval_row)

        cl.addSpacing(10)

        cl.addWidget(
            self._field_label(t("gcal_settings.quick_interval_label", "편집 후 빠른 동기화"))
        )
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        self.quick_interval_spin = QSpinBox()
        self._apply_input_style(self.quick_interval_spin, "spin")
        self.quick_interval_spin.setRange(5, 300)
        self.quick_interval_spin.setSuffix(t("gcal_settings.seconds_suffix", " 초"))
        self.quick_interval_spin.setFixedWidth(110)
        quick_row.addWidget(self.quick_interval_spin)
        quick_row.addWidget(
            self._help_label(
                t("gcal_settings.quick_interval_hint", "5 ~ 300초 사이로 설정하세요.")
            ),
            1,
        )
        cl.addLayout(quick_row)

        cl.addWidget(self._make_divider())

        # [10] Hide completed events in GCal
        self.hide_completed_check = QCheckBox(
            t("gcal_settings.hide_completed", "완료된 일정 구글 캘린더에서 숨기기")
        )
        self.hide_completed_check.setStyleSheet(self._style_bundle["check_toggle"])
        self.hide_completed_check.setChecked(
            self.settings.value("gcal_hide_completed_in_gcal", "false") == "true"
        )
        cl.addWidget(self.hide_completed_check)
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.hide_completed_help",
                    "일정을 완료로 표시하면 구글 캘린더에서 자동으로 숨깁니다.",
                )
            )
        )

        cl.addWidget(self._make_divider())
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.advanced_help",
                    "편집이 잦을 때는 빠른 동기화를, 백그라운드 부하를 줄이려면 정기 동기화 간격을 늘리세요.",
                )
            )
        )

        layout.addWidget(card)

        # ── 시간대 카드 ───────────────────────────────────────────────
        tz_card = self._make_card(t("gcal_settings.timezone_label", "시간대"))
        tl = tz_card.layout()

        tz_row = QHBoxLayout()
        tz_row.setSpacing(8)
        self.timezone_combo = QComboBox()
        self.timezone_combo.setEditable(True)
        self.timezone_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.timezone_combo.setMaxVisibleItems(20)
        self.timezone_combo.view().setAutoFillBackground(True)
        self.timezone_combo.currentTextChanged.connect(self._refresh_timezone_preview)

        completer = QCompleter(self._all_timezones, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.timezone_combo.setCompleter(completer)
        if self.timezone_combo.lineEdit():
            self.timezone_combo.lineEdit().setPlaceholderText(
                t("gcal_settings.timezone_search_placeholder", "도시명 검색 (예: Seoul)...")
            )
        self._apply_combo_input_style(self.timezone_combo)

        detect_btn = QPushButton(t("gcal_settings.detect_timezone", "현재 시간대 사용"))
        self._apply_section_button_style(detect_btn, "secondary")
        detect_btn.setFixedWidth(130)
        detect_btn.clicked.connect(self._apply_system_timezone)
        tz_row.addWidget(self.timezone_combo, 1)
        tz_row.addWidget(detect_btn)
        tl.addLayout(tz_row)

        self.timezone_preview = QLabel()
        self.timezone_preview.setProperty("role", "help")
        self.timezone_preview.setStyleSheet(self._style_bundle["help"])
        self.timezone_preview.setWordWrap(True)
        tl.addWidget(self.timezone_preview)

        layout.addWidget(tz_card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 섹션 3: 진단
    # ──────────────────────────────────────────────

    def _build_diagnostics_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.diagnostics_title", "Sync Diagnostics"))
        cl = card.layout()

        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.diagnostics_summary",
                    "Check current sync health, pending issues, and repair the local sync cache when needed.",
                )
            )
        )
        cl.addWidget(self._make_divider())

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(8)
        meta_grid.setVerticalSpacing(8)
        self.issue_meta = self._make_meta_box(t("gcal_settings.meta_issues", "Open issues"))
        self.delete_queue_meta = self._make_meta_box(
            t("gcal_settings.meta_delete_queue", "Delete queue")
        )
        self.bound_calendar_meta = self._make_meta_box(
            t("gcal_settings.meta_bound_calendar", "Bound calendar")
        )
        self.last_error_meta = self._make_meta_box(t("gcal_settings.meta_last_error", "Last error"))
        meta_grid.addWidget(self.issue_meta[0], 0, 0)
        meta_grid.addWidget(self.delete_queue_meta[0], 0, 1)
        meta_grid.addWidget(self.bound_calendar_meta[0], 1, 0)
        meta_grid.addWidget(self.last_error_meta[0], 1, 1)
        cl.addLayout(meta_grid)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.open_issues_btn = QPushButton(t("gcal_settings.open_issues", "Open Issues"))
        self._apply_section_button_style(self.open_issues_btn, "accent")
        self.open_issues_btn.clicked.connect(self._open_sync_issues)
        action_row.addWidget(self.open_issues_btn)
        self.reset_sync_state_btn = QPushButton(
            t("gcal_settings.reset_sync_state", "Reset Sync Cache")
        )
        self._apply_section_button_style(self.reset_sync_state_btn, "danger")
        self.reset_sync_state_btn.clicked.connect(self._reset_sync_state)
        action_row.addWidget(self.reset_sync_state_btn)
        action_row.addStretch(1)
        cl.addLayout(action_row)

        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.reset_sync_state_help",
                    "Resetting the sync cache clears stored sync tokens for the current binding and forces a safe full rescan on the next sync.",
                )
            )
        )

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 섹션 4: 가이드
    # ──────────────────────────────────────────────

    def _build_guide_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.setup_title", "초기 설정 가이드"))
        cl = card.layout()
        cl.addWidget(self._section_eyebrow(t("gcal_settings.setup_eyebrow", "QUICK START")))

        summary = QLabel(
            t(
                "gcal_settings.setup_summary",
                "Google Cloud OAuth 데스크탑 인증 정보를 사용합니다. "
                "공식 문서를 참고하면 최신 정보를 안전하게 따라할 수 있습니다.",
            )
        )
        summary.setWordWrap(True)
        summary.setProperty("role", "help")
        summary.setStyleSheet(self._style_bundle["help"])
        cl.addWidget(summary)
        cl.addSpacing(4)

        tip_items = [
            (
                t("gcal_settings.tip_project_title", "프로젝트"),
                t(
                    "gcal_settings.tip_project_body",
                    "Google Cloud 프로젝트를 생성하거나 기존 프로젝트를 재사용하세요.",
                ),
            ),
            (
                t("gcal_settings.tip_api_title", "API 활성화"),
                t(
                    "gcal_settings.tip_api_body",
                    "인증 정보를 만들기 전에 Google Calendar API를 활성화하세요.",
                ),
            ),
            (
                t("gcal_settings.tip_oauth_title", "OAuth 설정"),
                t(
                    "gcal_settings.tip_oauth_body",
                    "데스크탑 앱 OAuth 클라이언트 ID를 생성하세요. 웹 인증 정보는 동작하지 않습니다.",
                ),
            ),
            (
                t("gcal_settings.tip_json_title", "JSON 파일"),
                t(
                    "gcal_settings.tip_json_body",
                    "인증 JSON을 다운로드하여 [연결] 섹션에서 등록하세요.",
                ),
            ),
        ]
        for idx, (title, body) in enumerate(tip_items, 1):
            cl.addWidget(self._make_step_row(idx, title, body))

        cl.addSpacing(4)
        links = QHBoxLayout()
        links.setSpacing(8)
        doc_btn = QPushButton(t("gcal_settings.open_docs", "공식 문서"))
        doc_btn.setIcon(_ic(ICON.DOCS))
        self._apply_section_button_style(doc_btn, "secondary")
        doc_btn.clicked.connect(
            lambda: webbrowser.open("https://developers.google.com/calendar/api/quickstart/python")
        )
        console_btn = QPushButton(t("gcal_settings.open_console", "Cloud Console"))
        console_btn.setIcon(_ic(ICON.CLOUD))
        self._apply_section_button_style(console_btn, "secondary")
        console_btn.clicked.connect(lambda: webbrowser.open("https://console.cloud.google.com/"))
        oauth_btn = QPushButton(t("gcal_settings.open_oauth_docs", "OAuth 가이드"))
        oauth_btn.setIcon(_ic(ICON.OAUTH_GUIDE))
        self._apply_section_button_style(oauth_btn, "secondary")
        oauth_btn.clicked.connect(
            lambda: webbrowser.open("https://developers.google.com/identity/protocols/oauth2")
        )
        links.addWidget(doc_btn)
        links.addWidget(console_btn)
        links.addWidget(oauth_btn)
        links.addStretch(1)
        cl.addLayout(links)

        quick_note = QLabel(
            t(
                "gcal_settings.setup_note",
                "캘린더를 여러 개 관리하는 경우, 인증은 한 번만 하고 캘린더 ID를 변경하면 됩니다.",
            )
        )
        quick_note.setProperty("role", "help")
        quick_note.setStyleSheet(self._style_bundle["help"])
        quick_note.setWordWrap(True)
        cl.addWidget(quick_note)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 푸터
    # ──────────────────────────────────────────────

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setStyleSheet(self._style_bundle["footer"])
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(6)

        reset_btn = QPushButton(t("gcal_settings.reset", "연결 초기화"))
        self._apply_section_button_style(reset_btn, "danger")
        reset_btn.clicked.connect(self.reset_auth)
        layout.addWidget(reset_btn)
        layout.addStretch(1)

        auth_btn = QPushButton(t("gcal_settings.authenticate", "인증하기"))
        auth_btn.setIcon(_ic(ICON.AUTH))
        self._apply_section_button_style(auth_btn, "accent")
        auth_btn.setMinimumWidth(100)
        auth_btn.clicked.connect(self.run_auth)

        save_btn = QPushButton(t("gcal_settings.save", "설정 저장"))
        self._apply_section_button_style(save_btn, "success")
        # save_btn.setFixedHeight(28) # Removed for standardization
        save_btn.setMinimumWidth(80)
        save_btn.clicked.connect(self.save_settings)

        close_btn = QPushButton(t("common.close", "닫기"))
        self._apply_section_button_style(close_btn, "secondary")
        close_btn.setMinimumWidth(64)
        close_btn.clicked.connect(self.reject)

        layout.addWidget(auth_btn)
        layout.addWidget(save_btn)
        layout.addWidget(close_btn)
        return footer

    # ──────────────────────────────────────────────
    # 헬퍼 위젯
    # ──────────────────────────────────────────────

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(self._style_bundle["card"])
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setProperty("role", "sectionTitle")
        label.setStyleSheet(self._style_bundle["card_title"])
        layout.addWidget(label)
        return card

    def _make_divider(self) -> QFrame:
        d = QFrame()
        d.setObjectName("divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(self._style_bundle["divider"])
        return d

    def _make_info_box(self, title: str, body: str) -> QFrame:
        box = QFrame()
        box.setObjectName("subtleCard")
        box.setStyleSheet(self._style_bundle["subtle_card"])
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "tipTitle")
        title_lbl.setStyleSheet(self._style_bundle["tip_title"])
        body_lbl = QLabel(body)
        body_lbl.setProperty("role", "tipBody")
        body_lbl.setStyleSheet(self._style_bundle["tip_body"])
        body_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        layout.addWidget(body_lbl)
        return box

    def _make_meta_box(self, title: str):
        box = QFrame()
        box.setObjectName("subtleCard")
        box.setStyleSheet(self._style_bundle["meta_box"])
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "metaLabel")
        title_lbl.setStyleSheet(self._style_bundle["meta_label"])
        value_lbl = QLabel("-")
        value_lbl.setProperty("role", "metaValue")
        value_lbl.setStyleSheet(self._style_bundle["meta_value"])
        value_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        return box, value_lbl

    def _section_eyebrow(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "sectionEyebrow")
        label.setStyleSheet(self._style_bundle["eyebrow"])
        return label

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "fieldLabel")
        lbl.setStyleSheet(self._style_bundle["field_label"])
        return lbl

    def _help_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "help")
        lbl.setStyleSheet(self._style_bundle["help"])
        lbl.setWordWrap(True)
        return lbl

    def _apply_section_button_style(
        self, button: QPushButton, tone: str = "secondary"
    ) -> QPushButton:
        button.setStyleSheet(
            self._style_bundle.get(f"button_{tone}", self._style_bundle["button_secondary"])
        )
        return button

    def _apply_input_style(self, widget: QWidget, kind: str) -> QWidget:
        widget.setStyleSheet(self._style_bundle.get(f"input_{kind}", ""))
        return widget

    def _apply_combo_input_style(self, combo: QComboBox) -> QComboBox:
        combo.setStyleSheet(self._style_bundle.get("input_combo", ""))
        if combo.view() is not None:
            combo.view().setStyleSheet(self._style_bundle.get("input_popup", ""))
        if combo.lineEdit() is not None:
            combo.lineEdit().setStyleSheet(self._style_bundle.get("input_line", ""))
        completer = combo.completer()
        if completer is not None and completer.popup() is not None:
            completer.popup().setStyleSheet(self._style_bundle.get("input_popup", ""))
        return combo

    def _set_feedback_label(self, label: QLabel, text: str, tone: str = "help") -> QLabel:
        label.setText(text)
        label.setStyleSheet(
            self._style_bundle.get(f"feedback_{tone}", self._style_bundle["help"])
            if tone != "help"
            else self._style_bundle["help"]
        )
        return label

    def _make_step_row(self, number: int, title: str, body: str) -> QFrame:
        row = QFrame()
        row.setObjectName("subtleCard")
        row.setStyleSheet(self._style_bundle["guide_row"])
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        badge = QLabel(f"{number}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 28)
        badge.setStyleSheet(self._style_bundle["step_badge"])
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "tipTitle")
        title_lbl.setStyleSheet(self._style_bundle["tip_title"])
        body_lbl = QLabel(body)
        body_lbl.setProperty("role", "tipBody")
        body_lbl.setStyleSheet(self._style_bundle["tip_body"])
        body_lbl.setWordWrap(True)
        text_col.addWidget(title_lbl)
        text_col.addWidget(body_lbl)
        layout.addLayout(text_col, 1)
        return row

    def _build_timezone_list(self) -> list[str]:
        all_zones = sorted(available_timezones())
        ordered = []
        for tz_name in _COMMON_TIMEZONES + all_zones:
            if tz_name not in ordered:
                ordered.append(tz_name)
        return ordered

    # ──────────────────────────────────────────────
    # 상태 / 데이터
    # ──────────────────────────────────────────────

    def _load_state(self):
        self.enable_cb.setChecked(self.settings.value("gcal_enabled", "true") == "true")
        self.creds_path_edit.setText(CREDENTIALS_PATH if os.path.exists(CREDENTIALS_PATH) else "")
        self.cal_id_edit.setText(
            str(self.settings.value("gcal_calendar_id", "primary") or "primary")
        )
        self.interval_spin.setValue(int(self.settings.value("gcal_sync_interval", "10") or 10))
        self.quick_interval_spin.setValue(
            max(5, int(self.settings.value("gcal_quick_sync_interval", "30") or 30))
        )
        self._set_calendar_choices([])
        self._populate_timezones(
            str(self.settings.value("gcal_timezone", "Asia/Seoul") or "Asia/Seoul")
        )

    def _populate_timezones(self, current_tz: str):
        self.timezone_combo.clear()
        self.timezone_combo.addItems(self._all_timezones)
        idx = self.timezone_combo.findText(current_tz, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.timezone_combo.setCurrentIndex(idx)
        else:
            self.timezone_combo.setEditText(current_tz)
        self._refresh_timezone_preview()

    def _current_timezone(self) -> str:
        return self.timezone_combo.currentText().strip() or "UTC"

    def _refresh_timezone_preview(self):
        tz_name = self._current_timezone()
        try:
            offset = timezone_offset_for_name(tz_name, when=datetime.now())
            preview = t(
                "gcal_settings.timezone_preview",
                "현재 오프셋: {offset}  ·  {tz}",
                offset=offset,
                tz=tz_name,
            )
            self._set_feedback_label(self.timezone_preview, preview, "help")
        except Exception:
            self._set_feedback_label(
                self.timezone_preview,
                t("gcal_settings.timezone_invalid", "선택한 시간대를 해석할 수 없습니다."),
                "error",
            )

    def _system_timezone(self) -> str:
        try:
            # QTimeZone is much more reliable on Windows than standard datetime.astimezone()
            tz_id = QTimeZone.systemTimeZoneId().data().decode("utf-8", errors="replace")
            if tz_id:
                return tz_id
        except Exception:
            pass

        local_tz = datetime.now().astimezone().tzinfo
        key = getattr(local_tz, "key", None)
        return key or "UTC"

    def _apply_system_timezone(self):
        tz_name = self._system_timezone()
        idx = self.timezone_combo.findText(tz_name, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.timezone_combo.setCurrentIndex(idx)
        else:
            self.timezone_combo.setEditText(tz_name)
        self._refresh_timezone_preview()

    def _refresh_parent_state(self):
        if hasattr(self.parent_app, "update_gcal_sync_timer"):
            self.parent_app.update_gcal_sync_timer()
        if hasattr(self.parent_app, "update_sync_status"):
            self.parent_app.update_sync_status()
        if hasattr(self.parent_app, "load_center_panel"):
            self.parent_app.load_center_panel()

    def _set_calendar_choices(self, calendars: list[dict]):
        self._calendar_choices = calendars or []
        self.calendar_choice_combo.blockSignals(True)
        self.calendar_choice_combo.clear()
        self.calendar_choice_combo.addItem(
            t("gcal_settings.calendar_choice_placeholder", "Choose from accessible calendars"),
            "",
        )
        for item in self._calendar_choices:
            label = item.get("summary") or item.get("id") or "?"
            if item.get("primary"):
                label = f"{label} ({t('gcal_settings.calendar_primary', 'Primary')})"
            self.calendar_choice_combo.addItem(label, item.get("id") or "")
        self.calendar_choice_combo.blockSignals(False)

        current_id = self.cal_id_edit.text().strip() or "primary"
        idx = self.calendar_choice_combo.findData(current_id)
        if idx >= 0:
            self.calendar_choice_combo.setCurrentIndex(idx)
        elif current_id and current_id != "primary":
            # Show the currently saved ID even if the full searchable list hasn't been loaded yet.
            label = current_id if len(current_id) < 30 else current_id[:27] + "..."
            self.calendar_choice_combo.addItem(
                f"({t('gcal_settings.meta_calendar', 'Calendar')}) {label}", current_id
            )
            self.calendar_choice_combo.setCurrentIndex(self.calendar_choice_combo.count() - 1)
        else:
            self.calendar_choice_combo.setCurrentIndex(0)

    def _resolve_calendar_display_meta(self, calendar_id: str) -> tuple[str, str]:
        calendar_id = (calendar_id or "").strip()
        if not calendar_id:
            return "-", ""

        sync = getattr(self.parent_app, "gcal_sync", None)
        calendars = list(self._calendar_choices or [])
        if not calendars and sync and hasattr(sync, "list_accessible_calendars"):
            try:
                calendars = sync.list_accessible_calendars() or []
            except Exception:
                calendars = []

        matched = None
        if calendar_id == "primary":
            matched = next((item for item in calendars if item.get("primary")), None)
        if matched is None:
            matched = next(
                (item for item in calendars if (item.get("id") or "") == calendar_id), None
            )

        if matched is None:
            if calendar_id == "primary":
                return "-", ""
            return calendar_id, ""

        label = (matched.get("summary") or matched.get("id") or "-").strip() or "-"
        tooltip = (matched.get("id") or "").strip()
        return label, tooltip if tooltip != label else tooltip

    def _refresh_google_calendar_list(
        self, _=None, *, notify: bool = True, show_empty_message: bool = True
    ):
        """Refresh accessible Google calendars into the local list and update the dialog immediately."""
        from PyQt6.QtWidgets import QApplication

        sync = getattr(self.parent_app, "gcal_sync", None)
        if (
            not sync
            or not getattr(sync, "is_authenticated", False)
            or getattr(sync, "service", None) is None
        ):
            if notify:
                QMessageBox.warning(
                    self,
                    t("common.error", "오류"),
                    t(
                        "gcal_settings.load_calendars_auth_needed",
                        "인증을 먼저 진행한 뒤 캘린더 목록을 불러와 주세요.",
                    ),
                )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            calendars = sync.list_accessible_calendars()
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            if notify:
                QMessageBox.warning(self, t("common.error", "오류"), str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._set_calendar_choices(calendars)

        if not calendars:
            self._refresh_calendar_table()
            self._refresh_meta()
            if notify and show_empty_message:
                QMessageBox.information(
                    self,
                    t("gcal_settings.load_calendars", "Google 캘린더 불러오기"),
                    t("gcal_settings.load_calendars_empty", "접근 가능한 캘린더가 없습니다."),
                )
            return

        from calendar_app.infrastructure.db.calendar_repo import (
            list_calendars,
            make_gcal_id,
            upsert_calendar,
        )

        existing = {c["id"]: c for c in list_calendars(include_inactive=True)}
        imported = 0
        already_has_default = any(c.get("is_default") for c in existing.values())
        default_assigned_this_run = False

        for item in calendars:
            gcal_id = str(item.get("id") or "").strip()
            if not gcal_id or gcal_id == "primary":
                continue

            cal_db_id = make_gcal_id(gcal_id)
            name = item.get("summary") or gcal_id
            access = item.get("accessRole", "reader")
            is_active = access in ("owner", "writer")
            existing_color = existing.get(cal_db_id, {}).get("color")
            raw_color = str(item.get("backgroundColor") or "").strip()
            color = (
                existing_color
                or (raw_color if raw_color.startswith("#") else None)
                or DEFAULT_CALENDAR_COLOR
            )
            is_primary = bool(item.get("primary"))
            is_default = is_primary and not already_has_default and not default_assigned_this_run
            if is_default:
                default_assigned_this_run = True

            upsert_calendar(
                calendar_id=cal_db_id,
                name=name,
                cal_type="gcal",
                color=color,
                is_default=is_default,
                is_active=is_active,
                is_visible=True,
                gcal_calendar_id=gcal_id,
                access_role=access or None,
            )
            imported += 1

        for item in calendars:
            gcal_id = str(item.get("id") or "").strip()
            if gcal_id:
                self.settings.setValue(f"gcal_sync_token::{gcal_id}", "")
                self.settings.setValue(f"gcal_sync_token_fails::{gcal_id}", 0)

        self._refresh_calendar_table()
        self._refresh_meta()
        try:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
        except Exception:
            pass
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)
        if self.parent_app and hasattr(self.parent_app, "sync_google_calendar_silent"):
            self.parent_app.sync_google_calendar_silent()
        if notify:
            QMessageBox.information(
                self,
                t("gcal_settings.load_calendars", "Google 캘린더 불러오기"),
                t("gcal_settings.import_done", "{count}개 캘린더를 가져왔습니다.", count=imported),
            )

    def _import_gcal_calendars(
        self, _=None, *, notify: bool = True, show_empty_message: bool = True
    ):
        return self._refresh_google_calendar_list(
            _,
            notify=notify,
            show_empty_message=show_empty_message,
        )
        """Google 계정의 캘린더 목록을 가져와 calendar 테이블에 등록/갱신합니다."""
        from PyQt6.QtWidgets import QApplication

        sync = getattr(self.parent_app, "gcal_sync", None)
        if (
            not sync
            or not getattr(sync, "is_authenticated", False)
            or getattr(sync, "service", None) is None
        ):
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t(
                    "gcal_settings.load_calendars_auth_needed",
                    "인증을 먼저 진행한 후 캘린더 목록을 불러오세요.",
                ),
            )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            calendars = sync.list_accessible_calendars()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, t("common.error", "오류"), str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not calendars:
            QMessageBox.information(
                self,
                t("gcal_settings.load_calendars", "Google 캘린더 가져오기"),
                t("gcal_settings.load_calendars_empty", "접근 가능한 캘린더가 없습니다."),
            )
            return

        from calendar_app.infrastructure.db.calendar_repo import (
            list_calendars,
            make_gcal_id,
            upsert_calendar,
        )

        existing = {c["id"]: c for c in list_calendars(include_inactive=True)}
        imported = 0
        new_gcal_ids = []  # 새로 추가된 캘린더의 gcal_calendar_id
        # BUG B: is_default 중복 방지 — 루프 시작 전 1회만 확인 + 루프 내 플래그로 최대 1개만 허용
        already_has_default = any(c.get("is_default") for c in existing.values())
        default_assigned_this_run = False
        for item in calendars:
            gcal_id = item.get("id", "").strip()
            if not gcal_id:
                continue
            # "primary" 는 Google API 별칭이지 실제 캘린더 ID가 아니다. 무시한다.
            if gcal_id == "primary":
                continue
            cal_db_id = make_gcal_id(gcal_id)
            name = item.get("summary") or gcal_id
            # accessRole: owner/writer=쓰기 가능, reader=읽기 전용
            access = item.get("accessRole", "reader")
            is_active = access in ("owner", "writer")
            # 기존 캘린더 색상 유지, 신규는 Google 색상 사용
            existing_color = existing.get(cal_db_id, {}).get("color")
            raw_color = item.get("backgroundColor") or ""
            color = (
                existing_color
                or (raw_color if raw_color.startswith("#") else None)
                or DEFAULT_CALENDAR_COLOR
            )
            # primary 캘린더이고, 아직 기본 지정이 없고, 이번 루프에서 아직 할당 안 됐을 때만 is_default=True
            is_primary = bool(item.get("primary"))
            is_default = is_primary and not already_has_default and not default_assigned_this_run
            if is_default:
                default_assigned_this_run = True
            is_new = cal_db_id not in existing
            upsert_calendar(
                calendar_id=cal_db_id,
                name=name,
                cal_type="gcal",
                color=color,
                is_default=is_default,
                is_active=is_active,
                is_visible=True,
                gcal_calendar_id=gcal_id,
                access_role=access or None,
            )
            imported += 1
            if is_new:
                new_gcal_ids.append(gcal_id)

        # 모든 gcal 캘린더 token 리셋 → 다음 sync에서 전체 full rescan
        for item in calendars:
            gcal_id = item.get("id", "").strip()
            if gcal_id:
                self.settings.setValue(f"gcal_sync_token::{gcal_id}", "")
                self.settings.setValue(f"gcal_sync_token_fails::{gcal_id}", 0)

        self._refresh_calendar_table()
        from calendar_app.presentation.calendar.month_renderer import invalidate_calendar_meta_cache
        from calendar_app.presentation.panels.side_panel_renderer import (
            invalidate_panel_calendar_cache,
        )

        invalidate_calendar_meta_cache()
        invalidate_panel_calendar_cache()
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)
        # 즉시 GCal sync 트리거 (전체 full rescan)
        if self.parent_app and hasattr(self.parent_app, "sync_google_calendar_silent"):
            self.parent_app.sync_google_calendar_silent()
        QMessageBox.information(
            self,
            t("gcal_settings.load_calendars", "Google 캘린더 가져오기"),
            t("gcal_settings.import_done", "{count}개 캘린더를 가져왔습니다.", count=imported),
        )

    def _on_manual_refresh_calendar_list(self):
        """[11] Manual calendar list refresh with 10-second cooldown."""
        import time as _time

        sync = getattr(self.parent_app, "gcal_sync", None)
        if not sync or not getattr(sync, "is_authenticated", False):
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.not_authenticated", "구글 인증 후 사용 가능합니다."),
            )
            return
        _cooldown_key = "gcal_cal_list_manual_refresh_at"
        _last = float(self.settings.value(_cooldown_key, 0) or 0)
        _elapsed = _time.monotonic() - _last
        _cooldown_secs = 10
        if _elapsed < _cooldown_secs:
            remaining = int(_cooldown_secs - _elapsed) + 1
            QMessageBox.information(
                self,
                t("gcal_settings.refresh_cal_list", "캘린더 목록 새로고침"),
                t(
                    "gcal_settings.refresh_cooldown",
                    "잠시 후 다시 시도하세요. ({sec}초 남음)",
                    sec=remaining,
                ),
            )
            return
        self.settings.setValue(_cooldown_key, _time.monotonic())
        self._refresh_google_calendar_list()

    def _load_accessible_calendars(self):
        self.go_to_auth_btn.hide()
        sync = getattr(self.parent_app, "gcal_sync", None)
        if (
            not sync
            or not getattr(sync, "is_authenticated", False)
            or getattr(sync, "service", None) is None
        ):
            self._set_feedback_label(
                self.calendar_choice_hint,
                t(
                    "gcal_settings.load_calendars_auth_needed",
                    "인증을 먼저 진행한 후 캘린더 목록을 불러오세요.",
                ),
                "error",
            )
            self.go_to_auth_btn.show()
            return

        calendars = sync.list_accessible_calendars()
        self._set_calendar_choices(calendars)
        if calendars:
            self._set_feedback_label(
                self.calendar_choice_hint,
                t(
                    "gcal_settings.load_calendars_ok",
                    "Loaded {count} calendars. Choosing one will fill its Calendar ID.",
                    count=len(calendars),
                ),
                "help",
            )
        else:
            self._set_feedback_label(
                self.calendar_choice_hint,
                t(
                    "gcal_settings.load_calendars_empty",
                    "No accessible calendars were returned for this account.",
                ),
                "error",
            )
        self._refresh_diagnostics()

    def _on_calendar_choice_changed(self, index: int):
        if index <= 0:
            return
        calendar_id = self.calendar_choice_combo.itemData(index)
        if calendar_id:
            self.cal_id_edit.blockSignals(True)
            self.cal_id_edit.setText(calendar_id)
            self.cal_id_edit.blockSignals(False)

            # Auto-update timezone from calendar metadata
            for item in self._calendar_choices:
                if (item.get("id") or "primary") == calendar_id:
                    tz = item.get("timeZone")
                    if tz:
                        self._populate_timezones(tz)
                    break

    def _sync_edit_to_combo(self, text: str):
        target = text.strip() or "primary"
        idx = self.calendar_choice_combo.findData(target)
        if idx >= 0:
            self.calendar_choice_combo.blockSignals(True)
            self.calendar_choice_combo.setCurrentIndex(idx)
            self.calendar_choice_combo.blockSignals(False)

    def _open_sync_issues(self):
        if self.parent_app and hasattr(self.parent_app, "open_gcal_sync_issues_dialog"):
            self.parent_app.open_gcal_sync_issues_dialog()
        self._refresh_diagnostics()

    def _reset_sync_state(self):
        cleared = 0
        # 등록된 모든 gcal 캘린더 token 리셋
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            for cal in list_calendars(include_inactive=True):
                if cal.get("type") != "gcal":
                    continue
                gcal_id = cal.get("gcal_calendar_id") or ""
                if gcal_id:
                    self.settings.setValue(f"gcal_sync_token::{gcal_id}", "")
                    self.settings.setValue(f"gcal_sync_token_fails::{gcal_id}", 0)
                    cleared += 1
        except Exception:
            pass
        # bound/current calendar도 포함
        current_calendar = self.cal_id_edit.text().strip() or "primary"
        bound_calendar = str(self.settings.value("gcal_bound_calendar_id", "") or "")
        for calendar_id in {current_calendar, bound_calendar}:
            if not calendar_id:
                continue
            self.settings.setValue(f"gcal_sync_token::{calendar_id}", "")
            self.settings.setValue(f"gcal_sync_token_fails::{calendar_id}", 0)
            cleared += 1

        self._set_feedback_label(
            self.test_access_result,
            t("gcal_settings.test_access_idle", "No test has been run yet."),
            "help",
        )
        self._refresh_diagnostics()
        QMessageBox.information(
            self,
            t("gcal_settings.reset_sync_state_done_title", "Sync cache reset"),
            t(
                "gcal_settings.reset_sync_state_done_body",
                "Cleared sync cache for {count} calendar binding(s). The next sync will run as a full rescan.",
                count=cleared,
            ),
        )

    def _refresh_meta(self):
        account_value = t("gcal_settings.meta_not_connected", "연결되지 않음")
        if (
            hasattr(self.parent_app, "gcal_sync")
            and self.parent_app.gcal_sync
            and getattr(self.parent_app.gcal_sync, "is_authenticated", False)
            and getattr(self.parent_app.gcal_sync, "service", None) is not None
        ):
            try:
                primary_info = (
                    self.parent_app.gcal_sync.service.calendarList()
                    .get(calendarId="primary")
                    .execute()
                )
                account_value = primary_info.get("id") or account_value
            except Exception:
                pass
        self.account_meta[1].setText(account_value)
        calendar_text, calendar_tooltip = self._resolve_calendar_display_meta(
            self.cal_id_edit.text().strip() or "primary"
        )
        self.calendar_meta[1].setText(calendar_text)
        self.calendar_meta[1].setToolTip(calendar_tooltip)
        last_sync = str(self.settings.value("last_successful_sync", "") or "")
        self.last_sync_meta[1].setText(last_sync if last_sync else t("gcal.last_sync_none", "없음"))
        self._refresh_diagnostics()

    def _refresh_diagnostics(self):
        issue_count = 0
        delete_queue_count = 0
        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            issue_count = (
                _task_repo.count_unified_task_gcal_errors()
                + _task_repo.count_gcal_delete_queue_errors()
                + _task_repo.count_gcal_sync_conflicts()
            )
            delete_queue_count = len(_task_repo.get_gcal_delete_queue())
        except Exception:
            issue_count = 0
            delete_queue_count = 0

        sync = getattr(self.parent_app, "gcal_sync", None)
        is_authenticated = bool(sync and getattr(sync, "is_authenticated", False))

        bound_calendar = (
            str(self.settings.value("gcal_bound_calendar_id", "") or "") if is_authenticated else ""
        )
        error_kind = getattr(sync, "last_error_kind", None) if sync else None
        error_message = getattr(sync, "last_error_message", None) if sync else None
        error_text = (
            f"{error_kind}: {str(error_message or '-')[:80]}"
            if error_kind and is_authenticated
            else t("gcal_settings.meta_no_error", "None")
        )

        self.issue_meta[1].setText(str(issue_count))
        self.delete_queue_meta[1].setText(str(delete_queue_count))
        self.bound_calendar_meta[1].setText(
            bound_calendar or t("gcal_settings.meta_not_bound", "Not bound yet")
        )
        self.last_error_meta[1].setText(error_text)

    def _refresh_status(self):
        authenticated = bool(
            hasattr(self.parent_app, "gcal_sync")
            and self.parent_app.gcal_sync
            and getattr(self.parent_app.gcal_sync, "is_authenticated", False)
        )
        if authenticated:
            self.status_title.setText(t("gcal_settings.status_connected", "Google Calendar 연결됨"))
            self.status_pill.setText(t("gcal_settings.status_pill_connected", "● 연결됨"))
            self.status_title.setStyleSheet(self._style_bundle["status_title_connected"])
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_connected"])
        else:
            self.status_title.setText(
                t("gcal_settings.status_not_connected", "Google Calendar 미연결")
            )
            self.status_pill.setText(t("gcal_settings.status_pill_pending", "● 인증 필요"))
            self.status_title.setStyleSheet(self._style_bundle["status_title_pending"])
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
        self._refresh_meta()

    # ──────────────────────────────────────────────
    # 액션
    # ──────────────────────────────────────────────

    def browse_creds(self):
        if self._browse_creds_open:
            return

        current_path = self.creds_path_edit.text().strip()
        start_dir = os.path.dirname(current_path) if current_path else ""
        dialog = QFileDialog(
            self,
            t("gcal_settings.creds_dialog_title", "credentials.json 선택"),
            start_dir,
            "JSON Files (*.json)",
        )
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.setModal(True)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        self._browse_creds_open = True
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                if selected:
                    self.creds_path_edit.setText(selected[0])
        finally:
            self._browse_creds_open = False

    def _copy_credentials_if_needed(self) -> bool:
        selected_json = self.creds_path_edit.text().strip()
        if not selected_json:
            return True
        if not os.path.exists(selected_json):
            QMessageBox.warning(
                self,
                t("common.error", "오류"),
                t("gcal_settings.creds_missing", "선택한 인증 파일을 찾을 수 없습니다."),
            )
            return False
        if os.path.abspath(selected_json) == os.path.abspath(CREDENTIALS_PATH):
            return True
        try:
            shutil.copy(selected_json, CREDENTIALS_PATH)
            self.creds_path_edit.setText(CREDENTIALS_PATH)
            return True
        except Exception as exc:
            QMessageBox.warning(
                self,
                t("gcal_settings.copy_error_title", "파일 복사 오류"),
                t(
                    "gcal_settings.copy_error_body",
                    "인증 파일을 복사할 수 없습니다.\n{error}",
                    error=str(exc),
                ),
            )
            return False

    def _apply_runtime_settings(self, enabled: bool):
        cal_id = self.cal_id_edit.text().strip() or "primary"
        tz_name = self._current_timezone() or "UTC"
        if hasattr(self.parent_app, "gcal_sync") and self.parent_app.gcal_sync:
            self.parent_app.gcal_sync.calendar_id = cal_id
            self.parent_app.gcal_sync.time_zone = tz_name
            if not enabled:
                self.parent_app.gcal_sync.is_authenticated = False
                self.parent_app.gcal_sync.service = None

    def _test_calendar_access(self):
        sync = getattr(self.parent_app, "gcal_sync", None)
        if (
            not sync
            or not getattr(sync, "is_authenticated", False)
            or getattr(sync, "service", None) is None
        ):
            self._set_feedback_label(
                self.test_access_result,
                t(
                    "gcal_settings.test_access_auth_needed",
                    "먼저 인증을 완료해야 테스트할 수 있습니다.",
                ),
                "error",
            )
            return
        try:
            # calendarList().list() 로 계정 접근 자체를 확인
            result = sync.service.calendarList().list(maxResults=5).execute()
            items = result.get("items", [])
            cal_count = len(items)

            # cal_id_edit 에 특정 캘린더 ID가 입력된 경우 해당 캘린더 접근도 추가 확인
            cal_id = self.cal_id_edit.text().strip()
            if cal_id and cal_id != "primary":
                try:
                    info = sync.service.calendarList().get(calendarId=cal_id).execute()
                    summary = info.get("summaryOverride") or info.get("summary") or cal_id
                    self._set_feedback_label(
                        self.test_access_result,
                        t(
                            "gcal_settings.test_access_ok",
                            "접근 확인: {name} (계정 캘린더 {count}개)",
                            name=summary,
                            count=cal_count,
                        ),
                        "success",
                    )
                except Exception:
                    # 선택된 캘린더가 없거나 접근 불가 → 경고만 표시하고 계정 자체는 OK
                    names = ", ".join(
                        (i.get("summaryOverride") or i.get("summary") or "") for i in items[:3]
                    )
                    self._set_feedback_label(
                        self.test_access_result,
                        t(
                            "gcal_settings.test_access_cal_not_found",
                            "계정 접근 OK ({count}개 캘린더) — 선택된 캘린더 ID를 찾을 수 없습니다. 목록에서 다시 선택해 주세요.\n예: {names}",
                            count=cal_count,
                            names=names,
                        ),
                        "warning",
                    )
                    return
            else:
                # "primary" 또는 빈 값이면 calendarList 전체 접근 성공으로 판단
                names = ", ".join(
                    (i.get("summaryOverride") or i.get("summary") or "") for i in items[:3]
                )
                self._set_feedback_label(
                    self.test_access_result,
                    t(
                        "gcal_settings.test_access_ok_list",
                        "계정 접근 확인 ({count}개 캘린더: {names}…)",
                        count=cal_count,
                        names=names,
                    ),
                    "success",
                )
        except Exception as exc:
            self._set_feedback_label(
                self.test_access_result,
                t("gcal_settings.test_access_fail", "접근 실패: {error}", error=str(exc)),
                "error",
            )

    def run_auth(self):
        if not self._copy_credentials_if_needed():
            return
        cal_id = self.cal_id_edit.text().strip() or "primary"
        tz_name = self._current_timezone() or "UTC"

        from calendar_app.infrastructure.google_sync.service import prepare_calendar_sync_service

        if os.path.exists(TOKEN_PATH):
            with contextlib.suppress(OSError):
                os.remove(TOKEN_PATH)

        self.parent_app.gcal_sync = prepare_calendar_sync_service(
            getattr(self.parent_app, "gcal_sync", None),
            calendar_id=cal_id,
            time_zone=tz_name,
            reset_auth=True,
        )

        if self.parent_app.gcal_sync.authenticate(self):
            self.settings.setValue("gcal_enabled", "true")
            self.enable_cb.setChecked(True)
            self._refresh_parent_state()
            self._refresh_status()
            self._load_accessible_calendars()
            self._refresh_google_calendar_list(notify=False, show_empty_message=False)
            QMessageBox.information(
                self,
                t("gcal.setup_done", "설정 완료"),
                t("gcal_settings.auth_success", "Google 인증이 성공적으로 완료되었습니다."),
            )

    def save_settings(self):
        if not self._copy_credentials_if_needed():
            return

        enabled = self.enable_cb.isChecked()
        tz_name = self._current_timezone() or "UTC"
        self.settings.setValue("gcal_enabled", "true" if enabled else "false")
        self.settings.setValue("gcal_calendar_id", self.cal_id_edit.text().strip() or "primary")
        self.settings.setValue("gcal_timezone", tz_name)
        self.settings.setValue("gcal_sync_interval", str(self.interval_spin.value()))
        self.settings.setValue("gcal_quick_sync_interval", str(self.quick_interval_spin.value()))
        self.settings.setValue(
            "gcal_hide_completed_in_gcal",
            "true" if self.hide_completed_check.isChecked() else "false",
        )

        self._apply_runtime_settings(enabled)
        self._refresh_parent_state()
        self._refresh_status()
        QMessageBox.information(
            self,
            t("gcal_settings.saved_title", "저장 완료"),
            t("gcal_settings.saved_body", "Google 동기화 설정이 저장되었습니다."),
        )
        self.accept()

    def reset_auth(self):
        reply = QMessageBox.warning(
            self,
            t("gcal_settings.reset_title", "Disconnect reset"),
            t(
                "gcal_settings.reset_confirm",
                "Delete Google auth/token data and reset linked calendar/subscription info as well?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed_calendar_count = 0
        removed_subscription_count = 0

        # 연동 해제 전 Google 서버에서 토큰 취소 (로컬 삭제보다 먼저)
        _sync = getattr(self.parent_app, "gcal_sync", None)
        if _sync is not None and hasattr(_sync, "revoke_token"):
            _sync.revoke_token()

        for path in (TOKEN_PATH, CREDENTIALS_PATH):
            if os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.remove(path)

        try:
            from calendar_app.infrastructure.db.calendar_repo import delete_calendar, list_calendars

            for cal in list_calendars(include_inactive=True):
                if cal.get("type") not in ("gcal", "ics"):
                    continue
                cal_id = str(cal.get("id") or "").strip()
                if not cal_id:
                    continue
                if delete_calendar(cal_id):
                    removed_calendar_count += 1
        except Exception:
            pass

        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            for sub in _task_repo.list_gcal_subscriptions(include_inactive=True):
                calendar_id = str(sub.get("calendar_id") or "").strip()
                if not calendar_id:
                    continue
                if _task_repo.delete_gcal_subscription(calendar_id):
                    removed_subscription_count += 1
            _task_repo.clear_gcal_delete_queue()
        except Exception:
            pass

        try:
            for key in self.settings.allKeys():
                if key.startswith("gcal_sync_token::") or key.startswith("gcal_sync_token_fails::"):
                    self.settings.remove(key)
        except Exception:
            pass

        self.settings.setValue("gcal_enabled", "false")
        self.settings.setValue("gcal_bound_calendar_id", "")
        self.settings.setValue("last_successful_sync", "")
        self.settings.setValue("gcal_calendar_id", "primary")
        self.enable_cb.setChecked(False)
        self.creds_path_edit.clear()
        self.cal_id_edit.setText("primary")
        self._set_calendar_choices([])

        if self.parent_app and hasattr(self.parent_app, "_gcal_subscription_events_cache"):
            self.parent_app._gcal_subscription_events_cache = {}

        if hasattr(self.parent_app, "gcal_sync") and self.parent_app.gcal_sync:
            self.parent_app.gcal_sync.is_authenticated = False
            self.parent_app.gcal_sync.service = None

        self._refresh_calendar_table()
        self._refresh_subscription_table()

        try:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
        except Exception:
            pass

        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

        self._set_feedback_label(
            self.test_access_result,
            t("gcal_settings.test_access_idle", "No test has been run yet."),
            "help",
        )

        self._refresh_parent_state()
        self._refresh_status()
        QMessageBox.information(
            self,
            t("gcal_settings.reset_done_title", "Reset complete"),
            t(
                "gcal_settings.reset_done_body",
                "Google auth/linkage data was cleared.\nRemoved calendars: {cal_count}\nRemoved subscriptions: {sub_count}",
                cal_count=removed_calendar_count,
                sub_count=removed_subscription_count,
            ),
        )
