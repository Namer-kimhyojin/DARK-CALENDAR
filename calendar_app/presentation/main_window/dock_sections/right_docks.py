from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QFrame, QWidget

from calendar_app.infrastructure.i18n import t

from .floating_dock_behavior import attach_floating_dock_behavior


def create_routine_dock(self):
    self.routine_frame = QFrame()
    self.routine_frame.setFrameShape(QFrame.Shape.NoFrame)
    self.routine_frame.setStyleSheet("background: transparent; border: none;")
    self.routine_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.routine_frame.customContextMenuRequested.connect(self.show_right_context_menu)

    self.routine_dock = QDockWidget(t("panel.routine"), self)
    self.routine_dock.setObjectName("routine_dock")
    self.routine_dock.setWidget(self.routine_frame)
    self.routine_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.routine_dock.setMinimumWidth(100)
    self.routine_dock.setTitleBarWidget(QWidget())
    self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.routine_dock)
    self.routine_dock.visibilityChanged.connect(
        lambda: self.act_routine.setChecked(not self.routine_dock.isHidden())
    )
    attach_floating_dock_behavior(
        self.routine_dock,
        on_float_changed=lambda _: self._on_any_dock_float_changed(),
        app=self,
        label=t("panel.routine"),
    )


def create_directive_dock(self):
    self.directive_frame = QFrame()
    self.directive_frame.setFrameShape(QFrame.Shape.NoFrame)
    self.directive_frame.setStyleSheet("background: transparent; border: none;")
    self.directive_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.directive_frame.customContextMenuRequested.connect(self.show_directive_context_menu)

    self.directive_dock = QDockWidget(t("panel.directive"), self)
    self.directive_dock.setObjectName("directive_dock")
    self.directive_dock.setWidget(self.directive_frame)
    self.directive_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.directive_dock.setMinimumWidth(100)
    self.directive_dock.setTitleBarWidget(QWidget())
    self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.directive_dock)
    self.directive_dock.visibilityChanged.connect(
        lambda: self.act_directive.setChecked(not self.directive_dock.isHidden())
    )
    attach_floating_dock_behavior(
        self.directive_dock,
        on_float_changed=lambda _: self._on_any_dock_float_changed(),
        app=self,
        label=t("panel.directive"),
    )
