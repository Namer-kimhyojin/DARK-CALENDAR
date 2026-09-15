# -*- coding: utf-8 -*-
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager


class OverlayManagerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = QWidget()
        self.owner.resize(1000, 700)
        self.owner.show()
        self.settings = QSettings("codex_test", "dark_calendar_overlay_manager_lifecycle")
        self.settings.clear()
        self.owner.settings = self.settings
        self.manager = OverlayWidgetManager(self.owner)
        self.__class__._app.processEvents()

    def tearDown(self):
        self.manager.remove_all()
        self.__class__._app.processEvents()
        self.settings.clear()
        self.owner.close()
        super().tearDown()

    def test_same_type_instances_have_distinct_default_positions(self):
        first = self.manager.add_instance("clock")
        second = self.manager.add_instance("clock")

        self.assertNotEqual(
            self.manager.get_widget(first).pos(),
            self.manager.get_widget(second).pos(),
        )

    def test_shutdown_save_round_trips_widget_settings_and_position(self):
        inst_id = self.manager.add_instance("clock")
        widget = self.manager.get_widget(inst_id)
        widget._set("font_size", 47)
        widget.move(123, 234)

        self.manager.save_all()

        self.assertEqual(123, int(widget._get("pos_x")))
        self.assertEqual(234, int(widget._get("pos_y")))
        self.assertEqual(QSettings.Status.NoError, self.settings.status())

        restored_manager = OverlayWidgetManager(self.owner)
        restored_manager.restore_all()
        self.addCleanup(restored_manager.remove_all)
        restored_widget = restored_manager.get_widget(inst_id)

        self.assertEqual(47, restored_widget.font_size())
        self.assertEqual(widget.pos(), restored_widget.pos())

    def test_shutdown_preserves_enabled_state_but_stops_widget_runtime(self):
        inst_id = self.manager.add_instance("clock")
        widget = self.manager.get_widget(inst_id)
        self.manager.show_instance(inst_id)
        widget.move(211, 322)
        self.assertTrue(widget._timer.isActive())

        self.manager.shutdown()

        self.assertFalse(widget._timer.isActive())
        self.assertFalse(widget.isVisible())
        self.assertTrue(widget.is_enabled())
        self.assertEqual((int(widget._get("pos_x")), int(widget._get("pos_y"))), (211, 322))

    def test_deleted_instance_does_not_leak_settings_when_id_is_reused(self):
        first = self.manager.add_instance("clock")
        self.manager.get_widget(first)._set("font_size", 47)
        self.manager.remove_instance(first)
        self.settings.sync()

        restored_manager = OverlayWidgetManager(self.owner)
        restored_manager.restore_all()
        reused = restored_manager.add_instance("clock")
        self.addCleanup(restored_manager.remove_all)

        self.assertEqual(reused, "clock_0")
        self.assertNotEqual(restored_manager.get_widget(reused).font_size(), 47)

    def test_every_widget_supports_reset_position(self):
        with patch(
            "calendar_app.presentation.widgets.overlay_weather.OverlayWeatherWidget.request_update"
        ):
            for widget_type in (
                "clock",
                "stopwatch",
                "date_card",
                "countdown",
                "dday",
                "text",
                "weather",
            ):
                inst_id = self.manager.add_instance(widget_type)
                widget = self.manager.get_widget(inst_id)
                widget._action_reset_position()
                self.assertEqual(widget.pos(), widget._clamp_restored_position(widget.pos()))

    def test_hidden_timed_widgets_pause_and_resume_runtime_work(self):
        timer_attrs = {
            "clock": "_timer",
            "stopwatch": "_sw_timer",
            "date_card": "_dc_timer",
            "countdown": "_cd_timer",
            "dday": "_dd_timer",
        }
        for widget_type, timer_attr in timer_attrs.items():
            inst_id = self.manager.add_instance(widget_type)
            widget = self.manager.get_widget(inst_id)
            timer = getattr(widget, timer_attr)
            self.assertFalse(timer.isActive(), widget_type)
            self.manager.show_instance(inst_id)
            self.assertTrue(timer.isActive(), widget_type)
            self.manager.hide_instance(inst_id)
            self.assertFalse(timer.isActive(), widget_type)

    def test_hidden_weather_defers_network_refresh_until_enabled(self):
        with patch(
            "calendar_app.presentation.widgets.overlay_weather.OverlayWeatherWidget.request_update"
        ) as request_update:
            inst_id = self.manager.add_instance("weather")
            widget = self.manager.get_widget(inst_id)
            self.__class__._app.processEvents()
            self.assertFalse(widget._refresh_timer.isActive())
            request_update.assert_not_called()

            self.manager.show_instance(inst_id)
            self.__class__._app.processEvents()
            self.assertTrue(widget._refresh_timer.isActive())
            request_update.assert_called_once()

            self.manager.hide_instance(inst_id)
            self.assertFalse(widget._refresh_timer.isActive())

    def test_restore_ignores_malformed_or_duplicate_metadata(self):
        self.settings.setValue("overlay_instances", json.dumps({"not": "a list"}))
        self.manager.restore_all()
        self.assertEqual(self.manager.all_instances(), [])

        self.settings.setValue(
            "overlay_instances",
            json.dumps(
                [
                    None,
                    "bad",
                    {"id": 4, "type": "clock", "name": "Invalid", "enabled": False},
                    {"id": "clock_0", "type": "clock", "name": "A", "enabled": False},
                    {"id": "clock_0", "type": "clock", "name": "B", "enabled": False},
                ]
            ),
        )
        self.manager.restore_all()
        self.assertEqual(len(self.manager.all_instances()), 1)


class OverlayTextRefreshTierTests(unittest.TestCase):
    class _TextWidget:
        def __init__(self, tier):
            self.tier = tier
            self.calls = []

        def is_enabled(self):
            return True

        def refresh_tier(self):
            return self.tier

        def refresh_template(self, *args):
            self.calls.append(args)

    def test_fast_timer_does_not_refresh_slow_template_with_empty_app_data(self):
        manager = OverlayWidgetManager.__new__(OverlayWidgetManager)
        slow_widget = self._TextWidget("slow")
        manager.get_widgets_of_type = lambda _kind: [slow_widget]
        manager.widget_registry = lambda: {}
        manager._get_app_data = lambda: {"task_count": 9}

        manager.refresh_all_texts(tier="fast")
        self.assertEqual(slow_widget.calls, [])

        manager.refresh_all_texts(tier="slow")
        self.assertEqual(len(slow_widget.calls), 1)
        self.assertEqual(slow_widget.calls[0][2], {"task_count": 9})


if __name__ == "__main__":
    unittest.main()
