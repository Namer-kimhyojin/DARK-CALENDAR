# -*- coding: utf-8 -*-
"""Reading continuity, action discovery and processing feedback regressions."""

from unittest.mock import patch

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
import pytest

from calendar_app.infrastructure.i18n import t
from tests.test_widget_mode_ux import _APP, workspace  # noqa: F401


def _items(count=35):
    return [{"is_section": True, "title": "업무"}] + [
        {
            "source": "task",
            "item_id": index + 10,
            "item_kind": "work",
            "is_task": True,
            "title": f"검토할 업무 {index}",
            "time": "오늘 마감",
        }
        for index in range(count)
    ]


def _flush():
    for _ in range(3):
        _APP.processEvents()


def _render(widget, items=None):
    widget.controller.refresh_data = lambda: None
    widget.resize(420, 520)
    widget.update_agenda(items or _items())
    _flush()


@pytest.mark.parametrize("layout", ["stacked", "dashboard", "magazine"])
def test_calendar_action_matches_visibility_in_each_layout(workspace, layout):
    _, coordinator, widget = workspace
    coordinator.controller.set_layout(layout)
    _flush()
    expected = (
        "widget_mode.calendar_collapse"
        if widget.week_toggle_btn.isChecked()
        else "widget_mode.calendar_expand"
    )
    assert widget.week_toggle_btn.text() == t(expected)
    widget.week_toggle_btn.click()
    _flush()
    expected = (
        "widget_mode.calendar_collapse"
        if widget.week_toggle_btn.isChecked()
        else "widget_mode.calendar_expand"
    )
    assert widget.week_toggle_btn.accessibleName() == t(expected)


def test_toolbar_labels_expand_and_window_can_shrink_back(workspace):
    _, _, widget = workspace
    widget.resize(760, 600)
    _flush()
    assert widget.restore_btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert widget.customize_btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    widget.resize(320, 480)
    _flush()
    assert widget.width() == 320
    assert widget.restore_btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert widget.week_toggle_btn.text()


def test_same_context_refresh_preserves_visible_anchor_and_checkbox_focus(workspace):
    _, _, widget = workspace
    _render(widget)
    focused = widget._agenda_rows[16].findChild(QPushButton, "agenda_item_title")
    focused.setFocus()
    widget.scroll.ensureWidgetVisible(focused)
    _flush()
    anchor = next(
        row
        for row in widget._agenda_rows
        if row.mapTo(widget.scroll.viewport(), QPoint()).y() + row.height() > 0
    )
    key = anchor.item_key
    offset = anchor.mapTo(widget.scroll.viewport(), QPoint()).y()
    items = _items()
    items[-1]["title"] = "백그라운드에서 갱신됨"
    widget.update_agenda(items)
    _flush()
    restored = next(row for row in widget._agenda_rows if row.item_key == key)
    assert abs(restored.mapTo(widget.scroll.viewport(), QPoint()).y() - offset) <= 2
    assert QApplication.focusWidget().parent().item_key == ("task", 26)


def test_removed_focused_item_moves_to_next_neighbor(workspace):
    _, _, widget = workspace
    _render(widget)
    widget._agenda_rows[12].findChild(QPushButton, "agenda_item_title").setFocus()
    _flush()
    widget.update_agenda([item for item in _items() if item.get("item_id") != 22])
    _flush()
    assert QApplication.focusWidget().parent().item_key == ("task", 23)


def test_date_and_filter_change_reset_scroll(workspace):
    _, coordinator, widget = workspace
    _render(widget)
    widget.scroll.verticalScrollBar().setValue(650)
    widget.set_filter("work")
    _flush()
    assert widget.scroll.verticalScrollBar().value() == 0
    widget.scroll.verticalScrollBar().setValue(650)
    coordinator.controller.main_window.current_date = (
        coordinator.controller._current_date().addDays(1)
    )
    widget.update_agenda(_items())
    _flush()
    assert widget.scroll.verticalScrollBar().value() == 0


def test_deferred_restore_respects_new_toolbar_focus(workspace):
    _, _, widget = workspace
    _render(widget)
    widget._agenda_rows[12].findChild(QPushButton, "agenda_item_title").setFocus()
    items = _items()
    items[-1]["title"] = "변경"
    widget.update_agenda(items)
    widget.customize_btn.setFocus()
    _flush()
    assert widget.customize_btn.hasFocus()


def test_unchanged_render_keeps_row_objects_and_scroll(workspace):
    _, _, widget = workspace
    _render(widget)
    rows = list(widget._agenda_rows)
    widget.scroll.verticalScrollBar().setValue(650)
    value = widget.scroll.verticalScrollBar().value()
    widget.update_agenda(_items())
    _flush()
    assert widget._agenda_rows == rows
    assert widget.scroll.verticalScrollBar().value() == value


def test_named_feedback_and_focused_undo_survive_expiration(workspace):
    host, coordinator, widget = workspace
    item = next(item for item in widget._last_items if item.get("item_id") == 2)
    coordinator.controller.set_item_completed(item, True)
    assert item["title"] in widget.feedback_label.text()
    widget.undo_btn.setFocus()
    widget._expire_feedback()
    assert widget.undo_btn.isVisible()
    assert coordinator.controller._undo_completion is not None
    host.handle_task_status_changed.return_value = False
    widget.undo_btn.click()
    assert item["title"] in widget.feedback_label.text()
    assert widget.undo_btn.isVisible()
    assert coordinator.controller._undo_completion is not None
    host.handle_task_status_changed.return_value = True
    widget.undo_btn.click()
    host.handle_task_status_changed.assert_called_with(2, "in_progress")
    assert item["title"] in widget.feedback_label.text()
    assert not widget.undo_btn.isVisible()


def test_filtered_empty_explains_other_types_and_counts_context(workspace):
    _, _, widget = workspace
    _render(widget)
    widget.set_filter("schedule")
    _flush()
    labels = widget.scroll_content.findChildren(QLabel, "unified_hint")
    assert any("35" in label.text() for label in labels)
    assert "0/35" in widget.count_chip.accessibleName()
    assert widget.controller._current_date().toString("yyyy-MM-dd") in widget.count_chip.toolTip()


@pytest.mark.parametrize("density,lines", [("compact", 1), ("standard", 2), ("comfortable", 2)])
def test_long_titles_wrap_by_density_and_keep_full_accessible_text(workspace, density, lines):
    host, _, widget = workspace
    host.settings.setValue("widget_mode_density", density)
    items = _items(1)
    items[1]["title"] = (
        "예산 검토와 회의 자료를 준비하고 관계 기관의 검토 의견을 정리하는 매우 긴 업무 제목 " * 3
    )
    _render(widget, items)
    title = widget._agenda_rows[0].findChild(QPushButton, "agenda_item_title")
    assert len(title.text().splitlines()) == lines
    assert items[1]["title"].strip() in title.accessibleName()
    assert title.toolTip() == items[1]["title"].strip()


def test_more_menu_groups_and_retains_management_actions(workspace):
    _, _, widget = workspace
    captured = []

    def execute(menu, _position):
        captured.extend(action.text() for action in menu.actions())
        return None

    with patch("calendar_app.presentation.widgets.unified_widget_mode.QMenu.exec", new=execute):
        widget._open_menu(QPoint())
    groups = [t(f"widget_mode.menu_{name}") for name in ("date", "work", "view", "window")]
    assert [captured.index(group) for group in groups] == sorted(
        captured.index(group) for group in groups
    )
    assert t("widget_mode.customize") in captured
    assert t("menu.work_management") in captured


def test_failed_completion_restores_check_and_keeps_focus(workspace):
    host, _, widget = workspace
    from PyQt6.QtWidgets import QCheckBox

    check = next(row for row in widget._agenda_rows if row.item_key == ("task", 2)).findChild(
        QCheckBox, "agenda_complete"
    )
    check.setFocus()
    host.handle_task_status_changed.return_value = False
    check.click()
    _flush()
    assert not check.isChecked()
    assert check.hasFocus()


@pytest.mark.parametrize("source,item_id", [(None, None), ("task", 77)])
def test_missing_or_duplicate_ids_do_not_merge_distinct_rows(workspace, source, item_id):
    _, _, widget = workspace
    items = [
        {"title": "첫 항목", "source": source, "item_id": item_id},
        {"title": "두 번째 항목", "source": source, "item_id": item_id},
    ]
    _render(widget, items)
    items[1]["title"] = "수정한 두 번째 항목"
    widget.update_agenda(items)
    _flush()
    assert len(widget._agenda_rows) == 2
    assert widget._agenda_rows[0] is not widget._agenda_rows[1]
    assert {
        row.findChild(QPushButton, "agenda_item_title").toolTip()
        if item_id
        else row.findChild(QLabel, "agenda_item_title").toolTip()
        for row in widget._agenda_rows
    } == {"첫 항목", "수정한 두 번째 항목"}


def test_long_feedback_keeps_reading_space_and_full_accessible_message(workspace):
    _, _, widget = workspace
    widget.resize(320, 480)
    message = "아주 긴 업무 제목 " * 60
    widget.show_feedback(message, undo=True)
    _flush()
    assert widget.feedback_label.height() <= widget.feedback_label.fontMetrics().height() * 2 + 4
    assert widget.feedback_label.accessibleName() == message
    assert widget.feedback_label.toolTip() == message
    assert widget.scroll.viewport().height() > 100


@pytest.mark.parametrize("outcome", ["saved", "failed", "undone"])
def test_long_named_feedback_visible_result_precedes_full_title(workspace, outcome):
    host, coordinator, widget = workspace
    widget.resize(320, 480)
    item = dict(next(item for item in widget._last_items if item.get("item_id") == 2))
    item["title"] = "긴 항목 제목" * 60
    if outcome == "failed":
        host.handle_task_status_changed.return_value = False
    coordinator.controller.set_item_completed(item, True)
    if outcome == "undone":
        coordinator.controller.undo_completion()
    _flush()
    message = widget.feedback_label.text()
    named_keys = {
        "saved": "saved_status_named",
        "failed": "save_failed_named",
        "undone": "undone_named",
    }
    marker = "__TITLE_SENTINEL__"
    result_prefix = (
        t(f"widget_mode.{named_keys[outcome]}", name=marker, status=t("status.completed", "완료"))
        .split(marker)[0]
        .strip()
    )
    assert result_prefix
    assert message.startswith(result_prefix)
    assert message.index(result_prefix) < message.index(item["title"])
    assert item["title"] in widget.feedback_label.accessibleName()
    assert item["title"] in widget.feedback_label.toolTip()
    assert widget.feedback_label.height() <= widget.feedback_label.fontMetrics().height() * 2 + 4


@pytest.mark.parametrize(
    "layout,density",
    [
        ("dashboard", "standard"),
        ("agenda_first", "comfortable"),
        ("minimal", "standard"),
        ("stacked", "standard"),
    ],
)
def test_two_line_titles_and_time_do_not_overlap_in_long_lists(workspace, layout, density):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_density", density)
    coordinator.controller.set_layout(layout)
    items = _items(30)
    items[1]["title"] = "긴 제목의 일정과 업무를 여러 번 갱신해도 시간이 겹치지 않아야 합니다 " * 4
    _render(widget, items)
    row = widget._agenda_rows[0]
    title = row.findChild(QPushButton, "agenda_item_title")
    time = row.findChild(QLabel, "agenda_item_time")
    assert len(title.text().splitlines()) == 2
    assert not title.geometry().intersects(time.geometry())
