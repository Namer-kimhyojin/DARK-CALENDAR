# -*- coding: utf-8 -*-
"""Completing an item refreshes only the panels that can show it; hidden panels wait.

Ticking a routine in widget-only mode used to rebuild all three main-window panels
(about 0.7 s on a seeded database) although the main window was hidden and only the
right panel lists routines. A status change now refreshes the panels whose queries
list the task's type. While widget-only mode hides both right-panel frames,
``load_right_panel`` only publishes the widget's data and builds the panel when a
frame is shown again, before the window's first paint.
"""

import logging
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QObject, QPoint, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QFrame,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.main_window import action_handlers_tasks
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.main_window.calendar_view_actions import CalendarViewActionsMixin
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin
from calendar_app.presentation.panels import side_panel_renderer

_APP = QApplication.instance() or QApplication([])


class _Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def _pump(seconds=0.0):
    deadline = time.perf_counter() + seconds
    while True:
        _APP.processEvents()
        _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        if time.perf_counter() >= deadline:
            return
        time.sleep(0.002)


# --------------------------------------------------------------------------- status change


class _StatusHost(TaskActionsMixin):
    def __init__(self):
        self.refreshes = []

    def schedule_panel_refresh(self, left=False, center=False, right=False, **_kwargs):
        self.refreshes.append((left, center, right))

    def _refresh_all_panels(self):
        self.refreshes.append("all")


def _change_status(monkeypatch, task, *, saved=True):
    def get_unified_task(_task_id):
        if isinstance(task, Exception):
            raise task
        return task

    monkeypatch.setattr(
        action_handlers_tasks,
        "task_usecases",
        SimpleNamespace(update_task_status=lambda *_args: saved),
    )
    monkeypatch.setattr(
        action_handlers_tasks, "db_task", SimpleNamespace(get_unified_task=get_unified_task)
    )
    host = _StatusHost()
    return host.handle_task_status_changed(7, "completed"), host.refreshes


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ({"type": "routine"}, (False, False, True)),
        ({"type": "schedule"}, (True, True, False)),
        (
            {"type": "event", "gcal_sync_mode": "remote_mirror", "gcal_event_id": "abc"},
            (True, True, False),
        ),
    ],
)
def test_status_change_refreshes_only_panels_listing_the_task(monkeypatch, task, expected):
    assert _change_status(monkeypatch, task) == (True, [expected])


@pytest.mark.parametrize(
    "task",
    [
        None,
        {"type": "event"},
        {"type": "event", "gcal_sync_mode": "remote_mirror", "gcal_event_id": "  "},
        RuntimeError("database is locked"),
    ],
)
def test_status_change_of_unknown_task_refreshes_every_panel(monkeypatch, task):
    assert _change_status(monkeypatch, task) == (True, ["all"])


def test_failed_status_change_refreshes_nothing(monkeypatch):
    assert _change_status(monkeypatch, {"type": "routine"}, saved=False) == (False, [])


# --------------------------------------------------------------------------- deferred right panel


class _TitleBar(QWidget):
    def bind_dock(self, dock):
        self.dock = dock


class _DockHost(CalendarViewActionsMixin, RefreshSchedulerMixin, QMainWindow):
    reset_frame = staticmethod(WindowShellActionsMixin.reset_frame)

    def __init__(self):
        super().__init__()
        self.settings = _Settings()
        self.current_date = QDate.currentDate()
        self.selected_task_ids = set()
        self.setCentralWidget(QWidget())
        for name in ("routine", "directive"):
            frame = QFrame()
            dock = QDockWidget(name, self)
            dock.setObjectName(f"{name}_dock")
            dock.setWidget(frame)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            setattr(self, f"{name}_frame", frame)
            setattr(self, f"{name}_dock", dock)


class _SpyHost(_DockHost):
    def __init__(self):
        super().__init__()
        self.widget_mode = False
        self.widget_refreshes = 0

    def is_widget_mode_active(self):
        return self.widget_mode

    def refresh_widget_mode_panels(self, schedule=True, work=True):
        self.widget_refreshes += 1


class _FramePaints(QObject):
    """Logs the first paint of anything inside the right-panel frames."""

    def __init__(self, host, log):
        super().__init__()
        self._frames = (host.routine_frame, host.directive_frame)
        self._log = log

    def eventFilter(self, obj, event):  # noqa: N802
        if (
            event.type() == QEvent.Type.Paint
            and isinstance(obj, QWidget)
            and ("paint",) not in self._log
            and any(obj is frame or frame.isAncestorOf(obj) for frame in self._frames)
        ):
            self._log.append(("paint",))
        return False


@pytest.fixture
def spy_host(monkeypatch):
    log = []
    host = _SpyHost()

    def render(app):
        log.append(("render", app.routine_frame.isVisible()))
        for frame in (app.routine_frame, app.directive_frame):
            app.reset_frame(frame)
            layout = QVBoxLayout()
            layout.addWidget(QLabel(f"render {len(log)}"))
            frame.setLayout(layout)

    monkeypatch.setattr(side_panel_renderer, "load_right_panel", render)
    monkeypatch.setattr(
        side_panel_renderer,
        "publish_right_panel_data",
        lambda _app: log.append(("publish",)),
        raising=False,
    )
    yield host, log
    if hasattr(host, "_ui_refresh_timer"):
        host._ui_refresh_timer.stop()
    host.hide()
    host.deleteLater()
    _pump()


def test_hidden_right_panel_only_publishes_in_widget_mode(spy_host):
    host, log = spy_host
    host.widget_mode = True
    controller = Mock()
    host._unified_widget_controller = controller
    for _ in range(3):
        host.schedule_panel_refresh(right=True)
        host._flush_scheduled_refresh()
    assert log == [("publish",)] * 3
    assert host._right_panel_render_deferred
    assert host.widget_refreshes == 3
    assert controller.refresh_data.call_count == 3


def _visible_panel_texts(host):
    return sorted(
        label.text()
        for frame in (host.routine_frame, host.directive_frame)
        for label in frame.findChildren(QLabel)
        if label.isVisible()
    )


def test_deferred_right_panel_is_built_and_shown_inside_show(spy_host):
    host, log = spy_host
    host.load_right_panel(force=True)
    host.widget_mode = True
    host.load_right_panel(force=False)
    paints = _FramePaints(host, log)
    _APP.installEventFilter(paints)
    try:
        host.show()
        # Built inside show() before any paint, and already the visible panel: a
        # window shown while a click is handled is painted before queued shows run.
        assert log == [("render", False), ("publish",), ("render", True)]
        assert _visible_panel_texts(host) == ["render 3", "render 3"]
        _pump(0.05)
    finally:
        _APP.removeEventFilter(paints)
    assert log.count(("render", True)) == 1
    assert _visible_panel_texts(host) == ["render 3", "render 3"]
    assert not host._right_panel_render_deferred


def test_right_panel_is_built_while_hidden_outside_widget_mode(spy_host):
    host, log = spy_host
    host.load_right_panel(force=True)
    assert log == [("render", False)]
    assert not host._right_panel_render_deferred


def test_visible_floating_right_dock_is_built_in_widget_mode(spy_host):
    host, log = spy_host
    host.show()
    host.routine_dock.setFloating(True)
    _pump()
    host.widget_mode = True
    host.hide()
    _pump()
    assert host.routine_frame.isVisible() and not host.directive_frame.isVisible()
    log.clear()
    host.load_right_panel(force=True)
    assert log == [("render", True)]
    host.routine_dock.setFloating(False)


def test_deferred_build_is_not_skipped_by_unchanged_signature(spy_host):
    host, log = spy_host
    host.load_right_panel(force=True)
    host.widget_mode = True
    host.load_right_panel(force=False)
    # Widget mode ended without showing a frame (hidden to the tray).
    host.widget_mode = False
    host._ensure_refresh_scheduler()
    host._panel_dirty["right"] = False
    host.load_right_panel(force=False)
    assert log == [("render", False), ("publish",), ("render", False)]
    assert not host._right_panel_render_deferred


def test_shutdown_never_defers_the_right_panel(spy_host):
    host, log = spy_host
    host.widget_mode = True
    host._is_shutting_down = True
    host.load_right_panel(force=True)
    assert log == [("render", False)]


def test_show_after_shutdown_started_does_not_build_the_deferred_panel(spy_host):
    host, log = spy_host
    host.load_right_panel(force=True)
    host.widget_mode = True
    host.load_right_panel(force=False)
    host._is_shutting_down = True
    host.show()
    _pump()
    assert log == [("render", False), ("publish",)]


def test_failed_deferred_build_is_retried_by_the_next_load(spy_host, monkeypatch, caplog):
    host, log = spy_host
    host.load_right_panel(force=True)
    host.widget_mode = True
    host.load_right_panel(force=False)
    render = side_panel_renderer.load_right_panel
    failures = []

    def failing_render(app):
        # Fails on both frames' Show events, then works.
        if len(failures) < 2:
            failures.append(app)
            raise RuntimeError("render failed")
        render(app)

    monkeypatch.setattr(side_panel_renderer, "load_right_panel", failing_render)
    with caplog.at_level(logging.ERROR):
        host.show()
    assert len(failures) == 2
    assert "Deferred right panel render failed" in caplog.text
    assert host._right_panel_render_deferred
    # An unchanged signature and a clean dirty flag must not skip the retry.
    host._ensure_refresh_scheduler()
    host._panel_dirty["right"] = False
    host.load_right_panel(force=False)
    assert log == [("render", False), ("publish",), ("render", True)]
    assert not host._right_panel_render_deferred


# --------------------------------------------------------------------------- real database


@pytest.fixture
def temp_db(tmp_path):
    from calendar_app.infrastructure.db import database_unified

    original = database_unified.DB_PATH
    database_unified.db_manager.close_all_connections()
    database_unified.DB_PATH = str(tmp_path / "test.db")
    database_unified.initialize_unified_database()
    yield
    database_unified.db_manager.close_all_connections()
    database_unified.DB_PATH = original


def _add_routine(name, target_date, status):
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo

    return unified_repo.create_unified_task(
        {
            "name": name,
            "type": "routine",
            "priority": "normal",
            "status": status,
            "target_date": target_date.toString("yyyy-MM-dd"),
        }
    )


def _add_directive(content, deadline, status):
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo

    conn = unified_repo.get_connection()
    cur = conn.execute(
        "INSERT INTO task_directive (content, status, deadline) VALUES (?, ?, ?)",
        (content, status, deadline.toString("yyyy-MM-dd")),
    )
    conn.commit()
    return cur.lastrowid


def _stub_panel_widgets(monkeypatch):
    """Light panel widgets: one QLabel per task, real frames, docks and queries."""

    def create_panel(_app, _title, items, **_kwargs):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        for item in items:
            layout.addWidget(item)
        return panel, _TitleBar()

    monkeypatch.setattr(side_panel_renderer, "create_panel", create_panel)
    monkeypatch.setattr(
        side_panel_renderer, "create_task_box", lambda _app, title, *_a, **_k: QLabel(title)
    )
    monkeypatch.setattr(side_panel_renderer, "_panel_empty_items", lambda *_a, **_k: [])


def _normalized(data):
    return (
        data["context_date"],
        [sorted(row.items()) for row in data["routine_rows"]],
        [tuple(row) for row in data["directive_rows"]],
    )


def test_publish_matches_the_data_a_full_render_publishes(temp_db, monkeypatch):
    _stub_panel_widgets(monkeypatch)
    today = QDate.currentDate()
    expected_ids = {
        _add_routine("today pending", today, "pending"),
        _add_routine("today done", today, "completed"),
        _add_routine("overdue", today.addDays(-3), "in_progress"),
    }
    # Completed now, but its (monthly) period ended in an earlier month: never due today.
    _add_routine("done earlier", today.addDays(-40), "completed")
    _add_directive("review", today, "in_progress")
    _add_directive("send", today.addDays(2), "completed")
    host = _DockHost()
    try:
        side_panel_renderer.load_right_panel(host)
        # _normalized() converts rows, so check the published type here.
        assert all(isinstance(row, tuple) for row in host._latest_directive_data["directive_rows"])
        rendered = _normalized(host._latest_directive_data)
        host._latest_directive_data = None
        side_panel_renderer.publish_right_panel_data(host)
        assert _normalized(host._latest_directive_data) == rendered
        assert {row["id"] for row in host._latest_directive_data["routine_rows"]} == expected_ids
        assert len(host._latest_directive_data["directive_rows"]) == 2
    finally:
        host.deleteLater()
        _pump()


class _WorkHost(TaskActionsMixin, _DockHost):
    is_widget_mode_active = WindowShellActionsMixin.is_widget_mode_active
    refresh_widget_mode_panels = WindowShellActionsMixin.refresh_widget_mode_panels

    def __init__(self):
        super().__init__()
        today = self.current_date
        self._latest_calendar_range_data = {
            "range_start": today.addDays(-30).toString("yyyy-MM-dd"),
            "range_end": today.addDays(30).toString("yyyy-MM-dd"),
            "rows": [],
        }
        self._latest_directive_data = None
        self._widget_mode_coordinator = None
        self._unified_widget_controller = None
        self.renders = {"left": 0, "center": 0}
        for name in (
            "open_task_dialog",
            "open_modify_task_dialog",
            "open_directive_dialog",
            "open_work_management_dialog",
            "open_routine_add_dialog",
        ):
            setattr(self, name, Mock())

    def load_left_panel(self, force=True):
        self.renders["left"] += 1

    def load_center_panel(self, force=True):
        self.renders["center"] += 1


def _routine_texts(host):
    return sorted(
        label.text()
        for label in host.routine_frame.findChildren(QLabel)
        if label.isVisibleTo(host.routine_frame) and not label.property("replaced")
    )


def test_ticking_a_routine_in_widget_mode_builds_no_panel_until_main_returns(temp_db, monkeypatch):
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo
    from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator

    _stub_panel_widgets(monkeypatch)
    renders = {"right": 0, "publish": 0}
    real_render = side_panel_renderer.load_right_panel
    real_publish = getattr(side_panel_renderer, "publish_right_panel_data", None)
    real_reset = WindowShellActionsMixin.reset_frame

    def render(app):
        renders["right"] += 1
        real_render(app)

    def publish(app):
        renders["publish"] += 1
        real_publish(app)

    def reset_frame(frame):
        # Mark the replaced labels so the panel text ignores them until deleteLater runs.
        for label in frame.findChildren(QLabel):
            label.setProperty("replaced", True)
        real_reset(frame)

    monkeypatch.setattr(side_panel_renderer, "load_right_panel", render)
    if real_publish is not None:
        monkeypatch.setattr(side_panel_renderer, "publish_right_panel_data", publish)
    monkeypatch.setattr(_WorkHost, "reset_frame", staticmethod(reset_frame))
    today = QDate.currentDate()
    routine_id = _add_routine("write minutes", today, "pending")
    _add_routine("water plants", today, "pending")

    host = _WorkHost()
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    host._unified_widget_controller = coordinator.controller
    try:
        host.settings.setValue("widget_mode_show_completed", "true")
        host.load_right_panel()
        host.show()
        _pump()
        coordinator.enter("work")
        _pump()
        assert not host.isVisible()
        widget = coordinator.controller.widget
        check = next(
            row.findChild(QCheckBox, "agenda_complete")
            for row in widget._agenda_rows
            if getattr(row, "item_key", None) == ("task", routine_id)
        )
        before = dict(renders)
        check.click()
        _pump(0.1)
        assert renders["right"] == before["right"]
        assert renders["publish"] == before["publish"] + 1
        assert host.renders == {"left": 0, "center": 0}
        assert unified_repo.get_unified_task(routine_id)["status"] == "completed"
        published = {row["id"]: row for row in host._latest_directive_data["routine_rows"]}
        assert published[routine_id]["status"] == "completed"
        item = next(i for i in widget._last_items if i.get("item_id") == routine_id)
        assert item["completed"]

        first_paint = {}

        class _MainPaint(QObject):
            def eventFilter(self, obj, event):  # noqa: N802
                if (
                    event.type() == QEvent.Type.Paint
                    and isinstance(obj, QWidget)
                    and obj.window() is host
                    and not first_paint
                ):
                    first_paint["texts"] = _routine_texts(host)
                return False

        main_paint = _MainPaint()
        _APP.installEventFilter(main_paint)
        try:
            before = renders["right"]
            coordinator.exit_widget_mode()
            assert renders["right"] == before + 1
            assert host.isVisible()
            _pump(0.1)
        finally:
            _APP.removeEventFilter(main_paint)
        assert not host._right_panel_render_deferred
        settled = _routine_texts(host)
        host.load_right_panel(force=True)
        _pump()
        assert first_paint["texts"] == settled == _routine_texts(host)
        assert host.renders == {"left": 0, "center": 0}
    finally:
        coordinator.close_for_shutdown()
        coordinator.controller.widget.deleteLater()
        if hasattr(host, "_ui_refresh_timer"):
            host._ui_refresh_timer.stop()
        host.close()
        host.deleteLater()
        _pump()


def test_directives_from_the_database_are_listed_in_widget_mode(temp_db, monkeypatch):
    """The database returns sqlite3.Row rows, but the widget lists tuple or list rows only.

    Before rows were published as tuples, widget-only mode never showed a directive.
    """
    from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator

    _stub_panel_widgets(monkeypatch)
    today = QDate.currentDate()
    review_id = _add_directive("review contract", today, "pending")
    _add_directive("send invoice", today.addDays(3), "pending")

    host = _WorkHost()
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    host._unified_widget_controller = coordinator.controller
    try:
        host.load_right_panel()
        host.show()
        _pump()
        coordinator.enter("all")
        _pump()
        rows = host._latest_directive_data["directive_rows"]
        assert len(rows) == 2
        assert all(isinstance(row, tuple) for row in rows)
        titles = [
            item["title"]
            for item in coordinator.controller.widget._last_items
            if not item.get("is_section")
        ]
        assert "review contract" in titles
        assert "send invoice" not in titles
        visible = [row.item_key for row in coordinator.controller.widget._agenda_rows]
        assert ("directive", review_id) in visible
    finally:
        coordinator.close_for_shutdown()
        coordinator.controller.widget.deleteLater()
        if hasattr(host, "_ui_refresh_timer"):
            host._ui_refresh_timer.stop()
        host.close()
        host.deleteLater()
        _pump()


class _FocusWorkHost(_WorkHost):
    _is_text_input_focused = WindowShellActionsMixin._is_text_input_focused


def test_widget_menu_deletes_a_directive_while_the_search_box_has_focus(temp_db, monkeypatch):
    """The item menu leaves focus in the widget's search box, as a QMenu does not take it.

    The text-input guard meant for the Del key then dropped the delete without asking.
    Only an unpinned widget kept that focus: unpinning around the dialog recreates the window.
    """
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo
    from calendar_app.infrastructure.i18n import t
    from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator

    _stub_panel_widgets(monkeypatch)
    _add_directive("cancel order", QDate.currentDate(), "pending")
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_k: asked.append(1) or QMessageBox.StandardButton.Yes),
    )
    delete_text = t("widget_mode.menu_delete_directive", "삭제")
    monkeypatch.setattr(
        QMenu,
        "exec",
        lambda menu, *_a: next(a for a in menu.actions() if a.text() == delete_text),
    )

    host = _FocusWorkHost()
    host.settings.setValue("widget_mode_always_top", False)
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    host._unified_widget_controller = coordinator.controller
    try:
        host.load_right_panel()
        host.show()
        _pump()
        coordinator.enter("work")
        _pump()
        coordinator.controller.set_layout("day_brief")
        _pump()
        widget = coordinator.controller.widget
        assert not widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        widget.activateWindow()
        widget.search_input.setFocus()
        _pump()
        assert _APP.focusWidget() is widget.search_input
        item = next(i for i in widget._last_items if i.get("source") == "directive")

        coordinator.controller.open_item_menu(item, QPoint())
        _pump(0.1)

        assert asked == [1]
        conn = unified_repo.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM task_directive").fetchone()[0] == 0
        assert not any(i.get("source") == "directive" for i in widget._last_items)
    finally:
        coordinator.close_for_shutdown()
        coordinator.controller.widget.deleteLater()
        if hasattr(host, "_ui_refresh_timer"):
            host._ui_refresh_timer.stop()
        host.close()
        host.deleteLater()
        _pump()


class _SelectionHost(TaskActionsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_task_ids = set()
        self.selected_directive_ids = {3, 5}
        self.status_updates = []
        self.refreshes = []

    def update_task_selection_status(self):
        self.status_updates.append(set(self.selected_directive_ids))

    def schedule_panel_refresh(self, left=False, center=False, right=False, **_kwargs):
        self.refreshes.append((left, center, right))

    def _refresh_all_panels(self):
        self.refreshes.append("all")


@pytest.mark.parametrize(
    ("reply", "deleted", "selected"),
    [(QMessageBox.StandardButton.Yes, [5], {3}), (QMessageBox.StandardButton.No, [], {3, 5})],
    ids=["deleted", "cancelled"],
)
def test_widget_delete_restores_the_panel_selection_without_the_deleted_row(
    monkeypatch, reply, deleted, selected
):
    """The widget borrows the panel selection to delete one row, then gives it back."""
    from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetController

    removed = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *_a, **_k: reply))
    monkeypatch.setattr(
        action_handlers_tasks,
        "db_directive",
        SimpleNamespace(delete_directives=lambda ids: removed.extend(ids) or len(ids)),
    )
    host = _SelectionHost()
    try:
        UnifiedWidgetController(host)._delete_item({"item_id": 5, "source": "directive"})
        assert removed == deleted
        assert host.selected_directive_ids == selected
        if deleted:
            assert host.status_updates[-1] == selected
        # Only the right panel lists directives; left and center list schedules.
        assert host.refreshes == ([(False, False, True)] if deleted else [])
    finally:
        host.deleteLater()
        _pump()


def test_directive_updates_report_a_row_deleted_elsewhere(temp_db):
    """A tick or undo on a directive deleted elsewhere must fail, not report success."""
    from calendar_app.infrastructure.db import directive_repo

    directive_id = _add_directive("kept", QDate.currentDate(), "pending")
    assert directive_repo.update_directive_status(directive_id, "completed")
    assert directive_repo.update_directive_priority(directive_id, "urgent")
    missing_id = directive_id + 100
    assert not directive_repo.update_directive_status(missing_id, "completed")
    assert not directive_repo.update_directive_priority(missing_id, "urgent")


# --------------------------------------------------------------------------- untick and undo


@pytest.fixture
def widget_session(temp_db, monkeypatch):
    """Widget-only mode on a real database, with completed rows kept in the list."""
    from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator

    _stub_panel_widgets(monkeypatch)
    host = _WorkHost()
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    host._unified_widget_controller = coordinator.controller
    host.settings.setValue("widget_mode_show_completed", "true")
    try:
        yield host, coordinator
    finally:
        coordinator.close_for_shutdown()
        coordinator.controller.widget.deleteLater()
        if hasattr(host, "_ui_refresh_timer"):
            host._ui_refresh_timer.stop()
        host.close()
        host.deleteLater()
        _pump()


def _enter_with(host, coordinator):
    host.load_right_panel()
    host.show()
    _pump()
    coordinator.enter("all")
    _pump()
    return coordinator.controller


def _widget_item(controller, source, item_id):
    return dict(
        next(
            item
            for item in controller.widget._last_items
            if item.get("source") == source and item.get("item_id") == item_id
        )
    )


def _routine_row(routine_id):
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo

    return unified_repo.get_unified_task(routine_id)


def _directive_status(directive_id):
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo

    row = (
        unified_repo.get_connection()
        .execute("SELECT status FROM task_directive WHERE id=?", (directive_id,))
        .fetchone()
    )
    return row[0]


def test_unticking_a_completed_routine_reopens_it_as_in_progress(widget_session):
    """Completed -> pending is blocked for tasks, so the widget's untick used to fail."""
    from calendar_app.infrastructure.i18n import t

    host, coordinator = widget_session
    routine_id = _add_routine("file report", QDate.currentDate(), "completed")
    controller = _enter_with(host, coordinator)

    controller.set_item_completed(_widget_item(controller, "task", routine_id), False)
    _pump()

    row = _routine_row(routine_id)
    assert row["status"] == "in_progress"
    assert not row["completed_at"]
    item = _widget_item(controller, "task", routine_id)
    assert item["status"] == "in_progress" and not item["completed"]
    assert t("status.in_progress", "진행 중") in controller.widget.feedback_label.text()

    controller.undo_completion()
    _pump()
    assert _routine_row(routine_id)["status"] == "completed"
    assert controller._undo_completion is None


def test_undo_after_completing_restores_pending_through_in_progress(widget_session, monkeypatch):
    host, coordinator = widget_session
    routine_id = _add_routine("water plants", QDate.currentDate(), "pending")
    controller = _enter_with(host, coordinator)
    writes = []
    real_handler = host.handle_task_status_changed

    def handler(task_id, status):
        writes.append(status)
        return real_handler(task_id, status)

    monkeypatch.setattr(host, "handle_task_status_changed", handler)

    controller.set_item_completed(_widget_item(controller, "task", routine_id), True)
    _pump()
    assert _routine_row(routine_id)["status"] == "completed"

    controller.undo_completion()
    _pump()
    row = _routine_row(routine_id)
    assert row["status"] == "pending"
    assert not row["completed_at"]
    assert writes == ["completed", "in_progress", "pending"]
    assert controller._undo_completion is None
    assert _widget_item(controller, "task", routine_id)["status"] == "pending"


def test_failed_second_undo_step_shows_in_progress_and_retries_from_there(
    widget_session, monkeypatch
):
    host, coordinator = widget_session
    routine_id = _add_routine("call back", QDate.currentDate(), "pending")
    controller = _enter_with(host, coordinator)
    controller.set_item_completed(_widget_item(controller, "task", routine_id), True)
    _pump()

    real_handler = host.handle_task_status_changed
    failures = {"pending": 1}

    def flaky(task_id, status):
        if failures.get(status):
            failures[status] -= 1
            return False
        return real_handler(task_id, status)

    monkeypatch.setattr(host, "handle_task_status_changed", flaky)
    controller.undo_completion()
    _pump()
    assert _routine_row(routine_id)["status"] == "in_progress"
    assert _widget_item(controller, "task", routine_id)["status"] == "in_progress"
    assert controller._undo_completion[0]["status"] == "in_progress"
    assert controller.widget.undo_btn.isVisibleTo(controller.widget)

    retry_writes = []

    def recording(task_id, status):
        retry_writes.append(status)
        return real_handler(task_id, status)

    monkeypatch.setattr(host, "handle_task_status_changed", recording)
    controller.undo_completion()
    _pump()
    assert _routine_row(routine_id)["status"] == "pending"
    assert controller._undo_completion is None
    # The retry starts from in progress, so it writes only the remaining step.
    assert retry_writes == ["pending"]


def test_unticking_a_directive_still_writes_pending(widget_session):
    host, coordinator = widget_session
    directive_id = _add_directive("approve budget", QDate.currentDate(), "completed")
    controller = _enter_with(host, coordinator)

    controller.set_item_completed(_widget_item(controller, "directive", directive_id), False)
    _pump()
    assert _directive_status(directive_id) == "pending"
    controller.undo_completion()
    _pump()
    assert _directive_status(directive_id) == "completed"


def test_failed_save_puts_the_board_lane_checkbox_back(widget_session, monkeypatch):
    """Board lanes skip unchanged data, so a failed save must reset their checkbox."""
    host, coordinator = widget_session
    routine_id = _add_routine("send summary", QDate.currentDate(), "completed")
    controller = _enter_with(host, coordinator)
    controller.set_layout("work_board")
    _pump()
    monkeypatch.setattr(host, "handle_task_status_changed", lambda *_a: False)

    board = controller.widget._workspace_board
    row = next(row for row in board.rows() if row.item_key == ("task", routine_id))
    check = row.findChild(QCheckBox, "agenda_complete")
    assert check.isChecked()
    check.click()
    _pump()

    assert _routine_row(routine_id)["status"] == "completed"
    row = next(row for row in board.rows() if row.item_key == ("task", routine_id))
    assert row.findChild(QCheckBox, "agenda_complete").isChecked()


def test_failed_save_of_another_item_drops_the_earlier_undo(widget_session, monkeypatch):
    """The failure message must not offer an undo that reverts a different item."""
    host, coordinator = widget_session
    alpha = _add_routine("alpha", QDate.currentDate(), "pending")
    beta = _add_routine("beta", QDate.currentDate(), "completed")
    controller = _enter_with(host, coordinator)
    controller.set_item_completed(_widget_item(controller, "task", alpha), True)
    _pump()
    assert controller._undo_completion is not None

    real_handler = host.handle_task_status_changed
    monkeypatch.setattr(
        host,
        "handle_task_status_changed",
        lambda task_id, status: False if task_id == beta else real_handler(task_id, status),
    )
    controller.set_item_completed(_widget_item(controller, "task", beta), False)
    _pump()

    assert controller._undo_completion is None
    assert not controller.widget.undo_btn.isVisibleTo(controller.widget)
    assert _routine_row(alpha)["status"] == "completed"
    assert _routine_row(beta)["status"] == "completed"
