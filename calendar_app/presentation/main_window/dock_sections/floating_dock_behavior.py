"""Floating dock behavior — 패널 분리/재도킹 및 크기 조절 지원."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtWidgets import QDockWidget, QWidget

logger = logging.getLogger(__name__)

_GRIP_SIZE = 14


def _prepare_floating_dock_visuals(dock: QDockWidget | None):
    """Keep the floating dock root transparent so panel alpha remains visible."""
    if dock is None:
        return

    dock.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dock.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    dock_style = str(dock.styleSheet() or "")
    dock_rule = "QDockWidget { background: transparent; border: none; }"
    if dock_rule not in dock_style:
        dock.setStyleSheet((dock_style + "\n" + dock_rule).strip())

    root = dock.widget()
    if root is None:
        return
    root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    root_style = str(root.styleSheet() or "")
    if "background: transparent" not in root_style:
        root.setStyleSheet((root_style + "\nbackground: transparent;").strip())


class _CornerResizeHandle(QWidget):
    """floating dock 모서리에 배치되는 크기 조절 핸들."""

    def __init__(self, dock: QDockWidget, corner: str):
        super().__init__(dock)
        assert corner in ("tl", "tr", "bl", "br")
        self._dock = dock
        self._corner = corner
        self.setFixedSize(_GRIP_SIZE, _GRIP_SIZE)
        self.setStyleSheet("background: transparent;")
        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if corner in ("tl", "br")
            else Qt.CursorShape.SizeBDiagCursor
        )
        self._dragging = False
        self._start_global: QPoint = QPoint()
        self._start_geom: QRect = QRect()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_global = event.globalPosition().toPoint()
            self._start_geom = self._dock.geometry()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        delta = event.globalPosition().toPoint() - self._start_global
        dx, dy = delta.x(), delta.y()
        g = self._start_geom
        min_w, min_h = 150, 100

        if self._corner == "br":
            self._dock.setGeometry(
                g.x(), g.y(), max(min_w, g.width() + dx), max(min_h, g.height() + dy)
            )
        elif self._corner == "bl":
            nw = max(min_w, g.width() - dx)
            self._dock.setGeometry(g.right() - nw + 1, g.y(), nw, max(min_h, g.height() + dy))
        elif self._corner == "tr":
            nh = max(min_h, g.height() - dy)
            self._dock.setGeometry(g.x(), g.bottom() - nh + 1, max(min_w, g.width() + dx), nh)
        elif self._corner == "tl":
            nw = max(min_w, g.width() - dx)
            nh = max(min_h, g.height() - dy)
            self._dock.setGeometry(g.right() - nw + 1, g.bottom() - nh + 1, nw, nh)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()


class FloatingDockBehavior(QObject):
    """QDockWidget에 부착되어 floating 상태 전환을 처리한다.

    설계 원칙
    ---------
    - DockTitleBar(패널 고유 타이틀바)는 docked/floating 모두에서 **그대로 유지**한다.
      floating 전환 시 별도 타이틀바로 교체하지 않는다.
    - 드래그/재도킹은 Qt 기본 동작에 완전히 맡긴다 (Win32 HWND 조작 없음).
    - DockTitleBar의 mousePressEvent → dock.mousePressEvent 전달이 이미 Qt 도킹을
      트리거하므로 추가 처리가 불필요하다.
    - floating 상태에서는 모서리 크기 조절 핸들만 추가로 제공한다.
    - panel refresh(load_*_panel)가 _replace_title_bar를 통해 타이틀바를 교체할 때
      is_dock_float_wrapped 체크로 skip하던 로직을 제거한다.
    """

    def __init__(self, dock: QDockWidget, on_float_changed=None, app=None, label: str = ""):
        super().__init__(dock)
        self._dock = dock
        self._app = app
        self._label = label
        self._on_float_changed = on_float_changed
        _prepare_floating_dock_visuals(dock)

        # 모서리 크기 조절 핸들 (floating일 때만 표시)
        self._grips: dict[str, _CornerResizeHandle] = {
            c: _CornerResizeHandle(dock, c) for c in ("tl", "tr", "bl", "br")
        }
        for g in self._grips.values():
            g.hide()

        dock.installEventFilter(self)
        dock.topLevelChanged.connect(self._on_top_level_changed)
        self._update_grips()

    # ------------------------------------------------------------------
    # floating 상태 전환
    # ------------------------------------------------------------------
    def _on_top_level_changed(self, floating: bool):
        try:
            logger.info("[DockFloating] %s floating=%s", self._dock.objectName(), floating)
            if floating:
                _prepare_floating_dock_visuals(self._dock)
                self._dock.setWindowOpacity(1.0)
                # 재도킹 후 패널 refresh가 타이틀바를 복원하므로 별도 처리 불필요
            else:
                _prepare_floating_dock_visuals(self._dock)
                # re-dock: 패널 타이틀바를 즉시 재설치
                self._refresh_panel(delay_ms=0)
        except Exception:
            logger.exception(
                "[DockFloating] _on_top_level_changed 오류 dock=%s", self._dock.objectName()
            )
        self._update_grips()
        if self._on_float_changed is not None:
            try:
                self._on_float_changed(floating)
            except Exception:
                logger.exception(
                    "[DockFloating] on_float_changed 콜백 오류 dock=%s", self._dock.objectName()
                )

    def _refresh_panel(self, delay_ms: int = 0):
        """해당 dock의 패널을 강제 재로드해 타이틀바를 복원한다."""
        if self._app is None:
            return
        dock_name = self._dock.objectName()

        def _do():
            try:
                if dock_name == "center_dock":
                    self._app.load_center_panel(force=True)
                elif dock_name == "left_dock":
                    self._app.load_left_panel(force=True)
                elif dock_name in ("routine_dock", "directive_dock"):
                    self._app.load_right_panel(force=True)
            except Exception:
                logger.exception("[DockFloating] _refresh_panel 오류 dock=%s", dock_name)

        if delay_ms <= 0:
            QTimer.singleShot(0, _do)
        else:
            QTimer.singleShot(delay_ms, _do)

    # ------------------------------------------------------------------
    # 모서리 크기 조절 핸들
    # ------------------------------------------------------------------
    def eventFilter(self, watched, event):
        if watched is not self._dock:
            return False
        et = event.type()
        if et in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        ):
            self._update_grips()
        return False

    def _update_grips(self):
        if not self._dock.isFloating() or bool(getattr(self._app, "is_locked", False)):
            for g in self._grips.values():
                g.hide()
            return
        w, h = self._dock.width(), self._dock.height()
        m = 2
        positions = {
            "tl": (m, m),
            "tr": (w - _GRIP_SIZE - m, m),
            "bl": (m, h - _GRIP_SIZE - m),
            "br": (w - _GRIP_SIZE - m, h - _GRIP_SIZE - m),
        }
        for corner, (x, y) in positions.items():
            grip = self._grips[corner]
            grip.move(max(0, x), max(0, y))
            grip.raise_()
            grip.show()


# ------------------------------------------------------------------
# 공개 API
# ------------------------------------------------------------------


def attach_floating_dock_behavior(
    dock: QDockWidget | None,
    on_float_changed=None,
    app=None,
    label: str = "",
):
    if dock is None:
        return
    if bool(dock.property("_floating_behavior_attached")):
        return
    dock._floating_behavior = FloatingDockBehavior(
        dock, on_float_changed=on_float_changed, app=app, label=label
    )
    dock.setProperty("_floating_behavior_attached", True)


def is_dock_float_wrapped(_dock: QDockWidget) -> bool:
    """항상 False 반환 — 타이틀바 교체 skip 로직을 제거했으므로 더 이상 사용하지 않는다.

    _replace_title_bar에서 호출하는 기존 코드와의 호환성을 위해 유지하되,
    floating 상태에서도 타이틀바 교체를 허용한다.
    """
    return False
