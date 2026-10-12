# -*- coding: utf-8 -*-
"""Interactive Google sign-in without blocking the settings dialog."""

import threading

from PyQt6.QtCore import QThread

from calendar_app.infrastructure.google_sync.oauth import GoogleAuthError


class GCalAuthWorker(QThread):
    provider = "google"

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.success = False
        self.calendars = []
        self._cancelled = threading.Event()

    def requestInterruption(self):
        # QThread can lose an interruption requested before start(), or after run().
        self._cancelled.set()
        super().requestInterruption()

    def is_cancelled(self):
        return self._cancelled.is_set() or self.isInterruptionRequested()

    def run(self):
        try:
            self.success = False
            if self.is_cancelled():
                return
            self.success = self.service.authenticate(
                interactive=True,
                force_reauth=True,
                is_cancelled=self.is_cancelled,
                persist_token=False,
            )
            if not self.success or self.is_cancelled():
                self.success = False
                return
            self.calendars = (
                self.service.list_accessible_calendars(is_cancelled=self.is_cancelled) or []
            )
            self.success = (
                self.service.is_authenticated
                and not getattr(self.service, "last_error_kind", None)
                and not self.is_cancelled()
            )
        except GoogleAuthError as exc:
            self.success = False
            self.service._set_last_error(exc.kind, "Google authentication cancelled")
        except Exception:
            # Do not pass OAuth responses or credentials through error messages.
            self.success = False
            self.service._set_last_error("auth", "Google authentication failed")
        finally:
            if not self.success and hasattr(self.service, "_pending_token_json"):
                self.service._pending_token_json = None


class GCalQueryWorker(GCalAuthWorker):
    """Calendar metadata query with the same cancellation and lifecycle contract."""

    def run(self):
        try:
            self.success = False
            if self.is_cancelled():
                return
            factory = getattr(self.service, "create_metadata_reader", None)
            if callable(factory):
                self.service = factory(is_cancelled=self.is_cancelled)
            self.calendars = (
                self.service.list_accessible_calendars(is_cancelled=self.is_cancelled) or []
            )
            self.success = not self.is_cancelled() and not getattr(
                self.service, "last_error_kind", ""
            )
        except GoogleAuthError as exc:
            self.success = False
            self.service._set_last_error(exc.kind, "Google calendar query cancelled")
        except Exception:
            self.success = False
            self.service._set_last_error("calendar_list", "Google calendar query failed")


class GCalRevokeWorker(GCalAuthWorker):
    """Keep the bounded revocation request off the UI thread."""

    def run(self):
        try:
            self.success = bool(self.service.revoke_token())
        except Exception:
            self.success = False
