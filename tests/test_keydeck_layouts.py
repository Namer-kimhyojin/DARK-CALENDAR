# -*- coding: utf-8 -*-
"""KeyDeck layout files: document format, user library, applying, gallery and studio hooks."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from calendar_app.presentation.widgets.keydeck import layout_library as library
from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.layout_dialog import (
    LayoutLibraryDialog,
    _ChoiceDialog,
    resolve_request,
)
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY

_DIALOG = "calendar_app.presentation.widgets.keydeck.layout_dialog"
_STUDIO = "calendar_app.presentation.widgets.keydeck.studio"


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self._app.setProperty(EXITING_PROPERTY, False)

    def _file(self, name: str, color: str = "#d02040") -> str:
        folder = self.root / "source"
        folder.mkdir(exist_ok=True)
        path = folder / name
        if path.suffix == ".wav":
            path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24)
        else:
            image = QImage(24, 24, QImage.Format.Format_ARGB32)
            image.fill(QColor(color))
            self.assertTrue(image.save(str(path)))
        return str(path)

    def _deck_with_art(self) -> dict:
        deck = m.build_template_deck("macro_3x3")
        keys = deck["pages"][0]["keys"]
        keys[0]["insert"].update({"kind": "image", "path": self._file("art.png")})
        keys[1]["sound"], keys[1]["sound_path"] = "custom", self._file("click.wav")
        keys[2]["insert"]["kind"] = "panorama"
        deck["panorama"] = {**m.default_panorama(), "path": self._file("wide.png", "#2060d0")}
        return m.normalize_deck(deck)


class LayoutDocumentTests(_Case):
    def test_page_document_embeds_art_and_round_trips(self):
        deck = self._deck_with_art()
        document, skipped = library.build_document(deck, kind="page", name="  내   레이아웃 ")
        self.assertEqual(skipped, [])
        self.assertEqual(document["name"], "내 레이아웃")
        key = document["page"]["keys"][0]
        self.assertTrue(key["insert"]["path"].startswith(library.ASSET_PREFIX))
        self.assertTrue(document["page"]["keys"][1]["sound_path"].startswith("asset:"))
        self.assertTrue(document["panorama"]["path"].startswith("asset:"))
        self.assertEqual(len(document["assets"]), 3)
        written = library.write_layout(document, self.root / "share" / "mine")
        self.assertEqual(written.suffix, ".keydeck")
        loaded = library.read_layout(written)
        self.assertEqual(library.document_counts(loaded), (9, 1))
        content = library.materialize(loaded, asset_root=self.root)
        restored = Path(content["keys"][0]["insert"]["path"])
        self.assertTrue(restored.is_file())
        self.assertEqual(restored.parent, self.root / "launcher_assets" / "image")
        self.assertEqual(
            restored.read_bytes(), Path(deck["pages"][0]["keys"][0]["insert"]["path"]).read_bytes()
        )
        self.assertTrue(Path(content["panorama"]["path"]).is_file())
        original_ids = {key["id"] for key in deck["pages"][0]["keys"]}
        self.assertFalse(original_ids & {key["id"] for key in content["keys"]})

    def test_deck_document_keeps_every_page(self):
        deck = self._deck_with_art()
        deck["pages"].append({**m.new_page("둘"), "keys": m.template_keys("command_bar")})
        document, _skipped = library.build_document(m.normalize_deck(deck), kind="deck", name="덱")
        loaded = library.parse_document(json.dumps(document).encode("utf-8", errors="strict"))
        self.assertEqual(loaded["kind"], "deck")
        self.assertEqual(library.document_counts(loaded)[1], 2)
        content = library.materialize(loaded, asset_root=self.root)
        self.assertEqual(len(content["deck"]["pages"]), 2)
        self.assertTrue(Path(content["deck"]["panorama"]["path"]).is_file())

    def test_missing_files_are_reported_and_left_out(self):
        deck = m.build_template_deck("macro_3x3")
        deck["pages"][0]["keys"][0]["insert"].update(
            {"kind": "image", "path": str(self.root / "gone.png")}
        )
        document, skipped = library.build_document(deck, kind="page", name="x")
        self.assertEqual(skipped, ["gone.png"])
        self.assertEqual(document["page"]["keys"][0]["insert"]["path"], "")

    def test_bad_files_are_rejected_with_a_reason(self):
        good, _ = library.build_document(m.build_template_deck(), kind="page", name="ok")
        empty = {**good, "page": {**good["page"], "keys": []}}
        cases = {
            b"not json": "unreadable",
            b"[1, 2]": "not_layout",
            json.dumps({"format": "other"}).encode("utf-8", errors="strict"): "not_layout",
            json.dumps({**good, "version": 99}).encode("utf-8", errors="strict"): "newer_version",
            json.dumps(empty).encode("utf-8", errors="strict"): "empty",
            json.dumps({**good, "kind": "mystery"}).encode("utf-8", errors="strict"): "not_layout",
        }
        for raw, code in cases.items():
            with self.subTest(code=code), self.assertRaises(library.LayoutError) as caught:
                library.parse_document(raw)
            self.assertEqual(caught.exception.code, code)
        with (
            patch.object(library, "MAX_FILE_BYTES", 10),
            self.assertRaises(library.LayoutError) as caught,
        ):
            library.parse_document(json.dumps(good).encode("utf-8", errors="strict"))
        self.assertEqual(caught.exception.code, "too_large")

    def test_plain_deck_json_and_utf8_bom_are_accepted(self):
        deck = m.build_template_deck("numpad")
        loaded = library.parse_document(
            b"\xef\xbb\xbf" + m.deck_to_json(deck).encode("utf-8", errors="strict")
        )
        self.assertEqual(loaded["kind"], "deck")
        self.assertGreater(library.document_counts(loaded)[0], 0)

    def test_hostile_asset_entries_are_sanitised(self):
        document, _ = library.build_document(m.build_template_deck(), kind="page", name="x")
        document["page"]["keys"][0]["insert"].update(
            {"kind": "image", "path": "asset:abcdef012345"}
        )
        document["assets"] = {
            "abcdef012345": {"name": "../../evil.png", "kind": "image", "data": "@@not base64@@"},
            "../escape": {"name": "a.png", "kind": "image", "data": ""},
            "abcdef999999": {"name": "a.exe", "kind": "program", "data": ""},
        }
        loaded = library.parse_document(json.dumps(document).encode("utf-8", errors="strict"))
        self.assertEqual(list(loaded["assets"]), ["abcdef012345"])
        self.assertEqual(loaded["assets"]["abcdef012345"]["name"], "evil.png")
        content = library.materialize(loaded, asset_root=self.root)
        self.assertEqual(content["keys"][0]["insert"]["path"], "")

    def test_summary_lists_actions_and_real_targets(self):
        deck = m.build_template_deck("macro_3x3")
        keys = deck["pages"][0]["keys"]
        keys[0]["action"] = {"type": "url", "target": "https://example.com", "paste": False}
        keys[1]["action"] = {"type": "app", "target": "", "paste": False}
        keys[2]["hold_action"] = {"type": "url", "target": "https://", "paste": False}
        document, _ = library.build_document(deck, kind="page", name="x")
        summary = library.summarize_actions(
            library.parse_document(json.dumps(document).encode("utf-8", errors="strict"))
        )
        self.assertIn("https://example.com", summary["targets"])
        self.assertNotIn("", summary["targets"])
        self.assertNotIn("https://", summary["targets"])
        self.assertGreaterEqual(summary["counts"]["url"], 2)


class LayoutLibraryTests(_Case):
    def _saved(self, name: str, created: str) -> Path:
        document, _ = library.build_document(m.build_template_deck(), kind="page", name=name)
        document["created"] = created
        return library.save_to_library(document, self.root)

    def test_save_list_rename_and_delete(self):
        older = self._saved("예전", "2026-01-01T09:00:00")
        newer = self._saved("최근", "2026-09-01T09:00:00")
        (library.library_dir(self.root) / "broken.keydeck").write_text(
            "{", encoding="utf-8", errors="strict"
        )
        names = [entry.name for entry in library.list_layouts(self.root)]
        self.assertEqual(names, ["최근", "예전"])
        library.rename_layout(older, "새 이름", self.root)
        self.assertEqual(library.read_layout(older)["name"], "새 이름")
        self.assertTrue(library.delete_layout(newer, self.root))
        self.assertFalse(newer.exists())
        outside = self.root / "outside.keydeck"
        outside.write_text("{}", encoding="utf-8", errors="strict")
        self.assertFalse(library.delete_layout(outside, self.root))
        self.assertTrue(outside.exists())

    def test_file_names_are_safe(self):
        self.assertEqual(library.safe_file_stem('a/b:c*?"<>|d'), "a_b_c_d")
        self.assertEqual(library.safe_file_stem("..."), "layout")
        path = self._saved("CON / 홈 화면", "2026-09-30T10:00:00")
        self.assertEqual(path.parent, library.library_dir(self.root))
        self.assertNotIn("/", path.stem)

    def test_import_copies_into_the_library(self):
        document, _ = library.build_document(m.build_template_deck(), kind="page", name="받은 것")
        shared = library.write_layout(document, self.root / "download" / "gift")
        saved, loaded = library.import_to_library(shared, self.root)
        self.assertEqual(saved.parent, library.library_dir(self.root))
        self.assertEqual(loaded["name"], "받은 것")
        self.assertTrue(shared.exists())


class ApplyTests(_Case):
    def test_page_layout_replaces_or_adds_a_page_and_brings_its_panorama(self):
        source = self._deck_with_art()
        document, _ = library.build_document(source, kind="page", name="사진 페이지")
        content = library.materialize(
            library.parse_document(json.dumps(document).encode("utf-8", errors="strict")),
            asset_root=self.root,
        )
        target = m.build_template_deck("numpad")
        replaced = library.apply_content(target, content, "replace")
        self.assertEqual(len(replaced["pages"]), 1)
        self.assertEqual(len(replaced["pages"][0]["keys"]), 9)
        self.assertTrue(replaced["panorama"]["path"])
        self.assertEqual(replaced["theme"], m.CUSTOM_THEME_ID)
        added = library.apply_content(target, content, "new_page")
        self.assertEqual(len(added["pages"]), 2)
        self.assertEqual(added["page"], 1)
        self.assertEqual(added["pages"][1]["name"], "사진 페이지")
        self.assertEqual(len(target["pages"]), 1)  # 원본 덱은 바뀌지 않는다

    def test_deck_layout_replaces_everything(self):
        source = m.build_template_deck("stream_5x3")
        source["pages"].append(m.new_page("둘"))
        source["pages"][1]["keys"] = m.template_keys("numpad")
        document, _ = library.build_document(source, kind="deck", name="덱")
        request = (
            "layout",
            library.parse_document(json.dumps(document).encode("utf-8", errors="strict")),
            "deck",
        )
        result = resolve_request(m.build_template_deck("macro_3x3"), request)
        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual(result["page"], 0)

    def test_template_requests_replace_or_add_a_page(self):
        deck = m.build_template_deck("macro_3x3")
        replaced = resolve_request(deck, ("template", "command_bar", "replace"))
        self.assertEqual(len(replaced["pages"]), 1)
        added = resolve_request(deck, ("template", "command_bar", "new_page"))
        self.assertEqual(len(added["pages"]), 2)
        self.assertEqual(added["page"], 1)
        self.assertTrue(added["pages"][1]["keys"])


class GalleryDialogTests(_Case):
    def setUp(self):
        super().setUp()
        self.deck = m.build_template_deck("macro_3x3")
        self.dialog = LayoutLibraryDialog(self.deck, library_root=self.root)
        self.addCleanup(self.dialog.deleteLater)

    def _accept_confirmations(self, answer=QDialog.DialogCode.Accepted):
        patcher = patch.object(_ChoiceDialog, "exec", return_value=answer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_builtin_layouts_return_a_template_request(self):
        self._accept_confirmations()
        self.assertEqual(self.dialog.grid.count(), len(m.TEMPLATES))
        self.dialog.grid.setCurrentRow(4)
        self.dialog.new_page_button.click()
        self.assertEqual(self.dialog.request, ("template", m.TEMPLATES[4][0], "new_page"))

    def test_replacing_a_filled_page_asks_first(self):
        self._accept_confirmations(QDialog.DialogCode.Rejected)
        self.dialog.grid.setCurrentRow(0)
        self.dialog.apply_button.click()
        self.assertIsNone(self.dialog.request)

    def test_saved_page_shows_up_under_my_layouts_and_can_be_applied(self):
        self._accept_confirmations()
        path = self.dialog.save_current("page", name="첫 레이아웃")
        self.assertIsNotNone(path)
        self.assertEqual(self.dialog.tabs.currentIndex(), 1)
        self.assertEqual(self.dialog.grid.count(), 1)
        self.assertIn("(1)", self.dialog.tabs.tabText(1))
        self.dialog.apply_button.click()
        source, document, mode = self.dialog.request
        self.assertEqual((source, mode, document["name"]), ("layout", "replace", "첫 레이아웃"))

    def test_saved_deck_offers_only_whole_deck_replacement(self):
        self.dialog.save_current("deck", name="전체")
        self.assertTrue(self.dialog.new_page_button.isHidden())
        self._accept_confirmations()
        self.dialog.apply_button.click()
        self.assertEqual(self.dialog.request[2], "deck")

    def test_import_asks_before_adding_to_the_library(self):
        document, _ = library.build_document(self.deck, kind="page", name="선물")
        shared = library.write_layout(document, self.root / "incoming" / "gift")
        with patch.object(_ChoiceDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.assertIsNone(self.dialog.import_file(str(shared)))
        self.assertEqual(library.list_layouts(self.root), [])
        with patch.object(_ChoiceDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            saved = self.dialog.import_file(str(shared))
        self.assertIsNotNone(saved)
        self.assertEqual([entry.name for entry in library.list_layouts(self.root)], ["선물"])

    def test_broken_import_explains_why(self):
        broken = self.root / "broken.keydeck"
        broken.write_text("{nope", encoding="utf-8", errors="strict")
        with patch.object(QMessageBox, "warning") as warning:
            self.assertIsNone(self.dialog.import_file(str(broken)))
        warning.assert_called_once()

    def test_rename_export_and_delete(self):
        self.dialog.save_current("page", name="원래 이름")
        with patch(f"{_DIALOG}.QInputDialog.getText", return_value=("바뀐 이름", True)):
            self.dialog._rename()
        self.assertEqual(self.dialog.grid.currentItem().text(), "바뀐 이름")
        target = self.root / "exported"
        with patch(f"{_DIALOG}.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            self.dialog._export()
        self.assertEqual(library.read_layout(target.with_suffix(".keydeck"))["name"], "바뀐 이름")
        self._accept_confirmations()
        self.dialog._delete()
        self.assertEqual(library.list_layouts(self.root), [])
        self.assertFalse(self.dialog.empty.isHidden())


class StudioLayoutTests(_Case):
    def setUp(self):
        super().setUp()
        patcher = patch(
            f"{_STUDIO}.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.studio = KeyDeckStudioDialog(m.build_template_deck("macro_3x3"))
        self.studio._layout_root = self.root
        self.addCleanup(self.studio.force_close)

    def test_layout_button_opens_the_gallery_and_applies_with_undo(self):
        class _FakeGallery:
            def __init__(self, deck, parent=None, **kwargs):
                self.kwargs = kwargs
                self.request = ("template", "command_bar", "new_page")

            def exec(self):
                return QDialog.DialogCode.Accepted

        with patch(f"{_STUDIO}.LayoutLibraryDialog", _FakeGallery):
            self.studio.template_button.click()
        self.assertEqual(len(self.studio.deck["pages"]), 2)
        self.assertEqual(self.studio.deck["page"], 1)
        self.assertTrue(self.studio._dirty)
        self.studio.undo()
        self.assertEqual(len(self.studio.deck["pages"]), 1)

    def test_page_tab_menu_saves_and_exports_the_page(self):
        with patch(f"{_STUDIO}.QInputDialog.getText", return_value=("저장본", True)):
            self.studio._save_page_layout(0)
        self.assertEqual([entry.name for entry in library.list_layouts(self.root)], ["저장본"])
        target = self.root / "page_export.keydeck"
        with patch(f"{_STUDIO}.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            self.studio._export_page_layout(0)
        self.assertEqual(library.read_layout(target)["kind"], "page")

    def test_dropping_a_layout_file_starts_an_import(self):
        with patch.object(self.studio, "open_layout_library") as opened:
            self.studio._targets_dropped([("app", str(self.root / "gift.keydeck"))])
        opened.assert_called_once_with(import_path=str(self.root / "gift.keydeck"))


if __name__ == "__main__":
    unittest.main()
