# -*- coding: utf-8 -*-
"""KeyDeck renderer geometry/caches and the runtime canvas."""

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas, action_summary
from calendar_app.presentation.widgets.keydeck.physics import LATCH_DEPTH
from calendar_app.presentation.widgets.keydeck.renderer import (
    DeckGeometry,
    KeyDeckRenderer,
    KeyVisualState,
    fit_scale,
    render_deck_thumbnail,
)


class _AppCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])


class DeckGeometryTests(_AppCase):
    def test_keys_sit_inside_the_plate_and_hit_testing_matches(self):
        deck = m.build_template_deck("numpad")
        geometry = DeckGeometry(deck, scale=1.0)
        plate = geometry.plate_rect
        for key in geometry.keys:
            rect = geometry.key_rect(key)
            self.assertTrue(plate.contains(rect), key["label"])
            self.assertIs(geometry.hit_key(rect.center()), key)
        self.assertIsNone(geometry.hit_key(QPointF(1, 1)))
        self.assertEqual(geometry.size().width(), geometry.width)

    def test_scale_changes_every_dimension_proportionally(self):
        deck = m.build_template_deck("macro_3x3")
        small = DeckGeometry(deck, scale=1.0)
        large = DeckGeometry(deck, scale=2.0)
        self.assertAlmostEqual(large.unit, small.unit * 2)
        self.assertGreater(large.width, small.width * 1.9)

    def test_header_exposes_gear_and_one_dot_per_page(self):
        deck = m.build_template_deck("macro_3x3")
        deck["pages"].append(m.new_page("B"))
        deck["pages"].append(m.new_page("C"))
        geometry = DeckGeometry(deck, scale=1.0)
        self.assertEqual(len(geometry.dot_rects), 3)
        self.assertTrue(geometry.case_rect.contains(geometry.gear_rect))
        without_header = DeckGeometry(deck, scale=1.0, header=False)
        self.assertEqual(without_header.header_h, 0.0)
        self.assertLess(without_header.height, geometry.height)

    def test_floating_case_has_no_bezel(self):
        deck = m.build_template_deck("macro_3x3", "floating_glass")
        geometry = DeckGeometry(deck, scale=1.0)
        self.assertEqual(geometry.bezel, 0.0)

    def test_fit_scale_fits_the_box(self):
        deck = m.build_template_deck("stream_5x3")
        scale = fit_scale(deck, 0, 300, 200)
        geometry = DeckGeometry(deck, scale=scale)
        self.assertLessEqual(geometry.width, 302)
        self.assertLessEqual(geometry.height, 202)

    def test_pressing_moves_the_cap_top_down_by_travel(self):
        deck = m.build_template_deck("macro_3x3")
        geometry = DeckGeometry(deck, scale=1.0)
        metrics = geometry.cap_metrics(geometry.keys[0])
        self.assertGreater(metrics.travel_px, 1.0)
        self.assertLess(metrics.top.bottom(), metrics.base.bottom())


class RendererTests(_AppCase):
    def test_every_theme_and_material_renders(self):
        for theme in m.THEMES:
            deck = m.build_template_deck("creator_mixed", theme.theme_id)
            for material, *_rest in m.MATERIALS:
                for key in deck["pages"][0]["keys"]:
                    key["cap"]["material"] = material
                renderer = KeyDeckRenderer()
                renderer.set_deck(deck, 0, scale=0.8)
                keys = deck["pages"][0]["keys"]
                states = {keys[0]["id"]: KeyVisualState(travel=1.0, led=1.0, hover=True)}
                pixmap = renderer.render_pixmap(states)
                self.assertFalse(pixmap.isNull(), (theme.theme_id, material))

    def test_cap_tops_are_cached_until_invalidated(self):
        deck = m.build_template_deck("macro_3x3")
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=1.0)
        key = deck["pages"][0]["keys"][0]
        metrics = renderer.geometry.cap_metrics(key)
        first = renderer._top_pixmap(key, metrics, 1.0, KeyVisualState())
        second = renderer._top_pixmap(key, metrics, 1.0, KeyVisualState(travel=0.8, hover=True))
        self.assertIs(first, second)
        key["label"] = "바뀜"
        renderer.invalidate({key["id"]})
        third = renderer._top_pixmap(key, metrics, 1.0, KeyVisualState())
        self.assertIsNot(first, third)

    def test_background_is_cached_between_frames(self):
        deck = m.build_template_deck("macro_3x3")
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=1.0)
        first = renderer._background_pixmap(1.0, 0.8)
        self.assertIs(first, renderer._background_pixmap(1.0, 0.8))
        renderer.invalidate_background()
        self.assertIsNot(first, renderer._background_pixmap(1.0, 0.8))

    def test_image_insert_is_drawn_inside_the_clear_cap(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            art = QImage(64, 64, QImage.Format.Format_ARGB32)
            art.fill(QColor("#ff0000"))
            path = os.path.join(tmpdir, "art.png")
            art.save(path)
            deck = m.build_template_deck("macro_3x3")
            key = deck["pages"][0]["keys"][0]
            key["insert"].update({"kind": "image", "path": path})
            key["legend"]["layout"] = "art"
            renderer = KeyDeckRenderer()
            renderer.set_deck(deck, 0, scale=2.0)
            image = renderer.render_pixmap().toImage()
            center = renderer.insert_window(key).center()
            color = image.pixelColor(int(center.x()), int(center.y()))
            self.assertGreater(color.red(), 170)
            self.assertLess(color.green(), 90)

    def test_toggle_keys_show_their_on_off_state(self):
        deck = m.build_template_deck("macro_3x3")
        key = deck["pages"][0]["keys"][0]
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=2.0)
        tap = renderer.render_pixmap().toImage()
        key.update({"mode": "toggle", "indicator": "none"})
        renderer.invalidate()
        self.assertEqual(renderer.render_pixmap().toImage(), tap)
        key["indicator"] = "switch"
        renderer.invalidate()
        off = renderer.render_pixmap().toImage()
        key["active"] = True
        renderer.invalidate()
        on = renderer.render_pixmap().toImage()
        self.assertNotEqual(off, tap)
        self.assertNotEqual(on, off)

    def test_round_profile_is_a_circle_and_low_profile_travels_less(self):
        deck = m.build_template_deck("macro_3x3")
        key = deck["pages"][0]["keys"][0]
        geometry = DeckGeometry(deck, 0, scale=1.0)
        standard = geometry.cap_metrics(key)
        key["cap"]["profile"] = "round"
        metrics = geometry.cap_metrics(key)
        self.assertAlmostEqual(metrics.radius, metrics.base.width() / 2.0)
        self.assertAlmostEqual(metrics.top.width(), metrics.top.height())
        self.assertAlmostEqual(metrics.top_radius, metrics.top.width() / 2.0)
        key["cap"]["profile"] = "low"
        self.assertLess(geometry.cap_metrics(key).travel_px, standard.travel_px)

    def test_empty_page_hint_shrinks_to_fit(self):
        deck = m.normalize_deck({"pages": [{"name": "x", "keys": []}]})
        renderer = KeyDeckRenderer()
        renderer.empty_hint = "아주 긴 안내 문구 " * 8
        renderer.set_deck(deck, 0, scale=1.0)
        self.assertFalse(renderer.render_pixmap().toImage().isNull())

    def test_panorama_source_maps_each_window_to_its_slice(self):
        deck = m.build_template_deck("command_bar")
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=1.0)
        image = QImage(800, 100, QImage.Format.Format_ARGB32)
        keys = deck["pages"][0]["keys"]
        _target, first = renderer._panorama_source(image, renderer.insert_window(keys[0]))
        _target, last = renderer._panorama_source(image, renderer.insert_window(keys[-1]))
        self.assertLess(first.left(), last.left())
        self.assertGreaterEqual(first.left(), -1)
        self.assertLessEqual(last.right(), image.width() + 1)

    def test_studio_edit_margin_does_not_change_the_panorama_crop(self):
        deck = m.build_template_deck("macro_3x3")
        image = QImage(640, 360, QImage.Format.Format_ARGB32)
        live = KeyDeckRenderer()
        live.set_deck(deck, 0, scale=1.0)
        studio = KeyDeckRenderer()
        studio.set_deck(deck, 0, scale=1.0, fixed_origin=True, grid_min=(5.0, 5.0))
        self.assertGreater(studio.geometry.keys_rect.width(), live.geometry.keys_rect.width())
        for key in deck["pages"][0]["keys"]:
            _t1, live_source = live._panorama_source(image, live.insert_window(key))
            _t2, studio_source = studio._panorama_source(image, studio.insert_window(key))
            self.assertAlmostEqual(live_source.left(), studio_source.left(), places=3)
            self.assertAlmostEqual(live_source.top(), studio_source.top(), places=3)
            self.assertAlmostEqual(live_source.width(), studio_source.width(), places=3)

    def test_contain_panorama_leaves_keys_outside_the_picture_untouched(self):
        deck = m.build_template_deck("command_bar")
        deck["panorama"] = {**m.default_panorama(), "path": "x.png", "fit": "contain"}
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=1.0)
        image = QImage(100, 100, QImage.Format.Format_ARGB32)
        keys = deck["pages"][0]["keys"]
        placed = renderer.panorama_rect((image.width(), image.height()))
        self.assertAlmostEqual(placed.center().x(), renderer.geometry.content_rect.center().x())
        self.assertIsNone(renderer._panorama_source(image, renderer.insert_window(keys[0])))
        middle = [key for key in keys if renderer.insert_window(key).intersects(placed)]
        self.assertTrue(middle)
        target, source = renderer._panorama_source(image, renderer.insert_window(middle[0]))
        self.assertTrue(placed.contains(target))
        self.assertGreaterEqual(source.left(), -0.01)
        self.assertLessEqual(source.right(), image.width() + 0.01)

    def test_pressed_or_tilted_tops_are_drawn_in_perspective(self):
        rect = QRectF(0, 0, 60, 50)
        self.assertIsNone(KeyDeckRenderer._top_quad(rect, 0.0, 0.0, 0.0, 6.0))
        quad = KeyDeckRenderer._top_quad(rect, 0.8, 0.0, 1.0, 6.0)
        left_edge = quad[3].y() - quad[0].y()
        right_edge = quad[2].y() - quad[1].y()
        self.assertLess(right_edge, left_edge)
        pressed = KeyDeckRenderer._top_quad(rect, 0.0, 0.0, 1.0, 6.0)
        self.assertLess(pressed[1].x() - pressed[0].x(), rect.width())
        deck = m.build_template_deck("macro_3x3")
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=1.0)
        key = deck["pages"][0]["keys"][0]
        state = KeyVisualState(travel=0.9, tilt_x=0.5, tilt_y=-0.4, hover=True, led=1.0)
        self.assertFalse(renderer.render_pixmap({key["id"]: state}).isNull())

    def test_thumbnail_has_requested_size(self):
        pixmap = render_deck_thumbnail(m.build_template_deck("numpad"), 0, 90, 60)
        self.assertEqual((pixmap.width(), pixmap.height()), (90, 60))

    def test_paint_respects_clip_and_empty_hint(self):
        deck = m.build_template_deck("macro_3x3")
        deck["pages"][0]["keys"] = []
        renderer = KeyDeckRenderer()
        renderer.empty_hint = "empty"
        renderer.set_deck(deck, 0, scale=1.0)
        image = QImage(renderer.geometry.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        renderer.paint(painter, {}, clip=QRectF(0, 0, 10, 10))
        painter.end()
        self.assertFalse(image.isNull())


class CanvasTests(_AppCase):
    def setUp(self):
        super().setUp()
        self.deck = m.build_template_deck("macro_3x3")
        self.canvas = KeyDeckCanvas()
        self.canvas.set_deck(self.deck)
        self.canvas.resize(self.canvas.sizeHint())
        self.canvas.show()
        self._app.processEvents()
        self.canvas._armed_at = 0.0
        self.events = []
        self.canvas.keyActivated.connect(lambda key_id, which: self.events.append((key_id, which)))

    def tearDown(self):
        self.canvas.close()
        super().tearDown()

    def _center(self, key) -> QPoint:
        rect = self.canvas.renderer.geometry.key_rect(key)
        return (rect.center() + self.canvas.content_offset()).toPoint()

    def _wait_idle(self, limit=3.0):
        deadline = time.monotonic() + limit
        while self.canvas._timer.isActive() and time.monotonic() < deadline:
            self._app.processEvents()
            time.sleep(0.01)

    def test_click_presses_the_key_and_emits_tap_on_release(self):
        key = self.deck["pages"][0]["keys"][4]
        QTest.mousePress(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertTrue(self.canvas.is_pressing())
        self.assertEqual(self.canvas._runtime[key["id"]].spring.target, 1.0)
        QTest.mouseRelease(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual(self.events, [(key["id"], "tap")])

    def test_release_outside_cancels(self):
        key = self.deck["pages"][0]["keys"][0]
        QTest.mousePress(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        QTest.mouseMove(self.canvas, QPoint(2, 2))
        QTest.mouseRelease(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(2, 2)
        )
        self.assertEqual(self.events, [])

    def test_hold_action_fires_instead_of_tap(self):
        key = self.deck["pages"][0]["keys"][0]
        key["hold_action"] = {"type": "command", "target": "today", "paste": False}
        self.canvas.refresh()
        QTest.mousePress(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertTrue(self.canvas._hold_timer.isActive())
        self.canvas._on_hold()
        QTest.mouseRelease(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual(self.events, [(key["id"], "hold")])

    def test_disabled_keys_shake_but_never_fire(self):
        key = self.deck["pages"][0]["keys"][0]
        key["enabled"] = False
        self.canvas.refresh()
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual(self.events, [])
        self.assertGreater(self.canvas._runtime[key["id"]].shake_t, 0.0)

    def test_animation_timer_stops_when_everything_is_at_rest(self):
        key = self.deck["pages"][0]["keys"][0]
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.canvas.show_feedback(key["id"], True)
        self.assertTrue(self.canvas._timer.isActive())
        self._wait_idle()
        self.assertFalse(self.canvas._timer.isActive())

    def test_toggle_keys_rest_latched_and_hover_does_not_lift(self):
        key = self.deck["pages"][0]["keys"][0]
        key.update({"mode": "toggle", "active": True})
        self.canvas.sync_key_state(key["id"])
        self.assertEqual(self.canvas._runtime[key["id"]].spring.target, LATCH_DEPTH)
        other = self.deck["pages"][0]["keys"][1]
        self.canvas.update_hover(self._center(other))
        self.assertEqual(self.canvas._runtime[other["id"]].spring.target, 0.0)
        self.assertTrue(self.canvas._runtime[other["id"]].visual.hover)

    def _advance(self, seconds):
        for _ in range(int(seconds * 60)):
            self.canvas._last_tick -= 1 / 60
            self.canvas._tick()

    def _record_sounds(self):
        played = []
        patcher = patch(
            "calendar_app.presentation.widgets.keydeck.canvas.sound_bank",
            return_value=type(
                "_Bank",
                (),
                {
                    "play": lambda _self, path, volume, voices=None: played.append(
                        (os.path.basename(path), round(volume, 2))
                    ),
                    "preload": lambda _self, paths, voices=None: None,
                },
            )(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return played

    def test_quick_click_still_completes_a_full_keystroke(self):
        key = self.deck["pages"][0]["keys"][4]
        runtime = self.canvas._runtime[key["id"]]
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertTrue(runtime.pending_release)
        deepest = 0.0
        for _ in range(40):
            self._advance(1 / 60)
            deepest = max(deepest, runtime.visual.travel)
        self.assertGreaterEqual(deepest, 0.85)
        self._advance(0.6)
        self.assertEqual(runtime.visual.travel, 0.0)
        self.assertFalse(runtime.pending_release)

    def test_off_center_press_tilts_toward_the_finger_and_long_keys_stay_level(self):
        key = self.deck["pages"][0]["keys"][0]
        rect = self.canvas.renderer.geometry.key_rect(key)
        edge = (
            QPointF(rect.right() - 3, rect.center().y()) + self.canvas.content_offset()
        ).toPoint()
        QTest.mousePress(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, edge
        )
        runtime = self.canvas._runtime[key["id"]]
        self.assertGreater(runtime.tilt.tx, 0.5)
        QTest.mouseRelease(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, edge
        )
        self.assertEqual(runtime.tilt.tx, 0.0)
        wide = m.build_template_deck("command_bar")
        self.canvas.set_deck(wide)
        long_key = next(item for item in wide["pages"][0]["keys"] if item["w"] >= 2.0)
        rect = self.canvas.renderer.geometry.key_rect(long_key)
        edge = (
            QPointF(rect.right() - 3, rect.center().y()) + self.canvas.content_offset()
        ).toPoint()
        QTest.mousePress(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, edge
        )
        self.assertLess(self.canvas._runtime[long_key["id"]].tilt.tx, 0.3)
        QTest.mouseRelease(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, edge
        )

    def test_switch_sounds_follow_bottom_out_and_upstroke(self):
        played = self._record_sounds()
        key = self.deck["pages"][0]["keys"][0]
        key["switch"] = "tactile"
        key["sound"] = "auto"
        self.canvas.refresh()
        center = self._center(key)
        QTest.mousePress(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center
        )
        self.assertEqual(played, [])
        self._advance(0.1)
        kinds = [name.rsplit("_", 1)[0] for name, _volume in played]
        self.assertIn("bump", kinds)
        self.assertTrue(any(kind.startswith("bottom_") for kind in kinds))
        QTest.mouseRelease(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center
        )
        self._advance(0.3)
        kinds = [name.rsplit("_", 1)[0] for name, _volume in played]
        self.assertTrue(any(kind.startswith("top_") for kind in kinds))

    def test_custom_sound_choice_keeps_playing_on_press(self):
        played = self._record_sounds()
        key = self.deck["pages"][0]["keys"][0]
        key["sound"] = "pop"
        self.canvas.refresh()
        QTest.mousePress(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual([name for name, _volume in played], ["pop.wav"])
        QTest.mouseRelease(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )

    def test_studio_preview_can_force_sound_while_the_deck_is_muted(self):
        played = self._record_sounds()
        self.deck["sound_enabled"] = False
        key = self.deck["pages"][0]["keys"][0]
        self.canvas.refresh()
        self.canvas.press_visual(key["id"])
        self._advance(0.1)
        self.canvas._release_visual(key["id"])
        self._advance(0.4)
        self.assertEqual(played, [])
        self.canvas.press_visual(key["id"], force_sound=True)
        self._advance(0.1)
        self.assertTrue(played)

    def test_reduce_motion_snaps_without_animating(self):
        self.deck["reduce_motion"] = True
        self.canvas.set_deck(self.deck)
        key = self.deck["pages"][0]["keys"][0]
        QTest.mousePress(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual(self.canvas._runtime[key["id"]].visual.travel, 1.0)
        QTest.mouseRelease(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )

    def test_hidden_canvas_does_not_run_timers(self):
        self.canvas.set_runtime_active(False)
        key = self.deck["pages"][0]["keys"][0]
        self.canvas.show_feedback(key["id"], False)
        self.assertFalse(self.canvas._timer.isActive())

    def test_gear_and_page_dots_are_interactive(self):
        self.deck["pages"].append(m.new_page("B"))
        self.canvas.set_deck(self.deck)
        geometry = self.canvas.renderer.geometry
        offset = self.canvas.content_offset()
        edits, pages = [], []
        self.canvas.editRequested.connect(edits.append)
        self.canvas.pageRequested.connect(pages.append)
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            (geometry.gear_rect.center() + offset).toPoint(),
        )
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            (geometry.dot_rects[1].center() + offset).toPoint(),
        )
        self.assertEqual(edits, [""])
        self.assertEqual(pages, [1])

    def test_presses_right_after_the_deck_appears_are_ignored(self):
        key = self.deck["pages"][0]["keys"][0]
        self.canvas.hide()
        self.canvas.show()
        QTest.mouseClick(
            self.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._center(key),
        )
        self.assertEqual(self.events, [])

    def test_header_close_button_requests_close(self):
        closes = []
        self.canvas.closeRequested.connect(lambda: closes.append(True))
        geometry = self.canvas.renderer.geometry
        point = (geometry.close_rect.center() + self.canvas.content_offset()).toPoint()
        self.assertEqual(self.canvas.header_control_at(point), "close")
        QTest.mouseClick(
            self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point
        )
        self.assertEqual(closes, [True])
        self.assertFalse(geometry.close_rect.intersects(geometry.gear_rect))

    def test_headerless_close_badge_only_appears_on_hover(self):
        self.deck["case"]["header"] = False
        self.canvas.set_deck(self.deck)
        geometry = self.canvas.renderer.geometry
        point = (geometry.close_rect.center() + self.canvas.content_offset()).toPoint()
        self.canvas._set_mouse_inside(False)
        self.assertEqual(self.canvas.header_control_at(point), "")
        self.canvas._set_mouse_inside(True)
        self.assertEqual(self.canvas.header_control_at(point), "close")
        self.canvas.close_control_enabled = False
        self.assertEqual(self.canvas.header_control_at(point), "")

    def test_action_summary_is_human_readable(self):
        self.assertIn("Ctrl+C", action_summary({"type": "hotkey", "target": "Ctrl+C"}))
        page = m.new_page("작업")
        deck = {"pages": [page]}
        self.assertIn("작업", action_summary({"type": "page", "target": page["id"]}, deck))


if __name__ == "__main__":
    unittest.main()
