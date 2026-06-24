"""Main-window shell/UI utility action mixin."""

import os

from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime import system_manager
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic


class WindowShellActionsMixin:
    # ------------------------------------------------------------------ #
    # 레이아웃 유틸
    # ------------------------------------------------------------------ #
    def clear_layout(self, layout):
        """레이아웃 내부 위젯 안전 삭제"""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if not item:
                break
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    @staticmethod
    def reset_frame(frame):
        """QFrame/QWidget의 레이아웃과 모든 자식 위젯을 완전히 제거한다.

        기존 패턴인 clear_layout() + QWidget().setLayout() 은 레이아웃을
        frame에서 실제로 분리하지 못한다 (Qt는 이미 부모가 있는 레이아웃을
        다른 QWidget으로 이동시키지 않는다).  이 메서드는 sip.delete()로
        레이아웃 C++ 객체를 즉시 파괴해 frame을 깨끗한 상태로 만든다.
        """
        import PyQt6.sip as sip

        layout = frame.layout()
        if layout is not None:
            # 자식 위젯 제거
            while layout.count():
                item = layout.takeAt(0)
                if item:
                    w = item.widget()
                    if w:
                        w.deleteLater()
            # 레이아웃 자체를 즉시 파괴 → frame.layout()이 None이 됨
            sip.delete(layout)

    def toggle_magnet_mode(self, _checked=None, show_toast=True):
        """패널 자동 도킹(자석) 모드를 토글한다.

        ON  → AllDockWidgetAreas  : 드래그 시 가장자리에 자동 흡착
        OFF → NoDockWidgetArea    : 드래그 중 자동 도킹 없음, 자유 이동
        """
        if hasattr(self, "magnet_btn"):
            is_checked = self.magnet_btn.isChecked()
        else:
            is_checked = bool(self.settings.value("magnet_enabled", True, type=bool))

        if hasattr(self, "settings"):
            self.settings.setValue("magnet_enabled", is_checked)

        if hasattr(self, "magnet_btn"):
            self.magnet_btn.setText("")  # Icon-only per user request
            _ic_color = getattr(self, "_tb_icon_color", "#aab0ba")
            if is_checked:
                self.magnet_btn.setIcon(_ic(ICON.MAGNET, color=_ic_color))
                self.magnet_btn.setToolTip(t("topbar.magnet_on_hint"))
            else:
                self.magnet_btn.setIcon(_ic(ICON.MAGNET_OFF, color=_ic_color))
                self.magnet_btn.setToolTip(t("topbar.magnet_off_hint"))

        from PyQt6.QtCore import Qt

        # ON: 모든 영역에 자동 도킹 허용 / OFF: 자동 도킹 비활성화 (자유 이동)
        areas = (
            Qt.DockWidgetArea.AllDockWidgetAreas
            if is_checked
            else Qt.DockWidgetArea.NoDockWidgetArea
        )

        for dock_name in ["left_dock", "center_dock", "routine_dock", "directive_dock"]:
            if hasattr(self, dock_name):
                dock = getattr(self, dock_name)
                dock.setAllowedAreas(areas)
                dock.setFeatures(
                    dock.features()
                    | dock.DockWidgetFeature.DockWidgetMovable
                    | dock.DockWidgetFeature.DockWidgetFloatable
                )

        if show_toast:
            title = t("magnet.toast_title")
            msg = t("magnet.toast_msg_on") if is_checked else t("magnet.toast_msg_off")
            self.show_toast(title, msg)

    def toggle_lock_mode(self):
        """바탕화면 고정 모드를 토글한다."""
        from PyQt6.QtCore import Qt

        is_checked = self.lock_btn.isChecked()
        self.is_locked = is_checked

        if hasattr(self, "settings"):
            self.settings.setValue("is_locked", is_checked)
            self.settings.setValue("lock_enabled", is_checked)

        _ic_color = getattr(self, "_tb_icon_color", "#aab0ba")
        if is_checked:
            self.lock_btn.setText("")
            self.lock_btn.setIcon(_ic(ICON.LOCK, color=_ic_color))
            self.lock_btn.setToolTip(t("lock.on_hint"))
            self.lock_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            overlay_btn = self._ensure_lock_overlay_toggle_button()
            overlay_btn.blockSignals(True)
            overlay_btn.setChecked(True)
            overlay_btn.setText(t("lock.overlay_unlock", "고정 해제"))
            overlay_btn.setToolTip(
                t("lock.overlay_unlock_hint", "고정 모드를 해제합니다. (Ctrl+Shift+L)")
            )
            overlay_btn.blockSignals(False)
            self._update_lock_overlay_geometry()
            self.lock_overlay.show()
            self.lock_overlay.raise_()
            overlay_btn.show()
            overlay_btn.raise_()
            self._raise_lock_mode_controls()
        else:
            self.lock_btn.setText("")
            self.lock_btn.setIcon(_ic(ICON.UNLOCK, color=_ic_color))
            self.lock_btn.setToolTip(t("lock.off_hint"))
            self.lock_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.lock_overlay.hide()
            overlay_btn = getattr(self, "_lock_overlay_toggle_btn", None)
            if overlay_btn is not None:
                overlay_btn.blockSignals(True)
                overlay_btn.setChecked(False)
                overlay_btn.blockSignals(False)
                overlay_btn.hide()

        self._apply_lock_mode_ui(is_checked)
        self._apply_lock_mode_to_docks(is_checked)
        self._update_lock_overlay_geometry()
        self.schedule_panel_refresh(center=True)

    def _apply_lock_mode_ui(self, locked: bool):
        """고정 모드 활성 여부에 따라 lock_btn을 제외한 상단바 버튼들을 비활성화/활성화한다."""
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        _LOCKABLE = [
            "add_menu_btn",
            "view_menu_btn",
            "display_menu_btn",
            "widgets_menu_btn",
            "sys_menu_btn",
            "sync_action_btn",
            "magnet_btn",
            "slider",
            "search_edit",
            "widget_mode_btn",
        ]
        for attr in _LOCKABLE:
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            widget.setEnabled(not locked)
            effect = widget.graphicsEffect()
            if locked:
                if not isinstance(effect, QGraphicsOpacityEffect):
                    effect = QGraphicsOpacityEffect(widget)
                    widget.setGraphicsEffect(effect)
                effect.setOpacity(0.35)
            else:
                if isinstance(effect, QGraphicsOpacityEffect):
                    effect.setOpacity(1.0)
        lock_btn = getattr(self, "lock_btn", None)
        if lock_btn is not None:
            lock_btn.setEnabled(True)
            effect = lock_btn.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(1.0)

    def _raise_lock_mode_controls(self):
        for attr in ("_top_bar_menu_wrapper", "top_bar_frame"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.raise_()
        lock_btn = getattr(self, "lock_btn", None)
        if lock_btn is not None:
            lock_btn.raise_()
        overlay_btn = getattr(self, "_lock_overlay_toggle_btn", None)
        if overlay_btn is not None and overlay_btn.isVisible():
            overlay_btn.raise_()

    def _ensure_lock_overlay_toggle_button(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QPushButton

        overlay = getattr(self, "lock_overlay", None)
        if overlay is None:
            return None

        btn = getattr(self, "_lock_overlay_toggle_btn", None)
        if btn is None or btn.parent() is not overlay:
            btn = QPushButton(t("lock.overlay_unlock", "고정 해제"), overlay)
            btn.setObjectName("ghost_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked=False, _self=self: _self._on_lock_overlay_toggle_clicked(checked)
            )
            self._lock_overlay_toggle_btn = btn
        return btn

    def _on_lock_overlay_toggle_clicked(self, checked: bool):
        if hasattr(self, "lock_btn"):
            self.lock_btn.setChecked(bool(checked))
        self.toggle_lock_mode()

    def _iter_lock_mode_docks(self):
        docks = []
        seen = set()
        for dock_name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
            dock = getattr(self, dock_name, None)
            if dock is None:
                continue
            dock_id = id(dock)
            if dock_id in seen:
                continue
            seen.add(dock_id)
            docks.append(dock)
        return docks

    def _ensure_dock_lock_blocker(self, dock):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QWidget

        blocker = getattr(dock, "_lock_mode_blocker", None)
        if blocker is None:
            blocker = QWidget(dock)
            blocker.setObjectName("lockModeDockBlocker")
            blocker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            blocker.setStyleSheet("background: transparent;")
            blocker.hide()
            dock._lock_mode_blocker = blocker
        return blocker

    def _apply_lock_mode_to_docks(self, locked: bool):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDockWidget

        if not hasattr(self, "_lock_mode_saved_dock_features"):
            self._lock_mode_saved_dock_features = {}
        if not hasattr(self, "_lock_mode_saved_dock_areas"):
            self._lock_mode_saved_dock_areas = {}

        for dock in self._iter_lock_mode_docks():
            dock_key = dock.objectName() or str(id(dock))
            blocker = self._ensure_dock_lock_blocker(dock)

            if locked:
                if dock_key not in self._lock_mode_saved_dock_features:
                    self._lock_mode_saved_dock_features[dock_key] = dock.features()
                if dock_key not in self._lock_mode_saved_dock_areas:
                    self._lock_mode_saved_dock_areas[dock_key] = dock.allowedAreas()
                dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
                dock.setAllowedAreas(Qt.DockWidgetArea.NoDockWidgetArea)
                blocker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                blocker.setGeometry(dock.rect())
                blocker.show()
                blocker.raise_()
            else:
                dock.setFeatures(
                    self._lock_mode_saved_dock_features.get(
                        dock_key,
                        dock.features(),
                    )
                )
                dock.setAllowedAreas(
                    self._lock_mode_saved_dock_areas.get(
                        dock_key,
                        dock.allowedAreas(),
                    )
                )
                blocker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                blocker.hide()

    def _update_lock_overlay_geometry(self):
        if hasattr(self, "lock_overlay"):
            self.lock_overlay.setGeometry(0, 0, self.width(), self.height())
            self.lock_overlay.setStyleSheet("background: transparent;")
            overlay_btn = getattr(self, "_lock_overlay_toggle_btn", None)
            if overlay_btn is not None:
                btn_w = max(96, overlay_btn.sizeHint().width() + 18)
                btn_h = max(30, overlay_btn.sizeHint().height())
                overlay_btn.setGeometry(
                    self.width() - btn_w - 18, self.height() - btn_h - 18, btn_w, btn_h
                )
                overlay_btn.raise_()
            if getattr(self, "is_locked", False):
                self._raise_lock_mode_controls()

        for dock in self._iter_lock_mode_docks():
            blocker = getattr(dock, "_lock_mode_blocker", None)
            if blocker is not None:
                blocker.setGeometry(dock.rect())

    # ------------------------------------------------------------------ #
    # 토스트 / 트레이
    # ------------------------------------------------------------------ #
    def show_toast(self, title, message):
        try:
            from winotify import Notification

            from calendar_app.app_paths import APP_ICON_TOAST_PATH, APP_NAME

            toast = Notification(
                app_id=APP_NAME,
                title=title,
                msg=message,
                icon=APP_ICON_TOAST_PATH if os.path.exists(APP_ICON_TOAST_PATH) else "",
            )
            toast.show()
        except Exception:
            # winotify 실패 시 트레이 아이콘으로 대체
            if hasattr(self, "tray_icon") and getattr(self.tray_icon, "isVisible", lambda: False)():
                self.tray_icon.showMessage(
                    title, message, QSystemTrayIcon.MessageIcon.Information, 5000
                )

    # ------------------------------------------------------------------ #
    # 함수 / 시스템 이벤트
    # ------------------------------------------------------------------ #
    def toggle_overlay(self):
        if self.is_widget_mode_active():
            self.stop_widget_mode()
            return
        from calendar_app.infrastructure.runtime.infra_manager import toggle_overlay

        toggle_overlay(self)

    def toggle_fullscreen(self):
        from calendar_app.infrastructure.runtime.infra_manager import toggle_fullscreen

        toggle_fullscreen(self)

    def toggle_top_bar(self):
        visible = self.top_bar_frame.isVisible()
        self.top_bar_frame.setVisible(not visible)

    def _on_any_dock_float_changed(self):
        """하나라도 분리되면 상단바 숨김, 모두 도킹 상태일 때만 상단바 표시."""
        any_floating = any(
            getattr(self, attr).isFloating()
            for attr in ("left_dock", "center_dock", "routine_dock", "directive_dock")
            if hasattr(self, attr)
        )
        frame = getattr(self, "top_bar_frame", None)
        if frame is not None:
            frame.setVisible(not any_floating)
        act = getattr(self, "act_topbar", None)
        if act is not None:
            act.setChecked(not any_floating)
            act.setEnabled(not any_floating)

    def _ensure_widget_mode_controller(self):
        controller = getattr(self, "_panel_widget_mode_controller", None)
        if controller is None:
            from calendar_app.presentation.widgets.panel_widget_mode import (
                PanelWidgetModeController,
            )

            controller = PanelWidgetModeController(self)
            self._panel_widget_mode_controller = controller
        return controller

    def _ensure_unified_widget_controller(self):
        controller = getattr(self, "_unified_widget_controller", None)
        if controller is None:
            from calendar_app.presentation.widgets.unified_widget_mode import (
                UnifiedWidgetController,
            )

            controller = UnifiedWidgetController(self)
            self._unified_widget_controller = controller
        return controller

    def toggle_unified_widget(self):
        controller = self._ensure_unified_widget_controller()
        controller.toggle_widget()

    def toggle_widget_mode_panel(self):
        # Use unified widget instead of separate panels per new requirement
        self.toggle_unified_widget()

    def open_schedule_widget_panel(self):
        controller = self._ensure_widget_mode_controller()
        controller.enter_widget_mode(show_schedule=True, show_work=False)

    def open_work_widget_panel(self):
        controller = self._ensure_widget_mode_controller()
        controller.enter_widget_mode(show_schedule=False, show_work=True)

    def open_all_widget_panels(self):
        controller = self._ensure_widget_mode_controller()
        controller.enter_widget_mode(show_schedule=True, show_work=True)

    def stop_widget_mode(self):
        controller = getattr(self, "_panel_widget_mode_controller", None)
        if controller is None:
            return
        controller.exit_widget_mode()

    def is_widget_mode_active(self):
        controller = getattr(self, "_panel_widget_mode_controller", None)
        if controller is None:
            return False
        return controller.is_widget_mode_active()

    def refresh_widget_mode_panels(self, schedule=True, work=True):
        controller = getattr(self, "_panel_widget_mode_controller", None)
        if controller is None:
            return
        controller.refresh_visible_widgets(schedule=bool(schedule), work=bool(work))

    def close_widget_mode_panels(self):
        controller = getattr(self, "_panel_widget_mode_controller", None)
        if controller is None:
            return
        controller.close_widgets()

    def _calendar_toolbar_visible_setting(self):
        raw = (
            self.settings.value("calendar_toolbar_visible", True)
            if hasattr(self, "settings")
            else True
        )
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int | float):
            return raw != 0
        return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

    def set_calendar_toolbar_visible(self, visible: bool):
        visible = bool(visible)
        if hasattr(self, "settings"):
            self.settings.setValue("calendar_toolbar_visible", visible)

        tb = getattr(self, "calendar_toolbar_widget", None)
        if tb is not None and hasattr(tb, "set_toolbar_expanded"):
            tb.set_toolbar_expanded(visible)
            tb.updateGeometry()
            tb.repaint()
            if hasattr(self, "center_dock") and self.center_dock is not None:
                self.center_dock.updateGeometry()
                self.center_dock.repaint()
        elif hasattr(self, "schedule_panel_refresh"):
            self.schedule_panel_refresh(center=True)

        act = getattr(self, "act_calendar_toolbar", None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(visible)
            act.blockSignals(False)

    def toggle_calendar_toolbar(self):
        tb = getattr(self, "calendar_toolbar_widget", None)
        if tb is not None and hasattr(tb, "is_toolbar_expanded"):
            current = tb.is_toolbar_expanded()
        else:
            current = self._calendar_toolbar_visible_setting()
        self.set_calendar_toolbar_visible(not current)

    def toggle_focus_mode(self):
        from calendar_app.presentation.focus_mode import toggle_focus_mode

        toggle_focus_mode(self)

    def toggle_focus_pause(self):
        from calendar_app.presentation.focus_mode import toggle_focus_pause

        toggle_focus_pause(self)

    def toggle_autostart(self):
        """윈도우 시작 시 자동 실행 설정 토글."""
        enabled = system_manager.is_autostart_enabled()
        new_state = not enabled
        system_manager.set_autostart(new_state)
        if hasattr(self, "autostart_act"):
            self.autostart_act.setChecked(new_state)
        status_text = t("autostart.enabled") if new_state else t("autostart.disabled")
        msg = t("autostart.msg").format(status=status_text)
        QMessageBox.information(self, t("common.notification"), msg)

    # ------------------------------------------------------------------ #
    # 레이아웃 / 컬럼
    # ------------------------------------------------------------------ #
    def set_column_layout(self, cols):
        from calendar_app.presentation.layout_manager import set_column_layout

        set_column_layout(self, cols)

    def sync_panel_menu_state(self):
        """패널 표시 상태를 메뉴 체크 상태와 동기화.

        floating 도크는 isVisible()==True 이더라도 실제로 화면에 떠 있는 것이므로
        '표시 중'으로 간주한다. 명시적으로 hide()된 경우에만 체크 해제.
        """
        for act_attr, dock_attr in (
            ("act_today", "left_dock"),
            ("act_calendar", "center_dock"),
            ("act_routine", "routine_dock"),
            ("act_directive", "directive_dock"),
        ):
            act = getattr(self, act_attr, None)
            dock = getattr(self, dock_attr, None)
            if act is not None and dock is not None:
                # isVisible()이 False인 경우만 체크 해제 (floating + hidden 구분)
                act.setChecked(not dock.isHidden())
        # Overlay widget instances are managed by overlay_manager;
        # there are no static top-menu actions to sync here.

    # ------------------------------------------------------------------ #
    # 검색
    # ------------------------------------------------------------------ #
    def handle_search_changed(self, _text):
        self.search_debounce_timer.start()

    def _exec_search_refresh(self):
        self.schedule_panel_refresh(left=True, center=True, right=True)

    # ------------------------------------------------------------------ #
    # 입력 유틸
    # ------------------------------------------------------------------ #
    def _is_text_input_focused(self):
        from PyQt6.QtWidgets import (
            QAbstractSpinBox,
            QComboBox,
            QDateTimeEdit,
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
        )

        focus_widget = QApplication.focusWidget()
        if focus_widget is None:
            return False
        return isinstance(
            focus_widget,
            QLineEdit | QTextEdit | QPlainTextEdit | QDateTimeEdit | QAbstractSpinBox | QComboBox,
        )
