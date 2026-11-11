# -*- coding: utf-8 -*-
"""Goal-oriented token editing preserves hidden drafts, all raw keys and alpha."""

import json
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QColorDialog, QComboBox, QLineEdit
import pytest

from calendar_app.presentation.dialogs.dialog_styles import (
    DIALOG_METRIC_DEFAULTS,
    DIALOG_TOKEN_EDITABLE_KEYS,
    get_dialog_metric_tokens,
)
from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
    DialogTokenEditorDialog,
    _normalize_color,
    _to_qcolor,
)

_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def editor(tmp_path, monkeypatch):
    # These responsive cases model a real desktop, independently of the
    # offscreen plugin's synthetic 800px monitor and global text-fit policy.
    monkeypatch.setattr(
        "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
        lambda _dialog: (1888, 976),
    )
    settings = QSettings(str(tmp_path / "tokens.ini"), QSettings.Format.IniFormat)
    settings.setValue("font_size", 11)
    dialog = DialogTokenEditorDialog(
        settings=settings,
        persist_on_apply=False,
        initial_color_overrides={},
        initial_metric_overrides={},
    )
    yield dialog, settings
    dialog._preview_timer.stop()
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def snapshot(settings):
    return {key: settings.value(key) for key in settings.allKeys()}


def test_recommended_and_expert_share_the_complete_authoritative_registries(editor):
    dialog, settings = editor
    before = snapshot(settings)
    colors = dict(dialog._color_edits)
    metrics = dict(dialog._metric_spins)
    assert set(colors) == set(DIALOG_TOKEN_EDITABLE_KEYS)
    assert set(metrics) == set(DIALOG_METRIC_DEFAULTS)
    assert not dialog._color_rows["surface_bg"].isHidden()
    assert dialog._color_rows["surface_hover"].isHidden()
    assert not dialog.apply_btn.isEnabled() and dialog.change_count == 0
    dialog.expert_mode_check.setChecked(True)
    assert not dialog._color_rows["surface_hover"].isHidden()
    dialog.expert_mode_check.setChecked(False)
    assert colors == dialog._color_edits and metrics == dialog._metric_spins
    assert snapshot(settings) == before
    assert all(action.isVisible() for action in dialog.file_menu.actions())


def test_search_finds_keys_across_categories_without_mutating_draft_or_preview(editor):
    dialog, settings = editor
    before = snapshot(settings)
    css = dialog.preview_root.styleSheet()
    dialog.search_edit.setText("button_primary_bg")
    assert not dialog._color_rows["button_primary_bg"].isHidden()
    assert dialog._color_rows["surface_bg"].isHidden()
    assert dialog.metric_search_edit.text() == "button_primary_bg"
    assert dialog.change_count == 0 and dialog.preview_root.styleSheet() == css
    dialog.search_edit.clear()
    dialog.category_nav.setCurrentRow(2)
    assert not dialog._color_rows["surface_item"].isHidden()
    assert dialog._color_rows["button_primary_bg"].isHidden()
    assert snapshot(settings) == before


def test_hidden_changes_are_counted_and_returned_when_filter_and_expert_are_off(editor):
    dialog, settings = editor
    before = snapshot(settings)
    dialog._color_edits["button_disabled_border"].setText("rgba(17, 34, 51, 64)")
    dialog._metric_spins["radio_spacing"].setValue(13)
    dialog.search_edit.setText("not-present")
    assert all(row.isHidden() for row in dialog._color_rows.values())
    assert dialog.change_count == 2
    dialog._apply()
    assert dialog.selected_color_overrides()["button_disabled_border"] == "rgba(17, 34, 51, 64)"
    assert dialog.selected_metric_overrides()["radio_spacing"] == 13
    assert snapshot(settings) == before


def test_invalid_hidden_raw_value_is_revealed_before_focusing(editor):
    dialog, _ = editor
    dialog._color_edits["toolbutton_disabled_border"].setText("bad-color")
    dialog.search_edit.setText("surface")
    with (
        patch("calendar_app.presentation.dialogs.dialog_token_editor_dialog.QMessageBox.warning"),
        patch.object(dialog, "accept") as accept,
    ):
        dialog._apply()
    accept.assert_not_called()
    assert dialog.editor_tabs.currentIndex() == 0
    assert dialog.expert_mode_check.isChecked()
    assert dialog.search_edit.text() == ""
    assert not dialog._color_rows["toolbutton_disabled_border"].isHidden()
    assert not dialog.apply_btn.isEnabled()


def test_metric_explicit_default_is_preserved_until_its_reset_and_px_units_stay_exact(tmp_path):
    settings = QSettings(str(tmp_path / "explicit.ini"), QSettings.Format.IniFormat)
    settings.setValue("font_size", 24)
    default = get_dialog_metric_tokens(apply_overrides=False, settings=settings)["base_font_pt"]
    settings.setValue("dialog_token.metric.base_font_pt", default)
    dialog = DialogTokenEditorDialog(settings=settings, persist_on_apply=False)
    try:
        assert dialog._metric_spins["base_font_pt"].suffix() == " px"
        assert dialog._metric_spins["base_font_pt"].value() == 32
        assert dialog.change_count == 0
        dialog._reset_metric_key("base_font_pt")
        assert dialog._metric_spins["base_font_pt"].value() == default
        assert dialog.change_count == 1
        dialog._apply()
        assert "base_font_pt" not in dialog.selected_metric_overrides()
        assert settings.value("dialog_token.metric.base_font_pt") == default
    finally:
        dialog.close()
        dialog.deleteLater()


def test_color_and_metric_presets_keep_the_other_tier_unchanged(editor):
    dialog, _ = editor
    dialog._metric_spins["button_height"].setValue(37)
    dialog.preset_mode_all.setChecked(True)
    dialog.color_preset_combo.setCurrentText("Light Aqua Form")
    dialog._apply_selected_color_preset()
    assert dialog._metric_spins["button_height"].value() == 37
    assert dialog._color_edits["accent"].text() == "#22c3ca"
    colors = dialog.get_color_overrides_from_edits()
    dialog._apply_selected_metric_preset()
    assert dialog.get_color_overrides_from_edits() == colors
    dialog._reset_all()
    assert dialog._collect_color_overrides(True) == ({}, None)
    assert dialog._collect_metric_overrides(True) == {}


def test_generic_preset_names_are_shown_translated_but_selected_by_key(editor):
    """The shown label is localized; logic must still resolve the internal key."""
    from calendar_app.infrastructure.i18n import t
    from calendar_app.presentation.dialogs import dialog_token_editor_dialog as module

    dialog, _ = editor
    for key, (locale_key, fallback) in module._PRESET_NAME_LABELS.items():
        label = t(f"dialog.token_editor.preset_name.{locale_key}", fallback)
        assert module._preset_label(key) == label
        assert module._preset_key(label) == module._preset_key(key) == key
    # Design names are proper names and are shown unchanged.
    assert module._preset_label("Light Aqua Form") == module._preset_key("Light Aqua Form")

    shown = [
        dialog.color_preset_combo.itemText(i) for i in range(dialog.color_preset_combo.count())
    ]
    assert shown[:2] == [
        module._preset_label("Default (Auto)"),
        module._preset_label("System Default"),
    ]
    assert [dialog.metric_preset_combo.itemText(i) for i in range(2)] == [
        module._preset_label("Default (Auto)"),
        module._preset_label("System Default"),
    ]

    # Choosing "System Default" by its shown label still resets every color to default.
    dialog._color_edits["accent"].setText("#123456")
    dialog.color_preset_combo.setCurrentText(module._preset_label("System Default"))
    dialog._apply_selected_color_preset()
    assert dialog._color_edits["accent"].text() == dialog._default_color("accent")
    # The note under each combo is localized too (no raw English source text left).
    for note in module._PRESET_NOTE_LABELS:
        assert module._preset_note(note) == t(
            f"dialog.token_editor.preset_note.{module._PRESET_NOTE_LABELS[note][0]}",
            module._PRESET_NOTE_LABELS[note][1],
        )


def test_json_export_import_includes_hidden_keys_and_does_not_persist(editor, tmp_path):
    dialog, settings = editor
    before = snapshot(settings)
    path = tmp_path / "full.json"
    dialog._color_edits["toolbutton_disabled_border"].setText("rgba(17, 34, 51, 64)")
    dialog._metric_spins["radio_spacing"].setValue(13)
    dialog.search_edit.setText("no-match")
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(path), "JSON")):
        dialog._export_tokens()
    document = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    assert set(document["colors"]) == set(DIALOG_TOKEN_EDITABLE_KEYS)
    assert document["metrics"]["radio_spacing"] == 13
    dialog._reset_all()
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(path), "JSON")):
        dialog._import_tokens()
    assert dialog._color_edits["toolbutton_disabled_border"].text() == "rgba(17, 34, 51, 64)"
    assert dialog._metric_spins["radio_spacing"].value() == 13
    assert snapshot(settings) == before


@pytest.mark.parametrize("width,narrow", [(1200, False), (820, True)])
def test_preview_stays_outside_editor_scroll_and_footer_is_reachable(editor, width, narrow):
    dialog, _ = editor
    dialog.show()
    for _ in range(3):
        _APP.processEvents()
    dialog.resize(width, 820)
    _APP.processEvents()
    assert dialog._responsive_mode is narrow
    assert not dialog.color_token_area.isAncestorOf(dialog.preview_wrap)
    assert dialog.rect().contains(
        QRect(dialog.apply_btn.mapTo(dialog, QPoint()), dialog.apply_btn.size())
    )
    if narrow:
        assert dialog.preview_wrap.geometry().bottom() < dialog.editor_tabs.geometry().top()
    else:
        assert dialog.editor_tabs.geometry().right() < dialog.preview_wrap.geometry().left()
    field = dialog._color_edits["surface_bg"]
    assert field.width() >= 230
    assert field.toolTip() == field.text()
    assert dialog.color_token_area.viewport().width() >= field.minimumWidth()


@pytest.mark.parametrize("alpha", [0, 1, 36, 128, 255])
def test_qt_color_picker_preserves_alpha_and_uses_themed_non_native_selector(editor, alpha):
    dialog, _ = editor
    edit = dialog._color_edits["surface_bg"]
    edit.setText("rgba(10, 20, 30, 36)")
    chosen = QColor(17, 34, 51, alpha)
    with patch(
        "calendar_app.presentation.dialogs.dialog_token_editor_dialog.QColorDialog.getColor",
        return_value=chosen,
    ) as pick:
        dialog._pick_color("surface_bg")
    args = pick.call_args.args
    assert args[0].alpha() == 36
    assert args[3] & QColorDialog.ColorDialogOption.ShowAlphaChannel
    assert args[3] & QColorDialog.ColorDialogOption.DontUseNativeDialog
    assert _to_qcolor(edit.text()).getRgb() == chosen.getRgb()
    assert _normalize_color(_normalize_color(edit.text())) == _normalize_color(edit.text())
    before = edit.text()
    with patch(
        "calendar_app.presentation.dialogs.dialog_token_editor_dialog.QColorDialog.getColor",
        return_value=QColor(),
    ):
        dialog._pick_color("surface_bg")
    assert edit.text() == before


def test_default_preview_form_uses_natural_control_heights_and_theme_surface(editor):
    dialog, _ = editor
    dialog.show()
    for _ in range(3):
        _APP.processEvents()
    line = dialog.preview_root.findChild(QLineEdit)
    combo = dialog.preview_root.findChild(QComboBox)
    assert 28 <= line.height() <= 44
    assert 28 <= combo.height() <= 44
    gap = (
        combo.mapTo(dialog.preview_root, QPoint()).y()
        - line.mapTo(dialog.preview_root, QPoint()).y()
        - line.height()
    )
    assert 8 <= gap <= 12
    pixel = dialog.preview_root.grab().toImage().pixelColor(2, 2)
    assert pixel.name() == QColor(dialog._current_tokens["surface_bg"]).name()
    assert not dialog.color_token_area.widget().autoFillBackground()
    assert not dialog.color_token_area.viewport().autoFillBackground()


@pytest.mark.parametrize("persist", [False, True])
@pytest.mark.parametrize(
    "key,value",
    [
        ("dialog_token.accent", "#AABBCC"),
        ("dialog_token.text_primary", "invalid-color"),
        ("dialog_token.metric.button_height", "invalid-number"),
    ],
)
def test_open_show_cancel_never_normalizes_or_deletes_the_original_settings(
    tmp_path, persist, key, value
):
    from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter

    settings = QSettings(str(tmp_path / "unclean.ini"), QSettings.Format.IniFormat)
    settings.setValue(key, value)
    before = snapshot(settings)
    install_common_dialog_style_filter(_APP)
    with (
        patch.object(settings, "setValue", wraps=settings.setValue) as write,
        patch.object(settings, "remove", wraps=settings.remove) as remove,
    ):
        dialog = DialogTokenEditorDialog(settings=settings, persist_on_apply=persist)
        try:
            dialog.show()
            for _ in range(3):
                _APP.processEvents()
            dialog._refresh_preview(force=True)
            dialog.reject()
            write.assert_not_called()
            remove.assert_not_called()
            assert snapshot(settings) == before
            assert dialog._dc_chrome_settings is dialog._read_settings
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("alpha", [0, 1, 36, 128, 255])
def test_picker_apply_and_reopen_roundtrip_preserves_the_selected_alpha_byte(tmp_path, alpha):
    from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens

    settings = QSettings(str(tmp_path / "persisted-alpha.ini"), QSettings.Format.IniFormat)
    dialog = DialogTokenEditorDialog(settings=settings, persist_on_apply=True)
    try:
        with patch(
            "calendar_app.presentation.dialogs.dialog_token_editor_dialog.QColorDialog.getColor",
            return_value=QColor(17, 34, 51, alpha),
        ):
            dialog._pick_color("accent")
        dialog._apply()
        for _ in range(3):
            actual = get_dialog_theme_tokens(settings=settings)["accent"]
            assert _to_qcolor(actual).getRgb() == (17, 34, 51, alpha)
    finally:
        dialog.close()
        dialog.deleteLater()


def test_actual_nested_editor_accept_and_cancel_preserve_the_parent_two_tier_draft(tmp_path):
    from PyQt6.QtWidgets import QDialog, QWidget

    from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog

    host = QWidget()
    host.settings = QSettings(str(tmp_path / "nested.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("font_size", 11)
    before = snapshot(host.settings)
    parent = PanelColorPickerDialog(host, current_font_size=11)
    try:

        def stage(child):
            assert child._persist_on_apply is False
            child._color_edits["accent"].setText("#123456")
            child._metric_spins["button_height"].setValue(35)
            child._apply()
            return QDialog.DialogCode.Accepted

        with patch.object(DialogTokenEditorDialog, "exec", stage):
            parent._open_token_editor()
        assert parent.selected_dialog_color_overrides()["accent"] == "#123456"
        assert parent.selected_dialog_metric_overrides()["button_height"] == 35
        assert snapshot(host.settings) == before
        staged_colors = parent.selected_dialog_color_overrides()
        staged_metrics = parent.selected_dialog_metric_overrides()

        def cancel(child):
            child._color_edits["accent"].setText("#654321")
            child.reject()
            return QDialog.DialogCode.Rejected

        with patch.object(DialogTokenEditorDialog, "exec", cancel):
            parent._open_token_editor()
        assert parent.selected_dialog_color_overrides() == staged_colors
        assert parent.selected_dialog_metric_overrides() == staged_metrics
        parent.reject()
        assert snapshot(host.settings) == before
    finally:
        parent.close()
        parent.deleteLater()
        host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize(
    "section,key",
    [(0, "surface_bg"), (1, "button_primary_bg"), (2, "surface_item"), (3, "list_selected_bg")],
)
def test_metric_shortcut_preserves_the_last_color_category_on_top_tab_return(editor, section, key):
    dialog, _ = editor
    dialog.category_nav.setCurrentRow(section)
    assert not dialog._color_rows[key].isHidden()
    dialog.category_nav.setCurrentRow(4)
    assert dialog.editor_tabs.currentIndex() == 1
    assert dialog.metric_category_nav.currentRow() == 4
    dialog.editor_tabs.setCurrentIndex(0)
    assert dialog.category_nav.currentRow() == section
    assert not dialog._color_rows[key].isHidden()
    assert dialog.change_count == 0
