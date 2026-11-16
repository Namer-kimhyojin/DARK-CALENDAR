# -*- coding: utf-8 -*-
"""A new weather widget paints its loading frame before the blocking city lookup.

Settings live in a temporary INI file; the network and the GeoNames lookup are mocked.
"""

import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QRect, QSettings, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets import (
    moment_asset_packs,
    overlay_weather,
    weather_asset_packs,
)
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from tests.test_weather_widget_loading import FakeReply

SEOUL_KEY = ("Seoul", ("Seoul", "celsius"))


class _PaintRecorder(QObject):
    def __init__(self, widget, log):
        super().__init__(widget)
        self._log = log
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.Paint:
            self._log.append("paint")
        return False


def _pump_until(app, condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    return condition()


def _pump_for(app, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)


@pytest.fixture
def weather(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    log = []
    errors = []
    previous_hook = sys.excepthook
    # Record exceptions raised inside Qt callbacks instead of letting PyQt abort.
    sys.excepthook = lambda *exc_info: errors.append(exc_info)
    # Only a paint may start the lookup within a test's wait; the fallback test emits it.
    monkeypatch.setattr(overlay_weather, "_FIRST_PAINT_FALLBACK_MS", 60_000)

    def fake_find_city(name):
        log.append(("find_city", name))
        return SimpleNamespace(latitude=37.566, longitude=126.9784, name=name, timezone="UTC")

    def new_reply(_request):
        log.append("get")
        return FakeReply()

    network = Mock()
    network.get.side_effect = new_reply
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "weather.ini"), QSettings.Format.IniFormat)
    with (
        patch.object(overlay_weather, "get_network_manager", return_value=network),
        patch.object(overlay_weather, "find_city", side_effect=fake_find_city) as find_city,
    ):
        widget = OverlayWeatherWidget(owner)
        _PaintRecorder(widget, log)
        state = SimpleNamespace(
            app=app, widget=widget, owner=owner, network=network, find_city=find_city, log=log
        )
        try:
            yield state
        finally:
            if not sip.isdeleted(state.widget):
                state.widget._set_runtime_active(False)
                state.widget.close()
                state.widget.deleteLater()
            owner.close()
            owner.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            sys.excepthook = previous_hook
    assert not errors, errors


def _lookups(state):
    return [entry for entry in state.log if isinstance(entry, tuple)]


def _show_and_request(state):
    state.widget._runtime_active = True
    state.widget.show()
    state.widget.request_update()


def test_shown_widget_paints_loading_frame_before_lookup_and_request(weather):
    _show_and_request(weather)

    assert weather.widget._status_text == t("widget.weather.loading", "날씨를 불러오는 중…")
    assert weather.widget._weather_data["city"] == "Seoul"
    weather.find_city.assert_not_called()
    weather.network.get.assert_not_called()
    assert weather.widget._deferred_lookup == SEOUL_KEY

    assert _pump_until(weather.app, lambda: weather.network.get.called)
    _pump_for(weather.app, 0.05)
    assert weather.find_city.call_count == 1
    assert weather.network.get.call_count == 1
    log = weather.log
    assert log.index("paint") < log.index(("find_city", "Seoul")) < log.index("get")
    assert weather.widget._deferred_lookup is None
    assert not weather.widget._deferred_lookup_timer.isActive()
    assert weather.widget._get("display_name") == "Seoul"


def test_unshown_widget_keeps_the_synchronous_lookup(weather):
    weather.widget._runtime_active = True
    weather.widget.request_update()
    assert _lookups(weather) == [("find_city", "Seoul")]
    assert weather.network.get.call_count == 1


def test_deactivation_before_the_paint_drops_the_lookup(weather):
    _show_and_request(weather)
    weather.widget._set_runtime_active(False)
    assert weather.widget._deferred_lookup is None
    assert not weather.widget._deferred_lookup_timer.isActive()

    assert _pump_until(weather.app, lambda: "paint" in weather.log)
    _pump_for(weather.app, 0.1)
    weather.find_city.assert_not_called()
    weather.network.get.assert_not_called()


def test_location_change_before_the_paint_resolves_only_the_new_location(weather):
    _show_and_request(weather)
    weather.widget._set("location", "Busan")
    weather.widget.request_update()
    assert weather.widget._deferred_lookup == ("Busan", ("Busan", "celsius"))

    assert _pump_until(weather.app, lambda: weather.network.get.called)
    _pump_for(weather.app, 0.05)
    assert _lookups(weather) == [("find_city", "Busan")]
    assert weather.network.get.call_count == 1
    assert weather.widget._weather_data["city"] == "Busan"


def test_fallback_timeout_runs_the_lookup_when_no_paint_arrived(weather):
    _show_and_request(weather)
    timer = weather.widget._deferred_lookup_timer
    assert timer.isActive() and timer.isSingleShot()
    assert timer.interval() == overlay_weather._FIRST_PAINT_FALLBACK_MS
    assert "paint" not in weather.log

    timer.timeout.emit()
    assert _lookups(weather) == [("find_city", "Seoul")]
    assert weather.network.get.call_count == 1

    # The paint that follows finds nothing left to run.
    assert _pump_until(weather.app, lambda: "paint" in weather.log)
    _pump_for(weather.app, 0.05)
    assert weather.find_city.call_count == 1
    assert weather.network.get.call_count == 1


def test_deleting_the_widget_before_the_paint_runs_nothing(weather):
    _show_and_request(weather)
    weather.widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(weather.widget)

    _pump_for(weather.app, 0.2)
    weather.find_city.assert_not_called()
    weather.network.get.assert_not_called()


def test_deleting_the_widget_after_the_paint_drops_the_queued_lookup(weather):
    _show_and_request(weather)
    # The paint queued the lookup; the widget goes away before it runs.
    weather.widget._on_painted_after_show()
    weather.widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(weather.widget)

    _pump_for(weather.app, 0.2)
    weather.find_city.assert_not_called()
    weather.network.get.assert_not_called()


def test_hide_show_cycle_keeps_the_pending_lookup_until_the_next_paint(weather):
    _show_and_request(weather)
    weather.widget.hide()
    _pump_for(weather.app, 0.05)
    weather.find_city.assert_not_called()
    assert weather.widget._deferred_lookup == SEOUL_KEY

    weather.widget.show()
    assert _pump_until(weather.app, lambda: weather.network.get.called)
    _pump_for(weather.app, 0.05)
    assert _lookups(weather) == [("find_city", "Seoul")]
    assert weather.network.get.call_count == 1
    assert weather.log.index("paint") < weather.log.index(("find_city", "Seoul"))


def test_synchronous_lookup_while_hidden_replaces_the_waiting_one(weather):
    replies = []

    def new_reply(_request):
        weather.log.append("get")
        replies.append(FakeReply())
        return replies[-1]

    weather.network.get.side_effect = new_reply
    _show_and_request(weather)
    weather.widget.hide()
    # Hidden again before the paint: the next request looks up synchronously, as before.
    weather.widget.request_update()
    assert _lookups(weather) == [("find_city", "Seoul")]
    assert weather.widget._deferred_lookup is None
    assert not weather.widget._deferred_lookup_timer.isActive()

    # With the reply done (fresh cache, nothing pending) the next paint must not look up again.
    replies[0].finish()
    _pump_until(weather.app, lambda: not weather.widget._pending_replies)
    assert not weather.widget._pending_replies
    weather.widget.show()
    assert _pump_until(weather.app, lambda: "paint" in weather.log)
    _pump_for(weather.app, 0.05)
    assert _lookups(weather) == [("find_city", "Seoul")]
    assert weather.network.get.call_count == 1


def test_slow_lookup_does_not_delay_the_first_paint_of_an_enabled_widget(weather):
    def slow_find_city(name):
        weather.log.append(("find_city", name))
        time.sleep(0.3)
        return SimpleNamespace(latitude=37.566, longitude=126.9784, name=name, timezone="UTC")

    weather.find_city.side_effect = slow_find_city
    # The manager's add path: show, then activate (which queues request_update).
    weather.widget.set_enabled(True)

    assert _pump_until(weather.app, lambda: weather.network.get.called)
    log = weather.log
    assert "paint" in log
    assert log.index("paint") < log.index(("find_city", "Seoul")) < log.index("get")
    assert weather.find_city.call_count == 1


def _reference_trim(cell: QPixmap) -> QPixmap:
    """The per-pixel loop that _trim_transparent replaced, kept as the oracle."""
    if cell.isNull():
        return cell
    image = cell.toImage().convertToFormat(QImage.Format.Format_Alpha8)
    pointer = image.constBits()
    if pointer is None:
        return cell
    alpha = pointer.asstring(image.sizeInBytes())
    stride, width, height = image.bytesPerLine(), image.width(), image.height()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        row = alpha[y * stride : y * stride + width]
        first = next((x for x, opacity in enumerate(row) if opacity > 4), None)
        if first is None:
            continue
        last = width - 1 - next(x for x, opacity in enumerate(reversed(row)) if opacity > 4)
        left, right = min(left, first), max(right, last)
        top, bottom = min(top, y), max(bottom, y)
    if right < left:
        return cell
    padding = max(2, round(max(right - left + 1, bottom - top + 1) * 0.035))
    rect = QRect(left, top, right - left + 1, bottom - top + 1)
    rect = rect.adjusted(-padding, -padding, padding, padding).intersected(cell.rect())
    return cell.copy(rect)


def _assert_same_trim(cell: QPixmap) -> None:
    trimmed = weather_asset_packs._trim_transparent(cell)
    expected = _reference_trim(cell)
    assert trimmed.size() == expected.size()
    assert trimmed.toImage() == expected.toImage()


@pytest.mark.parametrize("pack_id", ("air_soft", "paper_weather", "mono_atmosphere"))
def test_trim_matches_the_reference_for_every_weather_sprite_cell(pack_id):
    QApplication.instance() or QApplication([])
    sprite = weather_asset_packs._load_sprite(pack_id)
    assert not sprite.isNull()
    for index in range(16):
        row, column = divmod(index, 4)
        left = round(column * sprite.width() / 4)
        right = round((column + 1) * sprite.width() / 4)
        top = round(row * sprite.height() / 4)
        bottom = round((row + 1) * sprite.height() / 4)
        _assert_same_trim(sprite.copy(QRect(left, top, right - left, bottom - top)))


@pytest.mark.parametrize("pack_id", ("air_moments", "paper_seasons"))
def test_trim_matches_the_reference_for_scaled_moment_art(pack_id):
    QApplication.instance() or QApplication([])
    for moment in moment_asset_packs._MOMENT_TO_CELL:
        art = moment_asset_packs.moment_asset_pixmap(pack_id, moment, 600)
        assert not art.isNull()
        _assert_same_trim(art)


def _alpha_cell(width, height, points):
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    for x, y, alpha in points:
        image.setPixelColor(x, y, QColor(255, 0, 0, alpha))
    return QPixmap.fromImage(image)


@pytest.mark.parametrize(
    ("width", "height", "points"),
    [
        (64, 64, []),
        (1, 1, []),
        (1, 1, [(0, 0, 255)]),
        (1, 1, [(0, 0, 4)]),
        # Odd width pads every Alpha8 row; the last column must still count.
        (13, 7, [(12, 0, 5), (0, 6, 200), (6, 3, 4)]),
        (13, 7, [(12, 3, 255)]),
        (37, 9, [(4, 2, 5), (5, 2, 4), (30, 2, 6), (36, 8, 3)]),
    ],
)
def test_trim_matches_the_reference_for_edge_cells(width, height, points):
    QApplication.instance() or QApplication([])
    _assert_same_trim(_alpha_cell(width, height, points))
