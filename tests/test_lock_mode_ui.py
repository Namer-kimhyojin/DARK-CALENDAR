import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QToolButton,
    QWidget,
)

from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin


class FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        if type is not None and value is not None:
            return type(value)
        return value

    def setValue(self, key, value):
        self.values[key] = value


class TrackingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.raise_calls = 0

    def raise_(self):
        self.raise_calls += 1
        return super().raise_()


class LockModeHost(WindowShellActionsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(900, 620)
        self.setCentralWidget(QWidget(self))
        self.settings = FakeSettings()
        self.lock_btn = QPushButton(self)
        self.lock_btn.setCheckable(True)
        self.lock_overlay = QWidget(self)
        self.lock_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._top_bar_menu_wrapper = TrackingWidget(self)
        self.top_bar_frame = TrackingWidget(self)
        self.add_menu_btn = QToolButton(self)
        self.view_menu_btn = QToolButton(self)
        self.display_menu_btn = QToolButton(self)
        self.widgets_menu_btn = QToolButton(self)
        self.sys_menu_btn = QToolButton(self)
        self.sync_action_btn = QToolButton(self)
        self.magnet_btn = QPushButton(self)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.search_edit = QLineEdit(self)
        self.widget_mode_btn = QToolButton(self)
        self._refresh_calls = []
        self.left_dock = self._make_dock("left_dock")
        self.center_dock = self._make_dock("center_dock")
        self.routine_dock = self._make_dock("routine_dock")
        self.directive_dock = self._make_dock("directive_dock")

    def _make_dock(self, name):
        dock = QDockWidget(name, self)
        dock.setObjectName(name)
        dock.setWidget(QWidget(dock))
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        return dock

    def schedule_panel_refresh(self, **kwargs):
        self._refresh_calls.append(kwargs)


class LockModeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_toggle_lock_mode_blocks_mouse_interaction_and_dock_features(self):
        host = LockModeHost()
        self.addCleanup(host.close)
        host.show()
        QApplication.processEvents()
        host.lock_btn.setChecked(True)

        host.toggle_lock_mode()
        QApplication.processEvents()

        self.assertTrue(host.lock_overlay.isVisible())
        self.assertFalse(
            host.lock_overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )
        self.assertEqual(host.rect(), host.lock_overlay.geometry())
        self.assertEqual([{"center": True}], host._refresh_calls)
        self.assertFalse(host.add_menu_btn.isEnabled())
        self.assertFalse(host.search_edit.isEnabled())
        self.assertTrue(host.lock_btn.isEnabled())
        self.assertGreater(host._top_bar_menu_wrapper.raise_calls, 0)
        self.assertGreater(host.top_bar_frame.raise_calls, 0)
        self.assertTrue(hasattr(host, "_lock_overlay_toggle_btn"))
        self.assertTrue(host._lock_overlay_toggle_btn.isVisible())
        self.assertTrue(host._lock_overlay_toggle_btn.isChecked())

        for dock in (host.left_dock, host.center_dock, host.routine_dock, host.directive_dock):
            self.assertEqual(dock.features(), QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.assertEqual(dock.allowedAreas(), Qt.DockWidgetArea.NoDockWidgetArea)
            blocker = getattr(dock, "_lock_mode_blocker", None)
            self.assertIsNotNone(blocker)
            self.assertTrue(blocker.isVisible())
            self.assertEqual(dock.rect(), blocker.geometry())

    def test_unlock_restores_overlay_and_dock_state(self):
        host = LockModeHost()
        self.addCleanup(host.close)
        host.show()
        QApplication.processEvents()
        original_features = {
            dock.objectName(): dock.features()
            for dock in (host.left_dock, host.center_dock, host.routine_dock, host.directive_dock)
        }
        original_areas = {
            dock.objectName(): dock.allowedAreas()
            for dock in (host.left_dock, host.center_dock, host.routine_dock, host.directive_dock)
        }

        host.lock_btn.setChecked(True)
        host.toggle_lock_mode()
        QApplication.processEvents()
        host._lock_overlay_toggle_btn.click()
        QApplication.processEvents()

        self.assertFalse(host.lock_overlay.isVisible())
        self.assertTrue(
            host.lock_overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )
        self.assertTrue(host.add_menu_btn.isEnabled())
        self.assertTrue(host.search_edit.isEnabled())
        self.assertTrue(host.lock_btn.isEnabled())
        self.assertFalse(host._lock_overlay_toggle_btn.isVisible())

        for dock in (host.left_dock, host.center_dock, host.routine_dock, host.directive_dock):
            self.assertEqual(dock.features(), original_features[dock.objectName()])
            self.assertEqual(dock.allowedAreas(), original_areas[dock.objectName()])
            blocker = getattr(dock, "_lock_mode_blocker", None)
            self.assertIsNotNone(blocker)
            self.assertFalse(blocker.isVisible())


if __name__ == "__main__":
    unittest.main()
