# -*- coding: utf-8 -*-
"""Durable ETag resources, isolated by account and calendar collection."""

from contextlib import contextmanager


class CalDAVResourceCache:
    def __init__(self, conn, account):
        self.conn, self.account = conn, account
        conn.execute("""
            CREATE TABLE IF NOT EXISTS caldav_resource_cache (
                account_id TEXT NOT NULL, calendar_url TEXT NOT NULL, href TEXT NOT NULL,
                etag TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY(account_id,calendar_url,href)
            )
        """)

    def load(self, calendar):
        return {
            row[0]: (row[1], row[2])
            for row in self.conn.execute(
                "SELECT href,etag,data FROM caldav_resource_cache WHERE account_id=? AND calendar_url=?",
                (self.account, calendar),
            )
        }

    @contextmanager
    def atomic(self):
        self.conn.execute("SAVEPOINT caldav_cache_snapshot")
        try:
            yield
            self.conn.execute("RELEASE SAVEPOINT caldav_cache_snapshot")
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT caldav_cache_snapshot")
            self.conn.execute("RELEASE SAVEPOINT caldav_cache_snapshot")
            raise

    def save(self, calendar, resources):
        with self.atomic():
            self.conn.execute(
                "DELETE FROM caldav_resource_cache WHERE account_id=? AND calendar_url=?",
                (self.account, calendar),
            )
            self.conn.executemany(
                "INSERT INTO caldav_resource_cache VALUES(?,?,?,?,?)",
                [
                    (self.account, calendar, href, etag, data)
                    for href, (etag, data) in resources.items()
                ],
            )
