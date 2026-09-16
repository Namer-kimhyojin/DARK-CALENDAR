# -*- coding: utf-8 -*-
"""Window opacity and theme-related action mixin."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMenu

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.color_utils import contrast_safe_color
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
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
        neutral_rgb = "0,0,0" if snapshot.text_theme == "light" else "255,255,255"

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
                height: 4px; background: rgba({neutral_rgb},{groove_alpha}); border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {theme}; border: 2px solid {_ta(handle_border_alpha)};
                width: 12px; height: 12px; margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {snapshot.text_palette["text_primary"]}; border: 2px solid {theme};
            }}
            QSlider::sub-page:horizontal {{
                background: {_ta(sub_alpha)}; border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: rgba({neutral_rgb},{add_alpha}); border-radius: 2px;
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
        from calendar_app.presentation.main_window.top_bar_builder import (
            build_top_bar_frame_style,
            build_top_bar_runtime_styles,
        )
        from calendar_app.presentation.theme.style_builder import (
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

        _txt_primary = palette["text_primary"]
        self._tb_icon_color = _txt_primary
        self._tb_icon_active_color = theme
        topbar_styles = build_top_bar_runtime_styles(self.settings, size, theme)

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
        if getattr(self, "_welcome_banner", None) is not None:
            from calendar_app.presentation.main_window.first_run_banner import (
                apply_first_run_banner_theme,
            )

            apply_first_run_banner_theme(self)

        self._apply_slider_opacity_style()

        if hasattr(self, "search_edit"):
            search_style_changed = _set_stylesheet_if_changed(
                self.search_edit,
                topbar_styles["search"],
            )
            if search_style_changed:
                self.search_edit.style().unpolish(self.search_edit)
                self.search_edit.style().polish(self.search_edit)

        for attr in ("lock_label", "magnet_label"):
            if getattr(self, attr, None) is not None:
                _set_stylesheet_if_changed(getattr(self, attr), topbar_styles["label"])
        if getattr(self, "top_bar_divider", None) is not None:
            _set_stylesheet_if_changed(self.top_bar_divider, topbar_styles["divider"])
        for attr in ("lock_btn", "magnet_btn"):
            if getattr(self, attr, None) is not None:
                _set_stylesheet_if_changed(getattr(self, attr), topbar_styles["mode_button"])
        if getattr(self, "widget_mode_btn", None) is not None:
            _set_stylesheet_if_changed(self.widget_mode_btn, topbar_styles["tool_button"])

        apply_top_menu_theme(
            self,
            size,
            theme,
            text_theme,
            panel_base,
            opacity_factor,
            persist_opacity=persist_opacity,
        )
        from calendar_app.presentation.main_window.top_menus.common import (
            refresh_top_menu_icons,
        )

        role_colors = {
            "neutral": _txt_primary,
            "accent": contrast_safe_color(theme, panel_base, minimum=3.0),
            "warning": contrast_safe_color("#d39a2a", panel_base, minimum=3.0),
            "danger": contrast_safe_color("#d25a66", panel_base, minimum=3.0),
        }
        refresh_top_menu_icons(self, role_colors)

        if getattr(self, "sync_action_btn", None) is not None:
            self.sync_action_btn.setIcon(_ic(ICON.SYNC, color=role_colors["accent"]))
        if getattr(self, "widget_mode_btn", None) is not None:
            self.widget_mode_btn.setIcon(_ic(ICON.WIDGET_MGR, color=_txt_primary))
        if getattr(self, "lock_btn", None) is not None:
            locked = bool(self.lock_btn.isChecked())
            self.lock_btn.setIcon(
                _ic(ICON.LOCK if locked else ICON.UNLOCK, color=theme if locked else _txt_primary)
            )
        if getattr(self, "magnet_btn", None) is not None:
            magnet_enabled = bool(self.magnet_btn.isChecked())
            self.magnet_btn.setIcon(
                _ic(ICON.MAGNET if magnet_enabled else ICON.MAGNET_OFF, color=_txt_primary)
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
