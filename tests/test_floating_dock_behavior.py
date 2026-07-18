import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDockWidget, QFrame, QMainWindow

from calendar_app.presentation.main_window.dock_sections.floating_dock_behavior import (
    _prepare_floating_dock_visuals,
)


class FloatingDockBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_prepare_floating_dock_visuals_keeps_dock_and_root_transparent(self):
        host = QMainWindow()
        self.addCleanup(host.close)

        dock = QDockWidget("Test Dock", host)
        frame = QFrame()
        dock.setWidget(frame)
        self.addCleanup(dock.close)

        _prepare_floating_dock_visuals(dock)

        self.assertTrue(dock.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(dock.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground))
        self.assertIn("QDockWidget", dock.styleSheet())
        self.assertIn("background: transparent", dock.styleSheet())

        self.assertTrue(frame.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertIn("background: transparent", frame.styleSheet())


if __name__ == "__main__":
    unittest.main()
