from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QFrame, QWidget

from calendar_app.infrastructure.i18n import t

from .floating_dock_behavior import attach_floating_dock_behavior


def create_left_dock(self):
    self.left_frame = QFrame()
    self.left_frame.setFrameShape(QFrame.Shape.NoFrame)
    self.left_frame.setStyleSheet("background: transparent; border: none;")
    self.left_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.left_frame.customContextMenuRequested.connect(self.show_left_context_menu)

    self.left_dock = QDockWidget(t("panel.today_schedule"), self)
    self.left_dock.setObjectName("left_dock")
    self.left_dock.setWidget(self.left_frame)
    self.left_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.left_dock.setMinimumWidth(100)
    self.left_dock.setTitleBarWidget(QWidget())
    self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)
    self.left_dock.visibilityChanged.connect(
        lambda: self.act_today.setChecked(not self.left_dock.isHidden())
    )
    attach_floating_dock_behavior(
        self.left_dock,
        on_float_changed=lambda _: self._on_any_dock_float_changed(),
        app=self,
        label=t("panel.today_schedule"),
    )


def create_center_dock(self):
    self.center_frame = QFrame()
    self.center_frame.setFrameShape(QFrame.Shape.NoFrame)
    self.center_frame.setStyleSheet("background: transparent; border: none;")
    self.center_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.center_frame.customContextMenuRequested.connect(self.show_center_context_menu)

    self.center_dock = QDockWidget(t("panel.main_calendar"), self)
    self.center_dock.setObjectName("center_dock")
    self.center_dock.setWidget(self.center_frame)
    self.center_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.center_dock.setMinimumWidth(100)
    self.center_dock.setTitleBarWidget(QWidget())
    self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.center_dock)
    self.center_dock.visibilityChanged.connect(
        lambda: self.act_calendar.setChecked(not self.center_dock.isHidden())
    )
    attach_floating_dock_behavior(
        self.center_dock,
        on_float_changed=lambda _: self._on_any_dock_float_changed(),
        app=self,
        label=t("panel.main_calendar"),
    )
