import types
import unittest
from unittest.mock import patch

from calendar_app.shared import background_worker as bgw


class BackgroundWorkerHelperTests(unittest.TestCase):
    def test_translate_fallback_formats_kwargs_when_i18n_unavailable(self):
        with patch(
            "calendar_app.shared.background_worker.import_module", side_effect=ModuleNotFoundError
        ):
            text = bgw._translate("sample.key", "Hello {name}", name="World")
        self.assertEqual(text, "Hello World")

    def test_resolve_sync_runtime_uses_engine_symbols(self):
        fake_engine = types.SimpleNamespace(
            sync_google_calendar=lambda app, silent=False: True,
            SYNC_OUTCOME_FAILED="FAILED_X",
            SYNC_OUTCOME_SKIPPED="SKIPPED_X",
        )
        with patch("calendar_app.shared.background_worker.import_module", return_value=fake_engine):
            sync_func, failed, skipped = bgw._resolve_sync_runtime()
        self.assertTrue(callable(sync_func))
        self.assertEqual(failed, "FAILED_X")
        self.assertEqual(skipped, "SKIPPED_X")

    def test_close_db_connection_is_safe_and_calls_manager(self):
        called = []
        fake_db_module = types.SimpleNamespace(
            db_manager=types.SimpleNamespace(close_connection=lambda: called.append(True))
        )
        with patch(
            "calendar_app.shared.background_worker.import_module", return_value=fake_db_module
        ):
            bgw._close_db_connection()
        self.assertEqual(called, [True])


if __name__ == "__main__":
    unittest.main()
