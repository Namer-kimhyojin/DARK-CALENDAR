import unittest

from calendar_app.presentation.widgets import overlay_preset_store as store


class _FakeSettings:
    def __init__(self):
        self._values = {}

    def value(self, key, default=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value


class OverlayPresetStoreTests(unittest.TestCase):
    def test_user_presets_roundtrip_with_cleanup(self):
        s = _FakeSettings()
        prefix = "widget_x"
        store.save_user_presets(
            s,
            prefix,
            [
                {"name": "A", "template": "x"},
                {"name": "  ", "template": "ignored"},
                {"name": "B", "template": "y"},
            ],
        )

        loaded = store.load_user_presets(s, prefix)
        self.assertEqual(loaded, [{"name": "A", "template": "x"}, {"name": "B", "template": "y"}])

    def test_hidden_builtins_roundtrip(self):
        s = _FakeSettings()
        prefix = "widget_y"
        store.save_hidden_builtins(s, prefix, {"B", "A"})
        loaded = store.load_hidden_builtins(s, prefix)
        self.assertEqual(loaded, {"A", "B"})

    def test_invalid_json_returns_defaults(self):
        s = _FakeSettings()
        prefix = "widget_z"
        s.setValue(store._user_presets_key(prefix), "{broken")
        s.setValue(store._hidden_builtins_key(prefix), "{broken")
        self.assertEqual(store.load_user_presets(s, prefix), [])
        self.assertEqual(store.load_hidden_builtins(s, prefix), set())


if __name__ == "__main__":
    unittest.main()
