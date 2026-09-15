# -*- coding: utf-8 -*-
import unittest

from calendar_app.presentation.widgets import overlay_preset_logic as logic


class OverlayPresetLogicTests(unittest.TestCase):
    def test_normalize_built_in_presets_filters_blank_names(self):
        cleaned, names = logic.normalize_built_in_presets(
            [
                (" A ", "ta"),
                ("", "drop"),
                ("B", ""),
                (" C ", "tc"),
            ]
        )
        self.assertEqual(cleaned, [("A", "ta"), ("B", ""), ("C", "tc")])
        self.assertEqual(names, {"A", "C"})

    def test_build_effective_entries_keeps_builtins_fixed_and_visible(self):
        entries = logic.build_effective_entries(
            [("A", "ta"), ("B", "tb"), ("C", "tc")],
            [
                {"name": "A", "template": "ua"},
                {"name": "X", "template": "ux"},
            ],
            {"B"},
        )
        self.assertEqual(
            entries,
            [
                {"name": "A", "template": "ta", "kind": "builtin"},
                {"name": "B", "template": "tb", "kind": "builtin"},
                {"name": "C", "template": "tc", "kind": "builtin"},
                {"name": "X", "template": "ux", "kind": "user"},
            ],
        )

    def test_upsert_user_preset_rejects_duplicate_without_overwrite(self):
        updated, saved = logic.upsert_user_preset(
            [{"name": "A", "template": "old"}],
            "A",
            "new",
            allow_overwrite=False,
        )
        self.assertFalse(saved)
        self.assertEqual(updated, [{"name": "A", "template": "old"}])

    def test_upsert_user_preset_updates_first_matching_entry(self):
        updated, saved = logic.upsert_user_preset(
            [
                {"name": "A", "template": "old-1"},
                {"name": "A", "template": "old-2"},
            ],
            "A",
            "new",
            allow_overwrite=True,
        )
        self.assertTrue(saved)
        self.assertEqual(updated[0], {"name": "A", "template": "new"})
        self.assertEqual(updated[1], {"name": "A", "template": "old-2"})

    def test_rename_user_preset_appends_when_old_name_missing(self):
        updated, renamed = logic.rename_user_preset(
            [{"name": "X", "template": "tx"}],
            "A",
            "B",
            fallback_template="fallback",
        )
        self.assertFalse(renamed)
        self.assertEqual(
            updated,
            [
                {"name": "X", "template": "tx"},
                {"name": "B", "template": "fallback"},
            ],
        )

    def test_remove_user_preset_deletes_all_matching_names(self):
        updated = logic.remove_user_preset(
            [
                {"name": "A", "template": "1"},
                {"name": "B", "template": "2"},
                {"name": "A", "template": "3"},
            ],
            "A",
        )
        self.assertEqual(updated, [{"name": "B", "template": "2"}])

    def test_build_row_entries_keeps_builtin_then_user_order(self):
        entries = logic.build_row_entries(
            [("B1", "t1"), ("B2", "t2")],
            [
                {"name": "B1", "template": "override"},
                {"name": "U1", "template": "u1"},
                {"name": "", "template": "drop"},
            ],
        )
        self.assertEqual(
            entries,
            [
                {"name": "B1", "template": "t1", "kind": "builtin"},
                {"name": "B2", "template": "t2", "kind": "builtin"},
                {"name": "U1", "template": "u1", "kind": "user"},
            ],
        )

    def test_find_selection_index_matches_name_and_kind(self):
        entries = [
            {"name": "", "kind": "placeholder"},
            {"name": "A", "kind": "builtin"},
            {"name": "A", "kind": "user"},
        ]
        idx = logic.find_selection_index(entries, "A", "user", start_index=1, default_index=0)
        self.assertEqual(idx, 2)

    def test_find_selection_index_returns_default_when_missing(self):
        entries = [{"name": "A", "kind": "builtin"}]
        idx = logic.find_selection_index(entries, "X", None, start_index=0, default_index=7)
        self.assertEqual(idx, 7)

    def test_is_name_conflict_checks_builtin_and_user(self):
        user_presets = [{"name": "U1", "template": "t"}]
        self.assertTrue(logic.is_name_conflict("B1", {"B1"}, user_presets))
        self.assertTrue(logic.is_name_conflict("U1", {"B1"}, user_presets))
        self.assertFalse(logic.is_name_conflict("Z", {"B1"}, user_presets))

    def test_legacy_builtin_override_is_migrated_to_unique_user_copy(self):
        presets, changed = logic.migrate_builtin_name_conflicts(
            user_presets=[
                {"name": "B1", "template": "override"},
                {"name": "B1 (User copy)", "template": "existing"},
            ],
            built_in_names={"B1"},
            copy_suffix="(User copy)",
        )
        self.assertTrue(changed)
        self.assertEqual(
            presets,
            [
                {"name": "B1 (User copy) 2", "template": "override"},
                {"name": "B1 (User copy)", "template": "existing"},
            ],
        )

    def test_row_button_states_follow_current_kind_and_count(self):
        self.assertEqual(
            logic.row_button_states(current_kind="builtin", item_count=0),
            {"apply": False, "update": False, "delete": False},
        )
        self.assertEqual(
            logic.row_button_states(current_kind="user", item_count=1),
            {"apply": True, "update": True, "delete": True},
        )

    def test_manager_button_states_reflect_selection_template_and_dirty(self):
        self.assertEqual(
            logic.manager_button_states(
                has_selection=False,
                current_kind="placeholder",
                editor_text="x",
                current_template="x",
            ),
            {"add": True, "update": False, "rename": False, "delete": False},
        )
        self.assertEqual(
            logic.manager_button_states(
                has_selection=True,
                current_kind="builtin",
                editor_text="x",
                current_template="y",
            ),
            {"add": True, "update": False, "rename": False, "delete": False},
        )
        self.assertEqual(
            logic.manager_button_states(
                has_selection=True,
                current_kind="user",
                editor_text="x",
                current_template="y",
            ),
            {"add": True, "update": True, "rename": True, "delete": True},
        )
        self.assertEqual(
            logic.manager_button_states(
                has_selection=True,
                current_kind="user",
                editor_text="   ",
                current_template="",
            ),
            {"add": False, "update": False, "rename": True, "delete": True},
        )


if __name__ == "__main__":
    unittest.main()
