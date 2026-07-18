import contextlib

from PyQt6.QtCore import Qt


def set_column_layout(app, cols):
    """Rearrange dock widgets into 1~4 column layouts."""
    docks = [app.left_dock, app.center_dock, app.routine_dock, app.directive_dock]

    # Fully detach/reset first so previous split/tab state does not leak.
    for dock in docks:
        app.dock_manager.removeDockWidget(dock)
        if dock.isFloating():
            dock.setFloating(False)
        dock.show()

    if cols == 1:
        # Single-column tab stack. Expand to full width to avoid an empty central area.
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.left_dock)
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.center_dock)
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.routine_dock)
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.directive_dock)
        app.dock_manager.tabifyDockWidget(app.left_dock, app.center_dock)
        app.dock_manager.tabifyDockWidget(app.center_dock, app.routine_dock)
        app.dock_manager.tabifyDockWidget(app.routine_dock, app.directive_dock)
        app.left_dock.raise_()
        with contextlib.suppress(Exception):
            app.dock_manager.resizeDocks(
                [app.left_dock],
                [max(1, app.dock_manager.size().width())],
                Qt.Orientation.Horizontal,
            )
        return

    if cols == 2:
        # 2-column layout: Left(Today/Routine) | Right(Calendar/Directive)
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.left_dock)
        app.dock_manager.splitDockWidget(app.left_dock, app.center_dock, Qt.Orientation.Horizontal)
        app.dock_manager.tabifyDockWidget(app.left_dock, app.routine_dock)
        app.dock_manager.tabifyDockWidget(app.center_dock, app.directive_dock)
        app.left_dock.raise_()
        app.center_dock.raise_()
        return

    if cols == 3:
        # 3-column layout: Today | Calendar | Routine/Directive
        app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.left_dock)
        app.dock_manager.splitDockWidget(app.left_dock, app.center_dock, Qt.Orientation.Horizontal)
        app.dock_manager.splitDockWidget(
            app.center_dock, app.routine_dock, Qt.Orientation.Horizontal
        )
        app.dock_manager.tabifyDockWidget(app.routine_dock, app.directive_dock)
        app.routine_dock.raise_()
        return

    # cols == 4: 4-column layout (Today | Calendar | Routine | Directive)
    app.dock_manager.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, app.left_dock)
    app.dock_manager.splitDockWidget(app.left_dock, app.center_dock, Qt.Orientation.Horizontal)
    app.dock_manager.splitDockWidget(app.center_dock, app.routine_dock, Qt.Orientation.Horizontal)
    app.dock_manager.splitDockWidget(
        app.routine_dock, app.directive_dock, Qt.Orientation.Horizontal
    )
