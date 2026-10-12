# -*- coding: utf-8 -*-
"""Regression cases for malformed task input and failed shared-DB transactions."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from calendar_app.domain.task_validation import normalize_task_payload
from calendar_app.infrastructure.db import shared_db, task_repo
from calendar_app.shared.datetime_utils import parse_datetime_str, to_iso_with_tz
from tests.support import TemporaryDatabaseTestCase


@pytest.mark.parametrize("value", ["0", "false", "off", "no"])
def test_false_text_does_not_enable_task_flags(value):
    row, issues = normalize_task_payload({"name": "flag", "all_day": value, "is_completed": value})
    assert not issues
    assert row["all_day"] == row["is_completed"] == 0


@pytest.mark.parametrize("value", [float("inf"), -float("inf"), float("nan"), 1.5, True])
def test_invalid_series_number_is_a_validation_issue(value):
    _, issues = normalize_task_payload({"name": "series", "series_total": value})
    assert any(issue.field == "series_total" and issue.code == "invalid_int" for issue in issues)


@pytest.mark.parametrize("value", ["2026-10-08 10:30:99", "2026-10-08 10:30garbage"])
def test_invalid_datetime_suffix_is_not_silently_discarded(value):
    _, issues = normalize_task_payload({"name": "time", "deadline": value})
    assert any(issue.field == "deadline" and issue.code == "invalid_datetime" for issue in issues)


@pytest.mark.parametrize("value", ["2026-10-08 25:99:00", "2026-10-08junk", "not a date"])
def test_invalid_shared_datetime_does_not_turn_into_midnight(value):
    assert parse_datetime_str(value) is None


@pytest.mark.parametrize("value", [None, ""])
def test_absent_iso_input_returns_none(value):
    assert to_iso_with_tz(value) is None


def test_timezone_conversion_overflow_returns_none():
    assert parse_datetime_str("9999-12-31T23:30:00Z") is None


def test_valid_timezone_conversion_and_minute_input_remain_supported():
    assert parse_datetime_str("2026-10-08T09:15:00+00:00") == datetime(2026, 10, 8, 18, 15)
    assert parse_datetime_str("2026-10-08 09:15") == datetime(2026, 10, 8, 9, 15)


def test_date_only_all_day_payload_remains_supported():
    row, issues = normalize_task_payload(
        {"name": "Holiday", "all_day": True, "deadline": "2026-10-08", "end_date": "2026-10-09"}
    )
    assert not issues
    assert row["deadline"] == "2026-10-08 00:00:00"
    assert row["end_date"] == "2026-10-09 00:00:00"
    assert row["all_day"] == 1


@pytest.mark.parametrize("value", [[], {}, 123])
def test_invalid_datetime_type_does_not_reach_cache_hashing(value):
    assert parse_datetime_str(value) is None
    assert parse_datetime_str("2026-10-08 09:15", value) is None


@pytest.mark.parametrize("field", ["target_date", "period_start", "period_end"])
def test_invalid_date_suffix_is_rejected(field):
    _, issues = normalize_task_payload({"name": "Date", field: "2026-10-08garbage"})
    assert any(issue.field == field and issue.code == "invalid_date" for issue in issues)


class TestTaskValidationPersistence(TemporaryDatabaseTestCase):
    def test_invalid_update_preserves_existing_deadline(self):
        task_id = task_repo.create_unified_task(
            {"name": "Keep schedule", "deadline": "2026-10-08 10:30:00"}
        )
        assert not task_repo.update_unified_task(task_id, {"deadline": "bad time"})
        assert task_repo.get_unified_task(task_id)["deadline"] == "2026-10-08 10:30:00"

    def test_invalid_create_does_not_insert_an_undated_task(self):
        assert task_repo.create_unified_task({"name": "Bad time", "deadline": "bad time"}) is None


@pytest.fixture
def shared_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_db, "SHARED_DIR", str(tmp_path))
    monkeypatch.setattr(shared_db, "SHARED_DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setattr(shared_db, "_conn", None)
    yield
    if shared_db._conn is not None:
        shared_db._conn.close()
        shared_db._conn = None


def test_shared_schema_failure_is_not_cached_and_can_retry(shared_connection):
    with patch.object(shared_db, "_initialize_schema", side_effect=RuntimeError("schema failed")):
        assert shared_db._get_connection() is None
    assert shared_db._conn is None
    assert shared_db.upsert_shared_calendar("shared::work", "Work")


def test_shared_failed_delete_rolls_back_detachment_before_next_write(shared_connection):
    assert shared_db.upsert_shared_calendar("shared::work", "Work")
    task_id = shared_db.insert_shared_task("Keep ownership", calendar_id="shared::work")
    conn = shared_db._get_connection()
    conn.execute(
        "CREATE TRIGGER block_calendar_delete BEFORE DELETE ON shared_calendar "
        "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
    )
    conn.commit()
    assert not shared_db.delete_shared_calendar("shared::work")
    assert not conn.in_transaction
    assert shared_db.upsert_shared_calendar("shared::other", "Other")
    row = conn.execute("SELECT calendar_id FROM shared_task WHERE id=?", (task_id,)).fetchone()
    assert row["calendar_id"] == "shared::work"


@pytest.mark.parametrize("size", ["bad", float("inf"), [], 10**100])
def test_bootstrap_font_recovers_corrupt_saved_size(tmp_path, size):
    from PyQt6.QtCore import QSettings

    from calendar_app import bootstrap

    settings = QSettings(str(tmp_path / "font.ini"), QSettings.Format.IniFormat)
    settings.setValue("font_size", size)
    settings.setValue("font_family", [])
    fonts = []
    app = SimpleNamespace(setFont=fonts.append)
    with patch.object(bootstrap, "QSettings", return_value=settings):
        bootstrap._apply_saved_font(app, lambda family, points: (family, points))
    assert fonts[0][0] == "Segoe UI"
    assert 1 <= fonts[0][1] <= 256
    assert settings.value("font_size", type=int) == fonts[0][1]
    assert settings.value("font_family") == "Segoe UI"
