# -*- coding: utf-8 -*-
"""Helpers to restore window state and bind dock/menu visibility."""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QSizeGrip

_LAYOUT_VERSION = "v3"  # bump this when dock area topology changes

logger = logging.getLogger(__name__)


def restore_window_and_bind_menu_state(self):
    if hasattr(self, "focus_frame"):
        self.focus_frame.hide()

    geom = self.settings.value("last_geometry")
    if geom:
        self.restoreGeometry(geom)
    else:
        self.resize(1200, 700)

    state = self.settings.value("last_state")
    saved_ver = self.settings.value("layout_version", "")

    # Discard saved state when dock topology has changed (e.g. Left+Right area
    # → single LeftDockWidgetArea with splitDockWidget).  Restoring an
    # incompatible state would move docks back to the old RightDockWidgetArea.
    if saved_ver != _LAYOUT_VERSION:
        state = None
        self.settings.remove("last_state")
        self.settings.setValue("layout_version", _LAYOUT_VERSION)

    restored = False
    restore_source = "none"
    if state:
        restored = bool(self.restoreState(state))
        if restored:
            restore_source = "last_session"

    # The last live session is authoritative.  A user-saved default remains a
    # useful recovery fallback, but must not replace the layout that was active
    # immediately before a language-change restart or a normal relaunch.
    if not restored:
        preset_manager = getattr(self, "preset_manager", None)
        if preset_manager is not None:
            try:
                restored = bool(preset_manager.apply_saved_default_on_startup())
                if restored:
                    restore_source = "saved_default"
            except Exception:
                restored = False

    self._layout_restore_succeeded = restored
    self._layout_restore_source = restore_source
    should_normalize_splits = not restored

    # Re-apply screen-fill mode only as part of a valid last-session restore.
    # restoreGeometry alone is not enough because the fill action uses
    # setGeometry rather than Qt's maximized window state.
    if (
        restore_source == "last_session"
        and str(self.settings.value("screen_fill_active", "false")).lower() == "true"
    ):

        def _reapply_fill(app=self):
            try:
                avail = app._target_screen_geometry()
                if avail:
                    app.setGeometry(avail)
                    app._screen_fill_active = True
            except Exception:
                pass

        QTimer.singleShot(0, _reapply_fill)

    # 저장된 레이아웃이 없을 때(첫 실행·초기화 후) 기본 레이아웃(Preset 1: 전체 도킹) 적용
    if not restored:
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
    if state and not restored:
        for dock in docks:
            dock.setVisible(True)
        self.settings.remove("last_state")

    self.act_today.setChecked(not self.left_dock.isHidden())
    self.act_calendar.setChecked(not self.center_dock.isHidden())
    self.act_routine.setChecked(not self.routine_dock.isHidden())
    self.act_directive.setChecked(not self.directive_dock.isHidden())

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

    # 도크 변경(이동/플로팅/리사이즈/숨김) 직후 디바운스 저장 설치 — 비정상
    # 종료 시 직전 상태 손실 방지
    install_dock_persist_signals(self)


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


def flush_window_layout(self) -> bool:
    """Persist the complete live session before a restart or final shutdown."""

    saved = True
    try:
        self.settings.setValue("last_geometry", self.saveGeometry())
    except Exception:
        logger.exception("Failed to persist window geometry")
        saved = False
    try:
        self.settings.setValue("last_state", self.saveState())
        self.settings.setValue("layout_version", _LAYOUT_VERSION)
    except Exception:
        logger.exception("Failed to persist dock layout")
        saved = False

    # OverlayWidgetManager.save_all() captures live coordinates before syncing
    # its instance metadata.  This is required when the user changes language
    # while an overlay was moved since the last reactive settings write.
    try:
        overlay_manager = getattr(self, "overlay_manager", None)
        if overlay_manager is not None:
            overlay_manager.save_all()
    except Exception:
        logger.exception("Failed to persist overlay widget state")
        saved = False

    try:
        self.settings.sync()
    except Exception:
        logger.exception("Failed to flush application settings")
        saved = False
    return saved


def save_window_layout(self) -> bool:
    """종료 시점의 윈도우 geometry와 dock 레이아웃을 QSettings에 저장. 중복 호출 무해."""
    if getattr(self, "_layout_saved", False):
        return True
    saved = flush_window_layout(self)
    self._layout_saved = saved
    return saved


def persist_dock_layout(self):
    """도크 이동/플로팅/리사이즈/가시성 변경 직후 즉시 호출되는 가벼운 저장.

    종료-1회 가드(_layout_saved)를 무시하고 saveGeometry+saveState 만 다시
    써낸다. 비정상 종료 시 직전 상태 손실을 막기 위한 반응형 백업.
    """
    import contextlib

    if getattr(self, "_is_shutting_down", False):
        return
    with contextlib.suppress(Exception):
        self.settings.setValue("last_geometry", self.saveGeometry())
    with contextlib.suppress(Exception):
        self.settings.setValue("last_state", self.saveState())
        self.settings.setValue("layout_version", _LAYOUT_VERSION)


def install_dock_persist_signals(self):
    """모든 dock의 topLevelChanged / dockLocationChanged / visibilityChanged
    시그널을 디바운스된 persist 호출로 연결한다.

    설치는 한 번만 — 중복 연결 방지 플래그(_dock_persist_installed).
    """
    if getattr(self, "_dock_persist_installed", False):
        return
    self._dock_persist_installed = True

    from PyQt6.QtCore import QObject

    timer_parent = self if isinstance(self, QObject) else None
    debounce = QTimer(timer_parent)
    debounce.setSingleShot(True)
    debounce.setInterval(400)  # 0.4s — drag 중 spam 방지
    debounce.timeout.connect(lambda: persist_dock_layout(self))
    self._dock_persist_timer = debounce

    def _schedule(*_args):
        debounce.start()

    docks = [
        getattr(self, "left_dock", None),
        getattr(self, "center_dock", None),
        getattr(self, "routine_dock", None),
        getattr(self, "directive_dock", None),
    ]
    for dock in docks:
        if dock is None:
            continue
        try:
            dock.topLevelChanged.connect(_schedule)
            dock.dockLocationChanged.connect(_schedule)
            dock.visibilityChanged.connect(_schedule)
        except Exception:
            pass


def setup_size_grip(self):
    self.size_grip = QSizeGrip(self)
    self.size_grip.setFixedSize(20, 20)
    self.size_grip.setStyleSheet("background: transparent;")
    self.size_grip.raise_()
