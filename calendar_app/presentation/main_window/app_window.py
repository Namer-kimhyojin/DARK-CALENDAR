"""Main application window shell."""

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMainWindow

from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
from calendar_app.presentation.main_window.app_initializer import initialize_overlay_app
from calendar_app.presentation.main_window.window_events import WindowEventsMixin
from calendar_app.presentation.main_window.window_ui_actions import (
    MainWindowUiActionsMixin,
    build_ui_font,
)


class OverlayApp(MainWindowUiActionsMixin, ActionHandlersMixin, WindowEventsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        initialize_overlay_app(self)

    def show_command_palette(self):
        if not hasattr(self, "command_palette"):
            return
        active = QApplication.activeWindow()
        target = active if active is not None and active is not self.command_palette else self
        try:
            rect = target.frameGeometry()
        except Exception:
            rect = target.geometry()
        self.command_palette.show_at_center(rect)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

    def handle_palette_command(self, cmd_id: str, params: dict):
        """Execute commands from the palette."""
        params = params or {}
        if cmd_id == "theme_dark":
            self.settings.setValue("text_theme", "dark")
            self.settings.setValue("panel_base_color", "#1c1c1c")
            if hasattr(self, "apply_theme_settings"):
                self.apply_theme_settings()
        elif cmd_id == "theme_light":
            self.settings.setValue("text_theme", "light")
            self.settings.setValue("panel_base_color", "#fefefe")
            if hasattr(self, "apply_theme_settings"):
                self.apply_theme_settings()
        elif cmd_id == "sync_google":
            if hasattr(self, "refresh_gcal_sync_state"):
                self.refresh_gcal_sync_state(force_push=True)
        elif cmd_id == "toggle_routine":
            if hasattr(self, "routine_dock"):
                self.routine_dock.setVisible(not self.routine_dock.isVisible())
        elif cmd_id == "toggle_schedule":
            if hasattr(self, "left_dock"):
                self.left_dock.setVisible(not self.left_dock.isVisible())
            if hasattr(self, "center_dock"):
                self.center_dock.setVisible(not self.center_dock.isVisible())
        elif cmd_id == "exit_app":
            from PyQt6.QtWidgets import QApplication

            QApplication.quit()
        elif cmd_id == "create_task_nlp":
            # NLP task creation logic
            try:
                from calendar_app.infrastructure.db import task_repo
                from calendar_app.infrastructure.i18n import t

                title = params.get("title", t("dialog.task.untitled", "제목 없음"))
                date_value = params.get("date")
                time_value = params.get("time") or "00:00:00"
                if hasattr(date_value, "toString"):
                    date_str = date_value.toString("yyyy-MM-dd")
                else:
                    date_str = str(date_value or QDate.currentDate().toString("yyyy-MM-dd"))[:10]
                if hasattr(time_value, "toString"):
                    time_str = time_value.toString("HH:mm:ss")
                else:
                    time_str = str(time_value or "00:00:00")
                    if len(time_str) == 5:
                        time_str = f"{time_str}:00"

                # Create as task
                task_id = task_repo.create_unified_task(
                    {
                        "name": title,
                        "deadline": f"{date_str} {time_str}",
                        "status": "todo",
                        "type": "schedule",
                        "calendar_id": "local::기본",
                    }
                )
                if hasattr(self, "schedule_panel_refresh"):
                    self.schedule_panel_refresh(left=True, center=True, right=True)

                # Show localized feedback
                if hasattr(self, "show_toast"):
                    msg = t("palette.task_registered", "Registered: {title}").format(title=title)
                    self.show_toast(t("palette.title", "Command Palette"), msg)
            except Exception as e:
                print(f"Failed to create task via NLP: {e}")
        elif cmd_id == "open_task_record":
            task_id = params.get("task_id")
            if task_id is not None and hasattr(self, "open_modify_task_dialog"):
                self.open_modify_task_dialog(int(task_id), 0)
        elif cmd_id == "open_directive_record":
            directive_id = params.get("directive_id")
            if directive_id is not None and hasattr(self, "open_directive_dialog"):
                self.open_directive_dialog(int(directive_id))
        elif cmd_id == "jump_to_date":
            date_str = str(params.get("date") or "")
            qdate = QDate.fromString(date_str[:10], "yyyy-MM-dd")
            if qdate.isValid():
                self.current_date = qdate
                if hasattr(self, "schedule_panel_refresh"):
                    self.schedule_panel_refresh(left=True, center=True, right=True)


__all__ = ["OverlayApp", "build_ui_font"]
