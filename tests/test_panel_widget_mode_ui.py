import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QLocale, QPoint, QRect, QSize, QTime
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget

from calendar_app.presentation.widgets import panel_widget_mode as pwm


class _FakeSettings:
    def __init__(self):
        self._values = {
            "theme_color": "#4da6ff",
            "widget_mode_always_top": "false",
            "widget_mode_reserve_space": "false",
        }

    def value(self, key, default=None, type=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value

    def remove(self, key):
        self._values.pop(key, None)


class _FakeApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = _FakeSettings()
        self.current_date = QDate(2026, 3, 26)
        self.sync_calls = 0
        self.is_visible = True
        self._panel_widget_mode_controller = None
        self._latest_agenda_data = None
        self._latest_calendar_range_data = None
        self._latest_directive_data = None
        self.panel_refresh_requests = []
        self.open_task_dialog_calls = []

    def sync_google_calendar(self):
        self.sync_calls += 1

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


def _fake_t(_key: str, fallback: str = "", **kwargs) -> str:
    base = fallback or _key
    import contextlib

    with contextlib.suppress(Exception):
        base = base.format(**kwargs)
    return f"[L]{base}"


class PanelWidgetModeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = _FakeApp()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()

    def test_entry_list_accepts_scale_and_renders_empty_state(self):
        widget = pwm._EntryListWidget(self.host)
        widget.set_entries([], {"text_faint": "#8899aa"}, "No entries", scale=1.25)

        labels = [lbl.text() for lbl in widget.findChildren(QLabel)]
        self.assertIn("No entries", labels)

    def test_entry_list_row_click_opens_directly_and_context_menu(self):
        delete_hits = []
        open_hits = []
        context_hits = []
        widget = pwm._EntryListWidget(self.host)
        widget.set_entries(
            [
                pwm._WidgetEntry(
                    title="Task A",
                    callback=lambda: open_hits.append("open"),
                    delete_callback=lambda: delete_hits.append("delete"),
                    context_menu_callback=lambda anchor, pos: context_hits.append((anchor, pos)),
                )
            ],
            {"text_primary": "#fff"},
            "empty",
            scale=1.0,
        )

        entry_btn = widget.findChild(QPushButton, "widget_entry_btn")
        self.assertIsNotNone(entry_btn)
        entry_btn.click()

        self.assertEqual(open_hits, ["open"])
        self.assertEqual(delete_hits, [])
        self.assertIsNone(widget.findChild(QWidget, "widget_entry_open_btn"))
        self.assertIsNone(widget.findChild(QWidget, "widget_entry_secondary_btn"))

        entry_btn.customContextMenuRequested.emit(QPoint(4, 5))
        self.assertEqual(len(context_hits), 1)
        self.assertIs(context_hits[0][0], entry_btn)
        self.assertEqual(context_hits[0][1], QPoint(4, 5))

    def test_context_menu_refresh_action_calls_callback(self):
        widget = pwm._FloatingWidgetBase(self.host, "Title", "I")
        hits = []
        widget.on_refresh_requested = lambda: hits.append("refresh")
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(1, 1),
            QPoint(1, 1),
        )

        def _pick_refresh(menu, *_args, **_kwargs):
            return menu.actions()[2]

        with patch.object(QMenu, "exec", new=_pick_refresh):
            widget.contextMenuEvent(event)

        self.assertEqual(hits, ["refresh"])

    def test_context_menu_exit_action_uses_restore_callback(self):
        widget = pwm._FloatingWidgetBase(self.host, "Title", "I")
        hits = []
        widget.set_restore_callback(lambda: hits.append("restore"))
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(1, 1),
            QPoint(1, 1),
        )

        def _pick_exit(menu, *_args, **_kwargs):
            return menu.actions()[0]

        with patch.object(QMenu, "exec", new=_pick_exit):
            widget.contextMenuEvent(event)

        self.assertEqual(hits, ["restore"])

    def test_panel_widget_calendar_visual_state_tracks_today_selected_and_marks(self):
        widget = pwm._PanelWidget(self.host)
        today = QDate(2026, 3, 26)
        selected = QDate(2026, 3, 27)
        widget.calendar.setSelectedDate(selected)
        widget.set_calendar_marks({today, selected}, today=today, selected=selected)

        self.assertEqual(widget.calendar.visual_marked_dates(), {"2026-03-26": 1, "2026-03-27": 1})
        self.assertEqual(widget.calendar.visual_state(), (today, selected))

    def test_widget_calendar_skips_duplicate_stylesheet_work_for_same_visual_state(self):
        widget = pwm._PanelWidget(self.host)
        calendar = widget.calendar
        tokens = widget.theme_tokens()
        marked = {"2026-03-26": 1}
        today = QDate(2026, 3, 26)
        selected = QDate(2026, 3, 26)

        with (
            patch.object(
                calendar, "setStyleSheet", wraps=calendar.setStyleSheet
            ) as set_stylesheet_mock,
            patch.object(
                calendar,
                "updateCells",
                wraps=calendar.updateCells,
            ) as update_cells_mock,
        ):
            calendar.set_visual_state(tokens, marked, today, selected)
            calendar.set_visual_state(tokens, marked, today, selected)

        self.assertEqual(1, set_stylesheet_mock.call_count)
        self.assertEqual(1, update_cells_mock.call_count)

    def test_widget_calendar_layout_metrics_keep_marker_lane_separate_from_day_number(self):
        widget = pwm._PanelWidget(self.host)
        calendar = widget.calendar
        calendar.set_visual_state(
            widget.theme_tokens(),
            {"2026-03-26": 3},
            QDate(2026, 3, 26),
            QDate(2026, 3, 26),
        )

        metrics = calendar._cell_layout_metrics(QRect(0, 0, 46, 40), is_marked=True)

        self.assertLess(
            metrics["text_rect"].bottom(), metrics["marker_center_y"] - metrics["dot_radius"] - 1.0
        )
        self.assertLess(metrics["mark_rect"].bottom(), metrics["marker_center_y"])

    def test_panel_widget_palette_uses_calendar_and_chip_tokens(self):
        widget = pwm._PanelWidget(self.host)
        widget.apply_palette()
        tokens = widget.theme_tokens()

        self.assertIn(tokens["header_shell_bg"], widget.calendar.styleSheet())
        self.assertIn(tokens["header_shell_border"], widget.calendar.styleSheet())
        self.assertIn(tokens["button_hover"], widget.calendar.styleSheet())
        nav_r = tokens["widget_calendar_nav_radius"]
        cal_ss = widget.calendar.styleSheet()
        self.assertTrue(
            f"border-radius: {nav_r}px;" in cal_ss or f"border-radius:{nav_r}px;" in cal_ss
        )

    def test_panel_widget_uses_roomier_calendar_height_bounds(self):
        widget = pwm._PanelWidget(self.host)
        widget.apply_palette(scale=1.0)

        self.assertGreaterEqual(widget.calendar.minimumHeight(), 266)
        self.assertGreaterEqual(widget.calendar.maximumHeight(), 356)

    def test_quick_add_input_uses_larger_text_size(self):
        widget = pwm._QuickAddInput(self.host, "Add item")
        widget.apply_palette(
            {
                "input_bg": "rgba(10,20,30,240)",
                "button_primary_bg": "rgba(34,195,202,44)",
                "button_primary_hover_bg": "rgba(34,195,202,66)",
            },
            scale=1.0,
        )

        # Glass style: font-size 9.0pt for both QLineEdit and QToolButton
        ss = widget.styleSheet()
        self.assertTrue("font-size: 9.0pt" in ss or "font-size:9.0pt" in ss)
        # input_bg token inserted verbatim
        self.assertIn("rgba(10,20,30,240)", widget.styleSheet())
        self.assertEqual(widget.edit.minimumHeight(), 34)

    def test_quick_add_input_skips_duplicate_stylesheet_application(self):
        widget = pwm._QuickAddInput(self.host, "Add item")
        tokens = {
            "input_bg": "rgba(10,20,30,240)",
            "button_primary_bg": "rgba(34,195,202,44)",
            "button_primary_hover_bg": "rgba(34,195,202,66)",
        }

        with patch.object(
            widget, "setStyleSheet", wraps=widget.setStyleSheet
        ) as set_stylesheet_mock:
            widget.apply_palette(tokens, scale=1.0)
            widget.apply_palette(tokens, scale=1.0)

        self.assertEqual(1, set_stylesheet_mock.call_count)

    def test_panel_widget_render_entries_shows_items(self):
        widget = pwm._PanelWidget(self.host)
        widget.render_entries(
            [
                pwm._WidgetEntry(title="Section", is_section=True),
                pwm._WidgetEntry(title="Work 1", subtitle="오전 9:00"),
                pwm._WidgetEntry(title="Work 2"),
            ]
        )
        titles = [
            label.text() for label in widget.list_widget.findChildren(QLabel, "widget_entry_title")
        ]
        self.assertIn("Work 1", titles)
        self.assertIn("Work 2", titles)
        self.assertIn(
            "오전 9:00",
            [
                label.text()
                for label in widget.list_widget.findChildren(QLabel, "widget_entry_time_label")
            ],
        )

    def test_entry_list_renders_rows_as_timeline_sequence(self):
        widget = pwm._EntryListWidget(self.host)
        widget.set_entries(
            [
                pwm._WidgetEntry(title="Task A", subtitle="오전 9:00"),
                pwm._WidgetEntry(title="Task B", subtitle="오후 1:30"),
            ],
            {
                "section_bg": "rgba(10,20,30,220)",
                "section_bg_alt": "rgba(30,40,50,230)",
                "hero_border": "#22c3ca",
            },
            "empty",
            scale=1.0,
        )

        rows = [widget.layout().itemAt(i).widget() for i in range(2)]
        self.assertEqual("오전 9:00", rows[0]._entry_time_label.text())
        self.assertEqual("오후 1:30", rows[1]._entry_time_label.text())
        self.assertFalse(rows[0]._entry_timeline_track.isHidden())
        self.assertFalse(rows[1]._entry_timeline_track.isHidden())

    def test_panel_widget_meta_bar_reflects_relative_day_and_item_count(self):
        widget = pwm._PanelWidget(self.host)
        widget.calendar.setSelectedDate(QDate.currentDate())
        widget.render_entries([pwm._WidgetEntry(title="Work 1"), pwm._WidgetEntry(title="Work 2")])

        self.assertTrue(widget.context_chip.text())
        self.assertIn("2", widget.count_chip.text())

    def test_panel_widget_skips_duplicate_calendar_and_entry_renders(self):
        widget = pwm._PanelWidget(self.host)
        entries = [pwm._WidgetEntry(title="Work 1")]
        marked = {QDate(2026, 3, 26)}

        with (
            patch.object(
                widget.calendar, "set_visual_state", wraps=widget.calendar.set_visual_state
            ) as visual_mock,
            patch.object(
                widget.list_widget,
                "set_entries",
                wraps=widget.list_widget.set_entries,
            ) as set_entries_mock,
        ):
            widget.set_calendar_marks(marked, today=QDate(2026, 3, 26), selected=QDate(2026, 3, 26))
            widget.set_calendar_marks(marked, today=QDate(2026, 3, 26), selected=QDate(2026, 3, 26))
            widget.render_entries(entries)
            widget.render_entries(entries)

        self.assertEqual(1, visual_mock.call_count)
        self.assertEqual(1, set_entries_mock.call_count)

    def test_entry_list_row_reuses_cached_child_refs_without_findchild(self):
        widget = pwm._EntryListWidget(self.host)
        entry = pwm._WidgetEntry(title="Task A", delete_callback=lambda: None)
        tokens = {
            "section_bg": "rgba(10,20,30,220)",
            "section_bg_alt": "rgba(30,40,50,230)",
            "hero_border": "#ff00aa",
        }

        widget.set_entries([entry], tokens, "empty", scale=1.0)
        row = widget.layout().itemAt(0).widget()
        self.assertIsNotNone(getattr(row, "_entry_btn", None))
        self.assertIsNotNone(getattr(row, "_entry_timeline_track", None))

        with patch.object(
            row, "findChild", side_effect=AssertionError("findChild should not be used again")
        ):
            widget.set_entries([entry], tokens, "empty", scale=1.0)

    def test_widget_mode_date_helpers_are_locale_aware(self):
        locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        target = QDate(2026, 3, 28)

        compact = pwm._format_compact_date(target, locale)
        with_weekday = pwm._format_compact_date_with_weekday(target, locale)

        self.assertNotIn("2026", compact)
        self.assertIn(
            locale.dayName(target.dayOfWeek(), QLocale.FormatType.ShortFormat), with_weekday
        )
        self.assertIn(compact, with_weekday)

    def test_widget_mode_datetime_label_uses_locale_short_time_and_compact_date(self):
        locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        reference = QDate(2026, 3, 28)

        same_day = pwm._format_widget_datetime_label(
            "2026-03-28 14:30:00", reference_date=reference, locale=locale
        )
        other_day = pwm._format_widget_datetime_label(
            "2026-03-30 09:15:00", reference_date=reference, locale=locale
        )

        self.assertEqual(same_day, locale.toString(QTime(14, 30), QLocale.FormatType.ShortFormat))
        self.assertIn(pwm._format_compact_date(QDate(2026, 3, 30), locale), other_day)
        self.assertIn(locale.toString(QTime(9, 15), QLocale.FormatType.ShortFormat), other_day)
        self.assertNotIn("2026-03-30", other_day)

    def test_panel_widget_uses_locale_first_day_of_week(self):
        original = QLocale()
        us_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        de_locale = QLocale(QLocale.Language.German, QLocale.Country.Germany)
        try:
            QLocale.setDefault(us_locale)
            widget = pwm._PanelWidget(self.host)
            self.assertEqual(widget.calendar.firstDayOfWeek(), us_locale.firstDayOfWeek())

            QLocale.setDefault(de_locale)
            widget.apply_palette()
            self.assertEqual(widget.calendar.firstDayOfWeek(), de_locale.firstDayOfWeek())
        finally:
            QLocale.setDefault(original)

    def test_widget_mode_theme_tokens_use_light_aqua_preset(self):
        tokens = pwm._build_widget_mode_theme_tokens(self.host)
        self.assertTrue(tokens)
        self.assertEqual(tokens.get("accent"), "#22c3ca")
        self.assertEqual(tokens.get("card_text_primary"), "#31465f")
        self.assertIn("panel_bg_start", tokens)

    def test_widget_mode_launcher_palette_uses_resolved_theme_tokens(self):
        self.host.settings.setValue("ui_shape_preset", "modern")
        launcher = pwm._WidgetModeLauncher(self.host)
        tokens = pwm._build_widget_mode_theme_tokens(self.host)

        # Glass launcher uses panel_bg (not shell_gradient_start)
        self.assertIn(tokens["panel_bg"], launcher.styleSheet())
        self.assertIn(tokens["section_bg"], launcher.styleSheet())
        self.assertIn(tokens["hero_border"], launcher.styleSheet())
        lr = tokens["launcher_radius"]
        l_ss = launcher.styleSheet()
        self.assertTrue(f"border-radius: {lr}px;" in l_ss or f"border-radius:{lr}px;" in l_ss)

    def test_widget_mode_theme_tokens_respect_dialog_token_override(self):
        self.host.settings.setValue("dialog_token.accent", "#ff00aa")
        tokens = pwm._build_widget_mode_theme_tokens(self.host)
        self.assertEqual(tokens.get("accent"), "#ff00aa")

    def test_floating_widget_menu_stylesheet_uses_theme_tokens(self):
        widget = pwm._FloatingWidgetBase(self.host, "Title", "I")
        menu_qss = widget._menu_stylesheet()
        tokens = widget.theme_tokens()

        # Glass menu uses panel_bg and panel_border
        self.assertIn(tokens["panel_bg"], menu_qss)
        self.assertIn(tokens["panel_border"], menu_qss)
        self.assertIn(tokens["text_secondary"], menu_qss)

    def test_widget_accent_override_updates_widget_palette(self):
        widget = pwm._PanelWidget(self.host)
        self.host.settings.setValue(widget._color_setting_key(), "#ff6b6b")
        tokens = widget._read_theme_tokens()
        self.assertEqual(tokens.get("accent"), "#ff6b6b")

    def test_entry_list_uses_resolved_button_styles(self):
        widget = pwm._EntryListWidget(self.host)
        widget.set_entries(
            [
                pwm._WidgetEntry(
                    title="Task A",
                    delete_callback=lambda: None,
                )
            ],
            {
                "section_bg": "rgba(10,20,30,220)",
                "section_bg_alt": "rgba(30,40,50,230)",
                "hero_border": "#ff00aa",
            },
            "empty",
            scale=1.0,
        )

        entry_btn = widget.findChild(QPushButton, "widget_entry_btn")
        self.assertIsNotNone(entry_btn)
        # section_bg token inserted verbatim as row background
        self.assertIn("rgba(10,20,30,220)", entry_btn.styleSheet())
        # section_bg_alt token inserted verbatim for hover background
        self.assertIn("rgba(30,40,50,230)", entry_btn.styleSheet())
        # hero_border token used for hover border on entry button
        self.assertIn("#ff00aa", entry_btn.styleSheet())

    def test_open_panel_shows_unified_widget(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller

        controller.open_panel()
        panel = controller._panel
        self.assertIsNotNone(panel)
        self.assertTrue(panel.isVisible())
        panel.hide()

    def test_panel_widget_has_no_inline_quick_add_input(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        self.assertFalse(hasattr(panel, "quick_add"))

    def test_refresh_visible_widgets_keeps_existing_panel_position(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        controller._refresh_panel = lambda: None

        panel = controller._ensure_panel()
        panel.show()
        panel.move(120, 160)
        self.host.settings.setValue(panel.position_setting_key(), QPoint(120, 160))

        controller.refresh_visible_widgets()

        self.assertEqual(panel.pos(), QPoint(120, 160))

    def test_panel_widget_show_does_not_create_fade_animation(self):
        widget = pwm._PanelWidget(self.host)

        widget.show()
        QApplication.processEvents()

        self.assertFalse(hasattr(widget, "_entry_anim"))
        widget.hide()

    def test_refresh_visible_widgets_skips_duplicate_palette_apply(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        panel.show()
        controller._last_palette_signature = None
        controller._render_from_main_cache = lambda: None

        with patch.object(panel, "apply_palette", wraps=panel.apply_palette) as apply_mock:
            controller.refresh_visible_widgets()
            controller.refresh_visible_widgets()

        self.assertEqual(1, apply_mock.call_count)

    def test_panel_widget_refresh_timer_has_small_explicit_debounce(self):
        controller = pwm.PanelWidgetModeController(self.host)

        self.assertTrue(controller._debounce_timer.isSingleShot())
        self.assertEqual(24, controller._debounce_timer.interval())

    def test_position_panel_skips_redundant_window_updates(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        panel.show()

        controller._position_panel(force_reset=True)

        with (
            patch.object(panel, "resize", wraps=panel.resize) as resize_mock,
            patch.object(
                panel,
                "move",
                wraps=panel.move,
            ) as move_mock,
        ):
            controller._position_panel(force_reset=False)

        self.assertEqual(0, resize_mock.call_count)
        self.assertEqual(0, move_mock.call_count)

    def test_panel_opacity_changes_background_tokens_without_window_opacity(self):
        widget = pwm._PanelWidget(self.host)
        default_tokens = widget._read_theme_tokens()

        widget._set_individual_opacity(50)
        updated_tokens = widget._read_theme_tokens()

        self.assertAlmostEqual(1.0, widget.windowOpacity(), places=2)
        self.assertNotEqual(default_tokens["panel_bg"], updated_tokens["panel_bg"])

    def test_open_task_dialog_helper_does_not_force_immediate_refresh(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        refresh_hits = []
        controller._refresh_panel = lambda: refresh_hits.append("refresh")

        controller._open_task_dialog_helper(
            task_type="schedule", initial_date=QDate(2026, 3, 26), text="14:00 Team Meeting"
        )

        self.assertEqual([], refresh_hits)
        self.assertEqual(1, len(getattr(self.host, "open_task_dialog_calls", [])))

    def test_open_panel_restores_saved_panel_size(self):
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        self.host.settings.setValue(panel.size_setting_key(), QSize(444, 555))

        controller.open_panel()

        self.assertEqual(panel.size(), QSize(444, 555))
        controller.close_panel()

    def test_open_panel_skips_main_refresh_when_caches_are_already_fresh(self):
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-26",
            "routine_rows": [],
            "directive_rows": [],
        }
        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller

        controller.open_panel()

        self.assertEqual(self.host.panel_refresh_requests, [])
        controller.close_panel()

    def test_widget_renders_only_selected_date_schedule_and_work_from_main_cache(self):
        selected = QDate(2026, 3, 27)
        self.host.current_date = selected
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
            ],
            "directive_rows": [
                (21, "Selected Directive", "pending", "Team", "2026-03-27", "", "#ffffff", False),
                (22, "Other Directive", "pending", "Team", "2026-03-28", "", "#ffffff", False),
            ],
        }

        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        panel.show()
        panel.calendar.setSelectedDate(selected)

        controller._render_from_main_cache()

        titles = [
            label.text() for label in panel.list_widget.findChildren(QLabel, "widget_entry_title")
        ]
        self.assertTrue(any(text.startswith("Selected Schedule") for text in titles))
        self.assertTrue(any(text.startswith("Carryover Schedule") for text in titles))
        self.assertTrue(any(text.startswith("Selected Routine") for text in titles))
        self.assertTrue(any(text.startswith("Selected Directive") for text in titles))
        self.assertFalse(any(text.startswith("Other Schedule") for text in titles))
        self.assertFalse(any(text.startswith("Other Routine") for text in titles))
        self.assertFalse(any(text.startswith("Other Directive") for text in titles))

    def test_render_from_main_cache_skips_recomputing_same_signature(self):
        selected = QDate(2026, 3, 27)
        self.host.current_date = selected
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [{"id": 1, "name": "Selected Schedule", "deadline": "2026-03-27 09:00:00"}],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-27",
            "routine_rows": [],
            "directive_rows": [],
        }

        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        panel.show()
        panel.calendar.setSelectedDate(selected)

        with (
            patch.object(
                controller,
                "_cached_month_marked_dates",
                wraps=controller._cached_month_marked_dates,
            ) as marked_mock,
            patch.object(
                controller,
                "_cached_schedule_entries_for_date",
                wraps=controller._cached_schedule_entries_for_date,
            ) as schedule_mock,
            patch.object(
                controller,
                "_cached_work_entries_for_date",
                wraps=controller._cached_work_entries_for_date,
            ) as work_mock,
        ):
            controller._render_from_main_cache()
            controller._render_from_main_cache()

        self.assertEqual(1, marked_mock.call_count)
        self.assertEqual(1, schedule_mock.call_count)
        self.assertEqual(1, work_mock.call_count)

    def test_date_change_requests_main_cache_refresh_when_widget_cache_is_stale(self):
        self.host._latest_calendar_range_data = {
            "range_start": "2026-03-01",
            "range_end": "2026-03-31",
            "rows": [],
        }
        self.host._latest_directive_data = {
            "context_date": "2026-03-26",
            "routine_rows": [],
            "directive_rows": [],
        }

        controller = pwm.PanelWidgetModeController(self.host)
        self.host._panel_widget_mode_controller = controller
        panel = controller._ensure_panel()
        panel.calendar.setSelectedDate(QDate(2026, 4, 2))

        self.assertTrue(self.host.panel_refresh_requests)
        last_request = self.host.panel_refresh_requests[-1]
        self.assertEqual(last_request["center"], True)
        self.assertEqual(last_request["right"], True)
        self.assertEqual(self.host.current_date, QDate(2026, 4, 2))


if __name__ == "__main__":
    unittest.main()
