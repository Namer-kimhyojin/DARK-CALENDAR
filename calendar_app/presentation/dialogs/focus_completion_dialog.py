from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from calendar_app.infrastructure.i18n import t
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

        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 35, 250);
                border: 2px solid {theme_color};
                border-radius: 20px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: white;
            }}
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(30, 30, 30, 30)

        # Trophy
        trophy_lbl = QLabel()
        trophy_lbl.setPixmap(_ic(ICON.FOCUS_DONE).pixmap(52, 52))
        trophy_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(trophy_lbl)

        # Title
        title_lbl = QLabel(t("focus.congrats_title", "Task Completed!"))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffd700;")
        container_layout.addWidget(title_lbl)

        # Message
        msg_lbl = QLabel(t("focus.congrats_msg", "Great focus. Your productivity is rising."))
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 14px; color: #c7d2e8;")
        container_layout.addWidget(msg_lbl)

        # Stats Sections
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setSpacing(15)

        # Current set stats
        curr_row = QHBoxLayout()
        curr_lbl = QLabel(t("focus.stat_current_set", "This Set:"))
        curr_lbl.setStyleSheet("font-weight: bold; color: white;")
        curr_data = QLabel(self._format_session_summary(self.sessions, self.total_secs))
        curr_data.setStyleSheet(
            f"color: {theme_color}; font-weight: bold; font-family: 'MS Gothic';"
        )
        curr_row.addWidget(curr_lbl)
        curr_row.addStretch()
        curr_row.addWidget(curr_data)
        stats_layout.addLayout(curr_row)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #444; height: 1px;")
        stats_layout.addWidget(line)

        # Today total stats
        today_row = QHBoxLayout()
        today_lbl = QLabel(t("focus.stat_today_total", "Today's Total:"))
        today_lbl.setStyleSheet("font-weight: bold; color: white;")
        today_data = QLabel(self._format_session_summary(self.today_sessions, self.today_secs))
        today_data.setStyleSheet(
            "color: #00ff7f; font-weight: bold; font-family: 'MS Gothic';"
        )  # SpringGreen
        today_row.addWidget(today_lbl)
        today_row.addStretch()
        today_row.addWidget(today_data)
        stats_layout.addLayout(today_row)

        # Separator line 2
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("background-color: #444; height: 1px;")
        stats_layout.addWidget(line2)

        # Monthly total stats
        month_row = QHBoxLayout()
        month_lbl = QLabel(t("focus.stat_month_total", "This Month's Total:"))
        month_lbl.setStyleSheet("font-weight: bold; color: white;")
        month_data = QLabel(self._format_session_summary(self.monthly_sessions, self.monthly_secs))
        month_data.setStyleSheet(
            "color: #ff9933; font-weight: bold; font-family: 'MS Gothic';"
        )  # Orange
        month_row.addWidget(month_lbl)
        month_row.addStretch()
        month_row.addWidget(month_data)
        stats_layout.addLayout(month_row)

        container_layout.addWidget(stats_widget)
        container_layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        self.break_btn = None
        if self.allow_long_break:
            self.break_btn = QPushButton(t("focus.start_long_break", "Start Long Break"))
            self.break_btn.setObjectName("focusCompletionLongBreakBtn")
            self.break_btn.setFixedSize(160, 45)
            self.break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.break_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {theme_color};
                    border: 2px solid {theme_color};
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {theme_color};
                    color: white;
                }}
            """)
            self.break_btn.clicked.connect(lambda: self.done(self.RESULT_START_LONG_BREAK))

        self.log_btn = None
        if self.show_log_button:
            self.log_btn = QPushButton(t("focus.view_logs", "View Focus Logs"))
            self.log_btn.setObjectName("focusCompletionLogBtn")
            self.log_btn.setFixedSize(160, 45)
            self.log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.log_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    color: #d7e0ef;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                    border-color: rgba(255, 255, 255, 0.32);
                }
            """)
            self.log_btn.clicked.connect(lambda: self.done(self.RESULT_VIEW_LOGS))

        # Confirm Button
        ok_text = (
            t("common.confirm", "Finish Session")
            if self.allow_long_break
            else t("focus.return_to_main", "Return to Calendar")
        )
        self.ok_btn = QPushButton(ok_text)
        self.ok_btn.setFixedSize(160, 45)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_color};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: white;
                color: {theme_color};
            }}
        """)
        self.ok_btn.clicked.connect(self.accept)

        btn_layout.addStretch()
        if self.break_btn is not None:
            btn_layout.addWidget(self.break_btn)
        if self.log_btn is not None:
            btn_layout.addWidget(self.log_btn)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addStretch()

        container_layout.addLayout(btn_layout)

        main_layout.addWidget(self.container)
        self.setFixedSize(400, 520)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
