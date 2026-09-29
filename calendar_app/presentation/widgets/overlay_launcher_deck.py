# -*- coding: utf-8 -*-
"""Interactive launcher-deck overlay with mixed-size painted keycaps."""

from __future__ import annotations

import math
from pathlib import Path
import time

from PyQt6.QtCore import QEvent, QFileInfo, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QMovie,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - optional in minimal Qt installs
    QSoundEffect = None

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.hotkey_sender import send_hotkey
from calendar_app.presentation.widgets.launcher_deck_dialog import LauncherDeckEditorDialog
from calendar_app.presentation.widgets.launcher_deck_model import (
    DECK_TEMPLATES,
    deck_from_json,
    deck_to_json,
    keycap_style,
    new_key,
    preserve_deck_visuals,
    reflow_deck,
    template_deck,
)
from calendar_app.presentation.widgets.launcher_keycap_assets import (
    crop_mosaic_pixmap,
    keycap_asset,
)
from calendar_app.presentation.widgets.launcher_keycap_icons import (
    keycap_icon_asset,
    keycap_icon_pack,
)
from calendar_app.presentation.widgets.launcher_keycap_sounds import keycap_sound
from calendar_app.presentation.widgets.overlay_base import _BaseOverlayWidget, _GripFrame
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

_SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}
_ANIMATED_SUFFIXES = {".gif", ".webp"}


def _rgba_color(value: str, fallback: str = "#ffffff") -> QColor:
    raw = str(value or "").strip()
    if raw.startswith("#") and len(raw) == 9:
        try:
            return QColor(
                int(raw[1:3], 16),
                int(raw[3:5], 16),
                int(raw[5:7], 16),
                int(raw[7:9], 16),
            )
        except ValueError:
            pass
    color = QColor(raw)
    return color if color.isValid() else QColor(fallback)


class LauncherKeycapButton(QAbstractButton):
    """Painter-rendered keycap with configurable motion, state, sound, and media."""

    def __init__(
        self,
        key_data: dict,
        execute_callback,
        parent=None,
        state_callback=None,
        deck_data: dict | None = None,
    ):
        super().__init__(parent)
        self.key_data = key_data
        self.deck_data = deck_data or {}
        self._hovered = False
        self._pressed = False
        self._hold_active = False
        self._long_press_fired = False
        self._last_keyboard_release = 0.0
        self._feedback = ""
        self._phase = 0.0
        self._execute_callback = execute_callback
        self._state_callback = state_callback
        self._movie: QMovie | None = None
        self._movie_path = ""
        self._sound_effect = None
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(40)
        self._animation_timer.timeout.connect(self._advance_animation)
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if bool(key_data.get("enabled", True))
            else Qt.CursorShape.ForbiddenCursor
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(str(key_data.get("label", "")))
        self.setAccessibleDescription(self._accessible_state_description())
        self.setToolTip(str(key_data.get("target", "") or key_data.get("label", "")))
        self.clicked.connect(self._on_clicked)
        self._load_asset_movie()
        self._sync_animation_state()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(
            72 * int(self.key_data.get("width", 1)), 64 * int(self.key_data.get("height", 1))
        )

    def _accessible_state_description(self) -> str:
        if not bool(self.key_data.get("enabled", True)):
            return t("widget.launcher.state.disabled", "비활성")
        if bool(self.key_data.get("active", False)):
            return t("widget.launcher.state.active", "활성")
        return t("widget.launcher.state.ready", "실행 준비")

    def _on_clicked(self) -> None:
        if str(self.key_data.get("activation_trigger", "release")) == "release":
            self._execute()

    def _execute(self) -> None:
        if not bool(self.key_data.get("enabled", True)):
            self._feedback = "disabled"
            self._sync_animation_state()
            QTimer.singleShot(420, self._clear_feedback)
            return
        self._feedback = "running"
        self._play_sound("press")
        self._sync_animation_state()
        self.update()
        success = bool(self._execute_callback(self.key_data))
        self._feedback = "success" if success else "error"
        self._play_sound(self._feedback)
        if success and str(self.key_data.get("interaction_mode", "action")) == "toggle":
            self.key_data["active"] = not bool(self.key_data.get("active", False))
            self.setAccessibleDescription(self._accessible_state_description())
            if self._state_callback is not None:
                self._state_callback(self.key_data)
        self._sync_animation_state()
        self.update()
        duration = int(self.key_data.get("feedback_duration_ms", 720) or 720)
        QTimer.singleShot(duration, self._clear_feedback)

    def _clear_feedback(self) -> None:
        self._feedback = ""
        self._sync_animation_state()
        self.update()

    def _play_sound(self, event_name: str) -> None:
        configured_event = str(self.key_data.get("sound_event", "press") or "press")
        allowed = (
            configured_event == "all"
            or configured_event == event_name
            or (configured_event == "result" and event_name in {"success", "error"})
        )
        if not allowed:
            return
        profile = str(self.key_data.get("sound_profile", "none") or "none")
        if profile == "system":
            QApplication.beep()
            return
        if profile == "custom":
            path = Path(str(self.key_data.get("sound_path", "") or ""))
        else:
            bundled = keycap_sound(profile)
            path = bundled.path() if bundled is not None else Path()
        if path.suffix.lower() != ".wav" or not path.is_file():
            return
        if QSoundEffect is None:
            QApplication.beep()
            return
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(max(0, min(int(self.key_data.get("sound_volume", 65)), 100)) / 100.0)
        effect.play()
        self._sound_effect = effect

    def _advance_animation(self) -> None:
        speed = max(50, min(int(self.key_data.get("animation_speed", 100) or 100), 200))
        self._phase = (self._phase + 0.11 * speed / 100.0) % (math.pi * 2)
        self.update()

    def _sync_animation_state(self) -> None:
        reduce_motion = bool(self.key_data.get("reduce_motion", False))
        active = bool(self.key_data.get("active", False)) or self._hold_active
        dynamic = not reduce_motion and (
            (
                active
                and str(self.key_data.get("active_effect", "glow")) in {"glow", "pulse", "breathe"}
            )
            or (
                self._hovered
                and str(self.key_data.get("hover_effect", "lift")) in {"glow", "pulse"}
            )
            or bool(self._feedback)
            or self._pressed
        )
        if dynamic and not self._animation_timer.isActive():
            self._animation_timer.start()
        elif not dynamic:
            self._animation_timer.stop()
            self._phase = 0.0
        self._sync_movie_playback()

    def _load_asset_movie(self) -> None:
        path = self._effective_asset_path()
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        self._movie_path = ""
        if not path.is_file() or path.suffix.lower() not in _ANIMATED_SUFFIXES:
            return
        movie = QMovie(str(path))
        if not movie.isValid():
            return
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.frameChanged.connect(lambda _frame: self.update())
        self._movie = movie
        self._movie_path = str(path)
        self._sync_movie_playback()

    def _sync_movie_playback(self) -> None:
        if self._movie is None:
            return
        mode = str(self.key_data.get("asset_playback", "always") or "always")
        should_play = {
            "always": True,
            "hover": self._hovered,
            "press": self._pressed,
            "active": bool(self.key_data.get("active", False)) or self._hold_active,
            "never": False,
        }.get(mode, True)
        if should_play and self.isVisible():
            if self._movie.state() != QMovie.MovieState.Running:
                self._movie.start()
        else:
            self._movie.setPaused(True)
            if mode == "never":
                self._movie.jumpToFrame(0)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._sync_animation_state()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._sync_animation_state()
        self.update()
        super().leaveEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_animation_state()

    def hideEvent(self, event) -> None:  # noqa: N802
        if self._movie is not None:
            self._movie.setPaused(True)
        self._animation_timer.stop()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._long_press_fired = False
            if str(self.key_data.get("interaction_mode", "action")) == "hold":
                self._hold_active = True
            trigger = str(self.key_data.get("activation_trigger", "release"))
            if trigger == "press":
                self._execute()
            elif trigger == "long":
                self._long_press_timer.start(int(self.key_data.get("long_press_ms", 650)))
            self._sync_animation_state()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._long_press_timer.stop()
        self._pressed = False
        self._hold_active = False
        self._sync_animation_state()
        self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and str(self.key_data.get("activation_trigger", "release")) == "double"
        ):
            self._execute()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _on_long_press(self) -> None:
        if self._pressed and str(self.key_data.get("activation_trigger", "release")) == "long":
            self._long_press_fired = True
            self._execute()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._pressed = True
            if str(self.key_data.get("interaction_mode", "action")) == "hold":
                self._hold_active = True
            trigger = str(self.key_data.get("activation_trigger", "release"))
            if trigger == "press" and not event.isAutoRepeat():
                self._execute()
            elif trigger == "long" and not event.isAutoRepeat():
                self._long_press_timer.start(int(self.key_data.get("long_press_ms", 650)))
            self._sync_animation_state()
            self.update()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        self._long_press_timer.stop()
        self._pressed = False
        self._hold_active = False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            trigger = str(self.key_data.get("activation_trigger", "release"))
            if trigger == "release" and not event.isAutoRepeat():
                self._execute()
            elif trigger == "double" and not event.isAutoRepeat():
                released_at = time.monotonic()
                if released_at - self._last_keyboard_release <= 0.5:
                    self._last_keyboard_release = 0.0
                    self._execute()
                else:
                    self._last_keyboard_release = released_at
        self._sync_animation_state()
        self.update()
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        style = keycap_style(self.key_data.get("style"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = bool(self.key_data.get("enabled", True))
        active = bool(self.key_data.get("active", False)) or self._hold_active
        reduce_motion = bool(self.key_data.get("reduce_motion", False))
        pulse = 0.5 if reduce_motion else (math.sin(self._phase) + 1.0) / 2.0
        painter.setOpacity(1.0 if enabled else 0.62)
        depth_override = int(self.key_data.get("depth_override", -1))
        radius_override = int(self.key_data.get("radius_override", -1))
        depth = depth_override if depth_override >= 0 else style.depth
        radius = radius_override if radius_override >= 0 else style.radius
        hover_effect = str(self.key_data.get("hover_effect", "lift"))
        press_effect = str(self.key_data.get("press_effect", "depress"))
        lift = -2 if self._hovered and not self._pressed and hover_effect == "lift" else 0
        press = depth - 1 if self._pressed and press_effect == "depress" else 0
        if self._pressed and press_effect == "bounce" and not reduce_motion:
            lift -= int(round(2 + pulse * 2))
        offset = lift + press
        base_rect = QRectF(5, 5 + depth, self.width() - 10, self.height() - 10 - depth)
        if (
            self._feedback == "error"
            and str(self.key_data.get("error_effect", "shake")) == "shake"
            and not reduce_motion
        ):
            base_rect.translate(math.sin(self._phase * 4) * 3.0, 0)
        # 두 겹 그림자: 넓고 옅은 겹으로 "화면 위에 떠있는" 느낌, 좁고 진한 겹으로 타일 경계를 정리.
        soft_shadow = base_rect.translated(0, 7 - press)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 46))
        painter.drawRoundedRect(soft_shadow.adjusted(-2, 0, 2, 3), radius + 3, radius + 3)
        shadow = base_rect.translated(0, 3 - press)
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.drawRoundedRect(shadow, radius + 1, radius + 1)

        side_rect = base_rect.translated(0, offset)
        side_gradient = QLinearGradient(side_rect.topLeft(), side_rect.bottomLeft())
        bottom = _rgba_color(self.key_data.get("custom_bottom") or style.bottom, "#263d63")
        side_gradient.setColorAt(0.0, bottom.lighter(118))
        side_gradient.setColorAt(1.0, bottom.darker(126))
        painter.setBrush(side_gradient)
        painter.setPen(QPen(bottom.lighter(132), 1))
        painter.drawRoundedRect(side_rect, radius, radius)

        top_height = max(24.0, side_rect.height() - depth)
        top_rect = QRectF(side_rect.x(), side_rect.y() - depth + 1, side_rect.width(), top_height)
        top = _rgba_color(self.key_data.get("custom_top") or style.top, "#8aa9d9")
        if not enabled:
            top = _rgba_color(self.key_data.get("disabled_top"), "#596273")
        elif active:
            top = _rgba_color(self.key_data.get("active_top"), "#35d39a")
        result_effect = str(
            self.key_data.get(
                "success_effect" if self._feedback == "success" else "error_effect",
                "ring",
            )
        )
        if self._feedback in {"success", "error"} and result_effect == "flash":
            top = QColor("#58dc91" if self._feedback == "success" else "#ff6677")
        active_effect = str(self.key_data.get("active_effect", "glow"))
        if active and active_effect in {"pulse", "breathe"} and not reduce_motion:
            top = top.lighter(int(103 + pulse * (22 if active_effect == "breathe" else 12)))
        top_gradient = QLinearGradient(top_rect.topLeft(), top_rect.bottomLeft())
        hover_light = 122 if self._hovered and enabled else 112
        if self._hovered and hover_effect == "pulse" and not reduce_motion:
            hover_light = int(114 + pulse * 18)
        top_gradient.setColorAt(0.0, top.lighter(hover_light))
        top_gradient.setColorAt(1.0, top.darker(112))
        border = _rgba_color(
            self.key_data.get("custom_border") or self.key_data.get("accent") or style.border,
            "#b8d7ff",
        )
        if active and enabled:
            border = _rgba_color(self.key_data.get("active_border"), "#9affd4")
        if self._feedback == "running":
            border = QColor("#ffd166")
        if self._feedback == "success":
            border = QColor("#58dc91")
        elif self._feedback == "error":
            border = QColor("#ff6677")

        glow_requested = enabled and (
            (active and active_effect == "glow")
            or (self._hovered and hover_effect == "glow")
            or (self._pressed and press_effect == "glow")
        )
        if glow_requested:
            painter.save()
            glow = QColor(border)
            glow.setAlpha(60 + int(pulse * 70))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(glow, 4 + int(pulse * 3)))
            painter.drawRoundedRect(top_rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
            painter.restore()
        border_width = 2 if self.hasFocus() or self._feedback or active else 1
        if self._feedback in {"success", "error"} and result_effect == "pulse":
            border_width = 2 + int(pulse * 3)
        painter.setBrush(top_gradient)
        painter.setPen(QPen(border, border_width))
        painter.drawRoundedRect(top_rect, radius, radius)

        if self._feedback in {"success", "error"} and result_effect == "ring":
            painter.save()
            ring = QColor(border)
            ring.setAlpha(max(35, int(150 - pulse * 95)))
            expansion = 1.0 + pulse * 3.0
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2))
            painter.drawRoundedRect(
                top_rect.adjusted(-expansion, -expansion, expansion, expansion),
                radius + expansion,
                radius + expansion,
            )
            painter.restore()

        if self._pressed and press_effect == "ripple" and not reduce_motion:
            painter.save()
            painter.setClipPath(self._rounded_clip(top_rect, radius))
            ripple = QColor(255, 255, 255, max(25, int(110 - pulse * 70)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ripple, 2))
            diameter = min(top_rect.width(), top_rect.height()) * (0.35 + pulse * 0.85)
            painter.drawEllipse(top_rect.center(), diameter / 2, diameter / 2)
            painter.restore()

        highlight = QColor(255, 255, 255, 42 if self._hovered else 25)
        painter.setPen(QPen(highlight, 2))
        painter.drawLine(
            int(top_rect.left() + radius),
            int(top_rect.top() + 4),
            int(top_rect.right() - radius),
            int(top_rect.top() + 4),
        )

        asset = self._asset_pixmap()
        has_asset = not asset.isNull()
        if has_asset:
            if self._is_mosaic_mode():
                asset_rect = top_rect.adjusted(2, 2, -2, -2)
                asset_opacity = int(self.deck_data.get("mosaic_opacity", 92) or 92)
            else:
                scale = max(40, min(int(self.key_data.get("asset_scale", 100) or 100), 160))
                asset_size = min(top_rect.width(), top_rect.height()) * scale / 100.0
                asset_rect = QRectF(
                    top_rect.center().x() - asset_size / 2,
                    top_rect.center().y() - asset_size / 2,
                    asset_size,
                    asset_size,
                )
                asset_opacity = int(self.key_data.get("asset_opacity", 42) or 42)
            painter.save()
            painter.setClipPath(self._rounded_clip(top_rect, radius))
            painter.setOpacity(max(10, min(asset_opacity, 100)) / 100.0)
            painter.drawPixmap(asset_rect.toRect(), asset)
            painter.restore()

        icon = self._resolved_icon()
        label = str(self.key_data.get("label", ""))
        if self._is_mosaic_mode() and not bool(self.deck_data.get("mosaic_show_labels", True)):
            icon = QIcon()
            label = ""
        content_rect = top_rect.adjusted(8, 7, -8, -6)
        label_layout = str(self.key_data.get("label_layout", "icon_above"))
        if label_layout == "text_only":
            icon = QIcon()
        if label_layout == "icon_only":
            label = ""
        # 스트림덱 스타일: 커스텀 이미지가 없어도 아이콘이 타일 대부분을 채우고
        # 라벨은 하단의 얇은 캡션 한 줄로만 보여준다. icon_left 배치만 예외.
        graphic_mode = (has_asset or not icon.isNull()) and label_layout not in {
            "text_only",
            "icon_left",
        }
        icon_size = max(
            22,
            min(
                64 if graphic_mode else 30,
                int(content_rect.height() * (0.62 if graphic_mode else 0.46)),
            ),
        )
        if graphic_mode:
            caption_height = min(20.0, max(15.0, content_rect.height() * 0.22)) if label else 0.0
            visual_rect = content_rect.adjusted(0, 0, 0, -(caption_height + (3 if label else 0)))
            if not icon.isNull():
                visual_icon_size = min(
                    icon_size, int(min(visual_rect.width(), visual_rect.height()))
                )
                icon_rect = QRectF(
                    visual_rect.center().x() - visual_icon_size / 2,
                    visual_rect.center().y() - visual_icon_size / 2,
                    visual_icon_size,
                    visual_icon_size,
                )
                icon.paint(painter, icon_rect.toRect())
            text_rect = (
                QRectF(
                    content_rect.left(),
                    content_rect.bottom() - caption_height,
                    content_rect.width(),
                    caption_height,
                )
                if label
                else QRectF()
            )
        elif not icon.isNull() and label_layout == "icon_left" and label:
            icon_rect = QRectF(
                content_rect.left(),
                content_rect.center().y() - icon_size / 2,
                icon_size,
                icon_size,
            )
            icon.paint(painter, icon_rect.toRect())
            text_rect = QRectF(
                icon_rect.right() + 5,
                content_rect.top(),
                max(12.0, content_rect.right() - icon_rect.right() - 5),
                content_rect.height(),
            )
        else:
            text_rect = content_rect
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(7, min(11, int(text_rect.height() * 0.55))))
        font_scale = max(70, min(int(self.key_data.get("font_scale", 100) or 100), 160))
        font.setPointSize(max(6, int(round(font.pointSize() * font_scale / 100.0))))
        painter.setFont(font)
        text_color = self.key_data.get("custom_text") or style.text
        if not enabled:
            text_color = self.key_data.get("disabled_text") or "#aeb7c6cc"
        resolved_text_color = _rgba_color(text_color, "#ffffff")
        if graphic_mode:
            # 캡션 밴드는 한 줄 고정 — 길면 말줄임표로 잘라 "텍스트 board" 느낌을 없앤다.
            draw_text = QFontMetrics(font).elidedText(
                label, Qt.TextElideMode.ElideRight, max(0, int(text_rect.width()))
            )
        else:
            draw_text = label
            longest_word = max(label.split(), key=len, default="")
            while font.pointSize() > 7 and QFontMetrics(font).horizontalAdvance(longest_word) > int(
                text_rect.width()
            ):
                font.setPointSize(font.pointSize() - 1)
                painter.setFont(font)
        if graphic_mode and label and not text_rect.isEmpty():
            painter.save()
            backdrop = (
                QColor(0, 0, 0, 92)
                if resolved_text_color.lightness() >= 150
                else QColor(255, 255, 255, 112)
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(backdrop)
            painter.drawRoundedRect(text_rect.adjusted(1, 0, -1, 0), 7, 7)
            painter.restore()
        painter.setPen(resolved_text_color)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter
            | (Qt.TextFlag.TextSingleLine if graphic_mode else Qt.TextFlag.TextWordWrap),
            draw_text,
        )
        if bool(self.key_data.get("show_status_indicator", True)) and (
            self._feedback or active or not enabled
        ):
            indicator = border
            if not enabled:
                indicator = QColor("#8c96a8")
            painter.setBrush(border)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(indicator)
            painter.drawEllipse(int(top_rect.right() - 11), int(top_rect.top() + 7), 5, 5)
        painter.end()

    @staticmethod
    def _rounded_clip(rect: QRectF, radius: int):
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _asset_pixmap(self) -> QPixmap:
        custom_path = self._effective_asset_path()
        if (
            custom_path.suffix.lower() in _ANIMATED_SUFFIXES
            and str(custom_path) != self._movie_path
        ):
            self._load_asset_movie()
        if self._movie is not None:
            frame = self._movie.currentPixmap()
            if not frame.isNull():
                return self._crop_mosaic_asset(frame)
        if custom_path.exists() and custom_path.suffix.lower() in _IMAGE_SUFFIXES:
            return self._crop_mosaic_asset(QPixmap(str(custom_path)))
        asset = keycap_asset(self.key_data.get("asset_id"))
        asset_path = asset.path()
        return QPixmap(str(asset_path)) if asset.filename and asset_path.exists() else QPixmap()

    def _is_mosaic_mode(self) -> bool:
        return bool(self.deck_data.get("mosaic_enabled", False)) and bool(
            str(self.deck_data.get("mosaic_path", "") or "")
        )

    def _effective_asset_path(self) -> Path:
        if self._is_mosaic_mode():
            return Path(str(self.deck_data.get("mosaic_path", "") or ""))
        return Path(str(self.key_data.get("asset_path", "") or ""))

    def _crop_mosaic_asset(self, source: QPixmap) -> QPixmap:
        if source.isNull() or not self._is_mosaic_mode():
            return source
        return crop_mosaic_pixmap(source, self.deck_data, self.key_data)

    def _resolved_icon(self):
        icon_choice = str(self.key_data.get("icon", "auto") or "auto")
        if icon_choice == "none":
            return QIcon()
        style = keycap_style(self.key_data.get("style"))
        pack = keycap_icon_pack(self.deck_data.get("icon_pack"))
        icon_color = _rgba_color(
            self.key_data.get("custom_text") or pack.color or style.text,
            "#ffffff",
        ).name()
        custom_icon = keycap_icon_asset(icon_choice)
        if custom_icon.icon_key:
            return _ic(custom_icon.icon_key, color=icon_color)
        action_type = str(self.key_data.get("action_type", ""))
        target = str(self.key_data.get("target", ""))
        if action_type == "open" and target:
            path = Path(target)
            if path.exists():
                return QFileIconProvider().icon(QFileInfo(str(path)))
            return _ic(ICON.FOLDER, color=icon_color)
        if action_type == "url":
            return _ic(ICON.GLOBE, color=icon_color)
        if action_type == "hotkey":
            return _ic(ICON.WIDGET_LAUNCHER, color=icon_color)
        internal_icons = {
            "new_task": ICON.ADD,
            "today": ICON.GOTO_TODAY,
            "sync_google": ICON.SYNC,
            "command_palette": ICON.SEARCH,
            "widget_manager": ICON.WIDGET_MGR,
        }
        return _ic(internal_icons.get(target, ICON.PLAY), color=icon_color)


class OverlayLauncherDeckWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_launcher_deck"
    _DEFAULT_BG_RGBA = "#c20d1420"
    _DEFAULT_BORDER_RGBA = "#467da7d9"
    _STYLES = [("default", "Launcher Deck")]
    _STYLE_I18N_PREFIX = "widget.launcher"

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 10

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("launcherDeckFace")
        frame.setAcceptDrops(True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self._grip_label = QLabel(t("widget.launcher.title", "LAUNCH DECK"), frame)
        self._grip_label.setStyleSheet(
            "background: transparent; border: none; font-size: 9px; font-weight: 700;"
        )
        header.addWidget(self._grip_label)
        header.addStretch()
        self._edit_button = QToolButton(frame)
        self._edit_button.setIcon(_ic(ICON.EDIT))
        self._edit_button.setToolTip(t("widget.launcher.edit", "키캡 배열 편집"))
        self._edit_button.setAutoRaise(True)
        self._edit_button.clicked.connect(self._open_settings)
        header.addWidget(self._edit_button)
        layout.addLayout(header)
        self._grid_host = QWidget(frame)
        self._grid_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._grid_host)
        self._key_buttons: dict[str, LauncherKeycapButton] = {}
        self._rebuild_keys()
        return frame

    def eventFilter(self, watched, event):
        if isinstance(watched, (LauncherKeycapButton, QToolButton)):
            return QWidget.eventFilter(self, watched, event)
        if event.type() == QEvent.Type.DragEnter and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return True
        if event.type() == QEvent.Type.Drop and event.mimeData().hasUrls():
            self._add_dropped_urls(event.mimeData().urls())
            event.acceptProposedAction()
            return True
        return super().eventFilter(watched, event)

    def _deck(self) -> dict:
        return deck_from_json(self._get("launcher_deck_data", ""))

    def _store_deck(self, deck: dict) -> None:
        self._set("launcher_deck_data", deck_to_json(deck))

    def _rebuild_keys(self) -> None:
        if not hasattr(self, "_grid"):
            return
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._key_buttons.clear()
        deck = self._deck()
        self._grid.setSpacing(int(deck["gap"]))
        for column in range(24):
            self._grid.setColumnMinimumWidth(column, 0)
            self._grid.setColumnStretch(column, 0)
        for row in range(64):
            self._grid.setRowMinimumHeight(row, 0)
            self._grid.setRowStretch(row, 0)
        for column in range(int(deck["columns"])):
            self._grid.setColumnMinimumWidth(column, 62)
            self._grid.setColumnStretch(column, 1)
        for row in range(int(deck["rows"])):
            self._grid.setRowMinimumHeight(row, 58)
            self._grid.setRowStretch(row, 1)
        for key in deck["keys"]:
            button = LauncherKeycapButton(
                key,
                self._execute_key,
                self._grid_host,
                state_callback=self._persist_key_state,
                deck_data=deck,
            )
            button.installEventFilter(self)
            self._grid.addWidget(
                button,
                int(key["row"]),
                int(key["column"]),
                int(key["height"]),
                int(key["width"]),
            )
            self._key_buttons[str(key["id"])] = button

    def _persist_key_state(self, changed_key: dict) -> None:
        deck = self._deck()
        changed_id = str(changed_key.get("id", ""))
        for key in deck["keys"]:
            if str(key.get("id", "")) == changed_id:
                key["active"] = bool(changed_key.get("active", False))
                break
        self._store_deck(deck)

    def _apply_appearance(self) -> None:
        self._apply_base_appearance()
        color = self._text_color_str()
        self._grip_label.setStyleSheet(
            f"background: transparent; border: none; color: {color}; "
            "font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        self._edit_button.setIcon(
            _ic(ICON.EDIT, color=color[:7] if color.startswith("#") else None)
        )

    def _refresh_face(self) -> None:
        self._rebuild_keys()

    def _execute_key(self, key: dict) -> bool:
        action_type = str(key.get("action_type", ""))
        target = str(key.get("target", "") or "").strip()
        if action_type == "internal":
            return self._execute_internal(target)
        if action_type == "url":
            url = QUrl(target)
            if url.scheme().lower() not in {"http", "https"}:
                return False
            return bool(QDesktopServices.openUrl(url))
        if action_type == "hotkey":
            return send_hotkey(target)
        path = Path(target)
        if not target or not path.exists() or path.suffix.lower() in _SCRIPT_SUFFIXES:
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))

    def _execute_internal(self, command: str) -> bool:
        owner = self.owner
        handlers = {
            "new_task": lambda: owner.open_task_dialog(),
            "today": lambda: owner.jump_to_today(),
            "sync_google": lambda: owner.sync_google_calendar(),
            "command_palette": lambda: owner.show_command_palette(),
            "widget_manager": lambda: owner.overlay_manager._open_manager_dialog(),
        }
        handler = handlers.get(command)
        if handler is None:
            return False
        try:
            handler()
            return True
        except Exception:
            return False

    def _add_dropped_urls(self, urls: list[QUrl]) -> None:
        deck = self._deck()
        added = 0
        for url in urls[:12]:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if not path.exists() or path.suffix.lower() in _SCRIPT_SUFFIXES:
                    continue
                deck["keys"].append(
                    new_key(
                        path.stem or path.name,
                        int(deck["rows"]),
                        0,
                        action_type="open",
                        target=str(path),
                    )
                )
                added += 1
            elif url.scheme().lower() in {"http", "https"}:
                deck["keys"].append(
                    new_key(
                        url.host() or "Web",
                        int(deck["rows"]),
                        0,
                        action_type="url",
                        target=url.toString(),
                    )
                )
                added += 1
        if added:
            self._apply_deck_layout(reflow_deck(deck))

    def _apply_deck_layout(self, deck: dict) -> None:
        """Apply an array and return the outer window to content-fit sizing."""
        self._store_deck(deck)
        self._rebuild_keys()
        self._set("fixed_w", None)
        self._set("fixed_h", None)
        self._release_layout_constraints()
        self._apply_and_resize()
        if self.isVisible():
            self.adjustSize()

    def _open_settings(self) -> None:
        dialog = LauncherDeckEditorDialog(self._deck(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_deck_layout(dialog.result_deck())

    def _apply_template(self, template_id: str) -> None:
        deck = preserve_deck_visuals(self._deck(), template_deck(template_id))
        self._apply_deck_layout(deck)

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(t("widget.launcher.edit", "키캡 배열 편집..."), self._open_settings)
        template_menu = menu.addMenu(t("widget.launcher.templates", "배열 템플릿"))
        for template_id, key, fallback, _factory in DECK_TEMPLATES:
            template_menu.addAction(
                t(key, fallback),
                lambda *_, selected=template_id: self._apply_template(selected),
            )
        menu.addAction(
            t("widget.launcher.reset", "기본 혼합 배열로 초기화"),
            lambda: self._apply_template("mixed_4x3"),
        )

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def _action_reset_position(self):
        self.center_on_owner()

    def apply_initial_settings(self):
        if not self._setting_exists("launcher_deck_data"):
            self._store_deck(template_deck("mixed_4x3"))
        self._rebuild_keys()
        self._apply_and_resize()
        self.restore_position(QPoint(-520, 120))
        if self.is_enabled():
            self._show_with_correct_size()


__all__ = ["LauncherKeycapButton", "OverlayLauncherDeckWidget"]
