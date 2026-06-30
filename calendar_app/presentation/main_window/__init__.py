"""Main-window composition and event adapters."""

from .action_handlers import ActionHandlersMixin
from .action_handlers_gcal import GCalActionsMixin
from .action_handlers_tasks import TaskActionsMixin
from .app_initializer import initialize_overlay_app
from .app_window import OverlayApp
from .away_lock_actions import AwayLockMixin
from .calendar_view_actions import CalendarViewActionsMixin
from .refresh_scheduler import RefreshSchedulerMixin
from .routine_actions import RoutineActionsMixin
from .theme_actions import ThemeActionsMixin
from .window_events import WindowEventsMixin
from .window_shell_actions import WindowShellActionsMixin
from .window_ui_actions import MainWindowUiActionsMixin, build_ui_font

__all__ = [
    "OverlayApp",
    "ActionHandlersMixin",
    "GCalActionsMixin",
    "TaskActionsMixin",
    "initialize_overlay_app",
    "AwayLockMixin",
    "CalendarViewActionsMixin",
    "WindowShellActionsMixin",
    "RoutineActionsMixin",
    "ThemeActionsMixin",
    "MainWindowUiActionsMixin",
    "build_ui_font",
    "RefreshSchedulerMixin",
    "WindowEventsMixin",
]
