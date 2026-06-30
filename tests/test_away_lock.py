import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent, QShortcut
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QWidget

from calendar_app.presentation.dialogs.away_settings_dialog import AwaySettingsDialog
from calendar_app.presentation.main_window.away_lock_actions import AwayLockMixin


class FakeSettings:
    def __init__(self, initial=None):
        self._values = dict(initial or {})

    def value(self, key, default=None, type=None):
        value = self._values.get(key, default)
        if type is None or value is None:
            return value
        return type(value)

    def setValue(self, key, value):
        self._values[key] = value

    def remove(self, key):
        self._values.pop(key, None)


class AlarmWorkerStub:
    def __init__(self):
        self.updated_minutes = None

    def update_idle_timeout(self, minutes):
        self.updated_minutes = minutes


class AwayHost(QWidget, AwayLockMixin):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or FakeSettings()
        self.is_away_locked = False
        self._away_aux_overlays = []
        self.lock_frame = QFrame(self)
        self.lock_bg_label = QLabel(self.lock_frame)
        self.lock_clock_lbl = QLabel(self.lock_frame)
        self.lock_lbl = QLabel(self.lock_frame)
        self.lock_pw_widget = QWidget(self.lock_frame)
        self.lock_pw_edit = QLineEdit(self.lock_pw_widget)
        self.alarm_worker = AlarmWorkerStub()
        self.unlock_count = 0
        self.prompt_result = False

    def _restore_window_after_away_lock(self):
        pass

    def _restore_away_preview_settings_if_needed(self):
        pass

    def _do_away_unlock(self):
        self.unlock_count += 1
        self.is_away_locked = False
        self._remove_force_unlock_event_filter()

    def _prompt_admin_unlock_password(self, parent=None):
        return self.prompt_result


class AwaySettingsParent(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.alarm_worker = AlarmWorkerStub()


class AwayLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_password_entry_ready_enables_only_primary_overlay_input(self):
        settings = FakeSettings({"away_unlock_method": "password"})
        host = AwayHost(settings)
        self.addCleanup(host.close)
        host.is_away_locked = True

        primary_window = QWidget()
        secondary_window = QWidget()
        primary_edit = QLineEdit(primary_window)
        secondary_edit = QLineEdit(secondary_window)
        secondary_edit.setText("stale")
        host._away_aux_overlays = [
            {
                "window": primary_window,
                "pw_widget": QWidget(primary_window),
                "pw_edit": primary_edit,
                "is_current_screen": True,
            },
            {
                "window": secondary_window,
                "pw_widget": QWidget(secondary_window),
                "pw_edit": secondary_edit,
                "is_current_screen": False,
            },
        ]

        ready = host._ensure_password_entry_ready(force_activate=False)

        self.addCleanup(primary_window.close)
        self.addCleanup(secondary_window.close)
        self.assertTrue(ready)
        self.assertTrue(primary_edit.isEnabled())
        self.assertFalse(primary_edit.isReadOnly())
        self.assertFalse(secondary_edit.isEnabled())
        self.assertTrue(secondary_edit.isReadOnly())
        self.assertEqual(secondary_edit.text(), "")
        self.assertFalse(host.lock_pw_edit.isEnabled())

    def test_maintain_password_entry_focus_recovers_disabled_input(self):
        settings = FakeSettings({"away_unlock_method": "password"})
        host = AwayHost(settings)
        self.addCleanup(host.close)
        host.is_away_locked = True

        primary_window = QWidget()
        primary_edit = QLineEdit(primary_window)
        primary_edit.setEnabled(False)
        primary_edit.setReadOnly(True)
        host._away_aux_overlays = [
            {
                "window": primary_window,
                "pw_widget": QWidget(primary_window),
                "pw_edit": primary_edit,
                "is_current_screen": True,
            }
        ]

        host._maintain_password_entry_focus()

        self.addCleanup(primary_window.close)
        self.assertTrue(primary_edit.isEnabled())
        self.assertFalse(primary_edit.isReadOnly())

    def test_password_focus_target_falls_back_to_first_overlay_when_no_current_screen(self):
        settings = FakeSettings({"away_unlock_method": "password"})
        host = AwayHost(settings)
        self.addCleanup(host.close)
        host.is_away_locked = True

        first_window = QWidget()
        second_window = QWidget()
        first_edit = QLineEdit(first_window)
        second_edit = QLineEdit(second_window)
        host._away_aux_overlays = [
            {
                "window": first_window,
                "pw_widget": QWidget(first_window),
                "pw_edit": first_edit,
                "is_current_screen": False,
            },
            {
                "window": second_window,
                "pw_widget": QWidget(second_window),
                "pw_edit": second_edit,
                "is_current_screen": False,
            },
        ]

        overlay, window, edit = host._password_focus_target()

        self.addCleanup(first_window.close)
        self.addCleanup(second_window.close)
        self.assertIs(overlay, host._away_aux_overlays[0])
        self.assertIs(window, first_window)
        self.assertIs(edit, first_edit)
        self.assertTrue(host._away_aux_overlays[0]["is_current_screen"])
        self.assertFalse(host._away_aux_overlays[1]["is_current_screen"])

    def test_force_unlock_shortcut_is_kept_alive_on_overlay_window(self):
        host = AwayHost(FakeSettings())
        self.addCleanup(host.close)
        window = QWidget()

        shortcut = host._install_force_unlock_shortcut(window)

        self.addCleanup(window.close)
        self.assertIsInstance(shortcut, QShortcut)
        self.assertIs(window._away_force_unlock_shortcut, shortcut)
        self.assertIn(shortcut, host._away_force_unlock_shortcuts)
        self.assertIsInstance(host._away_main_force_unlock_shortcut, QShortcut)
        self.assertIn(host._away_main_force_unlock_shortcut, host._away_force_unlock_shortcuts)

    def test_force_unlock_event_filter_handles_ctrl_alt_shift_f12(self):
        host = AwayHost(FakeSettings())
        self.addCleanup(host.close)
        host.is_away_locked = True

        host._install_force_unlock_event_filter()
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_F12,
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier,
        )

        handled = host._away_force_unlock_filter.eventFilter(host, event)

        self.assertTrue(handled)
        self.assertEqual(host.unlock_count, 1)
        self.assertFalse(host.is_away_locked)

    def test_admin_unlock_hold_starts_only_in_hotspot(self):
        host = AwayHost(FakeSettings())
        self.addCleanup(host.close)
        host.is_away_locked = True
        overlay = {"admin_hint": QLabel()}

        started = host._begin_admin_unlock_hold(overlay, QPoint(12, 12))
        rejected = host._begin_admin_unlock_hold(overlay, QPoint(80, 80))

        self.assertTrue(started)
        self.assertFalse(rejected)
        self.assertFalse(overlay["admin_hint"].isVisible())

    def test_trigger_admin_unlock_dialog_unlocks_with_admin_password(self):
        host = AwayHost(FakeSettings())
        self.addCleanup(host.close)
        host.is_away_locked = True
        host.prompt_result = True
        overlay = {"window": QWidget(), "admin_hint": QLabel()}

        host._away_admin_hold_overlay = overlay
        host._trigger_admin_unlock_dialog()

        self.assertEqual(host.unlock_count, 1)
        self.assertFalse(host.is_away_locked)

    def test_verify_admin_unlock_password_matches_admin(self):
        host = AwayHost(FakeSettings())
        self.addCleanup(host.close)

        self.assertTrue(host._verify_admin_unlock_password("admin"))
        self.assertFalse(host._verify_admin_unlock_password("ADMIN"))

    def test_refresh_idle_lock_ui_uses_saved_color_and_opacity(self):
        settings = FakeSettings(
            {
                "away_unlock_method": "idle",
                "away_message": "Locked",
                "away_font_color": "#123456",
                "away_bg_opacity": 50,
                "away_show_clock": False,
                "font_size": 10,
            }
        )
        host = AwayHost(settings)
        self.addCleanup(host.close)
        host.lock_frame.resize(640, 480)
        host.resize(640, 480)

        host.refresh_idle_lock_ui()

        self.assertIn("#123456", host.lock_lbl.text())
        self.assertEqual(host.lock_frame.styleSheet(), "background-color: rgba(10, 10, 10, 128);")

    def test_away_settings_dialog_keeps_default_message_unchanged_on_save(self):
        settings = FakeSettings(
            {
                "away_default_message": "<p>Original default</p>",
                "away_message": "<p>Saved message</p>",
                "away_interval": 5,
                "away_unlock_method": "idle",
                "away_show_clock": True,
                "away_bg_opacity": 100,
            }
        )
        parent = AwaySettingsParent(settings)
        self.addCleanup(parent.close)

        dialog = AwaySettingsDialog(parent)
        self.addCleanup(dialog.close)
        dialog.msg_edit.setHtml("<p>Updated message</p>")
        dialog.interval_spin.setValue(7)

        saved = dialog._persist_settings()

        self.assertTrue(saved)
        self.assertEqual(settings.value("away_default_message"), "<p>Original default</p>")
        self.assertIn("Updated message", settings.value("away_message"))
        self.assertEqual(parent.alarm_worker.updated_minutes, 7)


if __name__ == "__main__":
    unittest.main()
