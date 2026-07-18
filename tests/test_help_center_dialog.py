import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog


class HelpCenterDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_help_center_has_search_page_and_navigation(self):
        dlg = HelpCenterDialog(app_version="v1.0.0")
        self.addCleanup(dlg.close)

        self.assertEqual(4, dlg.nav_list.count())
        self.assertEqual(5, dlg.page_stack.count())
        self.assertEqual("quickstart", dlg._selected_page_id)

    def test_help_center_search_switches_to_results_page(self):
        dlg = HelpCenterDialog(app_version="v1.0.0")
        self.addCleanup(dlg.close)

        dlg.search_input.setText("잠금")

        self.assertEqual(dlg._page_indexes["search"], dlg.page_stack.currentIndex())
        self.assertIn("검색 결과", dlg.search_results_count.text())
        self.assertGreater(dlg.search_results_container_layout.count(), 1)


if __name__ == "__main__":
    unittest.main()
