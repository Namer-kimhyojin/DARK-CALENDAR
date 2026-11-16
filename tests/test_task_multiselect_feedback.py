# -*- coding: utf-8 -*-
"""Ctrl+click multi-selection: in-place toggles, a visible count bar and clear feedback."""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.calendar import selection_bar
from calendar_app.presentation.calendar.month_renderer import _calendar_toolbar_style_bundle
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.panels import side_panel_renderer as spr
from calendar_app.presentation.widgets.ui_components import (
    DraggableTaskButton,
    _task_selected_fill,
)
from calendar_app.shared.color_utils import composite_color, contrast_ratio, parse_css_color
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens

CTRL = Qt.KeyboardModifier.ControlModifier


class MultiSelectHost(TaskActionsMixin, QWidget):
    def __init__(self, settings, button_ids=(1, 2, 3), panel_ids=(1, 2, 3)):
        super().__init__()
        self.settings = settings
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.schedule_panel_refresh = MagicMock(name="schedule_panel_refresh")
        self.load_center_panel = MagicMock(name="load_center_panel")
        self.handle_task_deleted = MagicMock(name="handle_task_deleted")
        layout = QHBoxLayout(self)
        self.selection_status_lbl = QLabel(self)
        layout.addWidget(self.selection_status_lbl)
        layout.addWidget(selection_bar.build_selection_bar(self, _calendar_toolbar_style_bundle()))
        self.buttons = {}
        for tid in button_ids:
            btn = DraggableTaskButton(tid, f"task {tid}")
            btn.set_tag_color("#ff8800" if tid % 2 else None)
            btn.taskClicked.connect(self.handle_task_clicked)
            layout.addWidget(btn)
            self.buttons[tid] = btn
        self._panel_task_frames = {}
        for tid in panel_ids:
            frame = QFrame(self)
            spr._apply_panel_item_style(frame, False, "#33aaff")
            layout.addWidget(frame)
            self._panel_task_frames[tid] = (frame, "#33aaff")


@pytest.fixture
def host(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "multiselect.ini"), QSettings.Format.IniFormat)
    widget = MultiSelectHost(settings)
    widget.show()
    app.processEvents()
    yield app, widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_ctrl_click_toggles_in_place_without_a_rerender(host):
    app, widget = host
    first, second = widget.buttons[1], widget.buttons[2]

    widget.handle_task_clicked(1, CTRL)
    widget.handle_task_clicked(2, CTRL)
    app.processEvents()

    assert widget.selected_task_ids == {1, 2}
    assert first.property("selected") is True and second.property("selected") is True
    assert widget.buttons[3].property("selected") is False
    assert first.accessibleDescription() == t("calendar.selected_state", "선택됨")
    mark = first.findChild(QLabel, "taskSelectedMark")
    assert mark is not None and mark.isVisible()
    widget.schedule_panel_refresh.assert_not_called()
    widget.load_center_panel.assert_not_called()

    widget.handle_task_clicked(1, CTRL)
    app.processEvents()
    assert widget.selected_task_ids == {2}
    assert first.property("selected") is False
    assert not mark.isVisible()
    assert first.accessibleDescription() == ""
    widget.schedule_panel_refresh.assert_not_called()


def test_toggle_does_not_reapply_the_whole_button_stylesheet(host):
    _app, widget = host
    btn = widget.buttons[1]
    with patch.object(btn, "_apply_tag_frame_style") as restyle:
        btn.set_selected(True)
        btn.set_selected(False)
    restyle.assert_not_called()


def test_only_changed_panel_cards_are_restyled(host):
    _app, widget = host
    with patch.object(spr, "_apply_panel_item_style", wraps=spr._apply_panel_item_style) as apply:
        widget.handle_task_clicked(2, CTRL)
    assert [call.args[1] for call in apply.call_args_list] == [True]
    frame = widget._panel_task_frames[2][0]
    assert frame.property("panelItemSelected") is True
    assert frame.accessibleDescription() == t("calendar.selected_state", "선택됨")


def test_selection_bar_shows_count_and_clears(host):
    app, widget = host
    bar = widget.selection_bar
    assert bar.isHidden()
    assert widget.selection_status_lbl.isVisible()

    widget.handle_task_clicked(1, CTRL)
    widget.handle_task_clicked(3, CTRL)
    app.processEvents()
    assert bar.isVisible()
    assert bar.chip.text() == t("panel.n_selected", n=2)
    assert bar.chip.accessibleName() == bar.chip.text()
    # The hint label steps aside so the count is not shown twice.
    assert widget.selection_status_lbl.isHidden()

    bar.clear_button.click()
    app.processEvents()
    assert widget.selected_task_ids == set()
    assert bar.isHidden()
    assert widget.selection_status_lbl.isVisible()
    assert all(btn.property("selected") is False for btn in widget.buttons.values())


def test_compact_toolbar_keeps_the_hint_hidden_but_the_count_visible(host):
    app, widget = host
    widget.selection_status_lbl.setProperty("toolbarCompact", True)
    selection_bar.sync_selection_bar(widget)
    assert widget.selection_status_lbl.isHidden()
    widget.handle_task_clicked(2, CTRL)
    app.processEvents()
    assert widget.selection_bar.isVisible()
    widget.clear_task_selection()
    assert widget.selection_status_lbl.isHidden()


def test_selection_menu_offers_existing_bulk_actions(host):
    _app, widget = host
    widget.handle_task_clicked(1, CTRL)
    widget.handle_task_clicked(2, CTRL)
    menu = widget.selection_bar.chip.menu()
    selection_bar.populate_selection_menu(widget, menu)
    texts = [action.text() for action in menu.actions()]
    submenus = [action.text() for action in menu.actions() if action.menu() is not None]
    assert texts[0] == t("panel.n_selected", n=2)
    assert len(submenus) == 2  # priority and status, as in the panel context menus
    assert any(text.startswith(t("calendar.selection_delete", "선택 항목 삭제")) for text in texts)
    clear = next(
        action
        for action in menu.actions()
        if action.text().startswith(t("calendar.selection_clear_short", "선택 해제"))
    )

    delete = next(a for a in menu.actions() if a.text().startswith(t("calendar.selection_delete")))
    delete.trigger()
    widget.handle_task_deleted.assert_called_once()
    assert widget.handle_task_deleted.call_args.args[0] in {1, 2}

    clear.trigger()
    assert widget.selected_task_ids == set()


def test_directive_only_selection_hides_task_only_actions(host):
    _app, widget = host
    widget.selected_directive_ids = {7}
    menu = widget.selection_bar.chip.menu()
    selection_bar.populate_selection_menu(widget, menu)
    assert not [action for action in menu.actions() if action.menu() is not None]
    assert not any(
        action.text().startswith(t("calendar.selection_delete")) for action in menu.actions()
    )


@pytest.mark.parametrize(
    ("mode", "base", "accent"),
    (("dark", "#121827", "#c5a3f5"), ("light", "#f3f1fa", "#7950b8")),
)
@pytest.mark.parametrize("opacity", (255, 150))
def test_selected_fill_keeps_titles_readable(tmp_path, mode, base, accent, opacity):
    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "contrast.ini"), QSettings.Format.IniFormat)
    for key, value in {
        "text_theme": mode,
        "panel_base_color": base,
        "theme_color": accent,
        "last_opacity_unit": "byte",
        "last_opacity": opacity,
    }.items():
        settings.setValue(key, value)
    snapshot = build_theme_snapshot(settings=settings)
    tokens = get_ui_tokens(settings=settings, snapshot=snapshot)
    surface = composite_color(tokens["bg_main"], snapshot.panel_base_color)
    item = composite_color(tokens["bg_item"], surface)
    resting = item
    selected = composite_color(_task_selected_fill(QColor(tokens["accent"])), item)
    text = composite_color(parse_css_color(tokens["text_primary"]), selected)

    assert contrast_ratio(text, selected) >= 4.5
    # The selected fill must differ visibly from the resting item.
    delta = sum(
        abs(a - b)
        for a, b in zip(
            (selected.red(), selected.green(), selected.blue()),
            (resting.red(), resting.green(), resting.blue()),
            strict=True,
        )
    )
    assert delta >= 40


def test_selection_menu_priority_applies_to_every_selected_task(host):
    _app, widget = host
    widget.handle_task_priority_changed = MagicMock(name="handle_task_priority_changed")
    widget.handle_task_clicked(1, CTRL)
    widget.handle_task_clicked(3, CTRL)
    menu = widget.selection_bar.chip.menu()
    selection_bar.populate_selection_menu(widget, menu)
    priority_menu = next(a.menu() for a in menu.actions() if a.menu() is not None)
    priority_menu.actions()[0].trigger()
    assert {call.args[0] for call in widget.handle_task_priority_changed.call_args_list} == {1, 3}


def test_priority_and_status_menus_are_disabled_without_a_selection(host):
    from PyQt6.QtWidgets import QMenu

    from calendar_app.domain.task_constants import PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS
    from calendar_app.presentation.context_menu_manager import _add_task_priority_status_menus

    _app, widget = host
    widget.handle_task_priority_changed = MagicMock(name="handle_task_priority_changed")
    menu = QMenu(widget)
    _add_task_priority_status_menus(menu, widget, PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS)
    submenus = [action.menu() for action in menu.actions() if action.menu() is not None]
    assert len(submenus) == 2
    assert not any(sub.isEnabled() for sub in submenus)
    submenus[0].actions()[0].trigger()
    widget.handle_task_priority_changed.assert_not_called()


def test_selection_change_does_not_change_render_signatures():
    from tests.test_panel_render_signatures import SignatureHost

    QApplication.instance() or QApplication([])
    signature_host = SignatureHost()
    before = (
        signature_host._build_center_render_signature(),
        signature_host._build_left_render_signature(),
    )
    signature_host.selected_task_ids = {4, 9}
    after = (
        signature_host._build_center_render_signature(),
        signature_host._build_left_render_signature(),
    )
    assert before == after


class TestWeekTimeGridMultiSelect:
    @pytest.fixture
    def grid(self):
        from PyQt6.QtCore import QDate

        from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

        app = QApplication.instance() or QApplication([])
        grid = WeekTimeGrid()
        grid.resize(1000, 700)
        tasks = [
            {
                "id": tid,
                "name": f"일정 {tid}",
                "deadline": f"2026-10-0{4 + tid} 09:00:00",
                "end_date": f"2026-10-0{4 + tid} 10:00:00",
                "all_day": 0,
            }
            for tid in (1, 2)
        ]
        tasks.append(
            {
                "id": "sub-1",
                "name": "구독",
                "deadline": "2026-10-07 09:00:00",
                "end_date": "2026-10-07 10:00:00",
                "all_day": 0,
                "is_subscription": True,
                "read_only": True,
            }
        )
        grid.set_week(QDate(2026, 10, 5), tasks)
        grid.show()
        app.processEvents()
        grid.scroll_to_time(8 * 60)
        app.processEvents()
        yield app, grid
        grid.close()
        grid.deleteLater()
        app.processEvents()

    @staticmethod
    def _point(grid, day):
        from PyQt6.QtCore import QPoint

        x = grid.GUTTER + (day + 0.5) * grid._column_width()
        return QPoint(round(x), round(9.5 * grid.HOUR_HEIGHT))

    def test_ctrl_click_toggles_without_opening_or_moving(self, grid):
        from PyQt6.QtTest import QSignalSpy, QTest

        app, grid = grid
        toggled = QSignalSpy(grid.selection_toggled)
        edits = QSignalSpy(grid.edit_requested)
        days = QSignalSpy(grid.day_selected)
        QTest.mouseClick(grid._timeline, Qt.MouseButton.LeftButton, CTRL, self._point(grid, 0))
        app.processEvents()
        assert [list(args) for args in toggled] == [[1]]
        assert len(edits) == 0 and len(days) == 0
        assert grid._gesture is None

        # Subscriptions cannot join a bulk selection; Ctrl+click falls back to a click.
        QTest.mouseClick(grid._timeline, Qt.MouseButton.LeftButton, CTRL, self._point(grid, 2))
        app.processEvents()
        assert len(toggled) == 1

    def test_mirrored_selection_and_keyboard(self, grid):
        from PyQt6.QtTest import QSignalSpy, QTest

        app, grid = grid
        grid.set_multi_selection({1, "2", "bad"})
        assert grid.multi_selection() == {1, 2}
        assert grid._is_multi_selected(grid._segments[0].task)

        toggled = QSignalSpy(grid.selection_toggled)
        cleared = QSignalSpy(grid.selection_clear_requested)
        grid.setFocus()
        QTest.keyClick(grid, Qt.Key.Key_Right)
        QTest.keyClick(grid, Qt.Key.Key_Space, CTRL)
        assert len(toggled) == 1
        QTest.keyClick(grid, Qt.Key.Key_Escape)
        assert len(cleared) == 1
        grid.set_multi_selection(set())
        QTest.keyClick(grid, Qt.Key.Key_Escape)
        assert len(cleared) == 1


def test_window_selection_reaches_the_week_grid(host):
    from PyQt6.QtCore import QDate

    from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid

    app, widget = host
    grid = WeekTimeGrid(widget)
    grid.set_week(QDate(2026, 10, 5), [])
    grid.selection_toggled.connect(lambda task_id: widget.handle_task_clicked(task_id, CTRL))
    grid.selection_toggled.emit(2)
    app.processEvents()
    assert widget.selected_task_ids == {2}
    assert grid.multi_selection() == {2}
    assert widget.buttons[2].property("selected") is True
    widget.clear_task_selection()
    assert grid.multi_selection() == set()
