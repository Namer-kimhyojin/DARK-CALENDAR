# -*- coding: utf-8 -*-
"""Contact-based multi-touch uses the same runtime without synthesized mouse repeats."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QEventPoint, QPointingDevice
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.widgets.keydeck import model
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas


@pytest.fixture
def canvas(monkeypatch):
    app = QApplication.instance() or QApplication([])
    bank = Mock()
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", lambda: bank)
    canvas = KeyDeckCanvas()
    canvas.set_deck(model.build_template_deck("beatmaker_4x4"))
    canvas.deck["reduce_motion"] = True
    canvas.resize(canvas.sizeHint())
    canvas.show()
    app.processEvents()
    canvas._armed_at = 0.0
    yield canvas, bank
    canvas.close()
    canvas.deleteLater()
    app.processEvents()


def point(canvas, identifier, index, state):
    key = canvas.deck["pages"][canvas.deck["page"]]["keys"][index]
    position = canvas.renderer.geometry.key_rect(key).center() + canvas.content_offset()
    return SimpleNamespace(id=lambda: identifier, state=lambda: state, position=lambda: position)


def touch(canvas, event_type, *points):
    event = SimpleNamespace(type=lambda: event_type, points=lambda: points, accept=Mock())
    assert canvas.event(event)
    event.accept.assert_called_once()


def test_multiple_contacts_hit_once_and_moving_does_not_retrigger(canvas):
    surface, bank = canvas
    triggered = []
    surface.padTriggered.connect(triggered.append)
    assert surface.testAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
    touch(
        surface,
        QEvent.Type.TouchBegin,
        point(surface, 1, 0, QEventPoint.State.Pressed),
        point(surface, 2, 1, QEventPoint.State.Pressed),
    )
    assert len(triggered) == bank.play.call_count == 2
    touch(
        surface,
        QEvent.Type.TouchUpdate,
        point(surface, 1, 2, QEventPoint.State.Updated),
        point(surface, 2, 1, QEventPoint.State.Stationary),
        point(surface, 3, 3, QEventPoint.State.Pressed),
    )
    assert len(triggered) == bank.play.call_count == 3
    touch(surface, QEvent.Type.TouchUpdate, point(surface, 3, 3, QEventPoint.State.Pressed))
    assert len(triggered) == bank.play.call_count == 3
    touch(
        surface,
        QEvent.Type.TouchEnd,
        point(surface, 1, 2, QEventPoint.State.Released),
        point(surface, 2, 1, QEventPoint.State.Released),
        point(surface, 3, 3, QEventPoint.State.Released),
    )
    assert not surface._touch_points
    assert len(triggered) == bank.play.call_count == 3


@pytest.mark.parametrize("boundary", ["cancel", "hide", "inactive", "page", "stop"])
def test_touch_boundaries_clear_contacts_without_actions(canvas, boundary):
    surface, bank = canvas
    activated = []
    surface.keyActivated.connect(lambda *args: activated.append(args))
    touch(surface, QEvent.Type.TouchBegin, point(surface, 5, 0, QEventPoint.State.Pressed))
    if boundary == "cancel":
        touch(surface, QEvent.Type.TouchCancel)
    elif boundary == "hide":
        surface.hide()
    elif boundary == "inactive":
        surface.set_runtime_active(False)
    elif boundary == "page":
        surface.deck["page"] = 1
        surface.set_deck(surface.deck)
    else:
        surface.stop_sounds()
    assert not surface._touch_points
    assert surface._touch_pointer_id is None
    assert not surface._hold_timer.isActive()
    assert not activated
    assert bank.play.call_count == 1


def test_same_pad_remains_pressed_until_touch_and_keyboard_release(canvas):
    surface, _bank = canvas
    surface.set_keyboard_performance(True)
    QTest.keyPress(surface, Qt.Key.Key_Z)
    key = surface.deck["pages"][0]["keys"][12]
    touch(surface, QEvent.Type.TouchBegin, point(surface, 8, 12, QEventPoint.State.Pressed))
    QTest.keyRelease(surface, Qt.Key.Key_Z)
    assert surface._runtime[key["id"]].visual.travel == 1.0
    touch(surface, QEvent.Type.TouchEnd, point(surface, 8, 12, QEventPoint.State.Released))
    assert surface._runtime[key["id"]].visual.travel == 0.0


def test_synthesized_mouse_is_ignored_but_real_mouse_still_plays(canvas):
    surface, bank = canvas
    contact = point(surface, 1, 0, QEventPoint.State.Pressed)
    touch(surface, QEvent.Type.TouchBegin, contact)
    touch(surface, QEvent.Type.TouchEnd, point(surface, 1, 0, QEventPoint.State.Released))
    for callback in (surface.mousePressEvent, surface.mouseReleaseEvent):
        event = SimpleNamespace(
            pointingDevice=lambda: SimpleNamespace(
                pointerType=lambda: QPointingDevice.PointerType.Finger
            ),
            accept=Mock(),
        )
        callback(event)
        event.accept.assert_called_once()
    assert bank.play.call_count == 1
    QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=contact.position().toPoint())
    assert bank.play.call_count == 2


def test_macro_touch_executes_only_on_release_and_hold_remains_distinct(canvas):
    surface, _bank = canvas
    surface.set_deck(model.build_template_deck("macro_3x3"))
    key = surface.deck["pages"][0]["keys"][0]
    key["hold_action"] = {"type": "command", "target": "today"}
    surface.refresh()
    activated = []
    surface.keyActivated.connect(lambda *args: activated.append(args))
    touch(surface, QEvent.Type.TouchBegin, point(surface, 1, 0, QEventPoint.State.Pressed))
    assert not activated
    touch(surface, QEvent.Type.TouchEnd, point(surface, 1, 0, QEventPoint.State.Released))
    assert activated == [(key["id"], "tap")]
    touch(surface, QEvent.Type.TouchBegin, point(surface, 2, 0, QEventPoint.State.Pressed))
    surface._on_hold()
    touch(surface, QEvent.Type.TouchEnd, point(surface, 2, 0, QEventPoint.State.Released))
    assert activated == [(key["id"], "tap"), (key["id"], "hold")]


@pytest.mark.parametrize("boundary", ["move_cancel", "release_outside"])
def test_macro_drag_out_and_touch_cancel_do_not_execute_or_remain_pressed(canvas, boundary):
    surface, _bank = canvas
    surface.set_deck(model.build_template_deck("macro_3x3"))
    activated = []
    surface.keyActivated.connect(lambda *args: activated.append(args))
    key = surface.deck["pages"][0]["keys"][0]
    touch(surface, QEvent.Type.TouchBegin, point(surface, 7, 0, QEventPoint.State.Pressed))
    outside = SimpleNamespace(
        id=lambda: 7, state=lambda: QEventPoint.State.Updated, position=lambda: QPointF(-100, -100)
    )
    if boundary == "move_cancel":
        touch(surface, QEvent.Type.TouchUpdate, outside)
        touch(surface, QEvent.Type.TouchCancel)
    else:
        outside.state = lambda: QEventPoint.State.Released
        touch(surface, QEvent.Type.TouchEnd, outside)
    assert surface._runtime[key["id"]].visual.travel == 0.0
    assert not surface._pressed_id
    assert not activated


def test_empty_touch_begin_is_left_to_existing_overlay_dragging(canvas):
    surface, bank = canvas
    contact = SimpleNamespace(
        id=lambda: 7, state=lambda: QEventPoint.State.Pressed, position=lambda: QPointF(-100, -100)
    )
    event = SimpleNamespace(
        type=lambda: QEvent.Type.TouchBegin, points=lambda: [contact], accept=Mock(), ignore=Mock()
    )
    assert surface.event(event) is False
    event.ignore.assert_called_once()
    event.accept.assert_not_called()
    assert not surface._touch_points
    assert surface._touch_mouse_suppressed_until == 0.0
    bank.play.assert_not_called()


def _at(identifier, state, position):
    return SimpleNamespace(id=lambda: identifier, state=lambda: state, position=lambda: position)


def _key_edge(surface, index, dx):
    key = surface.deck["pages"][surface.deck["page"]]["keys"][index]
    rect = surface.renderer.geometry.key_rect(key)
    return QPointF(rect.right() + dx, rect.center().y()) + surface.content_offset()


def test_touch_right_after_the_deck_is_shown_still_plays(canvas):
    import time

    surface, bank = canvas
    surface._armed_at = time.monotonic() + 10.0
    touch(surface, QEvent.Type.TouchBegin, point(surface, 1, 0, QEventPoint.State.Pressed))
    assert bank.play.call_count == 1


def test_touch_in_the_gap_beside_a_pad_plays_that_pad(canvas):
    surface, bank = canvas
    gap = surface.renderer.geometry.gap
    contact = _at(1, QEventPoint.State.Pressed, _key_edge(surface, 0, gap / 2.0 - 0.5))
    assert surface.key_at(contact.position()) is None
    touch(surface, QEvent.Type.TouchBegin, contact)
    assert bank.play.call_count == 1


def test_second_finger_on_a_macro_key_still_activates(canvas):
    surface, _bank = canvas
    surface.set_deck(model.build_template_deck("macro_3x3"))
    surface.deck["reduce_motion"] = True
    keys = surface.deck["pages"][0]["keys"]
    activated = []
    surface.keyActivated.connect(lambda *args: activated.append(args))
    touch(surface, QEvent.Type.TouchBegin, point(surface, 1, 0, QEventPoint.State.Pressed))
    touch(
        surface,
        QEvent.Type.TouchUpdate,
        point(surface, 1, 0, QEventPoint.State.Stationary),
        point(surface, 2, 1, QEventPoint.State.Pressed),
    )
    touch(
        surface,
        QEvent.Type.TouchEnd,
        point(surface, 1, 0, QEventPoint.State.Released),
        point(surface, 2, 1, QEventPoint.State.Released),
    )
    assert sorted(activated) == sorted([(keys[0]["id"], "tap"), (keys[1]["id"], "tap")])


def test_macro_finger_drifting_slightly_off_the_edge_still_activates(canvas):
    surface, _bank = canvas
    surface.set_deck(model.build_template_deck("macro_3x3"))
    key = surface.deck["pages"][0]["keys"][0]
    activated = []
    surface.keyActivated.connect(lambda *args: activated.append(args))
    touch(surface, QEvent.Type.TouchBegin, point(surface, 1, 0, QEventPoint.State.Pressed))
    touch(
        surface,
        QEvent.Type.TouchEnd,
        _at(1, QEventPoint.State.Released, _key_edge(surface, 0, 4.0)),
    )
    assert activated == [(key["id"], "tap")]


def test_switch_sound_plays_at_contact_and_is_not_repeated_by_the_animation(canvas):
    surface, bank = canvas
    surface.set_deck(model.build_template_deck("macro_3x3"))
    surface.deck["reduce_motion"] = False
    key = surface.deck["pages"][0]["keys"][0]
    runtime = surface._runtime[key["id"]]
    assert runtime.plan is not None
    bank.play.reset_mock()

    touch(surface, QEvent.Type.TouchBegin, point(surface, 1, 0, QEventPoint.State.Pressed))
    played_at_contact = bank.play.call_count
    for _ in range(30):
        surface._last_tick -= 1.0 / 60.0
        surface._tick()

    assert played_at_contact >= 1
    bottom_paths = [
        str(call.args[0]) for call in bank.play.call_args_list if "bottom" in str(call.args[0])
    ]
    assert len(bottom_paths) <= 1
