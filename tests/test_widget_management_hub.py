# -*- coding: utf-8 -*-
"""Management queries preserve state; actions reuse existing widget and mode routes."""

from unittest.mock import Mock, patch

from PyQt6.QtCore import QEvent, QPoint, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QMenu, QPushButton, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog
from calendar_app.presentation.widgets.widget_management_ui import WidgetAddDialog
from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)
from tests.test_widget_mode_ux import _APP, Host


class SampleWidget(QWidget):
    def __init__(self, enabled):
        super().__init__()
        self.enabled = enabled
        self.locked = False
        self._open_settings = Mock()
        self._open_graphic_collections = Mock()
        self._action_reset_position = Mock()
        self.save_position = Mock()

    def is_enabled(self):
        return self.enabled

    def placement_is_locked(self):
        return self.locked

    def _set_placement_locked(self, value):
        self.locked = value


class SampleManager:
    def __init__(self, host):
        self._owner = host
        self.rows = [
            ("clock_0", "회의실 시계", "clock", SampleWidget(True)),
            ("text_0", "업무 메모", "text", SampleWidget(False)),
            ("clock_1", "집중 시계", "clock", SampleWidget(True)),
        ]
        self.listeners = []
        self.renames = []
        self._ui_remove_with_confirm = Mock()
        self._ui_remove_all_with_confirm = Mock()

    def _settings(self):
        return self._owner.settings

    def add_listener(self, callback):
        self.listeners.append(callback)

    def remove_listener(self, callback):
        self.listeners.remove(callback)

    def all_instances(self):
        return list(self.rows)

    def notify(self):
        for callback in list(self.listeners):
            callback()

    def get_widget(self, iid):
        return next((row[3] for row in self.rows if row[0] == iid), None)

    def show_instance(self, iid):
        widget = self.get_widget(iid)
        widget.enabled = True
        widget.show()
        self.notify()

    def hide_instance(self, iid):
        widget = self.get_widget(iid)
        widget.enabled = False
        widget.hide()
        self.notify()

    def rename_instance(self, iid, name):
        self.renames.append((iid, name))
        self.rows = [
            (key, name if key == iid else old, kind, widget) for key, old, kind, widget in self.rows
        ]
        self.notify()

    def add_instance(self, kind, name):
        iid = kind + "_new"
        self.rows.append((iid, name or kind, kind, SampleWidget(False)))
        self.notify()
        return iid

    def duplicate_instance(self, iid):
        return self.add_instance("clock", "copy")


@pytest.fixture
def hub(tmp_path):
    host = Host()
    host.settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    coordinator = WidgetModeCoordinator(host)
    coordinator.controller.refresh_data = lambda: None
    host._widget_mode_coordinator = coordinator
    manager = SampleManager(host)
    dialog = OverlayManagerDialog(manager, host)
    host.show()
    dialog.show()
    _APP.processEvents()
    yield dialog, manager, host, coordinator
    dialog.close()
    coordinator.close_for_shutdown()
    for row in manager.rows:
        row[3].close()
        row[3].deleteLater()
    if coordinator.controller.widget is not None:
        coordinator.controller.widget.deleteLater()
    host.close()
    host.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()


def _matching(dialog):
    return {iid for iid, card in dialog._cards.items() if not card.isHidden()}


def _prefs(host):
    return {key: host.settings.value(key) for key in host.settings.allKeys()}


def test_search_and_visibility_filters_are_read_only_and_compose(hub):
    dialog, _, host, _ = hub
    before = _prefs(host)
    dialog.search_edit.setText("시계")
    assert _matching(dialog) == {"clock_0", "clock_1"}
    dialog.visibility_combo.setCurrentIndex(2)
    assert not _matching(dialog) and not dialog._empty_lbl.isHidden()
    dialog.search_edit.clear()
    assert _matching(dialog) == {"text_0"}
    dialog.visibility_combo.setCurrentIndex(1)
    assert _matching(dialog) == {"clock_0", "clock_1"}
    assert _prefs(host) == before


def test_notifications_coalesce_and_keep_editor_and_scroll(hub):
    dialog, manager, _, _ = hub
    card = dialog._cards["clock_0"]
    card.name_edit.setFocus()
    card.name_edit.setText("아직 입력 중")
    card.name_edit.setModified(True)
    before = dialog._scroll.verticalScrollBar().value()
    with patch.object(dialog, "_apply_filters", wraps=dialog._apply_filters) as refresh:
        for _ in range(30):
            manager.notify()
        assert not refresh.called
        _APP.processEvents()
        assert refresh.call_count == 1
    assert dialog._cards["clock_0"] is card
    assert card.name_edit.text() == "아직 입력 중"
    assert dialog._scroll.verticalScrollBar().value() == before


def test_rename_commits_only_changes_and_rejects_empty(hub):
    dialog, manager, _, _ = hub
    card = dialog._cards["clock_0"]
    dialog._on_rename("clock_0", "회의실 시계")
    assert not manager.renames
    card.name_edit.setText(" ")
    dialog._on_rename("clock_0", " ")
    assert card.name_edit.text() == "회의실 시계"
    dialog._on_rename("clock_0", " 새 이름 ")
    assert manager.renames == [("clock_0", "새 이름")]
    _APP.processEvents()
    assert dialog._cards["clock_0"] is card


def test_enter_in_name_field_saves_without_triggering_other_actions(hub):
    dialog, manager, _, _ = hub
    card = dialog._cards["clock_0"]
    card.name_edit.setFocus()
    card.name_edit.setText("Enter로 저장")
    with patch.object(WidgetAddDialog, "exec") as gallery:
        QTest.keyClick(card.name_edit, Qt.Key.Key_Return)
        _APP.processEvents()
        assert not gallery.called
    assert manager.renames == [("clock_0", "Enter로 저장")]
    assert not manager.get_widget("text_0").enabled


def test_actions_route_the_original_id_and_existing_confirmations(hub):
    dialog, manager, _, _ = hub
    card = dialog._cards["text_0"]
    card.graphics_button.click()
    manager.get_widget("text_0")._open_graphic_collections.assert_called_once()
    dialog._on_settings("text_0")
    manager.get_widget("text_0")._open_settings.assert_called_once()
    card.lock_action.trigger()
    assert manager.get_widget("text_0").locked
    dialog._on_delete("text_0")
    manager._ui_remove_with_confirm.assert_called_once_with("text_0", parent_widget=dialog)
    dialog._delete_all()
    manager._ui_remove_all_with_confirm.assert_called_once_with(parent_widget=dialog)


def test_find_recovers_hidden_widget_on_the_manager_screen(hub):
    dialog, manager, _, _ = hub
    widget = manager.get_widget("text_0")
    dialog._on_focus("text_0")
    assert widget.is_enabled() and widget.isVisible()
    assert dialog.screen().availableGeometry().contains(widget.frameGeometry().center())
    widget.save_position.assert_called_once()


def test_filtered_bulk_actions_explicitly_apply_to_all_instances(hub):
    dialog, manager, _, _ = hub
    dialog.search_edit.setText("메모")
    dialog._hide_all()
    _APP.processEvents()
    assert not any(row[3].enabled for row in manager.rows)
    dialog._show_all()
    _APP.processEvents()
    assert all(row[3].enabled for row in manager.rows)
    assert dialog.search_edit.text() == "메모"


def test_gallery_cancel_never_creates_a_widget_and_add_reveals_the_new_row(hub):
    dialog, manager, _, _ = hub
    with patch.object(WidgetAddDialog, "exec", return_value=QDialog.DialogCode.Rejected):
        dialog._add_instance()
    assert len(manager.rows) == 3
    dialog.search_edit.setText("no match")
    dialog.visibility_combo.setCurrentIndex(2)
    with (
        patch.object(WidgetAddDialog, "exec", return_value=QDialog.DialogCode.Accepted),
        patch.object(WidgetAddDialog, "selection", return_value=("text", "새 메모")),
    ):
        dialog._add_instance()
    assert len(manager.rows) == 4 and manager.get_widget("text_new").enabled
    assert "text_new" in _matching(dialog)
    assert dialog.search_edit.text() == ""


def test_gallery_native_keyboard_selection_and_optional_name(hub):
    dialog, _, _, _ = hub
    gallery = WidgetAddDialog(dialog)
    assert len(gallery.kind_buttons) == 9
    button = gallery.kind_buttons["weather"]
    gallery.show()
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    gallery.name_edit.setText(" 서울 날씨 ")
    assert gallery.selection() == ("weather", "서울 날씨")
    gallery.reject()
    gallery.deleteLater()


def test_removed_instances_are_the_only_rows_replaced(hub):
    dialog, manager, _, _ = hub
    stable = dialog._cards["clock_0"]
    manager.rows.pop(1)
    manager.notify()
    _APP.processEvents()
    assert "text_0" not in dialog._cards and dialog._cards["clock_0"] is stable


def test_closed_manager_releases_listener_and_resubscribes_once(hub):
    dialog, manager, _, _ = hub
    manager.notify()
    dialog.close()
    assert not manager.listeners and not dialog._refresh_timer.isActive()
    dialog.show()
    assert manager.listeners == [dialog._sync_from_manager]


def test_escape_hides_manager_without_leaving_background_refreshes(hub):
    dialog, manager, _, _ = hub
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert not manager.listeners and not dialog._refresh_timer.isActive()
    manager.notify()
    assert not dialog._refresh_timer.isActive()
    dialog.show()
    assert manager.listeners == [dialog._sync_from_manager]


def test_mode_overview_is_read_only_and_lifecycle_uses_existing_coordinator(hub):
    dialog, _, host, coordinator = hub
    before = _prefs(host)
    dialog.tabs.setCurrentIndex(1)
    dialog.mode_panel.refresh()
    assert coordinator.controller.widget is None
    assert _prefs(host) == before
    assert not dialog.mode_panel.return_button.isEnabled()
    dialog.mode_panel._enter()
    assert coordinator.state is WidgetModeState.ACTIVE
    assert not host.isVisible() and coordinator.controller.is_visible()
    assert host.settings.value("widget_mode_resume", type=bool)
    coordinator.hide_to_tray()
    dialog.mode_panel.refresh()
    assert dialog.mode_panel.return_button.isEnabled()
    dialog.mode_panel._enter()
    assert coordinator.controller.is_visible()
    dialog.mode_panel._return_main()
    assert coordinator.state is WidgetModeState.CLOSED and host.isVisible()
    assert not host.settings.value("widget_mode_resume", type=bool)


@pytest.mark.parametrize("free", [False, True])
def test_editors_cancel_without_entering_mode_or_changing_preferences(hub, free):
    dialog, _, host, coordinator = hub
    if free:
        host.settings.setValue("widget_mode_layout_mode", "free")
    before = _prefs(host)
    from calendar_app.presentation.dialogs.widget_customization_dialog import (
        WidgetCustomizationDialog,
    )
    from calendar_app.presentation.dialogs.widget_free_layout_editor import (
        WidgetFreeLayoutEditorDialog,
    )

    cls = WidgetFreeLayoutEditorDialog if free else WidgetCustomizationDialog
    with patch.object(cls, "exec", lambda self: self.reject()):
        (dialog.mode_panel._edit_free if free else dialog.mode_panel._customize)()
    assert coordinator.state is WidgetModeState.CLOSED
    assert host.isVisible() and not coordinator.controller.is_visible()
    assert _prefs(host) == before


def test_primary_buttons_fit_at_minimum_width(hub):
    dialog, _, _, _ = hub
    dialog.resize(760, 580)
    _APP.processEvents()
    card = dialog._cards["clock_0"]
    for button in (card.find_button, card.graphics_button, card.more_button, card.toggle):
        point = button.mapTo(dialog, QPoint())
        assert point.x() >= 0 and point.x() + button.width() <= dialog.width()


def test_common_style_survives_profile_theme_refresh(hub):
    dialog, _, host, _ = hub
    host.settings.setValue("theme_color", "#c3a1f6")
    host.settings.setValue("text_theme", "dark")
    host.settings.setValue("panel_base_color", "#131b2a")
    host.settings.setValue("dialog_token.metric.button_height", 41)
    dialog.hide()
    dialog.show()
    _APP.processEvents()

    assert dialog.styleSheet().count("/* DC_DIALOG_BASE */") == 1
    assert dialog._tok["accent"] == "#c3a1f6"
    assert dialog._tok["btn_h"] == 41
    assert dialog._header_frame.property("role") == "dialogHeader"
    assert all(card.property("role") == "dialogCard" for card in dialog._cards.values())


def test_widget_workspace_more_menu_offers_direct_manager_entry(hub):
    _, _, host, coordinator = hub
    host.open_widget_manager = Mock()
    widget = coordinator.controller.ensure_widget()
    with patch.object(QMenu, "exec", return_value=None):
        widget._open_menu(QPoint())
    menus = widget.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly)
    actions = menus[-1].actions()
    assert actions[0].text() == t("widget_manager.title", "위젯 관리자")
    actions[0].trigger()
    host.open_widget_manager.assert_called_once()
