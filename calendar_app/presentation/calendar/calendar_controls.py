# -*- coding: utf-8 -*-
"""Direct calendar display and new-event defaults on the main calendar."""

import sqlite3

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application.calendar_preferences import set_default_calendar
from calendar_app.application.calendar_provider_catalog import PROVIDERS
from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.shared.color_utils import contrast_safe_color
from calendar_app.shared.icon_map import ICON, icon


def _source_name(app, calendar):
    coordinator = getattr(app, "_calendar_sync_coordinator", None)
    provider = coordinator.calendar_providers.get(calendar["id"]) if coordinator else None
    if provider in PROVIDERS:
        from calendar_app.presentation.main_window.calendar_sync_coordinator import provider_name

        return provider_name(provider)
    return {
        "gcal": "Google Calendar",
        "outlook": "Outlook",
        "caldav": "CalDAV",
        "local": t("sync_unified.local", "로컬"),
        "shared": t("sync_unified.shared", "PC 공유"),
        "ics": t("sync_unified.ics", "ICS 구독"),
    }.get(calendar.get("type"), t("sync_unified.local", "로컬"))


def refresh_calendar_preferences(app, *, default_changed=False):
    """Refresh all views after a saved preference without starting OAuth."""
    from calendar_app.presentation.calendar.month_renderer import invalidate_calendar_meta_cache
    from calendar_app.presentation.panels.side_panel_renderer import invalidate_panel_calendar_cache

    invalidate_calendar_meta_cache()
    invalidate_panel_calendar_cache()
    if default_changed and hasattr(app, "refresh_gcal_sync_state"):
        app.refresh_gcal_sync_state(authenticate_silently=False)
    coordinator = getattr(app, "_calendar_sync_coordinator", None)
    if coordinator:
        coordinator.refresh()
    if hasattr(app, "schedule_panel_refresh"):
        app.schedule_panel_refresh(left=True, center=True, right=True)


class CalendarVisibilityDialog(QDialog):
    """Immediate display toggles that stay open while the calendar rerenders."""

    def __init__(self, app):
        # Parent the form to the window, never to a toolbar destroyed by rendering.
        super().__init__(app)
        self.app = app
        self.setObjectName("CalendarVisibilityDialog")
        title = t("calendar_controls.display_title", "메인 화면에 표시할 캘린더")
        apply_dialog_title(self, title)
        settings = app.settings
        apply_common_dialog_style(
            self,
            minimum_width=380,
            size=(480, 470),
            theme_color=settings.value("theme_color", "#4da6ff"),
            text_theme=settings.value("text_theme", "dark"),
            panel_base_color=settings.value("panel_base_color", "#0d1b2e"),
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        heading = QLabel(title)
        heading.setProperty("role", "dialogTitle")
        heading.setWordWrap(True)
        root.addWidget(heading)
        hint = QLabel(
            t(
                "calendar_controls.display_hint",
                "변경 즉시 달력과 일정 목록에 반영됩니다. 숨겨도 동기화와 기본 저장 대상은 유지됩니다.",
            )
        )
        hint.setProperty("role", "field_hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        scroll = QScrollArea()
        scroll.setObjectName("CalendarDisplayScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setAutoFillBackground(False)
        rows = QVBoxLayout(body)
        rows.setContentsMargins(0, 0, 8, 0)
        rows.setSpacing(10)
        self.checkboxes = {}
        load_failed = False
        try:
            calendars = calendar_repo.list_calendars(include_inactive=True)
        except (sqlite3.Error, OSError, RuntimeError):
            calendars, load_failed = [], True
        for calendar in calendars:
            name = str(calendar.get("name") or calendar["id"])
            check = QCheckBox(name)
            check.setObjectName("calendar_display_" + calendar["id"])
            check.setAccessibleName(name)
            check.setChecked(bool(calendar.get("is_visible", 1)))
            check.setToolTip(name)
            check.toggled.connect(
                lambda checked, identity=calendar["id"], control=check: self._toggle(
                    identity, checked, control
                )
            )
            self.checkboxes[calendar["id"]] = check
            rows.addWidget(check)
            traits = [_source_name(app, calendar)]
            if calendar.get("is_default"):
                traits.append(t("calendar_controls.default_badge", "새 일정 저장"))
            if calendar_repo.is_calendar_row_read_only(calendar):
                traits.append(t("outlook.read_only", "읽기 전용"))
            if not calendar.get("is_active", 1):
                traits.append(t("sync_redesign.not_selected_badge", "가져오기 선택 안 함"))
            meta = QLabel(" · ".join(traits))
            meta.setProperty("role", "field_hint")
            meta.setWordWrap(True)
            rows.addWidget(meta)
        if not self.checkboxes:
            rows.addWidget(QLabel(t("menu.no_calendars", "캘린더 없음")))
        rows.addStretch()
        scroll.setWidget(body)
        body.setAutoFillBackground(False)
        root.addWidget(scroll, 1)
        self.feedback = QLabel()
        self.feedback.setProperty("role", "field_hint")
        self.feedback.setWordWrap(True)
        if load_failed:
            self.feedback.setText(t("menu.calendar_load_error", "캘린더 로드 실패"))
        root.addWidget(self.feedback)
        footer, close, _ = build_dialog_footer(
            ok_label=t("common.close", "닫기"),
            cancel_label=None,
            ok_object_name="ghost_btn",
        )
        close.clicked.connect(self.accept)
        root.addLayout(footer)

    def _toggle(self, identity, checked, control):
        try:
            success = calendar_repo.set_calendar_visible(identity, checked)
        except (sqlite3.Error, OSError, RuntimeError):
            success = False
        if success:
            self.feedback.setText(t("sync_unified.calendar_saved", "캘린더 설정을 반영했습니다."))
            refresh_calendar_preferences(self.app)
        else:
            control.blockSignals(True)
            control.setChecked(not checked)
            control.blockSignals(False)
            self.feedback.setText(
                t(
                    "sync_unified.calendar_save_failed",
                    "설정을 저장하지 못했습니다. 다시 시도하세요.",
                )
            )


class CalendarQuickControls(QWidget):
    """One default selector shared by the main toolbar and calendar manager."""

    preference_saved = pyqtSignal(bool)

    def __init__(self, app, *, show_visibility=True, show_manage=True, parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("CalendarQuickControls")
        tokens = get_dialog_theme_tokens(settings=app.settings)
        self.setStyleSheet(
            f"QWidget#CalendarQuickControls {{ background: transparent; }}"
            f"QLabel#calendar_default_label {{ color: {tokens['text_secondary']}; }}"
            f"QComboBox#calendar_default_selector {{ color: {tokens['text_primary']}; "
            f"background: {tokens['surface_item']}; border: 1px solid {tokens['border']}; "
            "border-radius: 6px; padding: 3px 8px; min-height: 24px; max-height: 28px; }"
            "QComboBox#calendar_default_selector::drop-down { border: none; width: 20px; }"
            f"QComboBox#calendar_default_selector QAbstractItemView {{ background: {tokens['surface_item']}; "
            f"color: {tokens['text_primary']}; selection-background-color: {tokens['accent']}; "
            f"selection-color: {tokens['accent_text']}; }}"
            f"QPushButton#calendar_display_button, QPushButton#calendar_manage_button {{ "
            f"color: {tokens['text_secondary']}; background: transparent; border: 1px solid {tokens['border']}; "
            "border-radius: 6px; padding: 3px 8px; min-height: 24px; max-height: 28px; }"
            f"QPushButton#calendar_display_button:hover, QPushButton#calendar_manage_button:hover {{ "
            f"color: {tokens['text_primary']}; border-color: {tokens['accent']}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 3, 4, 3)
        root.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.label = QLabel(t("calendar_controls.default_label", "새 일정 저장"))
        self.label.setObjectName("calendar_default_label")
        row.addWidget(self.label)
        self.default_combo = QComboBox()
        self.default_combo.setObjectName("calendar_default_selector")
        self.default_combo.setAccessibleName(
            t("calendar_controls.default_accessible", "새 일정의 기본 캘린더")
        )
        self.default_combo.setMinimumWidth(100)
        self.default_combo.setMaximumWidth(260)
        self.default_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.default_combo.currentIndexChanged.connect(self._set_default)
        row.addWidget(self.default_combo, 1)
        self.display_button = QPushButton()
        self.display_button.setObjectName("calendar_display_button")
        self.display_button.setIcon(icon(ICON.VIEW_CALENDAR, color=tokens["text_primary"]))
        self.display_button.clicked.connect(self._display)
        self.display_button.setVisible(show_visibility)
        row.addWidget(self.display_button)
        self.manage_button = QPushButton(t("calendar_controls.manage", "관리"))
        self.manage_button.setObjectName("calendar_manage_button")
        self.manage_button.setToolTip(t("menu.calendar_manage", "캘린더 관리..."))
        self.manage_button.clicked.connect(lambda: app.open_calendar_management())
        self.manage_button.setVisible(show_manage)
        row.addWidget(self.manage_button)
        row.addStretch()
        root.addLayout(row)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        root.addWidget(self.feedback)
        coordinator = getattr(app, "_calendar_sync_coordinator", None)
        if coordinator:
            coordinator.changed.connect(self.reload)
        self.reload()

    def reload(self):
        try:
            rows = calendar_repo.list_calendars(include_inactive=True)
            writable = calendar_repo.get_writable_calendars()
            current = calendar_repo.get_default_calendar()
        except (sqlite3.Error, OSError, RuntimeError):
            rows, writable, current = [], [], None
            self.feedback.setText(t("menu.calendar_load_error", "캘린더 로드 실패"))
            self.feedback.show()
        current_id = (current or {}).get("id")
        tokens = get_dialog_theme_tokens(settings=self.app.settings)
        self.default_combo.blockSignals(True)
        self.default_combo.clear()
        for calendar in writable:
            name = str(calendar.get("name") or calendar["id"])
            if not calendar.get("is_visible", 1):
                name += " · " + t("calendar_controls.hidden_badge", "숨김")
            color = contrast_safe_color(
                calendar.get("color") or tokens["accent"],
                tokens["surface_item"],
                minimum=3.0,
            )
            self.default_combo.addItem(icon(ICON.VIEW_CALENDAR, color=color), name, calendar["id"])
            details = t(
                "calendar_controls.default_hint", "새 일정을 만들 때 처음 선택되는 캘린더입니다."
            )
            if not calendar.get("is_visible", 1):
                details += "\n" + t(
                    "calendar_controls.hidden_default_hint",
                    "이 캘린더의 일정은 현재 화면에서 숨겨져 있습니다.",
                )
            self.default_combo.setItemData(
                self.default_combo.count() - 1, details, Qt.ItemDataRole.ToolTipRole
            )
        index = self.default_combo.findData(current_id)
        self.default_combo.setCurrentIndex(index)
        self.default_combo.setEnabled(bool(writable))
        self.default_combo.setPlaceholderText(
            t("calendar_controls.no_writable", "저장 가능한 캘린더 없음")
        )
        self.default_combo.setToolTip(
            str((current or {}).get("name") or "")
            + "\n"
            + t("calendar_controls.default_hint", "새 일정을 만들 때 처음 선택되는 캘린더입니다.")
            + (
                "\n"
                + t(
                    "calendar_controls.hidden_default_hint",
                    "이 캘린더의 일정은 현재 화면에서 숨겨져 있습니다.",
                )
                if current and not current.get("is_visible", 1)
                else ""
            )
        )
        self.default_combo.blockSignals(False)
        count = sum(bool(calendar.get("is_visible", 1)) for calendar in rows)
        text = t("calendar_controls.display_count", "화면 표시 {count}/{total}").format(
            count=count, total=len(rows)
        )
        self.display_button.setText(text)
        self.display_button.setAccessibleName(text)
        self.display_button.setToolTip(
            t("calendar_controls.display_title", "메인 화면에 표시할 캘린더")
        )

    def _set_default(self, index):
        identity = self.default_combo.itemData(index)
        if identity is None:
            return
        try:
            success = set_default_calendar(identity, self.app.settings, repository=calendar_repo)
        except (sqlite3.Error, OSError, RuntimeError):
            success = False
        if success:
            self.feedback.hide()
            refresh_calendar_preferences(self.app, default_changed=True)
        else:
            self.feedback.setText(
                t(
                    "sync_unified.calendar_save_failed",
                    "설정을 저장하지 못했습니다. 다시 시도하세요.",
                )
            )
            self.feedback.show()
        self.reload()
        self.preference_saved.emit(success)

    def _display(self):
        # The dialog survives main-calendar redraws, so several toggles are easy.
        dialog = CalendarVisibilityDialog(self.app)
        dialog.exec()
        dialog.deleteLater()
