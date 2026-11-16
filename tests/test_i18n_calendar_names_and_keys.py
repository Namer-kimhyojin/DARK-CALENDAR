# -*- coding: utf-8 -*-
"""Built-in calendar names and small UI strings follow the UI language."""

import json
from pathlib import Path
import re
from unittest.mock import patch

from PyQt6.QtCore import QDate, QSettings, Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QApplication, QLabel
import pytest

from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.i18n import I18nManager, i18n, t
from calendar_app.presentation.locale_names import DEFAULT_LOCAL_CALENDAR_ID
from tests.support import TemporaryDatabaseTestCase

_HANGUL = re.compile(r"[가-힣]")
_EN_BUNDLE = Path(__file__).resolve().parents[1] / "locales" / "en.json"


def _switch_language(code):
    # conftest redirects this store to a temporary INI file.
    settings = QSettings("kimhyojin", "Dark Calendar")
    settings.setValue("language", code)
    settings.sync()
    I18nManager()._load_translations()


_APP = []


def _ui_language(code):
    # Keep the application alive across tests; translators installed by the
    # i18n manager are its children.
    if not _APP:
        _APP.append(QApplication.instance() or QApplication([]))
    app = _APP[0]
    previous = i18n.lang
    _switch_language(code)
    try:
        yield app
    finally:
        _switch_language(previous)


@pytest.fixture
def english_ui():
    yield from _ui_language("en")


@pytest.fixture
def korean_ui():
    yield from _ui_language("ko")


def _en_has(key):
    data = json.loads(_EN_BUNDLE.read_text(encoding="utf-8", errors="strict"))
    node = data
    if key in node:
        return True
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


class _Database(TemporaryDatabaseTestCase):
    def runTest(self):  # pragma: no cover - only used as a fixture helper
        pass


@pytest.fixture
def default_local_calendar():
    database = _Database()
    database.setUp()
    try:
        conn = calendar_repo.db_manager.get_connection()
        conn.execute("DELETE FROM calendar")
        conn.commit()
        assert calendar_repo.upsert_calendar(
            DEFAULT_LOCAL_CALENDAR_ID, "local", "기본", is_default=True
        )
        yield
    finally:
        database.tearDown()


def test_task_dialog_calendar_combo_shows_default_in_english(english_ui, default_local_calendar):
    from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

    dialog = UnifiedTaskDialog(initial_date=QDate(2026, 11, 13), task_type="schedule")
    try:
        index = dialog.calendar_combo.findData(DEFAULT_LOCAL_CALENDAR_ID)
        assert index >= 0
        text = dialog.calendar_combo.itemText(index)
        assert text.endswith("Default")
        assert not _HANGUL.search(text)
        assert dialog._get_selected_calendar_id() == DEFAULT_LOCAL_CALENDAR_ID
        # The stored row keeps its language-neutral identity and name.
        assert calendar_repo.get_calendar(DEFAULT_LOCAL_CALENDAR_ID)["name"] == "기본"
        label = next(child for child in dialog.findChildren(QLabel) if child.text() == "Calendar")
        font = QFont(label.font())
        font.setPixelSize(13)
        font.setBold(True)
        assert label.minimumWidth() >= QFontMetrics(font).horizontalAdvance("Calendar")
    finally:
        dialog.close()
        dialog.deleteLater()
        english_ui.processEvents()


def test_task_dialog_period_arrow_follows_right_to_left(english_ui, default_local_calendar):
    from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

    english_ui.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    try:
        dialog = UnifiedTaskDialog(initial_date=QDate(2026, 11, 13), task_type="schedule")
        try:
            dialog._update_period_layout_for_width(900)
            assert dialog._period_direction_label.text() == "←"
        finally:
            dialog.close()
            dialog.deleteLater()
    finally:
        english_ui.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        english_ui.processEvents()


def test_calendar_manager_names_follow_language(english_ui):
    from calendar_app.presentation.dialogs.calendar_manager_page import _shown_name

    assert _shown_name({"id": DEFAULT_LOCAL_CALENDAR_ID, "name": "기본"}) == "Default"
    assert _shown_name({"id": DEFAULT_LOCAL_CALENDAR_ID, "name": "Home"}) == "Home"
    assert _shown_name({"id": "local::메모", "name": "메모"}) == "메모"


class _FakePage:
    def __init__(self, calendar):
        self.calendar = calendar
        self.changed = []

    def current(self):
        return self.calendar

    def _changed(self, success):
        self.changed.append(success)


def _rename(page, typed=None):
    from calendar_app.presentation.dialogs import calendar_manager_page

    prefill = {}

    def fake_get_text(*_args, **kwargs):
        prefill["text"] = kwargs.get("text")
        return (prefill["text"] if typed is None else typed), True

    with (
        patch.object(calendar_manager_page.QInputDialog, "getText", side_effect=fake_get_text),
        patch.object(calendar_repo, "rename_calendar", return_value=True) as rename,
    ):
        calendar_manager_page.CalendarManagerPage._rename(page)
    return prefill["text"], rename


def test_unchanged_rename_keeps_the_stored_default_name(english_ui):
    page = _FakePage({"id": DEFAULT_LOCAL_CALENDAR_ID, "type": "local", "name": "기본"})
    prefill, rename = _rename(page)
    assert prefill == "Default"
    rename.assert_not_called()
    assert page.changed == []


def test_changed_rename_is_saved(english_ui):
    page = _FakePage({"id": DEFAULT_LOCAL_CALENDAR_ID, "type": "local", "name": "기본"})
    _prefill, rename = _rename(page, typed="  Home  ")
    rename.assert_called_once_with(DEFAULT_LOCAL_CALENDAR_ID, "Home")
    assert page.changed == [True]


def test_nlp_parser_leaves_empty_title_to_callers(english_ui):
    from calendar_app.infrastructure.nlp.nlp_engine import parse_nlp_task
    from calendar_app.presentation.widgets.panel_widget_common import _parse_quick_add_text

    assert parse_nlp_task("   ")["title"] == ""
    assert parse_nlp_task("3pm")["title"] == ""
    time_text, title = _parse_quick_add_text("3pm")
    assert time_text == "15:00"
    assert title == t("dialog.task.untitled", "제목 없음") == "Untitled"


def test_color_swatch_tooltips_are_translated(english_ui):
    from calendar_app.presentation.dialogs.color_swatch_widget import GoogleColorSwatch

    swatch = GoogleColorSwatch()
    try:
        none_button, *palette = swatch._buttons
        assert len(palette) == 11
        tips = [button.toolTip() for button in palette]
        assert "Lavender" in tips and "Tomato" in tips
        assert not any(_HANGUL.search(tip) for tip in tips)
        assert none_button.toolTip() == t("color.none", "색상 없음")
        if _en_has("color.none"):
            assert not _HANGUL.search(none_button.toolTip())
    finally:
        swatch.deleteLater()
        english_ui.processEvents()


def test_daily_routine_cycle_label_is_english(english_ui):
    from calendar_app.domain.routine_cycle import cycle_display_name

    assert cycle_display_name("daily") == "Daily"
    assert cycle_display_name("daily", scope="panel") == "[Daily]"
    assert cycle_display_name("weekly") == "Weekly"


def test_daily_routine_cycle_label_keeps_korean(korean_ui):
    from calendar_app.domain.routine_cycle import cycle_display_name

    assert cycle_display_name("daily") == "일간"
    assert cycle_display_name("weekly") == "주간"
    assert cycle_display_name("daily", scope="panel") == "[매일]"
