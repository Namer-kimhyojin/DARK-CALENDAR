# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from calendar_app.presentation.widgets.overlay_base import _BaseOverlayWidget


class _SettingsStub:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, type=None):  # noqa: A002
        value = self.values.get(key, default)
        return type(value) if type is not None else value


class _Owner(QWidget):
    def __init__(self, values=None):
        super().__init__()
        self.settings = _SettingsStub(values)


class _TestOverlay(_BaseOverlayWidget):
    _PREFIX = "overlay_test"

    def _settings_prefix(self):
        return self._PREFIX

    def _build_face(self):
        return QFrame()

    def _apply_appearance(self):
        return None


class OverlayAlwaysOnTopRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_saved_false_is_applied_before_window_creation(self):
        owner = _Owner({"overlay_test_always_on_top": False})
        widget = _TestOverlay(owner)
        self.addCleanup(widget.close)
        self.addCleanup(owner.close)

        self.assertFalse(bool(widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

    def test_default_remains_always_on_top(self):
        owner = _Owner()
        widget = _TestOverlay(owner)
        self.addCleanup(widget.close)
        self.addCleanup(owner.close)

        self.assertTrue(bool(widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))


if __name__ == "__main__":
    unittest.main()
