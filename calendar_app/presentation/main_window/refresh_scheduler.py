"""Panel refresh scheduling mixin for UI update coalescing."""


class RefreshSchedulerMixin:
    # ------------------------------------------------------------------ #
    # 패널 새로고침 스케줄러
    # ------------------------------------------------------------------ #
    def _ensure_refresh_scheduler(self):
        from PyQt6.QtCore import QTimer

        if hasattr(self, "_ui_refresh_timer"):
            return
        self._pending_refresh = {"left": False, "center": False, "right": False}
        self._panel_dirty = {"left": True, "center": True, "right": True}
        self._ui_refresh_timer = QTimer(self)
        self._ui_refresh_timer.setSingleShot(True)
        self._ui_refresh_timer.timeout.connect(self._flush_scheduled_refresh)

    def mark_panel_dirty(self, left=False, center=False, right=False):
        self._ensure_refresh_scheduler()
        self._panel_dirty["left"] = self._panel_dirty["left"] or bool(left)
        self._panel_dirty["center"] = self._panel_dirty["center"] or bool(center)
        self._panel_dirty["right"] = self._panel_dirty["right"] or bool(right)

    def schedule_panel_refresh(self, left=False, center=False, right=False, delay_ms=0):
        if getattr(self, "_is_shutting_down", False):
            return
        # 드래그 중에는 패널 리프레시를 보류 (필요 시 자동으로 인한 새로고침 방지)
        if getattr(self, "_is_dragging", False):
            if left or center:
                self._drag_pending_refresh = True
            return
        self._ensure_refresh_scheduler()
        self.mark_panel_dirty(left=left, center=center, right=right)
        self._pending_refresh["left"] = self._pending_refresh["left"] or left
        self._pending_refresh["center"] = self._pending_refresh["center"] or center
        self._pending_refresh["right"] = self._pending_refresh["right"] or right

        delay_ms = max(0, int(delay_ms or 16))

        from PyQt6.QtCore import Q_ARG, QMetaObject
        from PyQt6.QtCore import Qt as QtCoreQt

        if self._ui_refresh_timer.isActive() and delay_ms != 0:
            try:
                remaining = int(self._ui_refresh_timer.remainingTime())
            except Exception:
                remaining = -1
            if remaining >= 0 and remaining <= delay_ms:
                return
        QMetaObject.invokeMethod(
            self._ui_refresh_timer,
            "start",
            QtCoreQt.ConnectionType.QueuedConnection,
            Q_ARG(int, delay_ms),
        )

    def _flush_scheduled_refresh(self):
        self._ensure_refresh_scheduler()
        pending = dict(self._pending_refresh)
        self._pending_refresh = {"left": False, "center": False, "right": False}
        if pending["left"]:
            self.load_left_panel(force=False)
            self._panel_dirty["left"] = False
        if pending["center"]:
            self.load_center_panel(force=False)
            self._panel_dirty["center"] = False
        if pending["right"]:
            self.load_right_panel(force=False)
            self._panel_dirty["right"] = False

        # Proxy synchronization: trigger unified widget refresh if any operational data changed
        if pending["left"] or pending["center"] or pending["right"]:
            controller = getattr(self, "_unified_widget_controller", None)
            if controller is not None:
                controller.refresh_data()

    def _refresh_all_panels(self):
        self.schedule_panel_refresh(left=True, center=True, right=True)
