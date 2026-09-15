# -*- coding: utf-8 -*-
import unittest

from calendar_app.presentation.widgets import overlay_preset_service as service
from calendar_app.presentation.widgets import overlay_preset_store as store


class _FakeSettings:
    def __init__(self):
        self._values = {}

    def value(self, key, default=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value


class OverlayPresetServiceTests(unittest.TestCase):
    def test_upsert_add_and_duplicate_guard(self):
        s = _FakeSettings()
        prefix = "svc_a"

        created = service.upsert_user_preset_entry(s, prefix, "A", "t1", allow_overwrite=False)
        self.assertTrue(created)

        duplicate = service.upsert_user_preset_entry(s, prefix, "A", "t2", allow_overwrite=False)
        self.assertFalse(duplicate)

        overwritten = service.upsert_user_preset_entry(s, prefix, "A", "t3", allow_overwrite=True)
        self.assertTrue(overwritten)

    def test_remove_user_preset_entry(self):
        s = _FakeSettings()
        prefix = "svc_b"
        service.upsert_user_preset_entry(s, prefix, "A", "x", allow_overwrite=False)
        service.upsert_user_preset_entry(s, prefix, "B", "y", allow_overwrite=False)
        service.remove_user_preset_entry(s, prefix, "A")
        self.assertFalse(service.has_name_conflict(s, prefix, "A", set()))
        self.assertTrue(service.has_name_conflict(s, prefix, "B", set()))

    def test_has_name_conflict_checks_builtin_and_user(self):
        s = _FakeSettings()
        prefix = "svc_c"
        service.upsert_user_preset_entry(s, prefix, "U", "u", allow_overwrite=False)
        self.assertTrue(service.has_name_conflict(s, prefix, "U", set()))
        self.assertTrue(service.has_name_conflict(s, prefix, "B", {"B"}))
        self.assertFalse(service.has_name_conflict(s, prefix, "X", {"B"}))

    def test_rename_and_delete_policy_reject_builtin_presets(self):
        s = _FakeSettings()
        prefix = "svc_d"
        renamed = service.apply_rename_preset_policy(
            s,
            prefix,
            old_name="B1",
            new_name="N1",
            built_in_names={"B1"},
            fallback_template="fb",
        )
        deleted = service.apply_delete_preset_policy(
            s,
            prefix,
            name="B1",
            kind="builtin",
            built_in_names={"B1"},
        )
        self.assertFalse(renamed)
        self.assertFalse(deleted)
        self.assertFalse(service.has_name_conflict(s, prefix, "N1", set()))
        self.assertEqual(store.load_hidden_builtins(s, prefix), set())

    def test_apply_delete_preset_policy_builtin_vs_user_kind(self):
        s = _FakeSettings()
        prefix = "svc_e"
        service.upsert_user_preset_entry(s, prefix, "U1", "custom", allow_overwrite=False)

        deleted = service.apply_delete_preset_policy(
            s,
            prefix,
            name="U1",
            kind="user",
            built_in_names={"B1"},
        )
        self.assertTrue(deleted)
        self.assertFalse(service.has_name_conflict(s, prefix, "U1", set()))
        self.assertEqual(store.load_hidden_builtins(s, prefix), set())

        service.upsert_user_preset_entry(s, prefix, "B1", "override", allow_overwrite=False)
        deleted_builtin = service.apply_delete_preset_policy(
            s,
            prefix,
            name="B1",
            kind="builtin",
            built_in_names={"B1"},
        )
        self.assertFalse(deleted_builtin)
        self.assertTrue(service.has_name_conflict(s, prefix, "B1", set()))
        self.assertEqual(store.load_hidden_builtins(s, prefix), set())

    def test_restore_fixed_builtins_preserves_override_as_user_copy(self):
        s = _FakeSettings()
        prefix = "svc_f"
        service.upsert_user_preset_entry(s, prefix, "B1", "override", allow_overwrite=False)
        store.save_hidden_builtins(s, prefix, {"B1"})

        presets = service.restore_fixed_builtin_presets(
            s,
            prefix,
            {"B1"},
            copy_suffix="(User copy)",
        )

        self.assertEqual(presets, [{"name": "B1 (User copy)", "template": "override"}])
        self.assertEqual(store.load_hidden_builtins(s, prefix), set())


if __name__ == "__main__":
    unittest.main()
