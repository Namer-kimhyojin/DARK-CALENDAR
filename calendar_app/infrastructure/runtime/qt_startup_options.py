# -*- coding: utf-8 -*-
"""Pure, process-local Qt startup arguments; no Qt or environment side effects.

Qt 6.12 supports ``windows:fontengine=gdi`` and ``fontengine=native``.
The diagnostic name ``directwrite`` maps to ``native``: Qt selects its native
DirectWrite database when that support is built in. We never emit the unsupported
``fontengine=directwrite`` token. See qtbase v6.12.0 qwindowsintegration.cpp.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class QtStartupOptions:
    argv: tuple[str, ...]
    font_engine: str | None
    source: str
    reason: str
    changed: bool = False


def _explicit_platform(argv):
    selected = None
    found = False
    for index, argument in enumerate(argv[1:], 1):
        if argument in ("-platform", "--platform"):
            found = True
            selected = argv[index + 1] if index + 1 < len(argv) else None
        elif argument.startswith(("-platform=", "--platform=")):
            found = True
            selected = argument.split("=", 1)[1]
    return found, selected


def _declared_engine(platform_argument):
    if not isinstance(platform_argument, str):
        return None
    # A platform fallback list must also remain completely untouched.
    primary = platform_argument.split(";", 1)[0].split(":")
    if not primary or primary[0].lower() != "windows":
        return None
    for option in reversed(primary[1:]):
        if option.startswith("fontengine="):
            return option.split("=", 1)[1]
    return None


def resolve_qt_startup_options(
    argv: Sequence[str], environ: Mapping[str, str], platform: str
) -> QtStartupOptions:
    """Resolve an immutable QApplication argv without changing either input.

    Explicit CLI platforms take precedence over QT_QPA_PLATFORM, which takes
    precedence over the application's default or diagnostic engine. Plugin search
    paths are independent: preserve them verbatim, including PyInstaller's paths.
    Only an unspecified Windows platform gets an additional argument pair.
    ``AIR_CALENDAR_FONT_ENGINE=default`` or an invalid value leaves Qt untouched.
    """
    arguments = tuple(argv)
    if any(not isinstance(value, str) for value in arguments):
        raise TypeError("Qt arguments must contain strings")
    if platform != "win32":
        return QtStartupOptions(arguments, None, "platform", "non_windows_unchanged")

    explicit, value = _explicit_platform(arguments)
    if explicit:
        return QtStartupOptions(
            arguments, _declared_engine(value), "command_line", "explicit_platform_preserved"
        )
    value = environ.get("QT_QPA_PLATFORM")
    if value:
        return QtStartupOptions(
            arguments, _declared_engine(value), "environment", "explicit_platform_preserved"
        )
    if not arguments:
        return QtStartupOptions(arguments, None, "arguments", "empty_argv_unchanged")

    diagnostic = environ.get("AIR_CALENDAR_FONT_ENGINE")
    if "AIR_CALENDAR_FONT_ENGINE" in environ:
        requested = diagnostic.strip().lower() if isinstance(diagnostic, str) else ""
        if requested not in ("default", "gdi", "directwrite"):
            return QtStartupOptions(
                arguments, None, "diagnostic_override", "invalid_override_default"
            )
        if requested == "default":
            return QtStartupOptions(arguments, None, "diagnostic_override", "qt_default_requested")
        engine = "native" if requested == "directwrite" else "gdi"
        return QtStartupOptions(
            (*arguments, "-platform", "windows:fontengine=" + engine),
            requested,
            "diagnostic_override",
            "directwrite_native_alias" if requested == "directwrite" else "gdi_requested",
            True,
        )
    return QtStartupOptions(
        (*arguments, "-platform", "windows:fontengine=gdi"),
        "gdi",
        "windows_default",
        "windows_startup_compatibility",
        True,
    )


__all__ = ["QtStartupOptions", "resolve_qt_startup_options"]
