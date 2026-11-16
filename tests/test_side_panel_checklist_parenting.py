# -*- coding: utf-8 -*-
"""Side-panel checklist frames are never shown as native top-level windows.

``create_task_box`` used to call ``setVisible(True)`` on an expanded checklist frame
before the box layout gave it a parent. Every right-panel render then created a native
top-level window per expanded checklist, and the reparent destroyed it again. The frame
is now shown only after ``addWidget`` parents it; its final visibility is unchanged.
"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QObject, QSettings
from PyQt6.QtWidgets import QApplication, QFrame, QPushButton, QVBoxLayout, QWidget
import pytest

from calendar_app.presentation.panels import side_panel_renderer

EXPANDED_TID = 1
COLLAPSED_TID = 2
ROUTINE_TID = 3
EMPTY_TID = 4

# Initial visibility: expanded_tids holds EXPANDED_TID, routines always start expanded.
EXPECTED_VISIBLE = {EXPANDED_TID: True, COLLAPSED_TID: False, ROUTINE_TID: True}

_APP = None


class _PanelHost(QWidget):
    def __init__(self, settings_path):
        super().__init__()
        # A private INI file: the toggle test writes expanded_task_ids, and this keeps
        # that write away from the app store even if the conftest swap is not loaded.
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.expanded_tids = {EXPANDED_TID}
        self.selected_task_ids = set()
        self.selected_directive_ids = set()


class _TopLevelChecklistShows(QObject):
    """Counts Show events a checklist frame receives while it is a window."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def eventFilter(self, obj, event):  # noqa: N802
        if (
            event.type() == QEvent.Type.Show
            and isinstance(obj, QWidget)
            and obj.objectName() == "ChecklistContainer"
            and obj.isWindow()
        ):
            self.count += 1
        return False


@pytest.fixture
def app():
    global _APP
    # One application for the module. A fixture-local one is destroyed after each test
    # while that test's host widgets may still be alive in reference cycles.
    _APP = QApplication.instance() or QApplication([])
    return _APP


@pytest.fixture
def window_shows(app):
    spy = _TopLevelChecklistShows()
    app.installEventFilter(spy)
    yield spy
    app.removeEventFilter(spy)


def _items():
    return [("first", True, lambda: None), ("second", False, lambda: None)]


def _render_boxes(host):
    boxes = {}
    for tid, routine, display in (
        (EXPANDED_TID, False, "list"),
        (COLLAPSED_TID, False, "process"),
        (ROUTINE_TID, True, "list"),
    ):
        boxes[tid] = side_panel_renderer.create_task_box(
            host,
            f"task {tid}",
            lambda *_args: None,
            checklist_items=_items(),
            tid=tid,
            is_routine=routine,
            checklist_display_type=display,
        )
    return boxes


def _show_in_host(app, host, boxes):
    layout = QVBoxLayout(host)
    for box in boxes.values():
        layout.addWidget(box)
    host.show()
    app.processEvents()


def _checklist_frame(box):
    frame = box.findChild(QFrame, "ChecklistContainer")
    assert frame is not None
    return frame


def test_checklist_frames_never_become_top_level_windows(app, window_shows, tmp_path):
    host = _PanelHost(tmp_path / "panel.ini")
    try:
        boxes = _render_boxes(host)
        app.processEvents()
        assert window_shows.count == 0
        for tid, box in boxes.items():
            frame = _checklist_frame(box)
            assert frame.parentWidget() is box
            assert frame.isVisibleTo(box) is EXPECTED_VISIBLE[tid]

        _show_in_host(app, host, boxes)
        assert window_shows.count == 0
        for tid, box in boxes.items():
            assert _checklist_frame(box).isVisible() is EXPECTED_VISIBLE[tid]
    finally:
        host.close()
        host.deleteLater()


def test_box_without_checklist_keeps_no_checklist_frame(app, window_shows, tmp_path):
    # The unused frame must not become a child of the box: it is not in the layout, so
    # a visible child would sit at (0, 0) over the title and take its clicks.
    host = _PanelHost(tmp_path / "panel.ini")
    box = side_panel_renderer.create_task_box(
        host, "no checklist", lambda *_args: None, checklist_items=[], tid=EMPTY_TID
    )
    try:
        _show_in_host(app, host, {EMPTY_TID: box})
        assert box.findChild(QFrame, "ChecklistContainer") is None
        assert window_shows.count == 0
    finally:
        host.close()
        host.deleteLater()


def test_toggle_still_flips_checklist_visibility(app, window_shows, tmp_path):
    host = _PanelHost(tmp_path / "panel.ini")
    try:
        boxes = _render_boxes(host)
        _show_in_host(app, host, boxes)
        for tid in (EXPANDED_TID, COLLAPSED_TID):
            box = boxes[tid]
            frame = _checklist_frame(box)
            toggle = box.findChild(QPushButton, "panel_checklist_toggle")
            was_visible = frame.isVisible()

            toggle.click()
            app.processEvents()
            assert frame.isVisible() is not was_visible
            assert (tid in host.expanded_tids) is not was_visible
            saved = json.loads(host.settings.value("expanded_task_ids"))
            assert (tid in saved) is not was_visible

            toggle.click()
            app.processEvents()
            assert frame.isVisible() is was_visible
            assert (tid in host.expanded_tids) is was_visible
        assert window_shows.count == 0
    finally:
        host.close()
        host.deleteLater()
