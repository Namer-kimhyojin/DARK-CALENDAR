# -*- coding: utf-8 -*-
"""KeyDeck renderer: deck geometry, cached layers and the keycap painting pipeline.

Layer order for one key (bottom → top):
    background cache (case, plate, switch housing + stem, static LEDs)
    → dynamic LED underglow → cap drop shadow → skirt (side walls)
    → cached cap top (clear rim, insert art, legend, glass) moved by travel
    → light passing through the cap, hover sheen, press shade, disabled veil
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.keydeck.model import (
    auto_glyph,
    layout_bounds,
    panorama_rect,
)
from calendar_app.presentation.widgets.keydeck.physics import switch_profile
from calendar_app.presentation.widgets.keydeck.resources import (
    LruCache,
    file_icon_pixmap,
    file_stamp,
    glyph_pixmap,
    panorama_image,
    pattern_image,
    source_image,
)

_FONT_FAMILIES = [
    "Segoe UI Variable Text",
    "Segoe UI",
    "Malgun Gothic",
    "Apple SD Gothic Neo",
    "Noto Sans CJK KR",
]
_WEIGHTS = {
    "regular": QFont.Weight.Normal,
    "medium": QFont.Weight.DemiBold,
    "bold": QFont.Weight.Bold,
}
SUCCESS_COLOR = "#3ddc84"
ERROR_COLOR = "#ff5d6c"


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    body_alpha: float
    skirt_alpha: float
    transmission: float
    clear_rim: bool
    diffusion: float
    smoke: float
    sheen: float
    edge_glow: float


MATERIAL_SPECS = {
    "crystal": MaterialSpec(0.05, 0.2, 1.00, True, 0.00, 0.00, 0.30, 1.00),
    "frosted": MaterialSpec(0.52, 0.66, 0.80, True, 0.14, 0.00, 0.16, 0.85),
    "smoke": MaterialSpec(0.58, 0.66, 0.55, True, 0.00, 0.20, 0.20, 0.65),
    "pudding": MaterialSpec(1.00, 0.36, 0.95, False, 0.00, 0.00, 0.14, 1.00),
    "solid": MaterialSpec(1.00, 1.00, 0.00, False, 0.00, 0.00, 0.10, 0.30),
}


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    skirt: float  # 옆면 높이 (= 누름 거리)
    radius: float  # 모서리 둥글기 (키 크기 대비)
    dish: str  # 윗면 음영: cylindrical/spherical/deep/flat/chiclet/round
    side: float = 1.0  # 윗면이 바닥보다 좁아지는 정도 (높은 프로필일수록 큼)
    round: bool = False  # 원형(타자기) 키캡


PROFILE_SPECS = {
    "cylindrical": ProfileSpec(1.0, 0.13, "cylindrical"),
    "oem": ProfileSpec(1.14, 0.09, "cylindrical", side=1.12),
    "spherical": ProfileSpec(1.28, 0.19, "spherical", side=1.2),
    "mt3": ProfileSpec(1.5, 0.21, "deep", side=1.55),
    "flat": ProfileSpec(0.7, 0.11, "flat"),
    "xda": ProfileSpec(0.8, 0.17, "spherical", side=0.45),
    "low": ProfileSpec(0.42, 0.09, "chiclet", side=0.35),
    "round": ProfileSpec(0.95, 0.5, "round", side=1.1, round=True),
}


def _material(key: dict) -> MaterialSpec:
    return MATERIAL_SPECS.get(key["cap"]["material"], MATERIAL_SPECS["crystal"])


def _profile(key: dict) -> ProfileSpec:
    return PROFILE_SPECS.get(key["cap"]["profile"], PROFILE_SPECS["cylindrical"])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _with_alpha(color: QColor | str, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlphaF(_clamp(alpha, 0.0, 1.0))
    return result


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = _clamp(amount, 0.0, 1.0)
    return QColor(
        int(first.red() + (second.red() - first.red()) * amount),
        int(first.green() + (second.green() - first.green()) * amount),
        int(first.blue() + (second.blue() - first.blue()) * amount),
        int(first.alpha() + (second.alpha() - first.alpha()) * amount),
    )


def legend_font(pixel_size: float, weight: str = "bold") -> QFont:
    font = QFont()
    font.setFamilies(_FONT_FAMILIES)
    font.setPixelSize(max(6, int(round(pixel_size))))
    font.setWeight(_WEIGHTS.get(weight, QFont.Weight.Bold))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _flag_value(flags) -> int:
    return int(flags.value if hasattr(flags, "value") else flags)


def _wrap_lines(text: str, metrics: QFontMetricsF, width: float) -> list[str]:
    """Greedy word wrap; words longer than a line (e.g. Korean without spaces) break by char."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and metrics.horizontalAdvance(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
            while len(line) > 1 and metrics.horizontalAdvance(line) > width:
                cut = len(line) - 1
                while cut > 1 and metrics.horizontalAdvance(line[:cut]) > width:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines


def fill_text(
    painter: QPainter,
    rect: QRectF,
    flags,
    text: str,
    font: QFont,
    color: QColor,
    *,
    wrap: bool = False,
) -> None:
    """Draw text as filled glyph outlines inside ``rect`` honouring Qt alignment flags.

    ``drawText`` uses ClearType on opaque keycaps, which leaves red/blue fringes on thin
    strokes (Hangul jamo, brackets) and looks worse once a pressed cap is drawn in
    perspective.  Filled outlines are always greyscale-antialiased.
    """
    if not text:
        return
    metrics = QFontMetricsF(font)
    lines = _wrap_lines(text, metrics, rect.width()) if wrap else [text]
    value = _flag_value(flags)
    spacing = metrics.lineSpacing()
    total = spacing * (len(lines) - 1) + metrics.height()
    if value & _flag_value(Qt.AlignmentFlag.AlignBottom):
        top = rect.bottom() - total
    elif value & _flag_value(Qt.AlignmentFlag.AlignVCenter):
        top = rect.center().y() - total / 2.0
    else:
        top = rect.top()
    path = QPainterPath()
    for index, line in enumerate(lines):
        width = metrics.horizontalAdvance(line)
        if value & _flag_value(Qt.AlignmentFlag.AlignRight):
            x = rect.right() - width
        elif value & _flag_value(Qt.AlignmentFlag.AlignHCenter):
            x = rect.center().x() - width / 2.0
        else:
            x = rect.left()
        path.addText(QPointF(x, top + index * spacing + metrics.ascent()), font, line)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.fillPath(path, color)
    painter.restore()


@dataclass(slots=True)
class KeyVisualState:
    """Runtime look of one key; the canvas mutates these between frames."""

    travel: float = 0.0
    led: float = 0.0
    led_color: str = ""
    hover: bool = False
    shake: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    frame: QImage | None = None
    frame_no: int = -1


IDLE_STATE = KeyVisualState()


@dataclass(slots=True)
class CapMetrics:
    base: QRectF
    top: QRectF
    radius: float
    top_radius: float
    skirt: float
    travel_px: float
    rim: float


class DeckGeometry:
    """Pixel geometry of one deck page at a given scale."""

    def __init__(
        self,
        deck: dict,
        page_index: int | None = None,
        *,
        scale: float | None = None,
        grid_min: tuple[float, float] | None = None,
        fixed_origin: bool = False,
        header: bool | None = None,
    ):
        raw_scale = deck.get("scale", 100) / 100.0 if scale is None else scale
        self.scale = s = _clamp(float(raw_scale), 0.15, 4.0)
        self.unit = float(deck["unit"]) * s
        self.gap = float(deck["gap"]) * s
        case = deck["case"]
        self.case_style = str(case["style"])
        self.floating = self.case_style == "floating"
        self.header = bool(case["header"]) if header is None else bool(header)
        pages = deck["pages"]
        index = int(deck.get("page", 0)) if page_index is None else int(page_index)
        self.page_index = max(0, min(index, len(pages) - 1))
        self.keys: list[dict] = pages[self.page_index]["keys"]
        bounds = layout_bounds(self.keys)
        min_x, min_y, max_x, max_y = bounds
        if fixed_origin or not self.keys:
            min_x = min_y = 0.0
        if not self.keys:
            max_x, max_y = 3.0, 1.0
        grid_w = max(max_x - min_x, 1.0)
        grid_h = max(max_y - min_y, 1.0)
        if grid_min is not None:
            grid_w = max(grid_w, float(grid_min[0]))
            grid_h = max(grid_h, float(grid_min[1]))
        self.origin_u = (min_x, min_y)
        self.grid_u = (grid_w, grid_h)
        self.margin = round(14 * s)
        self.bezel = 0.0 if self.floating else round(11 * s)
        self.well_pad = 0.0 if self.floating else round(5 * s)
        self.header_h = float(round(22 * s)) if self.header else 0.0
        self.case_radius = round(16 * s)
        left = self.margin + self.bezel + self.well_pad
        top = self.margin + self.bezel + self.header_h + self.well_pad
        self.keys_rect = QRectF(left, top, grid_w * self.unit, grid_h * self.unit)
        # 파노라마 기준 영역: 스튜디오의 편집 여백(grid_min)과 무관하게 키가 놓인 범위만 쓴다.
        # 그래야 스튜디오에서 본 잘림 위치가 실제 위젯과 같다.
        if self.keys:
            self.content_rect = QRectF(
                left + (bounds[0] - min_x) * self.unit,
                top + (bounds[1] - min_y) * self.unit,
                max(bounds[2] - bounds[0], 0.25) * self.unit,
                max(bounds[3] - bounds[1], 0.25) * self.unit,
            )
        else:
            self.content_rect = QRectF(self.keys_rect)
        self.plate_rect = self.keys_rect.adjusted(
            -self.well_pad, -self.well_pad, self.well_pad, self.well_pad
        )
        self.case_rect = self.plate_rect.adjusted(
            -self.bezel, -(self.bezel + self.header_h), self.bezel, self.bezel
        )
        self.width = int(math.ceil(self.case_rect.right() + self.margin))
        self.height = int(math.ceil(self.case_rect.bottom() + self.margin))
        mid_y = self.case_rect.top() + (self.bezel + self.header_h) * 0.5 + self.bezel * 0.08
        control = max(10.0, self.header_h * 0.8)
        if self.header:
            # 헤더 오른쪽 끝: [페이지 점] [설정] [닫기]
            self.close_rect = QRectF(
                self.plate_rect.right() - control, mid_y - control / 2, control, control
            )
            self.gear_rect = QRectF(
                self.close_rect.left() - control - 4 * s, mid_y - control / 2, control, control
            )
        else:
            # 헤더가 없으면 케이스 오른쪽 위 모서리에 걸친 배지로 닫기 버튼을 둔다 (호버 시 표시).
            badge = max(12.0, 18.0 * s)
            self.close_rect = QRectF(
                self.case_rect.right() - badge * 0.62,
                self.case_rect.top() - badge * 0.38,
                badge,
                badge,
            )
            self.gear_rect = QRectF(
                self.plate_rect.right() - control, mid_y - control / 2, control, control
            )
        self.title_rect = QRectF(
            self.plate_rect.left() + 2 * s,
            mid_y - self.header_h / 2,
            max(0.0, self.plate_rect.width() * 0.62),
            self.header_h,
        )
        self.page_count = len(pages)
        self.dot_rects: list[QRectF] = []
        if self.header and self.page_count > 1:
            dot = 6.0 * s
            active_w = 14.0 * s
            spacing = 5.0 * s
            total = active_w + (self.page_count - 1) * (dot + spacing)
            x = self.gear_rect.left() - 10 * s - total
            for page in range(self.page_count):
                width = active_w if page == self.page_index else dot
                self.dot_rects.append(QRectF(x, mid_y - dot / 2, width, dot))
                x += width + spacing

    def size(self) -> QSize:
        return QSize(self.width, self.height)

    def key_rect(self, key: dict) -> QRectF:
        half = self.gap / 2.0
        return QRectF(
            self.keys_rect.left() + (float(key["x"]) - self.origin_u[0]) * self.unit + half,
            self.keys_rect.top() + (float(key["y"]) - self.origin_u[1]) * self.unit + half,
            float(key["w"]) * self.unit - self.gap,
            float(key["h"]) * self.unit - self.gap,
        )

    def paint_rect(self, key: dict) -> QRectF:
        margin = self.unit * 0.45
        return self.key_rect(key).adjusted(-margin, -margin, margin, margin)

    def to_u(self, point: QPointF) -> tuple[float, float]:
        return (
            (point.x() - self.keys_rect.left()) / self.unit + self.origin_u[0],
            (point.y() - self.keys_rect.top()) / self.unit + self.origin_u[1],
        )

    def hit_key(self, point: QPointF) -> dict | None:
        for key in reversed(self.keys):
            if self.key_rect(key).contains(point):
                return key
        return None

    def cap_metrics(self, key: dict, rect: QRectF | None = None) -> CapMetrics:
        base = self.key_rect(key) if rect is None else rect
        profile = _profile(key)
        unit = self.unit
        skirt = _clamp(unit * 0.1 * profile.skirt, 2.5, 18.0)
        side = _clamp(unit * 0.05 * profile.side, 0.8, 10.0)
        back = _clamp(unit * 0.016, 0.5, 3.0)
        top = QRectF(
            base.left() + side,
            base.top() + back,
            max(4.0, base.width() - 2 * side),
            max(4.0, base.height() - back - skirt),
        )
        if profile.round:
            # 원형 키캡: 바닥과 윗면 모두 원(길쭉한 키는 알약 모양)이 되도록 맞춘다.
            radius = min(base.width(), base.height()) / 2.0
            if base.width() <= base.height() * 1.05:
                size = min(top.width(), top.height())
                top = QRectF(base.center().x() - size / 2.0, top.top(), size, size)
            top_radius = min(top.width(), top.height()) / 2.0
        else:
            radius = _clamp(unit * profile.radius, 3.0, 18.0)
            top_radius = max(2.0, radius * 0.86)
        rim = _clamp(unit * 0.07, 2.0, 8.0) if _material(key).clear_rim else 0.0
        return CapMetrics(
            base=base,
            top=top,
            radius=radius,
            top_radius=top_radius,
            skirt=skirt,
            travel_px=skirt * 0.74,
            rim=rim,
        )


def fit_scale(deck: dict, page_index: int | None, width: int, height: int, **kwargs) -> float:
    """Largest scale at which a page fits inside width×height."""
    probe = DeckGeometry(deck, page_index, scale=1.0, **kwargs)
    return _clamp(min(width / max(1, probe.width), height / max(1, probe.height)), 0.15, 4.0)


class KeyDeckRenderer:
    """Paints a deck page; owns the per-instance layer caches."""

    def __init__(self):
        self.deck: dict | None = None
        self.geometry: DeckGeometry | None = None
        self._geometry_args: dict = {}
        self._background: QPixmap | None = None
        self._background_key: tuple | None = None
        self._tops: dict[str, tuple[tuple, QPixmap]] = {}
        self._signatures: dict[str, tuple] = {}
        self._shadows = LruCache(48)
        self._revision = 0
        self.empty_hint = ""

    # -- state -------------------------------------------------------------

    def set_deck(self, deck: dict, page_index: int | None = None, **geometry_args) -> None:
        self.deck = deck
        self._geometry_args = dict(geometry_args)
        self.geometry = DeckGeometry(deck, page_index, **geometry_args)
        self._background_key = None
        self._signatures.clear()
        # 현재 페이지 키의 캐시만 유지해 페이지를 오가도 메모리가 누적되지 않게 한다.
        live_ids = {key["id"] for key in self.geometry.keys}
        self._tops = {key_id: entry for key_id, entry in self._tops.items() if key_id in live_ids}
        self._revision += 1

    def relayout(self, **overrides) -> None:
        if self.deck is None or self.geometry is None:
            return
        args = dict(self._geometry_args)
        args.update(overrides)
        self.set_deck(self.deck, self.geometry.page_index, **args)

    def invalidate_background(self) -> None:
        """Re-render only the background (switch housings follow moved keys)."""
        self._background_key = None

    def invalidate(self, key_ids: set[str] | None = None) -> None:
        """Drop cached layers after edits (all keys when ``key_ids`` is None)."""
        self._background_key = None
        if key_ids is None:
            self._tops.clear()
            self._signatures.clear()
        else:
            for key_id in key_ids:
                self._tops.pop(key_id, None)
                self._signatures.pop(key_id, None)
        self._revision += 1

    # -- public painting ------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        states: dict[str, KeyVisualState] | None = None,
        *,
        dpr: float = 1.0,
        clip: QRectF | None = None,
        header_hover: str = "",
        led_brightness: float | None = None,
        show_close: bool = False,
    ) -> None:
        geometry = self.geometry
        deck = self.deck
        if geometry is None or deck is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        brightness = (
            deck.get("led_brightness", 80) / 100.0 if led_brightness is None else led_brightness
        )
        painter.drawPixmap(0, 0, self._background_pixmap(dpr, brightness))
        states = states or {}
        for key in sorted(geometry.keys, key=lambda item: (item["y"], item["x"])):
            if clip is not None and not geometry.paint_rect(key).intersects(clip):
                continue
            self.paint_key(painter, key, states.get(key["id"], IDLE_STATE), dpr, brightness)
        if not geometry.keys and self.empty_hint:
            self._paint_empty_hint(painter, geometry.keys_rect)
        if geometry.header:
            self._paint_header_controls(painter, header_hover, dpr)
        if geometry.header or show_close:
            self._paint_close_control(painter, header_hover == "close", dpr)

    def _paint_empty_hint(self, painter: QPainter, area: QRectF) -> None:
        """Centre the empty-page hint, wrapping and shrinking it so it is never clipped."""
        box = area.adjusted(area.width() * 0.06, 4, -area.width() * 0.06, -4)
        flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        size = max(9.0, self.geometry.unit * 0.17)
        font = legend_font(size, "medium")
        for _attempt in range(8):
            font = legend_font(size, "medium")
            bounds = QFontMetricsF(font).boundingRect(box, flags, self.empty_hint)
            if bounds.width() <= box.width() + 0.5 and bounds.height() <= box.height() + 0.5:
                break
            size = max(7.0, size * 0.86)
        fill_text(
            painter,
            box,
            flags,
            self.empty_hint,
            font,
            _with_alpha(self._header_ink(), 0.8),
            wrap=True,
        )

    def paint_key(
        self,
        painter: QPainter,
        key: dict,
        state: KeyVisualState,
        dpr: float = 1.0,
        brightness: float = 0.8,
    ) -> None:
        geometry = self.geometry
        if geometry is None:
            return
        rect = geometry.key_rect(key)
        if state.shake:
            rect.translate(state.shake, 0)
        metrics = geometry.cap_metrics(key, rect)
        material = _material(key)
        travel = _clamp(state.travel, -0.2, 1.0)
        offset = travel * metrics.travel_px
        enabled = bool(key["enabled"])
        led_color = state.led_color or key["led"]["color"]
        led_level = state.led * brightness if enabled or state.led_color else 0.0
        if led_level > 0.01:
            self._paint_glow(painter, metrics.base, led_color, led_level * material.edge_glow)
        self._paint_shadow(painter, key, metrics, travel)
        self._paint_skirt(painter, key, metrics, travel, material)
        top_rect = metrics.top.translated(0, offset)
        pixmap = self._top_pixmap(key, metrics, dpr, state)
        press = _clamp(travel, 0.0, 1.0)
        painter.save()
        quad = self._top_quad(top_rect, state.tilt_x, state.tilt_y, press, metrics.travel_px)
        transform = QTransform()
        if quad is not None and QTransform.quadToQuad(
            QPolygonF(
                [
                    QPointF(0, 0),
                    QPointF(top_rect.width(), 0),
                    QPointF(top_rect.width(), top_rect.height()),
                    QPointF(0, top_rect.height()),
                ]
            ),
            quad,
            transform,
        ):
            # 원근: 눌린 쪽은 카메라에서 멀어져 짧아지고, 전체는 깊이만큼 살짝 작아진다.
            painter.setTransform(transform, True)
        else:
            painter.translate(top_rect.topLeft())
        painter.drawPixmap(QPointF(0, 0), pixmap)
        local = QRectF(0, 0, top_rect.width(), top_rect.height())
        top_path = _rounded(local, metrics.top_radius)
        if led_level > 0.01 and material.transmission > 0.0:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            painter.fillPath(
                top_path, _with_alpha(led_color, led_level * 0.3 * material.transmission)
            )
            painter.restore()
        if key["mode"] == "toggle":
            self._paint_toggle_state(painter, key, local, metrics, bool(key["active"]), led_color)
        if state.hover and enabled:
            painter.fillPath(top_path, QColor(255, 255, 255, 14))
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(top_path)
        if press > 0.02:
            # 눌린 키는 이웃 키보다 낮아져 윗가장자리가 그늘지고(차폐광) 전체 조명도 줄어든다.
            occlusion = QLinearGradient(local.topLeft(), local.bottomLeft())
            occlusion.setColorAt(0.0, QColor(0, 0, 0, int(95 * press)))
            occlusion.setColorAt(0.22, QColor(0, 0, 0, int(30 * press)))
            occlusion.setColorAt(1.0, QColor(0, 0, 0, int(22 * press)))
            painter.fillPath(top_path, occlusion)
            painter.setPen(QPen(QColor(0, 0, 0, int(70 * press)), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(top_path)
        painter.restore()
        if not enabled:
            veil = _rounded(metrics.base, metrics.radius)
            painter.fillPath(veil, QColor(18, 20, 26, 118))

    def _paint_toggle_state(
        self,
        painter: QPainter,
        key: dict,
        local: QRectF,
        metrics: CapMetrics,
        on: bool,
        color: str,
    ) -> None:
        """Make toggle keys read as switches: an on/off indicator plus a tint while on."""
        style = key.get("indicator", "switch")
        if style == "none":
            return
        unit = self.geometry.unit
        accent = QColor(color)
        if not accent.isValid():
            accent = QColor("#5ab8ff")
        cap = QColor(key["cap"]["color"])
        if abs(accent.lightness() - cap.lightness()) < 70:
            # 밝은 키캡 위의 옅은 불빛처럼 대비가 약하면 켜짐 색을 진하게/밝게 보정한다.
            accent = accent.darker(170) if cap.lightness() > 128 else accent.lighter(170)
        painter.save()
        if on:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            painter.fillPath(_rounded(local, metrics.top_radius), _with_alpha(accent, 0.14))
            painter.restore()
        inset = max(3.0, unit * 0.075, metrics.rim + 2.0)
        # 모서리 글자 배치는 왼쪽 위를 쓰므로 표시를 오른쪽 아래로 옮긴다.
        corner = key["legend"]["layout"] == "corner"
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if style == "switch":
            width = _clamp(unit * 0.25, 11.0, 28.0)
            height = width * 0.54
            left = local.right() - inset - width if corner else local.left() + inset
            top = local.bottom() - inset - height if corner else local.top() + inset
            track = QRectF(left, top, width, height)
            path = _rounded(track, height / 2.0)
            if on:
                painter.setPen(QPen(_with_alpha(accent, 0.38), 3.0))
                painter.drawPath(path)
                painter.fillPath(path, accent)
            else:
                painter.fillPath(path, QColor(0, 0, 0, 130))
                painter.setPen(QPen(QColor(255, 255, 255, 110), 1.0))
                painter.drawPath(path)
            pad = height * 0.17
            knob_d = height - 2 * pad
            knob_x = track.right() - pad - knob_d if on else track.left() + pad
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255) if on else QColor(196, 202, 214))
            painter.drawEllipse(QRectF(knob_x, track.top() + pad, knob_d, knob_d))
        elif style == "bar":
            width = local.width() * 0.44
            height = _clamp(unit * 0.045, 2.0, 5.0)
            top = local.bottom() - inset * 0.8 - height if corner else local.top() + inset * 0.8
            bar = QRectF(local.center().x() - width / 2.0, top, width, height)
            if on:
                for spread, alpha in ((6.0, 0.14), (3.0, 0.3)):
                    painter.fillPath(
                        _rounded(
                            bar.adjusted(-spread, -spread, spread, spread), height / 2 + spread
                        ),
                        _with_alpha(accent, alpha),
                    )
                painter.fillPath(_rounded(bar, height / 2.0), accent.lighter(118))
            else:
                painter.fillPath(_rounded(bar, height / 2.0), QColor(0, 0, 0, 110))
                painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
                painter.drawPath(_rounded(bar, height / 2.0))
        elif style == "dot":
            radius = _clamp(unit * 0.05, 2.6, 6.0)
            cx = local.right() - inset - radius if corner else local.left() + inset + radius
            cy = local.bottom() - inset - radius if corner else local.top() + inset + radius
            center = QPointF(cx, cy)
            if on:
                halo = QRadialGradient(center, radius * 3.2)
                halo.setColorAt(0.0, _with_alpha(accent, 0.55))
                halo.setColorAt(1.0, _with_alpha(accent, 0.0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                painter.drawEllipse(center, radius * 3.2, radius * 3.2)
                painter.setBrush(accent)
                painter.drawEllipse(center, radius, radius)
                painter.setBrush(QColor(255, 255, 255, 220))
                painter.drawEllipse(center, radius * 0.42, radius * 0.42)
            else:
                painter.setPen(QPen(QColor(255, 255, 255, 120), 1.0))
                painter.setBrush(QColor(0, 0, 0, 110))
                painter.drawEllipse(center, radius, radius)
        elif style == "ring":
            edge = local.adjusted(1.5, 1.5, -1.5, -1.5)
            path = _rounded(edge, max(1.0, metrics.top_radius - 1.5))
            if on:
                painter.setPen(QPen(_with_alpha(accent, 0.35), 5.0))
                painter.drawPath(path)
                painter.setPen(QPen(accent.lighter(115), 2.2))
                painter.drawPath(path)
            else:
                painter.setPen(QPen(QColor(255, 255, 255, 80), 1.2, Qt.PenStyle.DashLine))
                painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _top_quad(
        rect: QRectF, tilt_x: float, tilt_y: float, press: float, travel_px: float
    ) -> QPolygonF | None:
        """Projected outline of a pressed/tilted cap top (None = draw flat)."""
        if abs(tilt_x) < 0.01 and abs(tilt_y) < 0.01 and press < 0.02:
            return None
        center = rect.center()
        shrink = 1.0 - 0.024 * press
        half_w = rect.width() / 2.0 * shrink
        half_h = rect.height() / 2.0 * shrink
        k = 0.06
        top_w = half_w * (1.0 + k * tilt_y)
        bottom_w = half_w * (1.0 - k * tilt_y)
        left_h = half_h * (1.0 + k * tilt_x)
        right_h = half_h * (1.0 - k * tilt_x)
        corners = []
        for sx, sy, x_extent, y_extent in (
            (-1, -1, top_w, left_h),
            (1, -1, top_w, right_h),
            (1, 1, bottom_w, right_h),
            (-1, 1, bottom_w, left_h),
        ):
            # 기울어져 내려간 모서리는 화면에서도 아래로(앞쪽 시점) 더 내려간다.
            sink = (tilt_x * sx + tilt_y * sy) / 2.0 * travel_px * 0.55
            corners.append(QPointF(center.x() + sx * x_extent, center.y() + sy * y_extent + sink))
        return QPolygonF(corners)

    # -- previews -------------------------------------------------------------

    def render_pixmap(
        self,
        states: dict[str, KeyVisualState] | None = None,
        dpr: float = 1.0,
        header_hover: str = "",
    ) -> QPixmap:
        geometry = self.geometry
        size = QSize(1, 1) if geometry is None else geometry.size()
        pixmap = QPixmap(
            max(1, int(math.ceil(size.width() * dpr))), max(1, int(math.ceil(size.height() * dpr)))
        )
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, states, dpr=dpr, header_hover=header_hover)
        painter.end()
        return pixmap

    def insert_window(self, key: dict) -> QRectF:
        """Insert-art window of a key at rest, in canvas coordinates."""
        metrics = self.geometry.cap_metrics(key)
        return metrics.top.adjusted(metrics.rim, metrics.rim, -metrics.rim, -metrics.rim)

    # -- background -----------------------------------------------------------

    def _background_pixmap(self, dpr: float, brightness: float) -> QPixmap:
        geometry = self.geometry
        cache_key = (self._revision, round(dpr, 2), round(brightness, 3))
        if self._background is not None and self._background_key == cache_key:
            return self._background
        pixmap = QPixmap(
            max(1, int(math.ceil(geometry.width * dpr))),
            max(1, int(math.ceil(geometry.height * dpr))),
        )
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if not geometry.floating:
            self._paint_case(painter)
            self._paint_plate(painter)
            for key in geometry.keys:
                self._paint_switch(painter, key)
        for key in geometry.keys:
            if key["enabled"] and key["led"]["mode"] == "static" and brightness > 0.01:
                material = _material(key)
                self._paint_glow(
                    painter,
                    geometry.key_rect(key),
                    key["led"]["color"],
                    brightness * 0.85 * material.edge_glow,
                )
        if geometry.header:
            self._paint_header_static(painter)
        painter.end()
        self._background = pixmap
        self._background_key = cache_key
        return pixmap

    def _case_color(self) -> QColor:
        return QColor(self.deck["case"]["color"])

    def _header_ink(self) -> QColor:
        if self.geometry.floating:
            return QColor(255, 255, 255, 190)
        base = self._case_color()
        if self.geometry.case_style == "acrylic":
            return QColor(40, 46, 60, 170)
        return QColor(255, 255, 255, 132) if base.lightness() < 140 else QColor(24, 28, 36, 150)

    def _paint_case(self, painter: QPainter) -> None:
        geometry = self.geometry
        scale = geometry.scale
        rect = geometry.case_rect
        radius = geometry.case_radius
        # 흐린 그림자: 여러 겹의 반투명 라운드 사각형으로 블러를 근사한다 (캐시되므로 1회 비용).
        painter.setPen(Qt.PenStyle.NoPen)
        layers = max(4, int(10 * scale))
        for index in range(layers):
            spread = index * 1.1
            alpha = 16 * (1.0 - index / layers) ** 1.6
            painter.setBrush(QColor(0, 0, 0, int(alpha)))
            painter.drawRoundedRect(
                rect.adjusted(-spread, -spread + 3 * scale, spread, spread + 5 * scale),
                radius + spread,
                radius + spread,
            )
        style = geometry.case_style
        base = self._case_color()
        path = _rounded(rect, radius)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if style == "acrylic":
            gradient.setColorAt(0.0, _with_alpha(base.lighter(112), 0.72))
            gradient.setColorAt(1.0, _with_alpha(base.darker(108), 0.6))
        elif style == "walnut":
            gradient.setColorAt(0.0, base.lighter(118))
            gradient.setColorAt(0.5, base)
            gradient.setColorAt(1.0, base.darker(135))
        elif style == "silver":
            gradient.setColorAt(0.0, base.lighter(110))
            gradient.setColorAt(1.0, base.darker(112))
        else:
            gradient.setColorAt(0.0, base.lighter(128))
            gradient.setColorAt(0.45, base)
            gradient.setColorAt(1.0, base.darker(130))
        painter.fillPath(path, gradient)
        painter.save()
        painter.setClipPath(path)
        rng = random.Random(int(rect.width()) * 131 + int(rect.height()))
        if style == "silver":
            for _ in range(int(rect.height() / max(1.0, 1.6 * scale))):
                y = rng.uniform(rect.top(), rect.bottom())
                shade = rng.choice((QColor(255, 255, 255), QColor(0, 0, 0)))
                painter.setPen(QPen(_with_alpha(shade, rng.uniform(0.02, 0.06)), 1.0))
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        elif style == "walnut":
            grain = base.darker(160)
            for _ in range(int(rect.height() / max(1.0, 3.2 * scale))):
                y = rng.uniform(rect.top(), rect.bottom())
                amplitude = rng.uniform(1.0, 4.0) * scale
                period = rng.uniform(60.0, 180.0) * scale
                phase = rng.uniform(0, math.tau)
                wave = QPainterPath(QPointF(rect.left(), y))
                steps = 24
                for step in range(1, steps + 1):
                    x = rect.left() + rect.width() * step / steps
                    wave.lineTo(x, y + amplitude * math.sin(phase + x / period * math.tau))
                painter.setPen(QPen(_with_alpha(grain, rng.uniform(0.08, 0.2)), 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(wave)
        elif style == "acrylic":
            for inset, alpha in ((3.0, 0.22), (6.0, 0.12)):
                painter.setPen(QPen(QColor(255, 255, 255, int(255 * alpha)), 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                inner = rect.adjusted(inset * scale, inset * scale, -inset * scale, -inset * scale)
                painter.drawRoundedRect(inner, radius - inset * scale, radius - inset * scale)
        gloss = QLinearGradient(
            rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.45)
        )
        gloss.setColorAt(0.0, QColor(255, 255, 255, 34 if style != "acrylic" else 60))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, gloss)
        painter.restore()
        chamfer = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        chamfer.setColorAt(0.0, QColor(255, 255, 255, 110 if style != "walnut" else 70))
        chamfer.setColorAt(0.12, QColor(255, 255, 255, 18))
        chamfer.setColorAt(1.0, QColor(0, 0, 0, 40))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(chamfer, 1.2))
        painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), radius - 0.6, radius - 0.6)
        painter.setPen(QPen(QColor(0, 0, 0, 120 if style != "acrylic" else 50), 1.0))
        painter.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)

    def _plate_color(self) -> QColor:
        style = self.geometry.case_style
        base = self._case_color()
        if style == "silver":
            return QColor("#2a2e35")
        if style == "acrylic":
            return QColor(18, 22, 30, 200)
        if style == "walnut":
            return QColor("#1f2126")
        return base.darker(190)

    def _paint_plate(self, painter: QPainter) -> None:
        geometry = self.geometry
        scale = geometry.scale
        rect = geometry.plate_rect
        radius = max(3.0, geometry.case_radius - geometry.bezel * 0.55)
        path = _rounded(rect, radius)
        plate = self._plate_color()
        painter.fillPath(path, plate)
        painter.save()
        painter.setClipPath(path)
        inner = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 10 * scale))
        inner.setColorAt(0.0, QColor(0, 0, 0, 120))
        inner.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, inner)
        dots = _with_alpha(QColor(255, 255, 255), 0.035)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dots)
        step = max(6.0, geometry.unit * 0.25)
        y = rect.top() + step / 2
        while y < rect.bottom():
            x = rect.left() + step / 2
            while x < rect.right():
                painter.drawEllipse(QPointF(x, y), 0.7 * scale, 0.7 * scale)
                x += step
            y += step
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        painter.drawLine(
            QPointF(rect.left() + radius, rect.bottom() + 0.5),
            QPointF(rect.right() - radius, rect.bottom() + 0.5),
        )
        painter.setPen(QPen(QColor(0, 0, 0, 150), 1.0))
        painter.drawRoundedRect(rect, radius, radius)

    def _paint_switch(self, painter: QPainter, key: dict) -> None:
        geometry = self.geometry
        rect = geometry.key_rect(key)
        unit = geometry.unit
        size = unit * 0.58
        center = rect.center()
        stem = QColor(switch_profile(key["switch"]).stem_color)
        painter.setPen(Qt.PenStyle.NoPen)
        if key["w"] >= 2.0 or key["h"] >= 2.0:
            horizontal = key["w"] >= key["h"]
            reach = (rect.width() if horizontal else rect.height()) / 2 - unit * 0.42
            wire = QPen(QColor(170, 176, 186, 150), max(1.0, unit * 0.025))
            painter.setPen(wire)
            first = (
                QPointF(center.x() - reach, center.y())
                if horizontal
                else QPointF(center.x(), center.y() - reach)
            )
            second = (
                QPointF(center.x() + reach, center.y())
                if horizontal
                else QPointF(center.x(), center.y() + reach)
            )
            painter.drawLine(first, second)
            painter.setPen(Qt.PenStyle.NoPen)
            for anchor in (first, second):
                stab = QRectF(
                    anchor.x() - unit * 0.1, anchor.y() - unit * 0.16, unit * 0.2, unit * 0.32
                )
                painter.setBrush(QColor(28, 31, 38))
                painter.drawRoundedRect(stab, unit * 0.04, unit * 0.04)
        housing = QRectF(center.x() - size / 2, center.y() - size / 2, size, size)
        body = QLinearGradient(housing.topLeft(), housing.bottomLeft())
        body.setColorAt(0.0, QColor(58, 63, 73))
        body.setColorAt(1.0, QColor(26, 29, 35))
        painter.setBrush(body)
        painter.drawRoundedRect(housing, unit * 0.06, unit * 0.06)
        painter.setBrush(QColor(255, 255, 255, 14))
        painter.drawRoundedRect(
            housing.adjusted(size * 0.12, size * 0.12, -size * 0.12, -size * 0.12),
            unit * 0.04,
            unit * 0.04,
        )
        lens = QRectF(
            center.x() - size * 0.13, housing.top() + size * 0.06, size * 0.26, size * 0.11
        )
        painter.setBrush(QColor(8, 9, 12, 220))
        painter.drawRoundedRect(lens, size * 0.03, size * 0.03)
        arm = size * 0.36
        thick = max(1.2, size * 0.11)
        painter.setBrush(stem)
        painter.drawRoundedRect(
            QRectF(center.x() - arm / 2, center.y() - thick / 2, arm, thick),
            thick * 0.3,
            thick * 0.3,
        )
        painter.drawRoundedRect(
            QRectF(center.x() - thick / 2, center.y() - arm / 2, thick, arm),
            thick * 0.3,
            thick * 0.3,
        )

    def _paint_header_static(self, painter: QPainter) -> None:
        geometry = self.geometry
        deck = self.deck
        ink = self._header_ink()
        name = deck.get("name") or str(t("widget.launcher.title", "KEYDECK"))
        page_name = deck["pages"][geometry.page_index]["name"]
        font = legend_font(geometry.header_h * 0.46, "bold")
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1 * geometry.scale)
        metrics = QFontMetricsF(font)
        title = name.upper() if name.isascii() else name
        title_w = metrics.horizontalAdvance(title)
        emboss = QColor(0, 0, 0, 90) if ink.lightness() > 128 else QColor(255, 255, 255, 80)
        rect = geometry.title_rect
        left_middle = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        fill_text(painter, rect.translated(0, 1), left_middle, title, font, emboss)
        fill_text(painter, rect, left_middle, title, font, ink)
        if geometry.page_count > 1 and page_name:
            sub_font = legend_font(geometry.header_h * 0.42, "medium")
            sub_rect = rect.adjusted(title_w + 8 * geometry.scale, 0, 0, 0)
            available = max(
                0.0,
                (geometry.dot_rects[0].left() if geometry.dot_rects else rect.right())
                - sub_rect.left()
                - 6,
            )
            text = QFontMetricsF(sub_font).elidedText(
                f"· {page_name}", Qt.TextElideMode.ElideRight, available
            )
            fill_text(
                painter,
                sub_rect,
                left_middle,
                text,
                sub_font,
                _with_alpha(ink, ink.alphaF() * 0.75),
            )
        accent = QColor(deck["case"]["accent"])
        painter.setPen(Qt.PenStyle.NoPen)
        for index, dot in enumerate(geometry.dot_rects):
            painter.setBrush(accent if index == geometry.page_index else _with_alpha(ink, 0.32))
            painter.drawRoundedRect(dot, dot.height() / 2, dot.height() / 2)

    def _paint_header_controls(self, painter: QPainter, hover: str, dpr: float) -> None:
        geometry = self.geometry
        rect = geometry.gear_rect
        ink = self._header_ink()
        accent = QColor(self.deck["case"]["accent"])
        if hover == "gear":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_with_alpha(accent, 0.22))
            painter.drawEllipse(rect)
        color = accent if hover == "gear" else ink
        glyph = glyph_pixmap("settings", color.name(), int(rect.width() * 0.72), dpr)
        if glyph is not None:
            size = rect.width() * 0.72
            painter.drawPixmap(
                QRectF(
                    rect.center().x() - size / 2, rect.center().y() - size / 2, size, size
                ).toRect(),
                glyph,
            )

    def _paint_close_control(self, painter: QPainter, hovered: bool, dpr: float) -> None:
        geometry = self.geometry
        rect = geometry.close_rect
        danger = QColor(ERROR_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        if geometry.header:
            if hovered:
                painter.setBrush(_with_alpha(danger, 0.9))
                painter.drawEllipse(rect)
            color = QColor("#ffffff") if hovered else self._header_ink()
        else:
            # 헤더 없는 덱의 모서리 배지: 어떤 배경 위에서도 보이도록 어두운 원 + 흰 테두리.
            painter.setBrush(danger if hovered else QColor(24, 27, 34, 235))
            painter.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
            painter.drawEllipse(rect.adjusted(0.6, 0.6, -0.6, -0.6))
            painter.setPen(Qt.PenStyle.NoPen)
            color = QColor("#ffffff")
        size = rect.width() * (0.62 if geometry.header else 0.58)
        glyph = glyph_pixmap("close", color.name(), int(size), dpr)
        if glyph is not None:
            painter.drawPixmap(
                QRectF(
                    rect.center().x() - size / 2, rect.center().y() - size / 2, size, size
                ).toRect(),
                glyph,
            )

    # -- per-key layers ---------------------------------------------------------

    def _paint_glow(self, painter: QPainter, rect: QRectF, color: str, level: float) -> None:
        if level <= 0.005:
            return
        unit = self.geometry.unit
        rx = rect.width() / 2 + unit * 0.34
        ry = rect.height() / 2 + unit * 0.34
        center = rect.center()
        gradient = QRadialGradient(QPointF(0, 0), 1.0)
        gradient.setColorAt(0.0, _with_alpha(color, 0.8 * level))
        gradient.setColorAt(0.55, _with_alpha(color, 0.38 * level))
        gradient.setColorAt(1.0, _with_alpha(color, 0.0))
        painter.save()
        painter.translate(center)
        painter.scale(rx, ry)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(0, 0), 1.0, 1.0)
        painter.restore()

    def _shadow_sprite(self, width: float, height: float, radius: float, blur: float) -> QPixmap:
        cache_key = (round(width), round(height), round(radius), round(blur))
        cached = self._shadows.get(cache_key)
        if cached is not None:
            return cached
        pad = int(math.ceil(blur * 2))
        pixmap = QPixmap(int(width) + pad * 2, int(height) + pad * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        steps = max(3, int(blur))
        for index in range(steps, -1, -1):
            spread = blur * index / steps
            painter.setBrush(QColor(0, 0, 0, int(22 + 38 * (1 - index / steps))))
            painter.drawRoundedRect(
                QRectF(pad - spread, pad - spread, width + spread * 2, height + spread * 2),
                radius + spread,
                radius + spread,
            )
        painter.end()
        self._shadows.put(cache_key, pixmap)
        return pixmap

    def _paint_shadow(
        self, painter: QPainter, key: dict, metrics: CapMetrics, travel: float
    ) -> None:
        geometry = self.geometry
        base = metrics.base
        floating = geometry.floating
        depth = 1.0 - _clamp(travel, 0.0, 1.0) * 0.75
        blur = geometry.unit * (0.12 if floating else 0.06)
        sprite = self._shadow_sprite(base.width(), base.height(), metrics.radius, blur)
        pad = (sprite.width() - int(base.width())) / 2
        drop = geometry.unit * (0.09 if floating else 0.035) * depth
        painter.save()
        painter.setOpacity((0.55 if floating else 0.75) * (0.5 + 0.5 * depth))
        painter.drawPixmap(QPointF(base.left() - pad, base.top() - pad + drop), sprite)
        # 접촉 그림자: 캡이 플레이트에 가까워질수록 가장자리 그림자가 좁고 진해진다.
        press = _clamp(travel, 0.0, 1.0)
        if press > 0.01:
            contact = self._shadow_sprite(
                base.width(), base.height(), metrics.radius, max(1.0, geometry.unit * 0.02)
            )
            contact_pad = (contact.width() - int(base.width())) / 2
            painter.setOpacity(0.25 + 0.55 * press)
            painter.drawPixmap(
                QPointF(
                    base.left() - contact_pad, base.top() - contact_pad + geometry.unit * 0.006
                ),
                contact,
            )
        painter.restore()

    def _paint_skirt(
        self,
        painter: QPainter,
        key: dict,
        metrics: CapMetrics,
        travel: float,
        material: MaterialSpec,
    ) -> None:
        base = metrics.base
        cap = QColor(key["cap"]["color"])
        path = _rounded(base, metrics.radius)
        alpha = material.skirt_alpha
        gradient = QLinearGradient(base.topLeft(), base.bottomLeft())
        if key["cap"]["material"] == "smoke":
            cap = _mix(cap, QColor(8, 10, 14), 0.45)
        light = cap.lightness() > 150
        gradient.setColorAt(0.0, _with_alpha(cap.darker(104 if light else 96), alpha))
        gradient.setColorAt(0.7, _with_alpha(cap.darker(118 if light else 112), alpha))
        gradient.setColorAt(
            1.0, _with_alpha(cap.darker(150 if light else 150), min(1.0, alpha + 0.1))
        )
        painter.fillPath(path, gradient)
        top_now = metrics.top.translated(0, travel * metrics.travel_px)
        front = QRectF(
            base.left(),
            top_now.bottom() - metrics.top_radius,
            base.width(),
            base.bottom() - top_now.bottom() + metrics.top_radius,
        )
        if front.height() > 1:
            painter.save()
            painter.setClipPath(path)
            wall = QLinearGradient(front.topLeft(), front.bottomLeft())
            wall.setColorAt(0.0, QColor(255, 255, 255, 34 if material.clear_rim or light else 22))
            wall.setColorAt(1.0, QColor(0, 0, 0, 46))
            painter.fillRect(front, wall)
            painter.restore()
        if material.transmission > 0.5:
            edge = QPen(QColor(255, 255, 255, int(90 * material.transmission)), 1.0)
        else:
            edge = QPen(_with_alpha(cap.darker(190), 0.7), 1.0)
        if travel > 0.02:
            # 옆면이 플레이트 우물 속으로 들어가며 빛을 덜 받는다.
            painter.fillPath(path, QColor(0, 0, 0, int(42 * _clamp(travel, 0.0, 1.0))))
        painter.setPen(edge)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(_rounded(base.adjusted(0.5, 0.5, -0.5, -0.5), metrics.radius))

    def _top_signature(
        self, key: dict, metrics: CapMetrics, dpr: float, state: KeyVisualState
    ) -> tuple:
        memo = self._signatures.get(key["id"])
        if memo is None:
            insert = key["insert"]
            parts: list = [
                json.dumps(
                    [
                        key["label"],
                        key["sublabel"],
                        key["enabled"],
                        insert,
                        key["legend"],
                        key["cap"],
                        key["action"],
                    ],
                    sort_keys=True,
                    ensure_ascii=False,
                )
            ]
            if insert["kind"] == "image":
                parts.append(file_stamp(insert["path"]))
            if insert["kind"] == "panorama":
                panorama = self.deck["panorama"]
                parts.extend((json.dumps(panorama, sort_keys=True), file_stamp(panorama["path"])))
            if key["action"]["type"] == "app" and key["legend"]["glyph"] == "auto":
                parts.append(file_stamp(key["action"]["target"]))
            memo = tuple(parts)
            self._signatures[key["id"]] = memo
        extra: tuple = (
            round(metrics.top.width(), 1),
            round(metrics.top.height(), 1),
            round(dpr, 2),
            round(self.geometry.unit, 2),
            state.frame_no,
        )
        if key["insert"]["kind"] == "panorama":
            window = metrics.top.adjusted(metrics.rim, metrics.rim, -metrics.rim, -metrics.rim)
            area = self.geometry.content_rect
            extra += (
                round(window.left() - area.left(), 1),
                round(window.top() - area.top(), 1),
                round(area.width(), 1),
                round(area.height(), 1),
            )
        return memo + extra

    def _top_pixmap(
        self, key: dict, metrics: CapMetrics, dpr: float, state: KeyVisualState
    ) -> QPixmap:
        signature = self._top_signature(key, metrics, dpr, state)
        cached = self._tops.get(key["id"])
        if cached is not None and cached[0] == signature:
            return cached[1]
        pixmap = self._render_top(key, metrics, dpr, state)
        self._tops[key["id"]] = (signature, pixmap)
        return pixmap

    def _render_top(
        self, key: dict, metrics: CapMetrics, dpr: float, state: KeyVisualState
    ) -> QPixmap:
        geometry = self.geometry
        width = metrics.top.width()
        height = metrics.top.height()
        pixmap = QPixmap(max(1, int(math.ceil(width * dpr))), max(1, int(math.ceil(height * dpr))))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(0, 0, width, height)
        radius = metrics.top_radius
        path = _rounded(rect, radius)
        material = _material(key)
        cap = QColor(key["cap"]["color"])
        body = QColor(cap)
        if key["cap"]["material"] == "smoke":
            body = _mix(cap, QColor(8, 10, 14), 0.5)
        elif key["cap"]["material"] == "frosted":
            body = _mix(cap, QColor(255, 255, 255), 0.3)
        painter.fillPath(path, _with_alpha(body, material.body_alpha))
        rim = metrics.rim
        window = rect.adjusted(rim, rim, -rim, -rim)
        window_radius = max(1.5, radius - rim * 0.7)
        window_path = _rounded(window, window_radius)
        insert_kind = key["insert"]["kind"]
        if rim > 0:
            rim_light = QLinearGradient(rect.topLeft(), rect.bottomRight())
            rim_light.setColorAt(0.0, QColor(255, 255, 255, 26))
            rim_light.setColorAt(0.5, QColor(255, 255, 255, 4))
            rim_light.setColorAt(1.0, QColor(255, 255, 255, 14))
            ring = QPainterPath(path)
            ring = ring.subtracted(window_path)
            painter.fillPath(ring, rim_light)
        painter.save()
        painter.setClipPath(window_path if rim > 0 else path)
        panorama_window = QRectF(window)
        panorama_window.translate(metrics.top.topLeft())
        self._paint_insert(painter, key, window if rim > 0 else rect, state, panorama_window, dpr)
        # 반투명 재질의 확산/스모크는 인서트만 흐리게 하고 레전드는 그 위에 선명하게 둔다.
        if material.diffusion:
            painter.fillRect(rect, QColor(255, 255, 255, int(255 * material.diffusion)))
        if material.smoke:
            painter.fillRect(rect, QColor(6, 8, 12, int(255 * material.smoke)))
        self._paint_legend(painter, key, window if rim > 0 else rect, dpr)
        painter.restore()
        if rim > 0 and insert_kind != "none":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 70), 1.0))
            painter.drawPath(window_path)
            painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
            painter.drawPath(_rounded(window.adjusted(-1, -1, 1, 1), window_radius + 1))
        self._paint_glass(painter, key, rect, radius, material)
        painter.end()
        del geometry
        return pixmap

    def _paint_insert(
        self,
        painter: QPainter,
        key: dict,
        window: QRectF,
        state: KeyVisualState,
        canvas_window: QRectF,
        dpr: float,
    ) -> None:
        insert = key["insert"]
        kind = insert["kind"]
        if kind == "none":
            return
        painter.save()
        painter.setOpacity(insert["opacity"] / 100.0)
        first = QColor(insert["color"])
        second = QColor(insert["color2"])
        if kind == "color":
            painter.fillRect(window, first)
        elif kind in {"gradient", "pattern"}:
            gradient = QLinearGradient(window.topLeft(), window.bottomRight())
            gradient.setColorAt(0.0, first)
            gradient.setColorAt(1.0, second)
            painter.fillRect(window, gradient)
            if kind == "pattern":
                tint = QColor(key["legend"]["color"]).name()
                side = max(window.width(), window.height())
                image = pattern_image(insert["pattern"], tint, int(math.ceil(side * dpr)))
                if image is not None:
                    painter.setOpacity(insert["opacity"] / 100.0 * 0.5)
                    target = QRectF(
                        window.center().x() - side / 2, window.center().y() - side / 2, side, side
                    )
                    painter.drawImage(target, image)
        elif kind == "image":
            image = state.frame if state.frame is not None else source_image(insert["path"])
            if image is not None and not image.isNull():
                self._draw_fitted(painter, image, window, insert)
            else:
                self._paint_missing(painter, window, first, second, dpr)
        elif kind == "panorama":
            image = panorama_image(self.deck["panorama"]["path"])
            if image is not None:
                mapped = self._panorama_source(image, canvas_window)
                if mapped is not None:
                    # canvas 좌표의 보이는 조각을 이 키 윗면(로컬 좌표)으로 옮긴다.
                    target, source = mapped
                    target.translate(window.topLeft() - canvas_window.topLeft())
                    painter.drawImage(target, image, source)
            else:
                self._paint_missing(painter, window, first, second, dpr)
        painter.restore()

    def _paint_missing(
        self, painter: QPainter, window: QRectF, first: QColor, second: QColor, dpr: float
    ) -> None:
        gradient = QLinearGradient(window.topLeft(), window.bottomRight())
        gradient.setColorAt(0.0, first)
        gradient.setColorAt(1.0, second)
        painter.fillRect(window, gradient)
        size = min(window.width(), window.height()) * 0.34
        glyph = glyph_pixmap("image", "#ffffff", int(size), dpr)
        if glyph is not None:
            painter.setOpacity(0.45)
            painter.drawPixmap(
                QRectF(
                    window.center().x() - size / 2, window.center().y() - size / 2, size, size
                ).toRect(),
                glyph,
            )

    @staticmethod
    def _draw_fitted(painter: QPainter, image: QImage, window: QRectF, insert: dict) -> None:
        source_w = max(1, image.width())
        source_h = max(1, image.height())
        rotate = int(insert["rotate"])
        rotated = rotate in (90, 270)
        view_w = source_h if rotated else source_w
        view_h = source_w if rotated else source_h
        zoom = insert["zoom"] / 100.0
        fit = insert["fit"]
        if fit == "stretch":
            scale_x = (window.height() if rotated else window.width()) / source_w
            scale_y = (window.width() if rotated else window.height()) / source_h
        else:
            factor = (max if fit == "cover" else min)(
                window.width() / view_w, window.height() / view_h
            )
            scale_x = scale_y = factor
        painter.save()
        painter.translate(
            window.center().x() + insert["ox"] / 100.0 * window.width(),
            window.center().y() + insert["oy"] / 100.0 * window.height(),
        )
        painter.rotate(rotate)
        painter.scale(scale_x * zoom, scale_y * zoom)
        painter.drawImage(QPointF(-source_w / 2.0, -source_h / 2.0), image)
        painter.restore()

    def panorama_rect(self, image_size: tuple[int, int]) -> QRectF:
        """Canvas rect the deck panorama covers on the current page."""
        area = self.geometry.content_rect
        left, top, width, height = panorama_rect(
            (area.left(), area.top(), area.width(), area.height()),
            image_size,
            self.deck["panorama"],
        )
        return QRectF(left, top, width, height)

    def _panorama_source(self, image: QImage, window: QRectF) -> tuple[QRectF, QRectF] | None:
        """(canvas target, image source) of the panorama slice visible in ``window``.

        In ``contain`` mode a window may be partly or wholly outside the picture; only the
        overlapping part is drawn so the keycap shows through elsewhere.
        """
        placed = self.panorama_rect((image.width(), image.height()))
        visible = window.intersected(placed)
        if visible.width() <= 0.01 or visible.height() <= 0.01:
            return None
        scale = placed.width() / max(1, image.width())
        source = QRectF(
            (visible.left() - placed.left()) / scale,
            (visible.top() - placed.top()) / scale,
            visible.width() / scale,
            visible.height() / scale,
        )
        return visible, source

    def _resolve_glyph(self, key: dict, size: float, color: str, dpr: float) -> QPixmap | None:
        glyph = key["legend"]["glyph"]
        action = key["action"]
        if glyph == "none":
            return None
        if glyph == "auto":
            if action["type"] == "app" and action["target"]:
                icon = file_icon_pixmap(action["target"], int(size), dpr)
                if icon is not None:
                    return icon
            glyph = auto_glyph(action)
            if glyph == "none":
                return None
        return glyph_pixmap(glyph, color, int(size), dpr)

    def _paint_legend(self, painter: QPainter, key: dict, area: QRectF, dpr: float) -> None:
        legend = key["legend"]
        layout = legend["layout"]
        if layout == "art":
            return
        unit = self.geometry.unit
        scale = legend["size"] / 100.0
        color = QColor(legend["color"])
        glyph_color = legend["glyph_color"] or legend["color"]
        weight = legend["weight"]
        shadow = bool(legend["shadow"])
        label = key["label"]
        sublabel = key["sublabel"]
        pad = unit * 0.075
        inner = area.adjusted(pad, pad * 0.8, -pad, -pad * 0.8)
        if inner.width() <= 4 or inner.height() <= 4:
            return
        center_flags = Qt.AlignmentFlag.AlignCenter
        if layout == "stack":
            if sublabel:
                # 보조 레전드(예: Ctrl+C)는 오른쪽 위 한 줄을 차지하고 본 레전드는 그 아래에 배치한다.
                self._draw_corner_sub(painter, inner, sublabel, unit, color, weight)
                inner = inner.adjusted(0, unit * 0.1, 0, 0)
            glyph_size = min(unit * 0.3 * scale, inner.height() * (0.5 if label else 0.8))
            glyph = self._resolve_glyph(key, glyph_size, glyph_color, dpr)
            font = legend_font(unit * 0.15 * scale, weight)
            line_h = QFontMetricsF(font).height()
            spacing = unit * 0.035
            total = (
                (glyph_size if glyph else 0)
                + (line_h if label else 0)
                + (spacing if glyph and label else 0)
            )
            y = inner.center().y() - total / 2
            if glyph is not None:
                self._draw_glyph(
                    painter,
                    glyph,
                    QPointF(inner.center().x(), y + glyph_size / 2),
                    glyph_size,
                    shadow,
                )
                y += glyph_size + spacing
            if label:
                self._draw_label(
                    painter,
                    QRectF(inner.left(), y, inner.width(), line_h),
                    label,
                    font,
                    color,
                    center_flags,
                    shadow,
                    min_scale=0.7,
                )
        elif layout == "caption":
            strip_h = max(unit * 0.25 * min(1.3, scale), 10.0)
            strip = QRectF(area.left(), area.bottom() - strip_h, area.width(), strip_h)
            painter.fillRect(
                strip,
                QColor(0, 0, 0, 120) if color.lightness() > 120 else QColor(255, 255, 255, 160),
            )
            if key["insert"]["kind"] not in {"image", "panorama"}:
                art = QRectF(inner.left(), inner.top(), inner.width(), strip.top() - inner.top())
                glyph_size = min(unit * 0.34 * scale, art.height() * 0.8, art.width() * 0.8)
                glyph = self._resolve_glyph(key, glyph_size, glyph_color, dpr)
                if glyph is not None:
                    self._draw_glyph(painter, glyph, art.center(), glyph_size, shadow)
            if label:
                font = legend_font(min(unit * 0.14 * scale, strip_h * 0.62), weight)
                self._draw_label(
                    painter,
                    strip.adjusted(pad, 0, -pad, 0),
                    label,
                    font,
                    color,
                    center_flags,
                    False,
                    min_scale=0.75,
                )
        elif layout == "corner":
            font = legend_font(unit * 0.145 * scale, weight)
            if label:
                self._draw_label(
                    painter,
                    inner,
                    label,
                    font,
                    color,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    shadow,
                    min_scale=0.7,
                )
            glyph_size = unit * 0.22 * scale
            glyph = self._resolve_glyph(key, glyph_size, glyph_color, dpr)
            if glyph is not None:
                self._draw_glyph(
                    painter,
                    glyph,
                    QPointF(inner.right() - glyph_size / 2, inner.bottom() - glyph_size / 2),
                    glyph_size,
                    shadow,
                )
            if sublabel:
                sub_font = legend_font(unit * 0.11 * scale, "medium")
                self._draw_label(
                    painter,
                    inner,
                    sublabel,
                    sub_font,
                    _with_alpha(color, 0.72),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                    shadow,
                    min_scale=0.8,
                )
        elif layout == "center":
            base_px = unit * 0.21 * scale
            font = legend_font(base_px, weight)
            if label:
                text_rect = inner.adjusted(0, 0, 0, -(unit * 0.12 if sublabel else 0))
                self._draw_label(
                    painter,
                    text_rect,
                    label,
                    font,
                    color,
                    center_flags | Qt.TextFlag.TextWordWrap,
                    shadow,
                    min_scale=0.55,
                    wrap=True,
                )
            if sublabel:
                sub_font = legend_font(unit * 0.11 * scale, "medium")
                sub_rect = QRectF(
                    inner.left(), inner.bottom() - unit * 0.14, inner.width(), unit * 0.14
                )
                self._draw_label(
                    painter,
                    sub_rect,
                    sublabel,
                    sub_font,
                    _with_alpha(color, 0.72),
                    center_flags,
                    shadow,
                    min_scale=0.8,
                )
        elif layout == "glyph":
            glyph_size = min(unit * 0.46 * scale, inner.height() * 0.86, inner.width() * 0.86)
            glyph = self._resolve_glyph(key, glyph_size, glyph_color, dpr)
            if glyph is not None:
                self._draw_glyph(painter, glyph, inner.center(), glyph_size, shadow)
            elif label:
                self._draw_label(
                    painter,
                    inner,
                    label,
                    legend_font(unit * 0.2 * scale, weight),
                    color,
                    center_flags,
                    shadow,
                    min_scale=0.6,
                )
            if sublabel:
                self._draw_corner_sub(painter, inner, sublabel, unit, color, weight)

    def _draw_corner_sub(
        self, painter: QPainter, inner: QRectF, text: str, unit: float, color: QColor, weight: str
    ) -> None:
        font = legend_font(unit * 0.095, "medium")
        metrics = QFontMetricsF(font)
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, inner.width() * 0.7)
        fill_text(
            painter,
            inner,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            elided,
            font,
            _with_alpha(color, 0.62),
        )
        del weight

    @staticmethod
    def _draw_glyph(
        painter: QPainter, glyph: QPixmap, center: QPointF, size: float, shadow: bool
    ) -> None:
        target = QRectF(center.x() - size / 2, center.y() - size / 2, size, size)
        if shadow:
            painter.save()
            painter.setOpacity(painter.opacity() * 0.35)
            painter.drawPixmap(
                target.translated(0, max(1.0, size * 0.04)), glyph, QRectF(glyph.rect())
            )
            painter.restore()
        painter.drawPixmap(target, glyph, QRectF(glyph.rect()))

    @staticmethod
    def _draw_label(
        painter: QPainter,
        rect: QRectF,
        text: str,
        font: QFont,
        color: QColor,
        flags,
        shadow: bool,
        *,
        min_scale: float = 0.7,
        wrap: bool = False,
    ) -> None:
        base_px = font.pixelSize()
        fitted = QFont(font)
        final_text = text
        for step in range(8):
            fitted.setPixelSize(max(6, int(round(base_px * (1.0 - (1.0 - min_scale) * step / 7)))))
            metrics = QFontMetricsF(fitted)
            if wrap:
                bound = metrics.boundingRect(
                    rect, int(flags.value if hasattr(flags, "value") else flags), text
                )
                if bound.height() <= rect.height() + 0.5 and bound.width() <= rect.width() + 0.5:
                    break
            elif metrics.horizontalAdvance(text) <= rect.width():
                break
        else:
            metrics = QFontMetricsF(fitted)
            if not wrap:
                final_text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        if shadow:
            shade = QColor(0, 0, 0, 125) if color.lightness() > 110 else QColor(255, 255, 255, 150)
            offset = max(1.0, fitted.pixelSize() * 0.08)
            fill_text(
                painter, rect.translated(0, offset), flags, final_text, fitted, shade, wrap=wrap
            )
        fill_text(painter, rect, flags, final_text, fitted, color, wrap=wrap)

    def _paint_glass(
        self, painter: QPainter, key: dict, rect: QRectF, radius: float, material: MaterialSpec
    ) -> None:
        path = _rounded(rect, radius)
        dish = _profile(key).dish
        painter.save()
        painter.setClipPath(path)
        if dish == "cylindrical":
            shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            shade.setColorAt(0.0, QColor(0, 0, 0, 52))
            shade.setColorAt(0.2, QColor(0, 0, 0, 10))
            shade.setColorAt(0.6, QColor(255, 255, 255, 0))
            shade.setColorAt(1.0, QColor(255, 255, 255, 34))
            painter.fillRect(rect, shade)
        elif dish in {"spherical", "deep", "round"}:
            # deep(MT3)은 더 깊게 파인 곡면, round는 가운데가 오목한 원형 접시
            depth = {"spherical": 58, "deep": 92, "round": 72}[dish]
            lift = 0.0 if dish == "round" else rect.height() * 0.08
            shade = QRadialGradient(
                QPointF(rect.center().x(), rect.center().y() - lift),
                max(rect.width(), rect.height()) * (0.62 if dish == "round" else 0.72),
            )
            shade.setColorAt(0.0, QColor(255, 255, 255, 26 if dish == "deep" else 20))
            shade.setColorAt(0.58, QColor(255, 255, 255, 0))
            shade.setColorAt(1.0, QColor(0, 0, 0, depth))
            painter.fillRect(rect, shade)
            if dish == "round":
                ring = rect.adjusted(
                    rect.width() * 0.1,
                    rect.height() * 0.1,
                    -rect.width() * 0.1,
                    -rect.height() * 0.1,
                )
                painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(ring, radius * 0.8, radius * 0.8)
        elif dish == "chiclet":
            shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            shade.setColorAt(0.0, QColor(255, 255, 255, 10))
            shade.setColorAt(1.0, QColor(0, 0, 0, 14))
            painter.fillRect(rect, shade)
        else:
            shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            shade.setColorAt(0.0, QColor(255, 255, 255, 18))
            shade.setColorAt(1.0, QColor(0, 0, 0, 26))
            painter.fillRect(rect, shade)
        sheen = QLinearGradient(
            rect.topLeft(),
            QPointF(rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.62),
        )
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(255 * material.sheen)))
        sheen.setColorAt(0.55, QColor(255, 255, 255, int(255 * material.sheen * 0.25)))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        highlight = QPainterPath()
        highlight.addRoundedRect(
            QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.5), radius, radius
        )
        painter.fillPath(highlight, sheen)
        painter.restore()
        edge = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        edge.setColorAt(0.0, QColor(255, 255, 255, int(120 + 90 * material.transmission)))
        edge.setColorAt(0.35, QColor(255, 255, 255, 26))
        edge.setColorAt(1.0, QColor(255, 255, 255, 12))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(edge, 1.0))
        painter.drawPath(_rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), max(1.0, radius - 0.5)))
        painter.setPen(QPen(QColor(0, 0, 0, 60), 0.8))
        painter.drawPath(path)


def render_deck_thumbnail(
    deck: dict, page_index: int | None, width: int, height: int, dpr: float = 1.0
) -> QPixmap:
    """Small static rendering of a deck page scaled to fit width×height."""
    renderer = KeyDeckRenderer()
    scale = fit_scale(deck, page_index, width, height, header=False)
    renderer.set_deck(deck, page_index, scale=scale, header=False)
    rendered = renderer.render_pixmap(dpr=dpr)
    canvas = QPixmap(int(width * dpr), int(height * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    size = renderer.geometry.size()
    painter.drawPixmap(QPointF((width - size.width()) / 2, (height - size.height()) / 2), rendered)
    painter.end()
    return canvas


__all__ = [
    "ERROR_COLOR",
    "IDLE_STATE",
    "MATERIAL_SPECS",
    "PROFILE_SPECS",
    "SUCCESS_COLOR",
    "CapMetrics",
    "DeckGeometry",
    "KeyDeckRenderer",
    "KeyVisualState",
    "fit_scale",
    "legend_font",
    "render_deck_thumbnail",
]
