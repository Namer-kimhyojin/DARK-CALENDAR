# -*- coding: utf-8 -*-
"""Calendar/import fields must stay literal and never resolve rich-text resources."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QDialog, QLabel
import pytest

from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.widgets import ui_components


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=("checklist", "task", "subscription"))
def field_labels(request, monkeypatch, qapp):
    fields = {
        "name": "<b>Title &amp; name</b>",
        "location": "<i>Location</i>",
        "assignee": "<u>Assignee</u>",
        "description": "<b>Description</b>\nSecond line &amp; text",
        "calendar_id": "remote-calendar",
        "_calendar_name": "<b>Source calendar</b>",
        "_gcal_event_id": "<b>Event ID</b>",
        "_gcal_status": "<b>Unknown status</b>",
        "_gcal_updated": "<b>Updated time</b>",
    }
    if request.param == "checklist":
        row = ui_components.WrappedChecklistRow(fields["name"])
        yield [row.label]
        row.close()
        return

    if request.param == "task":
        monkeypatch.setattr(ui_components.task_repo, "get_unified_task", lambda _: fields)
        monkeypatch.setattr(ui_components.checklist_repo, "get_task_checklist_items", lambda _: [])
        monkeypatch.setattr(
            ui_components.calendar_repo,
            "get_calendar",
            lambda _: {"name": fields["_calendar_name"]},
        )
        button = ui_components.DraggableTaskButton(42, fields["name"])
        button.toggle_expand()
        labels = button.detail_container.findChildren(QLabel)
        assert {label.text() for label in labels} >= {
            fields[key] for key in ("name", "location", "assignee", "description", "_calendar_name")
        }
        yield [label for label in labels if label.text() in fields.values()]
        ui_components.get_detail_overlay()._do_collapse(button)
        button._fade_anim.stop()
        button.close()
        return

    dialogs = []

    def capture_dialog(dialog):
        dialogs.append(dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", capture_dialog)
    month_renderer._show_subscription_detail(fields)
    assert len(dialogs) == 1
    assert {label.text() for label in dialogs[0].findChildren(QLabel)} >= {
        value for key, value in fields.items() if key != "calendar_id"
    }
    yield [label for label in dialogs[0].findChildren(QLabel) if label.text() in fields.values()]
    dialogs[0].close()


def _assert_literal_selection(label, text):
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSelection(0, len(text))
    assert label.selectedText().replace("\u2029", "\n") == text


def test_fields_display_literal_markup(field_labels):
    assert field_labels
    for label in field_labels:
        assert label.textFormat() == Qt.TextFormat.PlainText
        _assert_literal_selection(label, label.text())


@pytest.mark.parametrize(
    "resource_url",
    (
        "http://127.0.0.1:9/untrusted.png",
        "file:///C:/untrusted-label-probe.png",
        "file://127.0.0.1/share/untrusted-label-probe.png",
        r"\\127.0.0.1\share\untrusted-label-probe.png",
    ),
)
def test_displayed_fields_never_resolve_image_resources(field_labels, resource_url):
    for label in field_labels:
        requests = []
        image = QImage(1, 1, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)

        def resource_provider(url, requests=requests, image=image):
            requests.append(url.toString())
            return image

        label.setResourceProvider(resource_provider)
        payload = f'<img src="{resource_url}"><b>Untrusted</b> &amp; text'
        label.setText(payload)
        label.resize(360, 100)
        label.grab()
        assert requests == []
        _assert_literal_selection(label, payload)


def test_resource_probe_detects_rich_text_loading(qapp):
    """Positive control: the same probe observes a deliberately rich-text label."""
    requests = []
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setResourceProvider(lambda url: requests.append(url.toString()) or image)
    label.setText('<img src="file:///C:/untrusted-label-probe.png">')
    label.grab()
    assert "file:///C:/untrusted-label-probe.png" in requests
    label.close()


def test_literal_checklist_label_still_toggles(qapp):
    row = ui_components.WrappedChecklistRow("<b>Checklist item</b>")
    toggles = []
    row.toggled.connect(toggles.append)
    row.label.clicked.emit()
    assert row.checkbox.isChecked()
    assert toggles == [True]
    assert row.label.text() == "<b>Checklist item</b>"
    row.close()
