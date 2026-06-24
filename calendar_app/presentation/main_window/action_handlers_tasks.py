"""Task event interaction handlers mixin."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.application import task_delete_usecases, task_usecases
from calendar_app.infrastructure.db import checklist_repo as db_checklist
from calendar_app.infrastructure.db import directive_repo as db_directive
from calendar_app.infrastructure.db import legacy_task_repo as db_legacy_task
from calendar_app.infrastructure.db import search_repo as db_search
from calendar_app.infrastructure.db import task_repo as db_task
from calendar_app.infrastructure.google_sync.helpers import sync_task_to_google
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.color_swatch_widget import ColorSwatchPopup
from calendar_app.presentation.widgets.ui_components import DraggableTaskButton

logger = logging.getLogger(__name__)


class TaskActionsMixin:
    def _run_worker(self, worker, on_finished=None):
        """DbTaskWorker를 _bg_workers 리스트에 등록하고 시작."""
        from calendar_app.shared.background_worker import (
            DbTaskWorker,  # noqa: F401 (import for type reference)
        )

        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)
        if on_finished:
            worker.task_done.connect(on_finished)
        # deleteLater는 DbTaskWorker.__init__에서 QThread.finished에 이미 연결됨
        worker.task_done.connect(
            lambda: self._bg_workers.remove(worker) if worker in self._bg_workers else None
        )
        worker.start()

    def _select_google_palette_color(self, current_color=None):
        result = ColorSwatchPopup.pick(self, current_color)
        # None = cancelled, "" = clear, "#xxxxxx" = chosen color
        if result is None:
            return None
        return result or None  # convert "" → None so callers treat it as "no color"

    def update_task_selection_status(self):
        if not hasattr(self, "selection_status_lbl"):
            return

        count = (len(self.selected_task_ids) if hasattr(self, "selected_task_ids") else 0) + (
            len(self.selected_directive_ids) if hasattr(self, "selected_directive_ids") else 0
        )
        theme = (
            self.settings.value("theme_color", "#4da6ff")
            if hasattr(self, "settings")
            else "#4da6ff"
        )

        def hex_to_rgba(hex_color, alpha):
            hex_color = hex_color.lstrip("#")
            r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
            return f"rgba({r}, {g}, {b}, {alpha})"

        from PyQt6.QtGui import QFont as _QFont
        from PyQt6.QtWidgets import QApplication as _QApp

        lbl_font = _QFont("Segoe UI")
        lbl_font.setPointSize(max(6, _QApp.instance().font().pointSize() - 1))
        lbl_font.setBold(count > 0)
        self.selection_status_lbl.setFont(lbl_font)

        if count <= 0:
            text = t("panel.multiselect_guide")
            style = (
                "color: rgba(255,255,255,0.60); "
                "background: rgba(255,255,255,0.06); "
                "border: 1px solid rgba(255,255,255,0.12); "
                "border-radius: 10px; padding: 2px 12px;"
            )
        else:
            text = t("panel.n_selected", n=count)
            bg = hex_to_rgba(theme, 0.22)
            border = hex_to_rgba(theme, 0.5)
            style = (
                "color: white; "
                f"background-color: {bg}; "
                f"border: 1px solid {border}; "
                "border-radius: 10px; padding: 2px 12px;"
            )

        self.selection_status_lbl.setText(text)
        self.selection_status_lbl.setStyleSheet(style)

    def handle_task_added(self, task_data):
        # routine(일반업무)는 GCal 동기화 대상 아님 — schedule만 push
        _is_schedule = (task_data or {}).get("type", "schedule") != "routine"
        if task_data and _is_schedule and self.settings.value("gcal_enabled", "true") == "true":
            from calendar_app.shared.background_worker import DbTaskWorker

            worker = DbTaskWorker(
                lambda t=task_data: sync_task_to_google(self, t, create_if_missing=True)
            )
            self._run_worker(worker)
        self.schedule_panel_refresh(left=True, center=True, right=True)

    def handle_task_modified(self, modified_data):
        if task_usecases.apply_task_basic_modification(db_legacy_task, modified_data):
            self.schedule_panel_refresh(left=True, center=True)

    def handle_task_status_changed(self, task_id, status):
        """일정 상태 변경(완료/미완료)."""
        if task_usecases.update_task_status(db_task, task_id, status):
            self._refresh_all_panels()

    def handle_task_priority_changed(self, task_id, priority):
        """일정/일반업무 중요도 변경."""
        if task_usecases.update_task_priority(db_task, task_id, priority):
            self._refresh_all_panels()

    def handle_task_clicked(self, task_id, _modifiers=None):
        """Handle task click selection (Ctrl/Shift support)."""
        modifiers = _modifiers if _modifiers is not None else QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if task_id in self.selected_task_ids:
                self.selected_task_ids.remove(task_id)
            else:
                self.selected_task_ids.add(task_id)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.selected_task_ids.add(task_id)
        else:
            if not (task_id in self.selected_task_ids and len(self.selected_task_ids) > 1):
                self.selected_task_ids = {task_id}

        self._last_clicked_task_id = task_id
        self._update_selection_visuals()

    def _update_selection_visuals(self):
        """현재 화면의 일정 버튼 선택 상태를 갱신."""
        for btn in self.findChildren(DraggableTaskButton):
            btn.set_selected(btn.task_id in self.selected_task_ids)
        try:
            from calendar_app.presentation.panels.side_panel_renderer import (
                _refresh_panel_selection_visuals,
            )

            _refresh_panel_selection_visuals(self)
        except Exception:
            logger.exception("패널 선택 시각 갱신 실패")
        self.update_task_selection_status()

    def handle_cell_click(self, pack):
        """날짜 셀 클릭(날짜 선택)."""
        date = pack[0] if isinstance(pack, tuple) else pack
        self._last_clicked_date = date
        self.selected_task_ids.clear()
        if hasattr(self, "selected_directive_ids"):
            self.selected_directive_ids.clear()
        self.schedule_panel_refresh(center=True)
        self.update_task_selection_status()

    def handle_cell_shift_click(self, pack):
        """Shift+클릭으로 날짜 범위 선택 후 일정 추가."""
        end_d = pack[0] if isinstance(pack, tuple) else pack
        start_d = self._last_clicked_date if self._last_clicked_date else end_d

        if start_d > end_d:
            start_d, end_d = end_d, start_d

        self._last_clicked_date = end_d
        self.schedule_panel_refresh(center=True)
        self.open_task_dialog(start_d, None, end_d)

    def handle_task_dropped(self, task_id_list, target_date, target_time, action):
        from calendar_app.presentation import drag_drop_manager as ddm

        try:
            # handle_task_drop returns (changed_count, copied_ids)
            changed, copied_ids = ddm.handle_task_drop(
                self, task_id_list, target_date, target_time, action
            )

            # If gcal is enabled, push the changes (updates for move, creates for copy)
            if changed > 0 and self.settings.value("gcal_enabled", "true") == "true":
                from calendar_app.infrastructure.db import task_repo as _task_repo
                from calendar_app.shared.background_worker import DbTaskWorker

                # Determine which IDs to push to Google Calendar
                # If action is copy, we push the newly created copied_ids
                # If action is move, we push the original task_id_list
                push_ids = (
                    copied_ids if action == "copy" else [int(x) for x in (task_id_list or []) if x]
                )

                def _push_all_to_gcal(ids_to_sync=None):
                    for tid in ids_to_sync if ids_to_sync is not None else list(push_ids):
                        # Re-read task from DB to get the latest updated/copied data (e.g. new deadline)
                        task = _task_repo.get_unified_task(tid)
                        if task:
                            # sync_task_to_google will handle create (if new) or update (if exists)
                            sync_task_to_google(self, task, create_if_missing=True)
                    return True

                worker = DbTaskWorker(_push_all_to_gcal)
                self._run_worker(worker)

            # Trigger a general sync/refresh
            self.wake_gcal_sync()
        except Exception:
            logger.exception(
                "Unhandled error in handle_task_dropped task_ids=%s target_date=%s target_time=%s action=%s selected=%s",
                task_id_list,
                target_date,
                target_time,
                action,
                sorted(self.selected_task_ids) if hasattr(self, "selected_task_ids") else [],
            )
            if hasattr(self, "_is_dragging"):
                self._is_dragging = False

    def begin_inline_rename_for_selected_task(self):
        if len(self.selected_task_ids) != 1:
            return False

        target_id = next(iter(self.selected_task_ids))
        for btn in self.center_frame.findChildren(DraggableTaskButton):
            if btn.task_id == target_id and btn.isVisible():
                return btn.begin_inline_rename()
        return False

    def handle_task_rename_requested(self, task_id, new_name):
        from calendar_app.shared.background_worker import DbTaskWorker

        task = task_usecases.rename_task(db_task, task_id, new_name)
        if task:
            if self.settings.value("gcal_enabled", "true") == "true":
                worker = DbTaskWorker(
                    lambda: sync_task_to_google(self, task, create_if_missing=True)
                )
                self._run_worker(worker)

            self.wake_gcal_sync()
            self.schedule_panel_refresh(left=True, center=True, right=True)

    def auto_assign_color_tags_to_selection(self):
        """Apply auto color tags to the current mixed selection."""
        from PyQt6.QtCore import QSettings

        task_ids = sorted(
            int(v) for v in getattr(self, "selected_task_ids", set()) if str(v).isdigit()
        )
        directive_ids = sorted(
            int(v) for v in getattr(self, "selected_directive_ids", set()) if str(v).isdigit()
        )
        total_targets = len(task_ids) + len(directive_ids)
        if total_targets <= 0:
            return False

        theme = QSettings("kimhyojin", "Dark Calendar").value("theme_color", "#4da6ff")
        auto_colors = task_usecases.auto_assign_theme_colors(theme, total_targets)
        changed_task = False
        changed_directive = False

        for task_id, color_hex in zip(task_ids, auto_colors[: len(task_ids)], strict=False):
            if task_usecases.update_task_bg_color(db_task, task_id, color_hex):
                changed_task = True

        for directive_id, color_hex in zip(
            directive_ids, auto_colors[len(task_ids) :], strict=False
        ):
            if task_usecases.update_directive_bg_color(db_directive, directive_id, color_hex):
                changed_directive = True

        if changed_task:
            self._refresh_all_panels()
        elif changed_directive:
            self.mark_panel_dirty(right=True)
            self.schedule_panel_refresh(right=True)
        return changed_task or changed_directive

    def handle_color_change_requested(self, task_id):
        """일정 배경색 변경."""
        task = db_task.get_unified_task(task_id)
        color_hex = self._select_google_palette_color(task.get("bg_color") if task else None)
        if color_hex and db_task.update_unified_task(task_id, {"bg_color": color_hex}):
            self._refresh_all_panels()

    def handle_color_auto_assign_requested(self, task_id):
        """일정 배경색 자동 부여."""
        from PyQt6.QtCore import QSettings

        selected = getattr(self, "selected_task_ids", set())
        if (
            task_id in selected
            and len(selected) > 1
            and not getattr(self, "selected_directive_ids", set())
        ):
            self.auto_assign_color_tags_to_selection()
            return

        theme = QSettings("kimhyojin", "Dark Calendar").value("theme_color", "#4da6ff")
        auto_color = task_usecases.auto_assign_theme_color(theme)
        if task_usecases.update_task_bg_color(db_task, task_id, auto_color):
            self._refresh_all_panels()

    def handle_color_clear_requested(self, task_id):
        """일정/업무 색상 태그 제거."""
        if task_usecases.update_task_bg_color(db_task, task_id, None):
            self._refresh_all_panels()

    def handle_directive_color_change_requested(self, directive_id):
        """지시/협조사항 색상 태그 변경."""
        color_hex = self._select_google_palette_color()
        if not color_hex:
            return

        try:
            if task_usecases.update_directive_bg_color(db_directive, directive_id, color_hex):
                self.mark_panel_dirty(right=True)
                self.schedule_panel_refresh(right=True)
        except Exception:
            logger.exception("Error updating directive color tag for directive_id=%s", directive_id)

    def handle_directive_color_auto_assign_requested(self, directive_id):
        """지시/협조사항 색상 태그 자동 부여."""
        from PyQt6.QtCore import QSettings

        selected = getattr(self, "selected_directive_ids", set())
        if (
            directive_id in selected
            and len(selected) > 1
            and not getattr(self, "selected_task_ids", set())
        ):
            self.auto_assign_color_tags_to_selection()
            return

        theme = QSettings("kimhyojin", "Dark Calendar").value("theme_color", "#4da6ff")
        auto_color = task_usecases.auto_assign_theme_color(theme)
        try:
            if task_usecases.update_directive_bg_color(db_directive, directive_id, auto_color):
                self.mark_panel_dirty(right=True)
                self.schedule_panel_refresh(right=True)
        except Exception:
            logger.exception(
                "Error auto-assigning directive color tag for directive_id=%s", directive_id
            )

    def handle_directive_color_clear_requested(self, directive_id):
        """지시/협조사항 색상 태그 제거."""
        try:
            if task_usecases.update_directive_bg_color(db_directive, directive_id, None):
                self.mark_panel_dirty(right=True)
                self.schedule_panel_refresh(right=True)
        except Exception:
            logger.exception("Error clearing directive color tag for directive_id=%s", directive_id)

    def handle_checklist_requested(self, task_id):
        """체크리스트 탭으로 수정 다이얼로그 열기."""
        self.open_modify_task_dialog(task_id, tab_index=2)

    def handle_alarm_clear_requested(self, task_id):
        """알람 제거."""
        if task_usecases.clear_task_alarm(db_task, task_id):
            QMessageBox.information(self, t("dialog.alarm.title"), t("dialog.alarm.removed"))
            self._refresh_all_panels()

    def handle_task_deleted(self, task_id):
        """Delete task(s), supporting multi-selection."""
        target_ids = task_usecases.resolve_delete_target_ids(self.selected_task_ids, task_id)

        count = len(target_ids)
        if count > 1:
            msg = t("dialog.common.delete_n_confirm", n=count)
        else:
            msg = t("dialog.common.delete_confirm")
        msg += "\n" + t("dialog.common.delete_sub_msg")

        reply = QMessageBox.question(
            self,
            t("dialog.common.delete_title", "삭제 확인"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        from calendar_app.shared.background_worker import DbTaskWorker

        def run_delete():
            from calendar_app.infrastructure.google_sync.helpers import (
                queue_task_delete_from_google,
            )

            return task_delete_usecases.delete_tasks_with_google_queue(
                db_task,
                target_ids,
                queue_delete_fn=lambda event_id,
                local_task_id,
                gcal_calendar_id: queue_task_delete_from_google(
                    self,
                    event_id,
                    local_task_id=local_task_id,
                    gcal_calendar_id=gcal_calendar_id,
                ),
            )

        def on_delete_finished(success, result):
            if success and result and result > 0:
                self.selected_task_ids.clear()
                self.update_task_selection_status()
                self._refresh_all_panels()
                self.wake_gcal_sync()
                self.show_toast(
                    t("dialog.common.delete_done"), t("dialog.common.delete_toast_n", n=result)
                )
            elif not success:
                logger.error("Task delete worker failed: %s", result)
                if hasattr(self, "show_toast"):
                    self.show_toast(
                        t("dialog.task.save_failed", "실패"),
                        t("dialog.common.delete_error", "삭제 중 오류가 발생했습니다."),
                    )

        worker = DbTaskWorker(run_delete)
        self._run_worker(worker, on_delete_finished)

    def delete_selected_directives(self):
        """선택된 지시/협조사항 삭제 (Del 키 및 우클릭 메뉴에서 호출)."""
        if hasattr(self, "_is_text_input_focused") and self._is_text_input_focused():
            return
        selected = getattr(self, "selected_directive_ids", set())
        if not selected:
            return

        ids = list(selected)
        count = len(ids)
        msg = (
            t("dialog.common.delete_n_confirm", n=count)
            if count > 1
            else t("dialog.common.delete_confirm")
        )

        reply = QMessageBox.question(
            self,
            t("dialog.common.delete_title", "삭제 확인"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = db_directive.delete_directives(ids)
        if deleted:
            self.selected_directive_ids.clear()
            try:
                from calendar_app.presentation.panels.side_panel_renderer import (
                    _refresh_panel_selection_visuals,
                )

                _refresh_panel_selection_visuals(self)
            except Exception:
                logger.exception("지시사항 삭제 후 패널 선택 시각 갱신 실패")
            self.update_task_selection_status()
            self._refresh_all_panels()
            if hasattr(self, "show_toast"):
                toast_title = t("dialog.common.delete_done", "삭제 완료")
                toast_msg = t("dialog.common.delete_toast_n", "{n}개가 삭제되었습니다.").replace(
                    "{n}", str(deleted)
                )
                self.show_toast(toast_title, toast_msg)

    def _delete_selected_directives_without_prompt(self):
        selected = getattr(self, "selected_directive_ids", set())
        ids = [int(v) for v in selected]
        if not ids:
            return 0

        deleted = db_directive.delete_directives(ids)
        if deleted:
            self.selected_directive_ids.clear()
            try:
                from calendar_app.presentation.panels.side_panel_renderer import (
                    _refresh_panel_selection_visuals,
                )

                _refresh_panel_selection_visuals(self)
            except Exception:
                logger.exception("지시사항 일괄 삭제 후 패널 선택 시각 갱신 실패")
            self.update_task_selection_status()
        return int(deleted or 0)

    def delete_selected_items(self):
        if self._is_text_input_focused():
            return

        task_ids = [int(v) for v in getattr(self, "selected_task_ids", set())]
        directive_ids = [int(v) for v in getattr(self, "selected_directive_ids", set())]
        total_count = len(task_ids) + len(directive_ids)
        if total_count <= 0:
            return

        msg = (
            t("dialog.common.delete_n_confirm", n=total_count)
            if total_count > 1
            else t("dialog.common.delete_confirm")
        )
        msg += "\n" + t("dialog.common.delete_sub_msg")
        reply = QMessageBox.question(
            self,
            t("dialog.common.delete_title", "삭제 확인"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_directives = (
            self._delete_selected_directives_without_prompt() if directive_ids else 0
        )
        if not task_ids:
            self._refresh_all_panels()
            if deleted_directives > 0 and hasattr(self, "show_toast"):
                self.show_toast(
                    t("dialog.common.delete_done"),
                    t("dialog.common.delete_toast_n", n=deleted_directives),
                )
            return

        from calendar_app.shared.background_worker import DbTaskWorker

        def run_delete():
            from calendar_app.infrastructure.google_sync.helpers import (
                queue_task_delete_from_google,
            )

            return task_delete_usecases.delete_tasks_with_google_queue(
                db_task,
                task_ids,
                queue_delete_fn=lambda event_id,
                local_task_id,
                gcal_calendar_id: queue_task_delete_from_google(
                    self,
                    event_id,
                    local_task_id=local_task_id,
                    gcal_calendar_id=gcal_calendar_id,
                ),
            )

        def on_delete_finished(success, result):
            if success and result is not None:
                self.selected_task_ids.clear()
                self.update_task_selection_status()
                self._refresh_all_panels()
                self.wake_gcal_sync()
                deleted_total = int(result or 0) + deleted_directives
                if deleted_total > 0 and hasattr(self, "show_toast"):
                    self.show_toast(
                        t("dialog.common.delete_done"),
                        t("dialog.common.delete_toast_n", n=deleted_total),
                    )

        worker = DbTaskWorker(run_delete)
        self._run_worker(worker, on_delete_finished)

    def handle_task_resized(self, task_id, minutes):
        """일정 리사이즈 후 종료 시간을 갱신."""
        from calendar_app.shared.background_worker import DbTaskWorker

        task = task_usecases.resize_task_and_get_sync_payload(db_task, task_id, minutes)
        if task:
            worker = DbTaskWorker(lambda: sync_task_to_google(self, task, create_if_missing=True))
            self._run_worker(worker)
            self.wake_gcal_sync()
            self.selected_task_ids.clear()
            self.update_task_selection_status()
            self.schedule_panel_refresh(left=True, center=True)

    def delete_selected_tasks(self):
        if self._is_text_input_focused():
            return

        if self.selected_task_ids:
            self.handle_task_deleted(next(iter(self.selected_task_ids)))
            return

        clicked_date = getattr(self, "_last_clicked_date", None)
        if clicked_date:
            self.delete_all_tasks_on_date(clicked_date)

    def delete_all_tasks_on_date(self, target_date):
        """Delete all tasks on selected date."""
        date_str = (
            target_date.toString("yyyy-MM-dd")
            if hasattr(target_date, "toString")
            else str(target_date)
        )

        tasks = task_usecases.get_tasks_for_date(db_search, date_str)
        if not tasks:
            return

        count = len(tasks)
        msg = (
            t(
                "dialog.common.delete_all_date_msg",
                "<b>{date}</b>의 일정 <b>{count}개</b>를 모두 삭제하시겠습니까?<br>관련된 체크리스트도 함께 삭제됩니다.",
            )
            .replace("{date}", date_str)
            .replace("{count}", str(count))
        )
        reply = QMessageBox.question(
            self,
            t("dialog.common.delete_all_date_title", "날짜 일정 전체 삭제"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        from calendar_app.shared.background_worker import DbTaskWorker

        def run_delete():
            from calendar_app.infrastructure.google_sync.helpers import (
                queue_task_delete_from_google,
            )

            return task_delete_usecases.delete_tasks_on_date_with_google_queue(
                db_search,
                db_task,
                date_str,
                queue_delete_fn=lambda event_id,
                local_task_id,
                gcal_calendar_id: queue_task_delete_from_google(
                    self,
                    event_id,
                    local_task_id=local_task_id,
                    gcal_calendar_id=gcal_calendar_id,
                ),
            )

        def on_finished(success, result):
            if success and result and result > 0:
                self.selected_task_ids.clear()
                self.update_task_selection_status()
                self._refresh_all_panels()
                self.wake_gcal_sync()
                self.show_toast(
                    t("dialog.common.delete_done"), t("dialog.common.delete_toast_n", n=result)
                )

        worker = DbTaskWorker(run_delete)
        self._run_worker(worker, on_finished)

    def clear_task_selection(self):
        if not self.selected_task_ids:
            return
        self.selected_task_ids.clear()
        self._update_selection_visuals()

    def show_event_detail(self, task_id, task_name, deadline, priority, end_date):
        # 수정 다이얼로그로 대체됨(중복 팝업 방지)
        pass

    def handle_directive_status_changed(self, directive_id, new_status):
        """Change directive status."""
        try:
            if task_usecases.update_directive_status(db_directive, directive_id, new_status):
                self.schedule_panel_refresh(right=True)
        except Exception:
            logger.exception("Error updating directive status for directive_id=%s", directive_id)

    def handle_directive_priority_changed(self, directive_id, priority):
        """Change directive priority."""
        try:
            if task_usecases.update_directive_priority(db_directive, directive_id, priority):
                self.schedule_panel_refresh(right=True)
        except Exception:
            logger.exception("Error updating directive priority for directive_id=%s", directive_id)

    def toggle_checklist_item(self, link_id):
        if task_usecases.toggle_checklist_item(db_checklist, link_id):
            self._refresh_all_panels()

    def toggle_routine_step(self, step_id):
        self.toggle_checklist_item(step_id)

    def copy_subscription_to_local(self, task_row):
        """구독 일정을 로컬 일정으로 복사: 정보를 미리 채운 등록 다이얼로그를 팝업하여 사용자가 확인하도록 함."""
        if not task_row:
            return

        from PyQt6.QtCore import QDate, QDateTime, QTime

        # Parse start/end datetime
        start_raw = str(task_row.get("_start_raw") or task_row.get("deadline") or "").strip()
        end_raw = str(task_row.get("_end_raw") or task_row.get("end_date") or "").strip()
        _all_day = bool(task_row.get("all_day", False))

        start_d = QDate.currentDate()
        start_t = QTime(9, 0)
        end_d = None
        end_t = None

        if start_raw:
            # Try full datetime first
            dt = QDateTime.fromString(start_raw[:19].replace("T", " "), "yyyy-MM-dd HH:mm:ss")
            if not dt.isValid():
                dt = QDateTime.fromString(start_raw[:16].replace("T", " "), "yyyy-MM-dd HH:mm")

            if dt.isValid():
                start_d = dt.date()
                start_t = dt.time()
            else:
                d = QDate.fromString(start_raw[:10], "yyyy-MM-dd")
                if d.isValid():
                    start_d = d

        if end_raw:
            dt = QDateTime.fromString(end_raw[:19].replace("T", " "), "yyyy-MM-dd HH:mm:ss")
            if not dt.isValid():
                dt = QDateTime.fromString(end_raw[:16].replace("T", " "), "yyyy-MM-dd HH:mm")

            if dt.isValid():
                end_d = dt.date()
                end_t = dt.time()
            else:
                d = QDate.fromString(end_raw[:10], "yyyy-MM-dd")
                if d.isValid():
                    end_d = d

        prefill = {
            "name": task_row.get("name") or "",
            "memo": task_row.get("description") or "",
            "location": task_row.get("location") or "",
            "bg_color": task_row.get("bg_color"),
        }
        # open_task_dialog를 통해 다이얼로그 팝업 (사용자가 최종 '등록' 클릭 시 저장됨)
        # 이 방식이 사용자에게 명확한 '진입점(버튼)'과 '종료점(등록 완료)'을 제공함.
        if hasattr(self, "open_task_dialog"):
            self.open_task_dialog(
                initial_date=start_d,
                initial_time=start_t,
                end_date=end_d,
                end_time=end_t,
                prefill_dict=prefill,
            )
