# -*- coding: utf-8 -*-
"""Widget workspace interaction and preference isolation regressions."""

import os
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QPoint, Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QToolButton, QWidget
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController
from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class Host(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.current_date = QDate.currentDate()
        date = self.current_date.toString("yyyy-MM-dd")
        self._latest_calendar_range_data = {
            "range_start": self.current_date.addDays(-30).toString("yyyy-MM-dd"),
            "range_end": self.current_date.addDays(30).toString("yyyy-MM-dd"),
            "rows": [{"id": 1, "name": "프로젝트 회의", "deadline": f"{date} 14:00:00"}],
        }
        self._latest_directive_data = {
            "context_date": date,
            "routine_rows": [
                {"id": 2, "name": "회의 자료 정리", "target_date": date, "status": "in_progress"}
            ],
            "directive_rows": [(3, "검토 의견 전달", "pending", "", date)],
        }
        self.schedule_panel_refresh = Mock()
        self.open_task_dialog = Mock()
        self.open_modify_task_dialog = Mock()
        self.open_directive_dialog = Mock()
        self.open_work_management_dialog = Mock()
        self.handle_task_status_changed = Mock(return_value=True)
        self.handle_directive_status_changed = Mock(return_value=True)
        self.handle_task_priority_changed = Mock()
        self.handle_directive_priority_changed = Mock()


_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def workspace():
    host = Host()
    host.show()
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    coordinator.enter()
    _APP.processEvents()
    yield host, coordinator, coordinator.controller.widget
    coordinator.close_for_shutdown()
    coordinator.controller.widget.deleteLater()
    host.close()
    host.deleteLater()
    _APP.processEvents()


def test_pin_changes_do_not_exit_mode_and_return_button_is_explicit(workspace):
    host, coordinator, widget = workspace
    widget.pin_btn.click()
    assert coordinator.state is WidgetModeState.ACTIVE
    assert widget.isVisible()
    assert not host.isVisible()
    assert not widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert host.settings.value("widget_mode_always_top") is False
    widget.restore_btn.click()
    assert host.isVisible()
    assert host.settings.value("widget_mode_resume") is False


def test_hide_to_tray_preserves_mode_and_filter_for_reopening(workspace):
    host, coordinator, widget = workspace
    widget.set_filter("work")
    coordinator.hide_to_tray()
    assert not widget.isVisible() and not host.isVisible()
    assert host.settings.value("widget_mode_resume") is True
    coordinator.enter()
    assert widget._active_filter == "work"
    coordinator.close_for_shutdown()
    assert host.settings.value("widget_mode_resume") is True


def test_list_buttons_route_task_and_directive_ids(workspace):
    host, coordinator, widget = workspace
    buttons = widget.scroll_content.findChildren(QPushButton, "agenda_item_title")
    assert len(buttons) == 3
    buttons[0].click()
    host.open_modify_task_dialog.assert_called_once_with(1)
    buttons[-1].click()
    host.open_directive_dialog.assert_called_once_with(task_id=3)


def test_item_more_menu_routes_priority_change(workspace):
    host, coordinator, widget = workspace
    routine = next(item for item in widget._last_items if item.get("item_id") == 2)

    def execute(menu, _position):
        priority_menu = next(
            action.menu() for action in menu.actions() if action.menu() is not None
        )
        return priority_menu.actions()[0]

    with patch("calendar_app.presentation.widgets.unified_widget_mode.QMenu.exec", new=execute):
        coordinator.controller.open_item_menu(routine, QPoint())

    host.handle_task_priority_changed.assert_called_once_with(2, "urgent")


def test_read_only_subscription_item_cannot_open_mutating_dialog(workspace):
    host, coordinator, widget = workspace
    read_only_item = {
        "item_id": 99,
        "source": "task",
        "read_only": True,
        "is_task": False,
    }

    coordinator.controller.open_item(read_only_item)

    host.open_modify_task_dialog.assert_not_called()
    assert widget.feedback_label.isVisible()
    assert widget.feedback_label.text() == "읽기 전용 캘린더"


def test_edit_dialog_temporarily_unpins_without_changing_saved_setting(workspace):
    host, coordinator, widget = workspace
    before = host.settings.value("widget_mode_always_top")

    def check_dialog(_task_id):
        assert not widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert coordinator.state is WidgetModeState.ACTIVE

    host.open_modify_task_dialog.side_effect = check_dialog
    coordinator.controller.open_item({"item_id": 1, "source": "task"})
    assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert host.settings.value("widget_mode_always_top") == before


def test_startup_restores_workspace_from_reopened_settings(workspace, tmp_path):
    from PyQt6.QtCore import QSettings

    from calendar_app.presentation.widgets.widget_mode_coordinator import (
        restore_saved_widget_workspace,
    )

    host, coordinator, widget = workspace
    settings_path = str(tmp_path / "widget.ini")
    host.settings = QSettings(settings_path, QSettings.Format.IniFormat)
    host.settings.setValue("widget_mode_resume", True)
    host.settings.setValue("widget_mode_filter", "work")
    coordinator.close_for_shutdown()
    host.settings.sync()
    host.settings = QSettings(settings_path, QSettings.Format.IniFormat)
    host._ensure_widget_mode_coordinator = lambda: coordinator
    host.show()
    restore_saved_widget_workspace(host)
    assert widget.isVisible() and not host.isVisible()
    assert widget._active_filter == "work"


def test_complete_and_undo_preserve_original_status(workspace):
    host, coordinator, widget = workspace
    widget.scroll_content.findChildren(QCheckBox, "agenda_complete")[0].click()
    host.handle_task_status_changed.assert_called_once_with(2, "completed")
    assert not any(item.get("item_id") == 2 for item in widget._last_items)
    assert widget.undo_btn.isVisible()
    widget.undo_btn.click()
    host.handle_task_status_changed.assert_called_with(2, "in_progress")
    assert any(item.get("item_id") == 2 for item in widget._last_items)


def test_feedback_and_undo_are_cleared_when_context_changes(workspace):
    _, coordinator, widget = workspace
    widget.show_feedback("저장됨", undo=True)
    coordinator.controller._undo_completion = ({"item_id": 2}, "pending")

    widget.set_filter("schedule")

    assert widget.feedback_label.isHidden()
    assert widget.undo_btn.isHidden()
    assert coordinator.controller._undo_completion is None


def test_failed_completion_keeps_item_and_shows_no_false_success(workspace):
    host, coordinator, widget = workspace
    host.handle_task_status_changed.return_value = False
    widget.scroll_content.findChildren(QCheckBox, "agenda_complete")[0].click()
    assert any(item.get("item_id") == 2 for item in widget._last_items)
    assert coordinator.controller._undo_completion is None
    assert not widget.undo_btn.isVisible()


def test_work_add_uses_selected_date_and_correct_type(workspace):
    host, _, widget = workspace
    widget.set_filter("work")
    widget.add_btn.click()
    assert host.open_task_dialog.call_args.kwargs["task_type"] == "routine"
    assert host.open_task_dialog.call_args.kwargs["initial_date"] == host.current_date


def test_directive_add_uses_dedicated_dialog_instead_of_task_dialog(workspace):
    host, _, widget = workspace
    widget.set_filter("directive")
    widget.add_btn.click()

    host.open_directive_dialog.assert_called_once_with(initial_date=host.current_date)
    host.open_task_dialog.assert_not_called()


def test_text_without_time_never_routes_to_unsupported_directive_task_dialog(workspace):
    host, coordinator, _ = workspace

    coordinator.controller.handle_quick_add("검토 의견 전달")

    host.open_directive_dialog.assert_called_once_with(initial_date=host.current_date)
    host.open_task_dialog.assert_not_called()


def test_work_and_directive_filters_are_independent(workspace):
    _, _, widget = workspace

    widget.set_filter("work")
    work_titles = [
        item["title"]
        for item in widget._filter_items(widget._last_items)
        if not item.get("is_section")
    ]
    assert "회의 자료 정리" in work_titles
    assert "검토 의견 전달" not in work_titles

    widget.set_filter("directive")
    directive_titles = [
        item["title"]
        for item in widget._filter_items(widget._last_items)
        if not item.get("is_section")
    ]
    assert "회의 자료 정리" not in directive_titles
    assert "검토 의견 전달" in directive_titles


def test_all_add_menu_offers_three_types(workspace):
    host, _, widget = workspace
    with patch("calendar_app.presentation.widgets.unified_widget_mode.QMenu.exec") as execute:
        widget.add_btn.click()
    execute.assert_called_once()


def test_add_menu_exposes_directive_and_full_management(workspace):
    host, _, widget = workspace
    captured = {}

    def execute(menu, _position):
        captured["labels"] = [
            action.text() for action in menu.actions() if not action.isSeparator()
        ]
        target = next(action for action in menu.actions() if "전체 업무" in action.text())
        target.trigger()
        return target

    with patch("calendar_app.presentation.widgets.unified_widget_mode.QMenu.exec", new=execute):
        widget.add_btn.click()

    assert any("지시" in label and "추가" in label for label in captured["labels"])
    assert any(
        "지시" in label and "관리" in label or "현황" in label for label in captured["labels"]
    )
    assert any("전체 업무" in label for label in captured["labels"])
    host.open_work_management_dialog.assert_called_once_with(start_tab="schedule")


def test_date_navigation_changes_week_and_today(workspace):
    host, _, widget = workspace
    today = host.current_date
    widget.next_week_btn.click()
    assert host.current_date == today.addDays(7)
    widget.previous_week_btn.click()
    assert host.current_date == today


def test_loading_timeout_is_not_an_empty_agenda(workspace):
    host, coordinator, widget = workspace
    host._latest_directive_data = None
    coordinator.controller.force_refresh()
    assert widget._data_state == "loading"
    assert any(item.get("item_id") == 1 for item in widget._last_items)
    assert widget.scroll_content.findChildren(QPushButton, "agenda_item_title")
    coordinator.controller._loading_delayed()
    assert widget._data_state == "delayed"
    assert any(item.get("item_id") == 1 for item in widget._last_items)
    coordinator.controller.retry_refresh()
    assert widget._data_state == "loading"


def test_real_right_panel_refresh_publishes_widget_cache_while_host_hidden(workspace, monkeypatch):
    """Exercise the real scheduler -> panel loader -> widget, not prefilled work cache."""
    from types import MethodType

    from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
    from calendar_app.presentation.panels import side_panel_renderer as panels

    host, coordinator, widget = workspace
    date = host.current_date.toString("yyyy-MM-dd")
    host._latest_directive_data = None
    host._unified_widget_controller = coordinator.controller
    host.routine_frame, host.directive_frame = QWidget(), QWidget()
    host.routine_dock, host.directive_dock = Mock(), Mock()
    host.reset_frame = Mock()
    host.open_routine_add_dialog = Mock()
    # Main-panel filters must not leak into the widget's independent list.
    host.routine_status_filter = "completed"
    host.directive_status_filter = "completed"
    routine = {"id": 2, "name": "자료 정리", "status": "in_progress", "target_date": date}
    monkeypatch.setattr(
        panels.search_repo, "get_tasks_by_type_with_progress", lambda *args: [routine]
    )
    monkeypatch.setattr(
        panels.directive_repo, "get_recent_directives", lambda: [(3, "검토", "pending", "", date)]
    )
    monkeypatch.setattr(
        panels.checklist_repo, "get_task_checklist_items_for_owners", lambda *args: {}
    )
    monkeypatch.setattr(panels, "_panel_empty_items", lambda *args, **kwargs: [])
    monkeypatch.setattr(panels, "create_panel", lambda *args, **kwargs: (QWidget(), Mock()))
    for name in (
        "_ensure_refresh_scheduler",
        "mark_panel_dirty",
        "schedule_panel_refresh",
        "_flush_scheduled_refresh",
    ):
        setattr(host, name, MethodType(getattr(RefreshSchedulerMixin, name), host))
    host.load_right_panel = lambda force=False: panels.load_right_panel(host)
    coordinator.controller.force_refresh()
    assert not host.isVisible()
    assert widget._data_state == "loading"
    host._flush_scheduled_refresh()
    host._ui_refresh_timer.stop()
    assert widget._data_state == "ready"
    assert {item["item_id"] for item in widget._last_items if "item_id" in item} == {1, 2, 3}
    assert host._latest_directive_data["routine_rows"] == [routine]
    host.routine_frame.deleteLater()
    host.directive_frame.deleteLater()


@pytest.mark.parametrize("layout", ["dashboard", "magazine"])
def test_narrow_multicolumn_layout_reflows_without_changing_preference(workspace, layout):
    host, coordinator, widget = workspace
    coordinator.controller.set_layout(layout)
    widget.resize(420, 650)
    _APP.processEvents()
    index = widget.container_layout.indexOf(widget.agenda_section)
    assert widget.container_layout.getItemPosition(index) == (3, 0, 1, 1)
    assert widget.scroll.viewport().width() > 300
    assert host.settings.value("widget_mode_layout") == layout
    widget.resize(740, 650)
    _APP.processEvents()
    assert not widget._compact_layout


def test_controls_and_feedback_are_inside_one_surface(workspace):
    _, _, widget = workspace
    widget.show_feedback("저장됨", undo=True)
    for child in (
        widget.toolbar,
        widget.container,
        widget.completed_btn,
        widget.undo_btn,
        widget.size_grip,
        widget.feedback_label,
    ):
        assert widget.surface.isAncestorOf(child)
    assert widget.layout().count() == 1


def test_customization_preview_rescales_when_controls_take_more_width(workspace):
    from PyQt6.QtWidgets import QScrollArea, QTabWidget

    _, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.show()
    dialog.findChild(QTabWidget).setCurrentIndex(1)
    _APP.processEvents()
    pixmap = dialog.preview_label.pixmap()
    assert pixmap.width() / pixmap.devicePixelRatio() <= dialog.preview_label.width()
    controls = dialog.findChild(QScrollArea)
    assert dialog.skin_combo.parentWidget().width() <= controls.viewport().width()
    assert dialog.skin_combo.geometry().right() < dialog.skin_combo.parentWidget().width()
    dialog.close()
    dialog.deleteLater()


def test_font_picker_has_an_explicit_dropdown_button(workspace):
    _, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)

    assert isinstance(dialog.font_dropdown_btn, QToolButton)
    assert dialog.font_dropdown_btn.arrowType() == Qt.ArrowType.DownArrow
    assert dialog.font_dropdown_btn.width() == 38
    assert dialog.font_dropdown_btn.accessibleName()
    dialog.close()
    dialog.deleteLater()


def test_hint_toggle_is_reflected_in_every_layout_preview(workspace):
    _, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)

    for layout in ("minimal", "dashboard", "magazine"):
        dialog._change("widget_mode_layout", layout)
        dialog._change("widget_mode_show_hint", True)
        assert not dialog.preview.hint_label.isHidden()
        assert dialog.preview.hint_label.text()
        dialog._change("widget_mode_show_hint", False)
        assert dialog.preview.hint_label.isHidden()
    dialog.close()
    dialog.deleteLater()


def test_customization_keeps_calendar_visibility_independent_per_layout(workspace):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_show_week", False)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)

    dialog._change("widget_mode_layout", "dashboard")
    assert dialog.calendar_visibility_checkbox.isChecked()
    dialog.calendar_visibility_checkbox.setChecked(False)
    assert dialog.preview.cal_grid.isHidden()

    dialog._change("widget_mode_layout", "magazine")
    assert dialog.calendar_visibility_checkbox.isChecked()
    assert not dialog.preview.cal_grid.isHidden()

    dialog._change("widget_mode_layout", "dashboard")
    assert not dialog.calendar_visibility_checkbox.isChecked()
    assert dialog.preview.cal_grid.isHidden()
    assert host.settings.value("widget_mode_calendar_visible_dashboard") is None
    dialog.reject()
    dialog.deleteLater()


def test_font_preferences_survive_reopened_qsettings(workspace, tmp_path):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QFont

    host, coordinator, widget = workspace
    path = str(tmp_path / "widget.ini")
    host.settings = QSettings(path, QSettings.Format.IniFormat)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog.font_family.setCurrentFont(QFont("Arial"))
    selected_family = dialog.font_family.currentFont().family()
    # Trigger the same public signal even if Arial was already selected by fallback.
    dialog.font_family.currentFontChanged.emit(dialog.font_family.currentFont())
    dialog.font_size.setValue(16)
    dialog.font_weight.setCurrentIndex(dialog.font_weight.findData(700))
    assert host.settings.value("widget_mode_font_family") is None
    assert dialog.preview.font().family() == selected_family
    dialog._apply()
    widget.set_filter("work")
    coordinator.controller.set_always_top(False)
    coordinator.close_for_shutdown()
    host.settings.sync()
    host.settings = QSettings(path, QSettings.Format.IniFormat)
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    assert fresh.widget.font().family() == selected_family
    assert int(host.settings.value("widget_mode_font_size")) == 16
    assert int(host.settings.value("widget_mode_font_weight")) == 700
    assert fresh.widget._active_filter == "work"
    assert "font-weight: 700" in fresh.widget.styleSheet()
    assert not fresh.widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    fresh.hide_widget()
    fresh.widget.deleteLater()
    dialog.deleteLater()


def test_returning_to_cached_date_restores_list_after_loading(workspace):
    host, coordinator, widget = workspace
    original = host.current_date
    coordinator.controller.set_target_date(original.addDays(1))
    assert widget._data_state == "loading"
    coordinator.controller.set_target_date(original)
    assert widget._data_state == "ready"
    assert any(item.get("item_id") == 1 for item in widget._last_items)


def test_customization_cancel_has_no_settings_or_geometry_side_effects(workspace):
    host, coordinator, widget = workspace
    before = dict(host.settings.values)
    geometry = widget.geometry()
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog._change("widget_mode_layout", "dashboard")
    dialog._change("widget_mode_skin", "classic_dark")
    dialog._change("widget_mode_font_size", 16)
    dialog._change("widget_mode_font_family", "Arial")
    dialog._change("widget_mode_font_weight", 700)
    assert host.settings.values == before
    assert widget.geometry() == geometry
    assert not dialog.preview_label.pixmap().isNull()
    dialog.reject()
    dialog.deleteLater()
    assert host.settings.values == before


def test_customization_apply_and_fresh_controller_restore(workspace):
    host, coordinator, widget = workspace
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog._change("widget_mode_layout", "minimal")
    dialog._change("widget_mode_skin", "classic_dark")
    dialog._change("widget_mode_show_clock", False)
    dialog._change("widget_mode_font_size", 15)
    dialog._apply()
    assert widget.active_layout_id() == "minimal"
    assert not widget.clock_label.isVisible()
    assert host.settings.value("widget_mode_skin") == "classic_dark"
    assert host.settings.value("widget_mode_font_size") == 15
    widget.set_filter("work")
    coordinator.close_for_shutdown()
    fresh = UnifiedWidgetController(host)
    fresh.show_widget()
    assert fresh.widget._active_filter == "work"
    assert fresh.widget.active_layout_id() == "minimal"
    assert not fresh.widget.clock_label.isVisible()
    fresh.widget.hide()
    fresh.widget.deleteLater()
    dialog.deleteLater()


def test_color_preview_does_not_change_layout_without_an_explicit_saved_layout(workspace):
    host, coordinator, widget = workspace
    host.settings.values.pop("widget_mode_layout", None)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    dialog._change("widget_mode_skin", "midnight_blue")
    assert dialog.preview.active_layout_id() == "stacked"
    dialog._apply()
    assert widget.active_layout_id() == "stacked"
    dialog.deleteLater()


def test_refresh_hides_old_items_before_deferred_deletion(workspace):
    _, coordinator, widget = workspace
    old = widget.scroll_layout.itemAt(1).widget()
    assert old.isVisible()
    coordinator.controller.set_skin("classic_dark")
    assert old.isHidden()


def test_list_layout_never_overlaps_rows_when_window_is_small(workspace):
    _, coordinator, widget = workspace
    widget.resize(350, 460)
    _APP.processEvents()
    rectangles = [
        widget.scroll_layout.itemAt(i).geometry() for i in range(widget.scroll_layout.count() - 1)
    ]
    assert all(
        previous.bottom() < following.top()
        for previous, following in zip(rectangles, rectangles[1:], strict=False)
    )


def test_completed_items_can_be_shown_without_losing_original_status(workspace):
    host, coordinator, widget = workspace
    item = next(item for item in widget._last_items if item.get("item_id") == 3)
    coordinator.controller.set_item_completed(item, True)
    widget.completed_btn.click()
    completed = next(item for item in widget._last_items if item.get("item_id") == 3)
    assert completed["completed"] is True
    assert host.handle_directive_status_changed.call_args.args == (3, "completed")


def test_return_to_main_works_when_mode_was_opened_from_hidden_host(workspace):
    host, coordinator, widget = workspace
    coordinator.hide_to_tray()
    coordinator.enter()
    widget.restore_btn.click()
    assert host.isVisible()
    assert not widget.isVisible()


def test_widget_list_does_not_silently_truncate_work(workspace):
    host, coordinator, widget = workspace
    date = host.current_date.toString("yyyy-MM-dd")
    host._latest_directive_data["routine_rows"] = [
        {"id": number, "name": str(number), "target_date": date, "status": "pending"}
        for number in range(20, 36)
    ]
    coordinator.controller.force_refresh()
    assert (
        len(
            [
                item
                for item in widget._last_items
                if item.get("source") == "task" and item.get("is_task")
            ]
        )
        == 16
    )
