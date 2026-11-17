# -*- coding: utf-8 -*-
"""Theme work is shared within one render, and a cancelled edit dialog redraws nothing."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from calendar_app.infrastructure.db import database_unified
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.shared import theme_snapshot
from tests.support import TemporaryDatabaseTestCase


class _DraftSettings(QSettings):
    def value(self, key, default=None, type=None):  # noqa: A002
        return super().value(key, default)


class ThemeCacheScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.ini = str(Path(self._dir.name) / "settings.ini")
        self.settings = QSettings(self.ini, QSettings.Format.IniFormat)
        self.settings.setValue("theme_color", "#3366cc")

    def _count_builds(self):
        original = theme_snapshot._build_theme_snapshot_uncached
        calls = []

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        patcher = patch.object(theme_snapshot, "_build_theme_snapshot_uncached", counting)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_repeated_requests_in_one_scope_build_once(self):
        calls = self._count_builds()
        with theme_snapshot.theme_cache_scope():
            first = theme_snapshot.build_theme_snapshot(self.settings)
            second = theme_snapshot.build_theme_snapshot(self.settings)
            # A separate store object for the same file shares the result.
            third = theme_snapshot.build_theme_snapshot(
                QSettings(self.ini, QSettings.Format.IniFormat)
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(first, second)
        self.assertEqual(first.theme_color, third.theme_color)

    def test_without_scope_every_request_reads_settings(self):
        calls = self._count_builds()
        theme_snapshot.build_theme_snapshot(self.settings)
        theme_snapshot.build_theme_snapshot(self.settings)
        self.assertEqual(len(calls), 2)

    def test_settings_change_is_seen_after_the_scope_ends(self):
        with theme_snapshot.theme_cache_scope():
            theme_snapshot.build_theme_snapshot(self.settings)
        self.settings.setValue("theme_color", "#cc3366")
        with theme_snapshot.theme_cache_scope():
            snapshot = theme_snapshot.build_theme_snapshot(self.settings)
        self.assertEqual(snapshot.theme_color, "#cc3366")

    def test_draft_settings_and_persisting_calls_are_never_cached(self):
        calls = self._count_builds()
        draft = _DraftSettings(self.ini, QSettings.Format.IniFormat)
        with theme_snapshot.theme_cache_scope():
            theme_snapshot.build_theme_snapshot(draft)
            theme_snapshot.build_theme_snapshot(draft)
            theme_snapshot.build_theme_snapshot(self.settings, persist_opacity=True)
            theme_snapshot.build_theme_snapshot(self.settings, persist_opacity=True)
        self.assertEqual(len(calls), 4)

    def test_callers_cannot_edit_the_cached_values(self):
        with theme_snapshot.theme_cache_scope():
            first = theme_snapshot.build_theme_snapshot(self.settings)
            first.text_palette["text_primary"] = "#123456"
            tokens = theme_snapshot.build_dialog_base_tokens(self.settings)
            tokens["accent"] = "#654321"
            metrics = theme_snapshot.build_dialog_metric_tokens(self.settings)
            metrics["field_height"] = -1
            second = theme_snapshot.build_theme_snapshot(self.settings)
            self.assertNotEqual(second.text_palette["text_primary"], "#123456")
            self.assertNotEqual(
                theme_snapshot.build_dialog_base_tokens(self.settings)["accent"], "#654321"
            )
            self.assertNotEqual(
                theme_snapshot.build_dialog_metric_tokens(self.settings)["field_height"], -1
            )


class ChangeMarkerTests(TemporaryDatabaseTestCase):
    def test_marker_moves_on_own_and_other_connection_writes(self):
        manager = database_unified.db_manager
        start = manager.change_marker()
        self.assertIsNotNone(start)
        self.assertEqual(manager.change_marker(), start)

        conn = manager.get_connection(raise_on_error=True)
        conn.execute("INSERT INTO calendar (id, type, name) VALUES ('local::m1', 'local', 'x')")
        conn.commit()
        after_own = manager.change_marker()
        self.assertNotEqual(after_own, start)

        import sqlite3

        other = sqlite3.connect(database_unified.DB_PATH)
        try:
            other.execute("UPDATE calendar SET name='y' WHERE id='local::m1'")
            other.commit()
        finally:
            other.close()
        self.assertNotEqual(manager.change_marker(), after_own)


class _Settings:
    def value(self, key, default=None):
        return default


class _CancelDialog:
    writes = False

    def __init__(self, task_id, parent):
        self.task_id = task_id

    def exec(self):
        if _CancelDialog.writes:
            _ChangingMarker.value += 1
        return QDialog.DialogCode.Rejected


class _ChangingMarker:
    value = 0


class _Host(QWidget, DialogActionsMixin):
    def __init__(self):
        super().__init__()
        self.settings = _Settings()
        self.refresh_calls = 0

    def _refresh_all_panels(self):
        self.refresh_calls += 1


class CancelledEditDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _open(self, writes):
        _CancelDialog.writes = writes
        host = _Host()
        self.addCleanup(host.close)
        with (
            patch(
                "calendar_app.presentation.dialogs.modify_task_dialog_unified.UnifiedModifyTaskDialog",
                _CancelDialog,
            ),
            patch(
                "calendar_app.infrastructure.db.task_repo.get_unified_task",
                return_value={"id": 7, "type": "schedule"},
            ),
            patch(
                "calendar_app.presentation.dialogs.dialog_router._database_change_marker",
                side_effect=lambda: (_ChangingMarker.value, 0),
            ),
        ):
            host.open_modify_task_dialog(7)
        return host

    def test_cancel_without_changes_skips_the_redraw(self):
        self.assertEqual(self._open(writes=False).refresh_calls, 0)

    def test_cancel_after_a_write_still_redraws(self):
        # Deleting from the dialog or editing its checklist writes before closing.
        self.assertEqual(self._open(writes=True).refresh_calls, 1)


if __name__ == "__main__":
    unittest.main()
