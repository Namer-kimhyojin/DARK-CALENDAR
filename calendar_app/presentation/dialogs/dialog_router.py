# -*- coding: utf-8 -*-
"""Dialog-related action handlers mixin."""

import logging
import re
import time

from PyQt6.QtWidgets import QMessageBox
from calendar_app.app_metadata import APP_AUTHOR, APP_EMAIL, APP_NAME, APP_VERSION
from calendar_app.infrastructure.i18n import i18n, t


logger = logging.getLogger(__name__)


_DIALOG_ROUTE_MAP = {
    "task_dialog": "open_task_dialog",
    "work_management_dialog": "open_work_management_dialog",
    "task_management_dialog": "open_task_management_dialog",
    "directive_management_dialog": "open_directive_management_dialog",
    "routine_management_dialog": "open_routine_management_dialog",
    "gcal_settings_dialog": "open_gcal_settings_dialog",
    "gcal_sync_issues_dialog": "open_gcal_sync_issues_dialog",
    "modify_task_dialog": "open_modify_task_dialog",
    "directive_dialog": "open_directive_dialog",
    "routine_add_dialog": "open_routine_add_dialog",
    "focus_log_dialog": "open_focus_log_dialog",
    "checklist_manager_dialog": "open_checklist_manager",
}


def route_dialog(app, dialog_key: str, *args, **kwargs):
    """Route a dialog key to the corresponding app dialog opener method."""
    if app is None:
        logger.warning("route_dialog called with app=None key=%s", dialog_key)
        return None

    key = str(dialog_key or "").strip()
    method_name = _DIALOG_ROUTE_MAP.get(key, key)
    target = getattr(app, method_name, None)

    # Fallback: when a method name is given without "open_" prefix.
    if target is None and key and not key.startswith("open_"):
        alt_method = f"open_{key}"
        target = getattr(app, alt_method, None)
        if callable(target):
            method_name = alt_method

    if not callable(target):
        logger.error("route_dialog target not found: key=%s method=%s", key, method_name)
        return None

    try:
        return target(*args, **kwargs)
    except Exception:
        logger.exception("route_dialog failed: key=%s method=%s", key, method_name)
        raise


def _current_lang() -> str:
    return str(getattr(i18n, "lang", "en") or "en")


def _default_shortcut_guide_title() -> str:
    lang = _current_lang().lower()
    if lang.startswith("ko"):
        return f"{APP_NAME} 단축키 가이드"
    if lang.startswith("ja"):
        return f"{APP_NAME} ショートカットガイド"
    if lang.startswith("th"):
        return f"{APP_NAME} คู่มือปุ่มลัด"
    if lang.startswith("zh"):
        return f"{APP_NAME} 快捷键指南"
    return f"{APP_NAME} Shortcut Guide"


def _default_shortcut_guide_content() -> str:
    lang = _current_lang().lower()
    
    # Common Content Generator to avoid redundancy
    def get_footer(v_label="버전", a_label="제작"):
        return f"""
            <hr>
            <div style="color:#888; font-size:11px;">
                <b>{APP_NAME}</b><br>
                {v_label}: {APP_VERSION}<br>
                {a_label}: {APP_AUTHOR} ({APP_EMAIL})
            </div>
        """

    if lang.startswith("ko"):
        return f"""
            <h3>단축키 가이드</h3>
            <hr>
            <b>[일정 관리]</b><br>
            • <b>Ctrl + N</b>: 새 일정 추가<br>
            • <b>Ctrl + R</b>: 일반업무 등록<br>
            • <b>Ctrl + D</b>: 지시사항 등록<br>
            • <b>Ctrl + L</b>: 체크리스트 템플릿 관리<br>
            • <b>Ctrl + Shift + L</b>: 바탕화면 고정 모드<br><br>

            <b>[화면 조작]</b><br>
            • <b>Ctrl + B</b>: 상단바 보이기/숨기기<br>
            • <b>Ctrl + Alt + B</b>: 캘린더 기능바 보이기/숨기기<br>
            • <b>Ctrl + M</b>: 자석 모드 토글<br>
            • <b>Ctrl + F / Space</b>: 초집중 모드 토글<br>
            • <b>Alt + W</b>: 즉시 자리비움 모드<br>
            • <b>Ctrl + 0</b>: 창 위치/크기 복원<br>
            • <b>F11</b>: 전체화면 토글<br>
            • <b>Ctrl + Alt + R</b>: 일반업무 주간 대시보드<br><br>

            <b>[레이아웃 프리셋]</b><br>
            • <b>Ctrl + Shift + 1~5</b>: 저장된 레이아웃 불러오기<br>
            • <b>Ctrl + Shift + S</b>: 현재 레이아웃 저장<br><br>

            <b>[네비게이션 & 투명도]</b><br>
            • <b>Ctrl + Left/Right</b>: 이전/다음 날짜 이동<br>
            • <b>Ctrl + T</b>: 오늘 날짜로 이동<br>
            • <b>Ctrl + [ / ]</b>: 투명도 조절 (내리기/올리기)<br>
            • <b>Delete</b>: 선택한 일정 삭제<br>
            • <b>Esc</b>: 선택 해제<br>
            • <b>F1</b>: 단축키 가이드 열기
            {get_footer()}
        """.strip()

    # Default (English)
    return f"""
        <h3>Shortcut Guide</h3>
        <hr>
        <b>[Schedule Management]</b><br>
        • <b>Ctrl + N</b>: Add New Schedule<br>
        • <b>Ctrl + R</b>: Register Routine<br>
        • <b>Ctrl + D</b>: Register Directive<br>
        • <b>Ctrl + L</b>: Manage Checklist Templates<br>
        • <b>Ctrl + Shift + L</b>: Desktop Lock Mode<br><br>

        <b>[Screen Operations]</b><br>
        • <b>Ctrl + B</b>: Show/Hide Top Bar<br>
        • <b>Ctrl + Alt + B</b>: Show/Hide Calendar Toolbar<br>
        • <b>Ctrl + M</b>: Toggle Magnet Mode<br>
        • <b>Ctrl + F / Space</b>: Toggle Focus Mode<br>
        • <b>Alt + W</b>: Instant Away Mode<br>
        • <b>Ctrl + 0</b>: Restore Window Position<br>
        • <b>F11</b>: Toggle Fullscreen<br>
        • <b>Ctrl + Alt + R</b>: Routine Weekly Dashboard<br><br>

        <b>[Layout Presets]</b><br>
        • <b>Ctrl + Shift + 1~5</b>: Load Layout Presets<br>
        • <b>Ctrl + Shift + S</b>: Save Current Layout<br><br>

        <b>[Navigation & Opacity]</b><br>
        • <b>Ctrl + Left/Right</b>: Prev/Next Date<br>
        • <b>Ctrl + T</b>: Jump to Today<br>
        • <b>Ctrl + [ / ]</b>: Adjust Opacity (Down/Up)<br>
        • <b>Delete</b>: Delete Selected Schedule<br>
        • <b>Esc</b>: Clear Selection<br>
        • <b>F1</b>: Open Shortcut Guide
        {get_footer("Version", "Author")}
    """.strip()


def _default_calendar_help_title() -> str:
    return "How to Use Calendar"


def _default_calendar_help_content() -> str:
    return """
        <h3>How to Use Calendar</h3>
        <hr>
        <b>1) Add Schedule</b><br>
        Double-click a date or press <b>Ctrl + N</b>.<br><br>

        <b>2) Modify Schedule</b><br>
        Double-click a schedule to edit details.<br><br>

        <b>3) Delete Schedule</b><br>
        Select a schedule and press <b>Delete</b>.<br><br>

        <b>4) Navigation</b><br>
        Use <b>Ctrl + Arrow Keys</b> to change dates rapidly.
    """.strip()


class DialogActionsMixin:
    """Mixin providing dialog-opening action methods for the main window."""

    # ------------------------------------------------------------------
    # Guard: prevent duplicate dialogs opened within 500ms
    # ------------------------------------------------------------------
    def _acquire_dialog_guard(self, key: str) -> bool:
        if not hasattr(self, "_dialog_guards"):
            self._dialog_guards = {}
        now = time.monotonic()
        last = self._dialog_guards.get(key, 0.0)
        if now - last < 0.5:
            return False
        self._dialog_guards[key] = now
        return True

    # ------------------------------------------------------------------
    # Schedule / Task dialogs
    # ------------------------------------------------------------------
    def open_task_dialog(self, initial_date=None, task_type=None, end_date=None):
        from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
        dlg = UnifiedTaskDialog(self, initial_date=initial_date, task_type=task_type, end_date=end_date)
        if dlg.exec():
            self.schedule_panel_refresh(left=True, center=True)

    def open_modify_task_dialog(self, task_id, tab_index=0):
        from PyQt6.QtWidgets import QDialog
        from calendar_app.presentation.dialogs.modify_task_dialog_unified import UnifiedModifyTaskDialog

        if not self._acquire_dialog_guard(f"open_modify_task_dialog:{task_id}"):
            return

        try:
            dlg = UnifiedModifyTaskDialog(task_id, self)
            if hasattr(dlg, "tabs") and tab_index > 0:
                dlg.tabs.setCurrentIndex(tab_index)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._refresh_all_panels()
                if self.settings.value("gcal_enabled", "true") == "true":
                    from calendar_app.infrastructure.db import task_repo as _task_repo
                    from calendar_app.infrastructure.google_sync.helpers import sync_task_to_google
                    from calendar_app.shared.background_worker import DbTaskWorker
                    task = _task_repo.get_unified_task(task_id)
                    if task:
                        worker = DbTaskWorker(lambda t=task: sync_task_to_google(self, t, create_if_missing=True))
                        if not hasattr(self, "_bg_workers"):
                            self._bg_workers = []
                        self._bg_workers.append(worker)
                        worker.task_done.connect(
                            lambda _w=worker: self._bg_workers.remove(_w) if _w in self._bg_workers else None
                        )
                        worker.start()
        except Exception:
            logger.exception("open_modify_task_dialog failed for task_id=%s", task_id)

    # ------------------------------------------------------------------
    # Work management (tabbed) dialogs
    # ------------------------------------------------------------------
    def open_work_management_dialog(self, start_tab="schedule"):
        from calendar_app.presentation.dialogs.management_dialogs import WorkManagementTabbedDialog
        dlg = WorkManagementTabbedDialog(self, start_tab=start_tab)
        dlg.exec()
        self.schedule_panel_refresh(left=True, center=True, right=True)

    def open_task_management_dialog(self):
        from calendar_app.presentation.dialogs.management_dialogs import TaskManagementDialog
        dlg = TaskManagementDialog(self)
        dlg.exec()
        self.schedule_panel_refresh(left=True, center=True)

    def open_directive_management_dialog(self):
        from calendar_app.presentation.dialogs.management_dialogs import DirectiveManagementDialog
        dlg = DirectiveManagementDialog(self)
        dlg.exec()
        self.schedule_panel_refresh(right=True)

    def open_routine_management_dialog(self):
        from calendar_app.presentation.dialogs.management_dialogs import RoutineManagementDialog
        dlg = RoutineManagementDialog(self)
        dlg.exec()
        self.schedule_panel_refresh(right=True)

    # ------------------------------------------------------------------
    # Register dialogs
    # ------------------------------------------------------------------
    def open_directive_dialog(self, task_id=None):
        from calendar_app.presentation.dialogs.directive_dialog import DirectiveDialog
        dlg = DirectiveDialog(self, task_id=task_id)
        if dlg.exec():
            self.schedule_panel_refresh(right=True)

    def open_routine_add_dialog(self):
        from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
        dlg = UnifiedTaskDialog(self, task_type="routine")
        if dlg.exec():
            self.schedule_panel_refresh(right=True)

    # ------------------------------------------------------------------
    # Checklist / Focus log
    # ------------------------------------------------------------------
    def open_checklist_manager(self):
        from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import ChecklistManagerDialog
        dlg = ChecklistManagerDialog(self)
        dlg.exec()

    def open_focus_log_dialog(self):
        try:
            from calendar_app.presentation.dialogs.focus_task_selector import FocusTaskSelectorDialog
            dlg = FocusTaskSelectorDialog(self)
            dlg.exec()
        except Exception:
            logger.exception("open_focus_log_dialog failed")

    # ------------------------------------------------------------------
    # Help / Info
    # ------------------------------------------------------------------
    def show_shortcut_guide(self):
        from PyQt6.QtCore import Qt
        title = t("dialog.shortcut_guide.title") or _default_shortcut_guide_title()
        content = t("dialog.shortcut_guide.content") or _default_shortcut_guide_content()
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(content)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()

    def show_calendar_help(self):
        from PyQt6.QtCore import Qt
        title = t("dialog.calendar_help.title") or _default_calendar_help_title()
        content = t("dialog.calendar_help.content") or _default_calendar_help_content()
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(content)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()

    # ------------------------------------------------------------------
    # Language settings (tray shortcut)
    # ------------------------------------------------------------------
    def open_language_settings_dialog(self):
        import json
        import os
        from PyQt6.QtWidgets import QInputDialog
        locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(__file__))))), "locales")
        lang_names = []
        lang_codes = []
        if os.path.exists(locales_dir):
            filenames = sorted(f for f in os.listdir(locales_dir) if f.endswith(".json"))
            all_codes = {f[:-5] for f in filenames}
            for filename in filenames:
                code = filename[:-5]
                if code == "zh" and ("zh-CN" in all_codes or "zh-TW" in all_codes):
                    continue
                try:
                    with open(os.path.join(locales_dir, filename), "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    name = data.get("meta", {}).get("language_name", code)
                except Exception:
                    name = code
                lang_names.append(name)
                lang_codes.append(code)
        if not lang_codes:
            return
        current = self.settings.value("language", "ko")
        current_idx = lang_codes.index(current) if current in lang_codes else 0
        chosen, ok = QInputDialog.getItem(
            self,
            t("menu.language", "언어"),
            t("dialog.language.prompt", "언어를 선택하세요:"),
            lang_names,
            current_idx,
            False,
        )
        if ok and chosen:
            idx = lang_names.index(chosen)
            self.set_language(lang_codes[idx])
