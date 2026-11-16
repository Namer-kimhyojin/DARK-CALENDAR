# -*- coding: utf-8 -*-
"""Widths sized for Korean must not clip translated labels (i18n audit M11, M6).

Each surface keeps its Korean width and grows to the longest translation up to a
cap, past which the text is elided with the full text as a tooltip. The language
is switched in-process; settings live in the isolated test store (conftest).
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6 import sip
from PyQt6.QtCore import QRect, QSettings
from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QProxyStyle,
    QStyle,
    QStyleOptionComboBox,
    QWidget,
)
import pytest

from calendar_app.domain import task_constants
from calendar_app.infrastructure.i18n import I18nManager, t

LANGUAGES = ["ko", "en", "de", "ru", "vi"]
_PRIORITY_DEFAULTS = {"urgent": "긴급", "high": "높음", "normal": "보통", "low": "낮음"}
_STATUS_DEFAULTS = {
    "pending": "예정",
    "in_progress": "진행중",
    "completed": "완료",
    "deferred": "보류",
}


_APP = None


@pytest.fixture
def app():
    global _APP
    # Keep one application alive for the process: the translators installed by a
    # language switch are its children and must outlive this module.
    application = _APP = QApplication.instance() or QApplication([])
    original = QFont(application.font())
    # The app applies the saved font (default Segoe UI 11pt) at startup.
    application.setFont(QFont("Segoe UI", 11))
    yield application
    application.setFont(original)


@pytest.fixture(params=LANGUAGES)
def language(request, app):
    store = QSettings("kimhyojin", "Dark Calendar")
    original = store.value("language")
    priority = dict(task_constants.PRIORITY_TEXT)
    status = dict(task_constants.STATUS_TEXT)
    store.setValue("language", request.param)
    I18nManager()._load_translations()
    # Priority/status labels are translated once at import (a language change
    # restarts the app), so rebuild them for the in-process switch.
    for key, default in _PRIORITY_DEFAULTS.items():
        task_constants.PRIORITY_TEXT[key] = t(f"priority.{key}", default)
    for key, default in _STATUS_DEFAULTS.items():
        task_constants.STATUS_TEXT[key] = t(f"status.{key}", default)
    task_constants._rebuild_derived_constants()
    try:
        yield request.param
    finally:
        if original is None:
            store.remove("language")
        else:
            store.setValue("language", original)
        I18nManager()._load_translations()
        task_constants.PRIORITY_TEXT.update(priority)
        task_constants.STATUS_TEXT.update(status)
        task_constants._rebuild_derived_constants()


def _gcal_dialog(tmp_path, monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo, task_repo
    from calendar_app.infrastructure.google_sync import common
    from calendar_app.presentation.dialogs import gcal_settings_dialog as module

    monkeypatch.setattr(calendar_repo, "list_calendars", lambda **kwargs: [])
    monkeypatch.setattr(common, "get_default_gcal_calendar_id", lambda settings=None: "")
    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(task_repo, "get_gcal_delete_queue", lambda: [])
    monkeypatch.setattr(module, "CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setattr(module, "TOKEN_PATH", str(tmp_path / "token.json"))
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    parent.gcal_sync = SimpleNamespace(
        is_authenticated=False, service=None, calendar_id="", time_zone="Asia/Seoul"
    )
    parent._bg_workers = []
    parent.update_gcal_sync_timer = Mock()
    parent.update_sync_status = Mock()
    parent.load_center_panel = Mock()
    return parent, module.GCalSettingsDialog(parent)


def test_gcal_settings_nav_labels_fit_their_buttons(language, tmp_path, monkeypatch, app):
    parent, dialog = _gcal_dialog(tmp_path, monkeypatch)
    try:
        dialog.show()
        app.processEvents()
        sidebar = dialog.findChild(QFrame, "sidebar")
        # No exact Korean width: offscreen Hangul is narrower than Malgun Gothic,
        # which needs about 162px for "가져올 캘린더" (clipped at the old 152px).
        # The loop below checks that every label, that one included, fits.
        assert 152 <= sidebar.width() <= 280
        for index, button in enumerate(dialog._nav_btns):
            # The checked button draws its label bold, the widest state.
            dialog._switch_section(index)
            app.processEvents()
            assert button.sizeHint().width() <= button.width(), (language, button.text())
            if button.toolTip():
                assert button.text().endswith("…"), (language, button.text())
    finally:
        dialog.close()
        sip.delete(parent)  # and its dialog, while the patches hold


def _windows_ui_fonts_installed() -> bool:
    """The exact widths and caps below were measured with the Windows UI fonts.

    Without Segoe UI and Malgun Gothic (the Linux CI runner) wider fallback fonts
    are elided at the caps by design, so only the font-independent checks apply.
    """
    return {"Segoe UI", "Malgun Gothic"} <= set(QFontDatabase.families())


def _edit_field_width(combo) -> int:
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    return (
        combo.style()
        .subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            combo,
        )
        .width()
    )


def _painted_text_width(label) -> int:
    """Width QLabel paints its text into: a framed label indents it half an 'x'."""
    indent = label.indent()
    if indent < 0 and label.frameWidth() > 0:
        indent = label.fontMetrics().horizontalAdvance("x") // 2 - label.margin()
    return label.contentsRect().width() - 2 * label.margin() - max(0, indent)


def _assert_info_labels_fit(dialog, language):
    labels = [label for label, _text in dialog._info_row_labels]
    assert len(labels) == 2
    assert labels[0].width() == labels[1].width()
    for label in labels:
        text_width = QFontMetricsF(label.font()).horizontalAdvance(label.text())
        assert text_width <= _painted_text_width(label), (language, label.text())
        if label.wordWrap():
            # One line, as laid out: multi-word and CJK labels must not wrap.
            one_line = label.heightForWidth(100000)
            assert label.heightForWidth(label.width()) == one_line, (language, label.text())
        if label.toolTip():
            assert label.text().endswith("…"), (language, label.text())
    return labels


def _task_dialog(task_type, tmp_path, monkeypatch):
    from calendar_app.infrastructure.db import database_unified
    from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

    database_unified.db_manager.close_all_connections()
    monkeypatch.setattr(database_unified, "DB_PATH", str(tmp_path / "tasks.db"))
    database_unified.initialize_unified_database()
    return UnifiedTaskDialog(task_type=task_type)


@pytest.mark.parametrize("task_type", ["schedule", "routine"])
def test_task_dialog_info_labels_and_selectors_fit(language, task_type, tmp_path, monkeypatch, app):
    from calendar_app.infrastructure.db import database_unified

    dialog = _task_dialog(task_type, tmp_path, monkeypatch)
    try:
        dialog.show()
        for _ in range(3):
            app.processEvents()
        labels = _assert_info_labels_fit(dialog, language)
        combos = [dialog.priority_combo, dialog.status_combo]
        assert combos[0].width() == combos[1].width()
        for combo in combos:
            widest = max(
                combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                for i in range(combo.count())
            )
            assert widest <= _edit_field_width(combo), (language, combo.currentText())
        if language == "ko" and _windows_ui_fonts_installed():
            assert [label.width() for label in labels] == [52, 52]
            assert [combo.width() for combo in combos] == [155, 155]
    finally:
        dialog.close()
        sip.delete(dialog)
        database_unified.db_manager.close_all_connections()


def test_task_dialog_info_labels_fit_at_largest_font(language, tmp_path, monkeypatch, app):
    """At 24pt (Appearance's largest size) the labels widen or elide, never wrap or clip."""
    from calendar_app.infrastructure.db import database_unified

    QSettings("kimhyojin", "Dark Calendar").setValue("font_size", 24)
    app.setFont(QFont("Segoe UI", 24))
    dialog = _task_dialog("schedule", tmp_path, monkeypatch)
    try:
        dialog.show()
        for _ in range(3):
            app.processEvents()
        labels = _assert_info_labels_fit(dialog, language)
        assert labels[0].width() > 52
        if _windows_ui_fonts_installed():
            # The cap grows with the font, so these translations show in full.
            assert not any(label.toolTip() for label in labels), language
    finally:
        dialog.close()
        sip.delete(dialog)
        database_unified.db_manager.close_all_connections()


def test_width_caps_grow_with_the_font_size(app):
    from calendar_app.shared.typography import font_scaled_width

    assert font_scaled_width(QFontMetricsF(QFont("Segoe UI", 11)), 120) == 120
    assert font_scaled_width(QFontMetricsF(QFont("Segoe UI", 9)), 120) == 120
    assert font_scaled_width(QFontMetricsF(QFont("Segoe UI", 24)), 120) > 240


class _TextRecorder(QProxyStyle):
    def __init__(self):
        super().__init__()
        self.drawn = []

    def drawItemText(self, painter, rect, flags, palette, enabled, text, role=None):  # noqa: N802
        self.drawn.append((QRect(rect), text))
        if role is None:
            return super().drawItemText(painter, rect, flags, palette, enabled, text)
        return super().drawItemText(painter, rect, flags, palette, enabled, text, role)


def test_capped_selector_elides_instead_of_clipping(app):
    from calendar_app.presentation.dialogs.task_dialog_base import _ElidingComboBox

    combo = _ElidingComboBox()
    recorder = _TextRecorder()
    combo.setStyle(recorder)
    long_text = "⏸️ Aufgeschoben bis nächste Woche"
    combo.addItems(["⚡ Normal", long_text])
    combo.setFixedWidth(120)
    combo.resize(120, 32)
    try:
        for index, expect_elided in ((0, False), (1, True)):
            combo.setCurrentIndex(index)
            recorder.drawn.clear()
            combo.render(QImage(combo.size(), QImage.Format.Format_ARGB32))
            rect, text = recorder.drawn[-1]
            assert text.endswith("…") is expect_elided, text
            assert combo.fontMetrics().horizontalAdvance(text) <= rect.width(), text
        assert combo.currentText() == long_text
    finally:
        # Destroy the combo now, while its proxy style is still alive; a deferred
        # delete would run after Python has freed the style.
        sip.delete(combo)


def test_task_card_info_labels_fit_their_column(language, app):
    from calendar_app.presentation.widgets import ui_components

    task = {
        "name": "Review",
        "type": "schedule",
        "deadline": "2026-11-13 09:00:00",
        "end_date": "2026-11-13 10:00:00",
        "location": "Room 3",
        "assignee": "Kim",
        "memo": "Agenda",
        "calendar_id": "local::work",
    }
    button = ui_components.DraggableTaskButton(77, "Review")
    try:
        with patch.object(
            ui_components.calendar_repo, "get_calendar", return_value={"name": "Work"}
        ):
            assert button._render_info_items(task)
        layout = button.info_layout
        labels = [layout.itemAt(i).layout().itemAt(0).widget() for i in range(layout.count())]
        assert len(labels) >= 4
        assert len({label.width() for label in labels}) == 1
        for label in labels:
            text_width = label.fontMetrics().horizontalAdvance(label.text())
            assert text_width <= label.width(), (language, label.text())
        if language == "ko" and _windows_ui_fonts_installed():
            assert labels[0].width() == 70
    finally:
        sip.delete(button)


def test_drag_card_hint_fits_its_line(language, app):
    from calendar_app.presentation import drag_drop_manager

    pixmap = drag_drop_manager.build_task_drag_pixmap([1], {1: {"name": "Review"}})
    hint_room = 137 + pixmap.width() - 252
    hint = t("drag.hint_copy", "Ctrl: 복사  /  기본: 이동")
    metrics = QFontMetrics(drag_drop_manager._drag_font(8))
    assert 252 <= pixmap.width() <= 252 + 48
    if metrics.horizontalAdvance(hint) > hint_room:
        # Past the 48px the card may grow, the hint is shortened instead.
        assert pixmap.width() == 252 + 48, (language, hint)
    if _windows_ui_fonts_installed():
        assert metrics.horizontalAdvance(hint) <= hint_room, (language, hint)
    if language == "ko" and _windows_ui_fonts_installed():
        assert pixmap.width() == 252
