# -*- coding: utf-8 -*-
"""One tab stop and date-aware keyboard navigation for the monthly grid."""

from PyQt6 import sip
from PyQt6.QtCore import QDate, QEvent, QObject, Qt

from calendar_app.infrastructure.i18n import t


class MonthGridNavigation(QObject):
    def __init__(self, app, scroll):
        super().__init__(scroll)
        self.app = app
        self.scroll = scroll
        self.cells = dict(app._calendar_cells_by_date)
        self.dates = sorted(self.cells)
        hint = t(
            "calendar.keyboard_hint",
            "방향키: 날짜 이동 · Enter: 날짜 선택 · Ctrl+Enter: 일정 추가",
        )
        for cell in self.cells.values():
            cell.setProperty("monthKeyboardCell", True)
            cell.setProperty("keyboardFocused", False)
            cell.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            cell.setAccessibleDescription(cell.accessibleDescription() + " · " + hint)
            cell.setToolTip(hint)
            cell.installEventFilter(self)
        preferred = getattr(app, "_calendar_keyboard_date", None)
        if not isinstance(preferred, QDate) or preferred.toString("yyyy-MM-dd") not in self.cells:
            preferred = app.current_date
        key = preferred.toString("yyyy-MM-dd")
        self.active_key = key if key in self.cells else self.dates[0]
        self.cells[self.active_key].setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def restore_focus(self):
        if sip.isdeleted(self.scroll):
            return
        self.cells[self.active_key].setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, cell, event):
        if event.type() == QEvent.Type.FocusIn:
            self.cells[self.active_key].setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self.active_key = cell.target_date.toString("yyyy-MM-dd")
            cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.app._calendar_keyboard_date = QDate(cell.target_date)
            self.scroll.ensureWidgetVisible(cell, 8, 8)
            self._set_focus_visual(cell, True)
        elif event.type() == QEvent.Type.FocusOut:
            self._set_focus_visual(cell, False)
        elif event.type() == QEvent.Type.KeyPress:
            key, modifiers = event.key(), event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if modifiers == Qt.KeyboardModifier.ControlModifier:
                    # Use the existing queued signal to avoid opening a modal inside a key event.
                    cell.doubleClicked.emit((QDate(cell.target_date), None))
                elif modifiers == Qt.KeyboardModifier.NoModifier:
                    cell.clicked.emit(QDate(cell.target_date))
                else:
                    return False
                return True
            if modifiers != Qt.KeyboardModifier.NoModifier:
                return False
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                step = -1 if key == Qt.Key.Key_Left else 1
                index = self.dates.index(self.active_key) + step
                if 0 <= index < len(self.dates):
                    target = QDate.fromString(self.dates[index], "yyyy-MM-dd")
                else:
                    target = cell.target_date.addDays(step)
                    while not self.app.cal_show_weekends and target.dayOfWeek() >= 6:
                        target = target.addDays(step)
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                target = cell.target_date.addDays(-7 if key == Qt.Key.Key_Up else 7)
            else:
                return False
            self.app._calendar_keyboard_date = target
            target_cell = self.cells.get(target.toString("yyyy-MM-dd"))
            if target_cell is not None:
                target_cell.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.app.current_date = target
                self.app.load_center_panel()
            return True
        return False

    @staticmethod
    def _set_focus_visual(cell, focused):
        cell.setProperty("keyboardFocused", focused)
        cell.style().unpolish(cell)
        cell.style().polish(cell)
        cell.update()
