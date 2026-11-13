# -*- coding: utf-8 -*-
"""Key dialogs built under German and Arabic must not show Korean text.

Each language runs in its own pytest subprocess whose UI language is pinned before
any application import (conftest's AIR_CALENDAR_TEST_UI_LANGUAGE), as in the real
app; module-level t() values would otherwise keep the language of the first import.
Dialogs are built offscreen with temporary settings, a temporary database and no
Google account. Label, button, tooltip, window title, placeholder, combo, tab, action,
text-edit and spin-box texts and the cells, tooltips and headers of list, table and tree
views are collected. Hangul in them must be listed in
tests/fixtures/i18n_leak_allowlist.json, the known literals still awaiting
translation. After a reviewed change, rewrite that file with
``I18N_LEAK_UPDATE=1 pytest tests/test_i18n_leak_smoke.py``.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
    QCoreApplication,
    QEvent,
    QModelIndex,
    QObject,
    QSettings,
    Qt,
)
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QWidget,
)
import pytest

from calendar_app.infrastructure.db import database_unified
from calendar_app.infrastructure.i18n import i18n

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = Path(__file__).with_name("fixtures") / "i18n_leak_allowlist.json"
UPDATE = os.environ.get("I18N_LEAK_UPDATE") == "1"
LANGUAGE_ENV = "AIR_CALENDAR_TEST_UI_LANGUAGE"
REPORT_ENV = "AIR_CALENDAR_LEAK_REPORT"
HANGUL_RUN = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]+(?:\s+[\u3131-\u318e\uac00-\ud7a3]+)*")
LANGUAGES = ("de", "ar")


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance() or QApplication([])
    i18n.apply_application_locale()  # Direction and Qt catalogs, as bootstrap does.
    yield application
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(scope="module")
def temporary_database(tmp_path_factory):
    original = database_unified.DB_PATH
    database_unified.db_manager.close_all_connections()
    database_unified.DB_PATH = str(tmp_path_factory.mktemp("leak-db") / "test.db")
    database_unified.initialize_unified_database()
    yield
    database_unified.db_manager.close_all_connections()
    database_unified.DB_PATH = original


def owner_with_settings(tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "dialog.ini"), QSettings.Format.IniFormat)
    return owner


def build_task_dialog(tmp_path, keep):
    from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

    return UnifiedTaskDialog(task_type="schedule")


def build_appearance(tmp_path, keep):
    from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
        PanelColorPickerDialog,
    )

    keep.append(owner_with_settings(tmp_path))
    return PanelColorPickerDialog(keep[-1], current_font_size=11)


def build_token_editor(tmp_path, keep):
    from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
        DialogTokenEditorDialog,
    )

    keep.append(owner_with_settings(tmp_path))
    return DialogTokenEditorDialog(keep[-1], persist_on_apply=False, settings=keep[-1].settings)


def build_pomodoro(tmp_path, keep):
    from calendar_app.presentation.dialogs.pomodoro_settings_dialog import (
        PomodoroSettingsDialog,
    )

    keep.append(owner_with_settings(tmp_path))
    return PomodoroSettingsDialog(keep[-1])


def build_checklist(tmp_path, keep):
    from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
        ChecklistManagerDialog,
    )

    return ChecklistManagerDialog()


def build_gcal_settings(tmp_path, keep):
    from calendar_app.presentation.dialogs import gcal_settings_dialog as module

    # No account: empty repositories and credential paths that do not exist.
    for target, value in (
        ("calendar_app.infrastructure.db.calendar_repo.list_calendars", []),
        ("calendar_app.infrastructure.db.task_repo.count_unified_task_gcal_errors", 0),
        ("calendar_app.infrastructure.db.task_repo.count_gcal_delete_queue_errors", 0),
        ("calendar_app.infrastructure.db.task_repo.count_gcal_sync_conflicts", 0),
        ("calendar_app.infrastructure.db.task_repo.get_gcal_delete_queue", []),
    ):
        keep.append(patch(target, return_value=value))
    keep.append(patch.object(module, "CREDENTIALS_PATH", str(tmp_path / "credentials.json")))
    keep.append(patch.object(module, "TOKEN_PATH", str(tmp_path / "token.json")))
    keep.append(patch.object(module.QMessageBox, "information", Mock()))
    for patcher in keep:
        patcher.start()
    parent = owner_with_settings(tmp_path)
    keep.append(parent)
    return module.GCalSettingsDialog(parent=parent, initial_tab="calendar")


def build_widget_studio(tmp_path, keep):
    from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
    from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog

    owner = owner_with_settings(tmp_path)
    manager = OverlayWidgetManager(owner)
    keep.extend((owner, manager))
    return OverlayManagerDialog(manager, owner)


def build_help_center(tmp_path, keep):
    from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog

    return HelpCenterDialog()


DIALOGS = {
    "task_dialog": build_task_dialog,
    "appearance": build_appearance,
    "token_editor": build_token_editor,
    "pomodoro": build_pomodoro,
    "checklist": build_checklist,
    "gcal_settings": build_gcal_settings,
    "widget_studio": build_widget_studio,
    "help_center": build_help_center,
}


ITEM_ROLES = (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole)


def model_texts(model, parent=None, limit=2000):
    """Cell and tooltip text of a list, table or tree model, children included.

    PyQt marks the methods a list or table model does not use as private, so list
    models have one column and only tree models are walked for children.
    """
    parent = parent or QModelIndex()
    is_list = isinstance(model, QAbstractListModel)
    is_tree = not (is_list or isinstance(model, QAbstractTableModel))
    columns = 1 if is_list else model.columnCount(parent)
    texts = []
    for row in range(min(model.rowCount(parent), limit)):
        for column in range(columns):
            index = model.index(row, column, parent)
            texts += [model.data(index, role) for role in ITEM_ROLES]
            if is_tree and model.hasChildren(index):
                texts += model_texts(model, index, limit)
    if not parent.isValid() and not is_list:
        texts += [model.headerData(column, Qt.Orientation.Horizontal) for column in range(columns)]
    return [text for text in texts if isinstance(text, str)]


def visible_texts(root):
    """Every user-facing string the dialog's widgets and actions currently hold."""
    texts = []
    for obj in [root, *root.findChildren(QObject)]:
        if isinstance(obj, QWidget):
            texts += [obj.windowTitle(), obj.toolTip()]
        if isinstance(obj, (QLabel, QAbstractButton)):
            texts.append(obj.text())
        if isinstance(obj, QLineEdit):
            texts.append(obj.placeholderText())
        if isinstance(obj, (QTextEdit, QPlainTextEdit)):
            texts += [obj.toPlainText(), obj.placeholderText()]
        if isinstance(obj, QAbstractSpinBox):
            texts.append(obj.specialValueText())
        if isinstance(obj, (QSpinBox, QDoubleSpinBox)):
            texts += [obj.prefix(), obj.suffix()]
        if isinstance(obj, QGroupBox):
            texts.append(obj.title())
        if isinstance(obj, QComboBox):
            texts += [obj.itemText(index) for index in range(obj.count())]
        if isinstance(obj, QTabWidget):
            texts += [obj.tabText(index) for index in range(obj.count())]
            texts += [obj.tabToolTip(index) for index in range(obj.count())]
        if isinstance(obj, QAbstractItemView) and obj.model() is not None:
            texts += model_texts(obj.model())
        if isinstance(obj, QAction):
            texts += [obj.text(), obj.toolTip()]
    return texts


def hangul_fragments(texts):
    return sorted({match.group() for text in texts for match in HANGUL_RUN.finditer(text or "")})


def load_allowlist():
    if not ALLOWLIST.exists():
        return {}
    return json.loads(ALLOWLIST.read_text(encoding="utf-8", errors="strict")).get("dialogs", {})


def save_allowlist_entry(name, code, fragments):
    dialogs = load_allowlist()
    dialogs.setdefault(name, {})[code] = fragments
    document = {
        "note": (
            "Hangul still shown by dialogs under a non-Korean UI (known untranslated "
            "literals). Rewrite with I18N_LEAK_UPDATE=1 pytest tests/test_i18n_leak_smoke.py."
        ),
        "dialogs": {key: dict(sorted(value.items())) for key, value in sorted(dialogs.items())},
    }
    ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        errors="strict",
    )


def dispose(app, dialog, keep):
    for item in [dialog, *reversed(keep)]:
        if hasattr(item, "stop"):
            item.stop()
        elif hasattr(item, "shutdown"):
            item.shutdown()
        elif isinstance(item, QWidget) and not sip.isdeleted(item):
            item.close()
            item.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.skipif(not os.environ.get(REPORT_ENV), reason="runs in the per-language subprocess")
def test_collect_dialog_hangul(qapp, temporary_database, tmp_path):
    """Subprocess side: build every dialog in the pinned language and report Hangul."""
    assert i18n.lang == os.environ.get(LANGUAGE_ENV)
    report = {}
    for name, build in DIALOGS.items():
        keep, dialog = [], None
        try:
            dialog = build(tmp_path, keep)
            dialog.show()
            for _ in range(3):
                qapp.processEvents()
            report[name] = hangul_fragments(visible_texts(dialog))
        except Exception:
            report[name] = {"error": traceback.format_exc(limit=6)}
        finally:
            dispose(qapp, dialog, keep)
    Path(os.environ[REPORT_ENV]).write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8", errors="strict"
    )


@pytest.mark.skipif(bool(os.environ.get(REPORT_ENV)), reason="parent side only")
@pytest.mark.parametrize("code", LANGUAGES)
def test_dialogs_show_no_new_hangul(code, tmp_path):
    report_path = tmp_path / "report.json"
    env = dict(os.environ)
    env.update({LANGUAGE_ENV: code, REPORT_ENV: str(report_path), "PYTHONIOENCODING": "utf-8"})
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    command = [
        sys.executable,
        "-X",
        "faulthandler",
        "-m",
        "pytest",
        f"{Path(__file__).relative_to(ROOT).as_posix()}::test_collect_dialog_hangul",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    output = (result.stdout + result.stderr)[-4000:]
    assert result.returncode == 0 and report_path.exists(), output
    report = json.loads(report_path.read_text(encoding="utf-8", errors="strict"))
    errors = {name: value["error"] for name, value in report.items() if isinstance(value, dict)}
    assert not errors, "Dialogs that could not be built:\n" + "\n".join(errors.values())
    if UPDATE:
        for name, fragments in report.items():
            save_allowlist_entry(name, code, fragments)
        return
    allowlist = load_allowlist()
    new = {
        name: [item for item in fragments if item not in allowlist.get(name, {}).get(code, [])]
        for name, fragments in report.items()
    }
    new = {name: items for name, items in new.items() if items}
    assert not new, (
        f"Korean text under {code!r} that is not in {ALLOWLIST.name}: {new}. "
        "Route it through t() with a translated key."
    )
