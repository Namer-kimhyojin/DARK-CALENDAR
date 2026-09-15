# -*- coding: utf-8 -*-
"""Built-in versus user preset manager interaction regressions."""

import os

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_APP = QApplication.instance() or QApplication([])


def test_builtin_manager_entries_are_fixed_and_user_entries_are_editable():
    owner = QWidget()
    owner.settings = QSettings("codex_test", "overlay_preset_manager_ui")
    owner.settings.clear()
    widget = OverlayClockWidget(owner)
    parent = QWidget()
    editor = QPlainTextEdit("{time}", parent)
    manager = widget._build_preset_manager(parent, editor, [("Base", "{time}")])
    combo = manager["combo"]

    combo.setCurrentIndex(1)
    _APP.processEvents()
    assert combo.currentData(Qt.ItemDataRole.UserRole + 3) == "builtin"
    assert combo.currentText() != "Base"
    assert manager["buttons"]["add"].isEnabled()
    assert not manager["buttons"]["update"].isEnabled()
    assert not manager["buttons"]["rename"].isEnabled()
    assert not manager["buttons"]["delete"].isEnabled()

    widget._save_user_presets([{"name": "Mine", "template": "{date}"}])
    manager["refresh"]("Mine", "user")
    _APP.processEvents()
    assert combo.currentData(Qt.ItemDataRole.UserRole + 3) == "user"
    assert manager["buttons"]["rename"].isEnabled()
    assert manager["buttons"]["delete"].isEnabled()
    editor.setPlainText("{date|bold}")
    assert manager["buttons"]["update"].isEnabled()

    widget.close()
    parent.close()
    owner.settings.clear()
    owner.close()


def test_manager_restores_hidden_builtin_and_migrates_legacy_override():
    owner = QWidget()
    owner.settings = QSettings("codex_test", "overlay_preset_manager_migration")
    owner.settings.clear()
    widget = OverlayClockWidget(owner)
    parent = QWidget()
    editor = QPlainTextEdit("{time}", parent)
    widget._save_user_presets([{"name": "Base", "template": "{date}"}])
    widget._save_hidden_builtins({"Base"})

    manager = widget._build_preset_manager(parent, editor, [("Base", "{time}")])
    combo = manager["combo"]
    entries = [
        (
            combo.itemData(index, Qt.ItemDataRole.UserRole + 1),
            combo.itemData(index, Qt.ItemDataRole.UserRole + 2),
            combo.itemData(index, Qt.ItemDataRole.UserRole + 3),
        )
        for index in range(1, combo.count())
    ]

    assert entries[0] == ("Base", "{time}", "builtin")
    assert entries[1][0].startswith("Base ")
    assert entries[1][1:] == ("{date}", "user")
    assert widget._load_hidden_builtins() == set()

    widget.close()
    parent.close()
    owner.settings.clear()
    owner.close()
