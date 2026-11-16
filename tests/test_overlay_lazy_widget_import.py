# -*- coding: utf-8 -*-
"""Creating one overlay widget imports only that type's module; the Widgets menu
is rebuilt when it is opened, not eagerly after every menu action.

The KeyDeck module alone took about 28 ms to import, and the first widget of every
process used to import all nine widget modules. overlay_widgets now resolves each
class on first access (PEP 562), and the class lookups must stay static import
statements so PyInstaller still bundles every widget module.
"""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QWidget,
)
import pytest

from calendar_app.presentation.main_window.top_menus.widgets_menu import build_widgets_menu_btn
from calendar_app.presentation.widgets.overlay_manager import (
    _WIDGET_TYPES,
    OverlayWidgetManager,
    _SettingsProxy,
)

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "calendar_app/presentation/widgets/overlay_widgets.py"
SHIM_NAME = "calendar_app.presentation.widgets.overlay_widgets"
WIDGET_PACKAGE = "calendar_app.presentation.widgets"
WIDGET_CLASSES = {info["class"] for info in _WIDGET_TYPES.values()}

# The child isolates settings and app data before anything imports calendar_app,
# the same way tests/conftest.py does for this process.
CHILD = r"""
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
os.environ["LOCALAPPDATA"] = str(root)

from PyQt6 import QtCore

_RealQSettings = QtCore.QSettings


class _IsolatedQSettings(_RealQSettings):
    def __init__(self, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            name = "".join(ch if ch.isalnum() else "_" for ch in f"{args[0]}_{args[1]}")
            super().__init__(str(root / f"{name}.ini"), _RealQSettings.Format.IniFormat, *args[2:])
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings

from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication([])
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager

host = QWidget()
host.settings = _IsolatedQSettings(str(root / "host.ini"), _RealQSettings.Format.IniFormat)
widget = OverlayWidgetManager(host)._create_widget("clock", "clock_0")
loaded = sorted(
    name for name in sys.modules if name.startswith("calendar_app.presentation.widgets.")
)
print(json.dumps({"class": type(widget).__name__, "loaded": loaded}))
widget.deleteLater()
host.deleteLater()
app.processEvents()
"""


_APP = None


def _app():
    # Keep a reference: a QApplication nobody holds is destroyed at once, and the
    # next QWidget then ends the process with qFatal.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _flush_deleted():
    _app().processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_first_clock_imports_only_the_clock_module(tmp_path):
    environment = dict(
        os.environ,
        LOCALAPPDATA=str(tmp_path),
        PYTHONIOENCODING="utf-8",
        QT_QPA_PLATFORM="offscreen",
    )
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(tmp_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["class"] == "OverlayClockWidget"

    loaded = set(report["loaded"])
    type_modules = {
        f"{WIDGET_PACKAGE}.overlay_{suffix}"
        for suffix in (
            "clock",
            "countdown",
            "datecard",
            "dday",
            "launcher_deck",
            "loop_deck",
            "stopwatch",
            "text",
            "weather",
        )
    }
    assert loaded & type_modules == {f"{WIDGET_PACKAGE}.overlay_clock"}
    assert f"{WIDGET_PACKAGE}.keydeck.canvas" not in loaded


def test_shim_still_exports_every_widget_class():
    namespace: dict = {}
    exec(f"from {SHIM_NAME} import *", namespace)
    exported = {name for name in namespace if not name.startswith("__")}
    assert exported == WIDGET_CLASSES
    for name in WIDGET_CLASSES:
        assert isinstance(namespace[name], type)
        assert namespace[name].__name__ == name

    module = sys.modules[SHIM_NAME]
    assert WIDGET_CLASSES.issubset(dir(module))
    with pytest.raises(AttributeError, match="OverlayNopeWidget"):
        module.OverlayNopeWidget  # noqa: B018
    assert not hasattr(module, "OverlayNopeWidget")


def test_unknown_type_is_rejected_before_any_class_lookup(tmp_path, monkeypatch):
    _app()
    # A substitute shim records every attribute lookup (PEP 562 hook on the module).
    looked_up: list[str] = []
    stub = ModuleType(SHIM_NAME)
    stub.__getattr__ = looked_up.append
    monkeypatch.setitem(sys.modules, SHIM_NAME, stub)
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "unknown.ini"), QSettings.Format.IniFormat)
    try:
        with pytest.raises(ValueError, match="Unknown widget type: 'nope'"):
            OverlayWidgetManager(host)._create_widget("nope", "nope_0")
        assert looked_up == []
    finally:
        host.deleteLater()
        _flush_deleted()


def test_factory_reads_the_class_from_sys_modules(tmp_path, monkeypatch):
    """A module substituted in sys.modules wins even after the real shim was bound."""
    import calendar_app.presentation.widgets.overlay_widgets  # noqa: F401

    _app()

    class Substitute:
        def __init__(self, owner):
            self.owner = owner

    stub = ModuleType(SHIM_NAME)
    stub.OverlayTextWidget = Substitute
    monkeypatch.setitem(sys.modules, SHIM_NAME, stub)
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "factory.ini"), QSettings.Format.IniFormat)
    try:
        widget = OverlayWidgetManager(host)._create_widget("text", "text_3")
        assert isinstance(widget, Substitute)
        assert isinstance(widget.owner, _SettingsProxy)
        assert widget.owner._prefix == "oi_text_3"
    finally:
        host.deleteLater()
        _flush_deleted()


def test_every_widget_class_has_a_static_import_for_packaging():
    tree = ast.parse(SHIM.read_text(encoding="utf-8", errors="strict"))
    getter = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__"
    )
    lazy_imports = {}
    for node in ast.walk(getter):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module, ast.dump(node)
            for alias in node.names:
                lazy_imports[alias.name] = node.module
    for name in sorted(WIDGET_CLASSES):
        module = lazy_imports.get(name)
        assert module and module.startswith(f"{WIDGET_PACKAGE}.overlay_"), name
        assert (ROOT / (module.replace(".", "/") + ".py")).is_file(), module

    # Outside __getattr__ only the TYPE_CHECKING block may name a widget module;
    # a module-level import would bring back the eager cost.
    for node in tree.body:
        if node is getter or (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.ImportFrom):
                assert not (child.module or "").startswith(f"{WIDGET_PACKAGE}.overlay_")
    # Computed-name imports are invisible to PyInstaller.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "importlib" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "importlib"


class _MenuWidget(QWidget):
    """Never shown: the menu test only needs the manager-facing contract."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self._enabled = False

    def apply_initial_settings(self):
        pass

    def restore_position(self, offset):
        self.move(offset)

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)


def test_menu_actions_leave_the_rebuild_to_about_to_show(tmp_path, monkeypatch):
    _app()
    stub = ModuleType(SHIM_NAME)
    for name in WIDGET_CLASSES:
        setattr(stub, name, _MenuWidget)
    monkeypatch.setitem(sys.modules, SHIM_NAME, stub)

    host = QMainWindow()
    host.settings = QSettings(str(tmp_path / "menu.ini"), QSettings.Format.IniFormat)
    host.is_locked = False
    manager = OverlayWidgetManager(host)
    host.overlay_manager = manager
    layout = QHBoxLayout(QWidget(host))
    build_widgets_menu_btn(host, layout, "", "")
    builds = Mock(wraps=manager.build_widgets_menu)
    monkeypatch.setattr(manager, "build_widgets_menu", builds)
    opened = 0

    def open_menu():
        nonlocal opened
        opened += 1
        host.widgets_menu.aboutToShow.emit()
        assert builds.call_count == opened
        return {action.text(): action for action in host.widgets_menu.actions()}

    try:
        with patch(
            "calendar_app.presentation.widgets.overlay_manager._prompt_widget_name",
            side_effect=[("회의 메모", True), ("할 일", True), ("장보기", True)],
        ):
            for _ in range(3):
                manager._ui_add_instance("text")
        assert builds.call_count == 0
        menu = open_menu()
        for name in ("회의 메모", "할 일", "장보기"):
            assert menu[name].isCheckable() and menu[name].isChecked()

        first, second, _third = manager._meta
        with patch.object(QInputDialog, "getText", return_value=("집중 메모", True)):
            manager._ui_rename(first)
        assert builds.call_count == opened
        menu = open_menu()
        assert "집중 메모" in menu and "회의 메모" not in menu

        manager._ui_remove(first)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
            manager._ui_remove_with_confirm(second)
            manager._ui_remove_all_with_confirm()
        assert manager.all_instances() == []
        assert builds.call_count == opened
        menu = open_menu()
        assert not {"집중 메모", "할 일", "장보기"} & set(menu)
    finally:
        for _, _, _, widget in manager.all_instances():
            widget.deleteLater()
        host.deleteLater()
        _flush_deleted()
