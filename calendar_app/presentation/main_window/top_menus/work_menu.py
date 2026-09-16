from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import (
    format_top_menu_button_text,
    set_themed_icon,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import strip_leading_emoji as _se


def build_work_menu(self, top_bar, menu_btn_style, menu_style):
    icon_color = getattr(self, "_tb_icon_color", "#f4f7fb")
    self.view_menu_btn = QToolButton()
    self.view_menu_btn.setText(format_top_menu_button_text(t("menu.work_btn", "작업")))
    set_themed_icon(self.view_menu_btn, ICON.ALL_SCHEDULES, icon_color)
    self.view_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.view_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self.view_menu_btn.setStyleSheet(menu_btn_style)

    self.view_menu = QMenu(self)
    self.view_menu.setStyleSheet(menu_style)
    act_wm = self.view_menu.addAction(
        _se(t("menu.work_management")), self.open_work_management_dialog
    )
    set_themed_icon(act_wm, ICON.ALL_SCHEDULES, icon_color)
    self.view_menu.addSeparator()
    act_rs = self.view_menu.addAction(
        f"{_se(t('menu.routine_status'))}\t{get_key('routine_mgr')}",
        lambda: self.open_work_management_dialog(start_tab="routine"),
    )
    set_themed_icon(act_rs, ICON.ROUTINE, icon_color)
    act_ds = self.view_menu.addAction(
        _se(t("menu.directive_status")),
        lambda: self.open_work_management_dialog(start_tab="directive"),
    )
    set_themed_icon(act_ds, ICON.DIRECTIVE, icon_color)
    act_cl = self.view_menu.addAction(
        f"{_se(t('menu.checklist_mgmt'))}\t{get_key('checklist')}", self.open_checklist_manager
    )
    set_themed_icon(act_cl, ICON.CHECKLIST, icon_color)

    self.view_menu_btn.setMenu(self.view_menu)
    top_bar.addWidget(self.view_menu_btn)
