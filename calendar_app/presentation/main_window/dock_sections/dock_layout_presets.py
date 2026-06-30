"""Built-in panel layout presets (5 configurations, triggered via Ctrl+Shift+1-5)."""

from __future__ import annotations

import copy

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QGuiApplication

from calendar_app.infrastructure.i18n import t

# (display name, shortcut hint)
LAYOUT_PRESET_DEFS = [
    [t("layout.p1"), "Ctrl+Shift+1"],  # All 4 docked in default areas
    [t("layout.p2"), "Ctrl+Shift+2"],  # Only calendar visible
    [t("layout.p3"), "Ctrl+Shift+3"],  # Today + routines + directives, no calendar
    [t("layout.p4"), "Ctrl+Shift+4"],  # Left tabs | Right tabs
    [t("layout.p5"), "Ctrl+Shift+5"],  # All 4 floating in quadrants
]

# Release defaults baked from the current slot 1~5 layouts on the maintainer
# machine so fresh installs open with the same preset results even before any
# user-specific QSettings have been created.
_EMBEDDED_RELEASE_PRESET_PAYLOADS: list[dict | None] = [
    {
        "dock_state_b64": "AAAA/wAAAAD9AAAAAQAAAAAAAAdxAAADsPwCAAAAAfwAAAA3AAADsAAAAKgA/////AEAAAAC+wAAABYAYwBlAG4AdABlAHIAXwBkAG8AYwBrAQAAAAAAAAWmAAADdAD////8AAAFqQAAAcgAAAGeAP////wCAAAAA/sAAAASAGwAZQBmAHQAXwBkAG8AYwBrAQAAADcAAAD+AAAANgD////7AAAAGAByAG8AdQB0AGkAbgBlAF8AZABvAGMAawEAAAE4AAABQQAAADYA////+wAAABwAZABpAHIAZQBjAHQAaQB2AGUAXwBkAG8AYwBrAQAAAnwAAAFrAAAANgD///8AAAAAAAADsAAAAAQAAAAEAAAACAAAAAj8AAAAAA==",
        "visibility": {
            "left_dock": True,
            "center_dock": True,
            "routine_dock": True,
            "directive_dock": True,
        },
        "opacity": 200,
        "opacity_unit": "byte",
        "view_mode_state": "monthly",
    },
    {
        "dock_state_b64": "AAAA/wAAAAD9AAAAAQAAAAAAAAdxAAADsPwCAAAAAfwAAAA3AAADsAAAAG8A/////AEAAAAC/AAAAAAAAAWmAAADdAD////6AAAAAAEAAAAC+wAAABYAYwBlAG4AdABlAHIAXwBkAG8AYwBrAQAAAaEAAAQFAAADdAD////7AAAAEgBsAGUAZgB0AF8AZABvAGMAawEAAAAA/////wAAAZ4A/////AAABakAAAHIAAAA6AD////8AgAAAAL7AAAAGAByAG8AdQB0AGkAbgBlAF8AZABvAGMAawEAAAA3AAABugAAADYA////+wAAABwAZABpAHIAZQBjAHQAaQB2AGUAXwBkAG8AYwBrAQAAAfQAAAHzAAAANgD///8AAAAAAAADsAAAAAQAAAAEAAAACAAAAAj8AAAAAA==",
        "visibility": {
            "left_dock": True,
            "center_dock": True,
            "routine_dock": True,
            "directive_dock": True,
        },
        "opacity": 200,
        "opacity_unit": "byte",
        "view_mode_state": "monthly",
    },
    {
        "dock_state_b64": "AAAA/wAAAAD9AAAAAgAAAAAAAAdxAAADsPwCAAAAAvsAAAASAGwAZQBmAHQAXwBkAG8AYwBrAAAAADcAAANYAAAANgD////7AAAAFgBjAGUAbgB0AGUAcgBfAGQAbwBjAGsBAAAANwAAA7AAAAA8AP///wAAAAEAAAO3AAADsPwCAAAAAvsAAAAYAHIAbwB1AHQAaQBuAGUAXwBkAG8AYwBrAAAAADcAAAH7AAAANgD////7AAAAHABkAGkAcgBlAGMAdABpAHYAZQBfAGQAbwBjAGsAAAAANwAAA7AAAAA2AP///wAAAAAAAAOwAAAABAAAAAQAAAAIAAAACPwAAAAA",
        "visibility": {
            "left_dock": False,
            "center_dock": True,
            "routine_dock": False,
            "directive_dock": False,
        },
        "opacity": 200,
        "opacity_unit": "byte",
        "view_mode_state": "monthly",
    },
    {
        "dock_state_b64": "AAAA/wAAAAD9AAAAAgAAAAAAAAWUAAADsPwCAAAAAfwAAAA3AAADsAAAAFsBAAAe+gAAAAACAAAAAvsAAAAWAGMAZQBuAHQAZQByAF8AZABvAGMAawEAAAAA/////wAAADwA////+wAAABIAbABlAGYAdABfAGQAbwBjAGsBAAAAAP////8AAAA2AP///wAAAAEAAAHaAAADsPwCAAAAAfwAAAA3AAADsAAAAFUBAAAe+gAAAAACAAAAAvsAAAAYAHIAbwB1AHQAaQBuAGUAXwBkAG8AYwBrAQAAAAD/////AAAANgD////7AAAAHABkAGkAcgBlAGMAdABpAHYAZQBfAGQAbwBjAGsBAAAAAP////8AAAA2AP///wAAAAAAAAOwAAAABAAAAAQAAAAIAAAACPwAAAAA",
        "visibility": {
            "left_dock": True,
            "center_dock": True,
            "routine_dock": True,
            "directive_dock": True,
        },
        "opacity": 200,
        "opacity_unit": "byte",
        "view_mode_state": "monthly",
    },
    {
        "dock_state_b64": "AAAA/wAAAAD9AAAAAgAAAAAAAAO4AAAEEPwCAAAAAvsAAAASAGwAZQBmAHQAXwBkAG8AYwBrAwAAAAUAAAAFAAABgQAAAYH7AAAAFgBjAGUAbgB0AGUAcgBfAGQAbwBjAGsDAAABlQAAAAUAAAGBAAABgQAAAAEAAAd2AAAEEPwCAAAAAvsAAAAYAHIAdQB0AGkAbgBlAF8AZABvAGMAawMAAAAFAAABlQAAAYEAAAGB+wAAABwAZABpAHIAZQBjAHQAaQB2AGUAXwBkAG8AYwBrAwAAAZUAAAGVAAABgQAAAYEAAAAAAAAAAAAABAAAAAQAAAAIAAAACPwAAAAA",
        "visibility": {
            "left_dock": True,
            "center_dock": True,
            "routine_dock": True,
            "directive_dock": True,
        },
        "opacity": 200,
        "opacity_unit": "byte",
        "view_mode_state": "monthly",
    },
]


def load_custom_preset_names():
    from PyQt6.QtCore import QSettings

    settings = QSettings("kimhyojin", "Dark Calendar")
    custom_names = settings.value("layout_preset_names", None)
    if isinstance(custom_names, list) and len(custom_names) == len(LAYOUT_PRESET_DEFS):
        for i, name in enumerate(custom_names):
            if name:
                LAYOUT_PRESET_DEFS[i][0] = name


def save_custom_preset_names():
    from PyQt6.QtCore import QSettings

    settings = QSettings("kimhyojin", "Dark Calendar")
    names = [row[0] for row in LAYOUT_PRESET_DEFS]
    settings.setValue("layout_preset_names", names)


# Load overrides immediately on module import.
load_custom_preset_names()

_LEFT = Qt.DockWidgetArea.LeftDockWidgetArea
_RIGHT = Qt.DockWidgetArea.RightDockWidgetArea


def apply_layout_preset(app, index: int) -> None:
    """Apply preset by 0-based index (0–4).

    If the user has saved a custom layout for this slot it takes priority;
    otherwise the built-in hardcoded layout is applied.
    """
    _FUNCS = [
        _preset_all_docked,
        _preset_calendar_focus,
        _preset_work_focus,
        _preset_tabbed_split,
        _preset_all_floating,
    ]
    if not (0 <= index < len(_FUNCS)):
        return

    name = LAYOUT_PRESET_DEFS[index][0]

    # Use saved user layout when available
    if hasattr(app, "preset_manager"):
        presets = app.preset_manager._read_presets()
        if name in presets:
            app.preset_manager._load_preset(name)
            return

        embedded_payload = _embedded_release_preset_payload(index)
        if embedded_payload and app.preset_manager._apply_payload(copy.deepcopy(embedded_payload)):
            if hasattr(app, "show_toast"):
                title = t("layout.toast_title")
                msg = t("layout.toast_msg").format(name=name)
                app.show_toast(title, msg)
            return

    # Fall back to hardcoded layout
    _FUNCS[index](app)
    if hasattr(app, "show_toast"):
        title = t("layout.toast_title")
        msg = t("layout.toast_msg").format(name=name)
        app.show_toast(title, msg)


def _embedded_release_preset_payload(index: int) -> dict | None:
    if 0 <= index < len(_EMBEDDED_RELEASE_PRESET_PAYLOADS):
        return _EMBEDDED_RELEASE_PRESET_PAYLOADS[index]
    return None


# ---------------------------------------------------------------------------
# Preset 1: 전체 도킹 — all 4 panels docked in default left/right areas
# ---------------------------------------------------------------------------
def _preset_all_docked(app) -> None:
    _undock_all(app)
    app.addDockWidget(_LEFT, app.left_dock)
    app.addDockWidget(_LEFT, app.center_dock)
    app.addDockWidget(_RIGHT, app.routine_dock)
    app.addDockWidget(_RIGHT, app.directive_dock)
    for d in _all_docks(app):
        d.setVisible(True)
    if hasattr(app, "_on_any_dock_float_changed"):
        app._on_any_dock_float_changed()
    # 우측 두 독의 폭을 균등하게 맞춤
    QTimer.singleShot(
        50,
        lambda: app.resizeDocks(
            [app.routine_dock, app.directive_dock],
            [200, 200],
            Qt.Orientation.Horizontal,
        ),
    )
    # 좌/우 열의 수직 분할선을 50/50으로 동기화 (단차 제거)
    QTimer.singleShot(100, lambda: _sync_vertical_splits_preset(app))


# ---------------------------------------------------------------------------
# Preset 2: 캘린더 집중 — only the calendar panel
# ---------------------------------------------------------------------------
def _preset_calendar_focus(app) -> None:
    _undock_all(app)
    for d in (app.left_dock, app.routine_dock, app.directive_dock):
        d.setVisible(False)
    app.addDockWidget(_LEFT, app.center_dock)
    app.center_dock.setVisible(True)


# ---------------------------------------------------------------------------
# Preset 3: 업무 집중 — today's schedule + routines + directives, no calendar
# ---------------------------------------------------------------------------
def _preset_work_focus(app) -> None:
    _undock_all(app)
    app.center_dock.setVisible(False)
    app.addDockWidget(_LEFT, app.left_dock)
    app.addDockWidget(_RIGHT, app.routine_dock)
    app.addDockWidget(_RIGHT, app.directive_dock)
    app.left_dock.setVisible(True)
    app.routine_dock.setVisible(True)
    app.directive_dock.setVisible(True)


# ---------------------------------------------------------------------------
# Preset 4: 탭 분할 — left+center tabbed on left, routine+directive tabbed on right
# ---------------------------------------------------------------------------
def _preset_tabbed_split(app) -> None:
    _undock_all(app)
    app.addDockWidget(_LEFT, app.left_dock)
    app.tabifyDockWidget(app.left_dock, app.center_dock)
    app.addDockWidget(_RIGHT, app.routine_dock)
    app.tabifyDockWidget(app.routine_dock, app.directive_dock)
    for d in _all_docks(app):
        d.setVisible(True)
    # Bring the first tab of each group to front.
    app.left_dock.raise_()
    app.routine_dock.raise_()


# ---------------------------------------------------------------------------
# Preset 5: 전체 분리 — all 4 panels floating in four quadrants of the screen
# ---------------------------------------------------------------------------
def _preset_all_floating(app) -> None:
    screen = QGuiApplication.screenAt(app.geometry().center())
    if not screen:
        screen = QGuiApplication.primaryScreen()
    if not screen:
        return

    avail = screen.availableGeometry()
    mx, my = avail.left(), avail.top()
    w = (avail.width() - 30) // 2
    h = (avail.height() - 30) // 2

    quadrants = [
        QRect(mx + 5, my + 5, w, h),  # top-left
        QRect(mx + w + 20, my + 5, w, h),  # top-right
        QRect(mx + 5, my + h + 20, w, h),  # bottom-left
        QRect(mx + w + 20, my + h + 20, w, h),  # bottom-right
    ]

    for dock, rect in zip(_all_docks(app), quadrants, strict=False):
        dock.setVisible(True)
        dock.setFloating(True)
        _move_dock_deferred(dock, rect)


def _sync_vertical_splits_preset(app):
    try:
        app.resizeDocks([app.left_dock, app.center_dock], [500, 500], Qt.Orientation.Vertical)
        app.resizeDocks([app.routine_dock, app.directive_dock], [500, 500], Qt.Orientation.Vertical)
    except Exception:
        pass


def _move_dock_deferred(dock, rect: QRect) -> None:
    def _apply():
        dock.setGeometry(rect)
        dock.raise_()

    QTimer.singleShot(50, _apply)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _all_docks(app):
    return [app.left_dock, app.center_dock, app.routine_dock, app.directive_dock]


def _undock_all(app) -> None:
    """Return all floating docks back to the dock manager before re-arranging."""
    for d in _all_docks(app):
        if d.isFloating():
            d.setFloating(False)
