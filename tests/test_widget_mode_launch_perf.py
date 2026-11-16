# -*- coding: utf-8 -*-
"""Widget-only mode launch work: guards for the deferred month grid, cached tokens.

Count-based guards (no wall-clock thresholds):
- the hidden month grid is neither built nor rendered while a week layout is shown,
  and shows exactly what an eagerly rendered grid shows once a month layout opens;
- completion checkboxes paint from the tokens apply_theme resolved;
- one exit -> re-enter resolves the widget theme once;
- menu stylesheets built from the caller's tokens equal the re-resolved ones;
- harden_widget_readability is memoised without sharing mutable results.
"""

from collections import OrderedDict

from PyQt6.QtCore import QDate, QSettings, Qt
from PyQt6.QtWidgets import QCheckBox
import pytest

from calendar_app.presentation.widgets import unified_widget_mode as uwm
from calendar_app.presentation.widgets import widget_mode_theme as wmt
from calendar_app.presentation.widgets.panel_widget_style import menu_stylesheet
from calendar_app.presentation.widgets.panel_widget_theme import _widget_mode_menu_stylesheet
from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    widget_mode_skins,
)
from tests.test_widget_mode_ux import _APP, Host, workspace  # noqa: F401


class _Opened:
    """Enter widget mode like the shared ``workspace`` fixture, after spies are set."""

    def __init__(self):
        self.host = Host()
        self.host.show()
        self.coordinator = WidgetModeCoordinator(self.host)
        self.host._widget_mode_coordinator = self.coordinator
        self.coordinator.enter()
        _APP.processEvents()
        self.controller = self.coordinator.controller
        self.widget = self.controller.widget

    def close(self):
        self.coordinator.close_for_shutdown()
        self.widget.deleteLater()
        self.host.close()
        self.host.deleteLater()
        _APP.processEvents()


@pytest.fixture
def opened():
    created = []

    def factory():
        session = _Opened()
        created.append(session)
        return session

    yield factory
    for session in created:
        session.close()


@pytest.fixture
def month_renders(monkeypatch):
    """Count month-grid renders and stylings that actually run (not deferred)."""
    counts = {"update_month": 0, "apply_style": 0}
    month_cls = uwm._CompactMonthCalendar
    original_update = month_cls.update_month
    original_style = month_cls._apply_style

    def update_month(self, selected, *, force=False):
        if not getattr(self, "_render_deferred", False):
            counts["update_month"] += 1
        return original_update(self, selected, force=force)

    def apply_style(self):
        if not getattr(self, "_render_deferred", False):
            counts["apply_style"] += 1
        return original_style(self)

    monkeypatch.setattr(month_cls, "update_month", update_month)
    monkeypatch.setattr(month_cls, "_apply_style", apply_style)
    return counts


def _month_state(month):
    return {
        "title": month.month_label.text(),
        "qss": month.styleSheet(),
        "selected": month.selectedDate(),
        "weekdays": [
            (label.text(), label.accessibleName(), label.styleSheet())
            for label in month.weekday_labels
        ],
        "days": [
            (button.text(), button.toolTip(), button.accessibleName(), button.styleSheet())
            for button in month.day_buttons
        ],
        "dates": list(month._dates),
    }


def _eager_reference(grid, selected):
    """A standalone (always eager) month grid given the arguments the window passed."""
    tokens = dict(grid._tokens)
    reference = uwm._CompactMonthCalendar()
    reference.set_theme_tokens(
        tokens,
        opacities=(tokens["_text_opacity"], tokens["_background_opacity"]),
        font_size=tokens["_font_size"],
    )
    reference.setSelectedDate(selected)
    state = _month_state(reference)
    reference.deleteLater()
    return state


def test_week_layout_never_builds_or_renders_the_hidden_month_grid(opened, month_renders):
    session = opened()
    grid = session.widget.cal_grid
    session.controller.refresh_data()
    _APP.processEvents()

    assert grid.display_mode == "week"
    assert month_renders == {"update_month": 0, "apply_style": 0}

    # Built (on first read) but still unrendered while the week strip shows.
    month = grid.month_calendar
    assert month.isHidden()
    assert all(button.styleSheet() == "" for button in month.day_buttons)
    assert month_renders == {"update_month": 0, "apply_style": 0}

    session.controller.set_layout("dashboard")
    _APP.processEvents()
    assert grid.month_calendar is month
    assert not month.isHidden()
    assert month_renders["update_month"] > 0 and month_renders["apply_style"] > 0
    expected = _eager_reference(grid, session.host.current_date)
    assert all(row[3] for row in expected["days"])  # the standalone grid stays eager
    assert _month_state(month) == expected


def test_date_and_theme_changes_in_week_mode_reach_the_month_grid(opened, month_renders):
    session = opened()
    host, controller, grid = session.host, session.controller, session.widget.cal_grid
    target = QDate.currentDate().addDays(45)

    controller.set_target_date(target)
    for key, value in {
        "text_theme": "light",
        "panel_base_color": "#f6f7fb",
        "theme_color": "#7653c4",
    }.items():
        host.settings.setValue(key, value)
    controller.refresh_theme()
    _APP.processEvents()
    assert month_renders == {"update_month": 0, "apply_style": 0}

    controller.set_layout("dashboard")
    _APP.processEvents()
    month = grid.month_calendar
    assert grid._tokens["accent"] == uwm._widget_theme_tokens(host)["accent"]
    assert month.selectedDate() == host.current_date == target
    assert _month_state(month) == _eager_reference(grid, target)
    # Layout metrics recorded before the grid existed were replayed on creation.
    cell_height = get_widget_mode_layout("dashboard").calendar_cell_size[1]
    assert month.day_buttons[0].maximumHeight() == max(25, int(cell_height * 0.62))


def test_switching_week_and_month_layouts_shows_the_current_month(opened, month_renders):
    session = opened()
    controller, grid = session.controller, session.widget.cal_grid
    today = QDate.currentDate()

    controller.set_layout("dashboard")
    _APP.processEvents()
    month = grid.month_calendar
    assert month.month_label.text() == f"{today.year()}. {today.month():02d}"

    controller.set_layout("stacked")
    _APP.processEvents()
    assert month.isHidden()
    renders = dict(month_renders)
    target = today.addMonths(2)
    controller.set_target_date(target)
    _APP.processEvents()
    assert month_renders == renders  # no hidden render while the week strip shows

    controller.set_layout("dashboard")
    _APP.processEvents()
    assert not month.isHidden()
    assert month.month_label.text() == f"{target.year()}. {target.month():02d}"
    assert month.selectedDate() == target
    assert target in month._dates
    assert _month_state(month) == _eager_reference(grid, target)


def _checked_box(widget):
    # Replaced rows are hidden at once and deleted later; use a live one.
    check = next(
        box
        for box in widget.scroll_content.findChildren(QCheckBox, "agenda_complete")
        if box.isVisibleTo(widget)
    )
    blocked = check.blockSignals(True)
    check.setChecked(True)
    check.blockSignals(blocked)
    return check


def test_completion_checkbox_paints_current_theme_without_resolving_it(workspace, monkeypatch):
    host, coordinator, widget = workspace
    controller = coordinator.controller
    before = _checked_box(widget).grab().toImage()

    host.settings.setValue("theme_color", "#11aa55")
    controller.refresh_theme()
    _APP.processEvents()
    check = _checked_box(widget)
    after = check.grab().toImage()
    cached = controller._theme_tokens
    controller._theme_tokens = None  # fall back to resolving the theme now
    try:
        resolved_now = check.grab().toImage()
    finally:
        controller._theme_tokens = cached
    assert after == resolved_now
    assert after != before

    calls = []
    original = uwm._widget_theme_tokens

    def counting(host_widget):
        calls.append(host_widget)
        return original(host_widget)

    monkeypatch.setattr(uwm, "_widget_theme_tokens", counting)
    for _ in range(10):
        check.repaint()
        check.grab()
    assert calls == []


def test_one_exit_and_reenter_resolves_the_widget_theme_once(workspace, monkeypatch):
    host, coordinator, widget = workspace
    calls = []
    original = uwm._widget_theme_tokens

    def counting(host_widget):
        calls.append(host_widget)
        return original(host_widget)

    monkeypatch.setattr(uwm, "_widget_theme_tokens", counting)
    coordinator.exit_widget_mode()
    _APP.processEvents()
    calls.clear()

    coordinator.enter()
    _APP.processEvents()
    assert widget.isVisible()
    assert len(calls) == 1


def test_window_not_owned_by_its_controller_still_themes_on_show(workspace, monkeypatch):
    host, _coordinator, _widget = workspace
    stray = uwm.UnifiedWidgetWindow(uwm.UnifiedWidgetController(host))
    applied = []
    original = uwm.UnifiedWidgetWindow.apply_theme

    def counting(window):
        applied.append(window)
        return original(window)

    monkeypatch.setattr(uwm.UnifiedWidgetWindow, "apply_theme", counting)
    try:
        stray.show()
        _APP.processEvents()
        assert stray in applied
    finally:
        stray.hide()
        stray.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize(
    "mode,base,accent",
    [
        ("dark", "#121827", "#c5a3f5"),
        ("light", "#f6f7fb", "#7653c4"),
        ("custom", "#24413f", "#ff9d4d"),
    ],
)
@pytest.mark.parametrize("widget_color", [None, "#ff00aa"])
def test_menu_stylesheet_from_resolved_tokens_matches_re_resolution(
    tmp_path, mode, base, accent, widget_color
):
    host = Host()
    host.settings = QSettings(str(tmp_path / "main.ini"), QSettings.Format.IniFormat)
    for key, value in {
        "text_theme": mode,
        "panel_base_color": base,
        "theme_color": accent,
        "widget_mode_color_theme": widget_color,
    }.items():
        if value is not None:
            host.settings.setValue(key, value)
    try:
        for skin in widget_mode_skins():
            host.settings.setValue("widget_mode_skin", skin.skin_id)
            tokens = uwm._widget_theme_tokens(host)
            assert menu_stylesheet(tokens) == _widget_mode_menu_stylesheet(tokens), skin.skin_id
    finally:
        host.deleteLater()
        _APP.processEvents()


_SAMPLE_TOKENS = {
    "accent": "#4da6ff",
    "accent_hover": "#69b4ff",
    "text_primary": "#ffffff",
    "text_secondary": "#b9c2d3",
    "text_faint": "#7c88a3",
    "panel_bg": "rgba(28, 28, 28, 200)",
    "button_primary_bg": "#4da6ff",
    "calendar_weekday_sat": "#4da6ff",
}


@pytest.fixture
def harden_misses(monkeypatch):
    monkeypatch.setattr(wmt, "_HARDEN_CACHE", OrderedDict())
    misses = []
    original = wmt._harden_widget_readability_uncached

    def counting(tokens, base_color):
        misses.append(base_color)
        return original(tokens, base_color)

    monkeypatch.setattr(wmt, "_harden_widget_readability_uncached", counting)
    return misses


def test_harden_cache_hit_returns_an_independent_equal_copy(harden_misses):
    first = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS), "#1c1c1c")
    second = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS), "#1c1c1c")
    assert len(harden_misses) == 1
    assert second == first
    assert second is not first
    assert second == wmt._HARDEN_CACHE[next(iter(wmt._HARDEN_CACHE))]
    assert second is not wmt._HARDEN_CACHE[next(iter(wmt._HARDEN_CACHE))]

    expected = dict(first)
    first["accent"] = "mutated"
    second["text_primary"] = "mutated"
    third = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS), "#1c1c1c")
    assert third == expected
    assert len(harden_misses) == 1


def test_harden_cache_misses_on_any_changed_input(harden_misses):
    reference = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS), "#1c1c1c")
    other_base = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS), "#f6f7fb")
    other_token = wmt.harden_widget_readability(dict(_SAMPLE_TOKENS, accent="#ff9d4d"), "#1c1c1c")
    assert len(harden_misses) == 3
    assert other_base != reference
    assert other_token != reference
    assert other_base == wmt._harden_widget_readability_uncached(dict(_SAMPLE_TOKENS), "#f6f7fb")


def test_harden_uncacheable_inputs_still_return_a_result(harden_misses):
    tokens = dict(_SAMPLE_TOKENS, extra=["not", "hashable"])
    first = wmt.harden_widget_readability(tokens, "#1c1c1c")
    second = wmt.harden_widget_readability(tokens, "#1c1c1c")
    assert first == second
    assert first["extra"] == ["not", "hashable"]
    assert len(harden_misses) == 2
    assert not wmt._HARDEN_CACHE


def test_harden_cache_is_bounded(harden_misses):
    for index in range(wmt._HARDEN_CACHE_SIZE + 5):
        wmt.harden_widget_readability(dict(_SAMPLE_TOKENS, accent=f"#10{index:02d}ff"), "#1c1c1c")
    assert len(wmt._HARDEN_CACHE) == wmt._HARDEN_CACHE_SIZE


def _identity(widget):
    text = widget.text() if hasattr(widget, "text") else ""
    return (type(widget).__name__, widget.objectName(), text, widget.accessibleName())


def _tab_sequence(window):
    sequence = []
    start = window.restore_btn
    current = start
    for _ in range(5000):
        policy = current.focusPolicy().value
        if (
            window.isAncestorOf(current)
            and current.isVisibleTo(window)
            and current.isEnabled()
            and policy & Qt.FocusPolicy.TabFocus.value
        ):
            sequence.append(_identity(current))
        current = current.nextInFocusChain()
        if current is start:
            break
    return sequence


def _dashboard_snapshot(session):
    session.controller.set_layout("dashboard")
    _APP.processEvents()
    grid = session.widget.cal_grid
    month = grid.month_calendar
    return {
        "tab_order": _tab_sequence(session.widget),
        "week_strip_index": grid._root_layout.indexOf(grid._week_strip),
        "month_index": grid._root_layout.indexOf(month),
        "layout_count": grid._root_layout.count(),
        "geometry": [button.geometry().getRect() for button in month.day_buttons],
        "month": _month_state(month),
    }


def test_lazily_built_month_grid_matches_an_eagerly_built_one(opened, monkeypatch):
    lazy = opened()
    assert lazy.widget.cal_grid._month_calendar is None
    lazy_snapshot = _dashboard_snapshot(lazy)

    original_init = uwm.CompactCalendarGrid.__init__

    def eager_init(self, parent=None):
        original_init(self, parent)
        self.month_calendar  # noqa: B018  (built at construction, as before)

    monkeypatch.setattr(uwm.CompactCalendarGrid, "__init__", eager_init)
    eager = opened()
    assert eager.widget.cal_grid._month_calendar is not None
    eager_snapshot = _dashboard_snapshot(eager)

    assert lazy_snapshot["week_strip_index"] == 0
    assert lazy_snapshot["month_index"] == 1
    assert lazy_snapshot["layout_count"] == 2
    assert lazy_snapshot == eager_snapshot
