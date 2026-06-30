import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets import unified_widget_mode as uwm


class _FakeSettings:
    def __init__(self):
        self._values = {}

    def value(self, key, default=None, type=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value


class _FakeHost(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = _FakeSettings()
        self.current_date = QDate(2026, 3, 27)
        self._latest_agenda_data = None
        self._latest_calendar_range_data = None
        self._latest_directive_data = None
        self.panel_refresh_requests = []
        self.open_task_dialog_calls = []

    def schedule_panel_refresh(self, left=False, center=False, right=False, delay_ms=0):
        self.panel_refresh_requests.append(
            {
                "left": bool(left),
                "center": bool(center),
                "right": bool(right),
                "delay_ms": int(delay_ms),
            }
        )

    def open_task_dialog(self, **kwargs):
        self.open_task_dialog_calls.append(dict(kwargs))


class UnifiedWidgetModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = _FakeHost()

    def tearDown(self):
        controller = getattr(self, "controller", None)
        widget = getattr(controller, "widget", None)
        if widget is not None:
            widget.hide()
            widget.close()
            widget.deleteLater()
        self.host.close()
        self.host.deleteLater()

    def test_hidden_widget_does_not_request_refresh(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        self.controller.widget = uwm.UnifiedWidgetWindow(self.controller)
        self.controller.widget.hide()

        self.controller.refresh_data()

        self.assertEqual([], self.host.panel_refresh_requests)

    def test_visible_widget_requests_missing_cache_only_once(self):
        self.controller = uwm.UnifiedWidgetController(self.host)

        self.controller.toggle_widget()
        self.controller.refresh_data()

        self.assertEqual(1, len(self.host.panel_refresh_requests))
        self.assertEqual(
            {"left": False, "center": True, "right": True, "delay_ms": 0},
            self.host.panel_refresh_requests[0],
        )

    def test_refresh_data_shows_only_selected_date_items(self):
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [
                {"id": 1, "name": "Selected Schedule", "deadline": "2026-03-27 09:00:00"},
                {"id": 2, "name": "Other Schedule", "deadline": "2026-03-28 10:00:00"},
                {
                    "id": 3,
                    "name": "Carryover Schedule",
                    "deadline": "2026-03-26 18:00:00",
                    "end_date": "2026-03-27 12:00:00",
                },
            ],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-27",
            "routine_rows": [
                {
                    "id": 11,
                    "name": "Selected Routine",
                    "target_date": "2026-03-27",
                    "status": "pending",
                },
                {
                    "id": 12,
                    "name": "Other Routine",
                    "target_date": "2026-03-28",
                    "status": "pending",
                },
                {
                    "id": 13,
                    "name": "Done Routine",
                    "target_date": "2026-03-27",
                    "status": "completed",
                },
            ],
            "directive_rows": [
                (21, "Selected Directive", "pending", "", "2026-03-27", "", None, False),
                (22, "Other Directive", "pending", "", "2026-03-28", "", None, False),
                (23, "Done Directive", "completed", "", "2026-03-27", "", None, False),
            ],
        }
        self.controller = uwm.UnifiedWidgetController(self.host)

        self.controller.toggle_widget()
        self.controller.refresh_data()

        titles = [
            item["title"]
            for item in self.controller.widget._last_items
            if not item.get("is_section")
        ]
        self.assertIn("Selected Schedule", titles)
        self.assertIn("Carryover Schedule", titles)
        self.assertIn("Selected Routine", titles)
        self.assertIn("Selected Directive", titles)
        self.assertNotIn("Other Schedule", titles)
        self.assertNotIn("Other Routine", titles)
        self.assertNotIn("Other Directive", titles)
        self.assertNotIn("Done Routine", titles)
        self.assertNotIn("Done Directive", titles)

    def test_set_target_date_uses_existing_cache_without_forcing_refresh(self):
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-27",
            "routine_rows": [],
            "directive_rows": [],
        }
        self.controller = uwm.UnifiedWidgetController(self.host)

        self.controller.toggle_widget()
        self.assertEqual([], self.host.panel_refresh_requests)

        self.host._latest_directive_data = {
            "context_date": "2026-03-28",
            "routine_rows": [],
            "directive_rows": [],
        }
        self.host.panel_refresh_requests.clear()

        self.controller.set_target_date(QDate(2026, 3, 28))

        self.assertEqual(QDate(2026, 3, 28), self.host.current_date)
        self.assertEqual([], self.host.panel_refresh_requests)

    def test_refresh_data_skips_rebuilding_when_cache_signature_is_unchanged(self):
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [{"id": 1, "name": "A", "deadline": "2026-03-27 09:00:00"}],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-27",
            "routine_rows": [],
            "directive_rows": [],
        }
        self.controller = uwm.UnifiedWidgetController(self.host)
        self.controller.widget = uwm.UnifiedWidgetWindow(self.controller)

        with (
            patch.object(self.controller.widget, "isVisible", return_value=True),
            patch.object(
                self.controller,
                "_schedule_items_for_date",
                wraps=self.controller._schedule_items_for_date,
            ) as schedule_items_mock,
            patch.object(
                self.controller,
                "_work_items_for_date",
                wraps=self.controller._work_items_for_date,
            ) as work_items_mock,
        ):
            self.controller.refresh_data()
            self.controller.refresh_data()

        self.assertEqual(1, schedule_items_mock.call_count)
        self.assertEqual(1, work_items_mock.call_count)

    def test_widget_clock_timer_uses_single_shot_minute_ticks(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)

        self.assertTrue(widget.timer.isSingleShot())
        self.assertGreaterEqual(widget._ms_until_next_clock_tick(), 1000)
        self.assertLessEqual(widget._ms_until_next_clock_tick(), 60000)

    def test_today_button_syncs_selected_date(self):
        self.host.current_date = QDate(2026, 3, 20)
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)

        widget.today_btn.click()

        self.assertEqual(QDate.currentDate(), self.host.current_date)

    def test_update_agenda_updates_summary_chips(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)
        widget.update_header(QDate(2026, 3, 27))
        widget.update_agenda(
            [
                {"title": "Schedule", "time": "09:00", "is_task": False},
                {"title": "Work", "time": "", "is_task": True},
            ]
        )

        self.assertIn("2", widget.count_chip.text())
        self.assertTrue(widget.status_chip.text())

    def test_filter_buttons_reduce_visible_items_without_touching_source_cache(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)
        widget.update_agenda(
            [
                {"title": "Schedule", "is_section": True, "section_kind": "schedule"},
                {
                    "title": "Team Meeting",
                    "time": "09:00",
                    "is_task": False,
                    "item_kind": "schedule",
                },
                {"title": "Work", "is_section": True, "section_kind": "work"},
                {"title": "Review Deck", "time": "", "is_task": True, "item_kind": "work"},
            ]
        )

        widget._set_filter("schedule")

        titles = [item["title"] for item in widget._last_items if not item.get("is_section")]
        filtered_titles = [
            item["title"]
            for item in widget._filter_items(widget._last_items)
            if not item.get("is_section")
        ]
        self.assertIn("Team Meeting", titles)
        self.assertIn("Review Deck", titles)
        self.assertEqual(["Team Meeting"], filtered_titles)

    def test_work_filter_updates_header_copy(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)
        widget.update_agenda(
            [
                {"title": "Schedule", "is_section": True, "section_kind": "schedule"},
                {
                    "title": "Team Meeting",
                    "time": "09:00",
                    "is_task": False,
                    "item_kind": "schedule",
                },
                {"title": "Work", "is_section": True, "section_kind": "work"},
                {"title": "Review Deck", "time": "", "is_task": True, "item_kind": "work"},
            ]
        )

        widget._set_filter("work")

        self.assertEqual(uwm.t("widget_mode.filter_work", "Work"), widget.agenda_header.text())
        self.assertIn("1/2", widget.count_chip.text())

    def test_unified_widget_has_no_inline_quick_add_shell(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)

        self.assertFalse(hasattr(widget, "quick_add"))
        self.assertFalse(hasattr(widget, "quick_shell"))

    def test_add_button_uses_main_task_dialog(self):
        self.controller = uwm.UnifiedWidgetController(self.host)
        widget = uwm.UnifiedWidgetWindow(self.controller)

        widget.add_btn.click()

        self.assertEqual(1, len(self.host.open_task_dialog_calls))
        self.assertEqual(
            self.host.current_date, self.host.open_task_dialog_calls[0]["initial_date"]
        )
        self.assertEqual("schedule", self.host.open_task_dialog_calls[0]["task_type"])


if __name__ == "__main__":
    unittest.main()
