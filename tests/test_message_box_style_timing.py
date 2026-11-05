# -*- coding: utf-8 -*-
"""Standard messages inherit only their owner's topmost policy before presentation."""

from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QWidget
import pytest

from calendar_app.presentation.dialogs import dialog_styles
from calendar_app.presentation.dialogs.dialog_chrome import prepare_dialog_chrome


@pytest.fixture
def owner(tmp_path):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "message-timing.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("theme_color", "#7653c4")
    host.settings.setValue("text_theme", "light")
    host.settings.setValue("panel_base_color", "#f6f7fb")
    style_filter = dialog_styles._CommonDialogStyleFilter(app)
    app.installEventFilter(style_filter)
    yield app, host, style_filter
    app.removeEventFilter(style_filter)
    for widget in app.topLevelWidgets():
        parent = widget
        while parent is not None and parent is not host:
            parent = parent.parentWidget()
        if parent is host:
            widget.hide()
    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _message(host, kind=QMessageBox.Icon.Information):
    box = QMessageBox(host)
    box.setWindowTitle("테스트 안내")
    box.setText("표시 상태만 확인합니다.")
    box.setIcon(kind)
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Save)
    box.setEscapeButton(QMessageBox.StandardButton.Cancel)
    return box


@pytest.mark.parametrize(
    "kind",
    [
        QMessageBox.Icon.Information,
        QMessageBox.Icon.Warning,
        QMessageBox.Icon.Critical,
        QMessageBox.Icon.Question,
    ],
)
def test_all_standard_messages_inherit_topmost_owner_while_still_hidden(owner, kind):
    _app, host, style_filter = owner
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    box = _message(host, kind)
    box.ensurePolished()
    assert not box.isVisible()
    assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert box.property("_dc_owner_topmost_inherited")
    assert not box.property("_dc_common_style_in_progress")
    css, flags = box.styleSheet(), box.windowFlags()
    style_filter.eventFilter(box, QEvent(QEvent.Type.Polish))
    assert box.styleSheet() == css
    assert box.windowFlags() == flags


def test_normal_owner_does_not_add_topmost_to_a_message(owner):
    _app, host, _filter = owner
    box = _message(host)
    prepare_dialog_chrome(box)
    assert not box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not box.property("_dc_owner_topmost_inherited")


def test_nested_modal_uses_topmost_host_even_when_immediate_owner_has_no_qt_flag(owner):
    _app, host, _filter = owner
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    nested = QDialog(host)
    assert not nested.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    box = _message(nested)
    prepare_dialog_chrome(box)
    assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert box.property("_dc_owner_topmost_inherited")
    assert not nested.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


@pytest.mark.parametrize("owner_topmost", [False, True])
def test_explicit_message_topmost_is_preserved_when_owner_is_unpinned(owner, owner_topmost):
    _app, host, _filter = owner
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, owner_topmost)
    box = _message(host)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    prepare_dialog_chrome(box)
    assert not box.property("_dc_owner_topmost_inherited")
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    prepare_dialog_chrome(box)
    assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_reused_message_removes_only_a_derived_topmost_flag(owner):
    _app, host, _filter = owner
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    box = _message(host)
    prepare_dialog_chrome(box)
    assert box.property("_dc_owner_topmost_inherited")
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    prepare_dialog_chrome(box)
    assert not box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not box.property("_dc_owner_topmost_inherited")
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    prepare_dialog_chrome(box)
    assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert box.property("_dc_owner_topmost_inherited")


@pytest.mark.parametrize(
    "owner_pins,explicit,expected",
    [
        ((True, False), False, [True, False]),
        ((True, True), False, [True, True]),
        ((True, False), True, [True, True]),
    ],
)
def test_real_reused_exec_reconciles_owner_without_erasing_explicit_policy(
    owner, owner_pins, explicit, expected
):
    _app, host, _filter = owner
    box = _message(host)
    if explicit:
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    observations = []

    def inspect_and_close():
        observations.append(bool(box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        box.reject()

    for pinned in owner_pins:
        host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        QTimer.singleShot(0, inspect_and_close)
        box.exec()
    assert observations == expected


def test_visible_message_flags_are_unchanged_until_hidden_preparation(owner):
    app, host, _filter = owner
    box = _message(host)
    box.show()
    app.processEvents()
    flags = box.windowFlags()
    # Keep the owner's native handle stable while changing the policy observed by preparation.
    with patch.object(
        host, "windowFlags", return_value=host.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
    ):
        prepare_dialog_chrome(box)
        assert box.isVisible()
        assert box.windowFlags() == flags
        box.hide()
        prepare_dialog_chrome(box)
        assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        box.show()
        app.processEvents()
    flags = box.windowFlags()
    prepare_dialog_chrome(box)
    assert box.isVisible()
    assert box.windowFlags() == flags
    box.hide()
    prepare_dialog_chrome(box)
    assert not box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_nested_show_during_stylesheet_application_is_ignored(owner):
    _app, host, style_filter = owner
    box = _message(host)
    original = dialog_styles.apply_common_dialog_style
    entered = []

    def apply(dialog, **kwargs):
        if dialog is box:
            entered.append(bool(dialog.property("_dc_common_style_in_progress")))
            style_filter.eventFilter(dialog, QEvent(QEvent.Type.Show))
        return original(dialog, **kwargs)

    with patch.object(dialog_styles, "apply_common_dialog_style", side_effect=apply):
        style_filter.eventFilter(box, QEvent(QEvent.Type.Show))
    assert entered == [True]
    assert not box.property("_dc_common_style_in_progress")
    assert box.property("_dc_standard_dialog_controls_styled")


@pytest.mark.parametrize(
    "key,expected",
    [
        (Qt.Key.Key_Return, QMessageBox.StandardButton.Save),
        (Qt.Key.Key_Escape, QMessageBox.StandardButton.Cancel),
    ],
)
def test_modal_default_and_escape_results_survive_inherited_owner_flag(owner, key, expected):
    _app, host, _filter = owner
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    box = _message(host)
    box.ensurePolished()
    default, escape = box.defaultButton(), box.escapeButton()
    flags = box.windowFlags()
    QTimer.singleShot(0, lambda: QTest.keyClick(box, key))
    assert box.exec() == expected
    assert box.clickedButton() is box.button(expected)
    assert box.defaultButton() is default and box.escapeButton() is escape
    assert box.windowFlags() == flags


def test_ordinary_dialog_and_native_file_picker_keep_their_polish_policy(owner):
    _app, host, style_filter = owner
    ordinary = QDialog(host)
    style_filter.eventFilter(ordinary, QEvent(QEvent.Type.Polish))
    assert not ordinary.property("_dc_common_style_applied")
    picker = QFileDialog(host)
    picker.setOption(QFileDialog.Option.DontUseNativeDialog, False)
    flags = picker.windowFlags()
    style_filter.eventFilter(picker, QEvent(QEvent.Type.Polish))
    assert picker.windowFlags() == flags
    assert not picker.property("dcCommonChrome")
    assert not picker.property("_dc_common_style_applied")
