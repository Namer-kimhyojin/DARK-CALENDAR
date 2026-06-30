"""Top-menu group builders."""

from .display_menu import build_display_menu
from .register_menu import build_register_menu
from .system_menu import build_system_menu
from .widgets_menu import build_widgets_menu_btn
from .work_menu import build_work_menu

__all__ = [
    "build_register_menu",
    "build_work_menu",
    "build_display_menu",
    "build_system_menu",
    "build_widgets_menu_btn",
]
