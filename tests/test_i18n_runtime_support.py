import json
from pathlib import Path
import unittest

from calendar_app.infrastructure.i18n import I18nManager

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"


def _resolve_locale_value(data, dotted_key):
    if not isinstance(data, dict):
        return None
    if dotted_key in data:
        return data[dotted_key]

    parts = dotted_key.split(".")
    current = data
    for idx, part in enumerate(parts):
        if not isinstance(current, dict):
            return None
        if part in current:
            current = current[part]
            continue
        remaining = ".".join(parts[idx:])
        return current.get(remaining) if isinstance(current, dict) else None
    return current


def _flatten_locale_entries(data, prefix=""):
    out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_locale_entries(value, dotted))
    elif isinstance(data, list):
        out[prefix] = data
    else:
        out[prefix] = data
    return out


def _unflatten_locale_entries(flat):
    root = {}
    for dotted_key, value in flat.items():
        current = root
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return root


def _sort_locale_tree(data):
    if isinstance(data, dict):
        return {key: _sort_locale_tree(data[key]) for key in sorted(data)}
    if isinstance(data, list):
        return [_sort_locale_tree(item) for item in data]
    return data


def _render_locale_json(data, indent=0):
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return "{}"
        items = list(data.items())
        lines = ["{"]
        for idx, (key, value) in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            lines.append(
                f"{'  ' * (indent + 1)}{json.dumps(key, ensure_ascii=False)}: "
                f"{_render_locale_json(value, indent + 1)}{comma}"
            )
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return "[]"
        if all(not isinstance(item, (dict, list)) for item in data):
            return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in data) + "]"
        lines = ["["]
        for idx, item in enumerate(data):
            comma = "," if idx < len(data) - 1 else ""
            lines.append(f"{'  ' * (indent + 1)}{_render_locale_json(item, indent + 1)}{comma}")
        lines.append(f"{pad}]")
        return "\n".join(lines)
    return json.dumps(data, ensure_ascii=False)


class I18nRuntimeSupportTests(unittest.TestCase):
    def test_manager_resolves_flat_dotted_keys_and_fallbacks(self):
        manager = object.__new__(I18nManager)
        manager.translations = {
            "widget.weather.settings_title": "날씨 설정",
            "widget": {"weather.location": "지역"},
        }
        manager.same_lang_fallback_translations = {}
        manager.fallback_translations = {
            "topbar.widget_mode_hint": "Open widget mode",
        }

        self.assertEqual("날씨 설정", manager.get("widget.weather.settings_title"))
        self.assertEqual("지역", manager.get("widget.weather.location"))
        self.assertEqual("Open widget mode", manager.get("topbar.widget_mode_hint"))

    def test_base_locales_cover_runtime_regression_keys(self):
        required_keys = [
            "common.default",
            "dialog.task.untitled",
            "focus.pause",
            "focus.resume",
            "focus.phase_focus",
            "focus.phase_long_break",
            "focus.phase_short_break",
            "focus.phase_paused",
            "focus.session_saved_title",
            "topbar.widget_mode_btn",
            "topbar.widget_mode_hint",
            "weather.desc.clear",
            "weather.desc.storm",
            "widget.menu.overall_opacity",
            "widget_mode.menu_google_sync",
            "widget_mode.quick_actions",
            "widget_mode.schedule_title",
            "widget_mode.work_title",
        ]

        for lang in ("en", "ko"):
            data = json.loads(
                (LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8", errors="strict")
            )
            missing = [key for key in required_keys if _resolve_locale_value(data, key) is None]
            self.assertFalse(missing, msg=f"{lang} missing runtime keys: {missing}")

    def test_all_locales_include_recent_multilingual_regression_keys(self):
        required_keys = [
            "tray.focus_timer_settings",
            "menu.widget_weather",
            "widget.weather.settings_title",
            "widget.weather.location",
            "widget.weather.unit",
            "widget.weather.refresh_interval",
            "dialog.theme.preset.filter_label",
            "dialog.theme.bg.auto_apply_text",
            "calendar.opt_weekend_hidden",
            "calendar.opt_weekend_hidden_hint",
            "calendar.more_items",
            "dialog.task.calendar_read_only",
            "palette.theme_dark",
            "palette.sync_google",
            "palette.kw.theme",
            "widget_mode.scale_tooltip_value",
            "widget_mode.desc",
            "widget_mode.schedule_title",
            "widget_mode.legend_today_date",
            "widget_mode.legend_selected_date",
            "widget_mode.empty_schedule",
            "widget_mode.work_title",
            "widget_mode.work_summary",
            "widget_mode.empty_work",
        ]

        missing_by_locale = {}
        for path in sorted(LOCALES_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
            missing = [key for key in required_keys if _resolve_locale_value(data, key) is None]
            if missing:
                missing_by_locale[path.name] = missing

        self.assertFalse(missing_by_locale, msg=f"Locale coverage gaps: {missing_by_locale}")

    def test_en_and_ko_cover_recent_korean_locale_gap_keys(self):
        required_keys = [
            "dialog.theme.preview.input_hint",
            "dialog.theme.text.input_bg",
            "dialog.token_editor.apply_done",
            "dialog.token_editor.export_failed",
            "dialog.token_editor.export_success",
            "dialog.token_editor.import_failed",
            "dialog.token_editor.import_success",
            "dialog.token_editor.invalid_short",
            "dialog.token_editor.metric_preset_applied",
            "dialog.token_editor.mode_all",
            "dialog.token_editor.mode_dark",
            "dialog.token_editor.mode_light",
            "dialog.token_editor.preset_applied",
            "dialog.token_editor.preset_color_mode",
            "dialog.token_editor.reset_done",
            "drag.hint_copy",
            "gcal.setup_disabled_guide",
            "gcal.setup_needed_msg",
            "gcal_settings.ics_last_synced",
            "lock.overlay_lock",
            "lock.overlay_lock_hint",
            "lock.overlay_unlock",
            "lock.overlay_unlock_hint",
            "menu.theme_mode",
            "menu.widget_mode_toggle",
            "panel.help.default_name",
            "panel.help.title",
            "panel.help.quick_title",
            "panel.help.recovery_intro",
            "panel.help.magnet",
            "panel.help.topbar",
            "panel.help.lock",
            "panel.toolbar.quick_help",
            "theme.system_default",
            "focus.duration_hours_minutes",
            "focus.duration_minutes_seconds",
            "focus.duration_seconds",
            "focus.duration_minutes",
            "focus.session_summary",
            "dialog.pomodoro_settings.set_goal",
            "focus.error_no_task",
            "focus.error_title",
            "focus.exit_hint_pomodoro",
            "focus.phase_with_cycle",
            "focus.pomodoro_summary",
            "focus.session_saved_msg",
            "focus.start_long_break",
            "focus.stat_month_total",
            "focus_selector.delete_confirm_msg",
            "focus_selector.delete_confirm_title",
            "focus_selector.delete_no_selection",
            "focus_selector.filter_today_directives",
            "focus_selector.log_summary",
            "widget.countdown.end_of_day",
            "widget.countdown.quick_presets",
            "widget.countdown.title",
            "widget.countdown.set_target",
            "widget.countdown.tomorrow",
            "widget.datecard.preset_glass",
            "widget.datecard.preset_month_end",
            "widget.datecard.preset_quarter",
            "widget.datecard.preset_tomorrow",
            "widget.datecard.preset_week_num",
            "widget.datecard.style.banner",
            "widget.datecard.style.glass",
            "widget.datecard.style.mini_grid",
            "widget.datecard.style.retro",
            "widget.stopwatch.title",
            "widget.stopwatch.short_title",
            "widget.stopwatch.status_run",
            "widget.stopwatch.status_stop",
            "widget_manager.btn_add",
            "widget_manager.btn_hide_all",
            "widget_manager.btn_settings",
            "widget_manager.btn_show_all",
            "widget_manager.footer_hint",
            "widget_manager.list_heading",
            "widget_manager.new_widget",
            "widget_manager.tip_center",
            "widget_manager.tip_delete",
            "widget_manager.tip_reset",
            "widget_mode.empty_panel",
            "widget_mode.panel_title",
            "widget_mode.section_work_today",
            "widget_mode.style_panel_theme",
            "widget_mode.theme_dark",
            "widget_mode.theme_light",
        ]

        for lang in ("en", "ko"):
            data = json.loads(
                (LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8", errors="strict")
            )
            missing = [key for key in required_keys if _resolve_locale_value(data, key) is None]
            self.assertFalse(missing, msg=f"{lang} missing Korean locale gap keys: {missing}")

    def test_en_and_ko_locale_files_share_same_canonical_layout(self):
        locale_lines = {}
        for lang in ("en", "ko"):
            path = LOCALES_DIR / f"{lang}.json"
            raw = path.read_text(encoding="utf-8", errors="strict")
            data = json.loads(raw)
            canonical = _sort_locale_tree(_unflatten_locale_entries(_flatten_locale_entries(data)))
            rendered = _render_locale_json(canonical) + "\n"
            self.assertEqual(rendered, raw, msg=f"{lang} locale file is not in canonical format")
            locale_lines[lang] = len(raw.splitlines())

        self.assertEqual(
            locale_lines["en"],
            locale_lines["ko"],
            msg=f"Locale files should keep matching line counts: {locale_lines}",
        )


if __name__ == "__main__":
    unittest.main()
