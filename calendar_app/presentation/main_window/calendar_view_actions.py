# -*- coding: utf-8 -*-
"""Calendar/panel/context-menu view action mixin."""

import logging

from PyQt6.QtCore import QDate, QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.shared.calendar_display_settings import (
    WEEKDAY_DISPLAY_KEY,
    next_weekday_display_mode,
    normalize_weekday_display_mode,
    weekday_display_flags,
    weekday_display_mode_for,
)
from calendar_app.shared.theme_settings import wallpaper_opacity_floor
from calendar_app.shared.theme_snapshot import theme_cache_scope

logger = logging.getLogger(__name__)


def _show_only_layout_children(frame):
    """Show the frame's newly laid-out panel now and hide the replaced ones."""
    layout = frame.layout()
    for child in frame.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if not child.isWindow():
            child.setVisible(layout is not None and layout.indexOf(child) >= 0)


class _CenterPanelFirstShowWatch(QObject):
    """Builds the calendar when its frame is first shown, at its real height."""

    def __init__(self, host, parent):
        super().__init__(parent)
        self._host = host

    def eventFilter(self, obj, event):  # noqa: N802
        host = self._host
        if event.type() == QEvent.Type.Show and not getattr(host, "_center_panel_shown", False):
            host._center_panel_shown = True
            obj.removeEventFilter(self)
            if getattr(host, "_center_panel_render_deferred", False) and not getattr(
                host, "_is_shutting_down", False
            ):
                try:
                    host.load_center_panel(force=True)
                except Exception:
                    logger.exception("Deferred calendar render failed")
        return False


class _RightPanelShowWatch(QObject):
    """Builds a deferred right panel when one of its frames is shown."""

    def __init__(self, host, parent):
        super().__init__(parent)
        self._host = host

    def eventFilter(self, obj, event):  # noqa: N802
        host = self._host
        if (
            event.type() == QEvent.Type.Show
            and getattr(host, "_right_panel_render_deferred", False)
            # The app is exiting: nobody will look at the panel, and the workers
            # and database it reads may already be stopped.
            and not getattr(host, "_is_shutting_down", False)
        ):
            # Show arrives before the window is painted. Qt would show the new panel
            # with a queued call and drop the old one on deleteLater, but a window
            # shown while a click is handled is painted before either, so swap now.
            try:
                host.load_right_panel(force=True)
                for frame in (host.routine_frame, host.directive_frame):
                    _show_only_layout_children(frame)
            except Exception:
                # Keep the build pending so the next load_right_panel() retries it
                # instead of skipping on an unchanged signature.
                host._right_panel_render_deferred = True
                logger.exception("Deferred right panel render failed")
        return False


class CalendarViewActionsMixin:
    # ------------------------------------------------------------------ #
    # 패널 렌더링 위임
    # ------------------------------------------------------------------ #
    def _theme_signature_bits(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            return ("", "", "", 0, 0, 0, 0, "", "", "", "", "", "")

        def _setting_value(key, default=""):
            try:
                return settings.value(key, default)
            except Exception:
                return default

        def _setting_int(key, default=0):
            try:
                return int(settings.value(key, default, type=int) or 0)
            except Exception:
                try:
                    return int(_setting_value(key, default) or 0)
                except Exception:
                    return int(default)

        return (
            str(_setting_value("theme_color", "#4da6ff") or "#4da6ff"),
            str(_setting_value("text_theme", "dark") or "dark"),
            str(_setting_value("panel_base_color", "#1c1c1c") or "#1c1c1c"),
            _setting_int("last_opacity", 200),
            # The wallpaper can raise the visible opacity without a settings change.
            round(wallpaper_opacity_floor() * 255),
            _setting_int("last_border_opacity", 80),
            str(_setting_value("appearance_border_source", "") or ""),
            str(_setting_value("panel_border_color", "") or ""),
            _setting_int("text_opacity", 255),
            str(_setting_value("custom_text_primary", "") or ""),
            str(_setting_value("custom_text_secondary", "") or ""),
            str(_setting_value("custom_text_muted", "") or ""),
            str(_setting_value("custom_text_faint", "") or ""),
            str(_setting_value("custom_input_bg", "") or ""),
            str(_setting_value("ui_shape_preset", "sharp") or "sharp"),
        )

    def _common_ui_signature_bits(self):
        app_instance = QApplication.instance()
        app_font = app_instance.font() if app_instance else None
        search_text = ""
        if getattr(self, "search_edit", None) is not None:
            try:
                search_text = (self.search_edit.text() or "").strip()
            except Exception:
                search_text = ""

        # The selection is not part of the signature: Ctrl+click and clearing
        # restyle the visible items in place (_update_selection_visuals) and
        # every render applies the current selection, so a selection change
        # must not force a full calendar or panel rebuild.
        return (
            search_text,
            *self._theme_signature_bits(),
            app_font.family() if app_font else "",
            app_font.pointSize() if app_font else 0,
        )

    def _build_left_render_signature(self):
        from calendar_app.presentation.panels.side_panel_renderer import (
            left_panel_mode,
            selected_schedule_date,
        )

        mode = left_panel_mode(self)
        return (
            (selected_schedule_date(self) if mode == "selected" else QDate.currentDate()).toString(
                "yyyy-MM-dd"
            ),
            mode,
            str(self._directive_panel_option("left_group_by_date", "false")).lower() == "true",
            *self._common_ui_signature_bits(),
        )

    def _build_right_render_signature(self):
        return (
            self.current_date.toString("yyyy-MM-dd")
            if isinstance(getattr(self, "current_date", None), QDate)
            else "",
            str(self._directive_panel_option("directive_status_filter", "all")).lower() or "all",
            str(self._directive_panel_option("directive_group_by_receiver", "false")).lower()
            == "true",
            str(self._directive_panel_option("directive_group_by_deadline", "false")).lower()
            == "true",
            str(self._directive_panel_option("directive_sort_mode", "deadline") or "deadline"),
            str(self._directive_panel_option("routine_status_filter", "all")).lower() or "all",
            str(self._directive_panel_option("routine_sort_mode", "deadline") or "deadline"),
            str(self._directive_panel_option("routine_group_by_cycle", "false")).lower() == "true",
            str(self._directive_panel_option("routine_group_by_deadline", "false")).lower()
            == "true",
            *self._common_ui_signature_bits(),
        )

    def _load_panel_cached(self, panel_name, signature, loader_func, force=True):
        """공통 캐싱 헬퍼 — 시그니처가 바뀌지 않으면 렌더링을 건너뜁니다."""
        panel_dirty = (
            bool(self._panel_dirty.get(panel_name, True)) if hasattr(self, "_panel_dirty") else True
        )
        sig_attr = f"_last_{panel_name}_render_signature"
        if not force and not panel_dirty and getattr(self, sig_attr, None) == signature:
            return
        with theme_cache_scope():
            loader_func(self)
        setattr(self, sig_attr, signature)

    def load_left_panel(self, force=True):
        from calendar_app.presentation.panels.side_panel_renderer import load_left_panel

        self._load_panel_cached("left", self._build_left_render_signature(), load_left_panel, force)

    def load_right_panel(self, force=True):
        from calendar_app.presentation.panels.side_panel_renderer import (
            load_right_panel,
            publish_right_panel_data,
        )

        if self._right_panel_render_can_wait():
            # Nobody can see the panel: give the widget its data now and build the
            # panel when a frame is shown again (_RightPanelShowWatch).
            publish_right_panel_data(self)
            self._right_panel_render_deferred = True
        else:
            # A deferred build must not be skipped by an unchanged signature.
            deferred = bool(getattr(self, "_right_panel_render_deferred", False))
            self._right_panel_render_deferred = False
            self._load_panel_cached(
                "right", self._build_right_render_signature(), load_right_panel, force or deferred
            )
        if hasattr(self, "refresh_widget_mode_panels"):
            self.refresh_widget_mode_panels(schedule=False, work=True)

    def _center_panel_render_can_wait(self):
        """True until the calendar frame is shown for the first time."""
        if getattr(self, "_center_panel_shown", False) or getattr(self, "_is_shutting_down", False):
            return False
        frame = getattr(self, "center_frame", None)
        if frame is None or frame.isVisible():
            self._center_panel_shown = True
            return False
        if getattr(self, "_center_panel_show_watch", None) is None:
            self._center_panel_show_watch = _CenterPanelFirstShowWatch(self, frame)
            frame.installEventFilter(self._center_panel_show_watch)
        return True

    def _right_panel_render_can_wait(self):
        """True while widget-only mode is active and neither right-panel frame is visible."""
        if getattr(self, "_is_shutting_down", False):
            return False
        is_widget_mode_active = getattr(self, "is_widget_mode_active", None)
        if not callable(is_widget_mode_active) or not is_widget_mode_active():
            return False
        frames = (getattr(self, "routine_frame", None), getattr(self, "directive_frame", None))
        if any(frame is None or frame.isVisible() for frame in frames):
            return False
        if getattr(self, "_right_panel_show_watch", None) is None:
            watch = _RightPanelShowWatch(self, frames[0])
            for frame in frames:
                frame.installEventFilter(watch)
            self._right_panel_show_watch = watch
        return True

    def _directive_panel_option(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        if hasattr(self, "settings"):
            return self.settings.value(key, default)
        return default

    def _set_directive_panel_option(self, key, value):
        setattr(self, key, value)
        if hasattr(self, "settings"):
            self.settings.setValue(key, value)

    def toggle_directive_group_by_receiver(self):
        enabled = (
            str(self._directive_panel_option("directive_group_by_receiver", "false")).lower()
            == "true"
        )
        enabled = not enabled
        self._set_directive_panel_option("directive_group_by_receiver", enabled)
        if enabled:
            # 보완: 수신처 그룹화 시 마감일 그룹화는 해제
            self._set_directive_panel_option("directive_group_by_deadline", False)
        self.schedule_panel_refresh(right=True)

    def toggle_directive_group_by_deadline(self):
        enabled = (
            str(self._directive_panel_option("directive_group_by_deadline", "false")).lower()
            == "true"
        )
        enabled = not enabled
        self._set_directive_panel_option("directive_group_by_deadline", enabled)
        if enabled:
            # 보완: 마감일 그룹화 시 수신처 그룹화는 해제
            self._set_directive_panel_option("directive_group_by_receiver", False)
        self.schedule_panel_refresh(right=True)

    def set_directive_sort_mode(self, mode):
        self._set_directive_panel_option("directive_sort_mode", mode or "deadline")
        self.schedule_panel_refresh(right=True)

    def set_directive_status_filter(self, value):
        self._set_directive_panel_option("directive_status_filter", value or "all")
        self.schedule_panel_refresh(right=True)

    def set_routine_status_filter(self, value):
        self._set_directive_panel_option("routine_status_filter", value or "all")
        self.schedule_panel_refresh(right=True)

    def set_routine_sort_mode(self, mode):
        self._set_directive_panel_option("routine_sort_mode", mode or "deadline")
        self.schedule_panel_refresh(right=True)

    def toggle_left_group_by_date(self):
        enabled = str(self._directive_panel_option("left_group_by_date", "false")).lower() == "true"
        self._set_directive_panel_option("left_group_by_date", not enabled)
        self.schedule_panel_refresh(left=True)

    def toggle_routine_group_by_cycle(self):
        enabled = (
            str(self._directive_panel_option("routine_group_by_cycle", "false")).lower() == "true"
        )
        enabled = not enabled
        self._set_directive_panel_option("routine_group_by_cycle", enabled)
        if enabled:
            self._set_directive_panel_option("routine_group_by_deadline", False)
        self.schedule_panel_refresh(right=True)

    def toggle_routine_group_by_deadline(self):
        enabled = (
            str(self._directive_panel_option("routine_group_by_deadline", "false")).lower()
            == "true"
        )
        enabled = not enabled
        self._set_directive_panel_option("routine_group_by_deadline", enabled)
        if enabled:
            self._set_directive_panel_option("routine_group_by_cycle", False)
        self.schedule_panel_refresh(right=True)

    def _build_center_render_signature(self):
        common_bits = self._common_ui_signature_bits()
        search_text = common_bits[0]
        theme_bits = common_bits[1:-2]
        font_family = common_bits[-2]
        font_size = common_bits[-1]
        center_frame = getattr(self, "center_frame", None)
        return (
            str(getattr(self, "view_mode_state", "")),
            str(getattr(self, "cal_week_layout", "time")),
            self.current_date.toString("yyyy-MM-dd")
            if isinstance(getattr(self, "current_date", None), QDate)
            else "",
            bool(getattr(self, "cal_show_weekends", True)),
            bool(getattr(self, "cal_start_monday", True)),
            bool(getattr(self, "cal_show_month", False)),
            weekday_display_mode_for(self),
            search_text,
            *theme_bits,
            font_family,
            font_size,
            # render_calendar sizes month and date-week rows from this height.
            center_frame.height() if center_frame is not None else 0,
        )

    def load_center_panel(self, force=True):
        from calendar_app.presentation.calendar.month_renderer import render_calendar
        from calendar_app.presentation.panels.side_panel_renderer import (
            _selected_day_subscription_rows,
            left_panel_mode,
            selected_schedule_date,
        )

        if self._center_panel_render_can_wait():
            # Rows are sized from the frame height, which is only real once the
            # window is shown: startup used to build the calendar twice for nothing.
            self._center_panel_render_deferred = True
            return
        force = force or bool(getattr(self, "_center_panel_render_deferred", False))
        self._center_panel_render_deferred = False

        selected_date = (
            selected_schedule_date(self) if left_panel_mode(self) == "selected" else None
        )
        old_subscriptions = (
            _selected_day_subscription_rows(self, selected_date)
            if selected_date is not None
            else []
        )

        self._load_panel_cached(
            "center", self._build_center_render_signature(), render_calendar, force
        )
        if selected_date is not None and old_subscriptions != _selected_day_subscription_rows(
            self, selected_date
        ):
            self.load_left_panel()
        if hasattr(self, "refresh_widget_mode_panels"):
            self.refresh_widget_mode_panels(schedule=True, work=False)

    # ------------------------------------------------------------------ #
    # 캘린더 뷰 조작
    # ------------------------------------------------------------------ #
    def _set_calendar_flag(self, attr, settings_key, state):
        """캘린더 표시 플래그를 저장하고 센터 패널을 갱신하는 공통 헬퍼."""
        setattr(self, attr, bool(state))
        if hasattr(self, "settings"):
            self.settings.setValue(settings_key, getattr(self, attr))
        self.load_center_panel()

    def toggle_weekends(self, state):
        self._set_calendar_flag("cal_show_weekends", "cal_show_weekends", state)

    def toggle_start_day(self, state):
        self._set_calendar_flag("cal_start_monday", "cal_start_monday", state)

    def toggle_show_month(self, state):
        self._set_calendar_flag("cal_show_month", "cal_show_month", state)

    def toggle_show_weekday(self, state):
        self.set_weekday_display_mode("both" if state else "header")

    def set_weekday_display_mode(self, mode):
        mode = normalize_weekday_display_mode(mode)
        if mode is None:
            return
        self.cal_weekday_display_mode = mode
        self.cal_show_weekday = weekday_display_flags(mode)[1]
        if hasattr(self, "settings"):
            self.settings.setValue(WEEKDAY_DISPLAY_KEY, mode)
            self.settings.setValue("cal_show_weekday", self.cal_show_weekday)
        self.load_center_panel()

    def cycle_weekday_display_mode(self):
        self.set_weekday_display_mode(next_weekday_display_mode(weekday_display_mode_for(self)))

    def prev_day(self):
        if self.view_mode_state == "monthly":
            self.current_date = self.current_date.addMonths(-1)
        elif "weekly" in self.view_mode_state:
            self.current_date = self.current_date.addDays(-7)
        else:
            self.current_date = self.current_date.addDays(-1)
        self.schedule_panel_refresh(left=True, center=True)

    def next_day(self):
        if self.view_mode_state == "monthly":
            self.current_date = self.current_date.addMonths(1)
        elif "weekly" in self.view_mode_state:
            self.current_date = self.current_date.addDays(7)
        else:
            self.current_date = self.current_date.addDays(1)
        self.schedule_panel_refresh(left=True, center=True)

    def jump_to_today(self):
        from calendar_app.presentation.panels.side_panel_renderer import left_panel_mode

        self.current_date = QDate.currentDate()
        if left_panel_mode(self) == "selected":
            self._last_clicked_date = QDate(self.current_date)
        self.schedule_panel_refresh(left=True, center=True)

    def change_view_mode(self, mode):
        self.view_mode_state = mode
        self.load_center_panel()

    def toggle_view_mode(self):
        if self.view_mode_state == "monthly":
            self.view_mode_state = "weekly_1"
        else:
            self.view_mode_state = "monthly"
        self.load_center_panel()

    # ------------------------------------------------------------------ #
    # 컨텍스트 메뉴 위임
    # ------------------------------------------------------------------ #
    def show_left_context_menu(self, pos):
        from calendar_app.presentation.context_menu_manager import show_left_context_menu

        show_left_context_menu(self, pos)

    def show_center_context_menu(self, pos):
        from calendar_app.presentation.context_menu_manager import show_center_context_menu

        show_center_context_menu(self, pos)

    def show_right_context_menu(self, pos):
        from calendar_app.presentation.context_menu_manager import show_right_context_menu

        show_right_context_menu(self, pos)

    def show_directive_context_menu(self, pos):
        from calendar_app.presentation.context_menu_manager import show_directive_context_menu

        show_directive_context_menu(self, pos)
