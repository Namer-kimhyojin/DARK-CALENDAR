# -*- coding: utf-8 -*-
"""Runtime KeyDeck canvas.

One widget paints every key, hit-tests by geometry and drives all motion from a
single timer that stops as soon as nothing moves (idle CPU ≈ 0).
"""

from __future__ import annotations

import math
from pathlib import Path
import random
import time

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.keydeck.model import (
    ACTION_TYPES,
    COMMANDS,
    HOLD_DELAY_MS,
    PAGE_TARGETS,
    option_label,
)
from calendar_app.presentation.widgets.keydeck.physics import (
    EVENT_BOTTOM,
    EVENT_CLICK,
    EVENT_TOP,
    LATCH_DEPTH,
    KeySpring,
    TiltSpring,
    switch_profile,
)
from calendar_app.presentation.widgets.keydeck.renderer import (
    ERROR_COLOR,
    SUCCESS_COLOR,
    KeyDeckRenderer,
    KeyVisualState,
    fit_scale,
)
from calendar_app.presentation.widgets.keydeck.resources import (
    IMAGE_SUFFIXES,
    file_stamp,
    is_animated,
    key_sound_paths,
    physical_sound_plan,
    pick_switch_sound,
    sound_bank,
    switch_sound_variants,
)

_FRAME_MS = 16
_AMBIENT_MS = 50
_LED_DECAY_S = 0.38
_FLASH_S = 0.75
_SHAKE_S = 0.32
_FADE_S = 0.18
_MAX_MOVIE_CACHE_BYTES = 4 * 1024 * 1024
# 덱이 나타난 직후의 클릭(덱을 띄운 클릭이 그대로 키에 닿는 경우)은 실행하지 않는다.
_ARM_DELAY_S = 0.35
# 빠르게 클릭해도 키는 끝까지 눌렸다가 올라온다 (실제 타건처럼 바닥을 친 뒤 복귀).
_COMMIT_DEPTH = 0.85
# 오프센터 누름의 기울기. 스태빌라이저가 달린 긴 키는 수평을 유지한다.
_TILT_GAIN = 0.85
_STABILIZED_TILT = 0.3


def action_summary(action: dict, deck: dict | None = None) -> str:
    """Human readable one-liner for tooltips and the studio status bar."""
    kind = str(action.get("type", "none"))
    target = str(action.get("target", ""))
    kind_label = option_label(ACTION_TYPES, kind)
    if kind == "none":
        return kind_label
    if kind == "command":
        return f"{kind_label} · {option_label(COMMANDS, target)}"
    if kind == "page":
        if target in {"next", "prev"}:
            return f"{kind_label} · {option_label(PAGE_TARGETS, target)}"
        for page in (deck or {}).get("pages", []):
            if page.get("id") == target:
                return f"{kind_label} · {page.get('name', '')}"
        return kind_label
    if kind == "text":
        preview = " ".join(target.split())[:40]
        return f"{kind_label} · {preview}" if preview else kind_label
    if not target:
        not_set = t("widget.launcher.not_set", "미지정")
        return f"{kind_label} · {not_set}"
    return f"{kind_label} · {target}"


class _KeyRuntime:
    __slots__ = (
        "spring",
        "visual",
        "flash",
        "flash_color",
        "shake_t",
        "press_path",
        "release_path",
        "switch",
        "tilt",
        "plan",
        "pending_release",
    )

    def __init__(self, key: dict, rest: float):
        self.switch = key["switch"]
        self.spring = KeySpring(switch_profile(key["switch"]), rest)
        self.tilt = TiltSpring()
        self.visual = KeyVisualState(travel=rest)
        self.flash = 0.0
        self.flash_color = ""
        self.shake_t = 0.0
        self.pending_release = False
        self.plan = None
        self.press_path, self.release_path = key_sound_paths(key)


class KeyDeckCanvas(QWidget):
    """Interactive deck surface used by the overlay widget and the studio preview."""

    keyActivated = pyqtSignal(str, str)  # key id, "tap" | "hold"
    editRequested = pyqtSignal(str)  # key id or "" for the whole deck
    closeRequested = pyqtSignal()
    pageRequested = pyqtSignal(int)
    imageDropped = pyqtSignal(str, str)  # key id, image path
    targetsDropped = pyqtSignal(list)  # [(kind, target), ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(str(t("widget.launcher.title", "KEYDECK")))
        self.renderer = KeyDeckRenderer()
        self.renderer.empty_hint = str(
            t("widget.launcher.empty_page", "빈 페이지 · 스튜디오에서 키를 추가하세요")
        )
        self._deck: dict | None = None
        self._runtime: dict[str, _KeyRuntime] = {}
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last_tick = 0.0
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold)
        self._pressed_id = ""
        self._press_inside = False
        self._hold_fired = False
        self._hover_id = ""
        self._header_hover = ""
        self._active = True
        self._movies: dict[str, QMovie] = {}
        self._fade_pixmap: QPixmap | None = None
        self._fade_t = 0.0
        self._wheel_accum = 0
        self._live_box: QSize | None = None
        self._geometry_overrides: dict = {}
        self._mouse_inside = False
        self._armed_at = 0.0
        self._force_sound_until = 0.0
        self.close_control_enabled = True

    # -- deck binding -----------------------------------------------------------

    @property
    def deck(self) -> dict | None:
        return self._deck

    def set_deck(self, deck: dict, *, animate: bool = False) -> None:
        if animate and self._deck is not None and self.isVisible() and not self._reduce_motion():
            self._fade_pixmap = self.renderer.render_pixmap(
                self._states(), self.devicePixelRatioF()
            )
            self._fade_t = 1.0
        self._deck = deck
        self._relayout()
        self._rebuild_runtime()
        self._sync_movies()
        self._preload_sounds()
        self.updateGeometry()
        self.update()
        self._kick_if_moving()

    def _kick_if_moving(self) -> None:
        if self._fade_t > 0 or any(
            not runtime.spring.settled for runtime in self._runtime.values()
        ):
            self._ensure_timer()

    def refresh(self, key_ids: set[str] | None = None) -> None:
        """Re-read the bound deck after in-place edits (all keys when ``key_ids`` is None)."""
        if self._deck is None:
            return
        self.renderer.invalidate(key_ids)
        self._relayout()
        self._rebuild_runtime(force_ids=key_ids)
        self._sync_movies()
        self._preload_sounds()
        self.updateGeometry()
        self.update()
        self._kick_if_moving()

    def set_geometry_overrides(self, **overrides) -> None:
        self._geometry_overrides = dict(overrides)
        if self._deck is not None:
            self._relayout()
            self.updateGeometry()
            self.update()

    def set_live_box(self, size: QSize | None) -> None:
        """Preview a zoom while the overlay is being resized (None = deck scale)."""
        self._live_box = QSize(size) if size is not None else None
        if self._deck is not None:
            self._relayout()
            self.update()

    def fitted_scale(self, width: int, height: int) -> float:
        if self._deck is None:
            return 1.0
        return fit_scale(self._deck, self._deck["page"], width, height, **self._geometry_overrides)

    def _relayout(self) -> None:
        deck = self._deck
        args = dict(self._geometry_overrides)
        if self._live_box is not None and "scale" not in args:
            args["scale"] = fit_scale(
                deck, deck["page"], self._live_box.width(), self._live_box.height(), **args
            )
        self.renderer.set_deck(deck, deck["page"], **args)

    def _page_keys(self) -> list[dict]:
        geometry = self.renderer.geometry
        return geometry.keys if geometry is not None else []

    def _key_by_id(self, key_id: str) -> dict | None:
        return next((key for key in self._page_keys() if key["id"] == key_id), None)

    def _rest_position(self, key: dict) -> float:
        # 실물 키는 마우스를 올려도 떠오르지 않는다 — 호버는 빛으로만 표현한다.
        if key["mode"] == "toggle" and key["active"]:
            return LATCH_DEPTH
        return 0.0

    def _rebuild_runtime(self, force_ids: set[str] | None = None) -> None:
        fresh: dict[str, _KeyRuntime] = {}
        for key in self._page_keys():
            runtime = self._runtime.get(key["id"])
            rest = self._rest_position(key)
            if runtime is None or runtime.switch != key["switch"]:
                runtime = _KeyRuntime(key, rest)
            elif force_ids is None or key["id"] in force_ids:
                runtime.press_path, runtime.release_path = key_sound_paths(key)
            runtime.plan = physical_sound_plan(key, self._deck)
            if key["id"] != self._pressed_id and not runtime.pending_release:
                self._move_to(runtime, rest)
            fresh[key["id"]] = runtime
        self._runtime = fresh
        if self._pressed_id not in fresh:
            self._pressed_id = ""
            self._hold_timer.stop()
        if self._hover_id not in fresh:
            self._hover_id = ""

    def _states(self) -> dict[str, KeyVisualState]:
        return {key_id: runtime.visual for key_id, runtime in self._runtime.items()}

    def _reduce_motion(self) -> bool:
        return bool(self._deck and self._deck.get("reduce_motion"))

    # -- sizing & painting ------------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802
        geometry = self.renderer.geometry
        return geometry.size() if geometry is not None else QSize(240, 120)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 30)

    def content_offset(self) -> QPointF:
        geometry = self.renderer.geometry
        if geometry is None:
            return QPointF(0, 0)
        return QPointF(
            max(0.0, (self.width() - geometry.width) / 2.0),
            max(0.0, (self.height() - geometry.height) / 2.0),
        )

    def to_canvas(self, point) -> QPointF:
        return QPointF(point) - self.content_offset()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._deck is None or self.renderer.geometry is None:
            return
        painter = QPainter(self)
        offset = self.content_offset()
        painter.translate(offset)
        clip = QRectF(event.rect()).translated(-offset)
        self.renderer.paint(
            painter,
            self._states(),
            dpr=self.devicePixelRatioF(),
            clip=clip,
            header_hover=self._header_hover,
            show_close=self._close_visible(),
        )
        self.paint_overlay(painter)
        if self._fade_pixmap is not None and self._fade_t > 0.0:
            painter.setOpacity(self._fade_t)
            painter.drawPixmap(0, 0, self._fade_pixmap)
        painter.end()

    def paint_overlay(self, painter: QPainter) -> None:
        """Hook for subclasses (studio selection chrome)."""

    # -- hit testing ------------------------------------------------------------------

    def key_at(self, point) -> dict | None:
        geometry = self.renderer.geometry
        if geometry is None:
            return None
        return geometry.hit_key(self.to_canvas(point))

    def _close_visible(self) -> bool:
        geometry = self.renderer.geometry
        if geometry is None or not self.close_control_enabled:
            return False
        return geometry.header or self._mouse_inside

    def header_control_at(self, point) -> str:
        geometry = self.renderer.geometry
        if geometry is None:
            return ""
        local = self.to_canvas(point)
        if self._close_visible() and geometry.close_rect.adjusted(-3, -3, 3, 3).contains(local):
            return "close"
        if not geometry.header:
            return ""
        if geometry.gear_rect.adjusted(-3, -3, 3, 3).contains(local):
            return "gear"
        for index, dot in enumerate(geometry.dot_rects):
            if dot.adjusted(-4, -6, 4, 6).contains(local):
                return f"dot:{index}"
        return ""

    def is_interactive_at(self, point) -> bool:
        return self.key_at(point) is not None or bool(self.header_control_at(point))

    def is_pressing(self) -> bool:
        return bool(self._pressed_id)

    # -- feedback API -----------------------------------------------------------------

    def show_feedback(self, key_id: str, ok: bool | None) -> None:
        runtime = self._runtime.get(key_id)
        if runtime is None or ok is None:
            return
        runtime.flash = 1.0
        runtime.flash_color = SUCCESS_COLOR if ok else ERROR_COLOR
        if not ok and not self._reduce_motion():
            runtime.shake_t = _SHAKE_S
        self._ensure_timer()

    def sync_key_state(self, key_id: str) -> None:
        """Re-seat a key after its toggle state changed in the model."""
        key = self._key_by_id(key_id)
        runtime = self._runtime.get(key_id)
        if key is None or runtime is None:
            return
        if key_id != self._pressed_id:
            self._move_to(runtime, self._rest_position(key))
        self._ensure_timer()

    def press_visual(self, key_id: str, *, force_sound: bool = False) -> None:
        """Animate a full keystroke without mouse input (studio preview / test run)."""
        key = self._key_by_id(key_id)
        runtime = self._runtime.get(key_id)
        if key is None or runtime is None:
            return
        if force_sound:
            self._force_sound_until = time.monotonic() + 0.8
        self._press_runtime(key, runtime, None)
        QTimer.singleShot(110, lambda: self._release_visual(key_id))
        self._ensure_timer()

    def _release_visual(self, key_id: str) -> None:
        key = self._key_by_id(key_id)
        runtime = self._runtime.get(key_id)
        if key is not None and runtime is not None:
            self._release_runtime(key, runtime)
            self._ensure_timer()

    # -- runtime activity -------------------------------------------------------------

    def set_runtime_active(self, active: bool) -> None:
        self._active = bool(active)
        if not self._active:
            self._timer.stop()
            self._hold_timer.stop()
        self._sync_movies()
        if self._active:
            self._ensure_timer()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._armed_at = time.monotonic() + _ARM_DELAY_S
        self._sync_movies()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._hold_timer.stop()
        for movie in self._movies.values():
            movie.setPaused(True)
        super().hideEvent(event)

    # -- input --------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        control = self.header_control_at(event.position())
        if control == "close":
            self.closeRequested.emit()
            event.accept()
            return
        if control == "gear":
            self.editRequested.emit("")
            event.accept()
            return
        if control.startswith("dot:"):
            self.pageRequested.emit(int(control[4:]))
            event.accept()
            return
        key = self.key_at(event.position())
        if key is None or time.monotonic() < self._armed_at:
            event.ignore()
            return
        self._begin_press(key, self.to_canvas(event.position()))
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # 빠르게 두 번 누르면 Qt는 두 번째 누름을 더블클릭으로 보낸다 — 일반 누름으로 처리.
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._pressed_id:
            key = self._key_by_id(self._pressed_id)
            runtime = self._runtime.get(self._pressed_id)
            if key is not None and runtime is not None:
                geometry = self.renderer.geometry
                inside = geometry.key_rect(key).contains(self.to_canvas(event.position()))
                if inside != self._press_inside:
                    self._press_inside = inside
                    if inside:
                        self._press_runtime(key, runtime, self.to_canvas(event.position()))
                    else:
                        runtime.pending_release = False
                        runtime.tilt.set_target(0.0, 0.0)
                        self._move_to(runtime, self._rest_position(key))
                        self._hold_timer.stop()
                    self._ensure_timer()
            event.accept()
            return
        self.update_hover(event.position())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._pressed_id:
            event.ignore()
            return
        key_id = self._pressed_id
        key = self._key_by_id(key_id)
        runtime = self._runtime.get(key_id)
        self._pressed_id = ""
        self._hold_timer.stop()
        fire = self._press_inside and not self._hold_fired
        if key is not None and runtime is not None:
            if self._press_inside:
                self._release_runtime(key, runtime)
            self._ensure_timer()
        self.update_hover(event.position())
        if fire and key is not None:
            self.keyActivated.emit(key_id, "tap")
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._set_mouse_inside(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._pressed_id:
            self._set_hover("")
        if self._header_hover:
            self._header_hover = ""
            self._update_header()
        self._set_mouse_inside(False)
        super().leaveEvent(event)

    def _set_mouse_inside(self, inside: bool) -> None:
        if inside == self._mouse_inside:
            return
        self._mouse_inside = inside
        geometry = self.renderer.geometry
        if geometry is not None and not geometry.header:
            self._update_close_badge()

    def _update_close_badge(self) -> None:
        geometry = self.renderer.geometry
        if geometry is not None:
            rect = geometry.close_rect.adjusted(-4, -4, 4, 4).translated(self.content_offset())
            self.update(rect.toAlignedRect())

    def wheelEvent(self, event) -> None:  # noqa: N802
        deck = self._deck
        if deck is None or len(deck["pages"]) < 2:
            event.ignore()
            return
        self._wheel_accum += event.angleDelta().y()
        if abs(self._wheel_accum) >= 120:
            step = -1 if self._wheel_accum > 0 else 1
            self._wheel_accum = 0
            self.pageRequested.emit((int(deck["page"]) + step) % len(deck["pages"]))
        event.accept()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            key = self.key_at(event.position() if hasattr(event, "position") else event.pos())
            point = event.position() if hasattr(event, "position") else event.pos()
            control = self.header_control_at(point)
            if control == "close":
                QToolTip.showText(
                    event.globalPos(),
                    t(
                        "widget.launcher.close_tip",
                        "키덱 숨기기 — 상단 '위젯' 메뉴에서 다시 켤 수 있습니다",
                    ),
                    self,
                )
                return True
            if control == "gear":
                QToolTip.showText(
                    event.globalPos(),
                    t("widget.launcher.menu.studio", "KeyDeck 스튜디오 열기..."),
                    self,
                )
                return True
            if key is not None:
                title = key["label"] or t("widget.launcher.unnamed_key", "이름 없는 키")
                lines = [str(title), action_summary(key["action"], self._deck)]
                if key["hold_action"]["type"] != "none":
                    hold = t("widget.launcher.hold_prefix", "길게 누르기")
                    lines.append(f"{hold} · {action_summary(key['hold_action'], self._deck)}")
                QToolTip.showText(event.globalPos(), "\n".join(lines), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def update_hover(self, point) -> None:
        control = self.header_control_at(point)
        if control != self._header_hover:
            self._header_hover = control
            self._update_header()
        key = self.key_at(point) if not control else None
        self._set_hover(key["id"] if key is not None else "")
        if control or (key is not None and key["enabled"]):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif key is not None:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.unsetCursor()

    def _set_hover(self, key_id: str) -> None:
        if key_id == self._hover_id:
            return
        previous = self._hover_id
        self._hover_id = key_id
        for changed in (previous, key_id):
            key = self._key_by_id(changed) if changed else None
            runtime = self._runtime.get(changed) if changed else None
            if key is None or runtime is None:
                continue
            # 호버는 빛으로만 표현한다 (진행 중인 타건 스트로크를 건드리지 않는다).
            runtime.visual.hover = changed == key_id
            self._update_key(key)
        self._sync_movies()
        self._ensure_timer()

    def _update_header(self) -> None:
        geometry = self.renderer.geometry
        if geometry is None:
            return
        rect = geometry.close_rect.united(geometry.gear_rect).adjusted(-4, -4, 4, 4)
        self.update(rect.translated(self.content_offset()).toAlignedRect())

    def _update_key(self, key: dict) -> None:
        geometry = self.renderer.geometry
        if geometry is not None:
            self.update(geometry.paint_rect(key).translated(self.content_offset()).toAlignedRect())

    def _press_runtime(self, key: dict, runtime: _KeyRuntime, point: QPointF | None) -> None:
        """Finger contact: start the stroke, tilt toward the pressed spot, legacy press sound."""
        runtime.pending_release = False
        if self._reduce_motion():
            runtime.spring.snap(1.0)
            runtime.visual.travel = 1.0
            runtime.tilt.snap(0.0, 0.0)
            self._emit_switch_sound(runtime, EVENT_BOTTOM)
            self.update()
        else:
            runtime.spring.press(1.0)
            runtime.tilt.set_target(*self._tilt_for(key, point))
        if runtime.plan is None and (not runtime.spring.profile.click_at or self._reduce_motion()):
            self._play(runtime.press_path)

    def _release_runtime(self, key: dict, runtime: _KeyRuntime) -> None:
        """Finger lifted: finish a too-short tap as a full stroke, then let the cap return."""
        runtime.tilt.set_target(0.0, 0.0)
        if self._reduce_motion():
            runtime.spring.snap(self._rest_position(key))
            runtime.visual.travel = runtime.spring.position
            self._emit_switch_sound(runtime, EVENT_TOP)
            self.update()
        elif runtime.spring.target >= 0.9 and runtime.spring.position < _COMMIT_DEPTH:
            runtime.pending_release = True
        else:
            self._move_to(runtime, self._rest_position(key))
        if runtime.plan is None:
            self._play(runtime.release_path)

    def _tilt_for(self, key: dict, point: QPointF | None) -> tuple[float, float]:
        geometry = self.renderer.geometry
        if point is None or geometry is None:
            return (0.0, 0.0)
        rect = geometry.key_rect(key)
        half_w = max(1.0, rect.width() / 2.0)
        half_h = max(1.0, rect.height() / 2.0)
        dx = max(-1.0, min(1.0, (point.x() - rect.center().x()) / half_w))
        dy = max(-1.0, min(1.0, (point.y() - rect.center().y()) / half_h))
        gain = _TILT_GAIN * (_STABILIZED_TILT if key["w"] >= 2.0 or key["h"] >= 2.0 else 1.0)
        return (dx * gain, dy * gain)

    def _emit_switch_sound(self, runtime: _KeyRuntime, event: str) -> None:
        plan = runtime.plan
        if plan is None:
            if event == EVENT_CLICK:
                self._play(runtime.press_path)
            return
        cue = plan.get(event)
        if cue is None:
            return
        kind, gain = cue
        impact = runtime.spring.impact
        if event == EVENT_BOTTOM:
            gain *= min(1.0, 0.72 + impact / 90.0) if impact else 0.9
        elif event == EVENT_TOP:
            gain *= min(1.0, 0.6 + impact / 40.0) if impact else 0.8
        self._play(pick_switch_sound(kind), gain * random.uniform(0.88, 1.0), voices=1)

    def _begin_press(self, key: dict, point: QPointF | None = None) -> None:
        runtime = self._runtime.get(key["id"])
        if runtime is None:
            return
        if not key["enabled"]:
            if not self._reduce_motion():
                runtime.shake_t = _SHAKE_S * 0.6
            self._ensure_timer()
            return
        self._pressed_id = key["id"]
        self._press_inside = True
        self._hold_fired = False
        self._press_runtime(key, runtime, point)
        if key["led"]["mode"] == "reactive":
            runtime.visual.led = 1.0
        if key["hold_action"]["type"] != "none":
            self._hold_timer.start(HOLD_DELAY_MS)
        self._ensure_timer()

    def _on_hold(self) -> None:
        if not self._pressed_id or not self._press_inside:
            return
        self._hold_fired = True
        runtime = self._runtime.get(self._pressed_id)
        if runtime is not None:
            runtime.flash = 0.6
            runtime.flash_color = self._deck["case"]["accent"] if self._deck else ""
        self.keyActivated.emit(self._pressed_id, "hold")
        self._ensure_timer()

    def _move_to(self, runtime: _KeyRuntime, target: float) -> None:
        if self._reduce_motion():
            runtime.spring.snap(target)
            runtime.visual.travel = runtime.spring.position
            self.update()
        else:
            runtime.spring.set_target(target)

    def _play(self, path: str, gain: float = 1.0, *, voices: int | None = None) -> None:
        deck = self._deck
        if not path or deck is None:
            return
        forced = time.monotonic() < self._force_sound_until
        if not deck.get("sound_enabled", True) and not forced:
            return
        volume = (
            max(0.25, deck.get("sound_volume", 60) / 100.0)
            if forced
            else deck.get("sound_volume", 60) / 100.0
        )
        sound_bank().play(path, volume * gain, voices=voices)

    def _preload_sounds(self) -> None:
        deck = self._deck
        if deck is None or not deck.get("sound_enabled", True):
            return
        paths = set()
        kinds = set()
        for runtime in self._runtime.values():
            if runtime.plan is None:
                paths.update((runtime.press_path, runtime.release_path))
            else:
                kinds.update(kind for kind, _gain in runtime.plan.values())
        sound_bank().preload(sorted(path for path in paths if path))
        for kind in sorted(kinds):
            sound_bank().preload(switch_sound_variants(kind), voices=1)

    # -- animation --------------------------------------------------------------------

    def _ensure_timer(self) -> None:
        if not self._active or not self.isVisible():
            # 숨김 상태에서는 애니메이션 없이 최종 상태로 즉시 정착시킨다.
            self._settle_all()
            return
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start(_FRAME_MS)
        elif self._timer.interval() != _FRAME_MS:
            self._timer.setInterval(_FRAME_MS)

    def _settle_all(self) -> None:
        for key in self._page_keys():
            runtime = self._runtime.get(key["id"])
            if runtime is None:
                continue
            runtime.pending_release = False
            if runtime.spring.target >= 0.9 and key["id"] != self._pressed_id:
                runtime.spring.set_target(self._rest_position(key))
            runtime.spring.snap(runtime.spring.target)
            runtime.visual.travel = runtime.spring.position
            runtime.tilt.snap(0.0, 0.0)
            runtime.visual.tilt_x = runtime.visual.tilt_y = 0.0
            runtime.visual.shake = 0.0
            runtime.shake_t = 0.0
            runtime.flash = 0.0
            runtime.visual.led_color = ""
            active = key["mode"] == "toggle" and key["active"]
            runtime.visual.led = (
                1.0 if active and key["led"]["mode"] in {"reactive", "breathe"} else 0.0
            )
        self._fade_t = 0.0
        self._fade_pixmap = None

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(1.0 / 30.0, max(0.0, now - self._last_tick))
        self._last_tick = now
        geometry = self.renderer.geometry
        if geometry is None:
            self._timer.stop()
            return
        reduce_motion = self._reduce_motion()
        busy = False
        ambient = False
        dirty = QRectF()
        for key in geometry.keys:
            runtime = self._runtime.get(key["id"])
            if runtime is None:
                continue
            visual = runtime.visual
            before = (
                visual.travel,
                visual.led,
                visual.led_color,
                visual.shake,
                visual.tilt_x,
                visual.tilt_y,
            )
            if not runtime.spring.settled:
                for switch_event in runtime.spring.step(dt):
                    self._emit_switch_sound(runtime, switch_event)
                busy = True
            if runtime.pending_release and runtime.spring.position >= _COMMIT_DEPTH:
                runtime.pending_release = False
                runtime.spring.set_target(self._rest_position(key))
                busy = True
            if not runtime.tilt.settled:
                runtime.tilt.step(dt)
                busy = True
            visual.tilt_x, visual.tilt_y = runtime.tilt.x, runtime.tilt.y
            visual.travel = runtime.spring.position
            mode = key["led"]["mode"]
            pressed = key["id"] == self._pressed_id and self._press_inside
            active = key["mode"] == "toggle" and key["active"]
            target_led = 0.0
            if mode == "reactive" and (pressed or active):
                target_led = 1.0
            elif mode == "breathe" and active:
                if reduce_motion:
                    target_led = 0.8
                else:
                    target_led = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(now * math.tau / 2.6))
                    ambient = True
            if target_led >= visual.led or mode == "breathe":
                visual.led = target_led
            else:
                visual.led *= math.exp(-dt / _LED_DECAY_S)
                if visual.led < 0.01:
                    visual.led = 0.0
                else:
                    busy = True
            if runtime.flash > 0.0:
                runtime.flash = max(0.0, runtime.flash - dt / _FLASH_S)
                if runtime.flash > 0.0:
                    visual.led_color = runtime.flash_color
                    visual.led = max(visual.led, math.sin(runtime.flash * math.pi / 2))
                    busy = True
                else:
                    visual.led_color = ""
            if runtime.shake_t > 0.0:
                runtime.shake_t = max(0.0, runtime.shake_t - dt)
                decay = runtime.shake_t / _SHAKE_S
                visual.shake = math.sin(runtime.shake_t * 62.0) * 3.2 * geometry.scale * decay
                busy = True
            else:
                visual.shake = 0.0
            if (
                visual.travel,
                visual.led,
                visual.led_color,
                visual.shake,
                visual.tilt_x,
                visual.tilt_y,
            ) != before:
                dirty = dirty.united(geometry.paint_rect(key))
        if self._fade_t > 0.0:
            self._fade_t = max(0.0, self._fade_t - dt / _FADE_S)
            if self._fade_t <= 0.0:
                self._fade_pixmap = None
            dirty = QRectF(0, 0, geometry.width, geometry.height)
            busy = True
        if not dirty.isEmpty():
            self.update(
                dirty.translated(self.content_offset()).toAlignedRect().adjusted(-2, -2, 2, 2)
            )
        if busy:
            if self._timer.interval() != _FRAME_MS:
                self._timer.setInterval(_FRAME_MS)
        elif ambient:
            if self._timer.interval() != _AMBIENT_MS:
                self._timer.setInterval(_AMBIENT_MS)
        else:
            self._timer.stop()

    # -- animated inserts ---------------------------------------------------------------

    def _sync_movies(self) -> None:
        wanted: dict[str, str] = {}
        for key in self._page_keys():
            insert = key["insert"]
            if insert["kind"] == "image" and insert["path"] and is_animated(insert["path"]):
                wanted[key["id"]] = insert["path"]
        for key_id in list(self._movies):
            movie = self._movies[key_id]
            if wanted.get(key_id) != movie.fileName():
                movie.stop()
                movie.deleteLater()
                del self._movies[key_id]
                runtime = self._runtime.get(key_id)
                if runtime is not None:
                    runtime.visual.frame = None
                    runtime.visual.frame_no = -1
        for key_id, path in wanted.items():
            movie = self._movies.get(key_id)
            if movie is None:
                movie = QMovie(path, parent=self)
                stamp = file_stamp(path)
                small = stamp is not None and stamp[1] <= _MAX_MOVIE_CACHE_BYTES
                movie.setCacheMode(
                    QMovie.CacheMode.CacheAll if small else QMovie.CacheMode.CacheNone
                )
                movie.frameChanged.connect(lambda _frame, kid=key_id: self._on_movie_frame(kid))
                self._movies[key_id] = movie
                movie.jumpToFrame(0)
                self._on_movie_frame(key_id)
            key = self._key_by_id(key_id)
            playback = key["insert"]["playback"] if key is not None else "never"
            if playback == "always" and self._reduce_motion():
                playback = "hover"
            should_play = (
                self._active
                and self.isVisible()
                and (playback == "always" or (playback == "hover" and key_id == self._hover_id))
            )
            if should_play:
                if movie.state() == QMovie.MovieState.NotRunning:
                    movie.start()
                else:
                    movie.setPaused(False)
            elif movie.state() == QMovie.MovieState.Running:
                movie.setPaused(True)

    def _on_movie_frame(self, key_id: str) -> None:
        movie = self._movies.get(key_id)
        runtime = self._runtime.get(key_id)
        key = self._key_by_id(key_id)
        if movie is None or runtime is None or key is None:
            return
        runtime.visual.frame = movie.currentImage()
        runtime.visual.frame_no = movie.currentFrameNumber()
        self._update_key(key)

    # -- drag & drop ---------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return
        key = self.key_at(event.position())
        first = urls[0]
        if (
            key is not None
            and len(urls) == 1
            and first.isLocalFile()
            and Path(first.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
        ):
            self.imageDropped.emit(key["id"], first.toLocalFile())
        else:
            targets = []
            for url in urls[:12]:
                if url.isLocalFile():
                    targets.append(("app", url.toLocalFile()))
                elif url.scheme().lower() in {"http", "https"}:
                    targets.append(("url", url.toString()))
            if targets:
                self.targetsDropped.emit(targets)
        event.acceptProposedAction()


__all__ = ["KeyDeckCanvas", "action_summary"]
