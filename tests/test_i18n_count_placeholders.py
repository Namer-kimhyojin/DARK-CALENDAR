# -*- coding: utf-8 -*-
"""Counts and day numbers render through one translated string with a placeholder.

The task dialog used to glue numbers to translated fragments: "3checklist items
added.", "(5items)", "1th, 2th, 3th" and "📋 12 Done: ...". Each text is now one key
with {count} or {day}, so every language places the number itself. A template's item
count reuses checklist_mgr.n_items, the text the checklist manager shows. Languages
that inflect a noun after a number write "Label: {count}", so 1 reads correctly too.

The rendering checks read the bundled locale files, so they pass once the
integration step has written the new keys. Locales are swapped in memory: the
settings store is never touched.
"""

from contextlib import contextmanager
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QListWidget
import pytest
from scripts.i18n_sync import flatten_locale, placeholders

from calendar_app.infrastructure.i18n import I18nManager, i18n, t
from calendar_app.presentation.dialogs import task_dialog_base, task_dialog_unified
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    month_day_options,
    recurrence_summary,
)

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
CODES = sorted(path.stem for path in LOCALES.glob("*.json"))

NEW_KEYS = {
    "dialog.checklist.items_added_count": {"count"},
    "dialog.recurrence.day_of_month": {"day"},
    "dialog.recurrence.preview_range": {"count", "first", "last"},
    "dialog.recurrence.preview_dates": {"count", "dates"},
}
OLD_KEYS = (
    "dialog.checklist.items_added",
    "dialog.checklist.item_unit",
    "dialog.recurrence.day_unit",
    # Duplicated checklist_mgr.n_items.
    "dialog.checklist.item_count",
)
ITEM_COUNT_KEY = "checklist_mgr.n_items"
# Where a plural noun or verb after the number would misread 1 ("1 items").
_INFLECTING = ("en", "de", "es", "fr", "it", "nl", "pt", "ar", "ru")
LABEL_FIRST = {
    ITEM_COUNT_KEY: ("n", _INFLECTING),
    "dialog.checklist.items_added_count": ("count", (*_INFLECTING, "hi")),
}

EXPECTED = {
    "ko": {
        "items_added": "3개의 체크리스트 항목을 추가했습니다.",
        "items_added_one": "1개의 체크리스트 항목을 추가했습니다.",
        "item_count": "5개",
        "item_count_one": "1개",
        "day": "15일",
        "preview_range": "📋 생성될 일정 14개: 1/5 → 2/6",
        "preview_dates": "📋 생성될 일정 2개: 1/5, 2/5",
    },
    "en": {
        "items_added": "Checklist items added: 3.",
        "items_added_one": "Checklist items added: 1.",
        "item_count": "Items: 5",
        "item_count_one": "Items: 1",
        "day": "Day 15",
        "preview_range": "📋 Tasks to create (14): 1/5 → 2/6",
        "preview_dates": "📋 Tasks to create (2): 1/5, 2/5",
    },
    "de": {
        "items_added": "Hinzugefügte Checklisteneinträge: 3.",
        "items_added_one": "Hinzugefügte Checklisteneinträge: 1.",
        "item_count": "Einträge: 5",
        "item_count_one": "Einträge: 1",
        "day": "15. Tag",
        "preview_range": "📋 Zu erstellende Aufgaben (14): 1/5 → 2/6",
        "preview_dates": "📋 Zu erstellende Aufgaben (2): 1/5, 2/5",
    },
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _bundle(code):
    return I18nManager._load_locale_json(str(LOCALES / f"{code}.json"), code)


@contextmanager
def _locale(code):
    """Serve one bundled locale with the English fallback, in memory only."""
    with (
        patch.object(i18n, "translations", _bundle(code)),
        patch.object(i18n, "bundled_translations", {}),
        patch.object(i18n, "fallback_translations", _bundle("en")),
        patch.object(i18n, "lang", code),
    ):
        yield


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_new_keys_render_whole_texts(code):
    expected = EXPECTED[code]
    with _locale(code):
        assert t("dialog.checklist.items_added_count", count=3) == expected["items_added"]
        assert t("dialog.checklist.items_added_count", count=1) == expected["items_added_one"]
        assert t(ITEM_COUNT_KEY, n=5) == expected["item_count"]
        assert t(ITEM_COUNT_KEY, n=1) == expected["item_count_one"]
        assert t("dialog.recurrence.day_of_month", day=15) == expected["day"]
        assert (
            t("dialog.recurrence.preview_range", count=14, first="1/5", last="2/6")
            == expected["preview_range"]
        )
        assert (
            t("dialog.recurrence.preview_dates", count=2, dates="1/5, 2/5")
            == expected["preview_dates"]
        )


@pytest.mark.parametrize("code", CODES)
def test_every_locale_has_the_new_keys_and_drops_the_fragments(code):
    flat = flatten_locale(_bundle(code))
    for key, fields in NEW_KEYS.items():
        assert key in flat, f"{code} misses {key}"
        assert placeholders(flat[key]) == fields, f"{code} {key}: {flat[key]!r}"
        assert flat[key] == flat[key].strip(), f"{code} {key} has edge spaces"
    for key in OLD_KEYS:
        assert key not in flat, f"{code} still has {key}"
    assert placeholders(flat[ITEM_COUNT_KEY]) == {"n"}, f"{code}: {flat[ITEM_COUNT_KEY]!r}"


@pytest.mark.parametrize(
    ("key", "code"),
    [(key, code) for key, (_field, codes) in LABEL_FIRST.items() for code in codes],
)
def test_inflecting_languages_put_the_count_after_a_label(key, code):
    field = LABEL_FIRST[key][0]
    value = flatten_locale(_bundle(code))[key]
    assert re.search(r":\s*\{" + field + r"\}\W*$", value), f"{code} {key}: {value!r}"


def test_zh_mirrors_zh_cn_for_the_new_keys():
    zh, zh_cn = flatten_locale(_bundle("zh")), flatten_locale(_bundle("zh-CN"))
    for key in (*NEW_KEYS, ITEM_COUNT_KEY):
        assert zh.get(key) == zh_cn.get(key), key


@pytest.mark.parametrize(
    ("code", "first", "fifteenth", "last"),
    [
        ("ko", "1일", "15일", "말일"),
        ("en", "Day 1", "Day 15", "Last Day"),
        ("de", "1. Tag", "15. Tag", "Letzter Tag"),
    ],
)
def test_month_day_combo_uses_one_string_per_day(code, first, fifteenth, last):
    with _locale(code):
        options = month_day_options()
    assert [value for _label, value in options] == [*range(1, 32), "last"]
    assert options[0][0] == first
    assert options[14][0] == fifteenth
    assert options[-1][0] == last
    assert not any(re.search(r"\d(st|nd|rd|th)\b", label) for label, _value in options)


@pytest.mark.parametrize(
    ("code", "expected"),
    [("ko", "월간 반복 · 15일"), ("en", "Monthly · Day 15"), ("de", "Monatlich · 15. Tag")],
)
def test_monthly_summary_names_the_day(code, expected):
    with _locale(code):
        text = recurrence_summary(QDate(2026, 3, 15), "monthly", "mode=day_of_month;slot=1;day=15")
    assert text == expected


@pytest.mark.parametrize(("count", "expected_key"), [(5, "item_count"), (1, "item_count_one")])
@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_template_combo_shows_the_item_count_as_one_text(app, code, count, expected_key):
    host = SimpleNamespace(checklist_template_combo=QComboBox())
    template = {"id": 7, "name": "Weekly", "checklist_type": "list"}
    repo = task_dialog_base.checklist_template_repo
    with (
        _locale(code),
        patch.object(repo, "get_all_checklist_templates", return_value=[template]),
        patch.object(repo, "get_checklist_items", return_value=[{}] * count),
    ):
        task_dialog_base.BaseTaskDialog._load_checklist_templates(host)
        type_text = t("dialog.checklist.type_list")
    combo = host.checklist_template_combo
    assert combo.count() == 2
    assert combo.itemText(1) == f"  Weekly [{type_text}] ({EXPECTED[code][expected_key]})"
    assert combo.itemData(1) == 7


@pytest.mark.parametrize(
    ("names", "expected_key"), [(("a", "b", "c"), "items_added"), (("a",), "items_added_one")]
)
@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_template_items_added_message_is_one_text(app, code, names, expected_key):
    host = SimpleNamespace(
        _is_modify=False,
        checklist_widget=QListWidget(),
        checklist_display_type="list",
        _refresh_checklist_display=lambda: None,
    )
    repo = task_dialog_unified.checklist_template_repo
    items = [{"item_text": name} for name in names]
    with (
        _locale(code),
        patch.object(repo, "get_checklist_template", return_value={"checklist_type": "list"}),
        patch.object(repo, "get_checklist_items", return_value=items),
        patch.object(task_dialog_unified.QMessageBox, "information") as information,
    ):
        task_dialog_unified.UnifiedTaskDialog._load_checklist_from_template(host, 7)
    assert host.checklist_widget.count() == len(names)
    assert information.call_args.args[2] == EXPECTED[code][expected_key]


def _preview_host(dates):
    start, end = dates[0], dates[-1]
    return SimpleNamespace(
        routine_preview_label=QLabel(),
        repeat_task_radio=object(),
        single_task_radio=SimpleNamespace(isChecked=lambda: False),
        routine_period_end_date=SimpleNamespace(date=lambda: end),
        start_date=SimpleNamespace(date=lambda: start),
        _get_routine_cycle_type=lambda: "monthly",
        _iter_routine_dates=lambda *_args: dates,
        _ui_tokens=dict,
    )


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_routine_preview_counts_tasks_to_create(app, code):
    few = _preview_host([QDate(2026, 1, 5), QDate(2026, 2, 5)])
    many = _preview_host(
        [QDate(2026, 1, 5), *(QDate(2026, 1, 6 + i) for i in range(12)), QDate(2026, 2, 6)]
    )
    with _locale(code):
        task_dialog_unified.UnifiedTaskDialog._update_routine_preview(few)
        task_dialog_unified.UnifiedTaskDialog._update_routine_preview(many)
    assert few.routine_preview_label.text() == EXPECTED[code]["preview_dates"]
    assert many.routine_preview_label.text() == EXPECTED[code]["preview_range"]


def test_code_no_longer_reads_the_fragment_keys():
    pattern = re.compile("|".join(re.escape(key) + r"(?![\w.])" for key in OLD_KEYS))
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}: {match.group(0)}"
        for path in sorted((ROOT / "calendar_app").rglob("*.py"))
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="strict"))
    ]
    assert offenders == []


def test_task_dialogs_do_not_glue_numbers_to_translations():
    glued = re.compile(r"\{[\w\[\]'\"().]+\}\s*\{t\(")
    for module in (task_dialog_base, task_dialog_unified):
        source = Path(module.__file__).read_text(encoding="utf-8", errors="strict")
        lines = [line.strip() for line in source.splitlines() if glued.search(line)]
        # Only the duration units are left; they are tracked separately.
        assert all("dialog.task.unit_" in line for line in lines), lines
