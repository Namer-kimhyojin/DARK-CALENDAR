from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import focus_usecases
from calendar_app.application.pomodoro_engine import (
    PHASE_FOCUS,
    PHASE_LONG_BREAK,
    PomodoroEngine,
)
from calendar_app.infrastructure.db import checklist_repo, legacy_focus_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

try:
    from PyQt6 import sip
except Exception:
    import sip  # type: ignore

from calendar_app.presentation.dialogs.focus_completion_dialog import FocusCompletionDialog

FOCUS_MODE_POMODORO = "pomodoro"
FOCUS_MODE_STOPWATCH = "stopwatch"


def _is_widget_alive(widget):
    try:
        return widget is not None and not sip.isdeleted(widget)
    except Exception:
        return False


def _safe_int_setting(
    settings, key: str, default: int, *, minimum: int = 1, maximum: int = 240
) -> int:
    raw = settings.value(key, default) if settings is not None else default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = int(default)
    return max(minimum, min(maximum, value))


def _safe_bool_setting(settings, key: str, default: bool) -> bool:
    if settings is None:
        return default
    from calendar_app.shared.value_parsers import as_bool

    return as_bool(settings.value(key, default), default=default)


def _load_focus_timer_settings(app) -> dict:
    settings = getattr(app, "settings", None)
    mode_raw = str(
        settings.value("focus_mode_type", FOCUS_MODE_POMODORO)
        if settings is not None
        else FOCUS_MODE_POMODORO
    )
    mode_raw = mode_raw.strip().lower()
    mode = FOCUS_MODE_STOPWATCH if mode_raw == FOCUS_MODE_STOPWATCH else FOCUS_MODE_POMODORO
    return {
        "mode": mode,
        "focus_minutes": _safe_int_setting(
            settings, "pomodoro_focus_minutes", 25, minimum=1, maximum=180
        ),
        "short_break_minutes": _safe_int_setting(
            settings, "pomodoro_short_break_minutes", 5, minimum=1, maximum=60
        ),
        "long_break_minutes": _safe_int_setting(
            settings, "pomodoro_long_break_minutes", 15, minimum=1, maximum=120
        ),
        "long_break_every": _safe_int_setting(
            settings, "pomodoro_long_break_every", 4, minimum=2, maximum=12
        ),
        "goal_sessions": _safe_int_setting(
            settings, "pomodoro_daily_goal_cycles", 4, minimum=1, maximum=20
        ),
        "auto_start_break": _safe_bool_setting(settings, "pomodoro_auto_start_break", True),
        "auto_start_focus": _safe_bool_setting(settings, "pomodoro_auto_start_focus", True),
    }


def _clear_focus_frame_layout(app) -> None:
    if app.focus_frame.layout() is None:
        return
    old_layout = app.focus_frame.layout()
    while old_layout.count():
        item = old_layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.deleteLater()
    QWidget().setLayout(old_layout)


def _ensure_focus_timer(app):
    if not hasattr(app, "_focus_timer") or app._focus_timer is None:
        app._focus_timer = QTimer(app)
        app._focus_timer.timeout.connect(lambda: update_focus_timer(app))
    return app._focus_timer


def _format_mmss(total_secs: int) -> str:
    minutes, seconds = divmod(max(0, int(total_secs or 0)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _open_focus_log_dialog(app) -> None:
    try:
        from calendar_app.presentation.dialogs.focus_log_dialog import FocusLogDialog

        dlg = FocusLogDialog(app)
        dlg.exec()
    except Exception as exc:
        print(f"Failed to open focus log dialog: {exc}")


def _focus_phase_label(snapshot) -> str:
    if snapshot.phase == PHASE_FOCUS:
        phase = t("focus.phase_focus", "Focus")
    elif snapshot.phase == PHASE_LONG_BREAK:
        phase = t("focus.phase_long_break", "Long Break")
    else:
        phase = t("focus.phase_short_break", "Short Break")

    phase_text = t(
        "focus.phase_with_cycle",
        "{phase} {current}/{total}",
        phase=phase,
        current=snapshot.current_focus_index,
        total=snapshot.cycle_size,
    )
    if snapshot.paused:
        return t("focus.phase_paused", "{phase} (Paused)", phase=phase_text)
    return phase_text


def _persist_stopwatch_log(app) -> None:
    elapsed_secs = int(getattr(app, "_focus_elapsed_secs", 0) or 0)
    task_id = getattr(app, "_focus_task_id", None)
    if elapsed_secs <= 0 or not task_id:
        return
    if focus_usecases.persist_focus_log(legacy_focus_repo, task_id, elapsed_secs):
        app.show_toast(
            t("focus.toast_title"),
            t(
                "focus.toast_msg",
                minutes=elapsed_secs // 60,
                seconds=elapsed_secs % 60,
            ),
        )


def _persist_completed_pomodoro_focus(app, duration_secs: int) -> None:
    """Save the focus session and update the session counters."""
    task_id = getattr(app, "_focus_task_id", None)

    # Validation
    if not task_id:
        print("[Focus] Warning: Missing task_id, cannot persist focus session.")
        return
    if duration_secs <= 0:
        print(f"[Focus] skipping persistence for 0s session (task_id={task_id})")
        return

    print(f"[Focus] Persisting session: task_id={task_id}, duration={duration_secs}s")

    try:
        if focus_usecases.persist_focus_log(legacy_focus_repo, task_id, duration_secs):
            # Update local counters
            app._focus_sessions_saved = int(getattr(app, "_focus_sessions_saved", 0) or 0) + 1
            app._focus_saved_secs = int(getattr(app, "_focus_saved_secs", 0) or 0) + duration_secs

            print(f"[Focus] Success: Total saved in this run: {app._focus_sessions_saved} sessions")

            app.show_toast(
                t("focus.session_saved_title", "Focus session saved"),
                t(
                    "focus.session_saved_msg",
                    "Saved {minutes}m {seconds}s for current task.",
                    minutes=duration_secs // 60,
                    seconds=duration_secs % 60,
                ),
            )
        else:
            print("[Focus] Error: Database persistence failed in focus_usecases.")
    except Exception as e:
        print(f"[Focus] Exception during persistence: {e}")


def _render_pomodoro_state(app) -> None:
    pomodoro = getattr(app, "_focus_pomodoro", None)
    if pomodoro is None:
        return

    snapshot = pomodoro.snapshot()

    # 1. Update Floating Status Capsule Badge Styles dynamically
    phase_lbl = getattr(app, "focus_phase_lbl", None)
    if _is_widget_alive(phase_lbl):
        phase_lbl.setText(_focus_phase_label(snapshot))
        if snapshot.phase == PHASE_FOCUS:
            phase_lbl.setStyleSheet(
                "QLabel {"
                "  font-size: 13px;"
                "  font-weight: 800;"
                "  padding: 4px 14px;"
                "  border-radius: 12px;"
                "  background: rgba(16, 185, 129, 0.08);"
                "  color: #10b981;"
                "  border: 1px solid rgba(16, 185, 129, 0.25);"
                "}"
            )
        else:
            phase_lbl.setStyleSheet(
                "QLabel {"
                "  font-size: 13px;"
                "  font-weight: 800;"
                "  padding: 4px 14px;"
                "  border-radius: 12px;"
                "  background: rgba(245, 158, 11, 0.08);"
                "  color: #f59e0b;"
                "  border: 1px solid rgba(245, 158, 11, 0.25);"
                "}"
            )

    # 2. Update Timer Label Text
    timer_lbl = getattr(app, "timer_lbl", None)
    if _is_widget_alive(timer_lbl):
        timer_lbl.setText(_format_mmss(snapshot.phase_remaining_secs))

    # 3. Update Neon Progress Bar percentage
    progress_bar = getattr(app, "focus_progress", None)
    if _is_widget_alive(progress_bar):
        elapsed = max(0, snapshot.phase_elapsed_secs)
        remaining = max(0, snapshot.phase_remaining_secs)
        total = elapsed + remaining
        percent = int((elapsed / total) * 100) if total > 0 else 0
        progress_bar.setValue(max(0, min(100, percent)))

    # 4. Update Focus Summary Text
    summary_lbl = getattr(app, "focus_summary_lbl", None)
    if _is_widget_alive(summary_lbl):
        mins, secs = divmod(snapshot.focus_secs_total, 60)
        summary_lbl.setText(
            t(
                "focus.pomodoro_summary",
                "Completed: {sessions} sessions | Focus: {minutes}m {seconds}s",
                sessions=snapshot.focus_sessions_completed,
                minutes=mins,
                seconds=secs,
            )
        )

    # 5. Toggle Play/Pause vector icons & tooltips
    pause_btn = getattr(app, "_focus_pause_btn", None)
    if _is_widget_alive(pause_btn):
        if snapshot.paused:
            pause_btn.setIcon(_ic(ICON.PLAY, color="#10b981"))
            pause_btn.setToolTip(t("focus.resume", "Resume"))
        else:
            pause_btn.setIcon(_ic(ICON.PAUSE, color="#f3f4f6"))
            pause_btn.setToolTip(t("focus.pause", "Pause"))

    # 6. Update Skip button tooltip
    skip_btn = getattr(app, "_focus_skip_btn", None)
    if _is_widget_alive(skip_btn):
        if snapshot.phase == PHASE_FOCUS:
            skip_btn.setToolTip(t("focus.skip_focus", "Skip Focus"))
        else:
            skip_btn.setToolTip(t("focus.skip_break", "Skip Break"))


def _notify_phase_change(app, phase: str) -> None:
    """Show a toast notification. We now upgrade this with an announcement overlay."""
    if phase == PHASE_FOCUS:
        title = t("focus.phase_focus_title", "Focus Time")
        msg = t("focus.phase_focus_msg", "Stay productive!")
        icon = ICON.POMODORO
    elif phase == PHASE_LONG_BREAK:
        title = t("focus.phase_long_break_title", "Long Break")
        msg = t("focus.phase_long_break_msg", "Well deserved rest.")
        icon = ICON.BREAK_LONG
    else:
        title = t("focus.phase_short_break_title", "Short Break")
        msg = t("focus.phase_short_break_msg", "Take a breather.")
        icon = ICON.BREAK_SHORT

    if hasattr(app, "show_toast"):
        app.show_toast(title, msg)

    _announce_phase_change(app, title, msg, icon)


def _announce_phase_change(app, title: str, msg: str, icon: str) -> None:
    """Show a phase-change toast popup (bottom-right, independent top-level window)."""
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
    from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect

    theme_color = "#4da6ff"
    if hasattr(app, "settings"):
        theme_color = app.settings.value("theme_color", "#4da6ff")

    # Independent top-level window — no parent, so it never overlaps the focus UI
    popup = QFrame(None)
    popup.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Tool
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    popup.setFixedSize(360, 90)

    popup.setStyleSheet(f"""
        QFrame {{
            background-color: rgba(18, 20, 30, 220);
            border: 1px solid {theme_color};
            border-radius: 12px;
        }}
        QLabel {{
            background: transparent;
            border: none;
        }}
    """)

    layout = QHBoxLayout(popup)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(14)

    icon_lbl = QLabel()
    icon_lbl.setPixmap(_ic(icon).pixmap(36, 36))
    icon_lbl.setFixedWidth(46)
    layout.addWidget(icon_lbl)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {theme_color};")
    msg_lbl = QLabel(msg)
    msg_lbl.setStyleSheet("font-size: 12px; color: #b0b8cc;")
    text_col.addWidget(title_lbl)
    text_col.addWidget(msg_lbl)
    layout.addLayout(text_col)

    # Position: bottom-right of the screen, above the taskbar
    screen = QApplication.primaryScreen()
    if screen is not None:
        sg = screen.availableGeometry()
        x = sg.right() - popup.width() - 24
        y = sg.bottom() - popup.height() - 24
    else:
        x, y = 1060, 960
    popup.move(x, y)
    popup.show()

    # Fade-out after 3 s display
    opacity_effect = QGraphicsOpacityEffect(popup)
    popup.setGraphicsEffect(opacity_effect)

    anim = QPropertyAnimation(opacity_effect, b"opacity")
    anim.setDuration(800)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InQuad)
    anim.finished.connect(popup.deleteLater)

    QTimer.singleShot(3000, anim.start)
    # Keep references to prevent GC
    popup._fade_anim = anim
    popup._opacity_effect = opacity_effect


def _process_pomodoro_events(app, events: list[dict]) -> None:
    """Central processing for engine events (logging and notifications)."""
    set_completed = any(e.get("type") == "pomodoro_set_completed" for e in events)

    for event in events:
        etype = event.get("type")
        if etype == "focus_session_completed":
            try:
                _persist_completed_pomodoro_focus(app, int(event.get("duration_secs", 0) or 0))
            except Exception as exc:
                print(f"[Focus] Error persisting session: {exc}")
        elif etype == "phase_changed" and not set_completed:
            new_phase = event.get("phase", "")
            try:
                _notify_phase_change(app, new_phase)
            except Exception as exc:
                print(f"[Focus] Error notifying phase change: {exc}")
            # Auto-start: pause engine when auto_start is off for the new phase
            _apply_auto_start_pause(app, new_phase)

    if set_completed:
        # Show graduation dialog - user can pick 'Finish' or 'Start Long Break'
        _exit_focus_mode(app, is_set_completed=True)


def _apply_auto_start_pause(app, new_phase: str) -> None:
    """Pause the engine if the user has disabled auto-start for the new phase."""
    from calendar_app.application.pomodoro_engine import PHASE_FOCUS as _PF

    settings = getattr(app, "settings", None)
    pomodoro = getattr(app, "_focus_pomodoro", None)
    if pomodoro is None:
        return

    if new_phase == _PF:
        # Entering a focus phase — check auto_start_focus
        auto = _safe_bool_setting(settings, "pomodoro_auto_start_focus", True)
    else:
        # Entering a break phase — check auto_start_break
        auto = _safe_bool_setting(settings, "pomodoro_auto_start_break", True)

    if not auto:
        pomodoro.pause()
        _render_pomodoro_state(app)


def _reset_focus_runtime_refs(app) -> None:
    if hasattr(app, "_focus_timer") and app._focus_timer is not None:
        app._focus_timer.stop()
        app._focus_timer = None

    app.timer_lbl = None
    app.focus_phase_lbl = None
    app.focus_summary_lbl = None
    app._focus_pause_btn = None
    app._focus_skip_btn = None
    app._focus_pomodoro = None
    app._focus_mode_type = FOCUS_MODE_POMODORO
    app._focus_task_id = None
    app._focus_elapsed_secs = 0
    app._focus_saved_secs = 0
    app._focus_sessions_saved = 0


def _build_focus_checklist_panel(app, layout):
    """현재 집중 중인 업무의 체크리스트 미니 패널을 생성하여 레이아웃에 탑재합니다."""
    task_id = getattr(app, "_focus_task_id", None)
    if not task_id:
        return

    # 타이틀 라벨
    checklist_title = QLabel(t("dialog.tabs.checklist", "체크리스트"))
    checklist_title.setStyleSheet(
        "color: rgba(255, 255, 255, 0.4); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;"
    )
    layout.addWidget(checklist_title, alignment=Qt.AlignmentFlag.AlignLeft)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFixedHeight(120)
    scroll.setStyleSheet(
        "QScrollArea { border: none; background: transparent; } QScrollBar:vertical { width: 4px; background: transparent; } QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 2px; }"
    )

    scroll_content = QWidget()
    scroll_content.setStyleSheet("background: transparent;")
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(8)
    scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    items = checklist_repo.get_task_checklist_items(task_id)
    if not items:
        empty_lbl = QLabel(t("dialog.label_settings.none_to_load", "체크리스트 항목이 없습니다."))
        empty_lbl.setStyleSheet(
            "color: rgba(255, 255, 255, 0.25); font-size: 12px; font-style: italic;"
        )
        scroll_layout.addWidget(empty_lbl)
    else:
        for item in items:
            cb = QCheckBox(item.get("item_text", ""))
            cb.setChecked(bool(item.get("is_completed", False)))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)

            # 초기 상태 스타일 지정
            if cb.isChecked():
                cb.setStyleSheet(
                    "QCheckBox { color: rgba(255,255,255,0.3); font-size: 13px; spacing: 8px; text-decoration: line-through; }"
                    "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #10b981; background: #10b981; }"
                )
            else:
                cb.setStyleSheet(
                    "QCheckBox { color: #d1d5db; font-size: 13px; spacing: 8px; }"
                    "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.18); background: rgba(0,0,0,0.2); }"
                )

            # 체크박스 변경 이벤트 바인딩
            link_id = item.get("id")

            def _make_toggle_handler(l_id, checkbox):
                def _handle(checked):
                    checklist_repo.toggle_checklist_item(l_id)
                    # 스타일 업데이트
                    if checked:
                        checkbox.setStyleSheet(
                            "QCheckBox { color: rgba(255,255,255,0.3); font-size: 13px; spacing: 8px; text-decoration: line-through; }"
                            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #10b981; background: #10b981; }"
                        )
                    else:
                        checkbox.setStyleSheet(
                            "QCheckBox { color: #d1d5db; font-size: 13px; spacing: 8px; }"
                            "QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.18); background: rgba(0,0,0,0.2); }"
                        )

                return _handle

            cb.toggled.connect(_make_toggle_handler(link_id, cb))
            scroll_layout.addWidget(cb)

    scroll.setWidget(scroll_content)
    layout.addWidget(scroll)


def _enter_focus_mode(app) -> None:
    if hasattr(app, "_focus_timer") and app._focus_timer is not None:
        app._focus_timer.stop()

    # Show task selector BEFORE hiding the calendar — dialog stays on top
    from calendar_app.presentation.dialogs.focus_task_selector import FocusTaskSelectorDialog

    selector_dlg = FocusTaskSelectorDialog(app.current_date, app)
    if selector_dlg.exec():
        app._focus_task_id, task_name = selector_dlg.get_selected_task()
        if not app._focus_task_id:
            if hasattr(app, "show_toast"):
                app.show_toast(
                    t("focus.error_title", "Unable to start"),
                    t("focus.error_no_task", "No task was selected for Focus Mode."),
                )
            app.is_focus_mode = False
            _reset_focus_runtime_refs(app)
            return
    else:
        app.is_focus_mode = False
        _reset_focus_runtime_refs(app)
        return

    # Task confirmed — now switch the main window to focus UI
    app.dock_manager.hide()
    _clear_focus_frame_layout(app)

    # 1. Main outer frame layout alignment to center the focus card
    frame_layout = QHBoxLayout(app.focus_frame)
    frame_layout.setContentsMargins(0, 0, 0, 0)
    frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 2. Modern Glassmorphic Focus Card Container
    card = QFrame()
    card.setObjectName("PremiumFocusCard")
    card.setStyleSheet(
        "QFrame#PremiumFocusCard {"
        "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a26, stop:1 #111118);"
        "  border: 1px solid rgba(255, 255, 255, 0.08);"
        "  border-radius: 20px;"
        "  min-width: 480px;"
        "  max-width: 520px;"
        "}"
    )

    layout = QVBoxLayout(card)
    layout.setContentsMargins(32, 28, 32, 28)
    layout.setSpacing(14)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    frame_layout.addWidget(card)

    # 3. Focus Title Header
    title = QLabel(t("focus.title"))
    title.setStyleSheet(
        "color: #ef4444; font-size: 20px; font-weight: 800; text-transform: uppercase; letter-spacing: 2px; background: transparent; border: none;"
    )
    layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

    # 4. Current Focusing Task Label
    task_lbl = QLabel(t("focus.current_task", task_name=task_name))
    task_lbl.setStyleSheet(
        "color: #f3f4f6; font-size: 16px; font-weight: 600; text-align: center; background: transparent; border: none;"
    )
    task_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(task_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
    layout.addSpacing(6)

    timer_settings = _load_focus_timer_settings(app)
    app._focus_mode_type = timer_settings["mode"]
    app._focus_elapsed_secs = 0
    app._focus_saved_secs = 0
    app._focus_sessions_saved = 0

    # 5. Build Pomodoro Elements if applicable
    if app._focus_mode_type == FOCUS_MODE_POMODORO:
        app._focus_pomodoro = PomodoroEngine(
            focus_minutes=timer_settings["focus_minutes"],
            short_break_minutes=timer_settings["short_break_minutes"],
            long_break_minutes=timer_settings["long_break_minutes"],
            long_break_every=timer_settings["long_break_every"],
            goal_sessions=timer_settings["goal_sessions"],
        )

        # Floating Status Capsule Badge
        app.focus_phase_lbl = QLabel()
        app.focus_phase_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.focus_phase_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Big Neon Blue Timer Label
        app.timer_lbl = QLabel("00:00")
        app.timer_lbl.setStyleSheet(
            "color: #3b82f6; font-size: 64px; font-weight: 800; font-family: 'Courier New', monospace; background: transparent; border: none;"
        )
        app.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.timer_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Neon Gradient Progress Bar
        app.focus_progress = QProgressBar()
        app.focus_progress.setTextVisible(False)
        app.focus_progress.setFixedHeight(6)
        app.focus_progress.setStyleSheet(
            "QProgressBar {"
            "  border: none;"
            "  background-color: rgba(255, 255, 255, 0.05);"
            "  border-radius: 3px;"
            "}"
            "QProgressBar::chunk {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #10b981);"
            "  border-radius: 3px;"
            "}"
        )
        layout.addWidget(app.focus_progress)
        layout.addSpacing(2)

        # Focus Summary Text
        app.focus_summary_lbl = QLabel()
        app.focus_summary_lbl.setStyleSheet(
            "color: #9ca3af; font-size: 13px; font-weight: 500; background: transparent; border: none;"
        )
        app.focus_summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.focus_summary_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(6)

        # Premium Rounded Control Button Bar (using qtawesome icons instead of emojis)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        app._focus_pause_btn = QPushButton()
        app._focus_pause_btn.setFixedSize(40, 40)
        app._focus_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        app._focus_pause_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(255, 255, 255, 0.05);"
            "  border: 1px solid rgba(255, 255, 255, 0.1);"
            "  border-radius: 20px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.12);"
            "  border-color: rgba(255, 255, 255, 0.2);"
            "}"
        )
        app._focus_pause_btn.clicked.connect(lambda: toggle_focus_pause(app))
        btn_row.addWidget(app._focus_pause_btn)

        app._focus_skip_btn = QPushButton()
        app._focus_skip_btn.setFixedSize(40, 40)
        app._focus_skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        app._focus_skip_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(255, 255, 255, 0.05);"
            "  border: 1px solid rgba(255, 255, 255, 0.1);"
            "  border-radius: 20px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.12);"
            "  border-color: rgba(255, 255, 255, 0.2);"
            "}"
        )
        app._focus_skip_btn.setIcon(_ic(ICON.FORWARD, color="#f3f4f6"))
        app._focus_skip_btn.clicked.connect(lambda: skip_focus_phase(app))
        btn_row.addWidget(app._focus_skip_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addSpacing(4)

        _render_pomodoro_state(app)
        exit_text = t(
            "focus.exit_hint_pomodoro",
            "Stop Focus Mode with [Ctrl+Space / Ctrl+F].",
        )
    else:
        app._focus_pomodoro = None

        # Big Neon Blue Timer Label for Stopwatch
        app.timer_lbl = QLabel("00:00")
        app.timer_lbl.setStyleSheet(
            "color: #3b82f6; font-size: 60px; font-weight: 800; font-family: 'Courier New', monospace; background: transparent; border: none;"
        )
        app.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.timer_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(14)
        exit_text = t("focus.exit_hint")

    # 6. Quick Checklist Mini-Panel integration
    layout.addSpacing(4)
    _build_focus_checklist_panel(app, layout)
    layout.addSpacing(10)

    # 7. Bottom Action & Navigation Buttons
    exit_info = QLabel(exit_text)
    exit_info.setStyleSheet(
        "color: #6b7280; font-size: 12px; background: transparent; border: none;"
    )
    layout.addWidget(exit_info, alignment=Qt.AlignmentFlag.AlignCenter)
    layout.addSpacing(4)

    action_row = QHBoxLayout()
    action_row.setSpacing(10)
    action_row.addStretch()

    log_btn = QPushButton(t("focus.view_logs", "View Focus Logs"))
    log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    log_btn.setStyleSheet(
        "QPushButton {"
        "  background-color: rgba(255, 255, 255, 0.04);"
        "  color: #d1d5db;"
        "  border: 1px solid rgba(255, 255, 255, 0.08);"
        "  border-radius: 8px;"
        "  padding: 8px 16px;"
        "  font-weight: 600;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(255, 255, 255, 0.08);"
        "  border-color: rgba(255, 255, 255, 0.15);"
        "  color: white;"
        "}"
    )
    log_btn.clicked.connect(lambda: _open_focus_log_dialog(app))
    action_row.addWidget(log_btn)

    exit_btn = QPushButton(t("focus.exit", "Exit Focus Mode"))
    exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    exit_btn.setStyleSheet(
        "QPushButton {"
        "  background-color: rgba(239, 68, 68, 0.12);"
        "  color: #fca5a5;"
        "  border: 1px solid rgba(239, 68, 68, 0.35);"
        "  border-radius: 8px;"
        "  padding: 8px 16px;"
        "  font-weight: 700;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(239, 68, 68, 0.22);"
        "  border-color: rgba(239, 68, 68, 0.6);"
        "  color: white;"
        "}"
    )
    exit_btn.clicked.connect(lambda: _exit_focus_mode(app))
    action_row.addWidget(exit_btn)
    action_row.addStretch()
    layout.addLayout(action_row)

    app.focus_frame.show()
    _ensure_focus_timer(app).start(1000)


def _exit_focus_mode(app, is_set_completed: bool = False) -> None:
    if not getattr(app, "is_focus_mode", False):
        return

    app.is_focus_mode = False

    # Store necessary stats BEFORE resetting refs
    saved_secs = int(getattr(app, "_focus_saved_secs", 0) or 0)
    saved_sessions = int(getattr(app, "_focus_sessions_saved", 0) or 0)

    # 1. Immediately hide UI overlays and reset docks before any blocking modal dialogs
    if hasattr(app, "focus_frame"):
        app.focus_frame.hide()
    if hasattr(app, "dock_manager"):
        app.dock_manager.show()

    mode = str(getattr(app, "_focus_mode_type", FOCUS_MODE_STOPWATCH) or FOCUS_MODE_STOPWATCH)
    if mode == FOCUS_MODE_POMODORO:
        pomodoro = getattr(app, "_focus_pomodoro", None)
        if pomodoro:  # noqa: SIM102
            # When exiting manually (not set_completed), persist any partial focus time
            if not is_set_completed:
                snapshot = pomodoro.snapshot()
                if snapshot.phase == PHASE_FOCUS and snapshot.phase_elapsed_secs > 0:
                    _persist_completed_pomodoro_focus(app, snapshot.phase_elapsed_secs)
                    # Re-fetch local counters after possible final persistence
                    saved_secs = int(getattr(app, "_focus_saved_secs", 0) or 0)
                    saved_sessions = int(getattr(app, "_focus_sessions_saved", 0) or 0)

        # Show summary whenever there are completed sessions (always for set_completed, optionally for manual exit)
        show_summary = is_set_completed or saved_sessions > 0
        if show_summary:
            try:
                today_sessions, today_secs = focus_usecases.get_today_focus_stats(legacy_focus_repo)
                monthly_sessions, monthly_secs = focus_usecases.get_monthly_focus_stats(
                    legacy_focus_repo
                )

                # Graceful fallback: local memory (saved_sessions) is more reliable for 'this exact session'
                final_today_sessions = max(today_sessions, saved_sessions)
                final_today_secs = max(today_secs, saved_secs)
                final_monthly_sessions = max(monthly_sessions, saved_sessions)
                final_monthly_secs = max(monthly_secs, saved_secs)

                if final_today_sessions > 0:
                    dlg = FocusCompletionDialog(
                        app,
                        sessions=saved_sessions,
                        total_secs=saved_secs,
                        today_sessions=final_today_sessions,
                        today_secs=final_today_secs,
                        monthly_sessions=final_monthly_sessions,
                        monthly_secs=final_monthly_secs,
                        allow_long_break=is_set_completed,
                        show_log_button=True,
                    )
                    res = dlg.exec()

                    if is_set_completed and res == FocusCompletionDialog.RESULT_START_LONG_BREAK:
                        current_pomodoro = getattr(app, "_focus_pomodoro", None)
                        if current_pomodoro:
                            app.is_focus_mode = True  # Restore state
                            current_pomodoro.start_long_break()
                            # Restart UI
                            if hasattr(app, "focus_frame"):
                                app.focus_frame.show()
                            if hasattr(app, "dock_manager"):
                                app.dock_manager.hide()
                            _render_pomodoro_state(app)
                            return  # DO NOT cleanup — continuing in long break

                    if res == FocusCompletionDialog.RESULT_VIEW_LOGS:
                        _open_focus_log_dialog(app)
            except Exception as e:
                print(f"Failed to show exit summary: {e}")
    else:
        _persist_stopwatch_log(app)

    _reset_focus_runtime_refs(app)


def toggle_focus_pause(app) -> None:
    if not getattr(app, "is_focus_mode", False):
        return
    if getattr(app, "_focus_mode_type", FOCUS_MODE_STOPWATCH) != FOCUS_MODE_POMODORO:
        return

    pomodoro = getattr(app, "_focus_pomodoro", None)
    if pomodoro is None:
        return

    pomodoro.toggle_pause()
    _render_pomodoro_state(app)


def skip_focus_phase(app) -> None:
    import time

    now = time.time()
    if now - getattr(app, "_last_skip_time", 0) < 0.3:
        return
    app._last_skip_time = now

    if not getattr(app, "is_focus_mode", False):
        return
    if getattr(app, "_focus_mode_type", FOCUS_MODE_STOPWATCH) != FOCUS_MODE_POMODORO:
        return

    pomodoro = getattr(app, "_focus_pomodoro", None)
    if pomodoro is None:
        return

    events = pomodoro.skip_phase()
    _process_pomodoro_events(app, events)
    _render_pomodoro_state(app)


def toggle_focus_mode(app):
    if getattr(app, "is_focus_mode", False):
        _exit_focus_mode(app)
    else:
        app.is_focus_mode = True
        _enter_focus_mode(app)


def update_focus_timer(app):
    if not getattr(app, "is_focus_mode", False):
        _reset_focus_runtime_refs(app)
        return

    # Centralized UI Alive Check
    if not _is_widget_alive(getattr(app, "timer_lbl", None)):
        _reset_focus_runtime_refs(app)
        return

    if getattr(app, "_focus_mode_type", FOCUS_MODE_STOPWATCH) == FOCUS_MODE_POMODORO:
        pomodoro = getattr(app, "_focus_pomodoro", None)
        if pomodoro is None:
            _reset_focus_runtime_refs(app)
            return

        events = pomodoro.tick()
        _process_pomodoro_events(app, events)
        _render_pomodoro_state(app)
        return

    # Stopwatch path
    app._focus_elapsed_secs = int(getattr(app, "_focus_elapsed_secs", 0) or 0) + 1
    app.timer_lbl.setText(_format_mmss(app._focus_elapsed_secs))
