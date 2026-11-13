# -*- coding: utf-8 -*-
"""Small UI surfaces read their texts from locale keys (i18n audit batch C).

Covers the pomodoro settings dialog (M3, L11), the ON/OFF toggles (L11), the help
center eyebrows (L11), the side-panel checklist tooltips and directive badge (L8,
L11), the focus-mode empty checklist (M8), the pomodoro summary seconds (L16), the
drag preview title (M6) and the alarm reminder checkboxes (H4).

Under Korean each surface keeps today's text. For another language the new keys are
overlaid with English values, so the checks hold before and after the locale files
get those keys. The language is switched in-process in the isolated test store.
"""

import ast
from contextlib import contextmanager
import inspect
from pathlib import Path
import re
import textwrap
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.infrastructure import i18n as i18n_module
from calendar_app.infrastructure.i18n import I18nManager, i18n, t

HANGUL = re.compile(r"[ㄱ-ㆎ가-힣]")
ROOT = Path(__file__).resolve().parents[1]

# English values of the keys this batch adds (the integration step writes them to
# the locale files). Overlaid in the non-Korean checks.
NEW_KEYS_EN = {
    "common.toggle_on": "ON",
    "common.toggle_off": "OFF",
    "dialog.pomodoro_settings.run_mode": "Run Mode",
    "dialog.pomodoro_settings.run_mode_help": "The selected mode decides how the timer runs.",
    "dialog.pomodoro_settings.auto_start_break_help": (
        "When focus time ends, the break timer starts right away."
    ),
    "dialog.pomodoro_settings.auto_start_focus_help": (
        "When a break ends, the next focus cycle starts right away."
    ),
    "shortcut.hero.quickstart.eyebrow": "QUICK START",
    "shortcut.hero.workflows.eyebrow": "CORE FLOW",
    "shortcut.hero.recovery.eyebrow": "RECOVERY",
    "shortcut.hero.reference.eyebrow": "REFERENCE",
    "shortcut.hero.search.eyebrow": "SEARCH",
    "panel.directive_receiver_badge": "BY",
    "panel.checklist.progress_tooltip": "{done} of {total} done",
    "panel.checklist.locked_previous": "Complete the previous steps first",
    "panel.checklist.locked_next": "Uncheck the later steps first",
    "focus.checklist_empty": "No checklist items.",
    "drag.single_untitled": "1 event",
    "drag.count_title": "{count} events",
}

_APP = None


@pytest.fixture
def app():
    global _APP
    # One application for the process: translators installed by a language switch
    # are its children and must outlive this module.
    _APP = QApplication.instance() or QApplication([])
    return _APP


@contextmanager
def _overlay(values):
    """Put flat dotted keys in front of the loaded translations."""
    original = i18n.translations
    merged = dict(original)
    merged.update(values)
    i18n.translations = merged
    try:
        yield
    finally:
        i18n.translations = original


@contextmanager
def _language(code):
    store = QSettings("kimhyojin", "Dark Calendar")
    original = store.value("language")
    store.setValue("language", code)
    I18nManager()._load_translations()
    try:
        with _overlay(NEW_KEYS_EN if code != "ko" else {}):
            yield
    finally:
        if original is None:
            store.remove("language")
        else:
            store.setValue("language", original)
        I18nManager()._load_translations()


def _visible_texts(root):
    texts = [root.windowTitle()]
    for widget in root.findChildren(QWidget):
        if isinstance(widget, QLabel | QAbstractButton):
            texts.append(widget.text())
        if isinstance(widget, QComboBox):
            texts.extend(widget.itemText(i) for i in range(widget.count()))
        if isinstance(widget, QAbstractSpinBox):
            texts.extend((getattr(widget, "suffix", str)(), getattr(widget, "prefix", str)()))
        texts.append(widget.toolTip())
    return [text for text in texts if text]


def _label_texts(root):
    return [label.text() for label in root.findChildren(QLabel)]


# ── Pomodoro settings dialog (M3, L11) ────────────────────────────────────────


class _FakeSettings:
    def __init__(self, values=None):
        self._values = dict(values or {})

    def value(self, key, default=None, type=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value

    def sync(self):
        pass


def _pomodoro_dialog(values=None):
    from calendar_app.presentation.dialogs.pomodoro_settings_dialog import (
        PomodoroSettingsDialog,
    )

    host = QWidget()
    host.settings = _FakeSettings(values)
    return host, PomodoroSettingsDialog(host)


def _close(host, dialog):
    dialog.close()
    dialog.deleteLater()
    host.deleteLater()


def test_pomodoro_dialog_keeps_korean_texts(app):
    host, dialog = _pomodoro_dialog(
        {"pomodoro_auto_start_break": "true", "pomodoro_auto_start_focus": "false"}
    )
    try:
        labels = _label_texts(dialog)
        for text in (
            "실행 모드",
            "선택한 모드에 따라 타이머 동작 방식이 결정됩니다.",
            "집중 시간이 끝나면 휴식 타이머가 즉시 시작됩니다.",
            "휴식 시간이 끝나면 다음 집중 사이클이 즉시 시작됩니다.",
        ):
            assert text in labels
        assert dialog.auto_start_break_cb.text() == "ON"
        assert dialog.auto_start_focus_cb.text() == "OFF"
    finally:
        _close(host, dialog)


@pytest.mark.parametrize("code", ["en", "de"])
def test_pomodoro_dialog_shows_no_korean_in_other_languages(app, code):
    with _language(code):
        host, dialog = _pomodoro_dialog()
        try:
            leaked = [text for text in _visible_texts(dialog) if HANGUL.search(text)]
            assert leaked == [], (code, leaked)
            labels = _label_texts(dialog)
            assert t("dialog.pomodoro_settings.run_mode", "실행 모드") in labels
            assert t("dialog.pomodoro_settings.auto_start_focus_help", "") in labels
        finally:
            _close(host, dialog)


def test_pomodoro_toggle_reads_the_shared_on_off_keys(app):
    with _overlay({"common.toggle_on": "AN", "common.toggle_off": "AUS"}):
        host, dialog = _pomodoro_dialog(
            {"pomodoro_auto_start_break": "true", "pomodoro_auto_start_focus": "false"}
        )
        try:
            assert dialog.auto_start_break_cb.text() == "AN"
            assert dialog.auto_start_focus_cb.text() == "AUS"
            dialog.auto_start_focus_cb.setChecked(True)
            assert dialog.auto_start_focus_cb.text() == "AN"
        finally:
            _close(host, dialog)


def test_widget_manager_toggle_uses_the_shared_on_off_keys(app):
    from calendar_app.presentation.widgets.overlay_manager_dialog import (
        _load_tokens,
        _ToggleBtn,
    )

    tokens = _load_tokens()
    on_btn = _ToggleBtn(True, tokens)
    off_btn = _ToggleBtn(False, tokens)
    try:
        assert (on_btn.text(), off_btn.text()) == ("ON", "OFF")
        with _overlay({"common.toggle_on": "AN", "common.toggle_off": "AUS"}):
            on_btn.setChecked(False)
            off_btn.setChecked(True)
            assert (on_btn.text(), off_btn.text()) == ("AUS", "AN")
    finally:
        on_btn.deleteLater()
        off_btn.deleteLater()


# ── Help center eyebrows (L11) ────────────────────────────────────────────────

_EYEBROWS = {
    "quickstart": "QUICK START",
    "workflows": "CORE FLOW",
    "recovery": "RECOVERY",
    "reference": "REFERENCE",
    "search": "SEARCH",
}


def _eyebrow_texts(dialog):
    texts = {}
    for page in _EYEBROWS:
        widget = getattr(dialog, f"_build_{page}_page")()
        eyebrows = [
            label.text()
            for label in widget.findChildren(QLabel)
            if label.objectName() == "helpPageEyebrow"
        ]
        assert len(eyebrows) == 1, (page, eyebrows)
        texts[page] = eyebrows[0]
        widget.deleteLater()
    return texts


def test_help_center_eyebrows_keep_korean_ui_and_follow_their_keys(app):
    from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog

    dialog = HelpCenterDialog()
    try:
        assert _eyebrow_texts(dialog) == _EYEBROWS
        marked = {f"shortcut.hero.{page}.eyebrow": f"<{page}>" for page in _EYEBROWS}
        with _overlay(marked):
            assert _eyebrow_texts(dialog) == {page: f"<{page}>" for page in _EYEBROWS}
    finally:
        dialog.close()
        dialog.deleteLater()


def test_help_center_eyebrows_show_no_korean_in_english(app):
    from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog

    with _language("en"):
        dialog = HelpCenterDialog()
        try:
            texts = _eyebrow_texts(dialog)
            assert not [text for text in texts.values() if HANGUL.search(text)], texts
        finally:
            dialog.close()
            dialog.deleteLater()


# ── Side-panel checklist tooltips and directive badge (L8, L11) ───────────────


class _PanelHost(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("kimhyojin", "Dark Calendar")
        self.expanded_tids = {7}
        self.selected_task_ids = set()
        self.selected_directive_ids = set()


def _process_card():
    from calendar_app.presentation.panels import side_panel_renderer

    host = _PanelHost()
    # Steps 1 and 3 are done: unchecking step 1 waits for step 3 and checking step 4
    # waits for step 2, while steps 2 and 3 stay clickable.
    items = [
        ("step one", True, lambda: None),
        ("step two", False, lambda: None),
        ("step three", True, lambda: None),
        ("step four", False, lambda: None),
    ]
    card = side_panel_renderer.create_task_box(
        host,
        "process",
        lambda: None,
        tid=7,
        checklist_display_type="process",
        checklist_items=items,
    )
    return host, card


def _checklist_tooltips(card):
    progress = card.findChild(QProgressBar)
    rows = card.findChildren(QWidget, "panel_checklist_row")
    return progress.toolTip(), [row.toolTip() for row in rows]


def test_side_panel_checklist_tooltips_keep_korean_texts(app):
    host, card = _process_card()
    try:
        progress, rows = _checklist_tooltips(card)
        assert progress == "완료 2개 / 전체 4개"
        assert rows == ["이후 단계를 먼저 취소하세요", "", "", "이전 단계를 먼저 완료하세요"]
    finally:
        card.deleteLater()
        host.deleteLater()


def test_side_panel_checklist_tooltips_show_no_korean_in_english(app):
    with _language("en"):
        host, card = _process_card()
        try:
            progress, rows = _checklist_tooltips(card)
            assert progress == t("panel.checklist.progress_tooltip", "", done=2, total=4)
            assert "2" in progress and "4" in progress
            assert rows[0] == t("panel.checklist.locked_next", "")
            assert rows[3] == t("panel.checklist.locked_previous", "")
            leaked = [text for text in (progress, *rows) if HANGUL.search(text)]
            assert leaked == [], leaked
        finally:
            card.deleteLater()
            host.deleteLater()


def test_directive_badge_reads_its_key_and_widens_for_longer_text(app):
    from calendar_app.presentation.panels import side_panel_renderer

    def badge_of(header):
        return header.findChildren(QLabel)[0]

    header = side_panel_renderer._directive_group_header("Kim")
    try:
        badge = badge_of(header)
        assert badge.text() == "BY"
        assert badge.width() == 20
    finally:
        header.deleteLater()
    with _overlay({"panel.directive_receiver_badge": "PAR QUI"}):
        header = side_panel_renderer._directive_group_header("Kim")
        try:
            badge = badge_of(header)
            assert badge.text() == "PAR QUI"
            assert badge.width() >= badge.fontMetrics().horizontalAdvance("PAR QUI")
        finally:
            header.deleteLater()


# ── Focus mode (M8, L16) ──────────────────────────────────────────────────────


def _empty_focus_checklist():
    from calendar_app.presentation import focus_mode

    host = QWidget()
    layout = QVBoxLayout(host)
    focus_app = SimpleNamespace(settings=None, _focus_task_id=11, _focus_task_type="schedule")
    with patch.object(focus_mode.checklist_repo, "get_task_checklist_items", return_value=[]):
        focus_mode._build_focus_checklist_panel(focus_app, layout)
    return host


def test_focus_mode_empty_checklist_uses_its_own_key(app):
    host = _empty_focus_checklist()
    try:
        texts = _label_texts(host)
        assert "체크리스트 항목이 없습니다." in texts
        assert t("dialog.label_settings.none_to_load", "") not in texts
    finally:
        host.deleteLater()
    with _overlay({"focus.checklist_empty": "<empty checklist>"}):
        host = _empty_focus_checklist()
        try:
            assert "<empty checklist>" in _label_texts(host)
        finally:
            host.deleteLater()


def test_focus_mode_pomodoro_summary_passes_seconds(app):
    from calendar_app.presentation import focus_mode

    source = textwrap.dedent(inspect.getsource(focus_mode))
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "t"
        and node.args
        and getattr(node.args[0], "value", None) == "focus.pomodoro_summary"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert {keyword.arg for keyword in call.keywords} == {"sessions", "minutes", "seconds"}
    default = call.args[1].value
    assert "{seconds}" in default and HANGUL.search(default)


# ── Drag preview title (M6) ───────────────────────────────────────────────────


def _drag_titles(task_ids, task_map):
    from calendar_app.presentation import drag_drop_manager

    calls = []
    real_t = i18n_module.t

    def spy(key, default=None, **kwargs):
        value = real_t(key, default, **kwargs)
        calls.append((key, default, kwargs, value))
        return value

    with patch.object(i18n_module, "t", spy):
        drag_drop_manager.build_task_drag_pixmap(task_ids, task_map)
    return {key: (default, kwargs, value) for key, default, kwargs, value in calls}


def test_drag_preview_titles_use_keys_and_keep_korean(app):
    many = _drag_titles([1, 2, 3], {})
    assert many["drag.count_title"] == ("{count}개 일정", {"count": 3}, "3개 일정")
    untitled = _drag_titles([5], {5: {"name": ""}})
    assert untitled["drag.single_untitled"] == ("1개 일정", {}, "1개 일정")
    named = _drag_titles([5], {5: {"name": "Review"}})
    assert "drag.single_untitled" not in named


def test_drag_preview_titles_show_no_korean_in_english(app):
    with _language("en"):
        many = _drag_titles([1, 2, 3], {})
        untitled = _drag_titles([5], {})
    for key, result in (("drag.count_title", many), ("drag.single_untitled", untitled)):
        value = result[key][2]
        assert value and not HANGUL.search(value), (key, value)
    assert "3" in many["drag.count_title"][2]


def test_drag_preview_has_no_hangul_literal_outside_t_defaults():
    from calendar_app.presentation import drag_drop_manager

    tree = ast.parse(textwrap.dedent(inspect.getsource(drag_drop_manager.build_task_drag_pixmap)))
    defaults = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "t":
            defaults.update(id(sub) for arg in node.args[1:] for sub in ast.walk(arg))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and HANGUL.search(node.value)
        and id(node) not in defaults
    ]
    assert literals == []


# ── Alarm reminder checkboxes (H4) ────────────────────────────────────────────

_ALARM_KEYS = {
    10080: ("dialog.task.alarm_1w", "1주일 전"),
    1440: ("dialog.task.alarm_1d", "1일 전"),
    60: ("dialog.task.alarm_1h", "1시간 전"),
    10: ("dialog.task.alarm_10m", "10분 전"),
}


def _alarm_checks(tmp_path, monkeypatch):
    import PyQt6.QtCore

    from calendar_app.presentation.dialogs.task_dialog_base import BaseTaskDialog

    base_settings = PyQt6.QtCore.QSettings
    ini = str(tmp_path / "task_dialog.ini")

    class _TempSettings(base_settings):
        # The alarm defaults live in QSettings("DarkCalendar", "TaskDialog"); keep
        # the test off the real registry store.
        def __init__(self, *args, **kwargs):
            if args[:2] == ("DarkCalendar", "TaskDialog"):
                super().__init__(ini, base_settings.Format.IniFormat)
            else:
                super().__init__(*args, **kwargs)

    monkeypatch.setattr(PyQt6.QtCore, "QSettings", _TempSettings)

    class _AlarmHost(QWidget):
        _create_section = BaseTaskDialog._create_section
        _build_alarm_section = BaseTaskDialog._build_alarm_section
        _update_alarm_summary = BaseTaskDialog._update_alarm_summary
        _save_default_alarms = BaseTaskDialog._save_default_alarms

        def _ui_tokens(self):
            return {}

    host = _AlarmHost()
    section = host._build_alarm_section()
    section.setParent(host)
    return host, {minutes: box.text() for minutes, box in host.alarm_checks.items()}


def test_alarm_checkboxes_read_their_keys(app, tmp_path, monkeypatch):
    host, texts = _alarm_checks(tmp_path, monkeypatch)
    host.deleteLater()
    assert texts == {minutes: korean for minutes, (_key, korean) in _ALARM_KEYS.items()}

    marked = {key: f"<{key}>" for key, _korean in _ALARM_KEYS.values()}
    with _overlay(marked):
        host, texts = _alarm_checks(tmp_path, monkeypatch)
        host.deleteLater()
    assert texts == {minutes: f"<{key}>" for minutes, (key, _korean) in _ALARM_KEYS.items()}


def test_new_t_calls_keep_korean_defaults():
    """Every key this batch adds has a Korean default equal to the Korean UI text."""
    files = [
        "calendar_app/presentation/dialogs/pomodoro_settings_dialog.py",
        "calendar_app/presentation/widgets/overlay_manager_dialog.py",
        "calendar_app/presentation/dialogs/help_center_dialog.py",
        "calendar_app/presentation/panels/side_panel_renderer.py",
        "calendar_app/presentation/focus_mode.py",
        "calendar_app/presentation/drag_drop_manager.py",
    ]
    found = {}
    for name in files:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8", errors="strict"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "t"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in NEW_KEYS_EN
            ):
                found.setdefault(node.args[0].value, set()).add(node.args[1].value)
    assert set(found) == set(NEW_KEYS_EN)
    for key, defaults in found.items():
        assert len(defaults) == 1, (key, defaults)
    assert found["dialog.pomodoro_settings.run_mode"] == {"실행 모드"}
    assert found["panel.checklist.progress_tooltip"] == {"완료 {done}개 / 전체 {total}개"}
    assert found["drag.count_title"] == {"{count}개 일정"}
    assert found["common.toggle_on"] == {"ON"}
    assert found["common.toggle_off"] == {"OFF"}
