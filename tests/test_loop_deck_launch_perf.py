# -*- coding: utf-8 -*-
"""Loop mixer launch work: one dialog-theme resolution per restyle, same output.

Also guards the two menu buttons that used to make the Windows 11 style log
"QFont::setPointSize: Point size <= 0 (-1)" on the first paint of the mixer, and
the eight combo popups, which are styled when they first open instead of at launch.
"""

from types import SimpleNamespace

from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QSettings,
    Qt,
    QTimer,
    qInstallMessageHandler,
)
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QPushButton,
    QScroller,
    QStyleFactory,
    QStyleOptionButton,
    QWidget,
)
import pytest

from calendar_app import app_paths
from calendar_app.infrastructure.runtime import loop_mixer_audio
from calendar_app.presentation.dialogs import dialog_styles
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_menu_stylesheet,
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets import overlay_loop_deck
from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY
from calendar_app.shared.color_utils import parse_css_color

_APP = QApplication.instance() or QApplication([])

_THEMES = {
    "dark": {"text_theme": "dark", "panel_base_color": "#1c1c1c", "theme_color": "#4da6ff"},
    "light": {"text_theme": "light", "panel_base_color": "#f3f1fa", "theme_color": "#7950b8"},
    "custom_accent": {
        "text_theme": "dark",
        "panel_base_color": "#121827",
        "theme_color": "#f7e64c",
    },
    "black_panel": {"text_theme": "dark", "panel_base_color": "#000000", "theme_color": "#ff5a8a"},
    "dialog_token_overrides": {
        "text_theme": "light",
        "panel_base_color": "#f3f1fa",
        "theme_color": "#2f7d4f",
        "dialog_token.accent": "#ffff00",
        "dialog_token.surface_bg": "rgba(20, 40, 60, 0.6)",
        "dialog_token.button_primary_bg": "rgba(255, 0, 128, 0.5)",
        "dialog_token.border_soft": "#ccccdd",
    },
}


def _theme_settings(path, theme):
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    for key, value in _THEMES[theme].items():
        settings.setValue(key, value)
    return settings


@pytest.mark.parametrize("theme", sorted(_THEMES))
def test_complete_tokens_build_byte_identical_dialog_and_menu_stylesheets(tmp_path, theme):
    settings = _theme_settings(tmp_path / "theme.ini", theme)
    tokens = get_dialog_theme_tokens(settings=settings)

    assert build_dialog_stylesheet(
        settings=settings, tokens=tokens, tokens_are_complete=True
    ) == build_dialog_stylesheet(settings=settings, tokens=tokens)
    assert build_dialog_menu_stylesheet(
        settings=settings, tokens=tokens
    ) == build_dialog_menu_stylesheet(settings=settings)


def test_theme_cases_are_distinct_and_the_flag_without_tokens_still_resolves(tmp_path):
    stylesheets = set()
    for theme in _THEMES:
        settings = _theme_settings(tmp_path / f"{theme}.ini", theme)
        stylesheet = build_dialog_stylesheet(settings=settings)
        assert build_dialog_stylesheet(settings=settings, tokens_are_complete=True) == stylesheet
        stylesheets.add(stylesheet)
    assert len(stylesheets) == len(_THEMES)


@pytest.fixture
def mixer(tmp_path, monkeypatch):
    class ForbiddenDevice:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("A widget regression must not open an audio device")

    base = loop_mixer_audio.LoopMixer

    class DeviceFreeMixer(base):
        def __init__(self):
            super().__init__(backend_factory=ForbiddenDevice, threaded=False)

    monkeypatch.setattr(loop_mixer_audio, "LoopMixer", DeviceFreeMixer)
    desktop = SimpleNamespace(
        geometry=lambda: QRect(0, 0, 1920, 1080),
        availableGeometry=lambda: QRect(0, 0, 1920, 1080),
    )
    monkeypatch.setattr(OverlayLoopDeckWidget, "screen", lambda self: desktop)
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [desktop]))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(app_paths, "LOOP_MIXER_DIR", str(tmp_path / "local" / "loop-mixer"))
    previous = _APP.property(EXITING_PROPERTY)
    _APP.setProperty(EXITING_PROPERTY, False)
    host = QWidget()
    host.resize(1200, 900)
    host.settings = _theme_settings(tmp_path / "mixer.ini", "custom_accent")
    manager = OverlayWidgetManager(host)
    host.overlay_manager = manager
    widget = manager.get_widget(manager.add_instance("loop_deck", "Mixer"))
    assert isinstance(widget, OverlayLoopDeckWidget)
    yield widget
    manager.shutdown()
    for _, _, _, item in manager.all_instances():
        item.deleteLater()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.setProperty(EXITING_PROPERTY, previous)


def _mixer_stylesheets(widget):
    return (
        widget.face.styleSheet(),
        widget.project_menu.styleSheet(),
        [card.tools_menu.styleSheet() for card in widget.cards],
    )


def test_one_appearance_pass_resolves_the_dialog_theme_once(mixer, monkeypatch):
    calls = []
    original = dialog_styles.get_dialog_theme_tokens

    def counting(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    # The deck binds the name at import; the stylesheet builders use the module global.
    monkeypatch.setattr(overlay_loop_deck, "get_dialog_theme_tokens", counting)
    monkeypatch.setattr(dialog_styles, "get_dialog_theme_tokens", counting)
    mixer._apply_appearance()
    assert len(calls) == 1


def test_appearance_shortcut_keeps_the_mixer_and_menu_stylesheets(mixer, monkeypatch):
    mixer._apply_appearance()
    shortcut = _mixer_stylesheets(mixer)

    def full_dialog(*args, tokens_are_complete=False, **kwargs):
        return build_dialog_stylesheet(*args, **kwargs)

    def full_menu(*args, tokens=None, **kwargs):
        return build_dialog_menu_stylesheet(*args, **kwargs)

    monkeypatch.setattr(overlay_loop_deck, "build_dialog_stylesheet", full_dialog)
    monkeypatch.setattr(overlay_loop_deck, "build_dialog_menu_stylesheet", full_menu)
    mixer._apply_appearance()
    assert _mixer_stylesheets(mixer) == shortcut


def _has_menu_feature(button):
    option = QStyleOptionButton()
    button.initStyleOption(option)
    return bool(option.features & QStyleOptionButton.ButtonFeature.HasMenu)


def test_only_the_two_menu_buttons_drop_the_style_menu_feature(mixer):
    menu_buttons = [mixer.project_button, *(card.tools_button for card in mixer.cards)]
    for button in menu_buttons:
        assert type(button) is overlay_loop_deck._MenuButton
        assert isinstance(button.menu(), QMenu)
        assert not _has_menu_feature(button)
    menu_ids = {id(button) for button in menu_buttons}
    others = [b for b in mixer.face.findChildren(QPushButton) if id(b) not in menu_ids]
    assert len(others) > 20
    assert all(type(button) is QPushButton for button in others)
    # A plain button with a menu does carry the feature, so the check above is meaningful.
    plain = QPushButton(mixer.face)
    plain.setMenu(QMenu(plain))
    assert _has_menu_feature(plain)
    plain.deleteLater()


@pytest.mark.parametrize("open_with", ["mouse", "keyboard"])
def test_menu_buttons_still_open_their_menu(mixer, open_with):
    mixer.show()
    _APP.processEvents()
    for button in (mixer.project_button, mixer.cards[0].tools_button):
        menu = button.menu()
        shown = []

        def close_menu(menu=menu, shown=shown):
            shown.append(True)
            QTimer.singleShot(0, menu.close)

        menu.aboutToShow.connect(close_menu)
        try:
            if open_with == "mouse":
                QTest.mousePress(button, Qt.MouseButton.LeftButton)
            else:
                button.setFocus()
                QTest.keyClick(button, Qt.Key.Key_Space)
            _APP.processEvents()
        finally:
            menu.aboutToShow.disconnect(close_menu)
        assert shown == [True]
        assert not menu.isVisible()


def _forced_style(name):
    # Offscreen defaults to Fusion, which never takes the paths guarded here.
    if name.lower() not in map(str.lower, QStyleFactory.keys()):
        pytest.skip(f"{name} style is not available on this platform")
    # An application stylesheet left by an earlier test wraps the style in a
    # QStyleSheetStyle whose name() is empty, so the base style could not be
    # restored by name and the forced style would leak into the rest of the session.
    sheet = _APP.styleSheet()
    if sheet:
        _APP.setStyleSheet("")
    original = _APP.style().name()
    if not original:
        if sheet:
            _APP.setStyleSheet(sheet)
        pytest.skip("the application style cannot be restored by name")
    QApplication.setStyle(name)
    yield
    QApplication.setStyle(original)
    if sheet:
        _APP.setStyleSheet(sheet)


@pytest.fixture
def windows11_style():
    # The point-size warning comes from the Windows 11 style that users run.
    yield from _forced_style("windows11")


@pytest.fixture(params=["windows11", "Windows"])
def item_view_style(request):
    # Styles whose combo popup is an item view (Fusion uses a menu) draw the 44 px
    # touch rows. Windows 11 is what users run; Windows exists on every platform.
    yield from _forced_style(request.param)


def test_menu_buttons_paint_without_the_point_size_warning(windows11_style, mixer):
    assert _APP.style().name().lower() == "windows11"
    messages = []

    def capture(_kind, _context, message):
        messages.append(message)

    previous = qInstallMessageHandler(capture)
    try:
        mixer.setGeometry(QRect(0, 0, 1120, 820))
        image = mixer.grab().toImage()
    finally:
        qInstallMessageHandler(previous)
    assert not image.isNull()
    assert not [message for message in messages if "Point size <=" in message]


def _touch_combos(widget):
    return [widget.bars, widget.mic_combo, *(card.source for card in widget.cards)]


def _popup_rows(combo):
    view = combo.view()
    rects = [view.visualRect(combo.model().index(row, 0)) for row in range(combo.count())]
    return [(rect.y(), rect.height()) for rect in rects]


class _StyleChanges(QObject):
    def __init__(self):
        super().__init__()
        self.count = 0

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.StyleChange:
            self.count += 1
        return False


def test_combo_popups_are_prepared_on_first_open_only(mixer):
    combos = _touch_combos(mixer)
    assert len(mixer.findChildren(overlay_loop_deck.TouchMixerComboBox)) == len(combos) == 8
    for combo in combos:
        # Launch no longer styles eight hidden popup views.
        assert combo.view().styleSheet() == ""
        assert not QScroller.hasScroller(combo.view().viewport())
    for combo in combos:
        view = combo.view()
        hook = combo.before_popup
        seen_by_hook = []

        def before(view=view, hook=hook, seen=seen_by_hook):
            seen.append(view.styleSheet())
            if hook is not None:
                hook()

        restyles = _StyleChanges()
        view.installEventFilter(restyles)
        combo.before_popup = before
        counts = []
        try:
            for _ in range(2):
                combo.showPopup()
                _APP.processEvents()
                assert view.window().isVisible()
                assert "min-height:44px" in view.styleSheet()
                assert QScroller.hasScroller(view.viewport())
                combo.hidePopup()
                _APP.processEvents()
                counts.append(restyles.count)
        finally:
            combo.before_popup = hook
            view.removeEventFilter(restyles)
        # The source hook still runs before the popup is prepared, and the
        # second open does not restyle the view again.
        assert seen_by_hook == ["", view.styleSheet()]
        assert counts[0] >= 1
        assert counts[1] == counts[0]


@pytest.mark.parametrize("open_with", ["mouse", "f4", "alt_down", "space"])
def test_every_popup_entry_point_prepares_the_popup(mixer, open_with):
    mixer.show()
    _APP.processEvents()
    combo = mixer.bars
    combo.setFocus()
    if open_with == "mouse":
        QTest.mousePress(combo, Qt.MouseButton.LeftButton)
    else:
        key, modifier = {
            "f4": (Qt.Key.Key_F4, Qt.KeyboardModifier.NoModifier),
            "alt_down": (Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier),
            "space": (Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
        }[open_with]
        QTest.keyClick(combo, key, modifier)
    _APP.processEvents()
    try:
        assert combo.view().window().isVisible()
        assert "min-height:44px" in combo.view().styleSheet()
        assert QScroller.hasScroller(combo.view().viewport())
    finally:
        combo.hidePopup()
        _APP.processEvents()


def test_first_popup_rows_do_not_overlap(item_view_style, mixer):
    # A popup stylesheet set at launch was laid out during the mixer's deferred
    # first polish without its 44 px rows: rows 50 px tall stood 30-34 px apart.
    mixer.show()
    _APP.processEvents()
    for combo in _touch_combos(mixer):
        combo.showPopup()
        _APP.processEvents()
        rows = _popup_rows(combo)
        combo.hidePopup()
        _APP.processEvents()
        assert rows
        assert all(height >= 44 for _, height in rows), rows
        assert all(
            below[0] - above[0] == above[1] for above, below in zip(rows, rows[1:], strict=False)
        ), rows


def test_opened_popup_keeps_its_rows_and_follows_the_theme(item_view_style, mixer):
    mixer.show()
    _APP.processEvents()
    combo = mixer.bars

    def open_popup():
        combo.showPopup()
        _APP.processEvents()
        view = combo.view()
        rows = _popup_rows(combo)
        last = view.visualRect(combo.model().index(combo.count() - 1, 0))
        point = view.viewport().mapTo(view.window(), QPoint(last.right() - 6, last.center().y()))
        color = view.window().grab().toImage().pixelColor(point).name()
        combo.hidePopup()
        _APP.processEvents()
        return rows, color

    rows, color = open_popup()
    settings = mixer._real_settings()
    for key, value in _THEMES["light"].items():
        settings.setValue(key, value)
    mixer._apply_appearance()
    _APP.processEvents()
    themed_rows, themed_color = open_popup()
    expected = parse_css_color(get_dialog_theme_tokens(settings=settings)["input_bg"]).name()
    assert themed_color == expected != color
    assert themed_rows == rows
