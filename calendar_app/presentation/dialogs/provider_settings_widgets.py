# -*- coding: utf-8 -*-
"""Small view helpers for provider setup pages and stable selection lists."""

from html import escape
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QSizePolicy


def plain_label(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label


def plain_tooltip(text):
    """Qt tooltips auto-detect HTML, even when their associated label is plain."""
    value = str(text) if text else ""
    if not any(char in value for char in "<>&"):
        return value
    return "<qt>" + escape(value).replace("\n", "<br>") + "</qt>"


def scroll_page(content):
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setFrameShape(QScrollArea.Shape.NoFrame)
    page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    page.setWidget(content)
    content.setAutoFillBackground(False)
    page.viewport().setAutoFillBackground(False)
    return page


def calendar_snapshot_key(account, available):
    return (account, json.dumps(available, sort_keys=True))


def update_calendar_items(widget, account, choices, saved):
    """Keep unsaved checks only for the same account while metadata can change."""
    from PyQt6.QtWidgets import QListWidgetItem

    saved_ids = {row["remote_id"] for row in saved if row["is_active"]}
    snapshot = (account, json.dumps(choices, sort_keys=True), tuple(sorted(saved_ids)))
    if snapshot == getattr(widget, "_provider_snapshot", None):
        return
    previous_account = getattr(widget, "_provider_account", None)
    checked = {
        widget.item(i).data(Qt.ItemDataRole.UserRole)["id"]
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    }
    old_saved = getattr(widget, "_provider_saved", set())
    drafts = getattr(widget, "_provider_drafts", {})
    if previous_account:
        drafts[previous_account] = {
            remote_id: remote_id in checked for remote_id in checked ^ old_saved
        }
    pending = drafts.get(account, {})
    current = widget.currentItem()
    current_id = current.data(Qt.ItemDataRole.UserRole)["id"] if current else None
    scroll = widget.verticalScrollBar().value()
    blocked = widget.blockSignals(True)
    widget.clear()
    for label, remote in choices:
        item = QListWidgetItem(label)
        item.setToolTip(plain_tooltip(remote["name"]))
        item.setData(Qt.ItemDataRole.UserRole, remote)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        selected = pending.get(remote["id"], remote["id"] in saved_ids)
        item.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
        widget.addItem(item)
        if remote["id"] == current_id and previous_account == account:
            widget.setCurrentItem(item)
    widget.verticalScrollBar().setValue(scroll if previous_account == account else 0)
    widget.blockSignals(blocked)
    widget._provider_snapshot = snapshot
    widget._provider_account = account
    widget._provider_saved = saved_ids
    widget._provider_drafts = drafts


def update_issue_items(widget, account, entries):
    """Unchanged status signals do not replace issue items or the comparison."""
    from PyQt6.QtWidgets import QListWidgetItem

    snapshot = (account, json.dumps(entries, sort_keys=True))
    if snapshot == getattr(widget, "_provider_snapshot", None):
        return
    current = widget.currentItem()
    role = int(Qt.ItemDataRole.UserRole)

    def identity(item):
        value = item.data(role)
        if isinstance(value, dict):
            return (
                value.get("task_id"),
                value.get("event_id"),
                value.get("calendar_id"),
                value.get("transaction_id"),
                value.get("recovery_issue"),
            )
        detail = item.data(role + 2)
        return (
            value,
            item.data(role + 1),
            detail.get("kind")
            if isinstance(detail, dict) and detail.get("recovery_issue")
            else None,
        )

    selected = identity(current) if current else None
    previous_account = getattr(widget, "_provider_account", None)
    scroll = widget.verticalScrollBar().value()
    blocked = widget.blockSignals(True)
    widget.clear()
    for label, values in entries:
        item = QListWidgetItem(label)
        for offset, value in values.items():
            item.setData(role + int(offset), value)
        widget.addItem(item)
        if previous_account == account and selected == identity(item):
            widget.setCurrentItem(item)
    widget.verticalScrollBar().setValue(scroll if previous_account == account else 0)
    widget.blockSignals(blocked)
    widget._provider_snapshot = snapshot
    widget._provider_account = account
