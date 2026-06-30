from PyQt6.QtWidgets import QMenu

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.icon_map import ICON, icon
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_settings import opacity_byte_to_percent, opacity_percent_to_byte


def _strip_menu_emojis(menu):
    """메뉴/서브메뉴 액션 텍스트의 컬러 이모지 접두사를 제거한다.

    setIcon으로 단색 아이콘이 이미 지정돼 있어 라벨 이모지는 중복 표현이 된다.
    재귀적으로 모든 하위 메뉴까지 정리한다.
    """
    for act in menu.actions():
        if act.text():
            act.setText(_se(act.text()))
        sub = act.menu()
        if sub is not None:
            _strip_menu_emojis(sub)


def _add_task_priority_status_menus(menu, app, priority_items, status_items):
    priority_menu = menu.addMenu(t("context_menu.priority_change", default="Priority Change"))
    priority_menu.setIcon(icon(ICON.SORT_BY_PRIORITY))
    for label, value in priority_items:

        def _set_priority(*, v=value):
            ids = getattr(app, "selected_task_ids", set())
            if ids:
                for tid in list(ids):
                    app.handle_task_priority_changed(tid, v)
            else:
                app.handle_task_priority_changed(None, v)

        priority_menu.addAction(label, _set_priority)

    status_menu_change = menu.addMenu(t("context_menu.status_change", default="Status Change"))
    status_menu_change.setIcon(icon(ICON.FILTER))
    for label, value in status_items:

        def _set_status(*, v=value):
            ids = getattr(app, "selected_task_ids", set())
            if ids:
                for tid in list(ids):
                    app.handle_task_status_changed(tid, v)
            else:
                app.handle_task_status_changed(None, v)

        status_menu_change.addAction(label, _set_status)


def show_left_context_menu(app, pos):
    """Context menu for the left schedule panel."""
    from calendar_app.domain.task_constants import PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS

    menu = QMenu(app)
    app.apply_menu_opacity(menu)

    act_add = menu.addAction(
        t("context_menu.add_schedule", default="Add Schedule"), lambda: app.open_task_dialog()
    )
    act_add.setIcon(icon(ICON.ADD))
    act_checklist = menu.addAction(
        t("context_menu.checklist_mgmt", default="Checklist Management"), app.open_checklist_manager
    )
    act_checklist.setIcon(icon(ICON.CHECKLIST))
    menu.addSeparator()

    act_group_date = menu.addAction(t("context_menu.group_deadline", "Group by deadline"))
    act_group_date.setIcon(icon(ICON.GROUP_BY_DATE))
    act_group_date.setCheckable(True)
    act_group_date.setChecked(
        str(
            getattr(app, "left_group_by_date", app.settings.value("left_group_by_date", "false"))
        ).lower()
        == "true"
    )

    sort_menu = menu.addMenu(t("context_menu.sort_mode", default="Sort Mode"))
    sort_menu.setIcon(icon(ICON.SORT_MODE))
    act_sort_time = sort_menu.addAction(t("context_menu.sort_time", default="Sort by Time"))
    act_sort_time.setIcon(icon(ICON.SORT_BY_TIME))
    act_sort_pri = sort_menu.addAction(t("context_menu.sort_priority", default="Sort by Priority"))
    act_sort_pri.setIcon(icon(ICON.SORT_BY_PRIORITY))

    menu.addSeparator()
    _add_task_priority_status_menus(menu, app, PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS)

    menu.addSeparator()
    act_toggle = menu.addAction(
        t("context_menu.toggle_completed", default="Toggle Completed Status")
    )
    act_toggle.setIcon(icon(ICON.STATUS_COMPLETED))
    act_refresh = menu.addAction(t("context_menu.refresh", default="Refresh"), app.load_left_panel)
    act_refresh.setIcon(icon(ICON.REFRESH))
    act_all = menu.addAction(
        t("context_menu.all_schedule", default="All Schedules"), app.open_task_management_dialog
    )
    act_all.setIcon(icon(ICON.ALL_SCHEDULES))

    _strip_menu_emojis(menu)
    chosen = menu.exec(app.left_frame.mapToGlobal(pos))
    if chosen == act_group_date:
        app.toggle_left_group_by_date()


def show_center_context_menu(app, pos):
    """Context menu for the calendar panel."""
    menu = QMenu(app)
    app.apply_menu_opacity(menu)

    view_menu = menu.addMenu(t("context_menu.view_mode", default="View Mode"))
    view_menu.setIcon(icon(ICON.DISPLAY_STYLE))
    act_w1 = view_menu.addAction(
        t("view_mode.weekly_1", default="1-Week View"), lambda: app.change_view_mode("weekly_1")
    )
    act_w1.setIcon(icon(ICON.VIEW_CALENDAR))
    act_w2 = view_menu.addAction(
        t("view_mode.weekly_2", default="2-Week View"), lambda: app.change_view_mode("weekly_2")
    )
    act_w2.setIcon(icon(ICON.VIEW_CALENDAR))
    act_w3 = view_menu.addAction(
        t("view_mode.weekly_3", default="3-Week View"), lambda: app.change_view_mode("weekly_3")
    )
    act_w3.setIcon(icon(ICON.VIEW_CALENDAR))
    act_mo = view_menu.addAction(
        t("view_mode.monthly", default="Monthly View"), lambda: app.change_view_mode("monthly")
    )
    act_mo.setIcon(icon(ICON.VIEW_MONTHLY))

    act_today = menu.addAction(
        t("context_menu.goto_today", default="Go to Today"), app.jump_to_today
    )
    act_today.setIcon(icon(ICON.GOTO_TODAY))

    gcal_menu = menu.addMenu(t("context_menu.sync_google", default="Google Calendar"))
    gcal_menu.setIcon(icon(ICON.GCAL))
    act_sync_now = gcal_menu.addAction(
        t("context_menu.sync_now", default="Sync Now"), app.sync_google_calendar
    )
    act_sync_now.setIcon(icon(ICON.SYNC))
    act_sync_cfg = gcal_menu.addAction(
        t("context_menu.sync_settings", default="Sync Settings"), app.open_gcal_settings_dialog
    )
    act_sync_cfg.setIcon(icon(ICON.SYNC_SETTINGS))

    screen_menu = menu.addMenu(t("context_menu.screen_mgmt", default="Screen Management"))
    screen_menu.setIcon(icon(ICON.SCREEN_MGMT))
    act_next_mon = screen_menu.addAction(
        t("context_menu.next_monitor", default="Move to Next Monitor"), app.move_to_next_monitor
    )
    act_next_mon.setIcon(icon(ICON.NEXT_MONITOR))
    screen_menu.addSeparator()
    act_sl = screen_menu.addAction(
        t("context_menu.snap_left", default="Snap Left"), lambda: app.snap_to_edge("left")
    )
    act_sl.setIcon(icon(ICON.SNAP_LEFT))
    act_sr = screen_menu.addAction(
        t("context_menu.snap_right", default="Snap Right"), lambda: app.snap_to_edge("right")
    )
    act_sr.setIcon(icon(ICON.SNAP_RIGHT))
    act_st = screen_menu.addAction(
        t("context_menu.snap_top", default="Snap Top"), lambda: app.snap_to_edge("top")
    )
    act_st.setIcon(icon(ICON.SNAP_TOP))
    act_sb = screen_menu.addAction(
        t("context_menu.snap_bottom", default="Snap Bottom"), lambda: app.snap_to_edge("bottom")
    )
    act_sb.setIcon(icon(ICON.SNAP_BOTTOM))
    act_sc = screen_menu.addAction(
        t("context_menu.snap_center", default="Snap Center"), lambda: app.snap_to_edge("center")
    )
    act_sc.setIcon(icon(ICON.SNAP_CENTER))

    menu.addSeparator()
    opacity_menu = menu.addMenu(t("context_menu.opacity_ctrl", default="Opacity Control"))
    opacity_menu.setIcon(icon(ICON.OPACITY))
    current_val = app.slider.value() if hasattr(app, "slider") else 255
    current_percent = opacity_byte_to_percent(current_val)
    for label_key, val in [
        ("context_menu.opacity_title.v100", 100),
        ("context_menu.opacity_title.v85", 85),
        ("context_menu.opacity_title.v70", 70),
        ("context_menu.opacity_title.v50", 50),
        ("context_menu.opacity_title.v30", 30),
    ]:
        act_op = opacity_menu.addAction(
            t(label_key), lambda *args, v=val: app.slider.setValue(opacity_percent_to_byte(v))
        )
        act_op.setCheckable(True)
        act_op.setChecked(current_percent == val)

    opacity_menu.addSeparator()
    opacity_step = opacity_percent_to_byte(10)
    opacity_floor = opacity_percent_to_byte(20)
    act_op_up = opacity_menu.addAction(
        t("context_menu.opacity_up", default="Increase Opacity (10%)"),
        lambda: app.slider.setValue(min(app.slider.value() + opacity_step, 255)),
    )
    act_op_up.setIcon(icon(ICON.OPACITY_UP))
    act_op_dn = opacity_menu.addAction(
        t("context_menu.opacity_down", default="Decrease Opacity (10%)"),
        lambda: app.slider.setValue(max(app.slider.value() - opacity_step, opacity_floor)),
    )
    act_op_dn.setIcon(icon(ICON.OPACITY_DOWN))

    act_refresh = menu.addAction(
        t("context_menu.refresh", default="Refresh"), app.load_center_panel
    )
    act_refresh.setIcon(icon(ICON.REFRESH))
    act_preset = menu.addAction(
        t("context_menu.default_preset", default="Load Default Preset"),
        app.preset_manager.load_default_preset,
    )
    act_preset.setIcon(icon(ICON.PRESET_LOAD))

    _strip_menu_emojis(menu)
    menu.exec(app.center_frame.mapToGlobal(pos))


def show_right_context_menu(app, pos):
    """Context menu for the routine panel."""
    from calendar_app.domain.task_constants import PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS

    menu = QMenu(app)
    app.apply_menu_opacity(menu)

    act_add = menu.addAction(
        t("context_menu.add_routine", default="Add Routine/Directives"), app.open_routine_add_dialog
    )
    act_add.setIcon(icon(ICON.ADD))
    act_checklist = menu.addAction(
        t("context_menu.checklist_mgmt", default="Checklist Management"), app.open_checklist_manager
    )
    act_checklist.setIcon(icon(ICON.CHECKLIST))
    menu.addSeparator()

    act_group_cycle = menu.addAction(t("context_menu.group_cycle", "Group by cycle"))
    act_group_cycle.setIcon(icon(ICON.GROUP_BY_CYCLE))
    act_group_cycle.setCheckable(True)
    act_group_cycle.setChecked(
        str(
            getattr(
                app, "routine_group_by_cycle", app.settings.value("routine_group_by_cycle", "false")
            )
        ).lower()
        == "true"
    )

    act_group_dl = menu.addAction(t("context_menu.group_deadline", "Group by deadline"))
    act_group_dl.setIcon(icon(ICON.GROUP_BY_DATE))
    act_group_dl.setCheckable(True)
    act_group_dl.setChecked(
        str(
            getattr(
                app,
                "routine_group_by_deadline",
                app.settings.value("routine_group_by_deadline", "false"),
            )
        ).lower()
        == "true"
    )

    menu.addSeparator()
    sort_menu = menu.addMenu(t("context_menu.sort_mode", default="Sort Mode"))
    sort_menu.setIcon(icon(ICON.SORT_MODE))
    cur_sort = (
        str(
            getattr(app, "routine_sort_mode", app.settings.value("routine_sort_mode", "deadline"))
        ).lower()
        or "deadline"
    )

    act_sort_deadline = sort_menu.addAction(
        t("context_menu.sort_deadline", default="Sort by Deadline")
    )
    act_sort_deadline.setIcon(icon(ICON.SORT_BY_TIME))
    act_sort_deadline.setCheckable(True)
    act_sort_deadline.setChecked(cur_sort == "deadline")

    act_sort_reg = sort_menu.addAction(t("context_menu.sort_reg", default="Sort by Registration"))
    act_sort_reg.setIcon(icon(ICON.GROUP_BY_DATE))
    act_sort_reg.setCheckable(True)
    act_sort_reg.setChecked(cur_sort == "registration")

    act_sort_priority = sort_menu.addAction(
        t("context_menu.sort_priority", default="Sort by Priority")
    )
    act_sort_priority.setIcon(icon(ICON.SORT_BY_PRIORITY))
    act_sort_priority.setCheckable(True)
    act_sort_priority.setChecked(cur_sort == "priority")

    status_filter_menu = menu.addMenu(t("context_menu.status_filter", default="Status Filter"))
    status_filter_menu.setIcon(icon(ICON.SEARCH))
    cur_filter = (
        str(
            getattr(
                app, "routine_status_filter", app.settings.value("routine_status_filter", "all")
            )
        ).lower()
        or "all"
    )

    act_sf_all = status_filter_menu.addAction(
        t("context_menu.filter_all", default="All (No Filter)")
    )
    act_sf_all.setIcon(icon(ICON.FILTER_ALL))
    act_sf_all.setCheckable(True)
    act_sf_all.setChecked(cur_filter == "all")

    act_sf_progress = status_filter_menu.addAction(
        t("context_menu.filter_progress", default="In Progress Only")
    )
    act_sf_progress.setIcon(icon(ICON.FILTER_PROGRESS))
    act_sf_progress.setCheckable(True)
    act_sf_progress.setChecked(cur_filter == "in_progress")

    act_sf_overdue = status_filter_menu.addAction(
        t("context_menu.filter_overdue", default="Overdue Only")
    )
    act_sf_overdue.setIcon(icon(ICON.FILTER_OVERDUE))
    act_sf_overdue.setCheckable(True)
    act_sf_overdue.setChecked(cur_filter == "overdue")

    act_sf_completed = status_filter_menu.addAction(
        t("context_menu.filter_completed", default="Completed Only")
    )
    act_sf_completed.setIcon(icon(ICON.STATUS_COMPLETED))
    act_sf_completed.setCheckable(True)
    act_sf_completed.setChecked(cur_filter == "completed")

    menu.addSeparator()
    _add_task_priority_status_menus(menu, app, PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS)

    menu.addSeparator()
    act_refresh = menu.addAction(t("context_menu.refresh", default="Refresh"), app.load_right_panel)
    act_refresh.setIcon(icon(ICON.REFRESH))
    act_all = menu.addAction(
        t("context_menu.all_routine", default="Routine Management"),
        app.open_routine_management_dialog,
    )
    act_all.setIcon(icon(ICON.ROUTINE))

    _strip_menu_emojis(menu)
    chosen = menu.exec(app.routine_frame.mapToGlobal(pos))
    if chosen == act_group_cycle:
        app.toggle_routine_group_by_cycle()
    elif chosen == act_group_dl:
        app.toggle_routine_group_by_deadline()
    elif chosen == act_sort_deadline:
        app.set_routine_sort_mode("deadline")
    elif chosen == act_sort_reg:
        app.set_routine_sort_mode("registration")
    elif chosen == act_sort_priority:
        app.set_routine_sort_mode("priority")
    elif chosen == act_sf_all:
        app.set_routine_status_filter("all")
    elif chosen == act_sf_progress:
        app.set_routine_status_filter("in_progress")
    elif chosen == act_sf_overdue:
        app.set_routine_status_filter("overdue")
    elif chosen == act_sf_completed:
        app.set_routine_status_filter("completed")


def show_directive_context_menu(app, pos):
    """Context menu for the directive panel."""
    menu = QMenu(app)
    app.apply_menu_opacity(menu)

    act_add = menu.addAction(
        t("context_menu.add_directive", default="Add Directive/Cooperation"),
        lambda: app.open_directive_dialog(),
    )
    act_add.setIcon(icon(ICON.ADD))

    act_group_receiver = menu.addAction(
        t("context_menu.group_receiver", default="Group by Receiver")
    )
    act_group_receiver.setIcon(icon(ICON.GROUP_BY_RECEIVER))
    act_group_receiver.setCheckable(True)
    act_group_receiver.setChecked(
        str(
            getattr(
                app,
                "directive_group_by_receiver",
                app.settings.value("directive_group_by_receiver", "false"),
            )
        ).lower()
        == "true"
    )

    act_group_deadline = menu.addAction(
        t("context_menu.group_deadline", default="Group by Deadline")
    )
    act_group_deadline.setIcon(icon(ICON.GROUP_BY_DATE))
    act_group_deadline.setCheckable(True)
    act_group_deadline.setChecked(
        str(
            getattr(
                app,
                "directive_group_by_deadline",
                app.settings.value("directive_group_by_deadline", "false"),
            )
        ).lower()
        == "true"
    )

    act_sort_deadline = menu.addAction(
        t("context_menu.sort_deadline_near", default="Sort by Deadline (Near first)")
    )
    act_sort_deadline.setIcon(icon(ICON.SORT_BY_TIME))
    act_sort_deadline.setCheckable(True)
    act_sort_deadline.setChecked(
        (
            getattr(
                app, "directive_sort_mode", app.settings.value("directive_sort_mode", "deadline")
            )
            or "deadline"
        )
        == "deadline"
    )

    status_menu = menu.addMenu(t("context_menu.status_filter", default="Status Filter"))
    status_menu.setIcon(icon(ICON.SEARCH))
    cur_filter = (
        str(
            getattr(
                app, "directive_status_filter", app.settings.value("directive_status_filter", "all")
            )
        ).lower()
        or "all"
    )

    act_filter_all = status_menu.addAction(t("context_menu.filter_all", default="All (No Filter)"))
    act_filter_all.setIcon(icon(ICON.FILTER_ALL))
    act_filter_all.setCheckable(True)
    act_filter_all.setChecked(cur_filter == "all")

    act_filter_progress = status_menu.addAction(
        t("context_menu.filter_progress", default="In Progress")
    )
    act_filter_progress.setIcon(icon(ICON.FILTER_PROGRESS))
    act_filter_progress.setCheckable(True)
    act_filter_progress.setChecked(cur_filter == "in_progress")

    act_filter_overdue = status_menu.addAction(t("context_menu.filter_overdue", default="Overdue"))
    act_filter_overdue.setIcon(icon(ICON.FILTER_OVERDUE))
    act_filter_overdue.setCheckable(True)
    act_filter_overdue.setChecked(cur_filter == "overdue")

    act_filter_completed = status_menu.addAction(
        t("context_menu.filter_completed", default="Completed")
    )
    act_filter_completed.setIcon(icon(ICON.STATUS_COMPLETED))
    act_filter_completed.setCheckable(True)
    act_filter_completed.setChecked(cur_filter == "completed")

    menu.addSeparator()
    act_refresh = menu.addAction(t("context_menu.refresh", default="Refresh"), app.load_right_panel)
    act_refresh.setIcon(icon(ICON.REFRESH))
    act_all = menu.addAction(
        t("context_menu.all_directive", default="Directive Management"),
        app.open_directive_management_dialog,
    )
    act_all.setIcon(icon(ICON.ALL_SCHEDULES))

    _strip_menu_emojis(menu)
    chosen = menu.exec(app.directive_frame.mapToGlobal(pos))
    if chosen == act_group_receiver:
        app.toggle_directive_group_by_receiver()
    elif chosen == act_group_deadline:
        app.toggle_directive_group_by_deadline()
    elif chosen == act_sort_deadline:
        app.set_directive_sort_mode("deadline")
    elif chosen == act_filter_all:
        app.set_directive_status_filter("all")
    elif chosen == act_filter_progress:
        app.set_directive_status_filter("in_progress")
    elif chosen == act_filter_overdue:
        app.set_directive_status_filter("overdue")
    elif chosen == act_filter_completed:
        app.set_directive_status_filter("completed")
