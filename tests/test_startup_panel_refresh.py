# -*- coding: utf-8 -*-
"""Startup refresh requests that change no data must not re-render current panels.

Construction renders every panel. The opacity pass, the lock-mode restore, the
post-startup dock recovery and a routine pass that created nothing used to mark every
panel dirty, so the first flush (inside the splash) rendered all three panels again.
"""

import ast
from collections import Counter
import inspect
from unittest.mock import Mock

from PyQt6.QtCore import QDate, QObject
from PyQt6.QtWidgets import QApplication, QFrame
import pytest

from calendar_app.presentation.main_window import app_initializer, ui_builder
from calendar_app.presentation.main_window.calendar_view_actions import CalendarViewActionsMixin
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
from calendar_app.presentation.main_window.routine_actions import RoutineActionsMixin
from calendar_app.shared import background_worker

# Module level: a QApplication created and dropped inside a fixture crashes later tests.
_APP = QApplication.instance() or QApplication([])


class _Host(RefreshSchedulerMixin, CalendarViewActionsMixin, RoutineActionsMixin, QObject):
    """Real scheduler, render cache, calendar signature and routine callback.

    Side-panel signatures and the renders themselves are stubs; renders are counted.
    """

    def __init__(self):
        super().__init__()
        self.settings = None
        self.selected_task_ids = set()
        self.current_date = QDate(2026, 11, 15)
        self.center_frame = QFrame()
        self.center_frame.resize(640, 480)
        self.side_signatures = {"left": ("l", 1), "right": ("r", 1)}
        self.renders = Counter()
        self.worker_callbacks = []
        self._layout_restore_succeeded = True
        self._unified_widget_controller = None

    def _load(self, panel, force):
        if panel == "center":
            signature = self._build_center_render_signature()
        else:
            signature = self.side_signatures[panel]
        self._load_panel_cached(panel, signature, lambda _app: self.renders.update([panel]), force)

    def load_left_panel(self, force=True):
        self._load("left", force)

    def load_center_panel(self, force=True):
        self._load("center", force)

    def load_right_panel(self, force=True):
        self._load("right", force)

    def _run_worker(self, worker, on_finished=None):
        self.worker_callbacks.append(on_finished)

    def construction_render(self):
        """dock_factory renders every panel with force=True before any refresh request."""
        self.load_left_panel()
        self.load_center_panel()
        self.load_right_panel()
        self.renders.clear()


def _replay_startup_requests(host, routines_created=0):
    """The refresh requests startup makes between construction and the first flush."""
    # ui_builder: set_opacity -> apply_theme_settings with the settings just rendered.
    with host.presentation_refresh_only():
        host.schedule_panel_refresh(left=True, center=True, right=True, notify_data_consumers=False)
    # app_initializer: toggle_lock_mode restores the saved lock state.
    with host.presentation_refresh_only():
        host.schedule_panel_refresh(center=True)
    host.generate_today_routines()
    host.worker_callbacks.pop()(True, routines_created)
    app_initializer._force_restore_docks_and_panels(host)
    host._flush_scheduled_refresh()


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(background_worker, "DbTaskWorker", lambda task: Mock(task=task))
    target = _Host()
    yield target
    if hasattr(target, "_ui_refresh_timer"):
        # Deliver the queued timer start, then stop it before it fires.
        _APP.processEvents()
        target._ui_refresh_timer.stop()
    target.center_frame.deleteLater()
    target.deleteLater()
    _APP.processEvents()


@pytest.mark.parametrize(
    ("function", "method"),
    [
        (ui_builder.setup_main_ui, "set_opacity"),
        (app_initializer.initialize_overlay_app, "toggle_lock_mode"),
    ],
)
def test_startup_presentation_calls_stay_inside_the_context(function, method):
    """_replay_startup_requests stands in for these calls, so they must stay wrapped."""
    tree = ast.parse(inspect.getsource(function))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def wrapped(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, ast.With) and any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Attribute)
                and item.context_expr.func.attr == "presentation_refresh_only"
                for item in node.items
            ):
                return True
        return False

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    ]
    assert calls
    assert all(wrapped(call) for call in calls)


def test_startup_without_data_changes_renders_each_panel_once(host):
    host.construction_render()
    _replay_startup_requests(host)
    assert host.renders == Counter()


def test_startup_that_created_routines_rerenders_only_the_routine_panel(host):
    host.construction_render()
    _replay_startup_requests(host, routines_created=2)
    assert host.renders == Counter({"right": 1})


def test_startup_flush_rerenders_calendar_after_its_frame_height_changed(host):
    host.construction_render()
    host.center_frame.resize(640, 76)  # the frame got its first layout height
    _replay_startup_requests(host)
    assert host.renders == Counter({"center": 1})


def test_scheduler_created_before_any_render_starts_dirty(host):
    host.schedule_panel_refresh(left=True, mark_dirty=False)
    assert host._panel_dirty == {"left": True, "center": True, "right": True}


def test_runtime_request_still_rerenders_unchanged_panel(host):
    host.construction_render()
    host.schedule_panel_refresh(left=True)
    host._flush_scheduled_refresh()
    assert host.renders == Counter({"left": 1})


def test_data_request_coalesced_with_presentation_request_rerenders(host):
    host.construction_render()
    host.schedule_panel_refresh(left=True, center=True, right=True, mark_dirty=False)
    host.schedule_panel_refresh(right=True)
    host._flush_scheduled_refresh()
    assert host.renders == Counter({"right": 1})


def test_presentation_context_suppresses_dirty_marks_nests_and_restores_depth(host):
    host.construction_render()
    with pytest.raises(RuntimeError), host.presentation_refresh_only():
        with host.presentation_refresh_only():
            host.schedule_panel_refresh(left=True, center=True, right=True)
        raise RuntimeError("boom")
    assert host._presentation_refresh_depth == 0
    assert host._panel_dirty == {"left": False, "center": False, "right": False}
    host.schedule_panel_refresh(left=True)
    assert host._panel_dirty["left"] is True


def test_center_signature_tracks_calendar_frame_height(host):
    before = host._build_center_render_signature()
    assert host._build_center_render_signature() == before
    host.center_frame.resize(640, 22)
    assert host._build_center_render_signature() != before


@pytest.mark.parametrize(
    ("success", "created", "expected"),
    [(True, 0, Counter()), (True, 2, Counter({"right": 1})), (False, "error", Counter())],
)
def test_routine_generation_refreshes_only_when_rows_were_created(host, success, created, expected):
    host.construction_render()
    host.generate_today_routines()
    host.worker_callbacks.pop()(success, created)
    host._flush_scheduled_refresh()
    assert host.renders == expected
