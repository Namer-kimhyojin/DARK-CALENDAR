# -*- coding: utf-8 -*-
"""Window opacity and theme-related action mixin."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMenu

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.theme_settings import (
    get_opacity_factor,
    opacity_percent_label,
    set_opacity_byte,
)
from calendar_app.shared.theme_snapshot import build_theme_snapshot


def _set_stylesheet_if_changed(widget, stylesheet: str) -> bool:
    """Apply a stylesheet only when its rendered value changed."""
    if widget is None:
        return False
    stylesheet = str(stylesheet or "")
    try:
        if widget.styleSheet() == stylesheet:
            return False
    except Exception:
        pass
    widget.setStyleSheet(stylesheet)
    return True


class ThemeActionsMixin:
    def initialize_system_theme_listener(self):
        app = QApplication.instance()
        if app is None:
            return
        from calendar_app.shared.system_theme import (
            resolve_system_text_theme,
            set_runtime_system_text_theme,
        )

        resolved = resolve_system_text_theme()
        set_runtime_system_text_theme(resolved)
        self._last_system_text_theme = resolved
        self._last_applied_system_text_theme = resolved
        if self._system_theme_refresh_timer is None:
            self._system_theme_refresh_timer = QTimer(self)
            self._system_theme_refresh_timer.setSingleShot(True)
            self._system_theme_refresh_timer.setInterval(50)
            self._system_theme_refresh_timer.timeout.connect(
                self._apply_pending_system_theme_change
            )
        style_hints = app.styleHints()
        if self._system_theme_style_hints is style_hints:
            return
        style_hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        self._system_theme_style_hints = style_hints

    def _notify_open_appearance_dialogs(self, resolved_theme: str):
        for widget in QApplication.allWidgets():
            handler = getattr(widget, "handle_system_theme_change", None)
            if callable(handler):
                handler(resolved_theme)

    def _on_system_color_scheme_changed(self, color_scheme):
        from calendar_app.shared.system_theme import (
            color_scheme_text_theme,
            resolve_system_text_theme,
            set_runtime_system_text_theme,
        )

        resolved = color_scheme_text_theme(color_scheme) or resolve_system_text_theme()
        set_runtime_system_text_theme(resolved)
        self._last_system_text_theme = resolved
        self._notify_open_appearance_dialogs(resolved)
        if str(self.settings.value("text_theme", "dark") or "dark") != "auto":
            return
        self._pending_system_text_theme = resolved
        if resolved == self._last_applied_system_text_theme:
            self._system_theme_refresh_timer.stop()
            return
        self._system_theme_refresh_timer.start()

    def _apply_pending_system_theme_change(self):
        if str(self.settings.value("text_theme", "dark") or "dark") != "auto":
            return
        resolved = self._pending_system_text_theme
        if resolved not in {"dark", "light"}:
            return
        if resolved == self._last_applied_system_text_theme:
            return
        self._last_applied_system_text_theme = resolved
        self._system_theme_apply_count += 1
        self.apply_theme_settings(persist_opacity=False)

    def set_opacity(self, value):
        set_opacity_byte(self.settings, value)
        self._apply_opacity_preview()

        slider = getattr(self, "slider", None)
        if slider is not None and slider.isSliderDown():
            return

        if getattr(self, "_ui_fully_initialized", False):
            self.finalize_opacity_change()

    def _apply_opacity_preview(self):
        # Keep the native window opaque; transparency is expressed through rgba layers.
        self.setWindowOpacity(1.0)
        for dock_name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
            dock = getattr(self, dock_name, None)
            if dock is not None and dock.isFloating():
                dock.setWindowOpacity(1.0)

        opacity_factor = get_opacity_factor(self.settings, persist_normalized=True)

        if hasattr(self, "top_bar_frame"):
            from calendar_app.presentation.main_window.top_bar_builder import (
                build_top_bar_frame_style,
            )

            _set_stylesheet_if_changed(
                self.top_bar_frame,
                build_top_bar_frame_style(self.settings, opacity_factor),
            )

        self._apply_slider_opacity_style()

    def finalize_opacity_change(self):
        for widget in QApplication.allWidgets():
            if isinstance(widget, QMenu):
                self.apply_menu_opacity(widget)
        self.apply_theme_settings()

    def _apply_slider_opacity_style(self):
        if not hasattr(self, "slider"):
            return
        from calendar_app.presentation.theme.style_builder import _hex_to_rgba

        snapshot = build_theme_snapshot(self.settings)
        theme = snapshot.theme_color
        opacity = snapshot.opacity_factor

        def _ta(a):
            return _hex_to_rgba(theme, round(a / 255, 3))

        groove_alpha = max(8, int(25 * opacity))
        sub_alpha = max(36, int(128 * opacity))
        add_alpha = max(4, int(12 * opacity))
        handle_border_alpha = max(96, int(204 * opacity))
        self.slider.setToolTip(
            f"{t('topbar.opacity_tooltip')} ({opacity_percent_label(self.slider.value())})"
        )

        _set_stylesheet_if_changed(
            self.slider,
            f"""
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 4px; background: rgba(255,255,255,{groove_alpha}); border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {theme}; border: 2px solid {_ta(handle_border_alpha)};
                width: 12px; height: 12px; margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: white; border: 2px solid {theme};
            }}
            QSlider::sub-page:horizontal {{
                background: {_ta(sub_alpha)}; border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: rgba(255,255,255,{add_alpha}); border-radius: 2px;
            }}
            """,
        )

    def apply_menu_opacity(self, menu):
        """Apply unified menu style so hover/selection colors stay consistent."""
        from calendar_app.presentation.theme.style_builder import _build_app_menu_style

        size = self.settings.value("font_size", 10, type=int)
        if size <= 0:
            size = 10
        snapshot = build_theme_snapshot(self.settings)
        theme = snapshot.theme_color
        text_theme = snapshot.text_theme
        menu_style = _build_app_menu_style(
            size,
            theme,
            text_theme,
            panel_base_color=snapshot.panel_base_color,
            opacity_factor=snapshot.opacity_factor,
            settings=self.settings,
            persist_opacity=False,
        )
        self._last_menu_style = menu_style

        seen = set()

        def _apply(menu_obj):
            if menu_obj is None:
                return
            menu_id = id(menu_obj)
            if menu_id in seen:
                return
            seen.add(menu_id)
            menu_obj.setWindowOpacity(1.0)
            _set_stylesheet_if_changed(menu_obj, menu_style)
            for action in menu_obj.actions():
                sub = action.menu()
                if sub is not None:
                    _apply(sub)

        _apply(menu)

    def change_theme_color(self, color_hex):
        """Change the main theme color."""
        self.settings.setValue("theme_color", color_hex)
        self.apply_theme_settings()
        self.show_toast(t("theme.toast_title"), t("theme.toast_msg"))

    def set_system_default_theme(self):
        """Set theme to follow Windows system default."""
        self.settings.setValue("text_theme", "auto")
        self.apply_theme_settings()
        self.show_toast(t("theme.toast_title"), t("theme.system_default", "시스템 기본"))

    def change_text_theme(self, text_theme: str):
        """Change the text theme."""
        self.settings.setValue("text_theme", text_theme)
        self.apply_theme_settings()
        from calendar_app.infrastructure.i18n import t as i18n_t

        if text_theme == "light":
            label = i18n_t("theme.light_mode")
        elif text_theme == "custom":
            label = i18n_t("theme.custom_mode", "Custom Theme")
        else:
            label = i18n_t("theme.dark_mode")
        self.show_toast(i18n_t("theme.toast_title"), label)

    def apply_theme_settings(self, *, persist_opacity=True):
        """Apply saved theme settings across the UI."""
        from calendar_app.presentation.main_window.dock_factory import build_dock_manager_style
        from calendar_app.presentation.main_window.top_bar_builder import build_top_bar_frame_style
        from calendar_app.presentation.theme.style_builder import (
            _hex_to_rgba,
            apply_top_menu_theme,
            build_global_stylesheet,
            build_tooltip_stylesheet,
        )

        family = self.settings.value("font_family", "Malgun Gothic")
        size = self.settings.value("font_size", 10, type=int)
        if size <= 0:
            size = 10
        snapshot = build_theme_snapshot(self.settings, persist_opacity=persist_opacity)
        theme = snapshot.theme_color
        text_theme = snapshot.text_theme
        panel_base = snapshot.panel_base_color
        opacity_factor = snapshot.opacity_factor
        palette = snapshot.ui_palette
        if str(self.settings.value("text_theme", "dark") or "dark") == "auto":
            self._last_applied_system_text_theme = snapshot.text_theme

        # Helper vars for inline overrides
        def _ta(a):
            return _hex_to_rgba(theme, round(a / 255, 3))

        _txt_primary = palette["text_primary"]
        _txt_secondary = palette["text_secondary"]
        _vline = "rgba(255,255,255,18)"
        _hover_weak = "rgba(255,255,255,40)"
        _search_bg = "rgba(255,255,255,10)"
        _search_bg_hover = "rgba(255,255,255,14)"
        _search_bg_focus = "rgba(255,255,255,20)"

        # Style resolution
        global_qss = build_global_stylesheet(family, size, theme, text_theme, panel_base, palette)
        tooltip_qss = build_tooltip_stylesheet(size, theme, text_theme, panel_base, palette)
        combined_qss = f"{global_qss}\n{tooltip_qss}"

        # Application-wide styling (QMessageBox, dialogs, etc.)
        _set_stylesheet_if_changed(QApplication.instance(), combined_qss)

        # Explicit window styling
        _set_stylesheet_if_changed(self, global_qss)

        # Container specific styling
        if hasattr(self, "top_bar_frame"):
            _set_stylesheet_if_changed(
                self.top_bar_frame,
                build_top_bar_frame_style(self.settings, opacity_factor),
            )
        if hasattr(self, "dock_manager"):
            _set_stylesheet_if_changed(
                self.dock_manager,
                build_dock_manager_style(self.settings, theme),
            )

        self._apply_slider_opacity_style()

        if hasattr(self, "search_edit"):
            field_pt = max(8, size)
            search_style_changed = _set_stylesheet_if_changed(
                self.search_edit,
                f"""
                QLineEdit {{
                    background: {_search_bg}; border: 1px solid {_ta(80)};
                    border-radius: 10px; padding: 4px 10px; color: {_txt_primary}; font-size: {field_pt}pt;
                }}
                QLineEdit:hover {{ border: 1px solid {_ta(128)}; background: {_search_bg_hover}; }}
                QLineEdit:focus {{ border: 1px solid {theme}; background: {_search_bg_focus}; }}
                """,
            )
            if search_style_changed:
                self.search_edit.style().unpolish(self.search_edit)
                self.search_edit.style().polish(self.search_edit)

        if hasattr(self, "magnet_btn"):
            btn_pt = max(8, size - 1)
            _set_stylesheet_if_changed(
                self.magnet_btn,
                f"""
                QPushButton {{
                    color: {_txt_secondary};
                    background: transparent;
                    border: 1px solid {_vline};
                    border-radius: 6px;
                    font-size: {btn_pt}pt;
                    font-weight: bold;
                    padding: 3px 8px;
                    min-width: 62px;
                }}
                QPushButton:hover {{
                    background: {_hover_weak};
                }}
                QPushButton:checked {{
                    color: {_txt_primary};
                    border: 1px solid {_ta(150)};
                    background: {_ta(56)};
                }}
                """,
            )

        apply_top_menu_theme(
            self,
            size,
            theme,
            text_theme,
            panel_base,
            opacity_factor,
            persist_opacity=persist_opacity,
        )

        try:
            from calendar_app.presentation.widgets.ui_components import _hover_info_popup

            if _hover_info_popup is not None:
                _hover_info_popup._last_theme = None
        except Exception:
            pass

        if hasattr(self, "_apply_overlay_clock_settings"):
            self._apply_overlay_clock_settings()
        if hasattr(self, "_apply_stopwatch_settings"):
            self._apply_stopwatch_settings()
        if hasattr(self, "_apply_date_card_settings"):
            self._apply_date_card_settings()
        if hasattr(self, "_apply_countdown_settings"):
            self._apply_countdown_settings()

        try:
            from calendar_app.presentation.panels.side_panel_renderer import (
                refresh_dock_panel_theme,
            )

            for dock_name in ("left_dock", "routine_dock", "directive_dock"):
                refresh_dock_panel_theme(getattr(self, dock_name, None))
        except Exception:
            pass

        if hasattr(self, "refresh_sync_status_theme"):
            self.refresh_sync_status_theme()
        elif hasattr(self, "update_sync_status"):
            self.update_sync_status()
        self.schedule_panel_refresh(
            left=True,
            center=True,
            right=True,
            notify_data_consumers=False,
        )
