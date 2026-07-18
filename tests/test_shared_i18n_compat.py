import unittest
from unittest.mock import patch

from calendar_app.shared import i18n as shared_i18n


class SharedI18nCompatTests(unittest.TestCase):
    def test_tr_falls_back_to_input_when_infra_missing(self):
        with patch("calendar_app.shared.i18n.import_module", side_effect=ModuleNotFoundError):
            self.assertEqual(shared_i18n.tr("sample.key"), "sample.key")

    def test_tr_supports_format_kwargs_without_infra(self):
        with patch("calendar_app.shared.i18n.import_module", side_effect=ModuleNotFoundError):
            self.assertEqual(
                shared_i18n._infra_translate("k", "Hello {name}", name="World"), "Hello World"
            )


if __name__ == "__main__":
    unittest.main()
