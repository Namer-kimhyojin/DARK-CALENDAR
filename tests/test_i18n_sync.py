# -*- coding: utf-8 -*-
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import types
from unittest import TestCase
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "i18n_sync.py"
SPEC = importlib.util.spec_from_file_location("i18n_sync", MODULE_PATH)
i18n_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(i18n_sync)


class FakeTranslator:
    """Stands in for deep_translator: no network, records every request."""

    def __init__(self, translate):
        self._translate = translate
        self.requests = []

    def translate(self, text):
        self.requests.append(text)
        return self._translate(text)


class AutoTranslateSafetyTests(TestCase):
    def setUp(self):
        self._cache = i18n_sync._en_data_cache
        i18n_sync._en_data_cache = {
            "menu.save": "Save",
            "menu.hint": "Open {name} in Air Calendar with Ctrl+O, then press Enter.",
            "menu.html": "Read <b>credentials.json</b> before 09:00 (HH:mm).",
        }
        self.addCleanup(setattr, i18n_sync, "_en_data_cache", self._cache)
        self.base = {"menu": {"save": "저장", "hint": "힌트", "html": "안내"}}

    def test_short_labels_keep_english_and_are_marked_for_review(self):
        translator = FakeTranslator(lambda text: "ÜBERSETZT " + text)
        target, pending = {}, {}

        i18n_sync.fill_missing(self.base, target, translator, pending=pending)

        self.assertEqual(target["menu"]["save"], "Save")
        self.assertNotIn("Save", translator.requests)
        self.assertEqual(pending["menu.save"], "short_label")
        self.assertEqual(pending["menu.hint"], "machine_translated")

    def test_protected_tokens_are_masked_and_restored(self):
        translator = FakeTranslator(lambda text: text.replace("then press", "dann drücken"))
        target, pending = {}, {}

        i18n_sync.fill_missing(self.base, target, translator, pending=pending)

        sent = " ".join(translator.requests)
        for token in ("{name}", "Air Calendar", "Ctrl+O", "<b>", "credentials.json", "HH:mm"):
            self.assertNotIn(token, sent)
        self.assertEqual(
            target["menu"]["hint"],
            "Open {name} in Air Calendar with Ctrl+O, dann drücken Enter.",
        )
        self.assertIn("<b>credentials.json</b>", target["menu"]["html"])
        self.assertIn("(HH:mm)", target["menu"]["html"])

    def test_file_dialog_filter_patterns_are_protected(self):
        # A translated pattern such as "(*.पीडीएफ)" stops the file dialog matching files.
        value = "Programs (*.exe *.lnk);;All files (*.*)"
        masked, tokens = i18n_sync.mask_protected(value)

        self.assertEqual(tokens, ["(*.exe *.lnk)", "(*.*)"])
        self.assertNotIn("*", masked)
        self.assertEqual(i18n_sync.protected_tokens("All files (*)"), ["(*)"])

    def test_lost_or_failed_translation_keeps_english(self):
        def drop_marker(text):
            return re.sub(r"⟦0⟧", "", text)

        def fail(text):
            raise RuntimeError("offline")

        for translate, reason in ((drop_marker, "protected_lost"), (fail, "translation_failed")):
            target, pending = {}, {}
            i18n_sync.fill_missing(self.base, target, FakeTranslator(translate), pending=pending)
            self.assertEqual(target["menu"]["hint"], i18n_sync._en_data_cache["menu.hint"])
            self.assertEqual(pending["menu.hint"], reason)

    def test_fill_without_translator_records_untranslated_keys(self):
        target, pending = {"menu": {"save": "Speichern"}}, {}

        i18n_sync.fill_missing(self.base, target, pending=pending)

        self.assertEqual(target["menu"]["save"], "Speichern")
        self.assertEqual(pending, {"menu.hint": "untranslated", "menu.html": "untranslated"})

    def test_keys_without_english_are_never_filled_with_korean(self):
        base = {"menu": {"save": "저장", "only_ko": "한국어 전용 문구입니다. 계속할까요?"}}
        translator = FakeTranslator(lambda text: "ÜBERSETZT " + text)
        target, pending = {}, {}

        i18n_sync.fill_missing(base, target, translator, pending=pending, copy_korean=False)

        self.assertEqual(target, {"menu": {"save": "Save"}})
        self.assertEqual(pending["menu.only_ko"], "no_english")
        self.assertFalse(any("한국어" in text for text in translator.requests))

    def test_cjk_translations_that_keep_every_token_are_accepted(self):
        for value, translated in (
            (
                "Open credentials.json from the Google Cloud console first.",
                "⟦0⟧をGoogle Cloudコンソールから開きます。",
            ),
            ("Press Ctrl+S to save the current layout now.", "⟦0⟧で現在のレイアウトを保存します。"),
        ):
            text, reason = i18n_sync.translate_value(
                FakeTranslator(lambda _, out=translated: out), value
            )
            self.assertEqual(reason, "machine_translated", value)
            self.assertNotIn("⟦", text)

    def test_hangul_output_is_rejected(self):
        value = "Choose the calendar that new events use."
        text, reason = i18n_sync.translate_value(FakeTranslator(lambda _: "새 일정 캘린더"), value)
        self.assertEqual((text, reason), (value, "translation_failed"))

    def test_short_label_rule(self):
        for value in ("Save", "Set target...", "Time format:", "Open {name} now"):
            self.assertTrue(i18n_sync.is_short_label(value), value)
        for value in ("Sync stopped.", "Choose the calendar to show", "Done! Retry?"):
            self.assertFalse(i18n_sync.is_short_label(value), value)

    def test_machine_translation_missing_a_glossary_term_is_marked_glossary_check(self):
        glossary = {
            "terms": {"open": {"en": "open", "ko": "열기"}},
            "locales": {"de": {"open": "öffnen"}},
        }

        def check(english, translation):
            return i18n_sync.glossary_warnings(english, translation, "de", glossary)

        for wording, reason in (
            ("Öffnen Sie", "machine_translated"),
            ("Starten Sie", "glossary_check"),
        ):
            target, pending = {}, {}
            translator = FakeTranslator(lambda text, out=wording: text.replace("Open", out))

            i18n_sync.fill_missing(
                self.base, target, translator, pending=pending, glossary_check=check
            )

            self.assertEqual(pending["menu.hint"], reason, wording)
            self.assertEqual(
                target["menu"]["hint"],
                f"{wording} {{name}} in Air Calendar with Ctrl+O, then press Enter.",
            )
            self.assertEqual(pending["menu.html"], "machine_translated")


class GlossaryTests(TestCase):
    GLOSSARY = {
        "terms": {
            "save": {"en": "save", "ko": "저장", "note": "verb on buttons"},
            "calendar": {"en": "Calendar", "ko": "캘린더"},
            "even": {"en": "even", "ko": "짝수"},
            "keyboard_key": {"en": "keyboard key", "ko": "키"},
        },
        "locales": {"de": {"save": "Speichern", "keyboard_key": ["Taste", "Tasten"]}},
    }

    def test_terms_match_whole_words_case_insensitively_outside_protected_tokens(self):
        matches = i18n_sync.glossary_matches(
            "Save the event in Air Calendar ({save_count}).", "de", self.GLOSSARY
        )

        self.assertEqual(
            matches,
            [
                {
                    "term": "save",
                    "en": "save",
                    "ko": "저장",
                    "translation": "Speichern",
                    "note": "verb on buttons",
                }
            ],
        )
        self.assertEqual(
            [
                m["term"]
                for m in i18n_sync.glossary_matches("Press a keyboard\nkey.", "fr", self.GLOSSARY)
            ],
            ["keyboard_key"],
        )
        self.assertEqual(i18n_sync.glossary_matches("Saved events", "de", self.GLOSSARY), [])

    def test_warnings_only_for_terms_with_a_locale_wording_missing_from_the_translation(self):
        english = "Save the keyboard key."
        self.assertEqual(
            i18n_sync.glossary_warnings(english, "Die TASTE speichern.", "de", self.GLOSSARY), []
        )
        warnings = i18n_sync.glossary_warnings(english, "Die Taste sichern.", "de", self.GLOSSARY)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Speichern", warnings[0])
        self.assertEqual(i18n_sync.glossary_warnings(english, "Sauver", "fr", self.GLOSSARY), [])
        self.assertEqual(i18n_sync.glossary_warnings(english, "Store", "en", self.GLOSSARY), [])

    def test_missing_glossary_file_disables_every_glossary_feature(self):
        with tempfile.TemporaryDirectory() as temporary:
            glossary = i18n_sync.load_glossary(Path(temporary) / "missing.json")

        self.assertEqual(glossary, {"terms": {}, "locales": {}})
        self.assertEqual(i18n_sync.glossary_matches("Save", "de", glossary), [])
        self.assertEqual(i18n_sync.glossary_warnings("Save", "Sichern", "de", glossary), [])


class ReviewRoundTripTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.locales = self.root / "locales"
        self.locales.mkdir()
        self.source = self.root / "calendar_app"
        self.source.mkdir()
        self.pending = self.root / "pending.json"
        # Never read the real glossary; tests that need one write this file.
        self.glossary = self.root / "glossary.json"
        self.addCleanup(setattr, i18n_sync, "GLOSSARY_PATH", i18n_sync.GLOSSARY_PATH)
        i18n_sync.GLOSSARY_PATH = self.glossary
        documents = {
            "ko": {"menu": {"save": "저장", "count": "{count}개 열기 (Ctrl+O)"}},
            "en": {"menu": {"save": "Save", "count": "Open {count} items (Ctrl+O)"}},
            "de": {"menu": {"save": "Save", "count": "Open {count} items (Ctrl+O)"}},
        }
        for code, data in documents.items():
            i18n_sync.save_locale(self.locales / f"{code}.json", data)
        (self.source / "view.py").write_text(
            "label.setText(t('menu.save', '저장'))\n", encoding="utf-8", errors="strict"
        )
        i18n_sync.save_pending_review(
            {"de": {"menu.save": "short_label", "menu.count": "machine_translated"}},
            self.pending,
        )

    def export(self):
        path = self.root / "review.json"
        entries = i18n_sync.export_review(
            path, locales_dir=self.locales, pending_path=self.pending, source_dir=self.source
        )
        return path, entries

    def test_export_lists_source_text_and_code_locations(self):
        _, entries = self.export()
        save = next(entry for entry in entries if entry["key"] == "menu.save")
        self.assertEqual(save["en"], "Save")
        self.assertEqual(save["ko"], "저장")
        self.assertEqual(save["current"], "Save")
        self.assertEqual(save["locations"], ["calendar_app/view.py:1"])
        self.assertEqual(save["translation"], "")

    def test_import_applies_valid_reviews_and_rejects_broken_placeholders(self):
        path, entries = self.export()
        for entry in entries:
            entry["translation"] = {
                "menu.save": "Speichern",
                "menu.count": "{anzahl} Elemente öffnen (Strg+O)",
            }[entry["key"]]
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8", errors="strict")

        applied, rejected = i18n_sync.import_review(
            path, locales_dir=self.locales, pending_path=self.pending
        )

        self.assertEqual([entry["key"] for entry in applied], ["menu.save"])
        self.assertEqual([entry["key"] for entry in rejected], ["menu.count"])
        self.assertIn("placeholders", rejected[0]["problem"])
        german = i18n_sync.load_locale(self.locales / "de.json")
        self.assertEqual(german["menu"]["save"], "Speichern")
        self.assertEqual(german["menu"]["count"], "Open {count} items (Ctrl+O)")
        self.assertEqual(
            i18n_sync.load_pending_review(self.pending),
            {"de": {"menu.count": "machine_translated"}},
        )

    def test_review_rejects_glued_brand_and_file_names(self):
        self.assertIn(
            "protected",
            i18n_sync.review_problem(
                "Air Calendar is already running.", "Air Calendario è già in esecuzione.", "it"
            ),
        )
        self.assertIn(
            "protected",
            i18n_sync.review_problem("Add clear_day.webp", "أضف وclear_day.webp", "ar"),
        )
        for code, text in (
            ("ja", "Air Calendarはすでに実行中です。"),
            ("de", "Air Calendar läuft bereits."),
        ):
            self.assertIsNone(
                i18n_sync.review_problem("Air Calendar is already running.", text, code)
            )
        self.assertIsNone(
            i18n_sync.review_problem("Add clear_day.webp", "まずclear_day.webpを追加", "ja")
        )

    def test_english_for_a_no_english_key_is_checked_against_korean(self):
        i18n_sync.save_locale(
            self.locales / "ko.json",
            {"menu": {"save": "저장", "count": "{count}개 열기 (Ctrl+O)", "new": "{name} 추가"}},
        )
        i18n_sync.save_pending_review({"en": {"menu.new": "no_english"}}, self.pending)
        path, entries = self.export()
        self.assertEqual([(entry["key"], entry["en"]) for entry in entries], [("menu.new", None)])
        entries[0]["translation"] = "Add {name}"
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8", errors="strict")

        applied, rejected = i18n_sync.import_review(
            path, locales_dir=self.locales, pending_path=self.pending
        )

        self.assertEqual((len(applied), rejected), (1, []))
        english = i18n_sync.load_locale(self.locales / "en.json")
        self.assertEqual(english["menu"]["new"], "Add {name}")
        self.assertEqual(i18n_sync.load_pending_review(self.pending), {})

    def write_glossary(self, terms, locales):
        self.glossary.write_text(
            json.dumps({"version": 1, "terms": terms, "locales": locales}, ensure_ascii=False),
            encoding="utf-8",
            errors="strict",
        )

    def write_review(self, path, entries, translations):
        for entry in entries:
            entry["translation"] = translations[entry["key"]]
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8", errors="strict")

    def test_export_context_has_screen_neighbors_and_glossary(self):
        items = {f"item{index}": f"Item {index}" for index in range(8)}
        english = {"save": "Save the event in Air Calendar", "count": "Open {count}", **items}
        german = {"save": "Save the event in Air Calendar", "count": "{count} öffnen"}
        korean = {key: "번역" for key in english}
        for code, values in (("en", english), ("de", german), ("ko", korean)):
            i18n_sync.save_locale(self.locales / f"{code}.json", {"menu": values})
        i18n_sync.save_pending_review(
            {"de": {"menu.save": "untranslated", "menu.item4": "untranslated"}}, self.pending
        )
        self.write_glossary(
            {
                "save": {"en": "Save", "ko": "저장", "note": "button verb"},
                "calendar": {"en": "calendar", "ko": "캘린더"},
                "even": {"en": "even", "ko": "짝수"},
            },
            {"de": {"save": "Speichern"}},
        )

        _, entries = self.export()

        save = next(entry for entry in entries if entry["key"] == "menu.save")
        for field in ("locale", "key", "reason", "en", "ko", "current", "locations"):
            self.assertIn(field, save)
        context = save["context"]
        self.assertEqual(context["screen"], "view.py")
        self.assertEqual(
            [neighbor["key"] for neighbor in context["neighbors"]],
            [f"menu.item{index}" for index in range(3, 8)],
        )
        self.assertEqual(
            context["neighbors"][0], {"key": "menu.item3", "en": "Item 3", "current": None}
        )
        self.assertEqual(
            context["glossary"],
            [
                {
                    "term": "save",
                    "en": "Save",
                    "ko": "저장",
                    "translation": "Speichern",
                    "note": "button verb",
                }
            ],
        )
        item4 = next(entry for entry in entries if entry["key"] == "menu.item4")
        self.assertEqual(item4["context"]["screen"], "menu (no literal key in code)")
        self.assertEqual(
            [neighbor["key"] for neighbor in item4["context"]["neighbors"]],
            ["menu.item2", "menu.item3", "menu.item5", "menu.item6", "menu.item7"],
        )
        self.assertEqual(item4["context"]["glossary"], [])

    def test_export_context_works_without_a_glossary_file(self):
        _, entries = self.export()

        count = next(entry for entry in entries if entry["key"] == "menu.count")
        self.assertEqual(count["context"]["glossary"], [])
        self.assertEqual(
            count["context"]["neighbors"],
            [{"key": "menu.save", "en": "Save", "current": "Save"}],
        )

    def test_screen_hint_lists_distinct_source_files(self):
        locations = [
            "calendar_app/presentation/a.py:1",
            "calendar_app/presentation/a.py:9",
            "calendar_app/b.py:2",
            "calendar_app/c.py:3",
            "calendar_app/d.py:4",
        ]
        self.assertEqual(
            i18n_sync.screen_hint("menu.save", locations), "a.py, b.py, c.py (+1 more)"
        )

    def test_import_with_review_status_keeps_applied_keys_pending(self):
        path, entries = self.export()
        self.write_review(
            path,
            entries,
            {"menu.save": "Speichern", "menu.count": "{count} Elemente öffnen (Strg+O)"},
        )

        applied, rejected = i18n_sync.import_review(
            path,
            locales_dir=self.locales,
            pending_path=self.pending,
            review_status="machine_translated",
        )

        self.assertEqual((len(applied), rejected), (2, []))
        german = i18n_sync.load_locale(self.locales / "de.json")
        self.assertEqual(german["menu"]["save"], "Speichern")
        self.assertEqual(german["menu"]["count"], "{count} Elemente öffnen (Strg+O)")
        self.assertEqual(
            i18n_sync.load_pending_review(self.pending),
            {"de": {"menu.count": "machine_translated", "menu.save": "machine_translated"}},
        )

    def test_import_warns_about_missing_glossary_terms_without_rejecting(self):
        self.write_glossary(
            {
                "save": {"en": "save", "ko": "저장"},
                "open": {"en": "Open", "ko": "열기"},
                "items": {"en": "items", "ko": "항목"},
            },
            {"de": {"save": "Speichern", "open": "Öffnen", "items": ["Elemente", "Einträge"]}},
        )
        path, entries = self.export()
        self.write_review(
            path,
            entries,
            {"menu.save": "Sichern", "menu.count": "{count} Elemente öffnen (Strg+O)"},
        )

        applied, rejected = i18n_sync.import_review(
            path, locales_dir=self.locales, pending_path=self.pending
        )

        self.assertEqual(rejected, [])
        warnings = {entry["key"]: entry["warnings"] for entry in applied}
        self.assertEqual(warnings["menu.count"], [])
        self.assertEqual(len(warnings["menu.save"]), 1)
        self.assertIn("Speichern", warnings["menu.save"][0])
        self.assertEqual(i18n_sync.load_locale(self.locales / "de.json")["menu"]["save"], "Sichern")
        self.assertEqual(i18n_sync.load_pending_review(self.pending), {})

    def test_cli_import_passes_review_status_and_prints_warnings(self):
        result = ([{"locale": "de", "key": "menu.save", "warnings": ["glossary save: x"]}], [])
        output = io.StringIO()
        with (
            patch.object(i18n_sync, "import_review", return_value=result) as importer,
            contextlib.redirect_stdout(output),
        ):
            code = i18n_sync.main(
                ["--import-review", "review.json", "--review-status", "machine_translated"]
            )

        self.assertEqual(code, 0)
        importer.assert_called_once_with(Path("review.json"), review_status="machine_translated")
        self.assertIn("glossary warnings 1", output.getvalue())
        self.assertIn("pending review as machine_translated", output.getvalue())
        self.assertIn("de menu.save: glossary save: x", output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            i18n_sync.main(["--review-status", "machine_translated"])

    def test_review_accepts_localized_modifiers_but_not_a_changed_key(self):
        english = "Open {count} items (Ctrl+O)"
        self.assertIsNone(i18n_sync.review_problem(english, "{count} öffnen (Strg+O)", "de"))
        self.assertIn(
            "protected", i18n_sync.review_problem(english, "{count} öffnen (Strg+Ö)", "de")
        )
        self.assertIn("Hangul", i18n_sync.review_problem(english, "{count} 열기 (Ctrl+O)", "de"))


class ProcessLocaleTranslatorTests(TestCase):
    """process_locale() with a fake deep_translator module: no network."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.locales = Path(temporary.name)
        self.created = []
        created = self.created

        class FakeGoogleTranslator:
            def __init__(self, source, target):
                created.append((source, target))
                self.target = target

            def translate(self, text):
                return f"[{self.target}] {text}"

        fake_module = types.SimpleNamespace(GoogleTranslator=FakeGoogleTranslator)
        patcher = patch.dict(sys.modules, {"deep_translator": fake_module})
        patcher.start()
        self.addCleanup(patcher.stop)
        glossary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(glossary_dir.cleanup)
        self.glossary = Path(glossary_dir.name) / "i18n_glossary.json"
        for name, value in (
            ("LOCALES_DIR", self.locales),
            ("_en_data_cache", None),
            ("GLOSSARY_PATH", self.glossary),
        ):
            self.addCleanup(setattr, i18n_sync, name, getattr(i18n_sync, name))
            setattr(i18n_sync, name, value)
        self.korean = {
            "probe": {
                "save": "저장",
                "long": "변경 내용을 저장한 뒤 창을 닫습니다. 계속할까요?",
                "known": "알려진 문구",
            }
        }
        documents = {
            "ko": self.korean,
            "en": {"probe": {"known": "Close the window after saving your changes."}},
            "de": {"probe": {}},
        }
        for code, data in documents.items():
            i18n_sync.save_locale(self.locales / f"{code}.json", data)

    def test_auto_translate_sends_english_only_and_skips_en_json(self):
        pending = {}
        for code in ("de", "en"):
            pending[code] = {}
            i18n_sync.process_locale(
                i18n_sync.normalize_locale_data(self.korean),
                self.locales / f"{code}.json",
                fill=True,
                limit=1,
                auto_translate=True,
                pending=pending[code],
            )

        self.assertEqual(self.created, [("en", "de")])
        german = i18n_sync.load_locale(self.locales / "de.json")
        english = i18n_sync.load_locale(self.locales / "en.json")
        self.assertEqual(
            german["probe"], {"known": "[de] Close the window after saving your changes."}
        )
        self.assertEqual(english["probe"], {"known": "Close the window after saving your changes."})
        for code in ("de", "en"):
            self.assertEqual(pending[code]["probe.save"], "no_english")
            self.assertEqual(pending[code]["probe.long"], "no_english")
        self.assertEqual(pending["de"]["probe.known"], "machine_translated")
        self.assertNotIn("probe.known", pending["en"])

    def test_auto_translate_checks_the_glossary_file(self):
        self.glossary.write_text(
            json.dumps(
                {
                    "version": 1,
                    "terms": {"window": {"en": "window", "ko": "창"}},
                    "locales": {"de": {"window": "Fenster"}},
                }
            ),
            encoding="utf-8",
            errors="strict",
        )
        pending = {}

        i18n_sync.process_locale(
            i18n_sync.normalize_locale_data(self.korean),
            self.locales / "de.json",
            fill=True,
            limit=1,
            auto_translate=True,
            pending=pending,
        )

        german = i18n_sync.load_locale(self.locales / "de.json")
        self.assertEqual(
            german["probe"]["known"], "[de] Close the window after saving your changes."
        )
        self.assertEqual(pending["probe.known"], "glossary_check")


class LineEndingTests(TestCase):
    DATA = {"menu": {"save": "Speichern", "msg": "Zeile 1\nZeile 2"}, "about": "Air Calendar"}

    def canonical(self):
        return i18n_sync.render_locale_json(i18n_sync.normalize_locale_data(self.DATA)) + "\n"

    def test_save_locale_keeps_the_existing_line_ending_and_new_files_use_lf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            new, crlf, lf = root / "new.json", root / "crlf.json", root / "lf.json"
            crlf.write_bytes(b'{\r\n  "about": "old"\r\n}\r\n')
            lf.write_bytes(b'{\n  "about": "old"\n}\n')

            for path in (new, crlf, lf):
                i18n_sync.save_locale(path, self.DATA)

            self.assertEqual(new.read_bytes(), self.canonical().encode("utf-8", errors="strict"))
            self.assertEqual(lf.read_bytes(), self.canonical().encode("utf-8", errors="strict"))
            self.assertEqual(
                crlf.read_bytes(),
                self.canonical().replace("\n", "\r\n").encode("utf-8", errors="strict"),
            )
            self.assertEqual(i18n_sync.load_locale(crlf), self.DATA)

    def test_pending_review_file_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pending.json"
            path.write_bytes(b'{\r\n "de": {}\r\n}\r\n')

            i18n_sync.save_pending_review({"de": {"menu.save": "untranslated"}}, path)

            self.assertEqual(
                path.read_bytes(), b'{\r\n "de": {\r\n  "menu.save": "untranslated"\r\n }\r\n}\r\n'
            )


class I18nSyncTests(TestCase):
    def test_compare_locale_detects_missing_extra_and_placeholder_issues(self):
        base = {
            "menu": {
                "save": "저장",
                "count": "{count}개 저장",
            }
        }
        target = {
            "menu": {
                "count": "{total} saved",
                "unused": "x",
            }
        }

        issues = i18n_sync.compare_locale(base, target)

        self.assertEqual(issues["missing"], ["menu.save"])
        self.assertEqual(issues["extra"], ["menu.unused"])
        self.assertEqual(issues["placeholder_mismatch"], ["menu.count"])

    def test_fill_missing_only_copies_absent_keys(self):
        base = {"gcal": {"sync": "동기화", "status": {"ok": "정상"}}}
        target = {"gcal": {"sync": "Sync"}}

        changed = i18n_sync.fill_missing(base, target)

        self.assertTrue(changed)
        self.assertEqual(target["gcal"]["sync"], "Sync")
        self.assertEqual(target["gcal"]["status"]["ok"], "정상")

    def test_repair_placeholder_mismatches_uses_safe_fallback(self):
        base = {"focus": {"duration": "{minutes}분 {seconds}초"}}
        target = {"focus": {"duration": "{분}m {초}s"}}
        fallback = {"focus": {"duration": "{minutes}m {seconds}s"}}

        changed = i18n_sync.repair_placeholder_mismatches(base, target, fallback)

        self.assertTrue(changed)
        self.assertEqual(target["focus"]["duration"], "{minutes}m {seconds}s")

    def test_compare_locale_detects_broken_text_and_type_mismatch(self):
        base = {"dialog": {"title": "설정", "items": ["하나", "둘"]}}
        target = {"dialog": {"title": "???", "items": {"0": "one"}}}

        issues = i18n_sync.compare_locale(base, target)

        self.assertEqual(issues["broken"], ["dialog.title"])
        self.assertEqual(issues["type_mismatch"], ["dialog.items"])

    def test_compare_locale_allows_extra_list_entries(self):
        base = {"palette": {"kw": {"theme": ["theme", "dark"]}}}
        target = {"palette": {"kw": {"theme": ["theme", "dark", "light", "color"]}}}

        issues = i18n_sync.compare_locale(base, target)

        self.assertEqual(issues["type_mismatch"], [])
        self.assertEqual(issues["missing"], [])

    def test_compare_locale_allows_shorter_list_entries(self):
        base = {"palette": {"kw": {"theme": ["theme", "dark", "light"]}}}
        target = {"palette": {"kw": {"theme": ["theme", "dark"]}}}

        issues = i18n_sync.compare_locale(base, target)

        self.assertEqual(issues["type_mismatch"], [])
        self.assertEqual(issues["missing"], [])

    def test_all_locale_files_match_korean_base_structure(self):
        base_path, target_paths = i18n_sync.locale_paths("ko", None)
        base_data = i18n_sync.normalize_locale_data(i18n_sync.load_locale(base_path))

        problems = {}
        for path in target_paths:
            target_data = i18n_sync.normalize_locale_data(i18n_sync.load_locale(path))
            issues = i18n_sync.compare_locale(base_data, target_data)
            summary = {key: values for key, values in issues.items() if values}
            if summary:
                problems[path.name] = {key: values[:10] for key, values in summary.items()}

        self.assertFalse(problems, msg=f"Locale files out of sync with ko base: {problems}")

    def test_non_korean_locale_files_do_not_leave_hangul_values(self):
        hangul_re = re.compile(r"[\u3131-\u318E\uAC00-\uD7A3]")
        _, target_paths = i18n_sync.locale_paths("ko", None)

        def walk_strings(node, prefix=""):
            if isinstance(node, dict):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else key
                    yield from walk_strings(value, path)
                return
            if isinstance(node, list):
                for index, value in enumerate(node):
                    yield from walk_strings(value, f"{prefix}[{index}]")
                return
            if isinstance(node, str):
                yield prefix or "<root>", node

        problems = {}
        for path in target_paths:
            data = i18n_sync.normalize_locale_data(i18n_sync.load_locale(path))
            bad_keys = [key for key, value in walk_strings(data) if hangul_re.search(value)]
            if bad_keys:
                problems[path.name] = bad_keys[:20]

        self.assertFalse(problems, msg=f"Non-ko locales still contain Hangul text: {problems}")
