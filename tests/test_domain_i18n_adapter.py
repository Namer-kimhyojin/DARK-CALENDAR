import sys
import types
import unittest

from calendar_app.domain import i18n as domain_i18n


class DomainI18nAdapterTests(unittest.TestCase):
    def setUp(self):
        self._saved_module = sys.modules.get("calendar_app.infrastructure.i18n")
        domain_i18n.set_translator(None)

    def tearDown(self):
        domain_i18n.set_translator(None)
        if self._saved_module is None:
            sys.modules.pop("calendar_app.infrastructure.i18n", None)
        else:
            sys.modules["calendar_app.infrastructure.i18n"] = self._saved_module

    def test_fallback_and_format_without_translator(self):
        sys.modules.pop("calendar_app.infrastructure.i18n", None)

        self.assertEqual(domain_i18n.t("sample.key"), "sample.key")
        self.assertEqual(
            domain_i18n.t("sample.key", "Hello {name}", name="World"),
            "Hello World",
        )

    def test_set_translator_overrides_resolution(self):
        domain_i18n.set_translator(lambda key, fallback="", **kwargs: f"X:{key}")
        self.assertEqual(domain_i18n.t("priority.urgent", "Urgent"), "X:priority.urgent")

    def test_auto_resolve_from_infrastructure_module(self):
        fake_module = types.ModuleType("calendar_app.infrastructure.i18n")
        fake_module.t = lambda key, fallback="", **kwargs: f"AUTO:{key}"
        sys.modules["calendar_app.infrastructure.i18n"] = fake_module
        domain_i18n.set_translator(None)

        self.assertEqual(domain_i18n.t("status.pending", "Pending"), "AUTO:status.pending")


if __name__ == "__main__":
    unittest.main()
