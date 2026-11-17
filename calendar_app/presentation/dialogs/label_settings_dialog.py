# -*- coding: utf-8 -*-
"""Dialog for customizing priority/status icon glyphs, colours and text labels."""

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain import task_constants
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
    build_settings_dialog_stylesheet,
    build_settings_style_bundle,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_collapsible_section,
    build_dialog_footer,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.theme import task_glyphs

_GLYPH_PICKER_COLUMNS = 8
_COLOR_PICKER_COLUMNS = 8
_GLYPH_ICON_PX = 18
_SWATCH_PX = 14


def _glyph_names() -> dict:
    """Translated names of the selectable glyphs (tooltips, accessible names)."""
    return {
        "circle-exclamation": t("dialog.label_settings.glyphs.circle_exclamation", "느낌표 원"),
        "triangle-exclamation": t(
            "dialog.label_settings.glyphs.triangle_exclamation", "경고 삼각형"
        ),
        "exclamation": t("dialog.label_settings.glyphs.exclamation", "느낌표"),
        "fire-flame-curved": t("dialog.label_settings.glyphs.fire_flame_curved", "불꽃"),
        "fire": t("dialog.label_settings.glyphs.fire", "불"),
        "bolt": t("dialog.label_settings.glyphs.bolt", "번개"),
        "radiation": t("dialog.label_settings.glyphs.radiation", "위험 표시"),
        "skull-crossbones": t("dialog.label_settings.glyphs.skull_crossbones", "해골"),
        "angles-up": t("dialog.label_settings.glyphs.angles_up", "이중 위쪽 화살표"),
        "angle-up": t("dialog.label_settings.glyphs.angle_up", "위쪽 화살표"),
        "arrow-up": t("dialog.label_settings.glyphs.arrow_up", "위로"),
        "circle-arrow-up": t("dialog.label_settings.glyphs.circle_arrow_up", "위쪽 화살표 원"),
        "arrow-trend-up": t("dialog.label_settings.glyphs.arrow_trend_up", "상승 추세"),
        "caret-up": t("dialog.label_settings.glyphs.caret_up", "위쪽 삼각형"),
        "chevron-up": t("dialog.label_settings.glyphs.chevron_up", "위쪽 꺾쇠"),
        "signal": t("dialog.label_settings.glyphs.signal", "신호 막대"),
        "equals": t("dialog.label_settings.glyphs.equals", "등호"),
        "minus": t("dialog.label_settings.glyphs.minus", "빼기"),
        "angle-down": t("dialog.label_settings.glyphs.angle_down", "아래쪽 화살표"),
        "angles-down": t("dialog.label_settings.glyphs.angles_down", "이중 아래쪽 화살표"),
        "arrow-down": t("dialog.label_settings.glyphs.arrow_down", "아래로"),
        "circle-arrow-down": t(
            "dialog.label_settings.glyphs.circle_arrow_down", "아래쪽 화살표 원"
        ),
        "arrow-trend-down": t("dialog.label_settings.glyphs.arrow_trend_down", "하락 추세"),
        "caret-down": t("dialog.label_settings.glyphs.caret_down", "아래쪽 삼각형"),
        "flag": t("dialog.label_settings.glyphs.flag", "깃발"),
        "flag-checkered": t("dialog.label_settings.glyphs.flag_checkered", "체크 깃발"),
        "star": t("dialog.label_settings.glyphs.star", "별"),
        "bookmark": t("dialog.label_settings.glyphs.bookmark", "책갈피"),
        "thumbtack": t("dialog.label_settings.glyphs.thumbtack", "압정"),
        "heart": t("dialog.label_settings.glyphs.heart", "하트"),
        "gem": t("dialog.label_settings.glyphs.gem", "보석"),
        "crown": t("dialog.label_settings.glyphs.crown", "왕관"),
        "trophy": t("dialog.label_settings.glyphs.trophy", "트로피"),
        "medal": t("dialog.label_settings.glyphs.medal", "메달"),
        "rocket": t("dialog.label_settings.glyphs.rocket", "로켓"),
        "bullseye": t("dialog.label_settings.glyphs.bullseye", "과녁"),
        "crosshairs": t("dialog.label_settings.glyphs.crosshairs", "조준선"),
        "lightbulb": t("dialog.label_settings.glyphs.lightbulb", "전구"),
        "gauge-high": t("dialog.label_settings.glyphs.gauge_high", "계기판"),
        "temperature-high": t("dialog.label_settings.glyphs.temperature_high", "온도계"),
        "circle": t("dialog.label_settings.glyphs.circle", "원"),
        "circle-dot": t("dialog.label_settings.glyphs.circle_dot", "점 원"),
        "circle-notch": t("dialog.label_settings.glyphs.circle_notch", "열린 원"),
        "clock": t("dialog.label_settings.glyphs.clock", "시계"),
        "calendar": t("dialog.label_settings.glyphs.calendar", "달력"),
        "calendar-day": t("dialog.label_settings.glyphs.calendar_day", "하루 달력"),
        "hourglass-start": t("dialog.label_settings.glyphs.hourglass_start", "모래시계 시작"),
        "hourglass-half": t("dialog.label_settings.glyphs.hourglass_half", "모래시계"),
        "circle-half-stroke": t("dialog.label_settings.glyphs.circle_half_stroke", "반원"),
        "circle-play": t("dialog.label_settings.glyphs.circle_play", "재생 원"),
        "spinner": t("dialog.label_settings.glyphs.spinner", "진행 표시"),
        "arrows-rotate": t("dialog.label_settings.glyphs.arrows_rotate", "새로 고침"),
        "person-running": t("dialog.label_settings.glyphs.person_running", "달리는 사람"),
        "circle-check": t("dialog.label_settings.glyphs.circle_check", "체크 원"),
        "check": t("dialog.label_settings.glyphs.check", "체크"),
        "square-check": t("dialog.label_settings.glyphs.square_check", "체크 상자"),
        "calendar-check": t("dialog.label_settings.glyphs.calendar_check", "체크 달력"),
        "clipboard-check": t("dialog.label_settings.glyphs.clipboard_check", "체크 클립보드"),
        "list-check": t("dialog.label_settings.glyphs.list_check", "체크 목록"),
        "thumbs-up": t("dialog.label_settings.glyphs.thumbs_up", "좋아요"),
        "circle-pause": t("dialog.label_settings.glyphs.circle_pause", "일시정지 원"),
        "pause": t("dialog.label_settings.glyphs.pause", "일시정지"),
        "circle-stop": t("dialog.label_settings.glyphs.circle_stop", "정지 원"),
        "hourglass-end": t("dialog.label_settings.glyphs.hourglass_end", "모래시계 끝"),
        "circle-xmark": t("dialog.label_settings.glyphs.circle_xmark", "엑스 원"),
        "square-xmark": t("dialog.label_settings.glyphs.square_xmark", "엑스 상자"),
        "ban": t("dialog.label_settings.glyphs.ban", "금지"),
        "calendar-xmark": t("dialog.label_settings.glyphs.calendar_xmark", "엑스 달력"),
        "circle-question": t("dialog.label_settings.glyphs.circle_question", "물음표 원"),
        "circle-info": t("dialog.label_settings.glyphs.circle_info", "정보 원"),
        "circle-minus": t("dialog.label_settings.glyphs.circle_minus", "빼기 원"),
        "eye-slash": t("dialog.label_settings.glyphs.eye_slash", "숨김"),
        "bell": t("dialog.label_settings.glyphs.bell", "종"),
        "box-archive": t("dialog.label_settings.glyphs.box_archive", "보관함"),
        "inbox": t("dialog.label_settings.glyphs.inbox", "받은 편지함"),
        "paper-plane": t("dialog.label_settings.glyphs.paper_plane", "종이비행기"),
        "comments": t("dialog.label_settings.glyphs.comments", "대화"),
        "user-clock": t("dialog.label_settings.glyphs.user_clock", "사람과 시계"),
        "handshake": t("dialog.label_settings.glyphs.handshake", "악수"),
        "briefcase": t("dialog.label_settings.glyphs.briefcase", "서류 가방"),
    }


def glyph_display_name(name: str) -> str:
    """Translated name of a glyph id such as ``fa6s.circle-check``."""
    short = str(name or "").split(".", 1)[-1]
    return _glyph_names().get(short, short)


def _color_scheme_names() -> dict:
    return {
        "meaning": t("dialog.label_settings.color_schemes.meaning", "의미 색(기본)"),
        "vivid": t("dialog.label_settings.color_schemes.vivid", "선명"),
        "soft": t("dialog.label_settings.color_schemes.soft", "차분"),
        "mono": t("dialog.label_settings.color_schemes.mono", "단색"),
    }


# priority/status display labels
def _get_priority_display():
    return {
        "urgent": t("priority.urgent"),
        "high": t("priority.high"),
        "normal": t("priority.normal"),
        "low": t("priority.low"),
        "none": t("priority.none", "미지정"),
    }


def _get_status_display():
    return {
        "pending": t("status.pending"),
        "in_progress": t("status.in_progress"),
        "completed": t("status.completed"),
        "deferred": t("status.deferred"),
        "none": t("status.none", "미지정"),
    }


def row_paint_color(section: str, key: str, custom: str = "") -> str:
    """Colour a row's glyph is painted in: the user colour or the meaning colour."""
    if task_constants.is_color(custom):
        return task_glyphs.custom_glyph_color(custom)
    if section == "priority":
        return task_glyphs.default_priority_color(key)
    return task_glyphs.default_status_color(key)


def _label_settings_style_bundle(tokens=None, metrics=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_bundle = build_settings_style_bundle(tokens, metrics)

    base_font_px = max(12, int(metrics.get("base_font_pt", 14)))
    field_radius = max(6, int(metrics.get("field_radius", 7)))
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_alt = tokens.get("surface_alt", "#1c1c23")
    surface_hover = tokens.get("surface_hover", "#18181f")
    accent = tokens.get("accent", "#4da6ff")

    picker_button = "".join(
        f"QToolButton#{name} {{ "
        f"background: {surface_alt}; border: 1px solid {border_soft}; "
        f"border-radius: {field_radius}px; padding: 2px; "
        "}"
        f"QToolButton#{name}:hover {{ "
        f"background: {surface_hover}; border-color: {accent}; "
        "}"
        f"QToolButton#{name}:focus {{ "
        f"border: 1px solid {accent}; "
        "}"
        for name in ("glyphButton", "colorButton")
    )
    custom_bundle = {
        "hint": build_editor_text_style(
            tokens, tone="muted", font_px=max(11, base_font_px - 3), padding="0 2px"
        ),
        "scroll_shell": "QScrollArea { background: transparent; border: none; }",
        "inner_shell": "background: transparent;",
        "divider": f"background: {border_soft}; max-height: 1px; margin: 2px 0;",
        "header": build_editor_text_style(
            tokens, tone="muted", font_px=max(11, base_font_px - 3), weight=400
        ),
        "row_label": build_editor_text_style(
            tokens, tone="secondary", font_px=max(12, base_font_px - 1), weight=700
        ),
        "picker_button": picker_button,
        "text_edit": f"padding: 2px 8px; border-radius: {field_radius}px;",
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_accent": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_danger": build_editor_quick_button_style(tokens, metrics, tone="danger"),
    }
    return {**base_bundle, **custom_bundle}


def _glyph_picker_stylesheet(tokens=None, metrics=None) -> str:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    field_radius = max(6, int(metrics.get("field_radius", 7)))
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_bg = tokens.get("surface_bg", "#16161b")
    surface_item = tokens.get("surface_item", "#111116")
    surface_hover = tokens.get("surface_hover", "#18181f")
    accent = tokens.get("accent", "#4da6ff")
    text_primary = tokens.get("text_primary", "#f4f7fb")
    blocks = []
    for dialog_name, choice_name in (
        ("glyphPicker", "glyphChoice"),
        ("colorPicker", "colorChoice"),
    ):
        blocks.append(
            f"""
QDialog#{dialog_name} {{
    background-color: {surface_bg};
    border: 1px solid {border};
    border-radius: {field_radius + 1}px;
}}
QToolButton#{choice_name} {{
    background: {surface_item};
    border: 1px solid {border_soft};
    border-radius: {field_radius}px;
    padding: 2px;
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}}
QToolButton#{choice_name}:hover {{
    background: {surface_hover};
    border-color: {accent};
}}
QToolButton#{choice_name}:focus {{
    border: 1px solid {accent};
}}
QToolButton#{choice_name}:checked {{
    border: 2px solid {accent};
}}"""
        )
    blocks.append(
        f"""
QPushButton#colorAction {{
    background: {surface_item};
    color: {text_primary};
    border: 1px solid {border_soft};
    border-radius: {field_radius}px;
    padding: 4px 10px;
    min-height: 28px;
}}
QPushButton#colorAction:hover, QPushButton#colorAction:checked {{
    background: {surface_hover};
    border-color: {accent};
}}
QPushButton#colorAction:focus {{
    border: 1px solid {accent};
}}"""
    )
    return "\n".join(blocks).strip()


def swatch_icon(color: str, size: int = _SWATCH_PX) -> QIcon:
    """A filled round swatch for colour buttons."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor(color)
    painter.setBrush(fill if fill.isValid() else QColor("#9aa0aa"))
    outline = QColor(0, 0, 0, 90) if fill.lightnessF() > 0.6 else QColor(255, 255, 255, 90)
    painter.setPen(outline)
    painter.drawEllipse(1, 1, size * 2 - 2, size * 2 - 2)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


class _PickerPopup(QDialog):
    """Frameless popup shown below a row button."""

    def __init__(self, object_name: str, accessible_name: str, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAccessibleName(accessible_name)
        apply_common_dialog_style(
            self,
            extra_stylesheet=_glyph_picker_stylesheet(
                tokens=getattr(parent, "_ui_tokens", None),
                metrics=getattr(parent, "_dialog_metrics", None),
            ),
        )

    def show_near(self, widget):
        """Show the popup right below the given widget, kept on its screen."""
        self.adjustSize()
        pos = widget.mapToGlobal(QPoint(0, widget.height() + 2))
        screen = widget.screen()
        if screen is not None:
            area = screen.availableGeometry()
            if pos.y() + self.height() > area.bottom():
                pos.setY(widget.mapToGlobal(QPoint(0, 0)).y() - self.height() - 2)
            pos.setX(max(area.left(), min(pos.x(), area.right() - self.width())))
        self.move(pos)
        self.exec()


class GlyphPickerPopup(_PickerPopup):
    """Grid of the selectable priority/status glyphs, painted in one colour."""

    def __init__(self, color: str, current: str = "", parent=None):
        super().__init__(
            "glyphPicker", t("dialog.label_settings.glyph_picker", "아이콘 선택"), parent
        )
        self.selected_glyph = None
        self.choice_buttons = {}
        self._build_ui(color, current)

    def _build_ui(self, color: str, current: str):
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)
        current_btn = None
        for idx, name in enumerate(task_constants.GLYPH_CHOICES):
            btn = QToolButton()
            btn.setObjectName("glyphChoice")
            btn.setIcon(task_glyphs.glyph_icon(name, color))
            btn.setIconSize(QSize(_GLYPH_ICON_PX, _GLYPH_ICON_PX))
            label = glyph_display_name(name)
            btn.setToolTip(label)
            btn.setAccessibleName(label)
            btn.setCheckable(True)
            btn.setChecked(name == current)
            btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            btn.clicked.connect(lambda _=False, n=name: self._select(n))
            grid.addWidget(btn, idx // _GLYPH_PICKER_COLUMNS, idx % _GLYPH_PICKER_COLUMNS)
            self.choice_buttons[name] = btn
            if name == current:
                current_btn = btn
        if current_btn is not None:
            QTimer.singleShot(0, current_btn.setFocus)

    def _select(self, name: str):
        self.selected_glyph = name
        self.accept()


class ColorPickerPopup(_PickerPopup):
    """Colour swatches plus "default colour" and "custom colour…".

    ``selected_color`` is None when nothing was chosen, "" for the meaning
    (default) colour, or a #rrggbb value.
    """

    def __init__(self, current: str = "", default_color: str = "", parent=None):
        super().__init__("colorPicker", t("dialog.label_settings.color_picker", "색 선택"), parent)
        self.selected_color = None
        self.wants_custom = False
        self.choice_buttons = {}
        self._current = current if task_constants.is_color(current) else ""
        self._build_ui(default_color)

    def _build_ui(self, default_color: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(4)
        current_btn = None
        for idx, color in enumerate(task_constants.COLOR_SWATCHES):
            btn = QToolButton()
            btn.setObjectName("colorChoice")
            btn.setIcon(swatch_icon(color, 10))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(color)
            btn.setAccessibleName(color)
            btn.setCheckable(True)
            btn.setChecked(color == self._current)
            btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            btn.clicked.connect(lambda _=False, c=color: self._select(c))
            grid.addWidget(btn, idx // _COLOR_PICKER_COLUMNS, idx % _COLOR_PICKER_COLUMNS)
            self.choice_buttons[color] = btn
            if color == self._current:
                current_btn = btn
        root.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.default_btn = QPushButton(t("dialog.label_settings.color_default", "기본 색"))
        self.default_btn.setObjectName("colorAction")
        self.default_btn.setIcon(swatch_icon(default_color or "#9aa0aa", 7))
        self.default_btn.setCheckable(True)
        self.default_btn.setChecked(not self._current)
        self.default_btn.clicked.connect(lambda _=False: self._select(""))
        actions.addWidget(self.default_btn)
        self.custom_btn = QPushButton(t("dialog.label_settings.color_custom", "사용자 지정 색…"))
        self.custom_btn.setObjectName("colorAction")
        self.custom_btn.clicked.connect(self._choose_custom)
        actions.addWidget(self.custom_btn)
        actions.addStretch(1)
        root.addLayout(actions)
        QTimer.singleShot(0, (current_btn or self.default_btn).setFocus)

    def _choose_custom(self):
        # The owner opens the colour dialog once this popup has closed.
        self.wants_custom = True
        self.accept()

    def _select(self, color: str):
        self.selected_color = color
        self.accept()


class GlyphButton(QToolButton):
    """Shows one row's glyph; the chosen glyph id is kept on the button."""

    def __init__(self, row_name: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("glyphButton")
        self._color = color
        self._glyph = ""
        self.setIconSize(QSize(_GLYPH_ICON_PX, _GLYPH_ICON_PX))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(
            t("dialog.label_settings.change_icon", "{name} 아이콘 바꾸기", name=row_name)
        )

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color
        self.setIcon(task_glyphs.glyph_icon(self._glyph, self._color))

    def glyph(self) -> str:
        return self._glyph

    def set_glyph(self, name: str):
        self._glyph = name if task_constants.is_glyph(name) else ""
        self.setIcon(task_glyphs.glyph_icon(self._glyph, self._color))
        label = glyph_display_name(self._glyph) if self._glyph else ""
        self.setToolTip(label)
        self.setAccessibleDescription(label)


class ColorButton(QToolButton):
    """Shows one row's colour; "" means the meaning (default) colour."""

    def __init__(self, row_name: str, section: str, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("colorButton")
        self.section = section
        self.key = key
        self._custom = ""
        self.setIconSize(QSize(_SWATCH_PX, _SWATCH_PX))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(
            t("dialog.label_settings.change_color", "{name} 색 바꾸기", name=row_name)
        )
        self._refresh()

    def custom_color(self) -> str:
        return self._custom

    def default_paint_color(self) -> str:
        return row_paint_color(self.section, self.key, "")

    def paint_color(self) -> str:
        return row_paint_color(self.section, self.key, self._custom)

    def set_custom_color(self, color: str):
        self._custom = color.lower() if task_constants.is_color(color) else ""
        self._refresh()

    def _refresh(self):
        self.setIcon(swatch_icon(self.paint_color()))
        label = self._custom or t("dialog.label_settings.color_default", "기본 색")
        self.setToolTip(label)
        self.setAccessibleDescription(label)


class EmojiLineEdit(QLineEdit):
    """Windows emoji panel (Win + .) input-friendly line edit.

    Used by the task dialog name field. This version avoids problematic
    top-level window flags and modality that can cause crashes when embedded
    in layouts.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setInputMethodHints(Qt.InputMethodHint.ImhNone)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Ensure the parent window is active to receive IME events
        if self.window():
            self.window().activateWindow()
        QTimer.singleShot(0, self._reactivate_input_target)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.window():
            self.window().activateWindow()
        QTimer.singleShot(0, self._reactivate_input_target)

    def _reactivate_input_target(self):
        if not self.hasFocus():
            return
        try:
            from PyQt6.QtGui import QGuiApplication

            im = QGuiApplication.inputMethod()
            if im:
                im.update(Qt.InputMethodQuery.ImEnabled)
        except Exception:
            pass


class LabelSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.label_settings.title"))
        # Keep width slightly wider and reduce default height for denser layout.
        apply_common_dialog_style(self, minimum_width=720, size=(820, 640))
        settings = getattr(parent, "settings", None)
        self._ui_tokens = get_dialog_theme_tokens(settings=settings)
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True, settings=settings)
        self._style_bundle = _label_settings_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        # Fill the rows before the first paint so the dialog never shows empty
        # glyph buttons (binding is cheap now that the style bundle is shared).
        self._load_current_values()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    # ── UI ──────────────────────────────────────────────────────
    def _small_button(self, text: str, style_key: str = "button_secondary") -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(self._style_bundle[style_key])
        btn.setMinimumHeight(31)
        btn.setAutoDefault(False)
        return btn

    def _init_ui(self):
        apply_common_dialog_style(
            self,
            extra_stylesheet=build_settings_dialog_stylesheet(
                self._ui_tokens, include_common=False
            ),
        )
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        # Presets
        preset_group = QFrame()
        preset_group.setObjectName("card")
        preset_group.setStyleSheet(self._style_bundle.get("card", ""))
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setContentsMargins(20, 16, 20, 16)
        preset_layout.setSpacing(10)

        builtin_row = QHBoxLayout()
        builtin_row.addWidget(QLabel(t("dialog.label_settings.builtin")))
        for name in task_constants.BUILTIN_PRESETS:
            display_name = t(f"dialog.label_settings.builtin_presets.{name}", name)
            btn = self._small_button(display_name)
            btn.clicked.connect(lambda _, n=name: self._apply_builtin_preset(n))
            builtin_row.addWidget(btn)
        builtin_row.addStretch()
        preset_layout.addLayout(builtin_row)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel(t("dialog.label_settings.color_scheme", "색 구성:")))
        for key, display_name in _color_scheme_names().items():
            # A space keeps the swatch off the first letter.
            btn = self._small_button(f" {display_name}")
            btn.setAccessibleName(display_name)
            scheme = task_constants.COLOR_SCHEMES[key]
            preview = next(
                (c for c in scheme["priority"].values() if c),
                task_glyphs.default_priority_color("urgent"),
            )
            btn.setIcon(swatch_icon(preview, 6))
            btn.clicked.connect(lambda _, k=key: self._apply_color_scheme(k))
            color_row.addWidget(btn)
        color_row.addStretch()
        preset_layout.addLayout(color_row)

        user_row = QHBoxLayout()
        user_row.addWidget(QLabel(t("dialog.label_settings.user")))
        self.user_preset_combo = QComboBox()
        self.user_preset_combo.setMinimumWidth(150)
        self.user_preset_combo.setMinimumHeight(31)
        self._refresh_user_preset_combo()
        user_row.addWidget(self.user_preset_combo)

        load_btn = self._small_button(t("dialog.label_settings.load"))
        load_btn.clicked.connect(self._load_user_preset)
        user_row.addWidget(load_btn)

        save_preset_btn = self._small_button(t("dialog.label_settings.save_current"))
        save_preset_btn.clicked.connect(self._save_user_preset)
        user_row.addWidget(save_preset_btn)

        del_preset_btn = self._small_button(t("dialog.label_settings.delete"), "button_danger")
        del_preset_btn.clicked.connect(self._delete_user_preset)
        user_row.addWidget(del_preset_btn)

        user_row.addStretch()
        preset_layout.addLayout(user_row)

        preset_section_layout, _ = build_collapsible_section(
            t("dialog.label_settings.preset_group", "프리셋"),
            preset_group,
            expanded=False,
            settings_key="label_settings_preset_expanded",
        )
        root.addLayout(preset_section_layout)

        hint = QLabel(
            t(
                "dialog.label_settings.glyph_color_hint",
                "아이콘이나 색을 눌러 바꿀 수 있습니다. 미지정 일정은 캘린더와 목록에 아이콘 없이 표시됩니다.",
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(self._style_bundle["hint"])
        root.addWidget(hint)

        # Scroll area (priority + status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # The two cards stack when they do not fit side by side; never scroll
        # sideways (the status card used to be cut off at the minimum width).
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(self._style_bundle["scroll_shell"])

        inner = QWidget()
        inner.setStyleSheet(self._style_bundle["inner_shell"])
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(10)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        prio_group, prio_grid = self._build_group_card(t("dialog.label_settings.priority_group"))
        self.prio_fields = {}
        for idx, (key, display) in enumerate(_get_priority_display().items()):
            self.prio_fields[key] = self._add_row(prio_grid, idx + 1, display, "priority", key)

        status_group, status_grid = self._build_group_card(t("dialog.label_settings.status_group"))
        self.status_fields = {}
        for idx, (key, display) in enumerate(_get_status_display().items()):
            self.status_fields[key] = self._add_row(status_grid, idx + 1, display, "status", key)

        # Same label column in both cards so the icon columns line up.
        label_width = 0
        for grid in (prio_grid, status_grid):
            for row in range(grid.rowCount()):
                item = grid.itemAtPosition(row, 0)
                widget = item.widget() if item is not None else None
                if isinstance(widget, QLabel):
                    widget.ensurePolished()
                    bold = QFont(widget.font())
                    bold.setBold(True)
                    text_width = QFontMetrics(bold).horizontalAdvance(widget.text()) + 8
                    label_width = max(label_width, text_width, widget.sizeHint().width())
        for grid in (prio_grid, status_grid):
            grid.setColumnMinimumWidth(0, label_width)

        self._cards_grid = QGridLayout()
        self._cards_grid.setHorizontalSpacing(10)
        self._cards_grid.setVerticalSpacing(10)
        self._cards = (prio_group, status_group)
        self._cards_stacked = None
        inner_layout.addLayout(self._cards_grid)
        inner_layout.addStretch(1)

        scroll.setWidget(inner)
        self._cards_viewport = scroll.viewport()
        self._cards_viewport.installEventFilter(self)
        self._reflow_cards(self._cards_viewport.width())
        root.addWidget(scroll, 1)

        # Footer
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(self._style_bundle["divider"])
        root.addWidget(divider)

        self.reset_btn = QPushButton(t("dialog.label_settings.reset"))
        self.reset_btn.setObjectName("danger_btn")
        self.reset_btn.setAccessibleName(self.reset_btn.text())
        self.reset_btn.setAutoDefault(False)
        self.reset_btn.clicked.connect(self._reset_to_default)
        btn_row, self.save_btn, self.cancel_btn = build_dialog_footer(
            ok_label=t("dialog.common.save"),
            cancel_label=t("dialog.common.cancel"),
            extra_left_widget=self.reset_btn,
        )
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn.clicked.connect(self.reject)
        root.addLayout(btn_row)

    def _reflow_cards(self, available_width: int):
        """Side by side when both cards fit at their minimum, else stacked."""
        needed = sum(card.minimumWidth() for card in self._cards) + 10
        stacked = available_width < needed
        if stacked == self._cards_stacked:
            return
        self._cards_stacked = stacked
        for card in self._cards:
            self._cards_grid.removeWidget(card)
        first, second = self._cards
        if stacked:
            self._cards_grid.addWidget(first, 0, 0)
            self._cards_grid.addWidget(second, 1, 0)
            self._cards_grid.setColumnStretch(1, 0)
        else:
            self._cards_grid.addWidget(first, 0, 0)
            self._cards_grid.addWidget(second, 0, 1)
            self._cards_grid.setColumnStretch(1, 1)
        self._cards_grid.setColumnStretch(0, 1)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_cards_viewport", None) and event.type() == QEvent.Type.Resize:
            self._reflow_cards(obj.width())
        return super().eventFilter(obj, event)

    def _build_group_card(self, title: str):
        group = QFrame()
        group.setObjectName("card")
        group.setStyleSheet(self._style_bundle.get("card", ""))
        group_v = QVBoxLayout(group)
        group_v.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(title)
        lbl.setStyleSheet(self._style_bundle.get("card_title", ""))
        group_v.addWidget(lbl)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(self._style_bundle.get("divider", ""))
        group_v.addWidget(div)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        group_v.addWidget(grid_w)
        self._add_header_row(grid)
        grid.setColumnStretch(3, 1)
        group.setMinimumWidth(320)
        return group, grid

    def _add_header_row(self, grid):
        headers = [
            t("dialog.label_settings.header_type"),
            t("dialog.label_settings.header_icon"),
            t("dialog.label_settings.header_color", "색"),
            t("dialog.label_settings.header_name"),
        ]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setStyleSheet(self._style_bundle["header"])
            grid.addWidget(lbl, 0, col)

    def _add_row(self, grid, row, display_name, section, key):
        """Add one editable row and return its (glyph button, colour button, name editor)."""
        lbl = QLabel(display_name)
        lbl.setStyleSheet(self._style_bundle["row_label"])
        grid.addWidget(lbl, row, 0)

        color_btn = ColorButton(display_name, section, key)
        glyph_btn = GlyphButton(display_name, color_btn.paint_color())
        for btn in (glyph_btn, color_btn):
            btn.setFixedSize(44, 31)
            btn.setStyleSheet(self._style_bundle["picker_button"])
        glyph_btn.clicked.connect(lambda _=False, gb=glyph_btn: self._open_picker(gb))
        color_btn.clicked.connect(
            lambda _=False, cb=color_btn, gb=glyph_btn: self._open_color_picker(cb, gb)
        )
        grid.addWidget(glyph_btn, row, 1)
        grid.addWidget(color_btn, row, 2)

        text_edit = QLineEdit()
        text_edit.setMaxLength(10)
        text_edit.setMinimumWidth(90)
        text_edit.setMinimumHeight(31)
        text_edit.setStyleSheet(self._style_bundle["text_edit"])
        grid.addWidget(text_edit, row, 3)
        lbl.setBuddy(text_edit)

        return (glyph_btn, color_btn, text_edit)

    def _open_picker(self, glyph_btn: GlyphButton):
        """Open the glyph grid below the button and apply the chosen glyph."""
        popup = GlyphPickerPopup(glyph_btn.color, glyph_btn.glyph(), self)
        popup.show_near(glyph_btn)
        if popup.selected_glyph:
            glyph_btn.set_glyph(popup.selected_glyph)
        glyph_btn.setFocus()

    def _open_color_picker(self, color_btn: ColorButton, glyph_btn: GlyphButton):
        popup = ColorPickerPopup(color_btn.custom_color(), color_btn.default_paint_color(), self)
        popup.show_near(color_btn)
        chosen = popup.selected_color
        if popup.wants_custom:
            color = QColorDialog.getColor(
                QColor(color_btn.custom_color() or color_btn.paint_color()),
                self,
                t("dialog.label_settings.color_custom", "사용자 지정 색…"),
            )
            chosen = color.name(QColor.NameFormat.HexRgb).lower() if color.isValid() else None
        if chosen is not None:
            self._set_row_color(color_btn, glyph_btn, chosen)
        color_btn.setFocus()

    @staticmethod
    def _set_row_color(color_btn: ColorButton, glyph_btn: GlyphButton, color: str):
        color_btn.set_custom_color(color)
        glyph_btn.set_color(color_btn.paint_color())

    def _all_rows(self):
        for section, fields in (("priority", self.prio_fields), ("status", self.status_fields)):
            for key, row in fields.items():
                yield section, key, row

    # ── Data load/save ─────────────────────────────────────────
    def _apply_values(self, values: dict):
        """Fill every row from {"priority": {key: {icon, text, color}}, "status": ...}."""
        for section, key, (glyph_btn, color_btn, text_edit) in self._all_rows():
            vals = values.get(section, {}).get(key, {})
            self._set_row_color(color_btn, glyph_btn, vals.get("color", ""))
            glyph_btn.set_glyph(vals.get("icon", ""))
            text_edit.setText(vals.get("text", ""))

    def _load_current_values(self):
        self._apply_values(task_constants.get_current_labels())

    def _collect_data(self):
        defaults = {
            "priority": (
                task_constants._DEFAULT_PRIORITY_ICON,
                task_constants._DEFAULT_PRIORITY_TEXT,
            ),
            "status": (task_constants._DEFAULT_STATUS_ICON, task_constants._DEFAULT_STATUS_TEXT),
        }
        data = {"priority": {}, "status": {}}
        for section, key, (glyph_btn, color_btn, text_edit) in self._all_rows():
            icons, texts = defaults[section]
            data[section][key] = {
                "icon": glyph_btn.glyph() or icons[key],
                "text": text_edit.text().strip() or texts[key],
                "color": color_btn.custom_color(),
            }
        return data["priority"], data["status"]

    def _save(self):
        priority_data, status_data = self._collect_data()
        task_constants.save_custom_labels(priority_data, status_data)
        task_glyphs.clear_glyph_cache()
        self.accept()

    def _default_values(self) -> dict:
        defaults = task_constants.get_builtin_presets()["default"]
        for section in ("priority", "status"):
            for vals in defaults[section].values():
                vals["color"] = ""
        return defaults

    def _reset_to_default(self):
        """Put every row back to the default icon, colour and name (saved on Save)."""
        reply = QMessageBox.question(
            self,
            t("dialog.label_settings.reset"),
            t("dialog.label_settings.reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_values(self._default_values())

    # ── Presets ─────────────────────────────────────────────────
    def _apply_preset_data(self, preset: dict):
        """Apply a preset; icons that are not glyph ids (older emoji) use the default.

        Colours are applied only when the preset has them (user presets saved
        before colours existed keep the current colours).
        """
        sections = (
            ("priority", self.prio_fields, task_constants._DEFAULT_PRIORITY_ICON),
            ("status", self.status_fields, task_constants._DEFAULT_STATUS_ICON),
        )
        for section, fields, defaults in sections:
            for key, vals in preset.get(section, {}).items():
                if key not in fields:
                    continue
                glyph_btn, color_btn, text_edit = fields[key]
                if "color" in vals:
                    self._set_row_color(color_btn, glyph_btn, vals.get("color", ""))
                icon = vals.get("icon", "")
                glyph_btn.set_glyph(icon if task_constants.is_glyph(icon) else defaults[key])
                text_edit.setText(vals.get("text", ""))

    def _apply_builtin_preset(self, name: str):
        preset = task_constants.get_builtin_presets().get(name)
        if preset:
            self._apply_preset_data(preset)

    def _apply_color_scheme(self, name: str):
        scheme = task_constants.COLOR_SCHEMES.get(name)
        if not scheme:
            return
        for section, key, (glyph_btn, color_btn, _text_edit) in self._all_rows():
            self._set_row_color(color_btn, glyph_btn, scheme[section].get(key, ""))

    def _refresh_user_preset_combo(self):
        self.user_preset_combo.clear()
        presets = task_constants.get_user_presets()
        if not presets:
            self.user_preset_combo.addItem(t("dialog.label_settings.no_user_presets"))
        else:
            for p in presets:
                self.user_preset_combo.addItem(p["name"])

    def _load_user_preset(self):
        presets = task_constants.get_user_presets()
        if not presets:
            QMessageBox.information(
                self, t("dialog.common.notification"), t("dialog.label_settings.none_to_load")
            )
            return
        idx = self.user_preset_combo.currentIndex()
        if 0 <= idx < len(presets):
            self._apply_preset_data(presets[idx])

    def _save_user_preset(self):
        name, ok = QInputDialog.getText(
            self,
            t("dialog.label_settings.save_preset_title"),
            t("dialog.label_settings.enter_preset_name"),
            text="",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in task_constants.BUILTIN_PRESETS:
            QMessageBox.warning(
                self,
                t("dialog.task.error"),
                t("dialog.label_settings.error_builtin_name", name=name),
            )
            return

        priority_data, status_data = self._collect_data()
        task_constants.save_user_preset(name, priority_data, status_data)
        self._refresh_user_preset_combo()
        idx = self.user_preset_combo.findText(name)
        if idx >= 0:
            self.user_preset_combo.setCurrentIndex(idx)
        QMessageBox.information(
            self,
            t("dialog.label_settings.save_done"),
            t("dialog.label_settings.save_success_msg", name=name),
        )

    def _delete_user_preset(self):
        presets = task_constants.get_user_presets()
        if not presets:
            QMessageBox.information(
                self, t("dialog.common.notification"), t("dialog.label_settings.none_to_delete")
            )
            return
        idx = self.user_preset_combo.currentIndex()
        if idx < 0 or idx >= len(presets):
            return
        name = presets[idx]["name"]
        reply = QMessageBox.question(
            self,
            t("dialog.label_settings.delete"),
            t("dialog.label_settings.delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            task_constants.delete_user_preset(name)
            self._refresh_user_preset_combo()
