# -*- coding: utf-8 -*-

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic


class FocusCompletionDialog(QDialog):
    RESULT_START_LONG_BREAK = 10
    RESULT_VIEW_LOGS = 11

    def __init__(
        self,
        parent=None,
        sessions=0,
        total_secs=0,
        today_sessions=0,
        today_secs=0,
        monthly_sessions=0,
        monthly_secs=0,
        *,
        allow_long_break: bool = True,
        show_log_button: bool = True,
    ):
        super().__init__(parent)
        self.sessions = sessions
        self.total_secs = total_secs
        self.today_sessions = max(sessions, today_sessions)
        self.today_secs = max(total_secs, today_secs)
        self.monthly_sessions = max(self.today_sessions, monthly_sessions)
        self.monthly_secs = max(self.today_secs, monthly_secs)
        self.allow_long_break = bool(allow_long_break)
        self.show_log_button = bool(show_log_button)
        self._setup_ui()

    def _format_time_best(self, s: int) -> str:
        m, sec = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return t("focus.duration_hours_minutes", "{hours}h {minutes}m", hours=h, minutes=m)
        if m > 0:
            return t(
                "focus.duration_minutes_seconds", "{minutes}m {seconds}s", minutes=m, seconds=sec
            )
        return t("focus.duration_seconds", "{seconds}s", seconds=sec)

    def _format_session_summary(self, sessions: int, total_secs: int) -> str:
        return t(
            "focus.session_summary",
            "{sessions} sessions / {duration}",
            sessions=sessions,
            duration=self._format_time_best(total_secs),
        )

    def _setup_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        theme_color = "#4da6ff"
        if self.parent() and hasattr(self.parent(), "settings"):
            theme_color = self.parent().settings.value("theme_color", "#4da6ff")
        tokens = get_dialog_theme_tokens(
            theme_color=theme_color,
            settings=getattr(self.parent(), "settings", None),
        )
        self._ui_tokens = tokens
        theme_color = tokens.get("accent", theme_color)
        accent_display = tokens.get("tab_text_active", theme_color)
        accent_text = tokens.get("accent_text", "#101318")
        surface_bg = tokens.get("surface_bg", "#1e1e23")
        surface_item = tokens.get("surface_item", "#16161c")
        surface_hover = tokens.get("surface_hover", "#282832")
        text_primary = tokens.get("text_primary", "#f5f7fb")
        text_secondary = tokens.get("text_secondary", "#c7d2e8")
        border = tokens.get("border", "rgba(255,255,255,0.18)")
        border_soft = tokens.get("border_soft", "rgba(255,255,255,0.12)")
        accent_soft_border = tokens.get("accent_soft_border", border_soft)

        self.setAccessibleName(t("focus.congrats_title", "Task Completed!"))
        self.setAccessibleDescription(
            t("focus.congrats_msg", "Great focus. Your productivity is rising.")
        )

        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: {surface_bg};
                border: 1px solid {accent_soft_border};
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {text_primary};
            }}
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(28, 26, 28, 26)
        container_layout.setSpacing(10)

        # 완료 상태는 한 가지 강조색으로만 표시하고, 정보 수치는 명도 차로 구분한다.
        trophy_lbl = QLabel()
        trophy_lbl.setPixmap(_ic(ICON.FOCUS_DONE, color=accent_display).pixmap(48, 48))
        trophy_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trophy_lbl.setAccessibleName(t("focus.congrats_title", "Task Completed!"))
        container_layout.addWidget(trophy_lbl)

        title_lbl = QLabel(t("focus.congrats_title", "Task Completed!"))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setObjectName("dialogTitle")
        title_lbl.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {text_primary};")
        container_layout.addWidget(title_lbl)

        msg_lbl = QLabel(t("focus.congrats_msg", "Great focus. Your productivity is rising."))
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"font-size: 14px; color: {text_secondary};")
        container_layout.addWidget(msg_lbl)

        # Stats Sections
        stats_widget = QWidget()
        self.stats_widget = stats_widget
        stats_widget.setObjectName("focusCompletionStats")
        stats_widget.setStyleSheet(
            f"QWidget#focusCompletionStats {{ background: {surface_item}; "
            f"border: 1px solid {border_soft}; border-radius: 12px; }}"
        )
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(16, 12, 16, 12)
        stats_layout.setSpacing(10)

        # Current set stats
        curr_row = QHBoxLayout()
        curr_lbl = QLabel(t("focus.stat_current_set", "This Set:"))
        curr_lbl.setStyleSheet(f"font-weight: 600; color: {text_secondary};")
        curr_data = QLabel(self._format_session_summary(self.sessions, self.total_secs))
        self.current_value_label = curr_data
        curr_data.setStyleSheet(f"color: {accent_display}; font-weight: 700;")
        curr_row.addWidget(curr_lbl)
        curr_row.addStretch()
        curr_row.addWidget(curr_data)
        stats_layout.addLayout(curr_row)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {border_soft}; height: 1px;")
        stats_layout.addWidget(line)

        # Today total stats
        today_row = QHBoxLayout()
        today_lbl = QLabel(t("focus.stat_today_total", "Today's Total:"))
        today_lbl.setStyleSheet(f"font-weight: 600; color: {text_secondary};")
        today_data = QLabel(self._format_session_summary(self.today_sessions, self.today_secs))
        self.today_value_label = today_data
        today_data.setStyleSheet(f"color: {text_primary}; font-weight: 700;")
        today_row.addWidget(today_lbl)
        today_row.addStretch()
        today_row.addWidget(today_data)
        stats_layout.addLayout(today_row)

        # Separator line 2
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"background-color: {border_soft}; height: 1px;")
        stats_layout.addWidget(line2)

        # Monthly total stats
        month_row = QHBoxLayout()
        month_lbl = QLabel(t("focus.stat_month_total", "This Month's Total:"))
        month_lbl.setStyleSheet(f"font-weight: 600; color: {text_secondary};")
        month_data = QLabel(self._format_session_summary(self.monthly_sessions, self.monthly_secs))
        self.month_value_label = month_data
        month_data.setStyleSheet(f"color: {text_primary}; font-weight: 700;")
        month_row.addWidget(month_lbl)
        month_row.addStretch()
        month_row.addWidget(month_data)
        stats_layout.addLayout(month_row)

        container_layout.addWidget(stats_widget)
        container_layout.addSpacing(4)

        # Buttons
        secondary_btn_layout = QHBoxLayout()
        secondary_btn_layout.setSpacing(10)

        self.break_btn = None
        if self.allow_long_break:
            self.break_btn = QPushButton(t("focus.start_long_break", "Start Long Break"))
            self.break_btn.setObjectName("focusCompletionLongBreakBtn")
            self.break_btn.setMinimumHeight(44)
            self.break_btn.setMinimumWidth(140)
            self.break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.break_btn.setAccessibleName(self.break_btn.text())
            self.break_btn.setAutoDefault(False)
            self.break_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {accent_display};
                    border: 1px solid {accent_soft_border};
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: {theme_color};
                    color: {accent_text};
                }}
            """)
            self.break_btn.clicked.connect(lambda: self.done(self.RESULT_START_LONG_BREAK))
            secondary_btn_layout.addWidget(self.break_btn, 1)

        self.log_btn = None
        if self.show_log_button:
            self.log_btn = QPushButton(t("focus.view_logs", "View Focus Logs"))
            self.log_btn.setObjectName("focusCompletionLogBtn")
            self.log_btn.setMinimumHeight(44)
            self.log_btn.setMinimumWidth(140)
            self.log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.log_btn.setAccessibleName(self.log_btn.text())
            self.log_btn.setAutoDefault(False)
            self.log_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {surface_item};
                    color: {text_secondary};
                    border: 1px solid {border};
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: {surface_hover};
                    color: {text_primary};
                    border-color: {theme_color};
                }}
            """)
            self.log_btn.clicked.connect(lambda: self.done(self.RESULT_VIEW_LOGS))
            secondary_btn_layout.addWidget(self.log_btn, 1)

        # Confirm Button
        ok_text = (
            t("common.confirm", "Finish Session")
            if self.allow_long_break
            else t("focus.return_to_main", "Return to Calendar")
        )
        self.ok_btn = QPushButton(ok_text)
        self.ok_btn.setObjectName("primary_btn")
        self.ok_btn.setMinimumHeight(46)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setAccessibleName(ok_text)
        self.ok_btn.setDefault(True)
        self.ok_btn.setAutoDefault(True)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_color};
                color: {accent_text};
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {tokens.get("accent_hover", theme_color)};
                color: {accent_text};
            }}
        """)
        self.ok_btn.clicked.connect(self.accept)

        if secondary_btn_layout.count():
            container_layout.addLayout(secondary_btn_layout)
        container_layout.addWidget(self.ok_btn)

        main_layout.addWidget(self.container)
        self.setMinimumWidth(440)
        self.resize(460, 500)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
