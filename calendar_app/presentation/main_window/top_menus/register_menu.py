from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se


def build_register_menu(self, top_bar, menu_btn_style, menu_style):
    self.add_menu_btn = QToolButton()
    self.add_menu_btn.setText(format_top_menu_button_text(t("menu.register_btn", "등록")))
    self.add_menu_btn.setIcon(_ic(ICON.ADD))
    self.add_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.add_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self.add_menu_btn.setStyleSheet(menu_btn_style)

    self.add_menu = QMenu(self)
    self.add_menu.setStyleSheet(menu_style)
    act_as = self.add_menu.addAction(
        f"{_se(t('menu.add_schedule'))}\t{get_key('new_schedule')}", self.open_task_dialog
    )
    act_as.setIcon(_ic(ICON.VIEW_CALENDAR))
    act_ad = self.add_menu.addAction(
        f"{_se(t('menu.add_directive'))}\t{get_key('new_directive')}", self.open_directive_dialog
    )
    act_ad.setIcon(_ic(ICON.DIRECTIVE))
    act_ar = self.add_menu.addAction(
        f"{_se(t('menu.add_routine'))}\t{get_key('new_routine')}", self.open_routine_add_dialog
    )
    act_ar.setIcon(_ic(ICON.ROUTINE))

    self.add_menu_btn.setMenu(self.add_menu)
    top_bar.addWidget(self.add_menu_btn)
