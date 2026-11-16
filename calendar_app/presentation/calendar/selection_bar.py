# -*- coding: utf-8 -*-
"""Calendar toolbar selection bar: selected count, existing bulk actions, clear.

The bar appears only while tasks or directives are selected. The count button
opens the bulk actions the context menus already offer for a selection
(priority, status, automatic colour tags, delete) plus "clear selection".
The hint label ("Ctrl+click for multi-selection") steps aside while the bar
is shown so the count is not repeated.
"""

import logging

from PyQt6 import sip
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QSizePolicy, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.icon_map import ICON, icon

logger = logging.getLogger(__name__)


def _alive(widget):
    return widget is not None and not sip.isdeleted(widget)


def selection_count(app):
    return len(getattr(app, "selected_task_ids", ()) or ()) + len(
        getattr(app, "selected_directive_ids", ()) or ()
    )


def build_selection_bar(app, styles, *, icon_color=None):
    """Create the bar and keep it on ``app.selection_bar``; hidden until used."""
    bar = QWidget()
    bar.setObjectName("calendar_selection_bar")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    chip = QPushButton()
    chip.setObjectName("calendar_selection_chip")
    chip.setStyleSheet(styles["selection_chip"])
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    chip.setToolTip(
        t(
            "calendar.selection_actions_hint",
            "선택한 항목에 적용할 작업을 고릅니다. Esc를 누르면 선택이 해제됩니다.",
        )
    )
    chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    menu = QMenu(chip)
    menu.setObjectName("calendar_selection_menu")
    menu.setStyleSheet(styles["dropdown_menu"])
    menu.aboutToShow.connect(lambda: populate_selection_menu(app, menu))
    chip.setMenu(menu)
    layout.addWidget(chip)

    clear_btn = QPushButton()
    clear_btn.setObjectName("calendar_selection_clear")
    clear_btn.setIcon(icon(ICON.CLOSE, color=icon_color))
    clear_btn.setIconSize(QSize(13, 13))
    clear_btn.setStyleSheet(styles["icon_btn"])
    clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    clear_text = t("calendar.selection_clear", "선택 해제 (Esc)")
    clear_btn.setToolTip(clear_text)
    clear_btn.setAccessibleName(clear_text)
    clear_btn.clicked.connect(lambda _checked=False: app.clear_task_selection())
    layout.addWidget(clear_btn)

    bar.chip = chip
    bar.clear_button = clear_btn
    bar.hide()
    app.selection_bar = bar
    return bar


def populate_selection_menu(app, menu):
    """Fill the menu with the bulk actions that already exist for a selection."""
    from calendar_app.domain.task_constants import PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS
    from calendar_app.presentation.context_menu_manager import (
        _add_task_priority_status_menus,
        _strip_menu_emojis,
    )

    menu.clear()
    task_ids = set(getattr(app, "selected_task_ids", ()) or ())
    count = selection_count(app)
    header = menu.addAction(t("panel.n_selected", n=count))
    header.setEnabled(False)
    menu.addSeparator()
    if task_ids:
        _add_task_priority_status_menus(menu, app, PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS)
    if count and hasattr(app, "auto_assign_color_tags_to_selection"):
        color_act = menu.addAction(t("context_menu.color_auto", "자동부여"))
        color_act.setIcon(icon(ICON.COLOR_PICKER))
        color_act.triggered.connect(lambda _c=False: app.auto_assign_color_tags_to_selection())
    if task_ids and hasattr(app, "handle_task_deleted"):
        menu.addSeparator()
        delete_act = menu.addAction(t("calendar.selection_delete", "선택 항목 삭제") + "\tDelete")
        delete_act.setIcon(icon(ICON.DELETE))
        delete_act.triggered.connect(lambda _c=False: _delete_selected(app))
    menu.addSeparator()
    clear_act = menu.addAction(t("calendar.selection_clear_short", "선택 해제") + "\tEsc")
    clear_act.setIcon(icon(ICON.CLOSE))
    clear_act.triggered.connect(lambda _c=False: app.clear_task_selection())
    _strip_menu_emojis(menu)


def _delete_selected(app):
    task_ids = getattr(app, "selected_task_ids", None)
    if task_ids:
        # handle_task_deleted resolves the whole selection from one member.
        app.handle_task_deleted(next(iter(task_ids)))


def sync_selection_label_visibility(app, count=None):
    """Show the multi-select hint only when nothing is selected and it fits."""
    label = getattr(app, "selection_status_lbl", None)
    bar = getattr(app, "selection_bar", None)
    if not _alive(label) or not _alive(bar):
        return
    if count is None:
        count = selection_count(app)
    suppressed = bool(label.property("toolbarSuppressed")) or bool(label.property("toolbarCompact"))
    label.setVisible(not suppressed and count <= 0)


def sync_selection_bar(app, count=None):
    """Update the bar's count and visibility right after a selection change."""
    bar = getattr(app, "selection_bar", None)
    if not _alive(bar):
        return
    if count is None:
        count = selection_count(app)
    text = t("panel.n_selected", n=count)
    chip = bar.chip
    if chip.text() != text:
        chip.setText(text)
        chip.setAccessibleName(text)
        chip.setAccessibleDescription(chip.toolTip())
    bar.setVisible(count > 0)
    sync_selection_label_visibility(app, count)
