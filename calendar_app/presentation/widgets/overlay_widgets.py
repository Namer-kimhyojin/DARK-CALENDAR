# -*- coding: utf-8 -*-
"""Re-export shim: aggregates all overlay widget classes into one import target.

Usage::

    from calendar_app.presentation.widgets.overlay_widgets import (
        OverlayClockWidget,
        OverlayStopwatchWidget,
        OverlayDateCardWidget,
        OverlayCountdownWidget,
        OverlayDDayWidget,
        OverlayTextWidget,
    )

Each class is imported on first access through the module ``__getattr__`` (PEP 562),
so creating one widget type no longer imports the other eight modules (the KeyDeck
module alone took about 28 ms). The branches must stay static ``from ... import``
statements: PyInstaller only bundles modules it sees as import statements, so do not
replace them with ``importlib`` and computed names. A new widget type needs a branch
here as well as its ``_WIDGET_TYPES`` entry in ``overlay_manager.py``.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
    from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
    from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
    from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
    from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
    from calendar_app.presentation.widgets.overlay_loop_deck import OverlayLoopDeckWidget
    from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
    from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
    from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

__all__ = [
    "OverlayClockWidget",
    "OverlayStopwatchWidget",
    "OverlayDateCardWidget",
    "OverlayCountdownWidget",
    "OverlayDDayWidget",
    "OverlayTextWidget",
    "OverlayWeatherWidget",
    "OverlayLauncherDeckWidget",
    "OverlayLoopDeckWidget",
]


def __getattr__(name: str):
    if name == "OverlayClockWidget":
        from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget as value
    elif name == "OverlayCountdownWidget":
        from calendar_app.presentation.widgets.overlay_countdown import (
            OverlayCountdownWidget as value,
        )
    elif name == "OverlayDateCardWidget":
        from calendar_app.presentation.widgets.overlay_datecard import (
            OverlayDateCardWidget as value,
        )
    elif name == "OverlayDDayWidget":
        from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget as value
    elif name == "OverlayLauncherDeckWidget":
        from calendar_app.presentation.widgets.overlay_launcher_deck import (
            OverlayLauncherDeckWidget as value,
        )
    elif name == "OverlayLoopDeckWidget":
        from calendar_app.presentation.widgets.overlay_loop_deck import (
            OverlayLoopDeckWidget as value,
        )
    elif name == "OverlayStopwatchWidget":
        from calendar_app.presentation.widgets.overlay_stopwatch import (
            OverlayStopwatchWidget as value,
        )
    elif name == "OverlayTextWidget":
        from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget as value
    elif name == "OverlayWeatherWidget":
        from calendar_app.presentation.widgets.overlay_weather import (
            OverlayWeatherWidget as value,
        )
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # Cache the class so later lookups no longer reach this function.
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
