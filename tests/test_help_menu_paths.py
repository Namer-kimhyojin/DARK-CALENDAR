# -*- coding: utf-8 -*-
"""Menu paths in the help center and setup messages come from the real menu labels.

The shortcut cards used to show hand-written paths ("시스템 > ...", "작업 > ...",
"View > ...") that drifted whenever a menu was renamed, and the Google setup
messages pointed at a "Calendar Integration Settings" menu that no longer exists.
A path is now the tuple of i18n keys the menu builders pass to t(), rendered from
the active locale. These tests follow each top-bar path through the menus as they
are built, and tie each context-menu path to the modules that build those menus.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox
import pytest
from scripts.i18n_sync import flatten_locale, load_locale

from calendar_app.infrastructure.i18n import I18nManager, i18n, t
from calendar_app.infrastructure.runtime import system_manager
from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    SHORTCUT_MENU_PATHS,
    SHORTCUTS,
    get_shortcut_guide_entry,
)
from calendar_app.infrastructure.runtime.menu_paths import (
    GOOGLE_SYNC_SETUP_PATH,
    SELECTED_ITEM_MENU_KEY,
    TOP_MENU_BUTTON_KEYS,
    format_menu_path,
    menu_label,
)
from calendar_app.presentation.main_window import action_handlers_gcal, top_bar_builder
from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.presentation.main_window.top_menus.display_menu import build_display_menu
from calendar_app.presentation.main_window.top_menus.register_menu import build_register_menu
from calendar_app.presentation.main_window.top_menus.system_menu import build_system_menu
from calendar_app.presentation.main_window.top_menus.work_menu import build_work_menu
from calendar_app.shared.icon_map import strip_leading_emoji

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "calendar_app"
LOCALES = ROOT / "locales"
TOP_MENUS = APP / "presentation" / "main_window" / "top_menus"

# Top-bar button key -> the module that builds the button and its menu.
TOP_MENU_BUILDERS = {
    "menu.register_btn": TOP_MENUS / "register_menu.py",
    "menu.work_btn": TOP_MENUS / "work_menu.py",
    "menu.display_btn": TOP_MENUS / "display_menu.py",
    "menu.widgets": TOP_MENUS / "widgets_menu.py",
    "menu.system": TOP_MENUS / "system_menu.py",
}
# Shortcuts whose menu does not hang off a top-bar button.
OTHER_ROOTS = {
    "calendar_print": "panel.main_calendar",
    "color_assign": SELECTED_ITEM_MENU_KEY,
}
# Root keys that name where a menu opens instead of labelling a menu item.
NON_MENU_KEYS = {SELECTED_ITEM_MENU_KEY}
# Context menus are built inside event handlers, so their paths are checked against
# the modules that build them. Each inner list is one menu: its modules together use
# every key of the path.
CONTEXT_MENU_BUILDERS = {
    # The calendar dock's title, then the options menu on its toolbar.
    "calendar_print": [
        [
            APP / "presentation" / "main_window" / "dock_sections" / "left_center_docks.py",
            APP / "presentation" / "calendar" / "month_renderer.py",
        ]
    ],
    # The selection applies from the month calendar and from the side panels alike.
    "color_assign": [
        [APP / "presentation" / "widgets" / "ui_components.py"],
        [APP / "presentation" / "panels" / "side_panel_renderer.py"],
    ],
}
# Slots the top-bar menu builders connect. The menus are built, never triggered.
TOP_MENU_HOST_SLOTS = (
    "open_task_dialog",
    "open_directive_dialog",
    "open_routine_add_dialog",
    "open_work_management_dialog",
    "open_checklist_manager",
    "toggle_view_mode",
    "set_top_bar_auto_hide",
    "set_calendar_toolbar_visible",
    "toggle_fullscreen",
    "toggle_focus_mode",
    "toggle_widget_mode_panel",
    "toggle_idle_lock",
    "change_text_theme",
    "set_system_default_theme",
    "open_panel_background_color_dialog",
    "_sync_top_bar_visibility",
    "toggle_autostart",
    "open_label_settings_dialog",
    "open_away_settings_dialog",
    "open_daily_summary_dialog",
    "sync_calendars",
    "open_calendar_sync_hub",
    "open_calendar_management",
    "open_calendar_sync_issues",
    "show_shortcut_guide",
    "request_app_exit",
    "open_locale_override_folder",
    "open_current_locale_file",
    "validate_current_locale_override",
    "reset_current_locale_override",
)
GOOGLE_SETUP_BUILDERS = [
    TOP_MENUS / "system_menu.py",
    APP / "presentation" / "dialogs" / "calendar_sync_hub.py",
]
GOOGLE_SETUP_KEYS = (
    "gcal.setup_disabled_guide",
    "gcal.setup_needed_msg",
    "gcal.guidance.auth",
)


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    yield QApplication.instance() or QApplication([])


def _locale(code):
    return flatten_locale(load_locale(LOCALES / f"{code}.json"))


def _literal_t_keys(path):
    """Keys passed as a string literal to t(), including calls inside f-strings."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "t"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def _switch_language(code):
    # conftest redirects this store to a temporary INI file.
    QSettings("kimhyojin", "Dark Calendar").setValue("language", code)
    I18nManager()._load_translations()


@pytest.fixture
def ui_language():
    previous = i18n.lang
    try:
        yield _switch_language
    finally:
        _switch_language(previous)


@pytest.fixture
def top_menus(tmp_path):
    """Build the real top-bar menus on a stub window; returns {button label: QMenu}."""
    host = QMainWindow()
    host.settings = QSettings(str(tmp_path / "menus.ini"), QSettings.Format.IniFormat)
    for name in TOP_MENU_HOST_SLOTS:
        setattr(host, name, Mock())
    host._calendar_toolbar_visible_setting = lambda: True
    host.preset_manager = SimpleNamespace(
        update_load_menu=Mock(),
        update_save_menu=Mock(),
        update_rename_menu=Mock(),
        update_delete_menu=Mock(),
    )

    def build():
        bar = QHBoxLayout()
        with patch.object(system_manager, "is_autostart_enabled", return_value=False):
            for builder in (
                build_register_menu,
                build_work_menu,
                build_display_menu,
                build_system_menu,
            ):
                builder(host, bar, "", "")
        # The quick navigation rail adds its own toggle to Screen > View and Window.
        top_bar_builder._setup_navigation_rail(host, {"navigation_rail": ""}, "#f4f7fb", "#efac63")
        buttons = (host.add_menu_btn, host.view_menu_btn, host.display_menu_btn, host.sys_menu_btn)
        return {button.text().strip(): button.menu() for button in buttons}

    yield build
    host.close()
    host.deleteLater()


def _shown_label(action):
    """An action's label as its menu shows it, without the shortcut column."""
    text = strip_leading_emoji(action.text().split("\t", 1)[0].replace("&&", "&")).strip()
    for suffix in ("...", "…"):
        text = text.removesuffix(suffix)
    return text.strip()


def _follow_menu_path(menus, keys):
    """Open every submenu a path names and find its last item, or fail where it breaks."""
    menu = menus.get(menu_label(keys[0]))
    assert menu is not None, (keys, sorted(menus))
    for step, key in enumerate(keys[1:], start=2):
        shown = [action for action in menu.actions() if not action.isSeparator()]
        found = [action for action in shown if _shown_label(action) == menu_label(key)]
        assert found, (keys, key, [_shown_label(action) for action in shown])
        if step < len(keys):
            menu = found[0].menu()
            assert menu is not None, (keys, key, "is not a submenu")


def _all_paths():
    return {**SHORTCUT_MENU_PATHS, "<google setup>": GOOGLE_SYNC_SETUP_PATH}


def test_menu_paths_belong_to_real_shortcuts():
    shortcut_ids = {item["id"] for item in SHORTCUTS}
    assert set(SHORTCUT_MENU_PATHS) <= shortcut_ids
    assert all(len(keys) >= 2 for keys in _all_paths().values())


@pytest.mark.parametrize("code", ["ko", "en"])
def test_every_path_key_exists_in_the_source_locales(code):
    data = _locale(code)
    missing = sorted(
        {
            key
            for keys in _all_paths().values()
            for key in keys
            if not str(data.get(key) or "").strip()
        }
    )
    assert not missing


def test_each_path_starts_at_a_top_bar_button_or_a_declared_root():
    for shortcut_id, keys in SHORTCUT_MENU_PATHS.items():
        expected = OTHER_ROOTS.get(shortcut_id)
        if expected is None:
            assert keys[0] in TOP_MENU_BUTTON_KEYS, shortcut_id
        else:
            assert keys[0] == expected, shortcut_id
    assert GOOGLE_SYNC_SETUP_PATH[0] in TOP_MENU_BUTTON_KEYS


def test_top_bar_keys_name_the_button_each_menu_module_builds():
    assert set(TOP_MENU_BUILDERS) == set(TOP_MENU_BUTTON_KEYS)
    for key, builder in TOP_MENU_BUILDERS.items():
        assert key in _literal_t_keys(builder), (key, builder.name)
        # The path shows the button the way the top bar labels it.
        assert menu_label(key) == format_top_menu_button_text(t(key)).strip()


@pytest.mark.parametrize("code", ["ko", "en"])
def test_top_bar_paths_follow_the_built_menus(ui_language, top_menus, code):
    # Labels are read when a menu is built, so switch the language first.
    ui_language(code)
    menus = top_menus()
    top_bar_paths = {
        shortcut_id: keys
        for shortcut_id, keys in SHORTCUT_MENU_PATHS.items()
        if shortcut_id not in OTHER_ROOTS
    }
    assert top_bar_paths
    for shortcut_id, keys in sorted(top_bar_paths.items()):
        try:
            _follow_menu_path(menus, keys)
        except AssertionError as error:
            raise AssertionError(f"{shortcut_id}: {error}") from None
    # Settings > Calendars and sync > the hub entry; the last step is a tab in the hub.
    _follow_menu_path(menus, GOOGLE_SYNC_SETUP_PATH[:3])


def test_every_context_menu_path_has_its_builders():
    assert set(CONTEXT_MENU_BUILDERS) == set(OTHER_ROOTS)


@pytest.mark.parametrize("shortcut_id", sorted(CONTEXT_MENU_BUILDERS))
def test_context_menu_path_keys_are_the_keys_each_menu_uses(shortcut_id):
    keys = [key for key in SHORTCUT_MENU_PATHS[shortcut_id] if key not in NON_MENU_KEYS]
    for builders in CONTEXT_MENU_BUILDERS[shortcut_id]:
        used = set().union(*(_literal_t_keys(path) for path in builders))
        missing = [key for key in keys if key not in used]
        assert not missing, (shortcut_id, missing, [path.name for path in builders])


def test_google_setup_path_keys_are_the_keys_the_menu_and_hub_use():
    used = set().union(*(_literal_t_keys(path) for path in GOOGLE_SETUP_BUILDERS))
    assert [key for key in GOOGLE_SYNC_SETUP_PATH if key not in used] == []


@pytest.mark.parametrize("code", ["ko", "en"])
def test_menu_backed_shortcuts_have_no_hand_written_path(code):
    data = _locale(code)
    for item in SHORTCUTS:
        key = f"shortcut.entries.{item['id']}.menu_path"
        if item["id"] in SHORTCUT_MENU_PATHS:
            assert key not in data, key
        else:
            # What is left is a category such as "Navigation", never a menu path.
            assert str(data.get(key) or "").strip(), key
            assert ">" not in data[key], (key, data[key])


def test_rendered_korean_paths_match_the_real_menus(ui_language):
    ui_language("ko")
    expected = {
        "checklist": "업무 > 체크리스트 관리",
        "help": "설정 > 단축키 안내",
        "routine_mgr": "업무 > 일반업무 현황",
        "focus_mode": "화면 > 집중 및 잠금 > 초집중 모드",
        "cal_toolbar": "화면 > 화면 및 창 > 캘린더 기능바 표시/숨기기",
        "calendar_print": "메인 캘린더 > 옵션 > 인쇄",
        "sync_gcal": "설정 > 캘린더 및 동기화 > 연결된 모든 캘린더 동기화",
    }
    for shortcut_id, path in expected.items():
        assert get_shortcut_guide_entry(shortcut_id)["menu_path_ko"] == path, shortcut_id


def test_rendered_english_paths_use_the_screen_button(ui_language):
    ui_language("en")
    assert get_shortcut_guide_entry("focus_mode")["menu_path_ko"] == (
        "Screen > Focus and Lock > Focus Mode"
    )
    assert get_shortcut_guide_entry("help")["menu_path_ko"] == "Settings > Shortcut Guide"
    for shortcut_id in SHORTCUT_MENU_PATHS:
        path = get_shortcut_guide_entry(shortcut_id)["menu_path_ko"]
        assert not path.startswith("View >"), (shortcut_id, path)


def test_category_entries_keep_their_translated_text(ui_language):
    ui_language("ko")
    assert get_shortcut_guide_entry("today")["menu_path_ko"] == "탐색"
    assert get_shortcut_guide_entry("lock_mode")["menu_path_ko"] == "상단 바 버튼"


def _setup_message(monkeypatch, *, disabled):
    information = Mock()
    monkeypatch.setattr(QMessageBox, "information", information)
    GCalActionsMixin.notify_gcal_setup_needed(Mock(), disabled=disabled)
    return information.call_args.args[2]


@pytest.mark.parametrize(
    ("code", "path"),
    [
        ("ko", "설정 > 캘린더 및 동기화 > 캘린더 · 계정 및 동기화 > 연결 및 구독"),
        (
            "en",
            "Settings > Calendars and sync > Calendars / accounts and synchronization"
            " > Connections and subscriptions",
        ),
    ],
)
def test_google_setup_messages_show_the_live_path(ui_language, monkeypatch, code, path):
    ui_language(code)
    assert format_menu_path(GOOGLE_SYNC_SETUP_PATH) == path
    for disabled in (True, False):
        message = _setup_message(monkeypatch, disabled=disabled)
        assert path in message
        assert "{path}" not in message
        assert "시스템 >" not in message and "System >" not in message
        assert "Calendar Integration" not in message and "캘린더 통합 설정" not in message
    guidance = t("gcal.guidance.auth", path=path)
    assert path in guidance and "{path}" not in guidance


@pytest.mark.parametrize(
    ("sync", "saved_sign_in", "names_card"),
    [
        # Never connected: the Google card waits in the collapsed service list.
        (None, False, True),
        (SimpleNamespace(is_authenticated=False), False, True),
        # A paused account keeps its card among the active services.
        (None, True, False),
        (SimpleNamespace(is_authenticated=True), False, False),
    ],
)
def test_disabled_google_message_names_the_card_until_an_account_exists(
    monkeypatch, sync, saved_sign_in, names_card
):
    information = Mock()
    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(action_handlers_gcal.os.path, "exists", lambda _path: saved_sign_in)
    GCalActionsMixin.notify_gcal_setup_needed(SimpleNamespace(gcal_sync=sync), disabled=True)
    message = information.call_args.args[2]
    guide = t("gcal.setup_disabled_guide", path=format_menu_path(GOOGLE_SYNC_SETUP_PATH))
    assert message.startswith(guide)
    assert "{path}" not in message
    assert (t("gcal.setup_needed_auth_hint") in message) is names_card


def test_every_locale_fills_the_google_setup_path_from_the_menu():
    for locale_path in sorted(LOCALES.glob("*.json")):
        data = flatten_locale(load_locale(locale_path))
        for key in GOOGLE_SETUP_KEYS:
            assert data[key].count("{path}") == 1, (locale_path.stem, key)
        assert data[SELECTED_ITEM_MENU_KEY].strip(), locale_path.stem
