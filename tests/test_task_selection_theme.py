# -*- coding: utf-8 -*-
"""Selection hints keep readable foregrounds after status and theme updates."""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.shared.color_utils import composite_color, contrast_ratio, parse_css_color
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens


class SelectionHost(TaskActionsMixin, QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.selection_status_lbl = QLabel(self)
        QVBoxLayout(self).addWidget(self.selection_status_lbl)
        self.setAutoFillBackground(True)


@pytest.fixture
def selection_host(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "selection.ini"), QSettings.Format.IniFormat)
    settings.setValue("last_opacity_unit", "byte")
    settings.setValue("last_opacity", 255)
    settings.setValue("ui_shape_preset", "round")
    host = SelectionHost(settings)
    yield app, host
    host.close()
    host.deleteLater()
    app.processEvents()


def _configure(settings, profile):
    mode, base, accent, opacity = {
        "dark": ("dark", "#121827", "#c5a3f5", 255),
        "light": ("light", "#f3f1fa", "#7950b8", 255),
        "custom": ("custom", "#24413f", "#f2b96b", 150),
        "auto-family-light": ("auto", "#121827", "#c5a3f5", 255),
        "auto-family-dark": ("auto", "#f3f1fa", "#7950b8", 255),
    }[profile]
    for key, value in {
        "text_theme": mode,
        "panel_base_color": base,
        "theme_color": accent,
        "last_opacity": opacity,
    }.items():
        settings.setValue(key, value)
    if profile.startswith("auto-family"):
        for key, value in {
            "appearance_style_family": "navy_lilac",
            "appearance_accent_source": "family",
            "appearance_family_light_base": "#f3f1fa",
            "appearance_family_light_accent": "#7950b8",
            "appearance_family_dark_base": "#121827",
            "appearance_family_dark_accent": "#c5a3f5",
        }.items():
            settings.setValue(key, value)


def _reading_surface(host):
    snapshot = build_theme_snapshot(settings=host.settings)
    tokens = get_ui_tokens(settings=host.settings, snapshot=snapshot)
    surface = composite_color(tokens["bg_main"], snapshot.panel_base_color)
    palette = host.palette()
    palette.setColor(QPalette.ColorRole.Window, surface)
    host.setPalette(palette)
    return tokens, surface


@pytest.mark.parametrize(
    "profile", ("dark", "light", "custom", "auto-family-light", "auto-family-dark")
)
@pytest.mark.parametrize(
    ("task_ids", "directive_ids", "count"),
    (((), (), 0), ((1,), (), 1), ((), (7,), 1), ((1, 2), (7, 8), 4)),
    ids=("none", "task", "directive", "multiple"),
)
def test_selection_label_uses_effective_foreground_and_contrast(
    selection_host, profile, task_ids, directive_ids, count, record_testsuite_property
):
    app, host = selection_host
    _configure(host.settings, profile)
    system_mode = "light" if profile == "auto-family-light" else "dark"
    with patch(
        "calendar_app.shared.system_theme.resolve_system_text_theme", return_value=system_mode
    ):
        tokens, _surface = _reading_surface(host)
        before = {key: host.settings.value(key) for key in host.settings.allKeys()}
        host.selected_task_ids = set(task_ids)
        host.selected_directive_ids = set(directive_ids)
        host.update_task_selection_status()
        host.show()
        app.processEvents()
        label = host.selection_status_lbl
        foreground = label.palette().color(QPalette.ColorRole.WindowText)
        assert foreground == parse_css_color(tokens["text_primary"])
        background = composite_color(
            label.palette().color(QPalette.ColorRole.Window),
            host.palette().color(QPalette.ColorRole.Window),
        )
        effective_foreground = composite_color(foreground, background)
        ratio = contrast_ratio(effective_foreground, background)
        case = f"{profile}:{len(task_ids)}:{len(directive_ids)}"
        record_testsuite_property(f"selection-foreground:{case}", foreground.name())
        record_testsuite_property(f"selection-background:{case}", background.name())
        record_testsuite_property(f"selection-contrast:{case}", ratio)
        assert ratio >= 4.5
        expected = t("panel.n_selected", n=count) if count else t("panel.multiselect_guide")
        assert label.text() == expected
        assert label.font().bold() is (count > 0)
        assert {key: host.settings.value(key) for key in host.settings.allKeys()} == before


def test_system_family_switch_repaints_existing_selection_label(selection_host):
    app, host = selection_host
    _configure(host.settings, "auto-family-light")
    host.selected_task_ids = {1}
    colors = []
    for system_mode in ("light", "dark", "light"):
        with patch(
            "calendar_app.shared.system_theme.resolve_system_text_theme", return_value=system_mode
        ):
            tokens, _surface = _reading_surface(host)
            host.update_task_selection_status()
            host.show()
            app.processEvents()
            foreground = host.selection_status_lbl.palette().color(QPalette.ColorRole.WindowText)
            assert foreground == parse_css_color(tokens["text_primary"])
            colors.append(foreground.name())
    assert colors[0] == colors[2]
    assert colors[0] != colors[1]
    assert host.settings.value("text_theme") == "auto"
