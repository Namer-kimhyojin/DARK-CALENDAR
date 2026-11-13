# -*- coding: utf-8 -*-
"""Dialogs keep an explicit stable Tool owner without changing caller ownership."""

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.dialogs import dialog_styles
from calendar_app.presentation.dialogs.dialog_chrome import (
    ensure_dialog_chrome,
    prepare_dialog_chrome,
)


@pytest.fixture
def owner(tmp_path):
    app = QApplication.instance() or QApplication([])
    host = QMainWindow()
    host.setWindowFlags(
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnBottomHint
    )
    host.settings = QSettings(str(tmp_path / "owner.ini"), QSettings.Format.IniFormat)
    style_filter = dialog_styles._CommonDialogStyleFilter(app)
    app.installEventFilter(style_filter)
    dialogs = []
    yield app, host, dialogs
    app.removeEventFilter(style_filter)
    for dialog in reversed(dialogs):
        dialog.close()
        dialog.deleteLater()
    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def ordinary(parent, dialogs):
    dialog = QDialog(parent)
    QVBoxLayout(dialog).addWidget(QLabel("Existing dialog content"))
    dialogs.append(dialog)
    return dialog


@pytest.mark.parametrize("kind", ["ordinary", "message"])
def test_shown_dialog_restores_missing_tool_transient_without_changing_widget_parent(owner, kind):
    app, host, dialogs = owner
    host.show()
    app.processEvents()
    if kind == "ordinary":
        dialog = ordinary(host, dialogs)
    else:
        dialog = QMessageBox(host)
        dialogs.append(dialog)
        dialog.setText("Existing message")
        dialog.setStandardButtons(QMessageBox.StandardButton.No)
    before_flags = host.windowFlags()
    dialog.show()
    app.processEvents()
    assert dialog.parentWidget() is host
    assert dialog.windowHandle().transientParent() is host.windowHandle()
    assert host.windowFlags() == before_flags


def test_preparation_waits_for_native_creation_and_controller_covers_explicit_style(owner):
    app, host, dialogs = owner
    host.show()
    dialog = ordinary(host, dialogs)
    assert dialog.windowHandle() is None
    prepare_dialog_chrome(dialog, settings=host.settings)
    ensure_dialog_chrome(dialog, settings=host.settings)
    assert dialog.windowHandle() is None
    dialog.show()
    app.processEvents()
    assert dialog.windowHandle().transientParent() is host.windowHandle()


def test_existing_explicit_manager_transient_is_preserved(owner):
    app, host, dialogs = owner
    host.show()
    manager = ordinary(host, dialogs)
    manager.show()
    dialog = ordinary(host, dialogs)
    # Task routing binds its manager after the constructor finishes its flags.
    prepare_dialog_chrome(dialog, settings=host.settings)
    ensure_dialog_chrome(dialog, settings=host.settings)
    dialog.winId()
    dialog.windowHandle().setTransientParent(manager.windowHandle())
    for _index in range(3):
        prepare_dialog_chrome(dialog, settings=host.settings)
        ensure_dialog_chrome(dialog, settings=host.settings)
    dialog.show()
    app.processEvents()
    assert dialog.parentWidget() is host
    assert dialog.windowHandle().transientParent() is manager.windowHandle()


def test_parentless_dialog_remains_parentless_with_a_tool_window_present(owner):
    app, host, dialogs = owner
    host.show()
    dialog = ordinary(None, dialogs)
    dialog.show()
    app.processEvents()
    assert dialog.parentWidget() is None
    assert dialog.windowHandle().transientParent() is None


@pytest.mark.parametrize("kind", [Qt.WindowType.Popup, Qt.WindowType.ToolTip])
def test_popup_and_tooltip_parents_keep_qt_skipped_transient_policy(owner, kind):
    _app, host, dialogs = owner
    host.winId()
    transient = QWidget(host, kind)
    dialogs.append(transient)
    transient.winId()
    dialog = ordinary(transient, dialogs)
    prepare_dialog_chrome(dialog, settings=host.settings)
    ensure_dialog_chrome(dialog, settings=host.settings)
    dialog.winId()
    assert dialog.windowHandle().transientParent() is None


def test_embedded_dialog_and_native_file_picker_are_not_given_chrome_owners(owner):
    _app, host, dialogs = owner
    embedded = ordinary(host, dialogs)
    embedded.setWindowFlags(Qt.WindowType.Widget)
    assert not prepare_dialog_chrome(embedded)
    assert embedded.windowHandle() is None
    picker = QFileDialog(host)
    dialogs.append(picker)
    assert not picker.testOption(QFileDialog.Option.DontUseNativeDialog)
    assert not prepare_dialog_chrome(picker)


def test_reused_message_keeps_no_default_results_topmost_and_owner_after_flag_change(owner):
    app, host, dialogs = owner
    host.show()
    box = QMessageBox(host)
    dialogs.append(box)
    box.setText("Confirm only this temporary dialog")
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    observations = []
    for index in range(2):
        if index:
            box.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        def close_message():
            observations.append(box.windowHandle().transientParent() is host.windowHandle())
            box.button(QMessageBox.StandardButton.No).click()

        QTimer.singleShot(0, close_message)
        assert box.exec() == QMessageBox.StandardButton.No
        assert box.defaultButton() is box.button(QMessageBox.StandardButton.No)
        assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        app.processEvents()
    assert observations == [True, True]


def test_hidden_tool_owner_and_normal_window_owner_are_preserved(owner):
    app, host, dialogs = owner
    host.show()
    app.processEvents()
    host.hide()
    dialog = ordinary(host, dialogs)
    dialog.show()
    app.processEvents()
    assert dialog.windowHandle().transientParent() is host.windowHandle()
    dialog.hide()
    normal = QMainWindow()
    dialogs.append(normal)
    normal.show()
    regular_dialog = ordinary(normal, dialogs)
    regular_dialog.show()
    app.processEvents()
    assert regular_dialog.windowHandle().transientParent() is normal.windowHandle()
