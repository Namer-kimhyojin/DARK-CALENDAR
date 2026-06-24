from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se


def build_work_menu(self, top_bar, menu_btn_style, menu_style):
    self.view_menu_btn = QToolButton()
    self.view_menu_btn.setText(format_top_menu_button_text(t("menu.work_btn", "작업")))
    self.view_menu_btn.setIcon(_ic(ICON.ALL_SCHEDULES))
    self.view_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.view_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self.view_menu_btn.setStyleSheet(menu_btn_style)

    self.view_menu = QMenu(self)
    self.view_menu.setStyleSheet(menu_style)
    act_wm = self.view_menu.addAction(
        _se(t("menu.work_management")), self.open_work_management_dialog
    )
    act_wm.setIcon(_ic(ICON.ALL_SCHEDULES))
    self.view_menu.addSeparator()
    act_rs = self.view_menu.addAction(
        f"{_se(t('menu.routine_status'))}\t{get_key('routine_mgr')}",
        lambda: self.open_work_management_dialog(start_tab="routine"),
    )
    act_rs.setIcon(_ic(ICON.ROUTINE))
    act_ds = self.view_menu.addAction(
        _se(t("menu.directive_status")),
        lambda: self.open_work_management_dialog(start_tab="directive"),
    )
    act_ds.setIcon(_ic(ICON.DIRECTIVE))
    act_cl = self.view_menu.addAction(
        f"{_se(t('menu.checklist_mgmt'))}\t{get_key('checklist')}", self.open_checklist_manager
    )
    act_cl.setIcon(_ic(ICON.CHECKLIST))

    self.view_menu_btn.setMenu(self.view_menu)
    top_bar.addWidget(self.view_menu_btn)
