import unittest

from calendar_app.presentation.main_window.dock_sections import dock_layout_presets as dlp


class _PresetManagerStub:
    def __init__(self, presets=None, apply_ok=True):
        self._presets = presets or {}
        self.apply_ok = apply_ok
        self.loaded_names = []
        self.applied_payloads = []

    def _read_presets(self):
        return dict(self._presets)

    def _load_preset(self, name):
        self.loaded_names.append(name)

    def _apply_payload(self, payload):
        self.applied_payloads.append(payload)
        return self.apply_ok


class _AppStub:
    def __init__(self, preset_manager):
        self.preset_manager = preset_manager
        self.toasts = []

    def show_toast(self, title, message):
        self.toasts.append((title, message))


class DockLayoutPresetTests(unittest.TestCase):
    def test_embedded_release_payload_is_used_when_user_slot_is_missing(self):
        host = _AppStub(_PresetManagerStub())

        dlp.apply_layout_preset(host, 0)

        self.assertEqual([], host.preset_manager.loaded_names)
        self.assertEqual(1, len(host.preset_manager.applied_payloads))
        self.assertEqual(
            dlp._embedded_release_preset_payload(0)["dock_state_b64"],
            host.preset_manager.applied_payloads[0]["dock_state_b64"],
        )

    def test_embedded_release_payload_is_also_available_for_slot_five(self):
        host = _AppStub(_PresetManagerStub())

        dlp.apply_layout_preset(host, 4)

        self.assertEqual([], host.preset_manager.loaded_names)
        self.assertEqual(1, len(host.preset_manager.applied_payloads))
        self.assertEqual(
            dlp._embedded_release_preset_payload(4)["dock_state_b64"],
            host.preset_manager.applied_payloads[0]["dock_state_b64"],
        )

    def test_user_saved_slot_still_overrides_embedded_release_payload(self):
        slot_name = dlp.LAYOUT_PRESET_DEFS[0][0]
        host = _AppStub(_PresetManagerStub(presets={slot_name: {"dock_state_b64": "user"}}))

        dlp.apply_layout_preset(host, 0)

        self.assertEqual([slot_name], host.preset_manager.loaded_names)
        self.assertEqual([], host.preset_manager.applied_payloads)


if __name__ == "__main__":
    unittest.main()
