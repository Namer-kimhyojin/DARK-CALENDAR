# -*- coding: utf-8 -*-

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from calendar_app.shared.color_utils import hex_to_rgba, parse_hex_color, shift_rgb
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_snapshot import build_shared_ui_tokens, build_theme_snapshot

try:
    from PyQt6 import sip
except Exception:
    import sip  # type: ignore

from calendar_app.presentation.dialogs.focus_completion_dialog import FocusCompletionDialog

FOCUS_MODE_POMODORO = "pomodoro"
FOCUS_MODE_STOPWATCH = "stopwatch"


def _focus_ui_tokens(app) -> dict[str, str]:
    """Return a calm, theme-aware palette for the focus surface."""
    settings = getattr(app, "settings", None)
    snapshot = build_theme_snapshot(settings=settings)
    tokens = build_shared_ui_tokens(settings=settings, snapshot=snapshot)
    backdrop = parse_hex_color(snapshot.panel_base_color, "#15151d")
    center_delta = -8 if snapshot.text_theme == "light" else 12
    tokens["focus_backdrop"] = backdrop.name()
    tokens["focus_backdrop_center"] = shift_rgb(backdrop, center_delta).name()
    tokens["focus_icon_muted"] = "#5f6773" if snapshot.text_theme == "light" else "#8f96a3"
    return tokens


def _focus_phase_style(tokens: dict[str, str], phase: str) -> str:
    accent = tokens["accent"]
    if phase == PHASE_FOCUS:
        color = accent
        background = hex_to_rgba(accent, 0.14)
        border = hex_to_rgba(accent, 0.34)
    else:
        color = tokens["warning"]
        background = tokens["warning_soft_bg"]
        border = hex_to_rgba(tokens["warning"], 0.38)
    return (
        "QLabel {"
        f"  color: {color};"
        f"  background-color: {background};"
        f"  border: 1px solid {border};"
        "  border-radius: 12px;"
        "  padding: 4px 11px;"
        "  font-size: 12px;"
        "  font-weight: 700;"
        "}"
    )


def _set_focus_checklist_style(
    checkbox: QCheckBox,
    *,
    checked: bool,
    tokens: dict[str, str],
) -> None:
    font = checkbox.font()
    font.setStrikeOut(checked)
    checkbox.setFont(font)
    text_color = tokens["text_faint"] if checked else tokens["text_secondary"]
    indicator_bg = tokens["accent"] if checked else tokens["bg_hover"]
    indicator_border = tokens["accent"] if checked else tokens["border"]
    checkbox.setStyleSheet(
        "QCheckBox {"
        f"  color: {text_color};"
        "  font-size: 13px;"
        "  spacing: 9px;"
        "}"
        "QCheckBox::indicator {"
        "  width: 16px;"
        "  height: 16px;"
        "  border-radius: 5px;"
        f"  border: 1px solid {indicator_border};"
        f"  background-color: {indicator_bg};"
        "}"
        "QCheckBox::indicator:hover {"
        f"  border-color: {tokens['accent']};"
        "}"
    )


_FOCUS_DOCK_ATTRS = ("left_dock", "center_dock", "routine_dock", "directive_dock")


def _capture_focus_shell_state(app) -> None:
    if getattr(app, "_focus_saved_dock_visibility", None) is not None:
        return

    dock_visibility = {}
    for attr in _FOCUS_DOCK_ATTRS:
        dock = getattr(app, attr, None)
        if dock is not None:
            dock_visibility[attr] = bool(dock.isVisible())
    app._focus_saved_dock_visibility = dock_visibility

    menu_widget = getattr(app, "_top_bar_menu_wrapper", None)
    if menu_widget is None and hasattr(app, "menuWidget"):
        menu_widget = app.menuWidget()
    size_grip = getattr(app, "size_grip", None)
    app._focus_saved_chrome_visibility = {
        "menu": bool(menu_widget.isVisible()) if menu_widget is not None else False,
        "size_grip": bool(size_grip.isVisible()) if size_grip is not None else False,
    }

    app._focus_entry_was_fullscreen = bool(app.isFullScreen())
    app._focus_entry_was_maximized = bool(app.isMaximized())
    app._focus_windowed_was_maximized = bool(app.isMaximized())


def _activate_focus_shell(app, *, capture_state: bool = True) -> None:
    if capture_state:
        _capture_focus_shell_state(app)

    for attr in _FOCUS_DOCK_ATTRS:
        dock = getattr(app, attr, None)
        if dock is not None:
            dock.hide()

    menu_widget = getattr(app, "_top_bar_menu_wrapper", None)
    if menu_widget is None and hasattr(app, "menuWidget"):
        menu_widget = app.menuWidget()
    if menu_widget is not None:
        menu_widget.hide()

    size_grip = getattr(app, "size_grip", None)
    if size_grip is not None:
        size_grip.hide()

    if hasattr(app, "centralWidget") and app.centralWidget() is not app.focus_frame:
        app.setCentralWidget(app.focus_frame)
    app.focus_frame.show()
    app.show()


def _restore_focus_window_state(app) -> None:
    if getattr(app, "_focus_entry_was_fullscreen", False):
        if not app.isFullScreen():
            app.showFullScreen()
        app.is_fullscreen = True
        return
    if getattr(app, "_focus_entry_was_maximized", False):
        if not app.isMaximized():
            app.showMaximized()
        app.is_fullscreen = False
        return
    if app.isFullScreen() or app.isMaximized():
        app.showNormal()
    app.is_fullscreen = False


def _restore_focus_shell(app, *, restore_window_state: bool = True) -> None:
    if hasattr(app, "focus_frame"):
        app.focus_frame.hide()

    saved_docks = getattr(app, "_focus_saved_dock_visibility", None) or {}
    for attr in _FOCUS_DOCK_ATTRS:
        dock = getattr(app, attr, None)
        if dock is None:
            continue
        dock.setVisible(bool(saved_docks.get(attr, True)))

    saved_chrome = getattr(app, "_focus_saved_chrome_visibility", None) or {}
    menu_widget = getattr(app, "_top_bar_menu_wrapper", None)
    if menu_widget is None and hasattr(app, "menuWidget"):
        menu_widget = app.menuWidget()
    if menu_widget is not None:
        menu_widget.setVisible(bool(saved_chrome.get("menu", True)))

    size_grip = getattr(app, "size_grip", None)
    if size_grip is not None:
        size_grip.setVisible(bool(saved_chrome.get("size_grip", True)))

    if restore_window_state:
        _restore_focus_window_state(app)


def _update_focus_fullscreen_button(app) -> None:
    button = getattr(app, "_focus_fullscreen_btn", None)
    if not _is_widget_alive(button):
        return
    is_fullscreen = bool(app.isFullScreen())
    button.setChecked(is_fullscreen)
    if is_fullscreen:
        label = t("focus.windowed", "Window mode")
        hint = t(
            "focus.windowed_hint",
            "Exit fullscreen without ending the focus session. (Esc / F11)",
        )
    else:
        label = t("focus.fullscreen", "Fullscreen")
        hint = t("focus.fullscreen_hint", "Enter fullscreen focus. (F11)")
    button.setToolTip(hint)
    button.setAccessibleName(label)
    button.setAccessibleDescription(hint)


def toggle_focus_fullscreen(app) -> bool:
    """Toggle focus fullscreen while keeping the focus session active."""
    if not getattr(app, "is_focus_mode", False):
        return False

    if app.isFullScreen():
        if getattr(app, "_focus_windowed_was_maximized", False):
            app.showMaximized()
        else:
            app.showNormal()
        app.is_fullscreen = False
    else:
        app._focus_windowed_was_maximized = bool(app.isMaximized())
        app.showFullScreen()
        app.is_fullscreen = True
    _update_focus_fullscreen_button(app)
    return True


def exit_focus_fullscreen(app) -> bool:
    """Handle Escape: leave fullscreen only, never terminate the focus session."""
    if not getattr(app, "is_focus_mode", False) or not app.isFullScreen():
        return False
    if getattr(app, "_focus_windowed_was_maximized", False):
        app.showMaximized()
    else:
        app.showNormal()
    app.is_fullscreen = False
    _update_focus_fullscreen_button(app)
    return True


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
    sip.delete(old_layout)


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
        if hasattr(app, "open_focus_log_dialog"):
            app.open_focus_log_dialog()
            return
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
    tokens = _focus_ui_tokens(app)

    phase_lbl = getattr(app, "focus_phase_lbl", None)
    if _is_widget_alive(phase_lbl):
        phase_text = _focus_phase_label(snapshot)
        phase_lbl.setText(phase_text)
        phase_lbl.setAccessibleName(phase_text)
        phase_lbl.setStyleSheet(_focus_phase_style(tokens, snapshot.phase))

    timer_lbl = getattr(app, "timer_lbl", None)
    if _is_widget_alive(timer_lbl):
        timer_text = _format_mmss(snapshot.phase_remaining_secs)
        timer_lbl.setText(timer_text)
        timer_lbl.setAccessibleName(timer_text)

    progress_bar = getattr(app, "focus_progress", None)
    if _is_widget_alive(progress_bar):
        elapsed = max(0, snapshot.phase_elapsed_secs)
        remaining = max(0, snapshot.phase_remaining_secs)
        total = elapsed + remaining
        percent = int((elapsed / total) * 100) if total > 0 else 0
        progress_bar.setValue(max(0, min(100, percent)))

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

    pause_btn = getattr(app, "_focus_pause_btn", None)
    if _is_widget_alive(pause_btn):
        if snapshot.paused:
            pause_text = t("focus.resume", "Resume")
            pause_btn.setIcon(_ic(ICON.PLAY, color=tokens["accent"]))
        else:
            pause_text = t("focus.pause", "Pause")
            pause_btn.setIcon(_ic(ICON.PAUSE, color=tokens["accent"]))
        pause_btn.setText(pause_text)
        pause_btn.setToolTip(pause_text)
        pause_btn.setAccessibleName(pause_text)

    skip_btn = getattr(app, "_focus_skip_btn", None)
    if _is_widget_alive(skip_btn):
        if snapshot.phase == PHASE_FOCUS:
            skip_text = t("focus.skip_focus", "Skip Focus")
        else:
            skip_text = t("focus.skip_break", "Skip Break")
        skip_btn.setText(skip_text)
        skip_btn.setToolTip(skip_text)
        skip_btn.setAccessibleName(skip_text)


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
    app._focus_fullscreen_btn = None
    app._focus_pomodoro = None
    app._focus_mode_type = FOCUS_MODE_POMODORO
    app._focus_task_id = None
    app._focus_elapsed_secs = 0
    app._focus_saved_secs = 0
    app._focus_sessions_saved = 0
    app._focus_saved_dock_visibility = None
    app._focus_saved_chrome_visibility = None
    app._focus_entry_was_fullscreen = False
    app._focus_entry_was_maximized = False
    app._focus_windowed_was_maximized = False


def _build_focus_checklist_panel(app, layout):
    """Build a compact checklist surface for the selected task."""
    task_id = getattr(app, "_focus_task_id", None)
    if not task_id:
        return

    tokens = _focus_ui_tokens(app)
    items = checklist_repo.get_task_checklist_items(task_id)

    section = QFrame()
    section.setObjectName("FocusChecklistSection")
    section.setStyleSheet(
        "QFrame#FocusChecklistSection {"
        f"  background-color: {tokens['bg_item']};"
        f"  border: 1px solid {tokens['border_soft']};"
        "  border-radius: 12px;"
        "}"
    )
    section_layout = QVBoxLayout(section)
    section_layout.setContentsMargins(16, 12, 16, 12)
    section_layout.setSpacing(9)

    title_row = QHBoxLayout()
    title_row.setSpacing(8)
    checklist_title = QLabel(t("dialog.tabs.checklist", "체크리스트"))
    checklist_title.setStyleSheet(
        f"color: {tokens['text_secondary']}; font-size: 13px; font-weight: 700;"
    )
    title_row.addWidget(checklist_title)
    title_row.addStretch()
    count_lbl = QLabel(str(len(items)))
    count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    count_lbl.setFixedSize(24, 20)
    count_lbl.setStyleSheet(
        f"color: {tokens['text_muted']};"
        f"background-color: {tokens['bg_hover']};"
        f"border: 1px solid {tokens['border_soft']};"
        "border-radius: 10px;"
        "font-size: 11px;"
        "font-weight: 700;"
    )
    title_row.addWidget(count_lbl)
    section_layout.addLayout(title_row)

    if not items:
        empty_lbl = QLabel(t("dialog.label_settings.none_to_load", "체크리스트 항목이 없습니다."))
        empty_lbl.setStyleSheet(
            f"color: {tokens['text_faint']}; font-size: 12px; padding: 2px 0 4px 0;"
        )
        empty_lbl.setWordWrap(True)
        section_layout.addWidget(empty_lbl)
    else:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(min(116, max(34, len(items) * 30)))
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {tokens['border']};"
            " border-radius: 2px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(7)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for item in items:
            cb = QCheckBox(item.get("item_text", ""))
            cb.setChecked(bool(item.get("is_completed", False)))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            _set_focus_checklist_style(cb, checked=cb.isChecked(), tokens=tokens)
            link_id = item.get("id")

            def _make_toggle_handler(l_id, checkbox):
                def _handle(checked):
                    checklist_repo.toggle_checklist_item(l_id)
                    _set_focus_checklist_style(
                        checkbox,
                        checked=checked,
                        tokens=tokens,
                    )

                return _handle

            cb.toggled.connect(_make_toggle_handler(link_id, cb))
            scroll_layout.addWidget(cb)

        scroll.setWidget(scroll_content)
        section_layout.addWidget(scroll)

    layout.addWidget(section)


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

    # Task confirmed — now switch the main window to the in-window focus canvas.
    _clear_focus_frame_layout(app)

    tokens = _focus_ui_tokens(app)
    accent_soft = hex_to_rgba(tokens["accent"], 0.12)
    accent_hover = hex_to_rgba(tokens["accent"], 0.20)
    app.focus_frame.setObjectName("FocusModeShell")
    app.focus_frame.setStyleSheet(
        "QFrame#FocusModeShell {"
        "  background: qradialgradient("
        "    cx:0.5, cy:0.42, radius:0.82, fx:0.5, fy:0.42,"
        f"    stop:0 {tokens['focus_backdrop_center']},"
        f"    stop:0.52 {tokens['focus_backdrop']}, stop:1 {tokens['focus_backdrop']}"
        "  );"
        "  border: none;"
        "  border-radius: 0;"
        "}"
    )

    frame_layout = QHBoxLayout(app.focus_frame)
    frame_layout.setContentsMargins(24, 18, 24, 18)
    frame_layout.setSpacing(0)

    content = QFrame()
    content.setObjectName("FocusContent")
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    content.setMinimumWidth(420)
    content.setMaximumWidth(760)
    content.setStyleSheet("QFrame#FocusContent {  background: transparent;  border: none;}")

    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 22, 28, 22)
    layout.setSpacing(15)
    layout.addStretch(1)

    frame_layout.addStretch(1)
    frame_layout.addWidget(content, 6)
    frame_layout.addStretch(1)

    timer_settings = _load_focus_timer_settings(app)
    app._focus_mode_type = timer_settings["mode"]
    app._focus_elapsed_secs = 0
    app._focus_saved_secs = 0
    app._focus_sessions_saved = 0

    if app._focus_mode_type == FOCUS_MODE_POMODORO:
        app._focus_pomodoro = PomodoroEngine(
            focus_minutes=timer_settings["focus_minutes"],
            short_break_minutes=timer_settings["short_break_minutes"],
            long_break_minutes=timer_settings["long_break_minutes"],
            long_break_every=timer_settings["long_break_every"],
            goal_sessions=timer_settings["goal_sessions"],
        )
    else:
        app._focus_pomodoro = None

    header_row = QHBoxLayout()
    header_row.setSpacing(12)
    title = QLabel(_se(t("menu.focus_mode", "Focus Mode")))
    title.setStyleSheet(
        f"color: {tokens['text_primary']};"
        "font-size: 18px;"
        "font-weight: 750;"
        "background: transparent;"
        "border: none;"
    )
    header_row.addWidget(title)
    header_row.addStretch()
    if app._focus_mode_type == FOCUS_MODE_POMODORO:
        app.focus_phase_lbl = QLabel()
        app.focus_phase_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(app.focus_phase_lbl)
    else:
        app.focus_phase_lbl = None

    app._focus_fullscreen_btn = QPushButton()
    app._focus_fullscreen_btn.setObjectName("FocusFullscreenButton")
    app._focus_fullscreen_btn.setCheckable(True)
    app._focus_fullscreen_btn.setFixedSize(36, 36)
    app._focus_fullscreen_btn.setIconSize(QSize(14, 14))
    app._focus_fullscreen_btn.setIcon(_ic(ICON.FULLSCREEN, color=tokens["focus_icon_muted"]))
    app._focus_fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app._focus_fullscreen_btn.setStyleSheet(
        "QPushButton#FocusFullscreenButton {"
        f"  color: {tokens['text_muted']};"
        f"  background-color: {tokens['bg_item']};"
        f"  border: 1px solid {tokens['border_soft']};"
        "  border-radius: 10px;"
        "  padding: 0;"
        "}"
        "QPushButton#FocusFullscreenButton:hover {"
        f"  background-color: {tokens['bg_hover']};"
        f"  border-color: {tokens['border']};"
        "}"
        "QPushButton#FocusFullscreenButton:checked {"
        f"  background-color: {accent_soft};"
        f"  border-color: {hex_to_rgba(tokens['accent'], 0.42)};"
        "}"
    )
    app._focus_fullscreen_btn.clicked.connect(lambda: toggle_focus_fullscreen(app))
    header_row.addWidget(app._focus_fullscreen_btn)
    layout.addLayout(header_row)

    task_panel = QFrame()
    task_panel.setObjectName("FocusTaskPanel")
    task_panel.setStyleSheet(
        "QFrame#FocusTaskPanel {"
        f"  background-color: {accent_soft};"
        f"  border: 1px solid {hex_to_rgba(tokens['accent'], 0.26)};"
        "  border-radius: 13px;"
        "}"
    )
    task_layout = QVBoxLayout(task_panel)
    task_layout.setContentsMargins(16, 11, 16, 12)
    task_layout.setSpacing(4)
    task_caption = QLabel(t("focus.now_focusing", "Now focusing"))
    task_caption.setStyleSheet(
        f"color: {tokens['text_muted']};"
        "font-size: 11px;"
        "font-weight: 700;"
        "background: transparent;"
        "border: none;"
    )
    task_layout.addWidget(task_caption)
    task_lbl = QLabel(str(task_name or t("dialog.task.untitled", "Untitled")))
    task_lbl.setStyleSheet(
        f"color: {tokens['text_primary']};"
        "font-size: 17px;"
        "font-weight: 700;"
        "background: transparent;"
        "border: none;"
    )
    task_lbl.setWordWrap(True)
    task_lbl.setAccessibleName(
        t("focus.current_task", "Currently focusing on: {task_name}", task_name=task_name)
    )
    task_layout.addWidget(task_lbl)
    layout.addWidget(task_panel)

    if app._focus_mode_type == FOCUS_MODE_POMODORO:
        app.timer_lbl = QLabel("00:00")
        app.timer_lbl.setStyleSheet(
            f"color: {tokens['accent']};"
            "font-size: 68px;"
            "font-weight: 700;"
            "font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;"
            "letter-spacing: 1px;"
            "background: transparent;"
            "border: none;"
        )
        app.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.timer_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        app.focus_progress = QProgressBar()
        app.focus_progress.setRange(0, 100)
        app.focus_progress.setTextVisible(False)
        app.focus_progress.setFixedHeight(8)
        app.focus_progress.setAccessibleName(t("focus.title", "Focus timer"))
        app.focus_progress.setStyleSheet(
            "QProgressBar {"
            "  border: none;"
            f"  background-color: {tokens['bg_hover']};"
            "  border-radius: 4px;"
            "}"
            "QProgressBar::chunk {"
            f"  background-color: {tokens['accent']};"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(app.focus_progress)

        app.focus_summary_lbl = QLabel()
        app.focus_summary_lbl.setStyleSheet(
            f"color: {tokens['text_muted']};"
            "font-size: 12px;"
            "font-weight: 600;"
            "background: transparent;"
            "border: none;"
        )
        app.focus_summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.focus_summary_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        app._focus_pause_btn = QPushButton()
        app._focus_pause_btn.setObjectName("FocusPrimaryButton")
        app._focus_pause_btn.setMinimumSize(112, 42)
        app._focus_pause_btn.setIconSize(QSize(14, 14))
        app._focus_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        app._focus_pause_btn.setStyleSheet(
            "QPushButton#FocusPrimaryButton {"
            f"  color: {tokens['accent']};"
            f"  background-color: {accent_soft};"
            f"  border: 1px solid {hex_to_rgba(tokens['accent'], 0.42)};"
            "  border-radius: 10px;"
            "  padding: 0 16px;"
            "  font-size: 13px;"
            "  font-weight: 700;"
            "}"
            "QPushButton#FocusPrimaryButton:hover {"
            f"  color: {tokens['text_primary']};"
            f"  background-color: {accent_hover};"
            f"  border-color: {tokens['accent']};"
            "}"
        )
        app._focus_pause_btn.clicked.connect(lambda: toggle_focus_pause(app))
        btn_row.addWidget(app._focus_pause_btn)

        app._focus_skip_btn = QPushButton()
        app._focus_skip_btn.setObjectName("FocusSecondaryButton")
        app._focus_skip_btn.setMinimumSize(128, 42)
        app._focus_skip_btn.setIconSize(QSize(14, 14))
        app._focus_skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        app._focus_skip_btn.setStyleSheet(
            "QPushButton#FocusSecondaryButton {"
            f"  color: {tokens['text_secondary']};"
            f"  background-color: {tokens['bg_hover']};"
            f"  border: 1px solid {tokens['border_soft']};"
            "  border-radius: 10px;"
            "  padding: 0 16px;"
            "  font-size: 13px;"
            "  font-weight: 650;"
            "}"
            "QPushButton#FocusSecondaryButton:hover {"
            f"  color: {tokens['text_primary']};"
            f"  background-color: {tokens['bg_item_hover']};"
            f"  border-color: {tokens['border']};"
            "}"
        )
        app._focus_skip_btn.setIcon(_ic(ICON.FORWARD, color=tokens["focus_icon_muted"]))
        app._focus_skip_btn.clicked.connect(lambda: skip_focus_phase(app))
        btn_row.addWidget(app._focus_skip_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        _render_pomodoro_state(app)
        exit_text = t(
            "focus.exit_hint_pomodoro",
            "Stop Focus Mode with [Ctrl+Space / Ctrl+F].",
        )
    else:
        app.timer_lbl = QLabel("00:00")
        app.timer_lbl.setStyleSheet(
            f"color: {tokens['accent']};"
            "font-size: 68px;"
            "font-weight: 700;"
            "font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;"
            "letter-spacing: 1px;"
            "background: transparent;"
            "border: none;"
        )
        app.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(app.timer_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        exit_text = t("focus.exit_hint")

    _build_focus_checklist_panel(app, layout)

    exit_info = QLabel(exit_text)
    exit_info.setStyleSheet(
        f"color: {tokens['text_faint']};font-size: 11px;background: transparent;border: none;"
    )
    exit_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
    exit_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout.addWidget(exit_info)

    action_row = QHBoxLayout()
    action_row.setSpacing(10)

    log_btn = QPushButton(t("focus.view_logs", "View Focus Logs"))
    log_btn.setObjectName("FocusGhostButton")
    log_btn.setMinimumHeight(40)
    log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    log_btn.setStyleSheet(
        "QPushButton#FocusGhostButton {"
        f"  background-color: {tokens['bg_item']};"
        f"  color: {tokens['text_secondary']};"
        f"  border: 1px solid {tokens['border_soft']};"
        "  border-radius: 10px;"
        "  padding: 0 16px;"
        "  font-weight: 600;"
        "}"
        "QPushButton#FocusGhostButton:hover {"
        f"  background-color: {tokens['bg_hover']};"
        f"  border-color: {tokens['border']};"
        f"  color: {tokens['text_primary']};"
        "}"
    )
    log_btn.setAccessibleName(log_btn.text())
    log_btn.clicked.connect(lambda: _open_focus_log_dialog(app))
    action_row.addWidget(log_btn)

    exit_btn = QPushButton(t("focus.exit", "Exit Focus Mode"))
    exit_btn.setObjectName("FocusExitButton")
    exit_btn.setMinimumHeight(40)
    exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    exit_btn.setStyleSheet(
        "QPushButton#FocusExitButton {"
        f"  background-color: {tokens['danger_soft_bg']};"
        f"  color: {tokens['danger']};"
        f"  border: 1px solid {hex_to_rgba(tokens['danger'], 0.34)};"
        "  border-radius: 10px;"
        "  padding: 0 16px;"
        "  font-weight: 650;"
        "}"
        "QPushButton#FocusExitButton:hover {"
        f"  background-color: {hex_to_rgba(tokens['danger'], 0.22)};"
        f"  border-color: {tokens['danger']};"
        f"  color: {tokens['text_primary']};"
        "}"
    )
    exit_btn.setAccessibleName(exit_btn.text())
    exit_btn.clicked.connect(lambda: _exit_focus_mode(app))
    action_row.addWidget(exit_btn)
    layout.addLayout(action_row)
    layout.addStretch(1)

    _activate_focus_shell(app)
    _update_focus_fullscreen_button(app)
    _ensure_focus_timer(app).start(1000)


def _exit_focus_mode(app, is_set_completed: bool = False) -> None:
    if not getattr(app, "is_focus_mode", False):
        return

    app.is_focus_mode = False

    # Store necessary stats BEFORE resetting refs
    saved_secs = int(getattr(app, "_focus_saved_secs", 0) or 0)
    saved_sessions = int(getattr(app, "_focus_sessions_saved", 0) or 0)
    was_focus_fullscreen = bool(app.isFullScreen())

    # 1. Immediately hide UI overlays and reset docks before any blocking modal dialogs
    _restore_focus_shell(app)

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
                stats = focus_usecases.get_focus_stats_snapshot(legacy_focus_repo)
                today_sessions = stats.today_sessions
                today_secs = stats.today_secs
                monthly_sessions = stats.monthly_sessions
                monthly_secs = stats.monthly_secs

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
                            _activate_focus_shell(app, capture_state=False)
                            if was_focus_fullscreen and not app.isFullScreen():
                                app.showFullScreen()
                                app.is_fullscreen = True
                            _update_focus_fullscreen_button(app)
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
