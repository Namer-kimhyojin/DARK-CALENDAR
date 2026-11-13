# -*- coding: utf-8 -*-
"""Discoverable mixer opening with no pre-existing beatmaker or mixer widget."""

import builtins
from copy import deepcopy
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMenu, QWidget
import pytest

from calendar_app.presentation.main_window.top_menus.widgets_menu import build_widgets_menu_btn
from calendar_app.presentation.widgets import overlay_launcher_deck as launcher
from calendar_app.presentation.widgets.keydeck.model import build_template_deck

_APP = None


@pytest.fixture
def app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class Manager:
    def __init__(self, existing=False):
        self.widget = Mock()
        self.instances = [("loop_deck_7", "My loop", self.widget)] if existing else []
        self.added, self.shown = [], []

    def build_widgets_menu(self, menu, _style):
        menu.clear()
        menu.addAction("Widget manager")
        if self.instances:
            menu.addAction("My loop")

    def instances_of(self, kind):
        assert kind == "loop_deck"
        return list(self.instances)

    def add_instance(self, kind):
        assert kind == "loop_deck"
        self.added.append(kind)
        self.instances = [("loop_deck_7", "My loop", self.widget)]
        return "loop_deck_7"

    def show_instance(self, identity):
        self.shown.append(identity)

    def get_widget(self, identity):
        assert identity == "loop_deck_7"
        return self.widget


@pytest.mark.parametrize("existing", [False, True])
def test_main_widget_menu_keeps_manager_items_without_a_direct_mixer_action(app, existing):
    host = QMainWindow()
    manager = Manager(existing)
    host.overlay_manager = manager
    host.is_locked = False
    bar = QWidget(host)
    layout = QHBoxLayout(bar)
    build_widgets_menu_btn(host, layout, "", "")
    try:
        for _ in range(3):
            host.widgets_menu.aboutToShow.emit()
            matches = [
                action
                for action in host.widgets_menu.actions()
                if action.objectName() == "openLoopMixer"
            ]
            assert matches == []
            assert [action.text() for action in host.widgets_menu.actions()] == (
                ["Widget manager", "My loop"] if existing else ["Widget manager"]
            )
        assert manager.shown == [] and manager.added == []
        manager.widget.raise_.assert_not_called()
        manager.widget.activateWindow.assert_not_called()
    finally:
        host.deleteLater()
        app.processEvents()


def test_menu_build_does_not_eagerly_import_keydeck_and_lock_still_blocks_entry(app, monkeypatch):
    host = QMainWindow()
    host.is_locked = True
    host.overlay_manager = None
    bar = QWidget(host)
    layout = QHBoxLayout(bar)
    original = builtins.__import__
    imports = []

    def observed(name, *args, **kwargs):
        if name == "calendar_app.presentation.widgets.overlay_launcher_deck":
            imports.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", observed)
    try:
        build_widgets_menu_btn(host, layout, "", "")
        host.widgets_menu.aboutToShow.emit()
        assert imports == []
        assert host.widgets_menu.actions() == []
        assert not host.widgets_menu_btn.isEnabled()
    finally:
        host.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("template", ["macro_3x3", "beatmaker_4x4"])
def test_ordinary_and_beatmaker_keydecks_expose_one_top_level_entry_without_changing_deck(
    app, tmp_path, monkeypatch, template
):
    monkeypatch.setattr("calendar_app.presentation.widgets.keydeck.canvas.sound_bank", Mock())
    monkeypatch.setattr(launcher, "is_app_exiting", lambda: False)
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "entry.ini"), QSettings.Format.IniFormat)
    owner.overlay_manager = Manager()
    widget = launcher.OverlayLauncherDeckWidget(owner)
    widget._apply_deck(build_template_deck(template))
    before = deepcopy(widget.deck())
    observations = []

    def execute(menu, _point):
        direct = [action for action in menu.actions() if action.objectName() == "openLoopMixer"]
        assert len(direct) == 1 and direct[0].isVisible() and direct[0].isEnabled()
        recursive = list(menu.actions())
        for action in menu.actions():
            if action.menu() is not None:
                recursive.extend(action.menu().actions())
        assert sum(action.objectName() == "openLoopMixer" for action in recursive) == 1
        direct[0].trigger()
        observations.append(True)

    monkeypatch.setattr(QMenu, "exec", execute)
    try:
        widget._show_context_menu(QPoint())
        assert observations == [True]
        assert owner.overlay_manager.added == ["loop_deck"]
        assert owner.overlay_manager.shown == ["loop_deck_7"]
        assert widget.deck() == before
    finally:
        widget.deleteLater()
        owner.deleteLater()
        app.processEvents()
