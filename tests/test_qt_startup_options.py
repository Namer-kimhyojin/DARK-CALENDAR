# -*- coding: utf-8 -*-
"""Startup selection contracts without Qt, device, DB or settings initialization."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys

import pytest

from calendar_app.infrastructure.runtime.qt_startup_options import resolve_qt_startup_options


def test_windows_unspecified_platform_selects_process_only_gdi_and_preserves_inputs():
    arguments = ["Air Calendar.exe", "--restore", "saved layout"]
    environment = {"UNRELATED": "keep exactly"}
    result = resolve_qt_startup_options(arguments, environment, "win32")
    assert result.argv == (*arguments, "-platform", "windows:fontengine=gdi")
    assert result.font_engine == "gdi" and result.source == "windows_default" and result.changed
    assert arguments == ["Air Calendar.exe", "--restore", "saved layout"]
    assert environment == {"UNRELATED": "keep exactly"}
    with pytest.raises(FrozenInstanceError):
        result.changed = False


@pytest.mark.parametrize("platform", ["linux", "darwin", "cygwin", "win64", ""])
@pytest.mark.parametrize("diagnostic", ["gdi", "directwrite", "invalid"])
def test_non_windows_never_forces_a_qpa_plugin(platform, diagnostic):
    arguments = ["app", "--other"]
    result = resolve_qt_startup_options(
        arguments, {"AIR_CALENDAR_FONT_ENGINE": diagnostic}, platform
    )
    assert result.argv == tuple(arguments) and not result.changed
    assert result.reason == "non_windows_unchanged"


@pytest.mark.parametrize("flag", ["-platform", "--platform", "-platform=", "--platform="])
@pytest.mark.parametrize(
    "platform_argument",
    [
        "offscreen",
        "minimal",
        "windows",
        "windows:darkmode=2",
        "windows:fontengine=freetype:darkmode=2",
        "windows:fontengine=gdi",
        "windows:fontengine=native",
        "windows:fontengine=custom",
        "windows;offscreen",
    ],
)
def test_explicit_cli_is_preserved_even_with_competing_diagnostic(flag, platform_argument):
    arguments = (
        ["app", flag + platform_argument]
        if flag.endswith("=")
        else ["app", flag, platform_argument]
    )
    environment = {"QT_QPA_PLATFORM": "minimal", "AIR_CALENDAR_FONT_ENGINE": "directwrite"}
    result = resolve_qt_startup_options(arguments, environment, "win32")
    assert result.argv == tuple(arguments) and not result.changed
    assert result.source == "command_line"


@pytest.mark.parametrize(
    "value",
    [
        "offscreen",
        "minimal",
        "windows:darkmode=2",
        "windows:fontengine=gdi",
        "windows:fontengine=native",
        "windows:fontengine=unknown",
        "minimal;windows",
    ],
)
def test_explicit_environment_platform_beats_application_default_or_diagnostic(value):
    environment = {"QT_QPA_PLATFORM": value, "AIR_CALENDAR_FONT_ENGINE": "gdi"}
    result = resolve_qt_startup_options(["app"], environment, "win32")
    assert result.argv == ("app",) and not result.changed
    assert result.source == "environment"
    assert environment["QT_QPA_PLATFORM"] == value


@pytest.mark.parametrize(
    "environment",
    [
        {"QT_QPA_PLATFORM_PLUGIN_PATH": "C:/Bundle/PyQt6/Qt6/plugins"},
        {"QT_PLUGIN_PATH": "C:/Bundle/plugins"},
        {"QT_QPA_PLATFORM_PLUGIN_PATH": "", "QT_QPA_PLATFORMTHEME": "custom"},
    ],
)
def test_plugin_paths_remain_verbatim_and_do_not_disable_packaged_optimization(environment):
    before = dict(environment)
    result = resolve_qt_startup_options(["app"], environment, "win32")
    assert result.argv == ("app", "-platform", "windows:fontengine=gdi")
    assert environment == before


@pytest.mark.parametrize(
    "flag",
    [
        "-platformpluginpath",
        "--platformpluginpath",
        "-platformpluginpath=",
        "--platformpluginpath=",
    ],
)
def test_explicit_plugin_path_cli_is_orthogonal_to_font_selection(flag):
    value = "C:/Frozen App/PyQt6/Qt6/plugins"
    arguments = ["app", flag + value] if flag.endswith("=") else ["app", flag, value]
    result = resolve_qt_startup_options(arguments, {}, "win32")
    assert result.argv == (*arguments, "-platform", "windows:fontengine=gdi")


@pytest.mark.parametrize(
    "value,engine,reason,argument",
    [
        ("gdi", "gdi", "gdi_requested", "windows:fontengine=gdi"),
        (" GDI ", "gdi", "gdi_requested", "windows:fontengine=gdi"),
        ("directwrite", "directwrite", "directwrite_native_alias", "windows:fontengine=native"),
    ],
)
def test_diagnostic_engine_uses_only_supported_qt_tokens(value, engine, reason, argument):
    result = resolve_qt_startup_options(["app"], {"AIR_CALENDAR_FONT_ENGINE": value}, "win32")
    assert result.argv == ("app", "-platform", argument)
    assert result.font_engine == engine and result.reason == reason
    assert "fontengine=directwrite" not in " ".join(result.argv)


@pytest.mark.parametrize(
    "value",
    [
        "default",
        " DEFAULT ",
        "",
        " ",
        "freetype",
        "gdii",
        "gdi:darkmode=2",
        "default;offscreen",
        None,
        1,
    ],
)
def test_optout_or_invalid_diagnostic_leaves_default_path_and_environment_untouched(value):
    environment = {"AIR_CALENDAR_FONT_ENGINE": value}
    result = resolve_qt_startup_options(["app", "--keep"], environment, "win32")
    assert result.argv == ("app", "--keep") and not result.changed
    assert result.font_engine is None
    assert environment == {"AIR_CALENDAR_FONT_ENGINE": value}


def test_empty_environment_platform_is_qt_default_and_missing_cli_value_is_preserved():
    assert resolve_qt_startup_options(["app"], {"QT_QPA_PLATFORM": ""}, "win32").changed
    result = resolve_qt_startup_options(["app", "-platform"], {}, "win32")
    assert result.argv == ("app", "-platform") and not result.changed
    assert result.reason == "explicit_platform_preserved"


def test_second_application_or_child_resolution_never_duplicates_platform_flags():
    first = resolve_qt_startup_options(["app", "--restart"], {}, "win32")
    second = resolve_qt_startup_options(first.argv, {}, "win32")
    assert second.argv == first.argv and second.argv.count("-platform") == 1
    assert second.font_engine == "gdi" and not second.changed


def test_last_explicit_platform_wins_for_diagnostic_reporting_without_rewriting_anything():
    arguments = ["app", "-platform", "windows:fontengine=gdi", "--platform", "offscreen"]
    result = resolve_qt_startup_options(arguments, {}, "win32")
    assert result.argv == tuple(arguments) and result.font_engine is None


def test_empty_argv_does_not_put_an_option_in_program_name_position():
    result = resolve_qt_startup_options([], {}, "win32")
    assert result.argv == () and result.reason == "empty_argv_unchanged"


def test_importing_and_resolving_in_an_isolated_child_does_not_import_qt_or_touch_environment(
    tmp_path,
):
    path = (
        Path(__file__).resolve().parents[1]
        / "calendar_app/infrastructure/runtime/qt_startup_options.py"
    )
    script = """
import importlib.util, json, os, sys
sys.dont_write_bytecode = True
before = dict(os.environ)
spec = importlib.util.spec_from_file_location('startup_options_isolated', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
selection = module.resolve_qt_startup_options(['app'], {}, 'win32')
assert before == dict(os.environ)
assert not any(name.startswith(('PyQt6', 'sqlite3', 'calendar_app.app_paths')) for name in sys.modules)
print(json.dumps({'argv': selection.argv, 'font_engine': selection.font_engine}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "argv": ["app", "-platform", "windows:fontengine=gdi"],
        "font_engine": "gdi",
    }
