# -*- coding: utf-8 -*-
"""Google sync texts state their real scope and counts, in any UI language."""

import ast
from copy import deepcopy
from pathlib import Path
import re
import string
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox
import pytest

from calendar_app.infrastructure.db import calendar_repo, database_unified, task_repo
from calendar_app.infrastructure.google_sync import common, engine, helpers
from calendar_app.infrastructure.google_sync import service as gcal_service
from calendar_app.infrastructure.i18n import I18nManager, i18n, t
from calendar_app.presentation.dialogs import gcal_settings_dialog
from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
from calendar_app.shared import background_worker
from tests.support import TemporaryDatabaseTestCase
from tests.test_gcal_sync_integration import FakeDate, FakeGoogleEvent, FakeSettings

_ROOT = Path(__file__).resolve().parents[1]
_HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def code_defaults(monkeypatch):
    """Show the Korean code default for the given keys (locale files are filled later)."""

    def use(*keys):
        original = I18nManager.get

        def get(self, key, default=None, **kwargs):
            if key in keys:
                key = "__code_default__." + key
            return original(self, key, default, **kwargs)

        monkeypatch.setattr(I18nManager, "get", get)

    return use


def _switch_language(code):
    # conftest redirects this store to a temporary INI file.
    QSettings("kimhyojin", "Dark Calendar").setValue("language", code)
    I18nManager()._load_translations()


@pytest.fixture
def english_ui():
    previous = i18n.lang
    _switch_language("en")
    try:
        yield
    finally:
        _switch_language(previous)


def _record_t(monkeypatch, module):
    calls = []
    real = module.t

    def recording(key, default=None, **kwargs):
        calls.append((key, kwargs))
        return real(key, default, **kwargs)

    monkeypatch.setattr(module, "t", recording)
    return calls


# --- M10: Google reset confirmation and result --------------------------------


def test_reset_confirmation_names_calendars_and_subscriptions(code_defaults, monkeypatch):
    code_defaults("gcal_settings.reset_confirm")
    warning = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(gcal_settings_dialog.QMessageBox, "warning", warning)
    host = SimpleNamespace(_auth_worker=None, _query_worker=None, _parent_google_busy=lambda: False)

    gcal_settings_dialog.GCalSettingsDialog.reset_auth(host)

    text = warning.call_args.args[2]
    for word in ("인증 정보", "토큰", "Google 캘린더", "구독", "삭제 요청"):
        assert word in text, word


def test_reset_done_body_reports_the_removed_counts(code_defaults, monkeypatch, tmp_path):
    code_defaults("gcal_settings.reset_done_body")
    calls = _record_t(monkeypatch, gcal_settings_dialog)
    information = Mock()
    monkeypatch.setattr(gcal_settings_dialog.QMessageBox, "information", information)
    monkeypatch.setattr(gcal_settings_dialog, "TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setattr(gcal_settings_dialog, "CREDENTIALS_PATH", str(tmp_path / "creds.json"))
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        lambda **kwargs: [
            {"id": "gcal::a", "type": "gcal"},
            {"id": "gcal::b", "type": "gcal"},
            {"id": "local::x", "type": "local"},
        ],
    )
    monkeypatch.setattr(calendar_repo, "delete_calendar", lambda calendar_id: True)
    monkeypatch.setattr(
        task_repo,
        "list_gcal_subscriptions",
        lambda include_inactive=True: [{"calendar_id": c} for c in ("s1", "s2", "s3")],
    )
    monkeypatch.setattr(task_repo, "delete_gcal_subscription", lambda calendar_id: True)
    monkeypatch.setattr(task_repo, "clear_gcal_delete_queue", lambda: None)
    host = Mock()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.parent_app = None

    gcal_settings_dialog.GCalSettingsDialog._complete_reset_auth(host)

    assert ("gcal_settings.reset_done_body", {"cal_count": 2, "sub_count": 3}) in calls
    body = information.call_args.args[2]
    assert "캘린더: 2" in body and "구독: 3" in body


# --- L14 and L16: placeholders the code passes ---------------------------------


def test_sync_partial_reports_pull_failures(code_defaults, monkeypatch):
    code_defaults("gcal.worker.sync_partial")
    monkeypatch.setattr(engine, "sync_google_calendar", lambda app, silent=True: True)
    monkeypatch.setattr(background_worker, "_close_db_connection", lambda: None)
    app = SimpleNamespace(
        _last_gcal_sync_stats={"push_failures": 0, "delete_failures": 0, "pull_apply_failures": 4}
    )
    worker = background_worker.SyncWorker(app)
    results = []
    worker.result_ready.connect(lambda ok, text: results.append((ok, text)))

    worker.run()

    assert results == [(True, "동기화 완료 (일부 실패: push=0, delete=0, pull=4)")]


def _t_calls(path, keys):
    tree = ast.parse((_ROOT / path).read_text(encoding="utf-8", errors="strict"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) in {"t", "_translate"}
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in keys
        ):
            yield node.args[0].value, ast.literal_eval(node.args[1]), {k.arg for k in node.keywords}


@pytest.mark.parametrize(
    ("path", "key"),
    [
        (
            "calendar_app/presentation/dialogs/gcal_settings_dialog.py",
            "gcal_settings.reset_done_body",
        ),
        (
            "calendar_app/presentation/dialogs/gcal_settings_dialog.py",
            "gcal_settings.test_access_ok",
        ),
        ("calendar_app/shared/background_worker.py", "gcal.worker.sync_partial"),
        (
            "calendar_app/presentation/dialogs/gcal_sync_issues_dialog.py",
            "gcal.guidance.remote_orphan",
        ),
    ],
)
def test_korean_defaults_use_every_value_the_code_passes(path, key):
    found = list(_t_calls(path, {key}))
    assert found, key
    for _key, default, passed in found:
        fields = {name for _, name, _, _ in string.Formatter().parse(default) if name}
        assert fields == passed, (key, fields, passed)


# --- L16 (a): short table cells -----------------------------------------------


def test_sync_issue_cells_use_short_labels():
    from calendar_app.presentation.dialogs.gcal_sync_issues_dialog import GCalSyncIssuesDialog

    with patch(
        "calendar_app.presentation.dialogs.gcal_sync_issues_dialog.t",
        side_effect=lambda key, default=None, **kwargs: key,
    ):
        cells = {
            raw: GCalSyncIssuesDialog._map_error_to_friendly(None, raw)
            for raw in (
                "forbidden",
                "auth_required",
                "not_found",
                "remote_newer_than_local",
                "rate_limit",
                "remote_http_429",
                "[update] HttpError 500",
                "network",
            )
        }
    # The toast sentence gcal.errors.forbidden is not reused for the cell.
    assert cells["forbidden"] == ("gcal.errors.forbidden_label", "gcal.treatments.stopped")
    assert cells["auth_required"] == ("gcal.errors.auth_required", "gcal.treatments.stopped")
    for raw in ("rate_limit", "remote_http_429"):
        assert cells[raw] == ("gcal.errors.rate_limit", "gcal.treatments.pending_retry"), raw
    # Other errors get a short cell; the guidance panel keeps the full sentence.
    for raw in ("[update] HttpError 500", "network"):
        assert cells[raw] == ("gcal.errors.sync_error_label", "gcal.treatments.manual"), raw
    assert cells["not_found"] == ("gcal.errors.not_found", "gcal.treatments.auto_healing")
    assert cells["remote_newer_than_local"][1] == "gcal.treatments.mirrored"


# --- M4: the auth hint does not depend on translated text ----------------------


def _setup_needed_message(monkeypatch):
    information = Mock()
    monkeypatch.setattr(QMessageBox, "information", information)
    GCalActionsMixin.notify_gcal_setup_needed(Mock(), disabled=False)
    return information.call_args.args[2]


def test_setup_needed_adds_auth_hint_in_a_non_korean_ui(english_ui, monkeypatch):
    message = _setup_needed_message(monkeypatch)
    hint = t("gcal.setup_needed_auth_hint")
    assert message.endswith("\n" + hint)
    assert message.count(hint) == 1
    assert not _HANGUL.search(message)


def test_setup_needed_hint_is_chosen_by_state_not_by_message_text(code_defaults, monkeypatch):
    code_defaults("gcal.setup_needed_msg", "gcal.setup_needed_auth_hint")
    message = _setup_needed_message(monkeypatch)
    # The path comes from the live menu labels even when the sentence is the code default.
    assert message == (
        "Google Calendar 동기화가 아직 설정되지 않았습니다.\n"
        "설정 > 캘린더 및 동기화 > 캘린더 · 계정 및 동기화 > 연결 및 구독에서 구성하세요.\n"
        "Google Calendar 항목에서 Google 인증을 완료해 주세요."
    )


# --- L12: untitled Google events -----------------------------------------------


def test_google_event_without_title_gets_the_translated_untitled_name():
    sync = gcal_service.CalendarSyncService(calendar_id="team")
    event = sync._to_google_event(
        {"id": "e1", "start": {"date": "2026-10-09"}, "end": {"date": "2026-10-10"}}
    )
    assert event.summary == t("dialog.task.untitled", "제목 없음")
    assert event.summary != "Untitled"


def test_untitled_placeholders_are_written_to_google_as_no_title():
    for name in ("", "  ", "Untitled", "제목 없음", t("dialog.task.untitled", "제목 없음")):
        assert common.google_summary_for_task_name(name) == "", name
        assert common.google_summary_for_task_name(name, remote_summary="") == "", name
    assert common.google_summary_for_task_name("Team sync") == "Team sync"
    sync = gcal_service.CalendarSyncService(calendar_id="team", time_zone="Asia/Seoul")
    body = sync._build_event_body_from_op(
        {"summary": "", "start_iso": "2026-10-09 09:00:00", "end_iso": "2026-10-09 10:00:00"}
    )
    assert body["summary"] == ""


def test_a_real_google_title_equal_to_a_placeholder_word_is_kept():
    for word in ("Untitled", "Sans titre", "제목 없음"):
        assert common.google_summary_for_task_name(word, remote_summary=word) == word
    # A different remote title does not make a placeholder a real title.
    assert common.google_summary_for_task_name("Untitled", remote_summary="Team sync") == ""


def test_placeholders_of_every_bundled_language_stay_off_google():
    import json

    for path in sorted((_ROOT / "locales").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        value = data.get("dialog", {}).get("task", {}).get("untitled")
        if value:
            assert common.google_summary_for_task_name(value) == "", path.stem


class _RecordingSync:
    def __init__(self, events):
        self.is_authenticated = True
        self.events = list(events)
        self.calendar_id = "primary"
        self.time_zone = "Asia/Seoul"
        self.last_error_kind = None

    def authenticate(self, interactive=True):
        return True

    def fetch_sync_events(self, sync_token, calendar_id=None):
        return list(self.events), "next-token", False

    def delete_event(self, event_id, calendar_id=None):
        return True

    def update_event(self, *args, **kwargs):
        return True

    def create_event(self, *args, **kwargs):
        return "created-id"


class _Request:
    def __init__(self, result):
        self.result = result
        self.headers = {}

    def execute(self):
        return self.result


class _EventsApi:
    """Google events resource: get returns the remote event, update records the body."""

    def __init__(self, remote):
        self.remote = remote
        self.bodies = {}

    def get(self, calendarId, eventId):
        return _Request(deepcopy(self.remote[eventId]))

    def update(self, calendarId, eventId, body, **kwargs):
        self.bodies[eventId] = body
        return _Request({**body, "updated": "2026-03-14T02:00:00Z"})


class UntitledGoogleImportTests(TemporaryDatabaseTestCase):
    def _app(self, sync):
        return SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_bound_calendar_id": "primary",
                }
            ),
            current_date=FakeDate("2026-03-14"),
            gcal_sync=sync,
            update_sync_status=lambda: None,
            mark_panel_dirty=lambda **kwargs: None,
        )

    def _task(self, event_id):
        conn = database_unified.db_manager.get_connection()
        row = conn.execute(
            "SELECT id FROM unified_task WHERE gcal_event_id=?", (event_id,)
        ).fetchone()
        return task_repo.get_unified_task(row["id"])

    def test_untitled_event_is_stored_translated_and_pushed_back_without_title(self):
        titles = {"evt-empty": None, "evt-untitled": "Untitled", "evt-sans": "Sans titre"}
        events = [
            FakeGoogleEvent(
                event_id, title, "2026-03-14T09:00:00+09:00", "2026-03-14T10:00:00+09:00"
            )
            for event_id, title in titles.items()
        ]
        app = self._app(_RecordingSync(events))

        self.assertTrue(engine.sync_google_calendar(app, silent=True))
        names = {event_id: self._task(event_id)["name"] for event_id in titles}
        self.assertEqual(names["evt-empty"], t("dialog.task.untitled", "제목 없음"))
        self.assertNotEqual(names["evt-empty"], "Untitled")
        # A real Google title is stored as it is, even when it reads "untitled".
        self.assertEqual(names["evt-untitled"], "Untitled")
        self.assertEqual(names["evt-sans"], "Sans titre")

        # A local edit pushes each event back through the real update request.
        api = _EventsApi(
            {
                event_id: {
                    "id": event_id,
                    "updated": "2026-03-14T00:00:00Z",
                    **({"summary": title} if title else {}),
                    "start": {"dateTime": "2026-03-14T09:00:00+09:00"},
                    "end": {"dateTime": "2026-03-14T10:00:00+09:00"},
                }
                for event_id, title in titles.items()
            }
        )
        sync = gcal_service.CalendarSyncService(calendar_id="primary", time_zone="Asia/Seoul")
        sync.is_authenticated = True
        sync.service = SimpleNamespace(events=lambda: api)
        app.gcal_sync = sync
        for event_id in titles:
            result = helpers.sync_task_to_google(app, self._task(event_id), create_if_missing=False)
            self.assertTrue(result.success, (event_id, result))

        # Google keeps the untitled event untitled and never loses a real title.
        self.assertEqual(api.bodies["evt-empty"]["summary"], "")
        self.assertEqual(api.bodies["evt-untitled"]["summary"], "Untitled")
        self.assertEqual(api.bodies["evt-sans"]["summary"], "Sans titre")
