# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)

from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    BulkOperationsDialog,
    ChecklistItemEditDialog,
)
from calendar_app.presentation.dialogs.color_swatch_widget import (
    ColorSwatchPopup,
    GoogleColorSwatch,
    _color_swatch_button_shell_stylesheet,
    _color_swatch_popup_stylesheet,
    _color_swatch_theme_bundle,
)
from calendar_app.presentation.dialogs.dialog_token_editor_dialog import DialogTokenEditorDialog
from calendar_app.presentation.dialogs.focus_log_dialog import FocusLogDialog
from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog
from calendar_app.presentation.dialogs.label_settings_dialog import LabelSettingsDialog
from calendar_app.presentation.dialogs.time_picker_widget import (
    TimePickerWidget,
    _time_picker_metric_bundle,
)
from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow
from calendar_app.presentation.widgets.command_palette import CommandPalette
from calendar_app.presentation.widgets.overlay_base import _apply_span
from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget


def _safe_close(widget):
    import contextlib

    with contextlib.suppress(RuntimeError):
        widget.close()


class DialogEditorWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_time_picker_uses_dialog_metric_bundle(self):
        metrics = {"field_height": 40, "field_padding_x": 12}

        bundle = _time_picker_metric_bundle(metrics)
        widget = TimePickerWidget(metrics=metrics)
        self.addCleanup(widget.close)

        self.assertEqual(bundle["min_height"], 40)
        self.assertEqual(bundle["max_height"], 44)
        self.assertEqual(bundle["min_width"], 104)
        self.assertEqual(widget.minimumHeight(), 40)
        self.assertEqual(widget.maximumHeight(), 44)
        self.assertEqual(widget.minimumWidth(), 104)
        self.assertEqual(widget.objectName(), "TaskTimeEdit")

    def test_color_swatch_and_popup_follow_dialog_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft_border": "rgba(34,195,202,110)",
            "surface_alt": "rgba(12,24,36,220)",
            "surface_item": "rgba(18,30,42,220)",
            "border": "rgba(255,255,255,0.16)",
            "text_primary": "#eff4fa",
            "danger_hex": "#d25a66",
        }
        metrics = {
            "field_radius": 9,
            "field_padding_x": 14,
            "field_padding_y": 5,
            "button_height": 42,
        }
        shape = {"context_menu_radius": 12}

        theme = _color_swatch_theme_bundle(tokens=tokens, metrics=metrics, shape=shape)
        popup_qss = _color_swatch_popup_stylesheet(theme)
        swatch = GoogleColorSwatch(tokens=tokens, metrics=metrics, shape=shape)
        popup = ColorSwatchPopup("#a4bdfc", tokens=tokens, metrics=metrics, shape=shape)
        self.addCleanup(swatch.close)
        self.addCleanup(popup.close)

        self.assertEqual(theme["popup_bg"], "rgba(12,24,36,220)")
        self.assertEqual(theme["popup_border"], "rgba(34,195,202,110)")
        self.assertEqual(theme["popup_radius"], 12)
        self.assertEqual(theme["swatch_diameter"], 24)
        self.assertIn("min-width: 0px;", theme["button_shell"])
        self.assertIn("padding: 0px;", theme["button_shell"])
        self.assertIn("background: rgba(12,24,36,220);", popup_qss)
        self.assertIn("border-radius: 12px;", popup_qss)
        self.assertEqual(popup.styleSheet(), popup_qss)
        self.assertEqual(swatch._buttons[0]._theme["none_fill"], "rgba(18,30,42,220)")
        self.assertEqual(swatch._buttons[0].width(), 28)

        swatch.apply_dialog_theme(
            metrics={"button_height": 34, "field_padding_y": 4}, shape=shape, tokens=tokens
        )
        self.assertEqual(swatch._buttons[0].width(), 24)

    def test_color_swatch_bundle_merges_partial_dialog_defaults(self):
        baseline = _color_swatch_theme_bundle()
        partial = _color_swatch_theme_bundle(tokens={"accent": "#22c3ca"})

        self.assertEqual(partial["popup_bg"], baseline["popup_bg"])
        self.assertEqual(partial["none_fill"], baseline["none_fill"])
        self.assertEqual(partial["popup_border"], baseline["popup_border"])
        self.assertEqual(partial["none_ring"], "#22c3ca")
        self.assertEqual(partial["button_shell"], _color_swatch_button_shell_stylesheet())

    def test_checklist_subdialogs_use_editor_token_shell(self):
        parent = QWidget()
        parent._ui_tokens = {
            "accent": "#22c3ca",
            "surface_item": "rgba(12,24,36,220)",
            "surface_hover": "rgba(18,30,42,220)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
        }
        item_dialog = ChecklistItemEditDialog(template_id=1, parent=parent)
        bulk_dialog = BulkOperationsDialog(template_id=1, parent=parent)
        self.addCleanup(_safe_close, item_dialog)
        self.addCleanup(_safe_close, bulk_dialog)
        self.addCleanup(_safe_close, parent)

        self.assertEqual(item_dialog.objectName(), "TaskEditorDialog")
        self.assertIn("QDialog#TaskEditorDialog", item_dialog.styleSheet())
        self.assertIsNotNone(item_dialog.findChild(QLineEdit, "TaskTitleEdit"))
        self.assertIsNotNone(item_dialog.findChild(QCheckBox, "TaskDialogOptionCheck"))
        item_save = item_dialog.findChild(QPushButton, "primary_btn")
        item_cancel = item_dialog.findChild(QPushButton, "ghost_btn")
        self.assertIsNotNone(item_save)
        self.assertIsNotNone(item_cancel)
        self.assertIn("color:", item_save.styleSheet())
        self.assertIn("color:", item_cancel.styleSheet())

        self.assertEqual(bulk_dialog.objectName(), "TaskEditorDialog")
        self.assertIn("QLabel#TaskDialogFieldLabel", bulk_dialog.styleSheet())
        bulk_apply = bulk_dialog.findChild(QPushButton, "primary_btn")
        bulk_cancel = bulk_dialog.findChild(QPushButton, "ghost_btn")
        self.assertIsNotNone(bulk_apply)
        self.assertIsNotNone(bulk_cancel)
        self.assertIn("color:", bulk_apply.styleSheet())
        self.assertIn("color:", bulk_cancel.styleSheet())

    def test_gcal_main_dialog_inputs_use_runtime_token_styles(self):
        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogInputStyles")

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)

        self.assertIn("QLineEdit {", dialog.creds_path_edit.styleSheet())
        self.assertIn("QLineEdit {", dialog.cal_id_edit.styleSheet())
        self.assertIn("QComboBox {", dialog.calendar_choice_combo.styleSheet())
        self.assertIn(
            "QAbstractItemView, QListView", dialog.calendar_choice_combo.view().styleSheet()
        )
        self.assertIn("QSpinBox {", dialog.interval_spin.styleSheet())
        self.assertIn("QSpinBox {", dialog.quick_interval_spin.styleSheet())
        self.assertIn("QComboBox {", dialog.timezone_combo.styleSheet())
        self.assertIn("QLineEdit {", dialog.timezone_combo.lineEdit().styleSheet())
        self.assertIn("QAbstractItemView, QListView", dialog.timezone_combo.view().styleSheet())
        self.assertIn("QCheckBox {", dialog.enable_cb.styleSheet())
        self.assertIn("QFrame#statusBar", dialog.findChild(QFrame, "statusBar").styleSheet())
        self.assertIn("QFrame#sidebar", dialog.findChild(QFrame, "sidebar").styleSheet())
        self.assertIn("QWidget#contentArea", dialog.findChild(QWidget, "contentArea").styleSheet())
        first_scroll = dialog.findChild(QScrollArea)
        self.assertIsNotNone(first_scroll)
        self.assertIn("QScrollBar:vertical", first_scroll.styleSheet())

    def test_gcal_browse_creds_allows_sequential_changes_without_native_dialog(self):
        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogBrowseCreds")

        class _FakeFileDialog:
            class FileMode:
                ExistingFile = "existing"

            class AcceptMode:
                AcceptOpen = "open"

            class ViewMode:
                Detail = "detail"

            class Option:
                DontUseNativeDialog = "dont_use_native"

            instances = []
            next_files = [
                [r"C:\cred_a\credentials.json"],
                [r"D:\cred_b\credentials.json"],
            ]

            def __init__(self, parent, title, start_dir, name_filter):
                self.parent = parent
                self.title = title
                self.start_dir = start_dir
                self.name_filter = name_filter
                self.options = {}
                self.selected = _FakeFileDialog.next_files[len(_FakeFileDialog.instances)]
                _FakeFileDialog.instances.append(self)

            def setFileMode(self, mode):
                self.file_mode = mode

            def setAcceptMode(self, mode):
                self.accept_mode = mode

            def setViewMode(self, mode):
                self.view_mode = mode

            def setModal(self, modal):
                self.modal = modal

            def setWindowModality(self, modality):
                self.window_modality = modality

            def setOption(self, option, value=True):
                self.options[option] = value

            def exec(self):
                return QDialog.DialogCode.Accepted

            def selectedFiles(self):
                return list(self.selected)

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)
        dialog.creds_path_edit.clear()

        with patch(
            "calendar_app.presentation.dialogs.gcal_settings_dialog.QFileDialog", _FakeFileDialog
        ):
            dialog.browse_creds()
            dialog.browse_creds()

        self.assertEqual(dialog.creds_path_edit.text(), r"D:\cred_b\credentials.json")
        self.assertFalse(dialog._browse_creds_open)
        self.assertEqual(len(_FakeFileDialog.instances), 2)
        self.assertEqual(_FakeFileDialog.instances[0].start_dir, "")
        self.assertEqual(_FakeFileDialog.instances[1].start_dir, r"C:\cred_a")
        self.assertTrue(
            _FakeFileDialog.instances[0].options[_FakeFileDialog.Option.DontUseNativeDialog]
        )
        self.assertEqual(
            _FakeFileDialog.instances[0].file_mode, _FakeFileDialog.FileMode.ExistingFile
        )

    def test_gcal_status_meta_resolves_primary_alias_to_real_calendar_name(self):
        class _CalendarListApi:
            def get(self, calendarId):
                self.calendar_id = calendarId
                return self

            def execute(self):
                return {"id": "aplus.mylife@gmail.com"}

        class _SyncStub:
            def __init__(self):
                self.is_authenticated = True
                self.service = self

            def calendarList(self):
                return _CalendarListApi()

            def list_accessible_calendars(self):
                return [
                    {"id": "family@example.com", "summary": "가족", "primary": False},
                    {"id": "aplus.mylife@gmail.com", "summary": "이차진자님", "primary": True},
                ]

        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogMetaPrimary")
                self.gcal_sync = _SyncStub()

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)

        dialog.cal_id_edit.setText("primary")
        dialog._refresh_meta()

        self.assertEqual(dialog.account_meta[1].text(), "aplus.mylife@gmail.com")
        self.assertEqual(dialog.calendar_meta[1].text(), "이차진자님")
        self.assertEqual(dialog.calendar_meta[1].toolTip(), "aplus.mylife@gmail.com")

    def test_gcal_status_meta_hides_unresolved_primary_alias(self):
        class _CalendarListApi:
            def get(self, calendarId):
                raise RuntimeError("primary not available")

        class _SyncStub:
            def __init__(self):
                self.is_authenticated = True
                self.service = self

            def calendarList(self):
                return _CalendarListApi()

            def list_accessible_calendars(self):
                return [
                    {"id": "family@example.com", "summary": "가족", "primary": False},
                ]

        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogMetaUnresolved")
                self.gcal_sync = _SyncStub()

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)

        dialog.cal_id_edit.setText("primary")
        dialog._calendar_choices = []
        dialog._refresh_meta()

        self.assertEqual(dialog.calendar_meta[1].text(), "-")
        self.assertEqual(dialog.calendar_meta[1].toolTip(), "")

    def test_gcal_calendar_row_uses_fixed_action_button_styles_and_smaller_name_font(self):
        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogCalendarRowStyle")

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)

        row = dialog._make_calendar_row_widget(
            {
                "id": "local::family",
                "name": "아주 긴 캘린더 이름 테스트",
                "type": "local",
                "color": "#4da6ff",
                "is_default": 0,
                "is_visible": 1,
            }
        )
        self.addCleanup(_safe_close, row)

        name_lbl = row.findChild(QLabel, "calendarNameLabel")
        default_btn = row.findChild(QPushButton, "calendarDefaultButton")
        vis_btn = row.findChild(QPushButton, "calendarVisibilityButton")
        edit_btn = row.findChild(QPushButton, "calendarEditButton")
        del_btn = row.findChild(QPushButton, "calendarDeleteButton")

        self.assertIsNotNone(name_lbl)
        self.assertIsNotNone(default_btn)
        self.assertIsNotNone(vis_btn)
        self.assertIsNotNone(edit_btn)
        self.assertIsNotNone(del_btn)
        self.assertIn("font-size: 13px", name_lbl.styleSheet())
        self.assertIn("min-width: 26px", default_btn.styleSheet())
        self.assertIn("#1e2536", default_btn.styleSheet())
        self.assertIn("rgba(77, 166, 255, 0.16)", vis_btn.styleSheet())
        self.assertIn("#1e2536", edit_btn.styleSheet())
        self.assertIn("rgba(210, 90, 102, 0.16)", del_btn.styleSheet())
        for button in (default_btn, vis_btn, edit_btn, del_btn):
            self.assertTrue(button.accessibleName())
            self.assertEqual(button.accessibleDescription(), button.accessibleName())

    def test_gcal_run_auth_auto_refreshes_google_calendar_list(self):
        class _SyncStub:
            def __init__(self):
                self.is_authenticated = False
                self.service = None

            def authenticate(self, _parent):
                self.is_authenticated = True
                self.service = object()
                return True

            def list_accessible_calendars(self):
                return [
                    {
                        "id": "aplus.mylife@gmail.com",
                        "summary": "내 캘린더",
                        "primary": True,
                        "accessRole": "owner",
                        "timeZone": "Asia/Seoul",
                    }
                ]

        class _DummyParent(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "GCalSettingsDialogRunAuthRefresh")
                self.gcal_sync = None

        parent = _DummyParent()
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(_safe_close, dialog)
        self.addCleanup(_safe_close, parent)

        sync_stub = _SyncStub()
        refresh_calls = []

        with (
            patch(
                "calendar_app.infrastructure.google_sync.service.prepare_calendar_sync_service",
                return_value=sync_stub,
            ),
            patch.object(dialog, "_copy_credentials_if_needed", return_value=True),
            patch.object(
                dialog,
                "_refresh_google_calendar_list",
                side_effect=lambda _=None, *, notify=True, show_empty_message=True: (
                    refresh_calls.append((notify, show_empty_message))
                ),
            ),
            patch("calendar_app.presentation.dialogs.gcal_settings_dialog.QMessageBox.information"),
        ):
            dialog.run_auth()

        self.assertTrue(dialog.enable_cb.isChecked())
        self.assertIs(parent.gcal_sync, sync_stub)
        self.assertEqual(refresh_calls, [(False, False)])

    def test_command_palette_uses_shared_token_styles(self):
        class _PaletteHost(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "CommandPaletteStyles")
                self.settings.setValue("theme_color", "#22c3ca")
                self.settings.setValue("panel_base_color", "#101820")
                self.settings.setValue("text_theme", "dark")

        host = _PaletteHost()
        palette = CommandPalette(parent=host)
        self.addCleanup(_safe_close, palette)
        self.addCleanup(_safe_close, host)

        self.assertIn("#palette_container", palette.styleSheet())
        self.assertIn("#22c3ca", palette.styleSheet())
        self.assertEqual(palette.nlp_preview.objectName(), "palettePreview")
        self.assertEqual(palette.divider.objectName(), "paletteDivider")
        self.assertEqual(palette.hint_bar.objectName(), "paletteHintBar")
        self.assertEqual(palette.hint_label.objectName(), "paletteHintLabel")

    def test_overlay_manager_dialog_uses_runtime_style_bundle(self):
        class _WidgetStub:
            def __init__(self, enabled=True):
                self._enabled = enabled

            def is_enabled(self):
                return self._enabled

        class _ManagerStub:
            def __init__(self):
                self._listeners = []

            def add_listener(self, listener):
                self._listeners.append(listener)

            def remove_listener(self, listener):
                if listener in self._listeners:
                    self._listeners.remove(listener)

            def all_instances(self):
                return [("clock_0", "Desk Clock", "clock", _WidgetStub(True))]

        manager = _ManagerStub()
        dialog = OverlayManagerDialog(manager=manager)
        self.addCleanup(_safe_close, dialog)

        # Styles are applied via a single dialog-level stylesheet
        dlg_ss = dialog.styleSheet()
        self.assertIn("overlayManagerTitle", dlg_ss)
        self.assertIn("overlayManagerDesc", dlg_ss)
        self.assertIn("overlayManagerAddBar", dlg_ss)
        self.assertIn("overlayManagerHint", dlg_ss)
        self.assertIsNotNone(dialog.findChild(QLabel, "overlayManagerTitle"))
        self.assertIsNotNone(dialog.findChild(QLabel, "overlayManagerDesc"))
        self.assertIsNotNone(dialog.findChild(QFrame, "overlayManagerAddBar"))
        self.assertIsNotNone(dialog.findChild(QLabel, "overlayManagerHint"))

        # WidgetCard-based list (replaces old QTableWidget rows)
        cards = list(dialog._cards.values())
        self.assertEqual(len(cards), 1)
        card = cards[0]
        toggle = card.toggle
        name_edit = card.name_edit
        action_btn = card.findChild(QPushButton)
        self.assertIsNotNone(toggle)
        self.assertIsNotNone(name_edit)
        self.assertIsNotNone(action_btn)
        # toggle uses its own per-state stylesheet; name_edit uses dialog-level CSS
        self.assertIn("border-radius:", toggle.styleSheet())
        self.assertEqual(name_edit.objectName(), "cardNameEdit")

    def test_alarm_popup_uses_runtime_token_bundle(self):
        class _AlarmHost(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "AlarmPopupStyles")
                self.settings.setValue("theme_color", "#22c3ca")
                self.settings.setValue("panel_base_color", "#101820")
                self.settings.setValue("text_theme", "dark")
                self.settings.setValue("last_opacity", 20)

        host = _AlarmHost()
        popup = AlarmPopupWindow(
            {"id": 1, "name": "Review Notes", "type": "task", "location": "Desk"},
            datetime.now() + timedelta(minutes=20),
            parent=host,
        )
        self.addCleanup(_safe_close, popup)
        self.addCleanup(_safe_close, host)

        self.assertIn("QFrame#AlarmCard", popup.styleSheet())
        self.assertIn("#22c3ca", popup.styleSheet())
        self.assertIn("border-radius:", popup.styleSheet())
        self.assertIn("font-size:", popup._time_label.styleSheet())
        self.assertEqual(popup._style_bundle["card_bg"], "#101820")
        self.assertEqual(popup.windowOpacity(), 1.0)

    def test_template_color_aliases_resolve_in_preview_and_runtime(self):
        class _OverlayHost(QWidget):
            def __init__(self):
                super().__init__()
                self.settings = QSettings("CodexTests", "OverlayTemplateColorAliases")
                self.settings.setValue("theme_color", "#22c3ca")
                self.settings.setValue("panel_base_color", "#101820")
                self.settings.setValue("text_theme", "dark")

        host = _OverlayHost()
        widget = OverlayTextWidget(host)
        self.addCleanup(_safe_close, widget)
        self.addCleanup(_safe_close, host)

        alias_html = _apply_span("Alias", ["color=accent", "bold"])
        muted_html = _apply_span("Muted", ["color=muted"])
        hex_html = _apply_span("Hex", ["color=#ff00aa"])
        widget._set("label_text", "{time:%H:%M|color=accent}\\n{date:%Y.%m.%d|color=muted}")

        preview = widget._wrap_preview_html(alias_html + muted_html + hex_html)
        widget._apply_appearance()
        label_html = widget._text_label.text()

        self.assertIn("#22c3ca", preview)
        self.assertNotIn("color:accent", preview)
        self.assertNotIn("color:muted", preview)
        self.assertIn("#ff00aa", preview)
        self.assertIn("#22c3ca", label_html)
        self.assertNotIn("color:accent", label_html)
        self.assertNotIn("color:muted", label_html)
        self.assertIn('<span style="color:#22c3ca', label_html)

    def test_focus_log_dialog_uses_token_style_bundle(self):
        with patch(
            "calendar_app.presentation.dialogs.focus_log_dialog.focus_usecases.get_focus_logs",
            return_value=[],
        ):
            dialog = FocusLogDialog()
        self.addCleanup(_safe_close, dialog)

        self.assertIn("color:", dialog.layout().itemAt(0).widget().styleSheet())
        self.assertIn("QTableWidget {", dialog.table.styleSheet())
        button_row = dialog.layout().itemAt(2).layout()
        refresh_btn = button_row.itemAt(1).widget()
        close_btn = button_row.itemAt(2).widget()
        self.assertIn("color:", refresh_btn.styleSheet())
        self.assertIn("color:", close_btn.styleSheet())

    def test_label_settings_dialog_uses_token_style_bundle(self):
        dialog = LabelSettingsDialog()
        self.addCleanup(_safe_close, dialog)

        scroll = dialog.findChild(QScrollArea)
        self.assertIsNotNone(scroll)
        self.assertIn("QScrollArea", scroll.styleSheet())
        urgent_icon, urgent_text = dialog.prio_fields["urgent"]
        self.assertIn("font-size:", urgent_icon.styleSheet())
        self.assertIn("padding:", urgent_text.styleSheet())
        self.assertIn("color:", dialog.save_btn.styleSheet())
        self.assertIn("color:", dialog.cancel_btn.styleSheet())

    def test_dialog_token_editor_uses_token_style_bundle(self):
        dialog = DialogTokenEditorDialog()
        self.addCleanup(_safe_close, dialog)

        preset_bars = [
            frame for frame in dialog.findChildren(QFrame) if frame.objectName() == "presetBar"
        ]
        self.assertGreaterEqual(len(preset_bars), 2)
        self.assertTrue(all("QFrame#presetBar" in frame.styleSheet() for frame in preset_bars))
        first_key = next(iter(dialog._color_edits))
        dialog._color_edits[first_key].setText("not-a-color")
        dialog._update_color_row(first_key)
        self.assertIn("border: 1px solid", dialog._color_edits[first_key].styleSheet())
        self.assertIn("background: transparent", dialog._color_swatches[first_key].styleSheet())

    def test_dialog_token_editor_button_metric_defaults_allow_small_values(self):
        dialog = DialogTokenEditorDialog()
        self.addCleanup(_safe_close, dialog)

        width_spin = dialog._metric_spins["button_min_width"]
        height_spin = dialog._metric_spins["button_height"]

        self.assertEqual(width_spin.value(), 45)
        self.assertEqual(height_spin.value(), 24)
        self.assertEqual(width_spin.minimum(), 15)
        self.assertEqual(height_spin.minimum(), 15)

        width_spin.setValue(15)
        height_spin.setValue(15)
        self.assertEqual(width_spin.value(), 15)
        self.assertEqual(height_spin.value(), 15)

        dialog._reset_metric_key("button_min_width")
        dialog._reset_metric_key("button_height")
        self.assertEqual(width_spin.value(), 45)
        self.assertEqual(height_spin.value(), 24)

    def test_dialog_token_editor_feedback_tracks_preview_and_apply(self):
        dialog = DialogTokenEditorDialog()
        self.addCleanup(_safe_close, dialog)

        dialog._apply_selected_color_preset()
        self.assertFalse(dialog.feedback_label.isHidden())
        self.assertEqual(dialog.feedback_label.styleSheet(), dialog._style_bundle["feedback_info"])

        first_key = next(iter(dialog._color_edits))
        dialog._color_edits[first_key].setText("not-a-color")
        dialog._refresh_preview(force=True)
        self.assertFalse(dialog.feedback_label.isHidden())
        self.assertEqual(dialog.feedback_label.text(), dialog._invalid_feedback_text())
        self.assertEqual(dialog.feedback_label.styleSheet(), dialog._style_bundle["feedback_error"])

        dialog._color_edits[first_key].setText(dialog._default_color(first_key))
        dialog._update_color_row(first_key)
        dialog._refresh_preview(force=True)
        self.assertFalse(dialog.feedback_label.isVisible())

        dialog._color_edits[first_key].setText("not-a-color")
        with (
            patch(
                "calendar_app.presentation.dialogs.dialog_token_editor_dialog.QMessageBox.warning"
            ) as warning_mock,
            patch.object(dialog, "accept") as accept_mock,
        ):
            dialog._apply()
        warning_mock.assert_called_once()
        accept_mock.assert_not_called()
        self.assertEqual(dialog.feedback_label.text(), dialog._invalid_feedback_text())
        self.assertEqual(dialog.feedback_label.styleSheet(), dialog._style_bundle["feedback_error"])

        dialog._color_edits[first_key].setText("#112233")
        dialog._update_color_row(first_key)
        with (
            patch(
                "calendar_app.presentation.dialogs.dialog_token_editor_dialog.set_dialog_token_overrides"
            ) as token_mock,
            patch(
                "calendar_app.presentation.dialogs.dialog_token_editor_dialog.set_dialog_metric_overrides"
            ) as metric_mock,
            patch.object(dialog, "accept") as accept_mock,
        ):
            dialog._apply()
        token_mock.assert_called_once()
        metric_mock.assert_called_once()
        accept_mock.assert_called_once()
        self.assertFalse(dialog.feedback_label.isHidden())
        self.assertEqual(
            dialog.feedback_label.styleSheet(), dialog._style_bundle["feedback_success"]
        )


if __name__ == "__main__":
    unittest.main()
