# -*- coding: utf-8 -*-
"""Cached list projections and navigation controls for modern widget workspaces."""

from PyQt6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QSizePolicy, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.widget_free_layout_runtime import (
    FreeAgendaPanel,
    item_matches_block,
)


class WorkspaceOverview(QFrame):
    def __init__(self, window):
        super().__init__(window.hero)
        self.window = window
        self.setObjectName("workspace_overview")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)
        self.buttons = {}
        for kind in ("schedule", "work", "directive"):
            button = QToolButton(self)
            button.setObjectName("workspace_metric")
            button.setCheckable(True)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda _checked=False, selected=kind: window.set_filter(selected)
            )
            self.buttons[kind] = button
            row.addWidget(button, 1)

    def update_items(self, items, *, data_state="ready"):
        for kind, button in self.buttons.items():
            count = sum(1 for item in items if item_matches_block(item, kind))
            label = self.window._filter_labels()[kind]
            text = f"{label}  {count if data_state == 'ready' else '—'}"
            button.setText(text)
            button.setChecked(self.window._active_filter == kind)
            button.setAccessibleName(text)
            button.setToolTip(
                t(
                    "widget_workspace.selected_day_total",
                    "선택한 날짜 전체의 {label} 항목",
                    label=label,
                )
            )


class WorkspaceBoard(QFrame):
    def __init__(self, window):
        super().__init__(window.agenda_section)
        self.window = window
        self.setObjectName("workspace_board")
        self.row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(12)
        self.panels = {}
        for kind in ("schedule", "work", "directive"):
            panel = FreeAgendaPanel(window, kind, self)
            panel.setProperty("workspaceLane", True)
            panel.setMinimumSize(0, 0)
            panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
            self.panels[kind] = panel
            self.row.addWidget(panel, 1)

    def update_items(self, items, *, data_state="ready"):
        for kind, panel in self.panels.items():
            panel.update_items(items, data_state=data_state)
            panel.heading.setText(f"{self.window._filter_labels()[kind]}  {len(panel.rows)}")
            panel.setVisible(self.window._active_filter in {"all", kind})

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.row.setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < 740
            else QBoxLayout.Direction.LeftToRight
        )

    def rows(self):
        return [row for panel in self.panels.values() if not panel.isHidden() for row in panel.rows]
