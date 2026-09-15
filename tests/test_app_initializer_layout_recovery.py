# -*- coding: utf-8 -*-
from calendar_app.presentation.main_window.app_initializer import (
    _force_restore_docks_and_panels,
)


class _FocusStub:
    def hide(self):
        pass


class _DockStub:
    def __init__(self, *, floating=False):
        self._floating = floating
        self.show_calls = 0

    def isFloating(self):
        return self._floating

    def show(self):
        self.show_calls += 1


class _DockManagerStub:
    def __init__(self):
        self.added = []

    def addDockWidget(self, area, dock):
        self.added.append((area, dock))


class _AppStub:
    def __init__(self, restored):
        self._layout_restore_succeeded = restored
        self.focus_frame = _FocusStub()
        self.dock_manager = _DockManagerStub()
        self.left_dock = _DockStub()
        self.center_dock = _DockStub()
        self.routine_dock = _DockStub()
        self.directive_dock = _DockStub()
        self.sync_calls = 0
        self.float_calls = 0
        self.refresh_calls = []

    def sync_panel_menu_state(self):
        self.sync_calls += 1

    def _on_any_dock_float_changed(self):
        self.float_calls += 1

    def schedule_panel_refresh(self, **kwargs):
        self.refresh_calls.append(kwargs)


def test_post_startup_recovery_does_not_mutate_a_successfully_restored_layout():
    app = _AppStub(restored=True)

    _force_restore_docks_and_panels(app)

    assert app.dock_manager.added == []
    assert all(
        dock.show_calls == 0
        for dock in (
            app.left_dock,
            app.center_dock,
            app.routine_dock,
            app.directive_dock,
        )
    )
    assert app.sync_calls == 1
    assert app.float_calls == 1
    assert app.refresh_calls == [{"left": True, "center": True, "right": True}]


def test_post_startup_recovery_rebuilds_only_when_restore_failed():
    app = _AppStub(restored=False)

    _force_restore_docks_and_panels(app)

    assert len(app.dock_manager.added) == 4
    assert all(
        dock.show_calls == 1
        for dock in (
            app.left_dock,
            app.center_dock,
            app.routine_dock,
            app.directive_dock,
        )
    )
