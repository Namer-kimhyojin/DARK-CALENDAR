# -*- coding: utf-8 -*-
from collections.abc import Callable
import contextlib

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QGuiApplication,
    QMouseEvent,
    QPainterPath,
    QRegion,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.panel_widget_theme import (
    _WIDGET_COLOR_DEFAULT,
    _WIDGET_COLOR_FOLLOW_MAIN,
    _WIDGET_COLOR_PRESET_HEX,
    _WIDGET_COLOR_THEME_KEY,
    _apply_configured_widget_color,
    _apply_registered_widget_mode_skin,
    _apply_widget_background_opacity,
    _normalize_widget_color_mode,
    _read_widget_color_mode_from_settings,
    _resolve_widget_mode_tokens,
    _widget_color_mode_accent,
    _widget_mode_launcher_stylesheet,
    _widget_mode_menu_stylesheet,
    _widget_mode_panel_stylesheet,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_skin,
    read_widget_mode_skin_id,
    widget_mode_skins,
    write_widget_mode_skin_id,
)


class _FloatingWidgetBase(QWidget):
    """Base class for draggable floating panel widgets."""

    screen_changed = pyqtSignal()

    def __init__(self, app: QWidget, title: str, icon_text: str):
        super().__init__(None)
        self._app = app
        self._title = title
        self._icon_text = icon_text
        self._drag_start_global: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self._last_scale: float = 1.0
        self._theme_cache: dict[str, str] = {}
        self._restore_callback: Callable[[], None] | None = None
        self.on_refresh_requested: Callable[[], None] | None = None
        self.on_realign_requested: Callable[[], None] | None = None
        self.on_scale_changed: Callable[[float], None] | None = None
        self._custom_size: QSize | None = None  # Track manually resized dimensions
        self._surface_radius = 10
        self._manual_scale = 1.0

        always_top = str(app.settings.value("widget_mode_always_top", "false")).lower() == "true"

        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if always_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("widget_mode_panel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.surface = QFrame(self)
        self.surface.setObjectName("widget_mode_surface")
        self.surface_layout = QVBoxLayout(self.surface)
        self.surface_layout.setContentsMargins(4, 4, 4, 4)
        self.surface_layout.setSpacing(4)

        self.header = QFrame(self.surface)
        self.header.setObjectName("widget_mode_header")
        header_layout = QHBoxLayout(self.header)
        self.header_layout = header_layout
        header_layout.setContentsMargins(6, 5, 6, 5)
        header_layout.setSpacing(6)

        self.icon_label = QLabel(self._icon_text, self.header)
        self.icon_label.setObjectName("widget_mode_header_icon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.icon_label)

        self.title_label = QLabel(self._title, self.header)
        self.title_label.setObjectName("widget_mode_header_title")
        header_layout.addWidget(self.title_label, 1)

        # 캘린더 토글 버튼
        self.toggle_calendar_btn = QToolButton(self.header)
        self.toggle_calendar_btn.setObjectName("widget_mode_toggle_calendar_btn")
        self.toggle_calendar_btn.setText("📅")
        self.toggle_calendar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_calendar_btn.setToolTip(t("widget_mode.toggle_calendar", "캘린더 표시/숨김"))
        self.toggle_calendar_btn.setVisible(False)  # _PanelWidget에서만 표시
        header_layout.addWidget(self.toggle_calendar_btn)

        self.restore_btn = QToolButton(self.header)
        self.restore_btn.setObjectName("widget_mode_restore_btn")
        self.restore_btn.setText("↩")
        self.restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_btn.setToolTip(t("widget_mode.back_to_main", "메인 화면 보기"))
        self.restore_btn.clicked.connect(self._handle_restore_clicked)
        self.restore_btn.setVisible(False)
        header_layout.addWidget(self.restore_btn)

        self.close_btn = QToolButton(self.header)
        self.close_btn.setObjectName("widget_mode_close_btn")
        self.close_btn.setText("×")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip(t("widget_mode.close", "위젯 닫기"))
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)

        self.surface_layout.addWidget(self.header)
        self.accent_bar = QFrame(self.surface)
        self.accent_bar.setObjectName("widget_mode_accent_bar")
        self.accent_bar.setFixedHeight(3)
        self.accent_bar.setVisible(False)
        self.surface_layout.addWidget(self.accent_bar)

        self.content_container = QFrame(self.surface)
        self.content_container.setObjectName("widget_mode_content_container")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.surface_layout.addWidget(self.content_container, 1)

        self.size_grip_container = QFrame(self.surface)
        self.size_grip_container.setObjectName("widget_mode_size_grip_container")
        self.size_grip_layout = QHBoxLayout(self.size_grip_container)
        self.size_grip_layout.setContentsMargins(0, 0, 4, 0)
        self.size_grip_layout.addStretch()

        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(14, 14)
        self.size_grip_layout.addWidget(self.size_grip)
        self.surface_layout.addWidget(self.size_grip_container)

        self.surface.setGraphicsEffect(None)

        root.addWidget(self.surface)

        # Screen change detection
        self._last_screen_name = ""

    @staticmethod
    def _rounded_region(widget: QWidget, radius: int) -> QRegion:
        rect = widget.rect()
        if rect.width() <= 1 or rect.height() <= 1:
            return QRegion()
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()),
            float(rect.y()),
            float(rect.width()),
            float(rect.height()),
            float(radius),
            float(radius),
        )
        return QRegion(path.toFillPolygon().toPolygon())

    def _apply_corner_masks(self) -> None:
        # Transparent background: masks are not needed and waste CPU.
        # Clear any previously set mask so the widget clips nothing.
        if not self.mask().isEmpty():
            self.clearMask()
        if getattr(self, "surface", None) is not None and not self.surface.mask().isEmpty():
            self.surface.clearMask()

    def showEvent(self, event):
        super().showEvent(event)
        anim = getattr(self, "_entry_anim", None)
        if anim is not None:
            anim.stop()
        self._apply_corner_masks()

    def _get_current_screen(self):
        # We use the widget's own screen if available, fallback to screen at center
        screen = self.screen()
        if not screen:
            screen = QGuiApplication.screenAt(self.geometry().center())
        return screen

    @staticmethod
    def _clamp_manual_scale(value: float) -> float:
        return 1.0

    def _panel_settings_id(self) -> str:
        return type(self).__name__.lower()

    def _get_sibling_widget(self) -> "_FloatingWidgetBase | None":
        ctrl = getattr(self._app, "_panel_widget_mode_controller", None)
        if ctrl is None:
            return None
        panel = getattr(ctrl, "_panel", None)
        if isinstance(panel, _FloatingWidgetBase) and panel is not self:
            return panel
        return None

    def _trigger_sibling_realign(self) -> None:
        sib = self._get_sibling_widget()
        if sib is not None and sib.isVisible():
            sib._rebuild_scale_menu()
            if sib.on_realign_requested is not None:
                QTimer.singleShot(50, sib.on_realign_requested)

    def _size_setting_key(self) -> str:
        return f"widget_mode_size_{self._panel_settings_id()}"

    def _opacity_setting_key(self) -> str:
        return f"widget_mode_opacity_{self._panel_settings_id()}"

    def _position_setting_key(self) -> str:
        return f"widget_mode_pos_{self._panel_settings_id()}"

    def _color_setting_key(self) -> str:
        return _WIDGET_COLOR_THEME_KEY

    def _legacy_color_setting_key(self) -> str:
        return f"widget_mode_accent_{self._panel_settings_id()}"

    def _size_preset_setting_key(self) -> str:
        return "widget_mode_shared_size_preset"

    def size_setting_key(self) -> str:
        return self._size_setting_key()

    def position_setting_key(self) -> str:
        return self._position_setting_key()

    def _scale_setting_key(self) -> str:
        return "widget_mode_shared_manual_scale"

    @staticmethod
    def _size_presets() -> tuple[tuple[str, str, float, float], ...]:
        return (
            ("slim", "슬림", 0.88, 0.82),
            ("default", "기본", 1.00, 1.00),
            ("expanded", "확장", 1.12, 1.18),
        )

    @staticmethod
    def _color_presets() -> tuple[tuple[str, str, str], ...]:
        return (
            (_WIDGET_COLOR_DEFAULT, "Default", ""),
            (_WIDGET_COLOR_FOLLOW_MAIN, "Follow Main", ""),
            ("indigo", "Indigo", _WIDGET_COLOR_PRESET_HEX["indigo"]),
            ("ocean", "Ocean", _WIDGET_COLOR_PRESET_HEX["ocean"]),
            ("sage", "Sage", _WIDGET_COLOR_PRESET_HEX["sage"]),
            ("amber", "Amber", _WIDGET_COLOR_PRESET_HEX["amber"]),
            ("rose", "Rose", _WIDGET_COLOR_PRESET_HEX["rose"]),
            ("slate", "Slate", _WIDGET_COLOR_PRESET_HEX["slate"]),
        )

    def _read_size_preset(self) -> str:
        raw = (
            str(self._app.settings.value(self._size_preset_setting_key(), "default") or "default")
            .strip()
            .lower()
        )
        valid = {name for name, _label, _w, _h in self._size_presets()}
        return raw if raw in valid else "default"

    def _size_preset_multipliers(self) -> tuple[float, float]:
        current = self._read_size_preset()
        for name, _label, width_scale, height_scale in self._size_presets():
            if name == current:
                return width_scale, height_scale
        return 1.0, 1.0

    def _set_size_preset(self, preset: str) -> None:
        target = str(preset or "default").strip().lower()
        valid = {name for name, _label, _w, _h in self._size_presets()}
        if target not in valid:
            target = "default"
        self._app.settings.setValue(self._size_preset_setting_key(), target)
        self._app.settings.remove(self._size_setting_key())
        self._custom_size = None
        self._size_preset_dirty = True
        if self.on_realign_requested is not None:
            QTimer.singleShot(0, self.on_realign_requested)
        # Mark sibling dirty and trigger its realign too
        sib = self._get_sibling_widget()
        if sib is not None:
            sib._size_preset_dirty = True
        self._trigger_sibling_realign()

    def _read_widget_color_mode(self) -> str:
        return _read_widget_color_mode_from_settings(
            self._app.settings,
            legacy_key=self._legacy_color_setting_key(),
        )

    def _set_widget_color_mode(self, value: str) -> None:
        mode = _normalize_widget_color_mode(value)
        if mode == _WIDGET_COLOR_DEFAULT:
            self._app.settings.remove(self._color_setting_key())
        else:
            self._app.settings.setValue(self._color_setting_key(), mode)
        self._app.settings.remove(self._legacy_color_setting_key())
        self._theme_cache.clear()
        self.apply_palette(self._last_scale or 1.0)
        sib = self._get_sibling_widget()
        if sib is not None:
            sib._theme_cache.clear()
            sib.apply_palette(sib._last_scale or 1.0)

    def _read_widget_accent(self) -> str:
        return _widget_color_mode_accent(
            self._read_widget_color_mode(),
            settings=self._app.settings,
            palette=self._theme_cache,
        )

    def _set_widget_accent(self, value: str) -> None:
        self._set_widget_color_mode(value)

    def _pick_widget_accent(self) -> None:
        current = self._read_widget_accent() or self._theme_cache.get("accent", "#5856d6")
        picked = QColorDialog.getColor(
            QColor(current), self, t("widget_mode.color_picker", "위젯 강조색 선택")
        )
        if picked.isValid():
            self._set_widget_accent(picked.name(QColor.NameFormat.HexRgb))

    # ------------------------------------------------------------------ #
    # Panel surface theme: "light" | "dark"                              #
    # ------------------------------------------------------------------ #

    def _panel_theme_setting_key(self) -> str:
        return "widget_mode_panel_theme"

    def _read_panel_theme(self) -> str:
        return get_widget_mode_skin(self._read_widget_mode_skin()).base_theme

    def _set_panel_theme(self, value: str) -> None:
        self._set_widget_mode_skin("classic_dark" if value == "dark" else "classic_light")

    def _read_widget_mode_skin(self) -> str:
        return read_widget_mode_skin_id(self._app.settings)

    def _set_widget_mode_skin(self, skin_id: str) -> None:
        write_widget_mode_skin_id(self._app.settings, skin_id)
        self._theme_cache.clear()
        self.apply_palette(self._last_scale or 1.0)
        sib = self._get_sibling_widget()
        if sib is not None:
            sib._theme_cache.clear()
            sib.apply_palette(sib._last_scale or 1.0)

    def _read_manual_scale(self) -> float:
        return 1.0

    @staticmethod
    def _scale_steps() -> tuple[float, ...]:
        return (1.0,)

    @staticmethod
    def _scale_text(scale: float) -> str:
        return f"{int(round(scale * 100))}%"

    def manual_scale(self) -> float:
        return 1.0

    def _apply_manual_scale_resize(self, prev_scale: float, new_scale: float) -> None:
        return

    def _set_manual_scale(self, value: float, apply_resize: bool = True) -> None:
        self._manual_scale = 1.0
        return

    def _rebuild_scale_menu(self) -> None:
        return

    def _append_style_actions(self, menu: QMenu) -> None:
        style_menu = menu.addMenu(t("widget_mode.style_menu", "스타일"))

        size_menu = style_menu.addMenu(t("widget_mode.style_size", "크기"))
        current_size = self._read_size_preset()
        for name, label, _w, _h in self._size_presets():
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == current_size)
            action.triggered.connect(lambda _=False, preset=name: self._set_size_preset(preset))

        color_menu = style_menu.addMenu(t("widget_mode.style_color", "색상"))
        current_mode = self._read_widget_color_mode()
        for name, label, _color in self._color_presets():
            action = color_menu.addAction(label)
            action.setCheckable(True)
            action.setText(t(f"widget_mode.style_color_{name}", label))
            action.setChecked(name == current_mode)
            action.triggered.connect(
                lambda _=False, selected=name: self._set_widget_color_mode(selected)
            )

        color_menu.addSeparator()
        color_menu.addAction(
            t("widget_mode.style_color_custom", "직접 선택..."), self._pick_widget_accent
        )

        style_menu.addSeparator()
        skin_menu = style_menu.addMenu(t("widget_mode.style_color_skin", "색상 스킨"))
        current_skin = self._read_widget_mode_skin()
        for skin in widget_mode_skins():
            act = skin_menu.addAction(t(skin.label_key, skin.label_default))
            act.setCheckable(True)
            act.setChecked(current_skin == skin.skin_id)
            act.triggered.connect(
                lambda _=False, selected=skin.skin_id: self._set_widget_mode_skin(selected)
            )

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self._app.settings.setValue(self._position_setting_key(), self.pos())
        screen = self._get_current_screen()
        if screen:
            name = screen.name()
            if name != self._last_screen_name:
                self._last_screen_name = name
                self.screen_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            header_pos = self.header.mapFrom(self, event.position().toPoint())
            if self.header.rect().contains(header_pos):
                self._drag_start_global = event.globalPosition().toPoint()
                self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start_global is None or self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition().toPoint() - self._drag_start_global
        self.move(self._drag_start_pos + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_global = None
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        act_exit = menu.addAction(t("widget_mode.menu_exit", "Exit widget mode"))
        act_realign = menu.addAction(t("widget_mode.menu_realign", "Realign widgets"))
        act_refresh = menu.addAction(t("widget_mode.menu_refresh", "Refresh"))
        menu.addSeparator()

        settings = self._app.settings
        always_top = str(settings.value("widget_mode_always_top", "false")).lower() == "true"
        reserve_space = str(settings.value("widget_mode_reserve_space", "false")).lower() == "true"

        act_always_top = menu.addAction(t("widget_mode.menu_always_top", "Always on top"))
        act_always_top.setCheckable(True)
        act_always_top.setChecked(always_top)

        act_reserve_space = menu.addAction(
            t("widget_mode.menu_reserve_space", "Reserve screen space")
        )
        act_reserve_space.setCheckable(True)
        act_reserve_space.setChecked(reserve_space)

        menu.addSeparator()

        opacity_menu = menu.addMenu(t("widget_mode.menu_individual_opacity", "Opacity"))
        current_opacity = self._get_individual_opacity()
        for val in [100, 85, 70, 50, 30]:
            label = f"{val}%"
            act = opacity_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current_opacity == val)
            act.triggered.connect(lambda checked, v=val: self._set_individual_opacity(v))

        menu.addSeparator()
        self._append_style_actions(menu)
        menu.addSeparator()
        self._add_context_menu_actions(menu)

        action = menu.exec(event.globalPos())
        if action == act_exit:
            self._handle_restore_clicked()
        elif action == act_realign:
            if self.on_realign_requested:
                self.on_realign_requested()
        elif action == act_refresh:
            if self.on_refresh_requested:
                self.on_refresh_requested()
        elif action == act_always_top:
            controller = getattr(self._app, "_panel_widget_mode_controller", None)
            if controller:
                controller.toggle_always_on_top()
        elif action == act_reserve_space:
            controller = getattr(self._app, "_panel_widget_mode_controller", None)
            if controller:
                controller.toggle_reserve_space()

    def _menu_stylesheet(self) -> str:
        tokens = _resolve_widget_mode_tokens(app=self._app)
        tokens = _apply_registered_widget_mode_skin(tokens, self._app.settings)
        tokens = _apply_configured_widget_color(tokens, self._app.settings)
        return _widget_mode_menu_stylesheet(tokens)

    def _add_context_menu_actions(self, menu: QMenu) -> None:
        """Subclasses override this to add custom menu items."""
        pass

    def _get_individual_opacity(self) -> int:
        key = self._opacity_setting_key()
        try:
            value = int(self._app.settings.value(key, 100))
        except (TypeError, ValueError):
            value = 100
        return max(30, min(100, value))

    def _set_individual_opacity(self, value: int) -> None:
        clamped = max(30, min(100, int(value)))
        key = self._opacity_setting_key()
        self._app.settings.setValue(key, clamped)
        self._theme_cache.clear()
        self.apply_palette(self._last_scale or 1.0)
        self.update()


class _WidgetModeLauncher(QDialog):
    """Popup launcher with quick actions for widget creation."""

    def __init__(self, app: QWidget):
        super().__init__(app)
        self._app = app
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("widget_mode_launcher")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel(t("widget_mode.title", "Widget Mode"), self)
        title.setObjectName("widget_mode_launcher_title")
        layout.addWidget(title)

        desc = QLabel(
            t(
                "widget_mode.desc",
                "Open only the widgets you need.",
            ),
            self,
        )
        desc.setObjectName("widget_mode_launcher_desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.schedule_btn = QPushButton(
            t("widget_mode.open_schedule", "Open schedule widget"), self
        )
        self.work_btn = QPushButton(t("widget_mode.open_work", "Open work widget"), self)
        self.all_btn = QPushButton(t("widget_mode.open_all", "Open both widgets"), self)

        for btn in (self.schedule_btn, self.work_btn, self.all_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("widget_mode_launcher_btn")
            layout.addWidget(btn)

        self.apply_palette()

    def apply_palette(self, scale: float = 1.0) -> None:
        s = scale
        tokens = _resolve_widget_mode_tokens(app=self._app)
        tokens = _apply_registered_widget_mode_skin(tokens, self._app.settings)
        if not tokens:
            return
        self.setStyleSheet(_widget_mode_launcher_stylesheet(tokens=tokens, scale=s))


def _floating_set_restore_callback(self, callback: Callable[[], None] | None) -> None:
    self._restore_callback = callback
    if hasattr(self, "restore_btn"):
        self.restore_btn.setVisible(callback is not None)


def _floating_handle_restore_clicked(self) -> None:
    if self._restore_callback is not None:
        self._restore_callback()
    else:
        self.hide()


def _floating_read_theme_tokens(self) -> dict[str, str]:
    tokens = _resolve_widget_mode_tokens(app=self._app)
    tokens = _apply_registered_widget_mode_skin(tokens, self._app.settings)
    tokens = _apply_configured_widget_color(tokens, self._app.settings)
    return _apply_widget_background_opacity(tokens, self._get_individual_opacity())


def _floating_theme_tokens(self) -> dict[str, str]:
    if not self._theme_cache:
        self._theme_cache = self._read_theme_tokens()
    return dict(self._theme_cache)


def _floating_apply_palette(self, scale: float = 1.0) -> None:
    new_scale = max(0.75, float(scale or 1.0))
    # Only regenerate stylesheet when scale or skin-related settings changed.
    scale_changed = abs(new_scale - self._last_scale) > 0.001
    self._last_scale = new_scale
    tokens = self._read_theme_tokens()
    self._theme_cache = dict(tokens)
    self._surface_radius = max(10, int(round(16 * self._last_scale)))
    # Stylesheet cache: keyed by (scale, skin, accent override, opacity).
    cache_key = (
        int(round(new_scale * 100)),
        self._read_widget_mode_skin(),
        self._read_widget_color_mode(),
        self._get_individual_opacity(),
    )
    cached_ss = getattr(self, "_ss_cache", None)
    cached_key = getattr(self, "_ss_cache_key", None)
    if cached_ss is None or cached_key != cache_key or scale_changed:
        new_ss = _widget_mode_panel_stylesheet(tokens=tokens, scale=self._last_scale)
        self._ss_cache = new_ss
        self._ss_cache_key = cache_key
        self.setStyleSheet(new_ss)
    self.surface.update()
    self.update()
    self._apply_corner_masks()


def _floating_resize_event(self, event: QResizeEvent) -> None:
    QWidget.resizeEvent(self, event)
    if not self.isMinimized() and self.isVisible():
        self._custom_size = self.size()
        with contextlib.suppress(Exception):
            self._app.settings.setValue(self._size_setting_key(), self.size())
    resize_hook = getattr(self, "_handle_widget_resize", None)
    if callable(resize_hook):
        resize_hook()


_FloatingWidgetBase.set_restore_callback = _floating_set_restore_callback
_FloatingWidgetBase._handle_restore_clicked = _floating_handle_restore_clicked
_FloatingWidgetBase._read_theme_tokens = _floating_read_theme_tokens
_FloatingWidgetBase.theme_tokens = _floating_theme_tokens
_FloatingWidgetBase.apply_palette = _floating_apply_palette
_FloatingWidgetBase.resizeEvent = _floating_resize_event
