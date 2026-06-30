import unittest

from calendar_app.app_metadata import (
    APP_RELEASE_CHANNEL,
    APP_RELEASE_DATE,
    APP_VERSION,
    APP_VERSION_DETAIL,
    APP_VERSION_DISPLAY,
    APP_VERSION_LABEL,
)
from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    build_shortcut_guide_html,
    get_key,
)


class AppMetadataTests(unittest.TestCase):
    def test_user_facing_version_labels_are_consistent(self):
        self.assertEqual(APP_VERSION_LABEL, f"v{APP_VERSION}")
        self.assertIn(APP_VERSION_LABEL, APP_VERSION_DISPLAY)
        self.assertIn(APP_RELEASE_CHANNEL, APP_VERSION_DISPLAY)
        self.assertIn(APP_RELEASE_DATE, APP_VERSION_DETAIL)

    def test_shortcut_guide_footer_can_show_display_version(self):
        html = build_shortcut_guide_html(
            app_version=APP_VERSION_DISPLAY,
            app_author="Tester",
            app_email="tester@example.com",
        )

        self.assertIn(APP_VERSION_DISPLAY, html)
        self.assertIn("tester@example.com", html)

    def test_shortcut_guide_emphasizes_recovery_shortcuts_and_sections(self):
        html = build_shortcut_guide_html()

        self.assertIn("단축키 한눈에 보기", html)
        self.assertIn("Quick Recovery", html)
        for shortcut_id in ("topbar", "magnet_mode", "lock_mode", "force_unlock"):
            for key_part in get_key(shortcut_id).split("+"):
                self.assertIn(key_part, html)
        self.assertIn("등록", html)
        self.assertIn("창", html)
        self.assertIn("F12", html)
        self.assertIn("레이아웃 프리셋 1", html)


if __name__ == "__main__":
    unittest.main()
