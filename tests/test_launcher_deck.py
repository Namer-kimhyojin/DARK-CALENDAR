# -*- coding: utf-8 -*-
"""KeyDeck v4 data model and switch physics."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.physics import (
    EVENT_BOTTOM,
    EVENT_BUMP,
    EVENT_CLICK,
    EVENT_CLICK_UP,
    EVENT_TOP,
    LATCH_DEPTH,
    SWITCH_PROFILES,
    KeySpring,
    TiltSpring,
    switch_profile,
)


def _cells(keys):
    return [m.key_box(key) for key in keys]


class KeyDeckTemplateTests(unittest.TestCase):
    def test_every_template_and_theme_builds_a_valid_overlap_free_deck(self):
        self.assertEqual(len(m.TEMPLATES), 10)
        self.assertEqual(len(m.THEMES), 7)
        for template_id, *_rest in m.TEMPLATES:
            for theme in m.THEMES:
                deck = m.build_template_deck(template_id, theme.theme_id)
                keys = deck["pages"][0]["keys"]
                self.assertTrue(keys, template_id)
                self.assertFalse(m.has_overlaps(keys), (template_id, theme.theme_id))
                self.assertEqual(deck["theme"], theme.theme_id)
                self.assertEqual(m.layout_bounds(keys)[:2], (0.0, 0.0))
                if theme.insert_kind != "none" and template_id not in m.KEYBOARD_TEMPLATE_IDS:
                    self.assertTrue(all(key["insert"]["kind"] == theme.insert_kind for key in keys))

    def test_templates_mix_key_sizes_like_real_keyboards(self):
        widths = set()
        for template_id, *_rest in m.TEMPLATES:
            for key in m.template_keys(template_id):
                widths.add((key["w"], key["h"]))
        self.assertIn((1.5, 1.0), widths)
        self.assertIn((2.25, 1.0), widths)
        self.assertIn((1.0, 2.0), widths)

    def test_theme_keeps_user_images_but_restyles_caps(self):
        deck = m.build_template_deck("macro_3x3", "crystal_night")
        key = deck["pages"][0]["keys"][0]
        key["insert"].update({"kind": "image", "path": "C:/art/me.png"})
        m.apply_theme(deck, "walnut_studio")
        self.assertEqual(key["insert"]["kind"], "image")
        self.assertEqual(key["cap"]["material"], "solid")
        self.assertEqual(deck["case"]["style"], "walnut")

    def test_theme_can_target_selected_keys_only(self):
        deck = m.build_template_deck("macro_3x3", "crystal_night")
        keys = deck["pages"][0]["keys"]
        m.apply_theme(deck, "smoke_neon", page_index=0, key_ids={keys[0]["id"]})
        self.assertEqual(keys[0]["cap"]["material"], "smoke")
        self.assertEqual(keys[1]["cap"]["material"], "crystal")
        self.assertEqual(deck["case"]["style"], "anodized")

    def test_template_on_custom_deck_inherits_the_page_look(self):
        deck = m.build_template_deck("macro_3x3", "crystal_night")
        deck["theme"] = m.CUSTOM_THEME_ID
        deck["pages"][0]["keys"][0]["cap"]["color"] = "#123456"
        m.apply_template_to_page(deck, 0, "command_bar")
        keys = deck["pages"][0]["keys"]
        self.assertEqual(len(keys), 6)
        self.assertTrue(all(key["cap"]["color"] == "#123456" for key in keys))


class KeyDeckNormalizationTests(unittest.TestCase):
    def test_json_round_trip_preserves_korean_and_quarter_units(self):
        deck = m.build_template_deck("command_bar")
        deck["pages"][0]["keys"][0]["label"] = "한글 키"
        restored = m.deck_from_json(m.deck_to_json(deck))
        self.assertEqual(restored["pages"][0]["keys"][0]["label"], "한글 키")
        self.assertEqual(restored["pages"][0]["keys"][3]["w"], 2.25)
        self.assertEqual(restored, m.normalize_deck(restored))

    def test_invalid_values_are_clamped_and_replaced(self):
        raw = {
            "version": 4,
            "unit": 999,
            "gap": -4,
            "scale": 5,
            "case": {"style": "gold", "color": "red", "accent": "#12345"},
            "pages": [
                {
                    "id": "p1",
                    "keys": [
                        {
                            "id": "a",
                            "x": -3,
                            "y": 0.13,
                            "w": 99,
                            "h": 0.1,
                            "label": "x" * 200,
                            "action": {"type": "command", "target": "format_c"},
                            "mode": "tap",
                            "active": True,
                            "insert": {
                                "kind": "hologram",
                                "zoom": 9999,
                                "rotate": 100,
                                "pattern": "?",
                            },
                            "legend": {"glyph": "unknown", "size": 1},
                            "cap": {"material": "gold", "color": "#zzzzzz"},
                            "switch": "optical",
                            "sound": "boom",
                        },
                        {"id": "a", "x": 8, "y": 0},
                    ],
                }
            ],
        }
        deck = m.normalize_deck(raw)
        first, second = deck["pages"][0]["keys"]
        self.assertEqual((deck["unit"], deck["gap"], deck["scale"]), (112, 2, 60))
        self.assertEqual(deck["case"]["style"], "anodized")
        self.assertEqual(deck["case"]["color"], m.default_case()["color"])
        self.assertEqual(first["w"], m.MAX_KEY_W)
        self.assertEqual(first["h"], m.MIN_KEY_U)
        self.assertEqual(first["x"], 0.0)
        self.assertEqual(first["y"], 0.25)
        self.assertEqual(len(first["label"]), 48)
        self.assertEqual(first["action"]["target"], "")
        self.assertFalse(first["active"])
        self.assertEqual(first["insert"]["kind"], "none")
        self.assertEqual(first["insert"]["zoom"], 400)
        self.assertEqual(first["insert"]["rotate"], 90)
        self.assertEqual(first["insert"]["pattern"], "spark")
        self.assertEqual(first["legend"]["glyph"], "auto")
        self.assertEqual(first["legend"]["size"], 60)
        self.assertEqual(first["cap"]["material"], "crystal")
        self.assertEqual(first["switch"], "tactile")
        self.assertEqual(first["sound"], "auto")
        self.assertNotEqual(second["id"], "a")
        self.assertFalse(m.has_overlaps(deck["pages"][0]["keys"]))

    def test_page_targets_are_validated_against_existing_pages(self):
        deck = m.build_template_deck("macro_3x3")
        second = m.new_page("Two")
        deck["pages"].append(second)
        keys = deck["pages"][0]["keys"]
        keys[0]["action"] = {"type": "page", "target": second["id"], "paste": False}
        keys[1]["action"] = {"type": "page", "target": "ghost", "paste": False}
        deck = m.normalize_deck(deck)
        keys = deck["pages"][0]["keys"]
        self.assertEqual(keys[0]["action"]["target"], second["id"])
        self.assertEqual(keys[1]["action"]["target"], "next")
        deck["page"] = 0
        self.assertEqual(m.resolve_page_target(deck, second["id"]), 1)
        self.assertEqual(m.resolve_page_target(deck, "prev"), 1)

    def test_broken_json_falls_back_to_default_template(self):
        deck = m.deck_from_json("{not json")
        self.assertEqual(len(deck["pages"][0]["keys"]), len(m.template_keys(m.DEFAULT_TEMPLATE_ID)))

    def test_v3_decks_migrate_to_pages_without_losing_content(self):
        legacy = {
            "version": 3,
            "columns": 4,
            "rows": 2,
            "gap": 9,
            "icon_pack": "neon_cyan",
            "mosaic_enabled": False,
            "keys": [
                {
                    "id": "k1",
                    "label": "업무",
                    "row": 0,
                    "column": 0,
                    "width": 2,
                    "height": 1,
                    "style": "mechanical_pbt",
                    "action_type": "internal",
                    "target": "new_task",
                    "asset_path": "C:/art/work.png",
                    "icon": "star",
                    "label_layout": "icon_only",
                },
                {
                    "id": "k2",
                    "label": "토글",
                    "row": 0,
                    "column": 2,
                    "width": 1,
                    "height": 2,
                    "style": "arcade_glow",
                    "action_type": "open",
                    "target": "C:/Tools/app.exe",
                    "interaction_mode": "toggle",
                    "active": True,
                    "asset_id": "orbit",
                    "sound_profile": "custom",
                    "sound_path": "C:/s.wav",
                    "custom_top": "#aabbccff",
                },
            ],
        }
        deck = m.normalize_deck(legacy)
        self.assertEqual(deck["version"], 4)
        self.assertEqual(deck["gap"], 9)
        first, second = deck["pages"][0]["keys"]
        self.assertEqual((first["x"], first["y"], first["w"], first["h"]), (0.0, 0.0, 2.0, 1.0))
        self.assertEqual(first["action"], {"type": "command", "target": "new_task", "paste": False})
        self.assertEqual(first["insert"]["kind"], "image")
        self.assertEqual(first["insert"]["path"], "C:/art/work.png")
        self.assertEqual(first["cap"]["material"], "solid")
        self.assertEqual(first["legend"]["glyph"], "star")
        self.assertEqual(first["legend"]["layout"], "glyph")
        self.assertEqual(second["action"]["type"], "app")
        self.assertEqual(second["mode"], "toggle")
        self.assertTrue(second["active"])
        self.assertEqual(second["insert"]["kind"], "pattern")
        self.assertEqual(second["insert"]["pattern"], "orbit")
        self.assertEqual(second["cap"]["color"], "#aabbcc")
        self.assertEqual((second["sound"], second["sound_path"]), ("custom", "C:/s.wav"))

    def test_v3_mosaic_becomes_deck_panorama(self):
        legacy = {
            "mosaic_enabled": True,
            "mosaic_path": "C:/art/wide.png",
            "keys": [{"id": "a", "row": 0, "column": 0}, {"id": "b", "row": 0, "column": 1}],
        }
        deck = m.normalize_deck(legacy)
        self.assertEqual(deck["panorama"]["path"], "C:/art/wide.png")
        self.assertEqual(deck["panorama"]["name"], "wide.png")
        self.assertTrue(
            all(key["insert"]["kind"] == "panorama" for key in deck["pages"][0]["keys"])
        )


class KeyDeckLayoutTests(unittest.TestCase):
    def _key(self, x, y, w=1.0, h=1.0):
        key = m.default_key()
        key.update({"x": x, "y": y, "w": w, "h": h})
        return key

    def test_find_free_slot_fills_rows_then_nearest_position(self):
        keys = [self._key(0, 0), self._key(1, 0)]
        self.assertEqual(m.find_free_slot(keys, 1.0, 1.0, columns=2), (0.0, 1.0))
        self.assertEqual(m.find_free_slot(keys, 1.0, 1.0, columns=4), (2.0, 0.0))
        self.assertEqual(m.find_free_slot(keys, 1.0, 1.0, columns=4, near=(1.2, 1.1)), (1.25, 1.0))

    def test_settle_layout_pushes_overlapped_keys_but_keeps_anchor(self):
        anchor = self._key(0, 0, 2.0)
        displaced = self._key(1, 0)
        keys = [anchor, displaced, self._key(2, 0)]
        m.settle_layout(keys, {anchor["id"]})
        self.assertEqual((anchor["x"], anchor["y"]), (0.0, 0.0))
        self.assertFalse(m.has_overlaps(keys))

    def test_normalize_origin_and_reflow(self):
        keys = [self._key(1.5, 2.0), self._key(2.5, 2.0, 2.0)]
        m.normalize_origin(keys)
        self.assertEqual(m.layout_bounds(keys)[:2], (0.0, 0.0))
        m.reflow_keys(keys, 2.0)
        self.assertEqual([(key["x"], key["y"]) for key in keys], [(0.0, 0.0), (0.0, 1.0)])

    def test_snap_uses_quarter_units(self):
        self.assertEqual(m.snap_u(1.13), 1.25)
        self.assertEqual(m.snap_u(0.87), 0.75)


class KeyDeckKeyHelperTests(unittest.TestCase):
    def test_style_copy_paste_keeps_the_target_glyph(self):
        source = m.default_key()
        source["cap"]["material"] = "pudding"
        source["legend"].update({"glyph": "star", "color": "#ff0000"})
        target = m.default_key()
        target["legend"]["glyph"] = "copy"
        m.paste_key_style(target, m.copy_key_style(source))
        self.assertEqual(target["cap"]["material"], "pudding")
        self.assertEqual(target["legend"]["color"], "#ff0000")
        self.assertEqual(target["legend"]["glyph"], "copy")

    def test_inherit_style_never_copies_personal_images(self):
        reference = m.default_key()
        reference["insert"].update({"kind": "image", "path": "C:/me.png"})
        child = m.inherit_style(m.make_key("New"), reference)
        self.assertEqual(child["insert"]["kind"], "gradient")
        self.assertEqual(child["insert"]["path"], "")

    def test_auto_glyph_describes_the_action(self):
        self.assertEqual(m.auto_glyph({"type": "hotkey", "target": "Ctrl+C"}), "copy")
        self.assertEqual(m.auto_glyph({"type": "hotkey", "target": "volumemute"}), "volume_mute")
        self.assertEqual(m.auto_glyph({"type": "command", "target": "today"}), "calendar")
        self.assertEqual(m.auto_glyph({"type": "url", "target": "https://a"}), "globe")
        self.assertEqual(m.auto_glyph({"type": "none", "target": ""}), "none")

    def test_duplicate_key_gets_new_id_and_is_not_active(self):
        key = m.default_key()
        key.update({"mode": "toggle", "active": True})
        copy = m.duplicate_key(key)
        self.assertNotEqual(copy["id"], key["id"])
        self.assertFalse(copy["active"])

    def test_shade_lightens_and_darkens(self):
        self.assertEqual(m.shade("#808080", 0.5), "#404040")
        self.assertEqual(m.shade("#000000", 2.0), "#ffffff")


class KeySpringTests(unittest.TestCase):
    def _run(self, spring, seconds, dt=1 / 240):
        events = []
        elapsed = 0.0
        while elapsed < seconds:
            events.extend((event, round(elapsed, 3)) for event in spring.step(dt))
            elapsed += dt
        return events

    def test_finger_press_bottoms_out_like_a_real_switch(self):
        for switch_id in SWITCH_PROFILES:
            spring = KeySpring(switch_profile(switch_id))
            spring.press()
            events = self._run(spring, 0.06)
            self.assertEqual(spring.position, 1.0, switch_id)
            bottom = [at for event, at in events if event == EVENT_BOTTOM]
            self.assertEqual(len(bottom), 1, switch_id)
            self.assertLessEqual(bottom[0], 0.04, switch_id)
            self.assertGreater(spring.impact, 10.0, switch_id)

    def test_release_stops_at_the_top_housing_and_settles(self):
        for switch_id in SWITCH_PROFILES:
            spring = KeySpring(switch_profile(switch_id))
            spring.press()
            self._run(spring, 0.08)
            spring.set_target(0.0)
            lowest = 1.0
            events = []
            for _ in range(120):
                events.extend(spring.step(1 / 240))
                lowest = min(lowest, spring.position)
            self.assertGreaterEqual(lowest, 0.0, switch_id)
            self.assertIn(EVENT_TOP, events, switch_id)
            self._run(spring, 0.5)
            self.assertTrue(spring.settled, switch_id)
            self.assertEqual(spring.position, 0.0)

    def test_switch_specific_events(self):
        clicky = KeySpring(switch_profile("clicky"))
        clicky.press()
        down = [event for event, _at in self._run(clicky, 0.1)]
        clicky.set_target(0.0)
        up = [event for event, _at in self._run(clicky, 0.3)]
        self.assertEqual(down.count(EVENT_CLICK), 1)
        self.assertLess(down.index(EVENT_CLICK), down.index(EVENT_BOTTOM))
        self.assertEqual(up.count(EVENT_CLICK_UP), 1)
        tactile = KeySpring(switch_profile("tactile"))
        tactile.press()
        self.assertIn(EVENT_BUMP, [event for event, _at in self._run(tactile, 0.1)])
        linear = KeySpring(switch_profile("linear"))
        linear.press()
        linear_events = [event for event, _at in self._run(linear, 0.1)]
        self.assertNotIn(EVENT_BUMP, linear_events)
        self.assertNotIn(EVENT_CLICK, linear_events)

    def test_latched_toggle_rests_half_way_without_bottom_event(self):
        spring = KeySpring(switch_profile("tactile"))
        spring.set_target(LATCH_DEPTH)
        events = [event for event, _at in self._run(spring, 0.5)]
        self.assertAlmostEqual(spring.position, LATCH_DEPTH)
        self.assertNotIn(EVENT_BOTTOM, events)

    def test_snap_jumps_without_motion(self):
        spring = KeySpring(switch_profile("tactile"))
        spring.snap(LATCH_DEPTH)
        self.assertTrue(spring.settled)
        self.assertEqual(spring.position, LATCH_DEPTH)

    def test_tilt_wobbles_back_after_an_off_center_press(self):
        tilt = TiltSpring()
        tilt.set_target(0.6, -0.3)
        for _ in range(12):
            tilt.step(1 / 60)
        self.assertGreater(tilt.x, 0.4)
        tilt.set_target(0.0, 0.0)
        samples = []
        for _ in range(90):
            tilt.step(1 / 60)
            samples.append(tilt.x)
        self.assertLess(min(samples), -0.05)
        self.assertTrue(tilt.settled)


class KeyDeckToggleAndProfileTests(unittest.TestCase):
    def test_toggle_indicator_defaults_and_travels_with_the_style(self):
        key = m.normalize_key({"mode": "toggle", "indicator": "bogus"})
        self.assertEqual(key["indicator"], "switch")
        key["indicator"] = "ring"
        other = m.make_key("b")
        m.paste_key_style(other, m.copy_key_style(key))
        self.assertEqual(other["indicator"], "ring")

    def test_every_profile_survives_normalization(self):
        for profile_id, *_ in m.PROFILES:
            key = m.normalize_key({"cap": {"profile": profile_id}})
            self.assertEqual(key["cap"]["profile"], profile_id)
        self.assertGreaterEqual(len(m.PROFILES), 8)


class KeyDeckPanoramaTests(unittest.TestCase):
    def test_normalize_panorama_fills_defaults_and_clamps(self):
        self.assertEqual(m.normalize_panorama(None), m.default_panorama())
        data = m.normalize_panorama(
            {
                "path": " C:/a.png ",
                "name": "a.png",
                "fit": "stretch",
                "x": 500,
                "y": -3.4,
                "zoom": 20,
            }
        )
        self.assertEqual(
            data,
            {"path": "C:/a.png", "name": "a.png", "fit": "cover", "x": 100, "y": -3, "zoom": 100},
        )
        self.assertEqual(m.normalize_panorama({"name": "orphan.png"})["name"], "")
        deck = m.normalize_deck({"panorama": {"path": "C:/b.png"}})
        self.assertEqual(deck["panorama"]["fit"], "cover")
        self.assertEqual(deck["panorama"]["zoom"], 100)

    def test_panorama_rect_cover_contain_zoom_and_alignment(self):
        area = (10.0, 20.0, 300.0, 100.0)
        cover = m.panorama_rect(area, (200, 200), m.default_panorama())
        self.assertEqual(cover, (10.0, -80.0, 300.0, 300.0))
        contain = m.panorama_rect(area, (200, 200), {**m.default_panorama(), "fit": "contain"})
        self.assertEqual(contain, (110.0, 20.0, 100.0, 100.0))
        zoomed = m.panorama_rect(area, (300, 100), {**m.default_panorama(), "zoom": 200})
        self.assertEqual(zoomed[2:], (600.0, 200.0))
        left_edge = m.panorama_rect(area, (600, 100), {**m.default_panorama(), "x": -100})
        right_edge = m.panorama_rect(area, (600, 100), {**m.default_panorama(), "x": 100})
        self.assertEqual(left_edge[0], 10.0)
        self.assertAlmostEqual(right_edge[0] + right_edge[2], 310.0)

    def test_panorama_align_round_trips_and_reports_fixed_axes(self):
        area = (0.0, 0.0, 300.0, 100.0)
        for x in (-100, -40, 0, 65, 100):
            left, _top, width, _height = m.panorama_rect(
                area, (600, 100), {**m.default_panorama(), "x": x}
            )
            self.assertEqual(m.panorama_align_for(300.0, width, left), x)
        self.assertIsNone(m.panorama_align_for(100.0, 100.0, 0.0))

    def test_suggested_fit_fills_with_photos_and_keeps_logos_whole(self):
        self.assertEqual(m.suggest_panorama_fit((3200, 1792), (3, 3)), "cover")
        self.assertEqual(m.suggest_panorama_fit((3200, 1792), (6, 1)), "cover")
        self.assertEqual(m.suggest_panorama_fit((315, 81), (3, 3), transparent=True), "contain")
        self.assertEqual(m.suggest_panorama_fit((400, 300), (4, 3), transparent=True), "cover")

    def test_panorama_keys_per_page_and_deck(self):
        deck = m.build_template_deck("macro_3x3")
        deck["pages"].append(m.new_page("2"))
        deck["pages"][1]["keys"] = [m.make_key(0, 0)]
        deck["pages"][0]["keys"][0]["insert"]["kind"] = "panorama"
        deck["pages"][1]["keys"][0]["insert"]["kind"] = "panorama"
        self.assertEqual(len(m.panorama_keys(deck, 0)), 1)
        self.assertEqual(len(m.panorama_keys(deck)), 2)


class KeyboardTemplateTests(unittest.TestCase):
    SPECS = {"keyboard_full": (104, 22.5), "keyboard_tkl": (87, 18.25), "keyboard_60": (61, 15.0)}

    def test_keyboard_layouts_have_standard_key_counts_and_widths(self):
        for template_id, (count, width) in self.SPECS.items():
            with self.subTest(template=template_id):
                keys = m.build_template_deck(template_id)["pages"][0]["keys"]
                self.assertEqual(len(keys), count)
                self.assertEqual(m.layout_bounds(keys)[2], width)
                self.assertFalse(m.has_overlaps(keys))
                self.assertLessEqual(len(keys), m.MAX_KEYS_PER_PAGE)

    def test_every_keyboard_key_sends_a_valid_key(self):
        from calendar_app.infrastructure.runtime.hotkey_sender import parse_hotkey

        for template_id in self.SPECS:
            for key in m.template_keys(template_id):
                with self.subTest(template=template_id, key=key["label"]):
                    self.assertEqual(key["action"]["type"], "hotkey")
                    self.assertTrue(parse_hotkey(key["action"]["target"]))

    def test_modifiers_are_sticky_toggles_and_letters_carry_hangul(self):
        keys = m.template_keys("keyboard_60")
        modifiers = [key for key in keys if m.modifier_name(key)]
        self.assertEqual(
            sorted(m.modifier_name(key) for key in modifiers),
            sorted(["Shift", "Shift", "Ctrl", "Alt", "Win", "Win"]),
        )
        self.assertTrue(all(key["mode"] == "toggle" for key in modifiers))
        by_label = {key["label"]: key for key in keys}
        self.assertEqual(by_label["Q"]["sublabel"], "ㅂ")
        self.assertEqual(by_label["M"]["sublabel"], "ㅡ")
        self.assertEqual(by_label["Esc"]["action"]["target"], "Esc")
        self.assertIn("Hangul", {key["action"]["target"] for key in keys})

    def test_themes_keep_keyboards_as_plain_printed_keycaps(self):
        for theme in m.THEMES:
            keys = m.build_template_deck("keyboard_tkl", theme.theme_id)["pages"][0]["keys"]
            self.assertTrue(all(key["insert"]["kind"] == "none" for key in keys))
            self.assertTrue(all(key["legend"]["glyph"] == "none" for key in keys))
        deck = m.build_template_deck("macro_3x3")
        deck["theme"] = m.CUSTOM_THEME_ID
        m.apply_template_to_page(deck, 0, "keyboard_60")
        keys = deck["pages"][0]["keys"]
        self.assertEqual(len(keys), 61)
        self.assertTrue(all(key["legend"]["layout"] == "corner" for key in keys))

    def test_combine_hotkey_prefixes_modifiers_once(self):
        self.assertEqual(m.combine_hotkey(["Shift", "Ctrl"], "A"), "Shift+Ctrl+A")
        self.assertEqual(m.combine_hotkey(["Control"], "Ctrl+C"), "Ctrl+C")
        tap = m.make_key("x", "hotkey", "Shift")
        self.assertEqual(m.modifier_name(tap), "")
        tap["mode"] = "toggle"
        self.assertEqual(m.modifier_name(tap), "Shift")


if __name__ == "__main__":
    unittest.main()
