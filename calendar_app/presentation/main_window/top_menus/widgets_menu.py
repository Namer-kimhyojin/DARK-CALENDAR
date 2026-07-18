"""Widgets menu button builder."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se


def build_widgets_menu_btn(self, top_bar, menu_btn_style: str, menu_style: str):
    """Add the widgets menu button to the top bar."""
    self.widgets_menu_btn = QToolButton()
    self.widgets_menu_btn.setText(format_top_menu_button_text(_se(t("menu.widgets", "위젯"))))
    self.widgets_menu_btn.setIcon(_ic(ICON.WIDGET_MGR))
    self.widgets_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.widgets_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self.widgets_menu_btn.setStyleSheet(menu_btn_style)

    self.widgets_menu = QMenu(self)
    self.widgets_menu.setStyleSheet(menu_style)

    # Build once immediately when overlay manager is ready.
    if hasattr(self, "overlay_manager"):
        self.overlay_manager.build_widgets_menu(self.widgets_menu, menu_style)

    # Rebuild on open so menu items and style follow latest theme state.
    def _on_about_to_show():
        if hasattr(self, "overlay_manager"):
            style = (
                getattr(self, "_last_menu_style", "")
                or self.widgets_menu.styleSheet()
                or menu_style
            )
            self.overlay_manager.build_widgets_menu(self.widgets_menu, style)

    self.widgets_menu.aboutToShow.connect(_on_about_to_show)
    self.widgets_menu_btn.setEnabled(not bool(getattr(self, "is_locked", False)))

    self.widgets_menu_btn.setMenu(self.widgets_menu)
    top_bar.addWidget(self.widgets_menu_btn)
