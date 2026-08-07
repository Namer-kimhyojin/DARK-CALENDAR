# -*- coding: utf-8 -*-
"""Non-modal first-run guidance for the main calendar window."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.theme_snapshot import build_theme_snapshot

_WELCOME_SEEN_KEY = "ux_welcome_seen_v1"


def should_show_first_run_banner(settings) -> bool:
    """Return whether this profile still needs lightweight onboarding."""
    if settings.value(_WELCOME_SEEN_KEY, None) is not None:
        return False
    return settings.value("last_working_date", None) is None


def _mark_welcome_seen(app) -> None:
    app.settings.setValue(_WELCOME_SEEN_KEY, True)
    banner = getattr(app, "_welcome_banner", None)
    if banner is not None:
        banner.hide()


def _run_welcome_action(app, callback: Callable[[], None]) -> None:
    _mark_welcome_seen(app)
    callback()


def build_first_run_banner(app) -> QFrame | None:
    """Build a dismissible onboarding surface without blocking startup."""
    if not should_show_first_run_banner(app.settings):
        return None

    banner = QFrame()
    banner.setObjectName("firstRunBanner")
    banner.setAccessibleName(t("welcome.accessible_name", "처음 시작 안내"))

    root = QVBoxLayout(banner)
    root.setContentsMargins(12, 9, 10, 9)
    root.setSpacing(7)

    heading_row = QHBoxLayout()
    heading_row.setSpacing(8)

    copy_layout = QVBoxLayout()
    copy_layout.setSpacing(1)
    title = QLabel(t("welcome.title", "처음이신가요? 첫 일정을 바로 만들어 보세요."))
    title.setObjectName("firstRunTitle")
    body = QLabel(
        t(
            "welcome.body",
            "로컬 일정은 바로 사용할 수 있고, 필요할 때 Google 캘린더를 연결할 수 있습니다.",
        )
    )
    body.setObjectName("firstRunBody")
    body.setWordWrap(True)
    copy_layout.addWidget(title)
    copy_layout.addWidget(body)
    heading_row.addLayout(copy_layout, 1)

    dismiss_btn = QToolButton()
    dismiss_btn.setObjectName("firstRunDismiss")
    dismiss_btn.setText("×")
    dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    dismiss_label = t("welcome.dismiss", "시작 안내 닫기")
    dismiss_btn.setToolTip(dismiss_label)
    dismiss_btn.setAccessibleName(dismiss_label)
    dismiss_btn.setMinimumSize(32, 32)
    dismiss_btn.clicked.connect(lambda _checked=False: _mark_welcome_seen(app))
    heading_row.addWidget(dismiss_btn, alignment=Qt.AlignmentFlag.AlignTop)
    root.addLayout(heading_row)

    actions = QHBoxLayout()
    actions.setSpacing(7)
    actions.addStretch(1)

    action_specs = (
        (
            "primary_btn",
            t("welcome.create_schedule", "첫 일정 만들기"),
            app.open_task_dialog,
        ),
        (
            "ghost_btn",
            t("welcome.connect_calendar", "캘린더 연결"),
            app.open_gcal_settings_dialog,
        ),
        (
            "ghost_btn",
            t("welcome.open_help", "빠른 도움말"),
            app.show_shortcut_guide,
        ),
    )
    for object_name, label, callback in action_specs:
        button = QPushButton(label)
        button.setObjectName(object_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(32)
        button.setAccessibleName(label)
        button.clicked.connect(
            lambda _checked=False, handler=callback: _run_welcome_action(app, handler)
        )
        actions.addWidget(button)
    root.addLayout(actions)

    apply_first_run_banner_theme(app, banner=banner)
    return banner


def apply_first_run_banner_theme(app, *, banner: QFrame | None = None) -> None:
    """Refresh the banner from the current semantic theme snapshot."""
    target = banner if banner is not None else getattr(app, "_welcome_banner", None)
    if target is None:
        return

    snapshot = build_theme_snapshot(app.settings)
    palette = snapshot.ui_palette
    accent = snapshot.theme_color
    target.setStyleSheet(
        f"""
        QFrame#firstRunBanner {{
            background: {palette.get("surface_alt", palette.get("bg_hover", "rgba(20,20,28,0.96)"))};
            border: 1px solid {palette.get("accent_soft", accent)};
            border-radius: 10px;
        }}
        QLabel#firstRunTitle {{
            color: {palette.get("text_primary", "#ffffff")};
            font-weight: 800;
            background: transparent;
        }}
        QLabel#firstRunBody {{
            color: {palette.get("text_muted", palette.get("text_secondary", "#b7bdc8"))};
            background: transparent;
        }}
        QToolButton#firstRunDismiss {{
            color: {palette.get("text_secondary", "#d7dbe3")};
            background: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            font-size: 18px;
        }}
        QToolButton#firstRunDismiss:hover {{
            color: {palette.get("text_primary", "#ffffff")};
            background: {palette.get("bg_hover", "rgba(255,255,255,0.08)")};
            border-color: {palette.get("border_soft", "rgba(255,255,255,0.12)")};
        }}
        """
    )
