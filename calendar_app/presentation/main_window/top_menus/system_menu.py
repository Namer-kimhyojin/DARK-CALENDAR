# -*- coding: utf-8 -*-

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.app_metadata import APP_LICENSE_URL, APP_RELEASE_SOURCE_URL
from calendar_app.infrastructure.i18n import get_locale_display_name, list_available_locale_codes, t
from calendar_app.infrastructure.runtime import system_manager
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

HOMEPAGE_URL = "https://namer-kimhyojin.github.io/dark_calendar/"


def _open_homepage():
    QDesktopServices.openUrl(QUrl(HOMEPAGE_URL))


def _open_external_url(url: str):
    QDesktopServices.openUrl(QUrl(url))


def build_system_menu(self, top_bar, menu_btn_style="", menu_style=""):
    self.sys_menu_btn = QToolButton()
    self.sys_menu_btn.setText(format_top_menu_button_text(t("menu.system", "시스템")))
    self.sys_menu_btn.setIcon(_ic(ICON.SETTINGS))
    self.sys_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.sys_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self.sys_menu_btn.setStyleSheet(menu_btn_style)

    self.sys_menu = QMenu(self)
    self.sys_menu.setStyleSheet(menu_style)

    # ── 윈도우 시작시 자동 실행 (최상단 고정) ──────────────────────────────────
    self.autostart_act = QAction(_se(t("menu.autostart")), self)
    self.autostart_act.setIcon(_ic(ICON.AUTOSTART))
    self.autostart_act.setCheckable(True)
    self.autostart_act.setChecked(system_manager.is_autostart_enabled())
    self.autostart_act.triggered.connect(self.toggle_autostart)
    self.sys_menu.addAction(self.autostart_act)
    self.sys_menu.addSeparator()

    # ── 환경 설정 ─────────────────────────────────────────────────────────────
    act_label = self.sys_menu.addAction(
        _se(t("menu.label_settings")), self.open_label_settings_dialog
    )
    act_label.setIcon(_ic(ICON.COLOR_PICKER))
    act_away = self.sys_menu.addAction(_se(t("menu.away_settings")), self.open_away_settings_dialog)
    act_away.setIcon(_ic(ICON.BREAK_LONG))
    self.sys_menu.addSeparator()

    # ── 구글 캘린더 서브메뉴 ──────────────────────────────────────────────────
    self.gcal_menu = self.sys_menu.addMenu(_se(t("menu.gcal_submenu", "캘린더 및 동기화")))
    self.gcal_menu.setIcon(_ic(ICON.GCAL))
    self.gcal_menu.setStyleSheet(menu_style)
    self.gcal_settings_act = self.gcal_menu.addAction(
        _se(t("menu.sync_account", "캘린더 통합 설정...")), self.open_gcal_settings_dialog
    )
    self.gcal_settings_act.setIcon(_ic(ICON.SYNC_SETTINGS))
    self.gcal_sync_issues_act = self.gcal_menu.addAction(
        _se(t("menu.sync_issues", "동기화 문제 보기")),
        self.open_gcal_sync_issues_dialog,
    )
    self.gcal_sync_issues_act.setIcon(_ic(ICON.WARNING))
    self.sys_menu.addSeparator()

    # 언어 서브메뉴
    self.lang_menu = self.sys_menu.addMenu(_se(t("menu.language", "언어 설정")))
    self.lang_menu.setIcon(_ic(ICON.LOCALE_MGMT))
    self.lang_menu.setStyleSheet(menu_style)

    current_lang = self.settings.value("language", "ko")

    lang_codes = sorted(list_available_locale_codes())
    lang_set = set(lang_codes)
    for lang_code in lang_codes:
        if lang_code == "zh" and ("zh-CN" in lang_set or "zh-TW" in lang_set):
            continue
        lang_name = get_locale_display_name(lang_code)
        act = QAction(lang_name, self)
        act.setCheckable(True)
        act.setChecked(current_lang == lang_code)
        act.triggered.connect(lambda checked, lc=lang_code: self.set_language(lc))
        self.lang_menu.addAction(act)

    self.sys_menu.addSeparator()
    self.locale_tools_menu = self.sys_menu.addMenu(_se(t("menu.locale_tools", "로케일 파일 관리")))
    self.locale_tools_menu.setIcon(_ic(ICON.LOCALE_MGMT))
    self.locale_tools_menu.setStyleSheet(menu_style)
    act_lf = self.locale_tools_menu.addAction(
        _se(t("menu.locale_open_folder", "사용자 로케일 폴더 열기")),
        self.open_locale_override_folder,
    )
    act_lf.setIcon(_ic(ICON.FOLDER))
    act_lc = self.locale_tools_menu.addAction(
        _se(t("menu.locale_open_current", "현재 언어 파일 열기")),
        self.open_current_locale_file,
    )
    act_lc.setIcon(_ic(ICON.LOCALE_FILE))
    act_lv = self.locale_tools_menu.addAction(
        _se(t("menu.locale_validate_current", "현재 언어 파일 검증")),
        self.validate_current_locale_override,
    )
    act_lv.setIcon(_ic(ICON.VALIDATE))
    act_lr = self.locale_tools_menu.addAction(
        _se(t("menu.locale_reset_current", "현재 언어 오버라이드 초기화")),
        self.reset_current_locale_override,
    )
    act_lr.setIcon(_ic(ICON.REFRESH))
    self.sys_menu.addSeparator()
    act_sc = self.sys_menu.addAction(
        f"{_se(t('menu.shortcuts'))}\t{get_key('help')}", self.show_shortcut_guide
    )
    act_sc.setIcon(_ic(ICON.TIP))
    act_home = self.sys_menu.addAction(
        _se(t("menu.homepage", "홈페이지 열기")),
        lambda: _open_homepage(),
    )
    act_home.setIcon(_ic(ICON.GLOBE))
    self.open_source_menu = self.sys_menu.addMenu(_se(t("menu.open_source_info", "오픈소스 정보")))
    self.open_source_menu.setIcon(_ic(ICON.INFO))
    self.open_source_menu.setStyleSheet(menu_style)
    act_source = self.open_source_menu.addAction(
        _se(t("menu.release_source_code", "이 버전의 GitHub 소스")),
        lambda: _open_external_url(APP_RELEASE_SOURCE_URL),
    )
    act_source.setIcon(_ic(ICON.GLOBE))
    act_license = self.open_source_menu.addAction(
        _se(t("menu.open_source_license", "GPLv3 오픈소스 라이선스")),
        lambda: _open_external_url(APP_LICENSE_URL),
    )
    act_license.setIcon(_ic(ICON.INFO))
    self.sys_menu.addSeparator()
    act_exit = self.sys_menu.addAction(_se(t("menu.exit")), self.request_app_exit)
    act_exit.setIcon(_ic(ICON.CLOSE))

    self.sys_menu_btn.setMenu(self.sys_menu)
    top_bar.addWidget(self.sys_menu_btn)
