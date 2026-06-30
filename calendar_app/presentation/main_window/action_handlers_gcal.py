"""Google Calendar 동기화 관련 액션 핸들러 Mixin"""

import datetime
import logging
import os

from PyQt6.QtCore import QThread, pyqtSlot
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.infrastructure.google_sync.engine import SYNC_OUTCOME_FAILED, SYNC_OUTCOME_SKIPPED
from calendar_app.infrastructure.i18n import t
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

logger = logging.getLogger(__name__)


class GCalActionsMixin:
    def _sync_worker_running(self):
        worker = getattr(self, "_sync_worker", None)

        if worker is None:
            return False

        try:
            return worker.isRunning()

        except RuntimeError:
            self._sync_worker = None

            return False

    def _release_sync_worker(self, *args):
        self._sync_worker = None

    def _auth_worker_running(self):
        worker = getattr(self, "_auth_worker", None)

        if worker is None:
            return False

        try:
            return worker.isRunning()

        except RuntimeError:
            self._auth_worker = None

            return False

    def _release_auth_worker(self, *args):
        self._auth_worker = None

    def _on_auth_finished(self, success, message):
        self.update_sync_status()

        if not success:
            return

        self._gcal_subscription_events_cache = {}

        if hasattr(self, "schedule_panel_refresh"):
            self.schedule_panel_refresh(center=True)

    def init_gcal_sync_timer(self):
        from PyQt6.QtCore import QTimer

        self._ensure_refresh_scheduler()

        self._gcal_sync_failures = 0

        self._gcal_quick_interval_secs = 15

        self.gcal_sync_timer = QTimer(self)

        self.gcal_sync_timer.timeout.connect(self.sync_google_calendar_silent)

        self.gcal_quick_sync_timer = QTimer(self)

        self.gcal_quick_sync_timer.timeout.connect(self.sync_google_calendar_silent)

        # 검색 디바운스 타이머

        self.search_debounce_timer = QTimer(self)

        self.search_debounce_timer.setSingleShot(True)

        self.search_debounce_timer.setInterval(300)

        self.search_debounce_timer.timeout.connect(self._exec_search_refresh)

        # ICS 구독 1시간 타이머

        self.ics_sync_timer = QTimer(self)

        self.ics_sync_timer.setInterval(60 * 60 * 1000)  # 1시간

        self.ics_sync_timer.timeout.connect(self._sync_ics_calendars)

        self.ics_sync_timer.start()

        # 앱 시작 시 한 번 즉시 실행

        QTimer.singleShot(5000, self._sync_ics_calendars)

        self.update_gcal_sync_timer()

    def update_gcal_sync_timer(self):
        interval_mins = int(self.settings.value("gcal_sync_interval", "10"))

        enabled = is_gcal_enabled(self.settings)

        quick_interval_secs = self.settings.value("gcal_quick_sync_interval", "30")

        try:
            quick_interval_secs = int(quick_interval_secs)

        except (TypeError, ValueError):
            quick_interval_secs = 30

        quick_interval_secs = max(5, quick_interval_secs)

        self._gcal_quick_interval_secs = quick_interval_secs

        quick_interval_ms = self._effective_quick_sync_interval_ms()

        if enabled and interval_mins > 0:
            self.gcal_sync_timer.start(interval_mins * 60 * 1000)

            self.gcal_quick_sync_timer.start(quick_interval_ms)

        else:
            self.gcal_sync_timer.stop()

            self.gcal_quick_sync_timer.stop()

            if hasattr(self, "_sync_anim_timer") and self._sync_anim_timer.isActive():
                self._sync_anim_timer.stop()

    def _effective_quick_sync_interval_ms(self):
        base_secs = max(5, int(getattr(self, "_gcal_quick_interval_secs", 15)))

        failures = max(0, int(getattr(self, "_gcal_sync_failures", 0)))

        multiplier = min(16, 2**failures)

        return min(base_secs * 1000 * multiplier, 5 * 60 * 1000)

    def _reset_gcal_failure_backoff(self):
        self._gcal_sync_failures = 0

        if is_gcal_enabled(self.settings) and hasattr(self, "gcal_quick_sync_timer"):
            self.gcal_quick_sync_timer.start(self._effective_quick_sync_interval_ms())

    def _increase_gcal_failure_backoff(self):
        self._gcal_sync_failures = min(int(getattr(self, "_gcal_sync_failures", 0)) + 1, 6)

        failures = self._gcal_sync_failures

        if is_gcal_enabled(self.settings) and hasattr(self, "gcal_quick_sync_timer"):
            if failures >= 4:
                # 연속 4회 이상 실패 → quick timer 및 sleep poll timer 완전 정지

                self.gcal_quick_sync_timer.stop()

                logger.warning(
                    "GCal quick sync paused after %d consecutive failures. Will retry via slow timer.",
                    failures,
                )

            else:
                interval_ms = self._effective_quick_sync_interval_ms()

                self.gcal_quick_sync_timer.start(interval_ms)

                logger.info(
                    "GCal quick sync backoff: next in %.0fs (failures=%d)",
                    interval_ms / 1000,
                    failures,
                )

    def rotate_sync_icon(self):
        """동기화 중 아이콘 애니메이션 효과"""

        if not hasattr(self, "_sync_rot_idx"):
            self._sync_rot_idx = 0

        if hasattr(self, "sync_status_lbl"):
            from PyQt6.QtWidgets import QLabel

            lbl = self.sync_status_lbl
            if isinstance(lbl, QLabel):
                lbl.setPixmap(_ic(ICON.SYNC).pixmap(16, 16))
            else:
                lbl.setIcon(_ic(ICON.SYNC))
                lbl.setText("")

            self._sync_rot_idx += 1

    def refresh_gcal_sync_state(self, authenticate_silently=True):
        """구글 동기화 상태 갱신 (백그라운드 워커 사용)"""

        import os

        from calendar_app.app_paths import TOKEN_PATH
        from calendar_app.shared.background_worker import AuthWorker

        if authenticate_silently and os.path.exists(TOKEN_PATH):
            if self._auth_worker_running():
                return

            worker = AuthWorker(self)

            self._auth_worker = worker

            worker.result_ready.connect(self._on_auth_finished)

            worker.finished.connect(self._release_auth_worker)

            worker.start()

            return True  # 워커 시작됨

        else:
            return self.refresh_gcal_sync_state_internal(authenticate_silently)

    def refresh_gcal_sync_state_internal(self, authenticate_silently=True, update_ui=True):
        """실제 인증 및 서비스 객체 생성 로직 (워커나 직접 호출에서 사용)"""

        enabled = is_gcal_enabled(self.settings)

        _raw_cal = str(self.settings.value("gcal_calendar_id", "") or "").strip()
        if not _raw_cal or _raw_cal == "primary":
            from calendar_app.infrastructure.google_sync.common import get_default_gcal_calendar_id

            _raw_cal = get_default_gcal_calendar_id()
        cal_id = _raw_cal

        tz = self.settings.value("gcal_timezone", "Asia/Seoul")

        if not enabled:
            if hasattr(self, "gcal_sync") and self.gcal_sync:
                self.gcal_sync.is_authenticated = False

                self.gcal_sync.service = None

            self.gcal_sync = None

            if update_ui:
                self.update_gcal_sync_timer()

                self.update_sync_status()

            return False

        try:
            import os

            from calendar_app.app_paths import TOKEN_PATH
            from calendar_app.infrastructure.google_sync.service import (
                prepare_calendar_sync_service,
            )

            self.gcal_sync = prepare_calendar_sync_service(
                getattr(self, "gcal_sync", None),
                calendar_id=cal_id,
                time_zone=tz,
            )

            if authenticate_silently and os.path.exists(TOKEN_PATH):
                self.gcal_sync.authenticate(interactive=False)

        except Exception:
            if hasattr(self, "gcal_sync") and self.gcal_sync:
                self.gcal_sync.is_authenticated = False

                self.gcal_sync.service = None

            logger.exception("Failed to refresh Google sync state")

        if update_ui:
            self.update_gcal_sync_timer()

            self.update_sync_status()

            if getattr(self, "gcal_sync", None) and getattr(
                self.gcal_sync, "is_authenticated", False
            ):
                self._gcal_subscription_events_cache = {}

                if hasattr(self, "schedule_panel_refresh"):
                    self.schedule_panel_refresh(center=True)

                # 인증 성공 직후 calendar access_role을 갱신한다.
                # 이렇게 해야 앱 재시작 후 첫 sync 실행 전에도 read-only 판단이 정확하다.
                if authenticate_silently:
                    self._refresh_calendar_access_roles_bg()

        return bool(self.gcal_sync and getattr(self.gcal_sync, "is_authenticated", False))

    def _refresh_calendar_access_roles_bg(self):
        """인증 직후 백그라운드에서 calendar 목록을 조회해 access_role을 DB에 반영한다."""
        from calendar_app.shared.background_worker import DbTaskWorker

        def _work():
            try:
                from calendar_app.infrastructure.google_sync.engine import (
                    _refresh_calendar_list_from_google,
                )

                _refresh_calendar_list_from_google(self)
            except Exception:
                logger.exception("_refresh_calendar_access_roles_bg failed")

        worker = DbTaskWorker(_work)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)
        worker.task_done.connect(
            lambda _w=worker: self._bg_workers.remove(_w) if _w in self._bg_workers else None
        )
        worker.start()

    def notify_gcal_setup_needed(self, disabled=False):
        title = t("gcal.setup_guide_title", "동기화 안내")
        if disabled:
            message = t(
                "gcal.setup_disabled_guide",
                "Google Calendar 동기화가 아직 켜져 있지 않습니다.\n시스템 > 캘린더 통합 설정에서 사용을 켜고 인증해 주세요.",
            )
        else:
            message = t(
                "gcal.setup_needed_msg",
                "Google Calendar 동기화가 아직 설정되지 않았습니다.\n시스템 > 캘린더 통합 설정에서 인증을 완료해 주세요.",
            )
            if "인증" not in message:
                message = f"{message}\n" + t(
                    "gcal.setup_needed_auth_hint",
                    "캘린더 통합 설정에서 Google 인증을 완료해 주세요.",
                )
        QMessageBox.information(self, title, message)

    def _manual_sync_setup_state(self):
        from calendar_app.app_paths import CREDENTIALS_PATH, TOKEN_PATH

        if not is_gcal_enabled(self.settings):
            return "disabled"

        sync = getattr(self, "gcal_sync", None)
        if sync is not None and getattr(sync, "is_authenticated", False):
            return None

        has_token = os.path.exists(TOKEN_PATH)
        has_credentials = os.path.exists(CREDENTIALS_PATH)
        if not has_token and not has_credentials:
            return "not_configured"
        return None

    def notify_gcal_disabled(self):
        self.notify_gcal_setup_needed(disabled=True)

    def set_gcal_sync_enabled(self, enabled, show_message=True):
        enabled = bool(enabled)

        self.settings.setValue("gcal_enabled", "true" if enabled else "false")

        authenticated = self.refresh_gcal_sync_state(authenticate_silently=enabled)

        # Keep UI/data visibility consistent with integration state immediately.
        if hasattr(self, "schedule_panel_refresh"):
            self.schedule_panel_refresh(left=True, center=True)

        if enabled and hasattr(self, "sync_google_calendar_silent"):
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(300, self.sync_google_calendar_silent)

        if show_message:
            if enabled and authenticated:
                QMessageBox.information(
                    self,
                    t("gcal.setup_done", "설정 완료"),
                    t("gcal.setup_success", "구글 동기화가 성공적으로 활성화되었습니다."),
                )

            elif enabled:
                QMessageBox.information(
                    self,
                    t("gcal.setup_guide_title", "설정 안내"),
                    t(
                        "gcal.setup_guide_msg",
                        "구글 동기화 기능이 활성화되었습니다.\n인증을 거쳐 동기화를 시작해 주세요.",
                    ),
                )

            else:
                self.notify_gcal_disabled()

    def toggle_gcal_sync_enabled(self, checked=False):
        self.set_gcal_sync_enabled(checked, show_message=True)

    def wake_gcal_sync(self):
        """로컬 변경(등록/수정/삭제/이동) 직후 GCal 동기화를 즉시 트리거한다.

        연속 작업을 묶기 위해 짧은 디바운스를 적용한다. 마지막 변경 후 한 번만
        sync_google_calendar_silent를 호출하여 중복 푸시를 방지한다.
        """
        if getattr(self, "_is_shutting_down", False):
            return
        if not is_gcal_enabled(self.settings):
            return

        from PyQt6.QtCore import QTimer

        if not hasattr(self, "_wake_sync_timer"):
            self._wake_sync_timer = QTimer(self)
            self._wake_sync_timer.setSingleShot(True)
            self._wake_sync_timer.timeout.connect(self.sync_google_calendar_silent)
        self._wake_sync_timer.start(800)

    def sync_google_calendar_silent(self):
        """조용한 자동 동기화 (알림창 띄우지 않음)"""

        if getattr(self, "_is_shutting_down", False):
            return

        if is_gcal_enabled(self.settings):
            from calendar_app.shared.background_worker import SyncWorker

            if self._sync_worker_running():
                return

            self._sync_worker = SyncWorker(self, silent=True)

            self._sync_worker.result_ready.connect(self._on_sync_finished)

            self._sync_worker.finished.connect(self._release_sync_worker)

            self._sync_worker.start()

            self.update_sync_status()

    def sync_google_calendar(self, silent=False):
        if getattr(self, "_is_shutting_down", False):
            return

        if not silent:
            setup_state = self._manual_sync_setup_state()
            if setup_state == "disabled":
                self.notify_gcal_setup_needed(disabled=True)
                return
            if setup_state == "not_configured":
                self.notify_gcal_setup_needed(disabled=False)
                return

        if not is_gcal_enabled(self.settings):
            if not silent:
                self.notify_gcal_setup_needed(disabled=True)

            return

        if not hasattr(self, "gcal_sync") or self.gcal_sync is None:
            self.refresh_gcal_sync_state(authenticate_silently=True)

        from calendar_app.shared.background_worker import SyncWorker

        if self._sync_worker_running():
            if not silent:
                QMessageBox.information(
                    self,
                    t("gcal.sync_in_progress", "동기화 진행 중"),
                    t("gcal.sync_already_running", "이미 구글 동기화가 진행 중입니다."),
                )

            return

        self._sync_worker = SyncWorker(self, silent=silent)

        self._sync_worker.result_ready.connect(
            self._on_sync_finished_manual if not silent else self._on_sync_finished
        )

        self._sync_worker.finished.connect(self._release_sync_worker)

        self._sync_worker.start()

        self.update_sync_status()

    def _handle_gcal_sync_success(self):
        """GCal 동기화 성공 시 공통 처리 (자동/수동 공유).

        Returns:

            bool: 변경이 감지됐으면 True (패널 갱신 필요 여부).

        """

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.settings.setValue("last_successful_sync", now_str)

        self._reset_gcal_failure_backoff()

        stats = getattr(self, "_last_gcal_sync_stats", {}) or {}
        auto_healed = stats.get("auto_healed", 0)
        if auto_healed > 0 and hasattr(self, "show_toast"):
            self.show_toast(
                t("gcal.auto_healed_title", "동기화 자동 수정"),
                t(
                    "gcal.auto_healed_msg",
                    "{count}건의 문제성 일정이 성공적으로 자동 복구되어 설정하신 캘린더에 동기화되었습니다.",
                    count=auto_healed,
                ),
            )

        changed = getattr(self, "_last_gcal_sync_changed_any", False)
        return changed

    def _on_sync_finished(self, success, message):
        """동기화 완료 후 콜백 (자동/일반)"""
        self.update_sync_status()
        if success:
            self._handle_gcal_sync_success()
            self._sync_ics_calendars()
            self.schedule_panel_refresh(center=True)
        else:
            outcome = getattr(self, "_last_gcal_sync_outcome", None)
            if outcome == "skipped":
                logger.debug("GCal sync skipped: %s", message)
            else:
                self._increase_gcal_failure_backoff()

                if outcome == SYNC_OUTCOME_FAILED:
                    logger.warning("GCal Sync Failure: %s", message)

                else:
                    generic_localized = t(
                        "gcal.worker.sync_skipped_or_failed", "Sync failed or skipped"
                    )

                    if message == generic_localized:
                        logger.warning(
                            "GCal Sync Failure: sync skipped or failed (localized=%r)",
                            message,
                        )

                    else:
                        logger.warning("GCal Sync Failure: %s", message)

    def _on_sync_finished_manual(self, success, message):
        """수동 동기화 완료 후 콜백"""
        stats = getattr(self, "_last_gcal_sync_stats", {}) or {}
        if success:
            self._handle_gcal_sync_success()
        self.update_sync_status()

        from PyQt6.QtWidgets import QApplication

        for win in QApplication.topLevelWidgets():
            if (
                win.__class__.__name__ == "GCalSyncIssuesDialog"
                and win.isVisible()
                and hasattr(win, "load_rows")
            ):
                win.load_rows()

        if success:
            if stats.get("push_failures") or stats.get("delete_failures"):
                QMessageBox.warning(
                    self,
                    t("gcal.sync_warning", "Sync Warning"),
                    (
                        t("gcal.sync_success_msg", "Successfully synced with Google Calendar.")
                        + "\n"
                        + message
                    ),
                )

            else:
                QMessageBox.information(
                    self,
                    t("gcal.sync_success", "Sync Complete"),
                    t("gcal.sync_success_msg", "Successfully synced with Google Calendar."),
                )

            if getattr(self, "_last_gcal_sync_changed_any", False):
                self.schedule_panel_refresh(
                    left=getattr(self, "_last_gcal_sync_refresh_left", False),
                    center=True,
                )

        elif message:
            outcome = getattr(self, "_last_gcal_sync_outcome", None)

            if outcome == SYNC_OUTCOME_SKIPPED:
                return

            self._increase_gcal_failure_backoff()

            QMessageBox.warning(self, t("gcal.sync_failed", "Sync Failed"), message)

            self._show_sync_issue_popup(message)

    def _show_sync_issue_popup(self, message):
        """Show a proactive alarm-style popup for sync issues."""

        if not message or getattr(self, "_sync_issue_popup_active", False):
            return

        from datetime import datetime

        from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow

        fake_task = {
            "id": -99,
            "type": "sync_issue",
            "name": t("alarm_popup.sync_issue", "동기화 이슈"),
            "location": t(
                "alarm_popup.sync_error_details", "동기화 중 오류가 발생했습니다: {error}"
            ).replace("{error}", str(message)),
        }

        popup = AlarmPopupWindow(
            task=fake_task,
            deadline_dt=datetime.now(),
            on_open_task=lambda tid: self.open_gcal_sync_issues_dialog(),
            parent=None,
        )

        self._sync_issue_popup_active = True

        popup.destroyed.connect(lambda: setattr(self, "_sync_issue_popup_active", False))

        popup.show()

    def _sync_ics_calendars(self):
        """ICS 구독 캘린더를 백그라운드에서 fetch하여 DB에 저장합니다."""

        try:
            from calendar_app.infrastructure.ics.ics_fetcher import sync_all_ics_calendars

            results = sync_all_ics_calendars()

            if any(r[0] > 0 or r[1] > 0 for r in results.values()) and hasattr(
                self, "schedule_panel_refresh"
            ):
                self.schedule_panel_refresh(center=True)

        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"ICS sync error: {e}")

    def open_gcal_settings_dialog(self, initial_tab: str | None = None):
        from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog

        dlg = GCalSettingsDialog(self, initial_tab=initial_tab)

        if dlg.exec():
            self.refresh_gcal_sync_state(authenticate_silently=True)

            self.schedule_panel_refresh(center=True)

    def open_gcal_sync_issues_dialog(self, checked=False):
        from calendar_app.presentation.dialogs.gcal_sync_issues_dialog import GCalSyncIssuesDialog

        dlg = GCalSyncIssuesDialog(self)

        dlg.exec()

    @pyqtSlot()
    def update_sync_status(self):
        """구글 동기화 상태 및 마지막 동기화 시간 업데이트"""

        if not hasattr(self, "sync_status_lbl"):
            return

        from PyQt6.QtCore import QMetaObject, QTimer
        from PyQt6.QtCore import Qt as QtCoreQt

        if QApplication.instance().thread() != QThread.currentThread():
            QMetaObject.invokeMethod(
                self, "update_sync_status", QtCoreQt.ConnectionType.QueuedConnection
            )

            return

        sync_button = getattr(self, "sync_action_btn", None)

        status_text_lbl = getattr(self, "sync_status_text_lbl", None)

        enabled = is_gcal_enabled(self.settings)

        authenticated = (
            hasattr(self, "gcal_sync")
            and self.gcal_sync is not None
            and self.gcal_sync.is_authenticated
        )

        syncing = getattr(self, "_gcal_sync_in_progress", False)

        sync_issue_count = 0

        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            sync_issue_count = (
                _task_repo.count_unified_task_gcal_errors()
                + _task_repo.count_gcal_delete_queue_errors()
                + _task_repo.count_gcal_sync_conflicts()
            )

        except Exception:
            sync_issue_count = 0

        last_sync = self.settings.value("last_successful_sync", t("gcal.last_sync_none"))

        tooltip_suffix = (
            f"\n{t('gcal.tooltip.last_sync', time=last_sync)}"
            if last_sync != t("gcal.last_sync_none")
            else ""
        )

        if syncing:
            icon_text = ""
            status_qicon = _ic(ICON.SYNC)

            icon_color = self.settings.value("theme_color", "#4da6ff")

            status_text = t("gcal.status.syncing", "동기화 중")

            tooltip = t("gcal.tooltip.syncing", "구글 캘린더와 데이터를 주고받는 중입니다...")

            if not hasattr(self, "_sync_anim_timer"):
                self._sync_anim_timer = QTimer(self)

                self._sync_anim_timer.timeout.connect(self.rotate_sync_icon)

            if not self._sync_anim_timer.isActive():
                self._sync_anim_timer.start(250)

        else:
            if hasattr(self, "_sync_anim_timer"):
                self._sync_anim_timer.stop()

            if enabled and authenticated and sync_issue_count > 0:
                icon_text = ""
                status_qicon = _ic(ICON.WARNING)

                icon_color = "#ff9d4d"

                status_text = t("gcal.status.warning", "Sync Warning")

                tooltip = (
                    t("gcal.tooltip.warning", "There are unresolved sync conflicts or failures.")
                    + f"\n{t('gcal.tooltip.issue_count', count=sync_issue_count)}"
                    + tooltip_suffix
                )

            elif enabled and authenticated:
                icon_text = ""
                status_qicon = _ic(ICON.CLOUD)

                icon_color = self.settings.value("theme_color", "#4da6ff")

                status_text = t("gcal.status.active", "동기화 활성")

                tooltip = (
                    t(
                        "gcal.tooltip.active",
                        "구글 캘린더와 연동되어 있습니다. 주기적으로 자동 동기화됩니다.",
                    )
                    + tooltip_suffix
                )

            elif enabled:
                icon_text = ""
                status_qicon = _ic(ICON.AUTH)

                icon_color = "#ff9d4d"

                status_text = t("gcal.status.auth_needed", "인증 필요")

                tooltip = t(
                    "gcal.tooltip.auth_needed",
                    "구글 동기화가 설정되었으나 인증 정보가 아직 없습니다.",
                )

            else:
                icon_text = ""
                status_qicon = _ic(ICON.BLOCKED)

                icon_color = "#777777"

                status_text = t("gcal.status.disconnected", "연동 해제")

                tooltip = t(
                    "gcal.tooltip.disconnected", "구글 연동 기능을 사용하지 않는 상태입니다."
                )

        status_icon_widget = sync_button if sync_button is not None else self.sync_status_lbl

        if self.sync_status_lbl is not status_icon_widget:
            self.sync_status_lbl.hide()

            self.sync_status_lbl.setFixedWidth(0)

            self.sync_status_lbl.setMaximumWidth(0)

        base_pt = QApplication.instance().font().pointSize()

        if base_pt <= 0:
            base_pt = 10

        style = f"font-size: {base_pt}pt; font-weight: bold; margin-right: 4px; background: transparent; border: none;"

        text_pt = max(8, base_pt - 1)

        text_style = f"font-size: {text_pt}pt; font-weight: bold; margin-right: 8px; background: transparent; border: none;"

        status_icon_widget.setText(icon_text)

        from PyQt6.QtWidgets import QLabel as _QLabel

        if isinstance(status_icon_widget, _QLabel):
            status_icon_widget.setPixmap(status_qicon.pixmap(16, 16))
        else:
            status_icon_widget.setIcon(status_qicon)

        status_icon_widget.setStyleSheet(f"color: {icon_color}; {style}")

        status_icon_widget.setToolTip(tooltip)

        if sync_button is not None:
            sync_button.setIcon(status_qicon)
            sync_button.setText(icon_text)

            sync_button.setToolTip(tooltip)

            sync_button.setStyleSheet(
                f"""

                QToolButton {{

                    color: {icon_color};

                    background: transparent;

                    border: none;

                    font-size: {base_pt}pt;

                    font-weight: bold;

                    margin-right: 4px;

                    padding: 2px 6px;

                }}

                QToolButton:hover {{

                    background: rgba(255, 255, 255, 24);

                    border-radius: 6px;

                }}

                """
            )

        if status_text_lbl is not None:
            status_text_lbl.setText(status_text)

            status_text_lbl.setStyleSheet(f"color: {icon_color}; {text_style}")

            status_text_lbl.setToolTip(tooltip)

    def check_first_time_setup(self):
        """Mark the setup guide as seen without showing a startup modal."""

        if self.settings.value("gcal_setup_wizard_shown", None) is None:
            self.settings.setValue("gcal_setup_wizard_shown", "true")
