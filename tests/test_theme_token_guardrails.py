from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOTSPOT_PATTERN = re.compile(r"setStyleSheet\(|#[0-9A-Fa-f]{3,8}|rgba\(")
TEMPLATE_COLOR_HINT_PATTERN = re.compile(r"color=([A-Za-z_][A-Za-z0-9_-]*|#[0-9A-Fa-f]{3,8})")
RGBA_LITERAL_PATTERN = re.compile(r"(?<![A-Za-z_])rgba\(")
HEX_PLACEHOLDER_PATTERN = re.compile(r"#[R]{2}[G]{2}[B]{2}")
LEGACY_TEMPLATE_EQ_HEX_PATTERN = re.compile(r"color=#[0-9A-Fa-f]{3,8}")
INLINE_COLOR_HEX_PATTERN = re.compile(r"color:\s*#[0-9A-Fa-f]{3,8}")


class ThemeTokenGuardrailTests(unittest.TestCase):
    def test_completion_process_document_exists(self):
        process_doc = ROOT / "docs" / "theme_token_completion_process.md"
        self.assertTrue(process_doc.exists())
        text = process_doc.read_text(encoding="utf-8", errors="strict")
        self.assertIn("Stage 1. Baseline", text)
        self.assertIn("Stage 4. Guardrails", text)
        self.assertIn("Stage 5. Verification", text)

    def test_hotspot_counts_do_not_regress_for_runtime_widget_files(self):
        limits = {
            ROOT / "calendar_app" / "presentation" / "widgets" / "alarm_popup.py": 3,
            ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_manager.py": 1,
            ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_manager_dialog.py": 13,
            ROOT / "calendar_app" / "presentation" / "widgets" / "command_palette.py": 4,
        }

        for path, limit in limits.items():
            text = path.read_text(encoding="utf-8", errors="strict")
            count = len(HOTSPOT_PATTERN.findall(text))
            self.assertLessEqual(
                count, limit, f"{path.name} hotspot count regressed: {count} > {limit}"
            )

    def test_overlay_base_legacy_runtime_snippets_do_not_return(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_base.py"
        text = path.read_text(encoding="utf-8", errors="strict")

        forbidden = [
            "color:#6ab0f5;text-decoration:none;",
            "padding: 18px 12px;",
            "color:#5a7aaa; font-size:8pt;",
            "border: 1px solid #444; border-radius: 4px;",
            "QToolButton { color:#7a90b8; font-size:9pt; background:transparent;",
        ]
        for snippet in forbidden:
            self.assertNotIn(snippet, text)

        required_helpers = [
            "def _overlay_color_button_style(",
            "def _overlay_hint_toggle_style(",
            "def _overlay_hint_link_style(",
            "def _overlay_preview_card_inline_style(",
            "def _overlay_group_label_style(",
        ]
        for snippet in required_helpers:
            self.assertIn(snippet, text)

    def test_overlay_base_template_literal_policy_is_confined(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_base.py"
        lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
        allowed_colors = {"muted", "accent", "warning"}
        allowed_line_markers = (
            '"template":',
            "grammar_token",
            "grammar_plain_text",
            "custom hex color",
        )

        for index, line in enumerate(lines, 1):
            for match in TEMPLATE_COLOR_HINT_PATTERN.findall(line):
                self.assertIn(
                    match,
                    allowed_colors,
                    f"overlay_base.py:{index} introduced unexpected template/example color {match}",
                )
                self.assertTrue(
                    any(marker in line for marker in allowed_line_markers),
                    f"overlay_base.py:{index} template/example literal escaped its allowed buckets",
                )

    def test_widget_presets_json_uses_template_color_aliases(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "widget_presets.json"
        text = path.read_text(encoding="utf-8", errors="strict")

        self.assertIsNone(
            LEGACY_TEMPLATE_EQ_HEX_PATTERN.search(text),
            "widget_presets.json still contains a raw template hex color hint",
        )
        self.assertIn("color=muted", text)
        self.assertIn("color=accent", text)

    def test_locale_examples_drop_fixed_preview_hex_and_hex_placeholder_copy(self):
        locale_dir = ROOT / "locales"
        for path in locale_dir.glob("*.json"):
            text = path.read_text(encoding="utf-8", errors="strict")
            for line in text.splitlines():
                if '"preview_empty"' not in line:
                    continue
                self.assertIsNone(
                    INLINE_COLOR_HEX_PATTERN.search(line),
                    f"{path.name} still contains a preview_empty inline hex color",
                )
            self.assertIsNone(
                HEX_PLACEHOLDER_PATTERN.search(text),
                f"{path.name} still contains a raw hex placeholder string",
            )

    def test_dialog_token_editor_copy_drops_raw_hex_placeholder(self):
        path = ROOT / "calendar_app" / "presentation" / "dialogs" / "dialog_token_editor_dialog.py"
        text = path.read_text(encoding="utf-8", errors="strict")
        self.assertIsNone(
            HEX_PLACEHOLDER_PATTERN.search(text),
            "dialog_token_editor_dialog.py still contains a raw hex placeholder string",
        )

    def test_overlay_base_rgba_literals_stay_in_fallback_tables_or_token_mappers(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_base.py"
        lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
        allowed_markers = (
            "accent_bg_color",
            "accent_border_color",
            "accent_text_color",
            "stop:0 rgba(",
            "border: 1px solid rgba(",
            "QFrame#previewCard",
            "QFrame#hintBox",
            "QDialogButtonBox QPushButton",
            "QPushButton#dangerBtn",
            "QPushButton#resetBtn",
            "QPushButton#presetBtn",
            'return f"rgba(',
            'selected_bg = f"rgba(',
            'if raw.lower().startswith("rgba(")',
            '"rgba(60,140,255,0.12)"',
            '"rgba(60,140,255,0.20)"',
            '"rgba(60,140,255,0.25)"',
            '"rgba(60,140,255,0.30)"',
            '"rgba(60,140,255,0.35)"',
            '"rgba(60,140,255,0.55)"',
        )

        for index, line in enumerate(lines, 1):
            if not RGBA_LITERAL_PATTERN.search(line):
                continue
            self.assertTrue(
                any(marker in line for marker in allowed_markers),
                f"overlay_base.py:{index} has an rgba literal outside the approved fallback/mapper buckets",
            )

    def test_alarm_popup_static_stylesheet_does_not_return(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "alarm_popup.py"
        text = path.read_text(encoding="utf-8", errors="strict")

        self.assertNotIn("_SS = f", text)
        self.assertNotIn('_BTN_CONFIRM = "#2a7af4"', text)
        self.assertNotIn('_BG = "#1a2035"', text)
        self.assertIn("def _alarm_popup_style_bundle(", text)
        self.assertIn("def _build_alarm_popup_stylesheet(", text)
        self.assertIn("def _alarm_time_label_style(", text)

    def test_overlay_manager_dialog_no_longer_uses_legacy_accent_constants(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_manager_dialog.py"
        text = path.read_text(encoding="utf-8", errors="strict")

        self.assertNotIn("_ACCENT_COLOR =", text)
        self.assertNotIn("_DANGER_COLOR =", text)

    def test_overlay_manager_uses_overlay_menu_helper(self):
        path = ROOT / "calendar_app" / "presentation" / "widgets" / "overlay_manager.py"
        text = path.read_text(encoding="utf-8", errors="strict")

        self.assertNotIn("_DEFAULT_MENU_STYLE = (", text)
        self.assertIn("def _default_menu_style()", text)
        self.assertIn("_overlay_menu_style()", text)


if __name__ == "__main__":
    unittest.main()
