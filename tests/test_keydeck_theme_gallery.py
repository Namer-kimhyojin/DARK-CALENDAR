# -*- coding: utf-8 -*-
"""Theme browsing stays a preview until its scoped request is applied in Studio."""

from copy import deepcopy
import json
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QDialog, QWidget
import pytest

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.presentation.widgets.keydeck.theme_dialog import ThemeGalleryDialog
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget


@pytest.fixture
def owner(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.settings = QSettings(str(tmp_path / "theme-gallery.ini"), QSettings.Format.IniFormat)
    yield widget
    widget.close()
    app.processEvents()


@pytest.fixture
def deck():
    deck = m.build_template_deck("macro_3x3", "crystal_night")
    second = m.new_page("Second")
    second["keys"] = [m.duplicate_key(key) for key in deck["pages"][0]["keys"]]
    deck["pages"].append(second)
    deck["page"] = 1
    for index, page in enumerate(deck["pages"]):
        page["keys"][0]["insert"].update(
            {"kind": "image", "path": f"user-art-{index}.png", "fit": "contain"}
        )
        page["keys"][0]["action"] = m.normalize_action(
            {"type": "url", "target": "https://example.com/keep"}
        )
        page["keys"][1]["insert"]["kind"] = "panorama"
    deck["panorama"]["path"] = "user-panorama.png"
    return m.normalize_deck(deck)


@pytest.fixture
def gallery(owner, deck):
    selected = {deck["pages"][deck["page"]]["keys"][0]["id"]}
    dialog = ThemeGalleryDialog(deck, owner, key_ids=selected)
    yield dialog
    dialog.reject()
    dialog.close()


def select_theme(dialog, theme_id="smoke_neon"):
    item = next(
        dialog.grid.item(index)
        for index in range(dialog.grid.count())
        if dialog.grid.item(index).data(Qt.ItemDataRole.UserRole) == theme_id
    )
    dialog.grid.setCurrentItem(item)
    return item


def select_scope(dialog, scope):
    index = dialog.scope_combo.findData(scope)
    assert index >= 0, scope
    dialog.scope_combo.setCurrentIndex(index)


def content_snapshot(deck):
    return {
        "panorama": deepcopy(deck["panorama"]),
        "pages": [
            {
                "id": page["id"],
                "name": page["name"],
                "keys": [
                    {
                        key: deepcopy(item[key])
                        for key in (
                            "id",
                            "label",
                            "sublabel",
                            "x",
                            "y",
                            "w",
                            "h",
                            "action",
                            "hold_action",
                            "mode",
                            "active",
                            "enabled",
                        )
                    }
                    for item in page["keys"]
                ],
            }
            for page in deck["pages"]
        ],
        "art": {
            item["id"]: deepcopy(item["insert"])
            for page in deck["pages"]
            for item in page["keys"]
            if item["insert"]["kind"] in {"image", "panorama"}
        },
    }


def test_browsing_filtering_scopes_and_cancel_leave_original_and_request_untouched(gallery, deck):
    before = deepcopy(deck)
    select_theme(gallery)
    select_scope(gallery, "selection")
    gallery.category_combo.setCurrentIndex(1)
    gallery.category_combo.setCurrentIndex(0)
    gallery.search_edit.setText("no matching theme in this catalog")
    gallery.search_edit.clear()
    assert gallery.request is None
    assert deck == before
    gallery.reject()
    assert gallery.request is None
    assert deck == before


@pytest.mark.parametrize("scope", ["deck", "page", "selection"])
def test_gallery_apply_returns_only_selected_scope_request_without_editing_caller(
    gallery, deck, scope
):
    before = deepcopy(deck)
    select_theme(gallery)
    select_scope(gallery, scope)
    assert gallery.request is None
    assert gallery.apply_button.isEnabled()
    gallery.apply_button.click()
    assert gallery.result() == QDialog.DialogCode.Accepted
    assert gallery.request == ("smoke_neon", scope)
    assert deck == before


def test_empty_search_disables_apply_and_recovers_to_a_selectable_preview(gallery, deck):
    before = deepcopy(deck)
    gallery.search_edit.setText("impossible result 5a030c9e")
    assert gallery.grid.count() == 0
    assert not gallery.apply_button.isEnabled()
    gallery.apply_button.click()
    assert gallery.request is None
    gallery.search_edit.clear()
    assert gallery.grid.count() > 0
    assert gallery.apply_button.isEnabled()
    assert gallery.preview_deck is not None
    assert deck == before


def test_initial_empty_thumbnail_cards_keep_full_image_and_label_space_after_lazy_render(gallery):
    grid = gallery.grid
    first = grid.item(0)
    thumbnail_height = grid.iconSize().height()
    minimum_height = thumbnail_height + grid.fontMetrics().height() + 6
    assert first.icon().isNull()
    assert first.sizeHint().height() >= minimum_height

    # Measure the first visible layout before deferred image generation can run.
    gallery._thumb_timer.blockSignals(True)
    try:
        gallery.resize(920, 680)
        gallery.show()
        QApplication.processEvents()
        grid.scrollToTop()
        grid.doItemsLayout()
        initial_rect = grid.visualItemRect(first)
        assert initial_rect.height() >= minimum_height
        assert initial_rect.width() >= grid.iconSize().width()
        assert first.icon().isNull()
    finally:
        gallery._thumb_timer.blockSignals(False)

    gallery._schedule_thumbnails()
    for _ in range(grid.count() + 2):
        QApplication.processEvents()
    viewport = grid.viewport().rect()
    visible_cards = [
        grid.item(row)
        for row in range(grid.count())
        if viewport.contains(grid.visualItemRect(grid.item(row)))
    ]
    assert visible_cards
    for item in visible_cards:
        assert not item.icon().pixmap(grid.iconSize()).isNull()
        assert item.text().strip()
        assert grid.visualItemRect(item).height() >= minimum_height
    assert grid.visualItemRect(first).size() == initial_rect.size()


def test_double_click_selects_preview_without_committing_a_request(gallery, deck):
    before = deepcopy(deck)
    item = select_theme(gallery)
    gallery.grid.itemDoubleClicked.emit(item)
    assert gallery.request is None
    assert gallery.result() != QDialog.DialogCode.Accepted
    assert deck == before


@pytest.mark.parametrize("scope", ["deck", "page", "selection"])
def test_detail_preview_matches_scope_and_preserves_user_art_actions_and_layout(
    gallery, deck, scope
):
    before = deepcopy(deck)
    select_theme(gallery)
    select_scope(gallery, scope)
    preview = gallery.preview_deck
    assert preview is not deck
    assert content_snapshot(preview) == content_snapshot(before)
    for page_index, page in enumerate(before["pages"]):
        for key_index, original in enumerate(page["keys"]):
            actual = preview["pages"][page_index]["keys"][key_index]
            affected = (
                scope == "deck"
                or page_index == before["page"]
                and (scope == "page" or key_index == 0)
            )
            if affected:
                assert actual["cap"]["material"] == "smoke"
            else:
                assert actual == original
    if scope != "deck":
        assert preview["case"] == before["case"]
    assert deck == before


@pytest.mark.parametrize("attribute", ["category_combo", "scope_combo"])
def test_scrolling_over_filters_does_not_change_their_values(gallery, attribute):
    combo = getattr(gallery, attribute)
    before = combo.currentIndex()
    local = QPointF(combo.rect().center())
    event = QWheelEvent(
        local,
        QPointF(combo.mapToGlobal(local.toPoint())),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(combo, event)
    assert combo.currentIndex() == before


def test_selection_scope_is_unavailable_without_a_valid_current_page_selection(owner, deck):
    dialog = ThemeGalleryDialog(deck, owner, key_ids={"removed-key"})
    try:
        index = dialog.scope_combo.findData("selection")
        assert index < 0 or not dialog.scope_combo.model().item(index).isEnabled()
    finally:
        dialog.reject()


def test_studio_theme_button_opens_gallery_directly_cancel_has_no_undo_or_draft_change(owner, deck):
    studio = KeyDeckStudioDialog(deck, owner)
    try:
        before = deepcopy(studio.deck)
        original = deepcopy(deck)
        calls = []

        def browse_then_cancel(dialog):
            calls.append(dialog)
            select_theme(dialog)
            return QDialog.DialogCode.Rejected

        assert studio.theme_button.menu() is None
        with patch.object(ThemeGalleryDialog, "exec", browse_then_cancel):
            studio.theme_button.click()
        assert len(calls) == 1
        assert studio.deck == before
        assert deck == original
        assert studio._undo == []
        assert not studio._dirty
    finally:
        studio.force_close()


@pytest.mark.parametrize("scope", ["deck", "page", "selection"])
def test_gallery_application_is_one_reversible_studio_draft_change(owner, deck, scope):
    studio = KeyDeckStudioDialog(deck, owner)
    try:
        before = deepcopy(studio.deck)
        original = deepcopy(deck)
        selected = before["pages"][before["page"]]["keys"][0]["id"]
        studio.canvas.select([selected])

        def apply_preview(dialog):
            select_theme(dialog)
            select_scope(dialog, scope)
            dialog.apply_button.click()
            return dialog.result()

        with patch.object(ThemeGalleryDialog, "exec", apply_preview):
            studio.open_theme_gallery()
        changed = deepcopy(studio.deck)
        assert changed != before
        assert content_snapshot(changed) == content_snapshot(before)
        assert len(studio._undo) == 1
        assert studio._dirty
        assert deck == original
        if scope != "deck":
            assert changed["case"] == before["case"]
            assert changed["theme"] == m.CUSTOM_THEME_ID
        studio.undo()
        assert studio.deck == before
        studio.redo()
        assert studio.deck == changed
        assert deck == original
    finally:
        studio.force_close()


@pytest.mark.parametrize("accepted", [False, True])
def test_only_final_studio_apply_updates_live_widget_and_saved_deck(owner, deck, accepted):
    widget = OverlayLauncherDeckWidget(owner)
    try:
        widget._apply_deck(deck)
        widget._save_timer.stop()
        widget._flush_deck()
        before_live = deepcopy(widget._deck_data)
        before_saved = widget._get("keydeck_data")

        def apply_gallery(dialog):
            select_theme(dialog)
            select_scope(dialog, "deck")
            dialog.apply_button.click()
            return dialog.result()

        def edit_studio(dialog):
            with patch.object(ThemeGalleryDialog, "exec", apply_gallery):
                dialog.open_theme_gallery()
            assert dialog.deck != before_live
            assert widget._deck_data == before_live
            assert widget._get("keydeck_data") == before_saved
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

        with patch.object(KeyDeckStudioDialog, "exec", edit_studio):
            widget._open_settings()
        if accepted:
            assert widget._deck_data["theme"] == "smoke_neon"
            assert json.loads(widget._get("keydeck_data"))["theme"] == "smoke_neon"
            assert content_snapshot(widget._deck_data) == content_snapshot(before_live)
        else:
            assert widget._deck_data == before_live
            assert widget._get("keydeck_data") == before_saved
    finally:
        widget.close()
