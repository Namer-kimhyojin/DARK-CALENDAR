import importlib.util
from pathlib import Path
import re
from unittest import TestCase

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "i18n_sync.py"
SPEC = importlib.util.spec_from_file_location("i18n_sync", MODULE_PATH)
i18n_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(i18n_sync)


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
