import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from calendar_app.presentation.widgets.overlay_measure_utils import (
    _measure_face_height,
    _measure_face_size,
    _measure_face_size_precise,
)


class OverlayMeasureUtilsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _build_face(self):
        face = QWidget()
        layout = QVBoxLayout(face)
        lbl = QLabel("This is a long line that should wrap to multiple rows in narrow widths.")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        return face

    def test_measure_face_height_returns_positive(self):
        face = self._build_face()
        face.show()
        QApplication.processEvents()
        h = _measure_face_height(face, 120)
        self.assertGreater(h, 0)

    def test_measure_face_size_variants_return_positive(self):
        face = self._build_face()
        size_a = _measure_face_size(face, 120)
        size_b = _measure_face_size_precise(face, 120)
        self.assertGreater(size_a.width(), 0)
        self.assertGreater(size_a.height(), 0)
        self.assertGreater(size_b.width(), 0)
        self.assertGreater(size_b.height(), 0)


if __name__ == "__main__":
    unittest.main()
