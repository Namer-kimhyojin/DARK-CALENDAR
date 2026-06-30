"""UI actions and window event handlers used by the main window."""

import json
import logging
import time

from PyQt6.QtCore import QDateTime, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.theme.style_builder import (
    build_global_stylesheet,
    build_tooltip_stylesheet,
)
from calendar_app.shared.color_utils import derive_text_palette, parse_hex_color
from calendar_app.shared.theme_settings import get_opacity_byte, set_opacity_byte
from calendar_app.shared.theme_snapshot import build_theme_snapshot

logger = logging.getLogger(__name__)


def build_ui_font(family, size):
    from PyQt6.QtGui import QFont, QFontDatabase

    available_families = set(QFontDatabase.families())
    fallback_family = (
        QApplication.instance().font().family() if QApplication.instance() else "Segoe UI"
    )
    safe_family = (
        family if family in available_families or not available_families else fallback_family
    )

    font = QFont()
    font.setFamily(safe_family)
    if size is None or size <= 0:
        size = 10
    else:
        size = max(1, size)
    font.setPointSize(size)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferOutline
        | QFont.StyleStrategy.PreferAntialias
        | QFont.StyleStrategy.PreferQuality
    )
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


class MainWindowUiActionsMixin:
    def apply_layout_preset(self, index: int) -> None:
        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            apply_layout_preset,
        )

        apply_layout_preset(self, index)

    # ------------------------------------------------------------------
    # Overlay widget manager (multi-instance)
    # ------------------------------------------------------------------

    def init_overlay_manager(self):
        """Create the OverlayWidgetManager and restore saved instances."""
        if getattr(self, "overlay_manager", None) is not None:
            return
        from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager

        self.overlay_manager = OverlayWidgetManager(self)
        self.overlay_manager.restore_all()

        # Register app data provider for template variables like {task_count}
        self.overlay_manager.set_app_data_provider(self._get_overlay_app_data)

        # 진짜 첫 실행(저장된 키 없음)에만 기본 위젯 생성 — 사용자가 모두 삭제한 경우 제외
        if not self.overlay_manager.all_instances() and not getattr(
            self.overlay_manager, "_had_saved_instances", False
        ):
            self.overlay_manager.add_instance("clock")
            self.overlay_manager.add_instance("stopwatch")
            self.overlay_manager.add_instance("date_card")
            self.overlay_manager.add_instance("countdown")
            self.overlay_manager.add_instance("text")

        # Start timers for time-varying types
        self._ensure_stopwatch_timer()
        self._ensure_countdown_timer()
        self._ensure_slow_text_timer()

    def open_widget_manager(self):
        """위젯 관리자 다이얼로그를 열거나 이미 열려 있으면 앞으로 가져온다."""
        from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog

        self.init_overlay_manager()

        existing = getattr(self, "_widget_manager_dlg", None)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                # C++ 객체가 이미 삭제된 경우 — 참조를 초기화하고 새로 생성
                self._widget_manager_dlg = None

        dlg = OverlayManagerDialog(self.overlay_manager, parent=self)
        self._widget_manager_dlg = dlg
        dlg.destroyed.connect(lambda: setattr(self, "_widget_manager_dlg", None))
        dlg.show()  # non-modal — 메인 창 조작하면서 동시에 사용 가능

    def create_dday_widget_for_task(self, task_id: int):
        from PyQt6.QtCore import QDate

        from calendar_app.infrastructure.db import task_repo

        self.init_overlay_manager()

        task = task_repo.get_unified_task(task_id)
        if not task:
            if hasattr(self, "show_toast"):
                self.show_toast(
                    t("widget.dday.toast_title", "D-Day Widget"),
                    t("widget.dday.toast_task_missing", "Could not find the selected schedule."),
                )
            return

        raw_deadline = str(task.get("deadline") or task.get("target_date") or "").strip()
        target_date = QDate.fromString(raw_deadline[:10], "yyyy-MM-dd")
        if not target_date.isValid():
            if hasattr(self, "show_toast"):
                self.show_toast(
                    t("widget.dday.toast_title", "D-Day Widget"),
                    t("widget.dday.toast_no_date", "This schedule does not have a valid date."),
                )
            return

        task_name = str(task.get("name") or "").strip() or t("widget.dday.default_name", "D-Day")
        inst_id = self.overlay_manager.add_instance("dday", name=f"D-Day · {task_name}")
        widget = self.overlay_manager.get_widget(inst_id)
        if widget is None:
            return

        widget._set("dd_target_date", target_date.toString("yyyy-MM-dd"))
        widget._set("dd_label", task_name)
        widget._refresh_face()
        widget._apply_and_resize()
        self.overlay_manager.show_instance(inst_id)
        widget.center_on_owner()

        if hasattr(self, "show_toast"):
            self.show_toast(
                t("widget.dday.toast_title", "D-Day Widget"),
                t(
                    "widget.dday.toast_created",
                    "Created a D-Day widget for '{name}'.",
                    name=task_name,
                ),
            )

    def _ensure_stopwatch_timer(self):
        if getattr(self, "_stopwatch_timer", None) is None:
            self._stopwatch_elapsed_ms = float(
                self.settings.value("stopwatch_elapsed_ms", 0.0) or 0.0
            )
            self._stopwatch_running = self.settings.value("stopwatch_running", False, type=bool)
            self._stopwatch_started_at = time.monotonic() if self._stopwatch_running else None
            self._stopwatch_timer = QTimer(self)
            self._stopwatch_timer.timeout.connect(self._refresh_stopwatch_widgets)
            self._stopwatch_timer.start(100)

    def _ensure_countdown_timer(self):
        if getattr(self, "_countdown_timer", None) is None:
            self._countdown_timer = QTimer(self)
            self._countdown_timer.timeout.connect(self._refresh_countdown_widgets)
            self._countdown_timer.start(1000)

    def _ensure_slow_text_timer(self):
        """60-second timer for slow-tier text template vars ({date}, {task_count}, etc.)."""
        if getattr(self, "_slow_text_timer", None) is None:
            self._slow_text_timer = QTimer(self)
            self._slow_text_timer.timeout.connect(self._refresh_slow_text_widgets)
            self._slow_text_timer.start(60_000)

    # ------------------------------------------------------------------
    # Stopwatch shared state (timer/controls apply to ALL stopwatch instances)
    # ------------------------------------------------------------------

    def _current_stopwatch_elapsed_ms(self):
        base = float(getattr(self, "_stopwatch_elapsed_ms", 0.0) or 0.0)
        if (
            getattr(self, "_stopwatch_running", False)
            and getattr(self, "_stopwatch_started_at", None) is not None
        ):
            return base + max(0.0, (time.monotonic() - self._stopwatch_started_at) * 1000.0)
        return base

    def _format_stopwatch_elapsed(self, elapsed_ms: float):
        total_seconds = max(0.0, elapsed_ms) / 1000.0
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        tenths = int((elapsed_ms % 1000) // 100)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}.{tenths:d}"

    def _refresh_stopwatch_widgets(self):
        mgr = getattr(self, "overlay_manager", None)
        if mgr is not None:
            # Fast-tier: {stopwatch:id} and {time} variables in text widgets
            # Individual stopwatch widgets self-manage their own display.
            mgr.refresh_all_texts("", "", tier="fast")

    def toggle_stopwatch_running(self):
        self._ensure_stopwatch_timer()
        if getattr(self, "_stopwatch_running", False):
            self._stopwatch_elapsed_ms = self._current_stopwatch_elapsed_ms()
            self._stopwatch_running = False
            self._stopwatch_started_at = None
        else:
            self._stopwatch_running = True
            self._stopwatch_started_at = time.monotonic()
        self.settings.setValue("stopwatch_elapsed_ms", self._stopwatch_elapsed_ms)
        self.settings.setValue("stopwatch_running", self._stopwatch_running)
        self._refresh_stopwatch_widgets()

    def reset_stopwatch(self):
        self._ensure_stopwatch_timer()
        self._stopwatch_elapsed_ms = 0.0
        self._stopwatch_running = False
        self._stopwatch_started_at = None
        self.settings.setValue("stopwatch_elapsed_ms", 0.0)
        self.settings.setValue("stopwatch_running", False)
        self._refresh_stopwatch_widgets()

    # ------------------------------------------------------------------
    # Countdown shared state (target applies to ALL countdown instances)
    # ------------------------------------------------------------------

    def _countdown_target_dt(self):
        raw = str(self.settings.value("countdown_target_iso", "") or "").strip()
        if not raw:
            return None
        dt = QDateTime.fromString(raw, Qt.DateFormat.ISODate)
        return dt if dt.isValid() else None

    def _format_countdown_remaining(self):
        target = self._countdown_target_dt()
        if target is None:
            return "--:--:--", t("menu.countdown_no_target", "목표 시각 없음")
        now = QDateTime.currentDateTime()
        secs = now.secsTo(target)
        if secs < 0:
            return "00:00:00", t("menu.countdown_done", "카운트다운 종료")
        hours = secs // 3600
        mins = (secs % 3600) // 60
        seconds = secs % 60
        days = secs // 86400
        target_str = target.toString("yyyy-MM-dd HH:mm")
        if days > 0:
            remaining_after_days = secs - days * 86400
            h2 = remaining_after_days // 3600
            m2 = (remaining_after_days % 3600) // 60
            s2 = remaining_after_days % 60
            time_str = f"{h2:02d}:{m2:02d}:{s2:02d}"
            return time_str, t(
                "menu.countdown_d_days",
                "D-{days} remaining ({target})",
                days=days,
                target=target_str,
            )
        return f"{hours:02d}:{mins:02d}:{seconds:02d}", target_str

    def _refresh_countdown_widgets(self):
        mgr = getattr(self, "overlay_manager", None)
        if mgr is not None:
            # Med-tier: {countdown:id} variables in text widgets
            # Individual countdown widgets self-manage their own display.
            mgr.refresh_all_texts("", "", tier="med")

    def _refresh_slow_text_widgets(self):
        """Refresh text widgets that use slow-tier variables ({date}, {task_count}, etc.)."""
        mgr = getattr(self, "overlay_manager", None)
        if mgr is None:
            return
        # Slow-tier: {date}, {weekday}, {task_count}, {directive_count}, {next_event}, {custom_var}, {dday:id}
        # countdown_remaining and stopwatch_text come from individual widget instances via registry.
        mgr.refresh_all_texts("", "", tier="slow")

    def _get_overlay_app_data(self) -> dict:
        """Collect app data for text template variables."""
        data: dict = {}
        try:
            from calendar_app.application import task_usecases
            from calendar_app.infrastructure.db import search_repo as db_search

            today = getattr(self, "current_date", None)
            if today is not None:
                date_str = today.toString("yyyy-MM-dd")
                tasks = task_usecases.get_tasks_for_date(db_search, date_str)
                data["task_count"] = len(tasks) if tasks else 0
                # next event: first task with a time component in deadline field
                # deadline format: "yyyy-MM-dd HH:mm" or "yyyy-MM-dd HH:mm:ss"
                timed = [
                    t for t in (tasks or []) if t.get("deadline") and len(str(t["deadline"])) > 10
                ]
                if timed:
                    timed.sort(key=lambda t: str(t.get("deadline", "")))
                    first = timed[0]
                    task_name = first.get("name") or ""
                    dl = str(first.get("deadline", ""))
                    time_part = dl[11:16] if len(dl) >= 16 else ""  # HH:MM
                    data["next_event"] = (
                        f"{time_part} {task_name}".strip() if time_part else task_name
                    )
                else:
                    data["next_event"] = "—"
        except Exception:
            data.setdefault("task_count", 0)
            data.setdefault("next_event", "—")

        try:
            from calendar_app.infrastructure.db import directive_repo as db_directive

            directives = db_directive.get_recent_directives(limit=500)
            # rows are tuples: (id, content, status, receiver, deadline, ...)
            # status index=2; count those not in completed/deferred states
            _done_statuses = {
                "done",
                "completed",
                "canceled",
                "cancelled",
                "deferred",
                "완료",
                "취소",
            }
            active = [
                d
                for d in (directives or [])
                if len(d) >= 3 and str(d[2] or "").lower() not in _done_statuses
            ]
            data["directive_count"] = len(active)
        except Exception:
            data.setdefault("directive_count", 0)

        # custom_var from settings
        data["custom_var"] = str(self.settings.value("overlay_custom_var", "") or "")
        # Allow sub-keys: custom_var_key1, custom_var_key2 (set by user via settings)
        try:
            prefix = "overlay_custom_var_"
            for key in self.settings.allKeys():
                if str(key).startswith(prefix):
                    sub = str(key)[len(prefix) :]
                    data[f"custom_var_{sub}"] = str(self.settings.value(key, "") or "")
        except Exception:
            pass

        return data

    def set_countdown_target(self):
        from PyQt6.QtCore import QTime
        from PyQt6.QtWidgets import (
            QCalendarWidget,
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QSpinBox,
            QVBoxLayout,
        )

        from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

        current_dt = self._countdown_target_dt()
        now = QDateTime.currentDateTime()
        initial = current_dt if (current_dt and current_dt.isValid()) else now

        dlg = QDialog(self)
        apply_dialog_title(dlg, t("menu.countdown_set_target", "카운트다운 목표 시각"))
        apply_common_dialog_style(dlg, minimum_width=340, size=(420, 390))

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Calendar
        cal = QCalendarWidget(dlg)
        cal.setGridVisible(True)
        cal.setSelectedDate(initial.date())
        layout.addWidget(cal)

        # Time row
        time_row = QHBoxLayout()
        time_row.addStretch()
        time_row.addWidget(QLabel(t("menu.countdown_time_label", "Time:")))

        hour_spin = QSpinBox(dlg)
        hour_spin.setRange(0, 23)
        hour_spin.setValue(initial.time().hour())
        hour_spin.setWrapping(True)
        hour_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hour_spin.setFixedWidth(78)
        time_row.addWidget(hour_spin)

        colon = QLabel(":")
        theme = str(self.settings.value("theme_color", "#4da6ff"))
        colon.setStyleSheet(f"font-size: 16pt; font-weight: bold; color: {theme};")
        time_row.addWidget(colon)

        min_spin = QSpinBox(dlg)
        min_spin.setRange(0, 59)
        min_spin.setValue(initial.time().minute())
        min_spin.setWrapping(True)
        min_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        min_spin.setFixedWidth(78)
        time_row.addWidget(min_spin)

        time_row.addStretch()
        layout.addLayout(time_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = btns.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText(t("dialog.common.apply", "적용"))
            ok_btn.setObjectName("PrimaryBtn")
        if cancel_btn is not None:
            cancel_btn.setText(t("common.cancel", "취소"))
            cancel_btn.setObjectName("SecondaryBtn")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        result = QDateTime(cal.selectedDate(), QTime(hour_spin.value(), min_spin.value()))
        self.settings.setValue("countdown_target_iso", result.toString(Qt.DateFormat.ISODate))
        self._refresh_countdown_widgets()

    def clear_countdown_target(self):
        self.settings.remove("countdown_target_iso")
        self._refresh_countdown_widgets()

    # ------------------------------------------------------------------
    # Panel color helpers (unchanged)
    # ------------------------------------------------------------------

    def _normalize_hex_color(self, color_hex, fallback="#1c1c1c"):
        from PyQt6.QtGui import QColor

        return parse_hex_color(str(color_hex), fallback).name(QColor.NameFormat.HexRgb)

    def _get_recent_panel_colors(self):
        raw = self.settings.value("panel_base_color_recent", "[]")
        try:
            items = json.loads(str(raw))
        except Exception:
            items = []
        out = []
        for item in items:
            hx = self._normalize_hex_color(item)
            if hx not in out:
                out.append(hx)
            if len(out) >= 5:
                break
        return out

    def _set_recent_panel_colors(self, colors):
        cleaned = []
        for c in colors:
            hx = self._normalize_hex_color(c)
            if hx not in cleaned:
                cleaned.append(hx)
            if len(cleaned) >= 5:
                break
        self.settings.setValue("panel_base_color_recent", json.dumps(cleaned))

    def _remember_panel_color(self, color_hex):
        hx = self._normalize_hex_color(color_hex)
        recent = [c for c in self._get_recent_panel_colors() if c != hx]
        recent.insert(0, hx)
        self._set_recent_panel_colors(recent)

    def apply_panel_background_color(self, color_hex, remember=True):
        hx = self._normalize_hex_color(color_hex)
        self.settings.setValue("panel_base_color", hx)
        if remember:
            self._remember_panel_color(hx)
        self._apply_panel_background_color_refresh()
        if hasattr(self, "update_panel_color_recent_menu"):
            self.update_panel_color_recent_menu()

    def _apply_panel_background_color_refresh(self):
        try:
            from calendar_app.presentation.main_window.top_bar_builder import (
                build_top_bar_frame_style,
            )

            if hasattr(self, "top_bar_frame") and self.top_bar_frame is not None:
                opacity_raw = get_opacity_byte(self.settings, persist_normalized=True)
                opacity_factor = max(0.0, min(1.0, opacity_raw / 255.0))
                self.top_bar_frame.setStyleSheet(
                    build_top_bar_frame_style(self.settings, opacity_factor)
                )
        except Exception:
            logger.exception("탑바 스타일 갱신 실패")
        try:
            if hasattr(self, "apply_theme_settings"):
                for widget in QApplication.allWidgets():
                    if widget.__class__.__name__ == "QMenu" and hasattr(self, "apply_menu_opacity"):
                        self.apply_menu_opacity(widget)
                self.apply_theme_settings()
                return
        except Exception:
            logger.exception("테마 설정 적용 실패, 패널 직접 리로드로 폴백")
        self._refresh_all_panels()

    def open_panel_background_color_dialog(self):
        from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
            PanelColorPickerDialog,
        )
        from calendar_app.shared.color_utils import derive_text_palette

        current_base = str(self.settings.value("panel_base_color", "#1a2236"))
        current_theme = str(self.settings.value("theme_color", "#4da6ff"))
        current_opacity = get_opacity_byte(self.settings, persist_normalized=True)
        current_border_opacity = int(self.settings.value("last_border_opacity", 80, type=int))
        current_text_opacity = int(self.settings.value("last_text_opacity", 255, type=int))

        current_text_theme = str(self.settings.value("text_theme", "dark"))
        _tpal = derive_text_palette(current_text_theme, current_theme)
        current_text_primary = str(
            self.settings.value("custom_text_primary", _tpal["text_primary"])
        )
        current_text_secondary = str(
            self.settings.value("custom_text_secondary", _tpal["text_secondary"])
        )
        current_text_muted = str(self.settings.value("custom_text_muted", _tpal["text_muted"]))
        current_text_faint = str(self.settings.value("custom_text_faint", _tpal["text_faint"]))
        current_input_bg = str(self.settings.value("custom_input_bg", "rgba(0,0,0,0.2)"))

        app_font = QApplication.instance().font()
        current_font_family = str(self.settings.value("font_family", app_font.family()))
        current_font_size = int(
            self.settings.value(
                "font_size", app_font.pointSize() if app_font.pointSize() > 0 else 10
            )
        )

        dlg = PanelColorPickerDialog(
            parent=self,
            current_base=current_base,
            current_theme=current_theme,
            current_opacity=current_opacity,
            current_border_opacity=current_border_opacity,
            current_text_opacity=current_text_opacity,
            current_text_primary=current_text_primary,
            current_text_secondary=current_text_secondary,
            current_text_muted=current_text_muted,
            current_text_faint=current_text_faint,
            current_text_theme=current_text_theme,
            current_input_bg=current_input_bg,
            current_font_family=current_font_family,
            current_font_size=current_font_size,
        )
        if dlg.exec() != PanelColorPickerDialog.DialogCode.Accepted:
            return

        new_base = dlg.selected_base_hex()
        new_opacity = dlg.selected_opacity()  # 0~255

        # 모든 설정값을 먼저 저장한 뒤 한 번만 갱신
        self.settings.setValue("panel_base_color", self._normalize_hex_color(new_base))
        self._remember_panel_color(new_base)

        if dlg.point_color_changed():
            self.settings.setValue("theme_color", dlg.selected_point_hex())

        set_opacity_byte(self.settings, new_opacity)
        self.settings.setValue("last_border_opacity", dlg.selected_border_opacity())
        self.settings.setValue("last_text_opacity", dlg.selected_text_opacity())
        if hasattr(self, "slider"):
            self.slider.blockSignals(True)
            self.slider.setValue(new_opacity)
            self.slider.blockSignals(False)

        self.settings.setValue("text_theme", dlg.selected_text_theme())
        if dlg.text_colors_changed():
            self.settings.setValue("custom_text_primary", dlg.text_primary_hex())
            self.settings.setValue("custom_text_secondary", dlg.text_secondary_hex())
            self.settings.setValue("custom_text_muted", dlg.text_muted_hex())
            self.settings.setValue("custom_text_faint", dlg.text_faint_hex())
            self.settings.setValue("custom_input_bg", dlg.selected_input_bg())

        if dlg.font_changed():
            family = dlg.selected_font_family()
            size = dlg.selected_font_size()
            self.settings.setValue("font_family", family)
            self.settings.setValue("font_size", size)
            self.apply_font_settings(family, size, refresh=False)

        # 모든 값이 저장된 후 한 번만 UI 갱신
        if hasattr(self, "apply_theme_settings"):
            self.apply_theme_settings()
        if hasattr(self, "update_panel_color_recent_menu"):
            self.update_panel_color_recent_menu()

    def open_dialog_token_editor_dialog(self):
        from PyQt6.QtWidgets import QDialog

        from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
            DialogTokenEditorDialog,
        )

        dlg = DialogTokenEditorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if hasattr(self, "apply_theme_settings"):
                self.apply_theme_settings()
            if hasattr(self, "show_toast"):
                self.show_toast(
                    t("theme.toast_title", "UI 테마"),
                    t(
                        "dialog.token_editor.saved_toast",
                        "다이얼로그 UI 토큰이 저장되었습니다. 재시작 후 전체 반영됩니다.",
                    ),
                )

    def open_text_color_dialog(self, role):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog

        role_map = {
            "primary": ("custom_text_primary", "menu.text_color_primary", "기본 글자색"),
            "secondary": ("custom_text_secondary", "menu.text_color_secondary", "보조 글자색"),
            "faint": ("custom_text_faint", "menu.text_color_faint", "옅은 글자색"),
        }
        if role not in role_map:
            return

        setting_key, label_key, fallback_label = role_map[role]
        theme_color = self.settings.value("theme_color", "#4da6ff")
        current_theme = self.settings.value("text_theme", "dark")
        pal = derive_text_palette(current_theme, theme_color)
        fallback_map = {
            "primary": pal["text_primary"],
            "secondary": pal["text_secondary"],
            "faint": pal["text_faint"],
        }
        initial = QColor(str(self.settings.value(setting_key, fallback_map[role])))
        if not initial.isValid():
            initial = QColor(str(fallback_map[role]))

        picked = QColorDialog.getColor(
            initial,
            self,
            t(label_key, fallback_label),
        )
        if not picked.isValid():
            return

        hx = picked.name(QColor.NameFormat.HexRgb)
        self.settings.setValue(setting_key, hx)
        if role == "secondary":
            self.settings.setValue("custom_text_muted", hx)
        self.change_text_theme("custom")

    def reset_custom_text_colors(self):
        for key in (
            "custom_text_primary",
            "custom_text_secondary",
            "custom_text_muted",
            "custom_text_faint",
        ):
            self.settings.remove(key)
        self.change_text_theme("dark")

    def reset_panel_background_color(self):
        self.settings.remove("panel_base_color")
        self._apply_panel_background_color_refresh()

    def clear_recent_panel_colors(self):
        self.settings.remove("panel_base_color_recent")
        if hasattr(self, "update_panel_color_recent_menu"):
            self.update_panel_color_recent_menu()

    def update_panel_color_recent_menu(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

        menu = getattr(self, "panel_bg_recent_menu", None)
        if menu is None:
            return

        menu.clear()
        recent = self._get_recent_panel_colors()
        if not recent:
            empty_act = menu.addAction(t("menu.panel_bg_recent_empty", "최근 색상 없음"))
            empty_act.setEnabled(False)
            return

        for hx in recent[:5]:
            pixmap = QPixmap(14, 14)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(hx))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 1, 12, 12, 2, 2)
            painter.end()
            icon = QIcon(pixmap)
            menu.addAction(
                icon, hx, lambda *_, c=hx: self.apply_panel_background_color(c, remember=True)
            )

        menu.addSeparator()
        menu.addAction(
            t("menu.panel_bg_recent_clear", "최근 색상 비우기"),
            self.clear_recent_panel_colors,
        )

    def open_font_settings_dialog(self):
        from PyQt6.QtWidgets import (
            QDialog,
            QFontComboBox,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

        dlg = QDialog(self)
        apply_dialog_title(dlg, t("dialog.font.title"))
        apply_common_dialog_style(dlg, minimum_width=380, size=(460, 250))

        layout = QVBoxLayout(dlg)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(t("dialog.font.label")))
        font_combo = QFontComboBox()
        font_combo.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        font_combo.setCurrentFont(QApplication.instance().font())
        row1.addWidget(font_combo, 1)
        layout.addLayout(row1)

        preview_lbl = QLabel(t("dialog.font.preview"))
        preview_lbl.setStyleSheet(
            "color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 8px; background: #14141c;"
        )
        layout.addWidget(preview_lbl)

        def update_preview():
            current_size = QApplication.instance().font().pointSize()
            if current_size <= 0:
                current_size = 10
            f = build_ui_font(font_combo.currentFont().family(), current_size)
            preview_lbl.setFont(f)

        font_combo.currentFontChanged.connect(lambda _: update_preview())
        update_preview()

        btn_row = QHBoxLayout()
        ok_btn = QPushButton(t("dialog.font.apply"))
        ok_btn.setObjectName("PrimaryBtn")
        cancel_btn = QPushButton(t("dialog.font.cancel"))
        cancel_btn.setObjectName("SecondaryBtn")
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            family = font_combo.currentFont().family()
            size = QApplication.instance().font().pointSize()
            if size <= 0:
                size = 10
            self.apply_font_settings(family, size)
            self.settings.setValue("font_family", family)
            self.settings.setValue("font_size", size)

    def apply_font_settings(self, family, size, refresh=True):
        if size <= 0:
            size = 10
        snapshot = build_theme_snapshot(self.settings, persist_opacity=True)
        font = build_ui_font(family, size)
        QApplication.instance().setFont(font)

        safe_size = font.pointSize() if font.pointSize() > 0 else (size if size > 0 else 10)
        QApplication.instance().setStyleSheet(
            build_tooltip_stylesheet(
                safe_size,
                snapshot.theme_color,
                snapshot.text_theme,
                snapshot.panel_base_color,
                snapshot.ui_palette,
            )
        )
        self.setStyleSheet(
            build_global_stylesheet(
                font.family(),
                safe_size,
                snapshot.theme_color,
                snapshot.text_theme,
                snapshot.panel_base_color,
                snapshot.ui_palette,
            )
        )

        if refresh:
            self._refresh_all_panels()

    def open_label_settings_dialog(self):
        from calendar_app.presentation.dialogs.label_settings_dialog import LabelSettingsDialog

        dlg = LabelSettingsDialog(self)
        if dlg.exec():
            self._refresh_all_panels()
