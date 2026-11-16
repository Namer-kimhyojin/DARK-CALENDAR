# -*- coding: utf-8 -*-
"""Shell texts (command palette, tray, restart and locale-file messages) come from t().

The command palette (Ctrl+K) used to show hard-coded English titles and subtitles in
every language, Korean included. The tray built its routine-settings label by
replacing "관리자" in a translated string, so outside Korean two tray items read the
same. A failed restart launch blamed state saving, and the locale-file validation
messages were literal English that also rejected valid partial overrides.

New keys reach the locale files in a later integration step. Until then English
lookups of those keys return the Korean default, so the English checks here add the
proposed English values to the loaded translations first.
"""

import ast
import json
from pathlib import Path
import re
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.domain import task_constants
from calendar_app.infrastructure import i18n as i18n_module
from calendar_app.infrastructure.i18n import i18n, t
from calendar_app.infrastructure.runtime import infra_wiring
from calendar_app.presentation.main_window import action_handlers, window_ui_actions
from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin
from calendar_app.presentation.widgets import command_palette_runtime as palette_module

_APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")

# English values proposed for the keys this change adds.
NEW_KEYS_EN = {
    "palette.theme_system": "Theme: Use System Default",
    "palette.desc.work_management": "Opens the combined work management window.",
    "palette.desc.directive_status": "Opens the directive tab directly.",
    "palette.recent": "Recent",
    "palette.recent_subtitle": "Recent - {subtitle}",
    "palette.create_schedule": "Create Schedule: {title}",
    "palette.default_time": "{time} (default)",
    "palette.record_type.schedule": "Schedule",
    "palette.record_type.routine": "Routine",
    "palette.record_type.directive": "Directive",
    "tray.routine_settings": "⚙️ Routine Settings",
    "system_msg.restart_launch_failed": (
        "The app could not restart automatically. Please start it again yourself."
    ),
    "menu.locale_validate_empty_code": "The language code is empty.",
    "menu.locale_validate_no_file": "No user override file exists: {path}",
    "menu.locale_validate_parse_failed": "Could not read the JSON: {error}",
    "menu.locale_validate_not_object": "The top-level JSON of a locale file must be an object.",
    "menu.locale_validate_passed": "Validation passed: {path}",
    "menu.locale_validate_missing_keys": (
        "{count} top-level keys are not overridden and use the bundled translation: {keys}"
    ),
}

# Titles and subtitles the palette used to show in every language.
OLD_ENGLISH_LITERALS = {
    "Go To Today",
    "Previous Date",
    "Next Date",
    "Pause Or Resume Focus",
    "Focus Session Log",
    "Pomodoro Settings",
    "Widget Manager",
    "Open Schedule Widget Panel",
    "Open Work Widget Panel",
    "Open All Widget Panels",
    "Theme: Use System Default",
    "Font Settings",
    "Toggle Desktop Lock",
    "Toggle Magnet Mode",
    "Restore Window Position",
    "Move To Next Monitor",
    "Create a new schedule or calendar item",
    "Create a recurring routine",
    "Create a directive or request item",
    "Open the combined work management dialog",
    "Open the routine tab directly",
    "Open the directive tab directly",
    "Recent",
}

_HOST_METHODS = {
    "open_task_dialog",
    "open_routine_add_dialog",
    "open_directive_dialog",
    "open_checklist_manager",
    "open_work_management_dialog",
    "jump_to_today",
    "prev_day",
    "next_day",
    "toggle_focus_mode",
    "toggle_focus_pause",
    "open_focus_log_dialog",
    "open_pomodoro_settings_dialog",
    "toggle_top_bar",
    "toggle_navigation_rail",
    "toggle_calendar_toolbar",
    "toggle_fullscreen",
    "toggle_widget_mode_panel",
    "open_widget_manager",
    "open_schedule_widget_panel",
    "open_work_widget_panel",
    "open_all_widget_panels",
    "change_text_theme",
    "set_system_default_theme",
    "open_panel_background_color_dialog",
    "open_label_settings_dialog",
    "open_away_settings_dialog",
    "open_font_settings_dialog",
    "sync_calendars",
    "open_calendar_sync_hub",
    "open_calendar_sync_issues",
    "apply_layout_preset",
    "toggle_lock_mode",
    "toggle_magnet_mode",
    "toggle_idle_lock",
    "restore_window_to_safe_area",
    "move_to_next_monitor",
    "toggle_autostart",
    "open_language_settings_dialog",
    "show_shortcut_guide",
    "request_app_exit",
}


class _PaletteHost(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.preset_manager = object()

    def __getattr__(self, name):
        if name in _HOST_METHODS:
            return lambda *args, **kwargs: None
        raise AttributeError(name)


@pytest.fixture
def host(tmp_path):
    widget = _PaletteHost(QSettings(str(tmp_path / "palette.ini"), QSettings.Format.IniFormat))
    yield widget
    widget.deleteLater()


def _palette(host):
    palette = palette_module.CommandPalette(parent=host)
    palette.hide()
    return palette


@pytest.fixture
def english():
    """Switch the UI to English in-process and add the proposed values of new keys."""
    store = QSettings("kimhyojin", "Dark Calendar")  # the isolated store from conftest
    original = store.value("language")
    store.setValue("language", "en")
    i18n._load_translations()
    try:
        assert i18n.lang == "en"
        for key, value in NEW_KEYS_EN.items():
            if i18n._resolve_from(i18n.translations, key) is None:
                i18n.translations[key] = value
        # Status texts are translated once at import; a language change restarts the app.
        statuses = {key: t(f"status.{key}") for key in task_constants.STATUS_TEXT}
        with patch.dict(task_constants.STATUS_TEXT, statuses):
            yield
    finally:
        if original is None:
            store.remove("language")
        else:
            store.setValue("language", original)
        i18n._load_translations()


def _recording_t(calls):
    def recording_t(key, default=None, **kwargs):
        calls.append((key, default, kwargs))
        return f"<{key}>"

    return recording_t


def _shown_texts(entry):
    return [text for text in (entry["title"], entry.get("subtitle", "")) if text]


# --- M1: command palette --------------------------------------------------------------


def test_every_palette_command_title_is_looked_up_through_t(host):
    calls = []
    with patch.object(palette_module, "t", _recording_t(calls)):
        palette = _palette(host)
        commands = list(palette._commands)
    try:
        assert len(commands) >= 40
        for entry in commands:
            assert re.fullmatch(r"<[a-z0-9_.]+>", entry["title"]), entry
        titles = {entry["title"] for entry in commands}
        for key in (
            "shortcut.entries.today.label",
            "shortcut.entries.focus_pause.label",
            "shortcut.entries.lock_mode.label",
            "shortcut.entries.monitor_right.label",
            "labels.widget_manager",
            "widget_mode.open_all",
            "palette.theme_system",
            "dialog.font.title",
        ):
            assert f"<{key}>" in titles
        assert {f"<shortcut.entries.layout_{n}.label>" for n in range(1, 6)} <= titles
        # Every palette lookup keeps a Korean default.
        for key, default, _kwargs in calls:
            if key.startswith(("palette.", "shortcut.", "menu.", "widget_mode.")):
                assert default and HANGUL.search(default), (key, default)
    finally:
        palette.deleteLater()


def test_literal_subtitles_no_longer_override_the_translated_help_text(host):
    palette = _palette(host)
    try:
        help_text = {
            entry["id"]: entry["description_ko"] for entry in palette._shortcut_meta.values()
        }
        by_title = {entry["title"]: entry for entry in palette._commands}
        cases = (
            ("menu.add_schedule", "new_schedule"),
            ("menu.add_routine", "new_routine"),
            ("menu.add_directive", "new_directive"),
            ("menu.routine_status", "routine_mgr"),
        )
        for title_key, shortcut_id in cases:
            assert by_title[t(title_key)]["subtitle"] == help_text[shortcut_id]
    finally:
        palette.deleteLater()


def test_korean_palette_shows_korean_titles_and_subtitles(host):
    assert i18n.lang == "ko"
    host.settings.setValue(
        palette_module._RECENT_COMMANDS_KEY, json.dumps(["jump_to_today", "open_widget_manager"])
    )
    palette = _palette(host)
    try:
        for entry in palette._commands:
            for text in _shown_texts(entry):
                assert HANGUL.search(text), entry
                assert text not in OLD_ENGLISH_LITERALS
        by_title = {entry["title"]: entry for entry in palette._commands}
        assert "오늘로 이동" in by_title
        assert "레이아웃 프리셋 3" in by_title
        assert by_title["위젯 관리자"]["subtitle"] == ""

        recent = palette._build_default_results()[:2]
        assert [entry["id"] for entry in recent] == ["jump_to_today", "open_widget_manager"]
        assert recent[0]["subtitle"] == "최근 - " + t("shortcut.entries.today.description")
        assert recent[1]["subtitle"] == "최근"

        [entry], _preview = palette._build_create_entries("tomorrow planning", "create", False)
        assert entry["title"] == "일정 만들기: planning"
        assert entry["subtitle"].startswith("새 일정: [planning] - ")
        assert entry["subtitle"].endswith(" 09:00 (기본값)")

        task = palette._task_record_entry(
            {
                "id": 3,
                "type": "routine",
                "name": "",
                "deadline": "2026-04-04 10:00:00",
                "status": "in_progress",
            },
            1,
        )
        assert task["title"] == "(제목 없음)"
        assert task["subtitle"] == "일반업무 - 2026-04-04 10:00 - 진행중"
        directive = palette._directive_record_entry(
            {"id": 4, "content": "보고", "receiver_name": "Team", "status": "done"}, 1
        )
        assert directive["subtitle"] == "지시사항 - Team - 완료"
    finally:
        palette.deleteLater()


def test_english_palette_shows_no_korean(host, english):
    host.settings.setValue(
        palette_module._RECENT_COMMANDS_KEY, json.dumps(["jump_to_today", "open_widget_manager"])
    )
    palette = _palette(host)
    try:
        for entry in palette._commands:
            for text in _shown_texts(entry):
                assert not HANGUL.search(text), entry
        titles = {entry["title"] for entry in palette._commands}
        assert {"Jump to today", "Layout preset 2", "Theme: Use System Default"} <= titles

        recent = palette._build_default_results()[:2]
        assert recent[0]["subtitle"] == "Recent - Instantly moves the selected date to today."
        assert recent[1]["subtitle"] == "Recent"

        [entry], _preview = palette._build_create_entries("tomorrow planning", "create", False)
        assert entry["title"] == "Create Schedule: planning"
        assert entry["subtitle"].endswith(" 09:00 (default)")
        assert not HANGUL.search(entry["subtitle"])

        task = palette._task_record_entry(
            {
                "id": 3,
                "type": "schedule",
                "name": "",
                "deadline": "2026-04-04 10:00:00",
                "status": "pending",
            },
            1,
        )
        assert task["title"] == "(No Title)"
        assert task["subtitle"] == "Schedule - 2026-04-04 10:00 - Pending"
        directive = palette._directive_record_entry(
            {"id": 4, "content": "Report", "receiver_name": "Team", "status": "canceled"}, 1
        )
        assert directive["subtitle"] == "Directive - Team - Canceled"
    finally:
        palette.deleteLater()


_BUILDERS = (
    "_command_entry",
    "_build_command_entries",
    "_build_default_results",
    "_task_record_entry",
    "_directive_record_entry",
    "_build_create_entries",
)


def _is_t_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"


def _shown_values(node):
    """Expressions that become an entry title or subtitle in this AST node."""
    if isinstance(node, ast.keyword) and node.arg in {"title", "subtitle"}:
        return [node.value]
    if isinstance(node, ast.Dict):
        return [
            value
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and key.value in {"title", "subtitle"}
        ]
    if isinstance(node, ast.Assign):
        return [
            node.value
            for target in node.targets
            if isinstance(target, ast.Subscript)
            and isinstance(target.slice, ast.Constant)
            and target.slice.value in {"title", "subtitle"}
        ]
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "_command_entry":
        return node.args[1:2]  # the positional title
    return []


def test_palette_entry_builders_keep_no_title_or_subtitle_literals():
    tree = ast.parse(Path(palette_module.__file__).read_text(encoding="utf-8", errors="strict"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in _BUILDERS
    ]
    assert {node.name for node in functions} == set(_BUILDERS)
    offenders = []
    for function in functions:
        # Hangul may stay as a t() default or a search keyword (keywords are not shown).
        allowed = {
            id(child)
            for node in ast.walk(function)
            if _is_t_call(node) or (isinstance(node, ast.keyword) and node.arg == "keywords")
            for child in ast.walk(node)
        }
        for node in ast.walk(function):
            for value in _shown_values(node):
                if isinstance(value, (ast.Constant, ast.JoinedStr)):
                    offenders.append((function.name, value.lineno, ast.unparse(value)))
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and HANGUL.search(node.value)
                and id(node) not in allowed
            ):
                offenders.append((function.name, node.lineno, node.value))
    assert offenders == []


# --- M4: tray -------------------------------------------------------------------------


def _tray_actions():
    recorded = []

    def fake_create_action(app, label, handler, shortcut_id=None, parent_menu=None):
        recorded.append((label, handler, shortcut_id))
        return MagicMock()

    app = MagicMock()
    with (
        patch.object(infra_wiring, "QSystemTrayIcon") as tray_class,
        patch.object(infra_wiring, "_create_action", fake_create_action),
        patch.object(infra_wiring, "_create_tray_autostart_action"),
    ):
        tray_class.isSystemTrayAvailable.return_value = True
        infra_wiring.init_tray_icon(app)
    labels = [label for label, _handler, _shortcut in recorded]
    settings_index = next(
        index
        for index, (_label, handler, _shortcut) in enumerate(recorded)
        if handler is app.open_routine_management_dialog
    )
    return labels[settings_index - 1], labels[settings_index]


def test_korean_tray_routine_items_are_unchanged():
    assert i18n.lang == "ko"
    manager, settings = _tray_actions()
    assert manager == "⚙️ 일반업무 관리자"
    assert settings == "⚙️ 일반업무 설정"


def test_english_tray_routine_items_differ(english):
    manager, settings = _tray_actions()
    assert manager == t("tray.routine_manager")
    assert settings == t("tray.routine_settings")
    assert manager != settings
    assert not HANGUL.search(manager + settings)


_SHELL_FILES = (
    "calendar_app/infrastructure/runtime/infra_wiring.py",
    "calendar_app/presentation/main_window/action_handlers.py",
    "calendar_app/presentation/main_window/window_ui_actions.py",
    "calendar_app/presentation/widgets/command_palette_runtime.py",
    "calendar_app/infrastructure/i18n.py",
)
_TEXT_EDITS = {"replace", "split", "rsplit", "partition", "startswith", "endswith", "find"}


@pytest.mark.parametrize("relative", _SHELL_FILES)
def test_shell_code_never_edits_or_matches_translated_text(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8", errors="strict"))
    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _TEXT_EDITS
            and _is_t_call(node.func.value)
        ):
            offenders.append((node.lineno, ast.unparse(node)[:80]))
        if isinstance(node, ast.Compare) and any(
            _is_t_call(part) for part in (node.left, *node.comparators)
        ):
            offenders.append((node.lineno, ast.unparse(node)[:80]))
    assert offenders == []


# --- L15: restart launch failure --------------------------------------------------------

_LAUNCH_FAILED_KO = "앱을 자동으로 다시 시작하지 못했습니다. 앱을 직접 다시 실행해 주세요."
_SAVE_FAILED_KO = "앱 상태를 저장하지 못해 자동 재시작을 취소했습니다. 다시 시도해 주세요."


class _Settings:
    def __init__(self):
        self.values = {"language": "ko"}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):  # noqa: N802 - QSettings API
        self.values[key] = value

    def sync(self):
        pass


class _RestartHost:
    def __init__(self):
        self.settings = _Settings()
        self._exit_requested = False

    def shutdown_background_workers(self, wait_ms=500):
        raise AssertionError("the app must keep running when the restart fails")

    def close(self):
        raise AssertionError("the app must keep running when the restart fails")

    def set_language(self, lang_code):
        ActionHandlersMixin.set_language(self, lang_code)

    def restart_for_locale_tools(self):
        ActionHandlersMixin._restart_application_for_locale_tools(self)


def _run_restart(action, *, flushed, recorder=None):
    warnings = []
    patches = [
        patch.object(action_handlers.QMessageBox, "information"),
        patch.object(
            action_handlers.QMessageBox,
            "warning",
            side_effect=lambda _parent, _title, text, *rest: warnings.append(text),
        ),
        patch(
            "calendar_app.presentation.main_window.window_restore_helpers.flush_window_layout",
            return_value=flushed,
        ),
        patch("PyQt6.QtCore.QProcess.startDetached", return_value=(False, 0)),
    ]
    if recorder is not None:
        patches += [
            patch.object(action_handlers, "t", recorder),
            patch.object(i18n_module, "t", recorder),
        ]
    for item in patches:
        item.start()
    try:
        action(_RestartHost())
    finally:
        for item in reversed(patches):
            item.stop()
    return warnings


@pytest.mark.parametrize(
    "action",
    [lambda host: host.set_language("en"), lambda host: host.restart_for_locale_tools()],
    ids=["language", "locale_tools"],
)
def test_failed_launch_reports_the_launch_not_state_saving(action):
    assert _run_restart(action, flushed=True) == [_LAUNCH_FAILED_KO]
    assert _run_restart(action, flushed=False) == [_SAVE_FAILED_KO]

    calls = []
    assert _run_restart(action, flushed=True, recorder=_recording_t(calls)) == [
        "<system_msg.restart_launch_failed>"
    ]
    assert ("system_msg.restart_launch_failed", _LAUNCH_FAILED_KO, {}) in calls
    assert all(key != "system_msg.restart_failed" for key, _default, _kwargs in calls)


# --- L5: locale-file validation ---------------------------------------------------------


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", errors="strict")


@pytest.fixture
def locale_dirs(tmp_path):
    bundle, user = tmp_path / "bundles", tmp_path / "user"
    bundle.mkdir()
    user.mkdir()
    _write_json(bundle / "ja.json", {"meta": {"language_name": "日本語"}, "a": "A", "b": "B"})
    with (
        patch.object(i18n_module, "_BUNDLED_LOCALES_DIR", bundle),
        patch.object(i18n_module, "get_user_locales_dir", lambda create=False: user),
    ):
        yield user


def test_partial_override_is_valid_and_reports_missing_keys(locale_dirs):
    _write_json(locale_dirs / "ja.json", {"a": "上書き"})
    ok, message = i18n_module.validate_user_locale_file("ja")
    assert ok is True
    path = locale_dirs / "ja.json"
    assert message == (
        f"검증을 통과했습니다: {path}\n"
        "오버라이드하지 않은 최상위 키 2개는 기본 번역을 사용합니다: b, meta"
    )


def test_full_override_passes_without_missing_key_note(locale_dirs):
    _write_json(locale_dirs / "ja.json", {"meta": {}, "a": "1", "b": "2", "extra": "3"})
    ok, message = i18n_module.validate_user_locale_file("ja")
    assert (ok, message) == (True, f"검증을 통과했습니다: {locale_dirs / 'ja.json'}")


def test_validation_failures_and_missing_file(locale_dirs):
    assert i18n_module.validate_user_locale_file(" ") == (False, "언어 코드가 비어 있습니다.")
    ok, message = i18n_module.validate_user_locale_file("ja")
    assert (ok, message) == (True, f"사용자 오버라이드 파일이 없습니다: {locale_dirs / 'ja.json'}")

    (locale_dirs / "ja.json").write_text("{broken", encoding="utf-8", errors="strict")
    ok, message = i18n_module.validate_user_locale_file("ja")
    assert ok is False and message.startswith("JSON을 읽지 못했습니다: ")

    _write_json(locale_dirs / "ja.json", ["not", "an", "object"])
    assert i18n_module.validate_user_locale_file("ja") == (
        False,
        "로케일 파일의 최상위 JSON은 객체여야 합니다.",
    )


def test_validation_messages_come_from_t(locale_dirs):
    calls = []
    with patch.object(i18n_module, "t", _recording_t(calls)):
        results = [i18n_module.validate_user_locale_file("")]
        results.append(i18n_module.validate_user_locale_file("ja"))
        (locale_dirs / "ja.json").write_text("{broken", encoding="utf-8", errors="strict")
        results.append(i18n_module.validate_user_locale_file("ja"))
        _write_json(locale_dirs / "ja.json", [])
        results.append(i18n_module.validate_user_locale_file("ja"))
        _write_json(locale_dirs / "ja.json", {"a": "x"})
        results.append(i18n_module.validate_user_locale_file("ja"))
    assert results == [
        (False, "<menu.locale_validate_empty_code>"),
        (True, "<menu.locale_validate_no_file>"),
        (False, "<menu.locale_validate_parse_failed>"),
        (False, "<menu.locale_validate_not_object>"),
        (True, "<menu.locale_validate_passed>\n<menu.locale_validate_missing_keys>"),
    ]
    assert [key for key, _default, _kwargs in calls] == [
        "menu.locale_validate_empty_code",
        "menu.locale_validate_no_file",
        "menu.locale_validate_parse_failed",
        "menu.locale_validate_not_object",
        "menu.locale_validate_passed",
        "menu.locale_validate_missing_keys",
    ]
    for _key, default, _kwargs in calls:
        assert HANGUL.search(default)
    assert calls[-1][2] == {"count": 2, "keys": "b, meta"}


def test_english_validation_messages_show_no_korean(english, locale_dirs):
    # english first: it loads the real bundles before locale_dirs swaps the folders.
    _write_json(locale_dirs / "ja.json", {"a": "x"})
    ok, message = i18n_module.validate_user_locale_file("ja")
    assert ok is True
    assert not HANGUL.search(message)
    assert message.endswith("use the bundled translation: b, meta")


# --- M9: D-Day toast --------------------------------------------------------------------


class _DdayWidget:
    def __init__(self):
        self.values = {}

    def _set(self, key, value):
        self.values[key] = value

    def _refresh_face(self):
        pass

    def _apply_and_resize(self):
        pass

    def center_on_owner(self):
        pass


class _DdayHost:
    def __init__(self):
        self.widget = _DdayWidget()
        self.toasts = []
        self.overlay_manager = MagicMock()
        self.overlay_manager.add_instance.return_value = "dday_0"
        self.overlay_manager.get_widget.return_value = self.widget

    def init_overlay_manager(self):
        pass

    def show_toast(self, title, message):
        self.toasts.append((title, message))


def test_dday_toast_passes_the_task_name_to_a_placeholder():
    host = _DdayHost()
    calls = []
    with (
        patch(
            "calendar_app.infrastructure.db.task_repo.get_unified_task",
            return_value={"name": "Launch", "deadline": "2026-12-01 09:00:00"},
        ),
        patch.object(window_ui_actions, "t", _recording_t(calls)),
    ):
        MainWindowUiActionsMixin.create_dday_widget_for_task(host, 7)
    assert host.toasts == [("<widget.dday.toast_title>", "<widget.dday.toast_created>")]
    assert (
        "widget.dday.toast_created",
        "D-Day 위젯이 생성되었습니다: {name}",
        {"name": "Launch"},
    ) in calls
    assert host.widget.values["dd_label"] == "Launch"
