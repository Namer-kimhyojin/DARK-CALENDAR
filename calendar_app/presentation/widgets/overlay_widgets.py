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
"""

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
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
]
