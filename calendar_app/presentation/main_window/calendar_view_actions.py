"""Calendar/panel/context-menu view action mixin."""

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication


class CalendarViewActionsMixin:
    # ------------------------------------------------------------------ #
    # 패널 렌더링 위임
    # ------------------------------------------------------------------ #
    def _theme_signature_bits(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            return ("", "", "", 0, 0, 0, "", "", "", "", "", "")

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
            _setting_int("last_border_opacity", 80),
            _setting_int("last_text_opacity", 255),
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

        selected_ids = tuple(
            sorted(int(v) for v in getattr(self, "selected_task_ids", set()) if str(v).isdigit())
        )
        return (
            search_text,
            selected_ids,
            *self._theme_signature_bits(),
            app_font.family() if app_font else "",
            app_font.pointSize() if app_font else 0,
        )

    def _build_left_render_signature(self):
        return (
            self.current_date.toString("yyyy-MM-dd")
            if isinstance(getattr(self, "current_date", None), QDate)
            else "",
            str(
                getattr(self, "left_panel_mode", self.settings.value("left_panel_mode", "today"))
                if hasattr(self, "settings")
                else getattr(self, "left_panel_mode", "today")
            ),
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
        loader_func(self)
        setattr(self, sig_attr, signature)

    def load_left_panel(self, force=True):
        from calendar_app.presentation.panels.side_panel_renderer import load_left_panel

        self._load_panel_cached("left", self._build_left_render_signature(), load_left_panel, force)

    def load_right_panel(self, force=True):
        from calendar_app.presentation.panels.side_panel_renderer import load_right_panel

        self._load_panel_cached(
            "right", self._build_right_render_signature(), load_right_panel, force
        )
        if hasattr(self, "refresh_widget_mode_panels"):
            self.refresh_widget_mode_panels(schedule=False, work=True)

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
        selected_ids = common_bits[1]
        theme_bits = common_bits[2:-2]
        font_family = common_bits[-2]
        font_size = common_bits[-1]
        return (
            str(getattr(self, "view_mode_state", "")),
            self.current_date.toString("yyyy-MM-dd")
            if isinstance(getattr(self, "current_date", None), QDate)
            else "",
            bool(getattr(self, "cal_show_weekends", True)),
            bool(getattr(self, "cal_start_monday", True)),
            bool(getattr(self, "cal_show_month", False)),
            bool(getattr(self, "cal_show_weekday", False)),
            search_text,
            selected_ids,
            *theme_bits,
            font_family,
            font_size,
        )

    def load_center_panel(self, force=True):
        from calendar_app.presentation.calendar.month_renderer import render_calendar

        self._load_panel_cached(
            "center", self._build_center_render_signature(), render_calendar, force
        )
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
        self._set_calendar_flag("cal_show_weekday", "cal_show_weekday", state)

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
        self.current_date = QDate.currentDate()
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
