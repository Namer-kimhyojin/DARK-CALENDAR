# -*- coding: utf-8 -*-
"""Independent ETag download/cache and stable identity recovery regressions."""

from copy import deepcopy
import sqlite3

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.resource_cache import CalDAVResourceCache
from tests.test_caldav_sync import BASE, HREF, ICS, Response, Session, multi, xml_row
from tests.test_calendar_sync_engine import repo, setup, task

START, END = "2026-10-01T00:00:00+00:00", "2026-10-09T00:00:00+00:00"
COLLECTION = BASE + "calendar/"


def metadata(etag="1", href=HREF):
    return Response(multi(xml_row(href, "<d:getetag>" + etag + "</d:getetag>")))


def content(etag="1", data=ICS, href=HREF):
    return Response(
        multi(
            xml_row(
                href,
                "<d:getetag>"
                + etag
                + "</d:getetag><c:calendar-data>"
                + data
                + "</c:calendar-data>",
            )
        )
    )


def test_restart_reuses_unchanged_etag_without_content_download(tmp_path):
    path = tmp_path / "cache.db"
    conn = sqlite3.connect(path)
    store = CalDAVResourceCache(conn, "account-one")
    session = Session(metadata(), content())
    first = CalDAVClient("icloud", "fixture", "synthetic", session, resource_cache=store).events(
        COLLECTION, START, END
    )
    assert len(session.calls) == 2
    assert b"calendar-data" not in session.calls[0][2]["data"]
    assert b"calendar-multiget" in session.calls[1][2]["data"]
    conn.close()
    conn = sqlite3.connect(path)
    session = Session(metadata())
    second = CalDAVClient(
        "icloud",
        "fixture",
        "synthetic",
        session,
        resource_cache=CalDAVResourceCache(conn, "account-one"),
    ).events(COLLECTION, START, END)
    assert second == first
    assert len(session.calls) == 1
    assert CalDAVResourceCache(conn, "account-two").load(COLLECTION) == {}
    conn.close()


@pytest.mark.parametrize(
    "response",
    [content("newer"), Response(multi("")), Response(multi(xml_row(HREF, "", "403 Forbidden")))],
)
def test_partial_or_changed_multiget_preserves_cache(response):
    conn = sqlite3.connect(":memory:")
    store = CalDAVResourceCache(conn, "one")
    store.save(COLLECTION, {HREF: ("old", ICS)})
    client = CalDAVClient(
        "icloud", "fixture", "synthetic", Session(metadata("new"), response), resource_cache=store
    )
    with pytest.raises(CalendarSyncError):
        client.events(COLLECTION, START, END)
    assert store.load(COLLECTION) == {HREF: ("old", ICS)}
    conn.close()


def test_corrupted_cached_body_is_downloaded_again():
    conn = sqlite3.connect(":memory:")
    store = CalDAVResourceCache(conn, "one")
    store.save(COLLECTION, {HREF: ("1", "broken")})
    session = Session(metadata(), content())
    client = CalDAVClient("icloud", "fixture", "synthetic", session, resource_cache=store)
    assert len(client.events(COLLECTION, START, END)) == 1
    assert len(session.calls) == 2
    assert store.load(COLLECTION)[HREF] == ("1", ICS.replace("\r\n", "\n"))
    conn.close()


def test_empty_etag_report_invalidates_old_memory_resource():
    session = Session(Response(multi("")), Response(status=404))
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    client.cache[HREF] = ("1", ICS)
    assert client.events(COLLECTION, START, END) == []
    with pytest.raises(RemoteCalendarError):
        client.event(HREF)
    with pytest.raises(RemoteCalendarError):
        client.event(HREF)
    assert len(session.calls) == 2


def test_multiget_unsupported_falls_back_to_complete_query():
    session = Session(metadata(), Response(status=405), content())
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    assert len(client.events(COLLECTION, START, END)) == 1
    assert b"calendar-data" in session.calls[-1][2]["data"]
    assert len(session.calls) == 3


def test_cache_database_failure_preserves_previous_snapshot():
    conn = sqlite3.connect(":memory:")
    store = CalDAVResourceCache(conn, "account")
    store.save(COLLECTION, {HREF: ("1", ICS)})
    conn.execute(
        "CREATE TRIGGER reject_cache BEFORE INSERT ON caldav_resource_cache WHEN NEW.data='bad' BEGIN SELECT RAISE(ABORT,'synthetic storage error'); END"
    )
    with pytest.raises(sqlite3.Error):
        store.save(COLLECTION, {HREF: ("2", "bad")})
    assert store.load(COLLECTION) == {HREF: ("1", ICS)}
    assert not conn.in_transaction
    conn.close()


def test_cache_collection_isolation():
    conn = sqlite3.connect(":memory:")
    store = CalDAVResourceCache(conn, "account")
    store.save(COLLECTION, {HREF: ("1", ICS)})
    assert store.load(BASE + "other/") == {}
    store.save(BASE + "other/", {})
    assert store.load(COLLECTION) == {HREF: ("1", ICS)}
    conn.close()


def test_real_windows_encryption_survives_credential_store_restart(tmp_path):
    import sys

    from calendar_app.infrastructure.caldav_sync.credentials import CalDAVCredentials

    if sys.platform != "win32":
        pytest.skip("Windows CurrentUser DPAPI check")
    store = CalDAVCredentials(tmp_path)
    account = store.save("icloud", "synthetic@example.invalid", "synthetic-app-password")
    assert b"synthetic-app-password" not in store.path(account).read_bytes()
    restored = CalDAVCredentials(tmp_path).load(account)
    assert restored == {
        "service": "icloud",
        "username": "synthetic@example.invalid",
        "password": "synthetic-app-password",
    }


def caldav_import(repo):
    repo.provider = "caldav"
    with repo.conn:
        repo.conn.execute("UPDATE calendar SET is_active=0")
    key = repo.register("account", {"id": "calendar", "name": "CalDAV", "can_edit": True})
    provider, _, engine = setup(repo)
    provider.remote["old"] = {
        "id": "old",
        "etag": "1",
        "uid": "stable",
        "recurrence_id": "",
        "task": task(),
    }
    engine.run()
    return provider, key, engine, repo.tasks(key)[0]["id"]


def relocate(provider, etag="2", data=None):
    previous = provider.remote.pop("old")
    provider.remote["new"] = {
        **previous,
        "id": "new",
        "etag": etag,
        "task": data or previous["task"],
    }


def test_url_change_preserves_local_id_without_duplicate(repo):
    provider, key, engine, tid = caldav_import(repo)
    relocate(provider)
    result = engine.run()
    assert result["imported"] == 0
    assert [r["id"] for r in repo.tasks(key)] == [tid]
    assert repo.task_link(tid)["event_id"] == "new"
    assert not repo.issues("account")
    assert provider.writes == []


def test_url_change_preserves_both_sides_of_conflict(repo):
    provider, key, engine, tid = caldav_import(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    relocate(provider, data=task("Remote"))
    engine.run()
    assert repo.task(tid)["name"] == "Local"
    assert repo.issues("account")[0]["kind"] == "conflict"
    assert repo.task_link(tid)["event_id"] == "new"
    assert provider.writes == []


def test_duplicate_uid_response_is_rejected_before_import(repo):
    provider, key, engine, tid = caldav_import(repo)
    provider.remote["duplicate"] = {**provider.remote["old"], "id": "duplicate"}
    with pytest.raises(CalendarSyncError, match="duplicate_remote_event"):
        engine.run()
    assert len(repo.tasks(key)) == 1


def test_still_existing_old_url_cannot_be_reassigned(repo):
    provider, key, engine, tid = caldav_import(repo)
    event = {**provider.remote["old"], "id": "new"}
    provider.events = lambda *args: [deepcopy(event)]
    with pytest.raises(CalendarSyncError, match="duplicate_remote_event"):
        engine.run()
    assert repo.task_link(tid)["event_id"] == "old"
    assert len(repo.tasks(key)) == 1


def test_known_remote_deletion_is_recovered_if_uid_reappears_at_new_url(repo):
    provider, key, engine, tid = caldav_import(repo)
    previous = provider.remote.pop("old")
    engine.run()
    assert repo.task_link(tid)["remote_deleted"] == 1
    provider.remote["new"] = {**previous, "id": "new"}
    engine.run()
    assert repo.task_link(tid)["remote_deleted"] == 0
    assert repo.task_link(tid)["event_id"] == "new"
    assert not repo.issues("account")
    assert len(repo.tasks(key)) == 1


@pytest.mark.parametrize("etag,deleted", [("1", True), ("2", False)])
def test_deleted_local_row_does_not_resurrect_after_url_change(repo, etag, deleted):
    provider, key, engine, tid = caldav_import(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    relocate(provider, etag)
    engine.run()
    assert repo.tasks(key) == []
    if deleted:
        assert provider.writes == ["delete"]
    else:
        row = repo.conn.execute("SELECT event_id,error FROM calendar_sync_delete_queue").fetchone()
        assert tuple(row) == ("new", "delete_conflict")
        assert provider.writes == []


@pytest.mark.parametrize("local_changed", [False, True])
def test_different_uid_at_same_url_preserves_local_and_remote(repo, local_changed):
    provider, key, engine, tid = caldav_import(repo)
    if local_changed:
        with repo.conn:
            repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    previous = repo.task(tid)
    provider.remote["old"].update(uid="another-event", task=task("Unrelated"))
    engine.run()
    assert repo.task(tid) == previous
    assert repo.task_link(tid)["remote_uid"] == "stable"
    assert repo.issues("account")[0]["kind"] == "remote_identity_changed"
    assert provider.writes == []


def test_deleted_local_row_cannot_delete_new_uid_with_same_etag(repo):
    provider, key, engine, tid = caldav_import(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    provider.remote["old"]["uid"] = "another-event"
    engine.run()
    row = repo.conn.execute("SELECT error,remote_uid FROM calendar_sync_delete_queue").fetchone()
    assert tuple(row) == ("delete_conflict", "stable")
    assert provider.writes == []


def test_deleted_during_create_receipt_keeps_uid_for_later_url_recovery(repo):
    provider, key, engine, tid = caldav_import(repo)
    with repo.conn:
        new_tid = repo.import_task(key, task("New"))
    original_create = provider.create

    def create_with_delete(calendar, payload, transaction):
        with repo.conn:
            repo.conn.execute("DELETE FROM unified_task WHERE id=?", (new_tid,))
        event = original_create(calendar, payload, transaction)
        event.update(uid="created-uid", recurrence_id="")
        provider.remote[event["id"]] = deepcopy(event)
        return event

    provider.create = create_with_delete
    # Interrupt after the write receipt, before the queue is sent to the server.
    original_deletions = engine._deletions
    engine._deletions = lambda key: 0
    engine.run()
    row = repo.conn.execute("SELECT * FROM calendar_sync_delete_queue").fetchone()
    assert row["remote_uid"] == "created-uid"
    old = provider.remote.pop(row["event_id"])
    provider.remote["relocated-create"] = {**old, "id": "relocated-create"}
    engine._deletions = original_deletions
    engine.run()
    assert [t["id"] for t in repo.tasks(key)] == [tid]
    assert provider.writes == ["create", "delete"]
    assert "relocated-create" not in provider.remote


def test_local_delete_during_old_url_probe_follows_resource_without_resurrection(repo):
    provider, key, engine, tid = caldav_import(repo)
    relocate(provider, etag="1")
    original_event = provider.event

    def delete_during_probe(event_id):
        if event_id == "old":
            with repo.conn:
                repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
        return original_event(event_id)

    provider.event = delete_during_probe
    engine.run()
    assert repo.tasks(key) == []
    assert provider.writes == ["delete"]
    engine.run()
    assert repo.tasks(key) == []
