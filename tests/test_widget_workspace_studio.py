# -*- coding: utf-8 -*-
"""Real Qt widgets: reversible workspaces, native previews, stacks and automation."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import patch

from PyQt6.QtCore import QDateTime, QEvent, QPoint, QSettings, QSize, Qt
from PyQt6.QtTest import QTest
import pytest

from calendar_app.domain.widget_workspace import CALENDAR_SCOPE_KEY, STATE_KEY
from calendar_app.presentation.dialogs.widget_desktop_layout_dialog import WidgetDesktopLayoutDialog
from calendar_app.presentation.dialogs.widget_workspace_options_dialog import (
    WidgetWorkspaceOptionsDialog,
)
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog
from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)
from calendar_app.presentation.widgets.widget_workspace_panel import SaveWorkspaceDialog
from calendar_app.presentation.widgets.widget_workspace_preview import (
    native_thumbnail,
    widget_health,
)
from tests.test_widget_mode_ux import _APP, Host


@pytest.fixture
def studio(tmp_path):
    host = Host()
    host.settings = QSettings(str(tmp_path / "studio.ini"), QSettings.Format.IniFormat)
    host.show()
    coordinator = WidgetModeCoordinator(host)
    coordinator.controller.refresh_data = lambda: None
    host._widget_mode_coordinator = coordinator
    manager = OverlayWidgetManager(host)
    host.overlay_manager = manager
    ids = [
        manager.add_instance(kind, name)
        for kind, name in (
            ("clock", "업무용 시계"),
            ("text", "회의 메모"),
            ("countdown", "집중 시간"),
        )
    ]
    for index, iid in enumerate(ids):
        manager.show_instance(iid)
        manager.get_widget(iid).move(40 + index * 150, 80 + index * 90)
    service = manager.workspace_service()
    _APP.processEvents()
    yield host, manager, service, ids
    manager.shutdown()
    coordinator.close_for_shutdown()
    for row in manager.all_instances():
        row[3].deleteLater()
    if coordinator.controller.widget is not None:
        coordinator.controller.widget.deleteLater()
    host.close()
    host.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()


def prefs(settings):
    return {key: settings.value(key) for key in settings.allKeys()}


def test_opening_service_does_not_persist_defaults_or_start_polling(studio):
    host, _, service, _ = studio
    assert host.settings.value(STATE_KEY) is None
    assert not service.timer.isActive()
    assert host._widget_mode_coordinator.controller.widget is None


def test_profiles_restore_combination_style_position_and_preserve_content_and_catalogs(studio):
    host, manager, service, ids = studio
    clock, note, countdown = [manager.get_widget(iid) for iid in ids]
    countdown._set(
        "cd_target_iso", QDateTime.currentDateTime().addSecs(600).toString(Qt.DateFormat.ISODate)
    )
    note._set("label_text", "살려둘 메모")
    clock._set("font_size", 34)
    clock._apply_and_resize()
    clock.move(75, 110)
    manager.hide_instance(ids[1])
    host.settings.setValue("widget_mode_skin", "studio_porcelain")
    host.settings.setValue("widget_mode_user_layout_presets", "existing custom catalog")
    host.settings.setValue("widget_mode_resume", False)
    profile = service.save_profile("업무용")
    clock._set("font_size", 50)
    clock._apply_and_resize()
    clock.move(500, 400)
    manager.show_instance(ids[1])
    extra = manager.add_instance("date_card", "나중에 추가")
    manager.show_instance(extra)
    host.settings.setValue("widget_mode_user_layout_presets", "newer catalog")
    target = countdown._get("cd_target_iso")
    assert service.apply_profile(profile) == []
    assert clock._get("font_size") == 34 and clock.pos() == QPoint(75, 110)
    assert not note.is_enabled() and not manager.get_widget(extra).is_enabled()
    assert note._get("label_text") == "살려둘 메모" and countdown._get("cd_target_iso") == target
    assert host.settings.value("widget_mode_user_layout_presets") == "newer catalog"
    assert host.settings.value("widget_mode_resume", type=bool) is False
    assert host._widget_mode_coordinator.state is WidgetModeState.CLOSED
    service.undo()
    assert clock._get("font_size") == 50 and clock.pos() == QPoint(500, 400)
    assert note.is_enabled() and manager.get_widget(extra).is_enabled()


def test_profile_missing_widget_is_reported_without_resurrection(studio):
    _, manager, service, ids = studio
    profile = service.save_profile("기본")
    manager.remove_instance(ids[1])
    assert service.apply_profile(profile) == [ids[1]]
    assert manager.get_widget(ids[1]) is None and len(manager.all_instances()) == 2


def test_apply_failure_rolls_back_partial_style_changes(studio):
    _, manager, service, ids = studio
    clock = manager.get_widget(ids[0])
    clock._set("font_size", 32)
    profile = service.save_profile("old")
    clock._set("font_size", 48)
    before = clock._get("font_size")
    original = clock._apply_and_resize
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic failed repaint")
        original()

    with (
        patch.object(clock, "_apply_and_resize", side_effect=fail_once),
        pytest.raises(RuntimeError),
    ):
        service.apply_profile(profile)
    assert clock._get("font_size") == before


def test_profile_scopes_calendar_selection_and_can_reset_to_all(studio):
    host, _, service, _ = studio
    host.settings.setValue(CALENDAR_SCOPE_KEY, "[1]")
    selected = service.save_profile("일정 하나", calendar_ids=[2])
    all_calendars = service.save_profile("전체", calendar_ids=None)
    service.apply_profile(selected)
    assert json.loads(host.settings.value(CALENDAR_SCOPE_KEY)) == [2]
    service.apply_profile(all_calendars)
    assert json.loads(host.settings.value(CALENDAR_SCOPE_KEY)) is None


def test_scoped_filter_changes_schedule_rows_and_cache_signature(studio):
    host, _, _, _ = studio
    controller = host._widget_mode_coordinator.controller
    date = host.current_date
    stamp = date.toString("yyyy-MM-dd")
    host._latest_calendar_range_data["rows"] = [
        {"id": 1, "calendar_id": 11, "name": "업무", "deadline": stamp + " 10:00:00"},
        {"id": 2, "calendar_id": 12, "name": "개인", "deadline": stamp + " 11:00:00"},
    ]
    before = controller._display_signature(date)
    host.settings.setValue(CALENDAR_SCOPE_KEY, "[12]")
    assert controller._display_signature(date) != before
    assert [row["id"] for row in controller._schedule_rows_for_date(date)] == [2]
    host.settings.setValue(CALENDAR_SCOPE_KEY, "[]")
    assert not controller._schedule_rows_for_date(date)


def test_native_preview_does_not_show_resize_write_or_start_hidden_widget(studio):
    host, manager, _, ids = studio
    widget = manager.get_widget(ids[1])
    manager.hide_instance(ids[1])
    before, geometry = prefs(host.settings), widget.geometry()
    preview = native_thumbnail(widget)
    assert not preview.isNull() and preview.width() <= 560 and preview.height() <= 320
    assert widget.isHidden() and widget.geometry() == geometry
    assert prefs(host.settings) == before


def test_gallery_size_and_opacity_stay_draft_until_apply(studio):
    host, manager, _, ids = studio
    dialog = OverlayManagerDialog(manager, host)
    dialog.show()
    dialog.view_combo.setCurrentIndex(1)
    _APP.processEvents()
    gallery = dialog.gallery
    widget = manager.get_widget(gallery.current_id)
    geometry, before = widget.geometry(), prefs(host.settings)
    gallery.width_spin.setValue(330)
    gallery.height_spin.setValue(210)
    gallery.opacity_spin.setValue(65)
    QTest.qWait(140)
    assert widget.geometry() == geometry and prefs(host.settings) == before
    gallery.reset_draft()
    assert widget.geometry() == geometry
    gallery.width_spin.setValue(330)
    gallery.height_spin.setValue(210)
    gallery.opacity_spin.setValue(65)
    gallery.apply_draft()
    assert widget._get("fixed_w") == 330 and widget._get("widget_opacity") == 65
    gallery.animate.setChecked(True)
    assert gallery._preview_timer.isActive()
    dialog.close()
    assert not gallery._preview_timer.isActive() and not gallery._draft_timer.isActive()
    dialog.deleteLater()


def test_canvas_cancel_preserves_real_positions_and_grid_does_not_shift_initial_draft(studio):
    _, manager, service, ids = studio
    widget = manager.get_widget(ids[0])
    widget.move(73, 117)
    before = widget.geometry()
    dialog = WidgetDesktopLayoutDialog(service)
    assert dialog.draft_rectangles()[ids[0]][:2] == [73, 117]
    dialog.items_by_id[ids[0]].setPos(300, 200)
    dialog.reject()
    assert widget.geometry() == before
    dialog.deleteLater()


def test_canvas_apply_and_undo_preserve_locked_widget(studio):
    _, manager, service, ids = studio
    locked = manager.get_widget(ids[1])
    locked._set_placement_locked(True)
    before_locked = locked.geometry()
    moving = manager.get_widget(ids[0])
    original = moving.geometry()
    dialog = WidgetDesktopLayoutDialog(service)
    dialog.items_by_id[ids[0]].setPos(300, 200)
    dialog.items_by_id[ids[1]].setPos(500, 500)
    dialog._apply()
    assert moving.pos() == QPoint(300, 200) and locked.geometry() == before_locked
    service.undo()
    assert moving.pos() == original.topLeft() and locked.geometry() == before_locked
    dialog.deleteLater()


def test_stack_switching_keeps_native_windows_enabled_content_and_flags(studio):
    _, manager, service, ids = studio
    first, second = manager.get_widget(ids[0]), manager.get_widget(ids[1])
    first_pos, second_pos, flags = first.pos(), second.pos(), second.windowFlags()
    second._set("label_text", "스택 메모")
    group_id = service.stacks.create(ids[:2], "정보 스택")
    assert first.isVisible() and second.isHidden()
    assert first.is_enabled() and second.is_enabled()
    service.stacks.select(group_id, 1)
    assert first.isHidden() and second.isVisible() and second.pos() == first_pos
    assert second.windowFlags() == flags and second._get("label_text") == "스택 메모"
    service.stacks.remove(group_id)
    assert first.isVisible() and second.isVisible() and second.pos() == second_pos


def test_hidden_all_and_deleted_stack_members_do_not_leave_orphan_bar(studio):
    _, manager, service, ids = studio
    group_id = service.stacks.create(ids[:2], "작업")
    manager.hide_all()
    _APP.processEvents()
    assert not service.stacks.bars[group_id].isVisible()
    manager.show_all()
    _APP.processEvents()
    assert sum(manager.get_widget(iid).isVisible() for iid in ids[:2]) == 1
    manager.remove_instance(ids[0])
    _APP.processEvents()
    assert not service.stacks.groups and not service.stacks.bars


def test_locked_or_already_grouped_widgets_cannot_be_grouped_again(studio):
    _, manager, service, ids = studio
    manager.get_widget(ids[1])._set_placement_locked(True)
    with pytest.raises(ValueError):
        service.stacks.create(ids[:2], "locked")
    assert not service.stacks.groups
    manager.get_widget(ids[1])._set_placement_locked(False)
    service.stacks.create(ids[:2], "first")
    with pytest.raises(ValueError):
        service.stacks.create([ids[0], ids[2]], "duplicate")


def test_stack_rotation_pauses_while_interacting(studio):
    _, manager, service, ids = studio
    group_id = service.stacks.create(ids[:2], "rotate")
    service.stacks.set_rotation(group_id, True)
    first = manager.get_widget(ids[0])
    now = datetime.now()
    service.stacks._last_rotate[group_id] = now - timedelta(seconds=20)
    with patch.object(first, "underMouse", return_value=True):
        service.stacks.rotate(now)
        assert service.stacks.groups[0]["index"] == 0
    with (
        patch.object(first, "underMouse", return_value=False),
        patch.object(first, "isActiveWindow", return_value=False),
        patch.object(service.stacks.bars[group_id], "underMouse", return_value=False),
        patch.object(service.stacks.bars[group_id], "isActiveWindow", return_value=False),
    ):
        service.stacks.rotate(now + timedelta(seconds=11))
    assert service.stacks.groups[0]["index"] == 1


def test_motion_and_fullscreen_policies_preserve_widget_preference(studio):
    _, manager, service, ids = studio
    widget = manager.get_widget(ids[0])
    widget.apply_graphic_collection("pure_air", motion=True)
    surface = widget._graphic_surface
    service.configure({"motion": "static", "pause_fullscreen": False, "automatic": False}, [])
    assert surface._studio_motion_mode == "static" and widget._get("graphics_motion", type_=bool)
    with patch(
        "calendar_app.presentation.widgets.widget_workspace_runtime.other_app_is_fullscreen",
        return_value=True,
    ):
        service.configure({"motion": "rich", "pause_fullscreen": True, "automatic": False}, [])
        assert surface._studio_motion_paused and service.timer.interval() == 1000
    with patch(
        "calendar_app.presentation.widgets.widget_workspace_runtime.other_app_is_fullscreen",
        return_value=False,
    ):
        service.tick()
        assert not surface._studio_motion_paused


def test_rule_switching_is_opt_in_ordered_and_manual_override_expires(studio):
    _, manager, service, ids = studio
    first = service.save_profile("work")
    manager.hide_instance(ids[1])
    second = service.save_profile("focus")
    rules = [{"profile": first, "days": [1], "start": "09:00", "end": "18:00", "enabled": True}]
    service.configure({"motion": "balanced", "pause_fullscreen": False, "automatic": False}, rules)
    now = datetime(2026, 11, 2, 10, 0)
    service.tick(now)
    assert service.state["active"] == ""
    service.configure({"motion": "balanced", "pause_fullscreen": False, "automatic": True}, rules)
    service.tick(now)
    assert service.state["active"] == first
    service.apply_profile(second)
    service._manual_until = now + timedelta(hours=1)
    service.tick(now + timedelta(minutes=30))
    assert service.state["active"] == second
    service.tick(now + timedelta(hours=1, minutes=1))
    assert service.state["active"] == first


def test_settings_dialog_cancel_and_profile_save_cancel_write_nothing(studio):
    host, _, service, _ = studio
    before = prefs(host.settings)
    options = WidgetWorkspaceOptionsDialog(service)
    options.motion.setCurrentIndex(options.motion.findData("static"))
    options.fullscreen.setChecked(True)
    options.reject()
    save = SaveWorkspaceDialog(service)
    save.name_edit.setText("취소할 구성")
    save.reject()
    assert prefs(host.settings) == before
    options.deleteLater()
    save.deleteLater()


def test_weather_health_uses_only_cached_data_and_reports_age(studio):
    _, manager, _, ids = studio
    widget = manager.get_widget(ids[0])
    widget._weather_data = {
        "temp": "10",
        "fetched_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
    }
    assert widget_health(widget, "weather")[0] == "delayed"
    widget._weather_data["error"] = "offline"
    assert widget_health(widget, "weather")[0] == "delayed"
    widget._weather_data = {"temp": "10", "fetched_at": datetime.now(UTC).isoformat()}
    assert widget_health(widget, "weather")[0] == "normal"


def test_workspace_settings_restart_restores_saved_stack_and_motion_policy(studio):
    host, manager, service, ids = studio
    service.stacks.create(ids[:2], "persist")
    service.configure({"motion": "static", "pause_fullscreen": False, "automatic": False}, [])
    service.save_profile("restart")
    service.shutdown()
    # New runtime on the same manager simulates application restoration after widget creation.
    from calendar_app.presentation.widgets.widget_workspace_runtime import WidgetWorkspaceService

    restored = WidgetWorkspaceService(manager)
    restored.start()
    assert len(restored.state["profiles"]) == 1 and len(restored.stacks.groups) == 1
    assert restored.state["options"]["motion"] == "static"
    assert sum(manager.get_widget(iid).isVisible() for iid in ids[:2]) == 1
    restored.shutdown()


def test_profile_restores_live_mode_geometry_and_skin_without_losing_custom_layouts(studio):
    host, _, service, _ = studio
    coordinator = host._widget_mode_coordinator
    coordinator.enter()
    controller = coordinator.controller
    controller.set_layout("day_brief")
    controller.set_skin("studio_porcelain")
    window = controller.widget
    window.resize(650, 600)
    window.move(40, 50)
    _APP.processEvents()
    expected = window.geometry()
    profile = service.save_profile("화면 구성")
    controller.set_layout("month_focus")
    controller.set_skin("studio_midnight")
    window.move(300, 150)
    service.apply_profile(profile)
    assert coordinator.state is WidgetModeState.ACTIVE and not host.isVisible()
    assert window.active_layout_id() == "day_brief"
    assert host.settings.value("widget_mode_skin") == "studio_porcelain"
    assert window.geometry().topLeft() == expected.topLeft()
    assert window.size() == expected.size()


def test_keydeck_visual_restore_preserves_changed_actions_and_text(studio):
    _, manager, service, _ = studio
    iid = manager.add_instance("launcher_deck", "키 덱")
    deck = manager.get_widget(iid)
    original_color = deck._deck_data["case"]["color"]
    profile = service.save_profile("키 덱 색상")
    changed = deepcopy(deck._deck_data)
    changed["case"]["color"] = "#aa6633"
    key = changed["pages"][0]["keys"][0]
    key["action"].update(type="text", target="나중에 수정한 키 내용")
    deck._apply_deck(changed)
    service.apply_profile(profile)
    assert deck._deck_data["case"]["color"] == original_color
    assert deck._deck_data["pages"][0]["keys"][0]["action"]["target"] == "나중에 수정한 키 내용"


def test_profile_and_stack_do_not_reset_running_stopwatch(studio):
    _, manager, service, ids = studio
    iid = manager.add_instance("stopwatch", "측정")
    stopwatch = manager.get_widget(iid)
    manager.show_instance(iid)
    stopwatch.toggle_running()
    profile = service.save_profile("실행 중")
    elapsed = stopwatch._sw_elapsed_ms()
    group = service.stacks.create([ids[0], iid], "측정 스택")
    QTest.qWait(35)
    assert stopwatch._sw_running() and stopwatch._sw_elapsed_ms() > elapsed
    service.stacks.select(group, 1)
    service.apply_profile(profile)
    assert stopwatch._sw_running() and stopwatch._sw_elapsed_ms() > elapsed


def test_profile_stack_definition_and_undo_are_persisted_consistently(studio):
    host, _, service, ids = studio
    plain = service.save_profile("개별")
    service.stacks.create(ids[:2], "묶음")
    stacked = service.save_profile("스택")
    service.apply_profile(plain)
    assert not service.stacks.groups
    assert not json.loads(host.settings.value(STATE_KEY))["stacks"]
    service.apply_profile(stacked)
    assert len(service.stacks.groups) == 1
    assert len(json.loads(host.settings.value(STATE_KEY))["stacks"]) == 1
    service.undo()
    assert not service.stacks.groups and not json.loads(host.settings.value(STATE_KEY))["stacks"]


def test_weather_surface_policy_preserves_user_off_and_windows_reduced_motion(studio):
    from calendar_app.presentation.widgets.weather_scene import WeatherSceneSurface

    surface = WeatherSceneSurface()
    surface.configure(scene_id="air_atmosphere", data={"temp": "18", "_wmo": 2}, motion="off")
    surface.show()
    surface.set_runtime_active(True)
    surface.set_motion_policy("rich")
    assert not surface._timer.isActive()
    with patch(
        "calendar_app.presentation.widgets.weather_scene.system_allows_weather_motion",
        return_value=False,
    ):
        surface.configure(scene_id="air_atmosphere", data={"temp": "18", "_wmo": 2}, motion="full")
        surface._check_policy()
        assert not surface._timer.isActive()
    surface.close()
    surface.deleteLater()


def test_automatic_switch_waits_for_modal_editor_to_close(studio):
    from PyQt6.QtWidgets import QApplication

    _, _, service, _ = studio
    profile = service.save_profile("modal")
    rules = [{"profile": profile, "days": [1], "start": "09:00", "end": "18:00", "enabled": True}]
    with patch.object(QApplication, "activeModalWidget", return_value=object()):
        service.configure(
            {"motion": "balanced", "pause_fullscreen": False, "automatic": True}, rules
        )
        service.tick(datetime(2026, 11, 2, 10, 0))
    assert service.state["active"] == ""
    with patch.object(QApplication, "activeModalWidget", return_value=None):
        service.tick(datetime(2026, 11, 2, 10, 1))
    assert service.state["active"] == profile


def test_arranging_circle_preserves_its_shape_ratio(studio):
    _, manager, service, ids = studio
    widget = manager.get_widget(ids[0])
    widget._set_widget_shape("circle")
    service.apply_geometry({ids[0]: [80, 80, 320, 180]})
    assert widget._get("fixed_w") == widget._get("fixed_h")


def test_real_manager_restart_restores_persisted_stack_without_opening_mode(studio):
    host, manager, service, ids = studio
    service.stacks.create(ids[:2], "restart")
    service.save_profile("saved")
    manager.shutdown()
    restored = OverlayWidgetManager(host)
    restored.restore_all()
    assert restored._workspace_service is not None
    assert len(restored.workspace_service().stacks.groups) == 1
    assert sum(restored.get_widget(iid).isVisible() for iid in ids[:2]) == 1
    assert host._widget_mode_coordinator.state is WidgetModeState.CLOSED
    restored.shutdown()
    for row in restored.all_instances():
        row[3].deleteLater()


def test_malformed_saved_workspace_is_retained_for_recovery(studio):
    from calendar_app.presentation.widgets.widget_workspace_runtime import WidgetWorkspaceService

    host, manager, _, _ = studio
    raw = '{"version":1,"profiles":[{"id":"broken","name":"missing snapshot"}]}'
    host.settings.setValue(STATE_KEY, raw)
    replacement = WidgetWorkspaceService(manager)
    replacement.start()
    assert replacement.load_error
    assert host.settings.value(STATE_KEY) == raw
    replacement.shutdown()


def test_repeated_stack_switches_coalesce_metadata_writes(studio):
    from PyQt6.QtTest import QSignalSpy

    host, _, service, ids = studio
    spy = QSignalSpy(service.changed)
    group = service.stacks.create(ids[:2], "batch")
    for _ in range(7):
        service.stacks.advance(group, 1)
    assert host.settings.value(STATE_KEY) is None
    QTest.qWait(180)
    assert len(spy) == 1
    assert json.loads(host.settings.value(STATE_KEY))["stacks"][0]["index"] == 1


def test_keydeck_global_static_policy_keeps_switch_sound_events_and_user_preference(studio):
    _, manager, service, _ = studio
    iid = manager.add_instance("launcher_deck", "motion")
    deck = manager.get_widget(iid)
    manager.show_instance(iid)
    canvas = deck._canvas
    preference = deck._deck_data.get("reduce_motion", False)
    service.configure({"motion": "static", "pause_fullscreen": False, "automatic": False}, [])
    assert canvas._studio_motion_mode == "static" and not canvas._timer.isActive()
    key = canvas._page_keys()[0]
    runtime = canvas._runtime[key["id"]]
    with patch.object(canvas, "_emit_switch_sound") as sounds, patch.object(canvas, "_play"):
        canvas._keyboard_held["A"] = key["id"]
        canvas._press_runtime(key, runtime, None)
        canvas._ensure_timer()
        assert runtime.visual.travel == 1.0
        canvas._release_runtime(key, runtime)
        canvas._keyboard_held.clear()
        canvas._ensure_timer()
        assert sounds.call_count == 2
    assert not canvas._timer.isActive()
    assert deck._deck_data.get("reduce_motion", False) == preference


def test_waiting_stack_filter_and_find_select_the_requested_page(studio):
    host, manager, service, ids = studio
    group = service.stacks.create(ids[:2], "상태")
    dialog = OverlayManagerDialog(manager, host)
    dialog.show()
    dialog.visibility_combo.setCurrentIndex(dialog.visibility_combo.findData("waiting"))
    assert not dialog._cards[ids[1]].isHidden() and dialog._cards[ids[0]].isHidden()
    dialog._on_focus(ids[1])
    _APP.processEvents()
    assert service.stacks.groups[0]["id"] == group and service.stacks.groups[0]["index"] == 1
    assert not dialog._cards[ids[0]].isHidden() and dialog._cards[ids[1]].isHidden()
    dialog.close()
    dialog.deleteLater()


def test_manager_entry_reuses_closed_dialog_instead_of_accumulating_windows(studio):
    from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin

    host, _, _, _ = studio
    host.init_overlay_manager = lambda: None
    MainWindowUiActionsMixin.open_widget_manager(host)
    first = host._widget_manager_dlg
    first.close()
    _APP.processEvents()
    MainWindowUiActionsMixin.open_widget_manager(host)
    assert host._widget_manager_dlg is first and first.isVisible()
    assert len(host.findChildren(OverlayManagerDialog)) == 1
    first.close()
