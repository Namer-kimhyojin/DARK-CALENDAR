"""Helpers to restore window state and bind dock/menu visibility."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QSizeGrip

_LAYOUT_VERSION = "v3"  # bump this when dock area topology changes


def restore_window_and_bind_menu_state(self):
    if hasattr(self, "focus_frame"):
        self.focus_frame.hide()

    geom = self.settings.value("last_geometry")
    state = self.settings.value("last_state")
    saved_ver = self.settings.value("layout_version", "")

    if geom:
        self.restoreGeometry(geom)
    else:
        self.resize(1200, 700)

    # Re-apply screen-fill mode if user had it active at last shutdown.
    # restoreGeometry alone is not enough because:
    #  - Qt's saveGeometry stores frame-relative coords; subsequent layout work
    #    can nudge by a pixel and the visual "fill" is lost.
    #  - The user's _toggle_screen_fill uses setGeometry (not showMaximized)
    #    for multi-monitor support, so the maximized flag was never set.
    # Persisting the flag lets us re-run the fill logic against the current
    # screen at startup.
    if str(self.settings.value("screen_fill_active", "false")).lower() == "true":

        def _reapply_fill(app=self):
            try:
                avail = app._target_screen_geometry()
                if avail:
                    app.setGeometry(avail)
                    app._screen_fill_active = True
            except Exception:
                pass

        QTimer.singleShot(0, _reapply_fill)

    # Discard saved state when dock topology has changed (e.g. Left+Right area
    # → single LeftDockWidgetArea with splitDockWidget).  Restoring an
    # incompatible state would move docks back to the old RightDockWidgetArea.
    if saved_ver != _LAYOUT_VERSION:
        state = None
        self.settings.remove("last_state")
        self.settings.setValue("layout_version", _LAYOUT_VERSION)

    restored = False
    if state:
        restored = bool(self.restoreState(state))
    should_normalize_splits = not state or not restored

    # 저장된 레이아웃이 없을 때(첫 실행·초기화 후) 기본 레이아웃(Preset 1: 전체 도킹) 적용
    if not state or not restored:
        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            _preset_all_docked,
        )

        QTimer.singleShot(0, lambda: _preset_all_docked(self))

    self.ensure_window_on_screen()

    # Recover from broken/legacy saved state that explicitly hides all panels.
    # NOTE: isVisible() returns False during __init__ because the parent window hasn't
    # been shown yet – use isHidden() (explicitly hidden flag) so we don't falsely
    # discard a valid state (including one with floating docks).
    docks = [self.left_dock, self.center_dock, self.routine_dock, self.directive_dock]
    if (state and not restored) or all(dock.isHidden() for dock in docks):
        for dock in docks:
            dock.setVisible(True)
        self.settings.remove("last_state")
    else:
        # Ensure right-side docks are alive; don't force-show floating ones.
        for dock in (self.routine_dock, self.directive_dock):
            if dock.isHidden():
                dock.setVisible(True)

    self.act_today.setChecked(self.left_dock.isVisible())
    self.act_calendar.setChecked(self.center_dock.isVisible())
    self.act_routine.setChecked(self.routine_dock.isVisible())
    self.act_directive.setChecked(self.directive_dock.isVisible())

    # 단차 방지: 좌/우 열의 수직 분할선을 항상 50/50으로 동기화
    # (저장된 상태에서 두 열의 분할 위치가 다를 경우 시각적 단차 발생)
    if should_normalize_splits:
        QTimer.singleShot(50, lambda: _sync_vertical_splits(self))

    # visibilityChanged(visible) 은 floating 도크가 화면에서 잠깐 사라질 때도
    # False를 보낼 수 있으므로, isHidden() 기준으로 체크 상태를 결정한다.
    self.left_dock.visibilityChanged.connect(
        lambda _: self.act_today.setChecked(not self.left_dock.isHidden())
    )
    self.center_dock.visibilityChanged.connect(
        lambda _: self.act_calendar.setChecked(not self.center_dock.isHidden())
    )
    self.routine_dock.visibilityChanged.connect(
        lambda _: self.act_routine.setChecked(not self.routine_dock.isHidden())
    )
    self.directive_dock.visibilityChanged.connect(
        lambda _: self.act_directive.setChecked(not self.directive_dock.isHidden())
    )


def _sync_vertical_splits(app):
    """좌/우 열의 수직 분할선을 50/50으로 동기화해 단차를 제거한다."""
    try:
        app.resizeDocks(
            [app.left_dock, app.center_dock],
            [500, 500],
            Qt.Orientation.Vertical,
        )
        app.resizeDocks(
            [app.routine_dock, app.directive_dock],
            [500, 500],
            Qt.Orientation.Vertical,
        )
    except Exception:
        pass


def save_window_layout(self):
    """종료 시점의 윈도우 geometry와 dock 레이아웃을 QSettings에 저장. 중복 호출 무해."""
    import contextlib

    if getattr(self, "_layout_saved", False):
        return
    self._layout_saved = True
    with contextlib.suppress(Exception):
        self.settings.setValue("last_geometry", self.saveGeometry())
    with contextlib.suppress(Exception):
        self.settings.setValue("last_state", self.saveState())
        self.settings.setValue("layout_version", _LAYOUT_VERSION)
    # 오버레이 위젯 위치도 저장
    with contextlib.suppress(Exception):
        if hasattr(self, "overlay_manager"):
            self.overlay_manager.save_all()


def setup_size_grip(self):
    self.size_grip = QSizeGrip(self)
    self.size_grip.setFixedSize(20, 20)
    self.size_grip.setStyleSheet("background: transparent;")
    self.size_grip.raise_()
