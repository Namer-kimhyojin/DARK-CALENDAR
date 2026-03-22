# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QPushButton, QMenu, QFrame, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QComboBox,
                             QDateTimeEdit, QMessageBox, QApplication,
                             QCheckBox, QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect,
                             QGraphicsOpacityEffect)
from PyQt6.QtGui import QAction, QDrag, QCursor, QColor, QPixmap, QIcon, QPainter, QPen, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QByteArray, QDataStream, QIODevice, QPropertyAnimation, QEasingCurve, QRect, QDateTime, QTime, QObject, QPoint, QEvent, QTimer, QParallelAnimationGroup, QSettings
import sys
import logging
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation import drag_drop_manager as ddm
from calendar_app.infrastructure.db import checklist_repo, task_repo
from calendar_app.domain.task_constants import PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS
from calendar_app.presentation.theme.ui_tokens import get_ui_shape_tokens
from calendar_app.shared.search_utils import strip_hashtags
from calendar_app.shared.color_utils import derive_ui_palette
from calendar_app.shared.qt_helpers import apply_hover_state
from calendar_app.shared.theme_settings import (
    get_opacity_factor,
    get_theme_palette_inputs,
    get_theme_color,
)

logger = logging.getLogger(__name__)

_ICON_TIME = "[T]"
_ICON_LOCATION = "[L]"
_ICON_ASSIGNEE = "[A]"
_ICON_DESC = "[M]"

def _set_hover_state(widget, hovered: bool):
    apply_hover_state(widget, hovered)


class _ChecklistTextLabel(QLabel):
    clicked = pyqtSignal()

    def enterEvent(self, event):
        _set_hover_state(self, True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        _set_hover_state(self, False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _ElidingLabel(QLabel):
    """?띿뒪?멸? 湲몃㈃ ?ㅻⅨ履쎌쓣 '...'?쇰줈 ?섎씪???쒖떆?섎뒗 QLabel."""
    def paintEvent(self, _event):
        from PyQt6.QtGui import QPainter
        p = QPainter(self)
        fm = self.fontMetrics()
        elided = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        p.drawText(self.rect(), int(self.alignment()), elided)
        p.end()


class _InlineRenameEdit(QLineEdit):
    canceled = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class WrappedChecklistRow(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, text, checked=False, parent=None):
        super().__init__(parent)
        self.setObjectName("wrapped_checklist_row")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                background: transparent;
                padding: 0;
                margin: 0;
            }
            QCheckBox::indicator { width: 14px; height: 14px; }
        """)

        self.label = _ChecklistTextLabel(text)
        self.label.setWordWrap(True)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setStyleSheet("""
            QLabel {
                color: #eee;
                font-size: 10pt;
                background: transparent;
                border: none;
                padding: 1px 0 0 0;
                margin: 0;
            }
        """)

        layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.label, 1)

        self.checkbox.toggled.connect(self.toggled.emit)
        self.label.clicked.connect(self._toggle_from_label)

    def _toggle_from_label(self):
        self.checkbox.toggle()


class HoverInfoPopup(QFrame):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("hover_info_popup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("hover_info_card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(9, 7, 9, 7)
        card_layout.setSpacing(0)

        self.content_label = QLabel()
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_label.setWordWrap(False)
        self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        card_layout.addWidget(self.content_label)
        layout.addWidget(self.card)
        self._anchor = None
        self._anchor_side = "right"
        self._anchor_mode = "side"
        self._last_theme = None
        self._apply_theme_style()

        # Windows layered tooltip windows are unstable with drop shadows.
        if sys.platform != "win32":
            shadow = QGraphicsDropShadowEffect(self.card)
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 70))
            self.card.setGraphicsEffect(shadow)

        # Safety guard: periodically check whether cursor left anchor area
        self._guard_timer = QTimer(self)
        self._guard_timer.setInterval(80)
        self._guard_timer.timeout.connect(self._check_cursor_outside)

    def _apply_theme_style(self):
        from PyQt6.QtCore import QSettings
        s = QSettings("kimhyojin", "Dark Calendar")
        theme = get_theme_color(s)
        text_theme = s.value("text_theme", "dark")
        panel_base = s.value("panel_base_color", "#1c1c1c")
        cache_key = f"{theme}|{text_theme}|{panel_base}"
        if cache_key == self._last_theme:
            return
        self._last_theme = cache_key

        c = QColor(theme)
        if not c.isValid():
            c = QColor("#4da6ff")
        border = f"rgba({c.red()},{c.green()},{c.blue()},0.74)"

        opacity_factor = get_opacity_factor(s)
        pal = derive_ui_palette(text_theme, panel_base, opacity_factor)
        pb = QColor(panel_base)
        if not pb.isValid():
            pb = QColor("#1c1c1c")
        # Keep popup background tied to panel base only.
        r = max(0, min(255, pb.red() + 4))
        g = max(0, min(255, pb.green() + 4))
        b = max(0, min(255, pb.blue() + 6))
        bg = f"rgba({r},{g},{b},248)"
        label_color = pal["text_primary"]

        self.setStyleSheet(f"""
            QFrame#hover_info_popup {{
                background: transparent;
                border: none;
            }}
            QFrame#hover_info_card {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 0px;
            }}
            QLabel {{
                color: {label_color};
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
                font-size: 9pt;
                line-height: 1.25;
                background: transparent;
            }}
        """)

    def show_for(self, anchor, html):
        if not anchor or not html:
            self.hide()
            return

        self._apply_theme_style()
        self._anchor = anchor
        self._anchor_mode = str(anchor.property("_hover_info_mode") or "side")
        
        # 1. ??용뮞????쇱젟 ?袁⑸퓠 ?λ뜃由??怨밴묶 ?類ｋ궖
        self.content_label.setText("")
        self.content_label.setMaximumWidth(280)
        self.content_label.setText(html)
        
        # 2. ??由??④쑴沅?揶쏅벡????낅쑓??꾨뱜 (?귐딇뒄 ??용뮞?紐껊뮉 筌왖?怨뺣쭆 ?④쑴沅??獄쏆뮇源??????됱벉)
        self.content_label.updateGeometry()
        self.content_label.adjustSize()
        
        # 3. ?뚢뫂???瑗?獄??袁⑷퍥 ??밸씜 筌???由?鈺곌퀣??
        self.card.updateGeometry()
        self.card.adjustSize()
        
        # ??밸씜 ??덈즲???癒?퍥??筌왖??살컭?紐꺿봺 揶쏄퉮??(餓κ쑴堉??뺣뮉 ??덉삂??癰귣똻???띾┛ ?袁る맙)
        self.setMinimumSize(0, 0)
        self.adjustSize()
        
        # 4. ?袁⑺뒄 ?④쑴沅?獄???뽯뻻
        self._anchor_side = self._resolve_side(anchor)
        self.move(self._compute_position(anchor, self._anchor_side, self._anchor_mode))
        
        if not self.isVisible():
            self.show()
        self.raise_()
        self._guard_timer.start()

    def hide_for(self, anchor):
        if self._anchor is anchor:
            self._guard_timer.stop()
            self.hide()
            self._anchor = None

    def _check_cursor_outside(self):
        """Hide popup immediately when cursor leaves anchor/active region."""
        try:
            anchor = self._anchor
            if anchor is None or not anchor.isVisible():
                self._stop_popup()
                return
            # Hide popup immediately while dragging
            app = QApplication.activeWindow()
            if app is not None and getattr(app, "_is_dragging", False):
                self._stop_popup()
                return
            global_rect = QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())
            if not global_rect.contains(QCursor.pos()):
                self._stop_popup()
        except (RuntimeError, AttributeError):
            self._stop_popup()

    def _stop_popup(self):
        self._guard_timer.stop()
        self.hide()
        self._anchor = None

    def refresh_position(self, anchor):
        try:
            if self.isVisible() and self._anchor is anchor:
                # Keep side stable while the same anchor is active.
                self.move(self._compute_position(anchor, self._anchor_side, self._anchor_mode))
        except (RuntimeError, AttributeError):
            self._stop_popup()

    def _resolve_side(self, anchor):
        global_top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = anchor.screen()
        available = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        right_x = global_top_left.x() + anchor.width() + 12
        if right_x + self.width() <= available.right() - 8:
            return "right"
        return "left"

    def _compute_position(self, anchor, side=None, mode="side"):
        global_top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = anchor.screen()
        available = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()

        if mode == "inline_center":
            # Keep popover near the multiday bar center for contextual readability.
            x = global_top_left.x() + (anchor.width() - self.width()) // 2
            y = global_top_left.y() - self.height() - 8
            if y < available.top() + 8:
                y = global_top_left.y() + anchor.height() + 8
            x = max(available.left() + 8, min(x, available.right() - self.width() - 8))
            y = max(available.top() + 8, min(y, available.bottom() - self.height() - 8))
            return QPoint(x, y)

        side = side or "right"
        if side == "left":
            x = global_top_left.x() - self.width() - 12
        else:
            x = global_top_left.x() + anchor.width() + 12

        # Deterministic vertical rule: align to anchor top.
        y = global_top_left.y()

        if x < available.left() + 8:
            x = available.left() + 8
        if x + self.width() > available.right() - 8:
            x = max(available.left() + 8, available.right() - self.width() - 8)
        if y + self.height() > available.bottom() - 8:
            y = max(available.top() + 8, available.bottom() - self.height() - 8)
        if y < available.top() + 8:
            y = available.top() + 8

        return QPoint(x, y)


class HoverInfoEventFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.setInterval(320)  # 0.32s delay to reduce accidental flicker
        self._delay_timer.timeout.connect(self._do_show_popup)
        self._current_watched = None

    def eventFilter(self, watched, event):
        popup = get_hover_info_popup()
        
        if event.type() == QEvent.Type.Enter:
            html = watched.property("_hover_info_html")
            if html:
                self._current_watched = watched
                mode = str(watched.property("_hover_info_mode") or "side")
                if mode == "inline_center":
                    self._delay_timer.stop()
                    popup.show_for(watched, html)
                else:
                    self._delay_timer.start()
                
        elif event.type() in (QEvent.Type.MouseMove, QEvent.Type.Move, QEvent.Type.Resize):
            if popup.isVisible() and popup._anchor is watched:
                popup.refresh_position(watched)
                
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate):
            self._delay_timer.stop()
            self._current_watched = None
            popup.hide_for(watched)
            
        elif event.type() == QEvent.Type.ToolTip:
            return True
            
        return super().eventFilter(watched, event)

    def _do_show_popup(self):
        if self._current_watched and self._current_watched.isVisible():
            html = self._current_watched.property("_hover_info_html")
            if html:
                popup = get_hover_info_popup()
                popup.show_for(self._current_watched, html)


_hover_info_popup = None
_hover_info_filter = None


def get_hover_info_popup():
    global _hover_info_popup
    if _hover_info_popup is None:
        _hover_info_popup = HoverInfoPopup()
    return _hover_info_popup


def install_hover_info(widget, html, mode="side"):
    global _hover_info_filter
    if _hover_info_filter is None:
        _hover_info_filter = HoverInfoEventFilter()
    widget.setProperty("_hover_info_html", html)
    widget.setProperty("_hover_info_mode", mode)
    widget.setToolTip(html)
    widget.setMouseTracking(True)
    if not widget.property("_hover_info_installed"):
        widget.installEventFilter(_hover_info_filter)
        widget.setProperty("_hover_info_installed", True)



# ---------------------------------------------------------------------------
# _DetailExpandOverlay - floating panel so grid rows are never resized.
# ---------------------------------------------------------------------------
class _DetailExpandOverlay(QFrame):
    """Frameless tool window that hosts a DraggableTaskButton's detail_container
    so the calendar grid layout rows are never affected by expansion."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("detailExpandOverlay")
        self._owner = None
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(0)
        self.setStyleSheet(
            "QFrame#detailExpandOverlay { background: transparent; border: none; }"
        )
        self.hide()
        from PyQt6.QtWidgets import QApplication as _QApp
        _QApp.instance().applicationStateChanged.connect(self._on_app_state_changed)
        _QApp.instance().installEventFilter(self)

    def _on_app_state_changed(self, state):
        """Hide detail overlay when the application loses focus."""
        from PyQt6.QtCore import Qt as _Qt
        if state != _Qt.ApplicationState.ApplicationActive and self.isVisible():
            owner = self._owner
            if owner is None:
                self.hide()
                return
            self._owner = None
            try:
                owner._fade_anim.stop()
                owner._detail_anim_group.stop()
                self._take_back(owner)
                owner._info_opacity_fx.setOpacity(0.0)
                owner.detail_container.setMaximumHeight(0)
                owner.detail_container.setVisible(False)
                if owner._expanded:
                    owner._expanded = False
                    owner._detail_anim_expanding = False
                    owner._detail_anim_collapsing = False
                    owner.setProperty("expanded", False)
                    owner.style().unpolish(owner)
                    owner.style().polish(owner)
                    owner._apply_tag_frame_style()
            except RuntimeError:
                pass
            self.hide()

    def _do_collapse(self, owner=None):
        """Collapse and hide overlay, resetting owner's expand state."""
        if owner is None:
            owner = self._owner
        if owner is None:
            self.hide()
            return
        if self._owner is owner:
            self._owner = None
        try:
            owner._fade_anim.stop()
            owner._detail_anim_group.stop()
            self._take_back(owner)
            owner._info_opacity_fx.setOpacity(0.0)
            owner.detail_container.setMaximumHeight(0)
            owner.detail_container.setVisible(False)
            if owner._expanded:
                owner._expanded = False
                owner._detail_anim_expanding = False
                owner._detail_anim_collapsing = False
                owner.setProperty("expanded", False)
                owner.style().unpolish(owner)
                owner.style().polish(owner)
                owner._apply_tag_frame_style()
        except RuntimeError:
            pass
        self.hide()

    def eventFilter(self, obj, event):
        """Close overlay on any click outside the overlay and its owner."""
        from PyQt6.QtCore import QEvent as _QEvent
        if (event.type() == _QEvent.Type.MouseButtonPress
                and self.isVisible() and self._owner is not None):
            try:
                pos = event.globalPosition().toPoint()
            except AttributeError:
                from PyQt6.QtCore import QPoint as _QPoint2
                pos = event.globalPos()
            # Click inside overlay itself - keep open
            if self.geometry().contains(pos):
                return super().eventFilter(obj, event)
            # Click inside owner button - let it handle toggle
            try:
                from PyQt6.QtCore import QRect as _QRect, QPoint as _QPoint
                tl = self._owner.mapToGlobal(_QPoint(0, 0))
                owner_rect = _QRect(tl, self._owner.size())
                if owner_rect.contains(pos):
                    return super().eventFilter(obj, event)
            except RuntimeError:
                pass
            # Click outside - collapse
            self._do_collapse()
        return super().eventFilter(obj, event)

    def _take_back(self, button):
        """Return detail_container from overlay back to button (no layout)."""
        lyt = self.layout()
        if lyt.count() > 0:
            item = lyt.takeAt(0)
            w = item.widget() if item else None
            if w:
                try:
                    w.setParent(button)
                    w.setMaximumHeight(0)
                    w.setVisible(False)
                except RuntimeError:
                    pass

    def _reposition(self):
        """Position overlay just below owner's title_bar (global coords)."""
        try:
            if self._owner is None:
                return
            bar = self._owner.title_bar
            gp = bar.mapToGlobal(QPoint(0, bar.height()))
            self.setFixedWidth(min(bar.width(), 280))
            self.adjustSize()
            self.move(gp)
        except RuntimeError:
            self.hide()
            self._owner = None

    def show_for(self, owner):
        """Collapse any previous owner, host owner's detail_container, then show."""
        if self._owner is not None and self._owner is not owner:
            prev = self._owner
            self._owner = None
            try:
                prev._fade_anim.stop()
                prev._detail_anim_group.stop()
                self._take_back(prev)
                prev._info_opacity_fx.setOpacity(0.0)
                prev.detail_container.setMaximumHeight(0)
                prev.detail_container.setVisible(False)
                if prev._expanded:
                    prev._expanded = False
                    prev._detail_anim_expanding = False
                    prev._detail_anim_collapsing = False
                    prev.setProperty("expanded", False)
                    prev.style().unpolish(prev)
                    prev.style().polish(prev)
                    prev._apply_tag_frame_style()
            except RuntimeError:
                pass

        self._owner = owner

        lyt = self.layout()
        while lyt.count():
            item = lyt.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        lyt.addWidget(owner.detail_container)

        self._reposition()
        self.show()
        self.raise_()

    def hide_for(self, owner):
        """Hide overlay and return detail_container to owner."""
        if self._owner is not owner:
            return
        self._take_back(owner)
        self._owner = None
        self.hide()


_detail_overlay = None


def get_detail_overlay():
    global _detail_overlay
    if _detail_overlay is None:
        _detail_overlay = _DetailExpandOverlay()
    return _detail_overlay


class DraggableTaskButton(QFrame):
    # Signals: status by (task_id, new_status), others by task_id
    taskStatusChanged = pyqtSignal(int, str)
    taskPriorityChanged = pyqtSignal(int, str)
    taskDeleted = pyqtSignal(int)
    taskClicked = pyqtSignal(int, object)
    doubleClicked = pyqtSignal(int)
    selectedChanged = pyqtSignal(int, bool)
    colorChangeRequested = pyqtSignal(int)
    colorAutoAssignRequested = pyqtSignal(int)
    colorClearRequested = pyqtSignal(int)
    checklistRequested = pyqtSignal(int)
    alarmClearRequested = pyqtSignal(int)
    taskResized = pyqtSignal(int, int) # (task_id, new_duration_minutes)
    taskRenameRequested = pyqtSignal(int, str)
    
    moved = pyqtSignal(int, object, object)
    resized = pyqtSignal(int, int)

    def __init__(self, task_id, text, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.raw_text = text
        self.drag_start_pos = None
        self._selected = False
        self._expanded = False
        self._watermark_title = False
        self._tag_color = None
        self._is_double_click = False
        self._pending_expand_toggle = False
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._flush_single_click_toggle)
        
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setProperty("selected", False)
        self.setProperty("hovered", False)
        self.setProperty("expanded", False)
        
        # Outer layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Title Bar (The original button look)
        self.title_bar = QFrame()
        self.title_bar.setObjectName("taskTitleBar")
        self.title_bar.setMinimumHeight(22)
        self.title_layout = QHBoxLayout(self.title_bar)
        self.title_layout.setContentsMargins(8, 0, 8, 0)
        self.title_layout.setSpacing(6)
        
        self.title_label = _ElidingLabel(text)
        self.title_label.setWordWrap(False)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply_title_label_style()
        self.title_layout.addWidget(self.title_label)
        
        self.rename_edit = _InlineRenameEdit()
        self.rename_edit.hide()
        self.title_layout.addWidget(self.rename_edit)
        self.rename_edit.returnPressed.connect(self._commit_inline_rename)
        self.rename_edit.canceled.connect(self._cancel_inline_rename)
        
        self.main_layout.addWidget(self.title_bar)
        
        # 2. Detail Card (The "new block" below)
        self.detail_container = QFrame()
        self.detail_container.setObjectName("taskDetailCard")
        self.detail_container.setStyleSheet("""
            QFrame#taskDetailCard {
                background-color: rgba(22, 24, 31, 0.96);
                border-top: 1px solid rgba(255, 255, 255, 0.14);
                border-left: 1px solid rgba(255, 255, 255, 0.05);
                border-right: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 0px;
                margin: 0px 2px 2px 2px;
            }
        """)
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(10, 8, 10, 8)
        self.detail_layout.setSpacing(8)
        self.detail_container.setVisible(False)
        self.detail_container.setMaximumHeight(0)
        
        self.info_widget = QWidget()
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(4)
        self.detail_layout.addWidget(self.info_widget)
        
        self.checklist_widget = QWidget()
        self.checklist_layout = QVBoxLayout(self.checklist_widget)
        self.checklist_layout.setContentsMargins(0, 0, 0, 0)
        self.checklist_layout.setSpacing(2)
        self.detail_layout.addWidget(self.checklist_widget)
        
        # detail_container is a free child (not in main_layout) so grid rows
        # are never resized by expansion; overlay manages its geometry.
        
        # Opacity effect
        self._info_opacity_fx = QGraphicsOpacityEffect(self.detail_container)
        self._info_opacity_fx.setOpacity(0.0)
        self.detail_container.setGraphicsEffect(self._info_opacity_fx)
        
        # Animations
        self._height_anim = QPropertyAnimation(self.detail_container, b"maximumHeight", self)
        self._height_anim.setDuration(220)
        self._height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self._fade_anim = QPropertyAnimation(self._info_opacity_fx, b"opacity", self)
        self._fade_anim.setDuration(180)
        
        self._detail_anim_group = QParallelAnimationGroup(self)
        self._detail_anim_group.addAnimation(self._height_anim)
        # _fade_anim runs independently (not inside the anim group)
        self._fade_anim.finished.connect(self._on_detail_animation_finished)
        
        self._detail_anim_expanding = False
        self._detail_anim_collapsing = False
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def _parent_cell(self):
        """Find and return the target ClickableCell."""
        # 1. Check parents (for legacy/other views)
        p = self.parentWidget()
        while p is not None:
            if isinstance(p, ClickableCell):
                return p
            p = p.parentWidget()
                
        # 2. Check siblings in Week Widget (new Matrix layout)
        # Walk up to find the Week Widget (the one with the QGridLayout)
        curr = self.parentWidget()
        week_widget = None
        while curr:
            if curr.objectName() == "week_grid_container":
                week_widget = curr
                break
            # Fallback heuristic: check if layout is QGridLayout with nhi亦쇨콓 columns
            if curr.layout() and hasattr(curr.layout(), "columnCount") and curr.layout().columnCount() >= 5:
                week_widget = curr
                break
            curr = curr.parentWidget()
            
        if week_widget:
            lp = week_widget.mapFromGlobal(QCursor.pos())
            # Search for direct ClickableCell children that contain the point
            # Note: ClickableCell is the background, so it spans the whole column
            for cell in week_widget.findChildren(ClickableCell, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if cell.geometry().contains(lp):
                    return cell
            
        return None

    def _apply_title_label_style(self):
        from PyQt6.QtCore import QSettings

        if self._watermark_title:
            # Post-start multiday segments should never show text.
            color = "rgba(255, 255, 255, 0.0)"
            base_pt = int(QSettings("kimhyojin", "Dark Calendar").value("font_size", 10))
            wm_pt = max(7, base_pt - 1)
            size_rule = f"font-size: {wm_pt}pt;"
        else:
            color = "#ffffff"
            size_rule = ""
        weight = "bold" if self._selected else "normal"
        self.title_label.setStyleSheet(
            f"background: transparent; border: none; color: {color}; font-weight: {weight}; {size_rule}"
        )

    def set_title_watermark(self, enabled):
        enabled = bool(enabled)
        if self._watermark_title != enabled:
            self._watermark_title = enabled
            self._apply_title_label_style()
            self._apply_tag_frame_style()

    def set_multiday_segment_shape(self, left_open=False, right_open=False):
        left_open = bool(left_open)
        right_open = bool(right_open)
        changed = False
        if bool(self.property("multiday_left_open")) != left_open:
            self.setProperty("multiday_left_open", left_open)
            changed = True
        if bool(self.property("multiday_right_open")) != right_open:
            self.setProperty("multiday_right_open", right_open)
            changed = True
        if changed:
            self.style().unpolish(self)
            self.style().polish(self)
            self._apply_tag_frame_style()

    def _set_range_hover_state(self, active):
        active = bool(active)
        if bool(self.property("range_hovered")) == active:
            return
        self.setProperty("range_hovered", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_title_label_style()
        self._apply_tag_frame_style()

    def _sync_multiday_range_hover(self, active):
        if not bool(self.property("is_multiday_bar")):
            return
        root = self.window()
        if root is None:
            return
        for btn in root.findChildren(DraggableTaskButton):
            if not bool(btn.property("is_multiday_bar")):
                continue
            if getattr(btn, "task_id", None) != self.task_id:
                continue
            btn._set_range_hover_state(active)

    def dragEnterEvent(self, event):
        cell = self._parent_cell()
        if cell:
            cell.dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        cell = self._parent_cell()
        if cell:
            cell.dragMoveEvent(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        cell = self._parent_cell()
        if cell:
            cell.dragLeaveEvent(event)
        else:
            super().dragLeaveEvent(event)

    def dropEvent(self, event):
        cell = self._parent_cell()
        if cell:
            cell.dropEvent(event)
        else:
            event.ignore()

    def begin_inline_rename(self):
        task = task_repo.get_unified_task(self.task_id)
        if not task:
            return False

        current_name = (task.get("name") or "").strip()
        if not current_name:
            return False

        self.rename_edit.blockSignals(True)
        self.rename_edit.setText(current_name)
        self.rename_edit.blockSignals(False)
        self.title_label.hide()
        self.rename_edit.show()
        self.rename_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.rename_edit.selectAll()
        return True

    def _finish_inline_rename(self):
        self.rename_edit.hide()
        self.title_label.show()

    def _cancel_inline_rename(self):
        if self.rename_edit.isVisible():
            self._finish_inline_rename()

    def _commit_inline_rename(self):
        if not self.rename_edit.isVisible():
            return

        new_name = self.rename_edit.text().strip()
        task = task_repo.get_unified_task(self.task_id)
        self._finish_inline_rename()
        if not task or not new_name:
            return

        current_name = (task.get("name") or "").strip()
        if new_name == current_name:
            return

        self.taskRenameRequested.emit(self.task_id, new_name)

    def set_tag_color(self, color_hex):
        self._tag_color = color_hex if color_hex else None
        self._apply_tag_frame_style()

    def _apply_tag_frame_style(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtGui import QColor

        shape = get_ui_shape_tokens()
        task_title_radius = int(shape.get("task_title_radius", 0))
        task_outer_radius = int(shape.get("task_outer_radius", 0))
        l_open = bool(self.property("multiday_left_open"))
        r_open = bool(self.property("multiday_right_open"))
        l_rad = "0px" if l_open else f"{task_title_radius}px"
        r_rad = "0px" if r_open else f"{task_title_radius}px"
        l_width = "0px" if l_open else "3px"

        # 湲곕낯 ?뚮쭏 ?뺣낫 媛?몄삤湲?
        theme_color = get_theme_color()
        theme_obj = QColor(str(theme_color))
        if not theme_obj.isValid():
            theme_obj = QColor("#4da6ff")

        # ?좏깮 ???ㅽ???怨듯넻
        selected_bg = f"rgba({theme_obj.red()}, {theme_obj.green()}, {theme_obj.blue()}, 40)"
        selected_hover_bg = f"rgba({theme_obj.red()}, {theme_obj.green()}, {theme_obj.blue()}, 55)"
        selected_border = f"rgba({theme_obj.red()}, {theme_obj.green()}, {theme_obj.blue()}, 180)"

        if not self._tag_color:
            tag_line = "rgba(255, 255, 255, 0.25)"
            base_bg = "rgba(255, 255, 255, 0.05)"
            hover_bg = "rgba(255, 255, 255, 0.09)"
            range_hover_bg = "rgba(255, 255, 255, 0.12)"
        else:
            tag_color_obj = QColor(self._tag_color)
            if tag_color_obj.isValid():
                tag_line = f"rgba({tag_color_obj.red()}, {tag_color_obj.green()}, {tag_color_obj.blue()}, 0.95)"
                base_bg = f"rgba({tag_color_obj.red()}, {tag_color_obj.green()}, {tag_color_obj.blue()}, 0.12)"
                hover_bg = f"rgba({tag_color_obj.red()}, {tag_color_obj.green()}, {tag_color_obj.blue()}, 0.17)"
                range_hover_bg = f"rgba({tag_color_obj.red()}, {tag_color_obj.green()}, {tag_color_obj.blue()}, 0.22)"
                selected_bg = f"rgba({(theme_obj.red()+tag_color_obj.red())//2}, {(theme_obj.green()+tag_color_obj.green())//2}, {(theme_obj.blue()+tag_color_obj.blue())//2}, 45)"
            else:
                tag_line = self._tag_color
                base_bg = "rgba(255, 255, 255, 0.03)"
                hover_bg = "rgba(255, 255, 255, 0.06)"
                range_hover_bg = "rgba(255, 255, 255, 0.09)"

        hide_tag_strip = bool(self.property("hide_tag_strip"))
        left_border_color = tag_line if not hide_tag_strip else "transparent"
        left_border_width = l_width if not hide_tag_strip else "1px"

        self.setStyleSheet(f"""
            DraggableTaskButton {{ 
                background: transparent; border: none; border-radius: {task_outer_radius}px; padding: 0; 
            }}
            QFrame#taskTitleBar {{
                background: {base_bg};
                border: 0.5px solid rgba(255, 255, 255, 0.12);
                border-left: {left_border_width} solid {left_border_color};
                border-top-left-radius: {l_rad};
                border-bottom-left-radius: {l_rad};
                border-top-right-radius: {r_rad};
                border-bottom-right-radius: {r_rad};
            }}
            DraggableTaskButton[hovered="true"] QFrame#taskTitleBar {{
                background: {hover_bg};
                border: 0.5px solid rgba(255, 255, 255, 0.22);
            }}
            DraggableTaskButton[selected="true"] QFrame#taskTitleBar {{
                background: {selected_bg};
                border: 1px solid {selected_border};
                border-left: {left_border_width} solid {theme_color};
            }}
            DraggableTaskButton[selected="true"][hovered="true"] QFrame#taskTitleBar {{
                background: {selected_hover_bg};
                border: 1px solid {theme_color};
            }}
            DraggableTaskButton[range_hovered="true"] QFrame#taskTitleBar {{
                background: {range_hover_bg};
                border: 0.5px solid {theme_color};
            }}
        """)


    def _render_checklist_items(self):
        items = checklist_repo.get_task_checklist_items(self.task_id)
        if not items:
            return False

        self._checklist_display_type = items[0].get('display_type', 'list')
        if self._checklist_display_type == 'process':
            first_incomplete = next((item for item in items if item['is_completed'] == 0), None)
            items = [first_incomplete] if first_incomplete else []

        while self.checklist_layout.count():
            child = self.checklist_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not items:
            return False

        for item in items:
            row = WrappedChecklistRow(item['item_text'], item['is_completed'] == 1)
            row.toggled.connect(lambda checked, iid=item['id']: self._handle_item_toggled(iid, checked))
            self.checklist_layout.addWidget(row)

        self.checklist_layout.setSpacing(6)
        self.checklist_layout.setContentsMargins(10, 0, 2, 2)
        return True

    def _render_info_items(self):
        task = task_repo.get_unified_task(self.task_id)
        if not task: return False
        s = QSettings("kimhyojin", "Dark Calendar")
        text_theme, panel_base, opacity_factor = get_theme_palette_inputs(s)
        text_pal = derive_ui_palette(text_theme, panel_base, opacity_factor)
        
        while self.info_layout.count():
            child = self.info_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        def _clean_text(value):
            if value is None:
                return ""
            return strip_hashtags(str(value)).strip()

        def _add_info(label, text, rich=False):
            if not text:
                return
            row = QHBoxLayout()
            row.setSpacing(5)
            llbl = QLabel(label)
            llbl.setFixedWidth(70)
            llbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            llbl.setStyleSheet(f"background:transparent; color: {text_pal['text_secondary']}; font-size: 9pt;")
            tlbl = QLabel()
            if rich:
                from PyQt6.QtCore import Qt as _Qt
                tlbl.setTextFormat(_Qt.TextFormat.RichText)
            tlbl.setText(text)
            tlbl.setStyleSheet(f"background:transparent; color: {text_pal['text_primary']}; font-size: 9pt;")
            tlbl.setWordWrap(True)
            row.addWidget(llbl, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(tlbl, 1)
            self.info_layout.addLayout(row)

        # Time range
        _deadline_str = str(task['deadline']) if task.get('deadline') else ""
        _deadline_parts = _deadline_str.split()
        _is_all_day = bool(task.get('all_day')) or len(_deadline_parts) <= 1
        if _is_all_day:
            start = t('tooltip.all_day', 'All day')
        else:
            start = _deadline_parts[1][:5]
        end = str(task.get('end_date', '')).split()[1][:5] if task.get('end_date') and not _is_all_day else ""
        if end:
            _add_info(f"{_ICON_TIME} {t('tooltip.label_time', 'Time')}", f"{start} - {end}")
        else:
            _add_info(f"{_ICON_TIME} {t('tooltip.label_time', 'Time')}", start)
        
        location = task.get('location')
        clean_location = _clean_text(location)
        if clean_location and clean_location not in ['None', 'none', '-']:
            _add_info(f"{_ICON_LOCATION} {t('tooltip.label_location', 'Location')}", clean_location)

        assignee = task.get('assignee')
        clean_assignee = _clean_text(assignee)
        if clean_assignee and clean_assignee not in ['None', 'none', '-']:
            _add_info(f"{_ICON_ASSIGNEE} {t('tooltip.label_assignee', 'Assignee')}", clean_assignee)

        memo = task.get('memo') or task.get('description')
        clean_memo = _clean_text(memo)
        if clean_memo and clean_memo not in ['None', 'none', '-']:
            import html as _html_mod
            _lined = _html_mod.escape(clean_memo).replace('\n', '<br>')
            _add_info(f"{_ICON_DESC} {t('tooltip.label_description', 'Description')}", _lined, rich=True)
        
        return self.info_layout.count() > 0

    def _collapsed_detail_height(self):
        return 0

    def _expanded_detail_height(self):
        self.detail_container.layout().activate()
        hint = self.detail_container.layout().sizeHint().height()
        return max(40, hint + 10)

    def _on_detail_animation_finished(self):
        if self._detail_anim_collapsing:
            get_detail_overlay().hide_for(self)
            self._info_opacity_fx.setOpacity(0.0)
            self.detail_container.setMaximumHeight(0)
        elif self._detail_anim_expanding:
            self._info_opacity_fx.setOpacity(1.0)
            ov = get_detail_overlay()
            ov.adjustSize()
            ov._reposition()
        self._detail_anim_expanding = False
        self._detail_anim_collapsing = False


    def _animate_detail(self, expand):
        ov = get_detail_overlay()
        self._detail_anim_group.stop()
        self._fade_anim.stop()
        if expand:
            # Move detail_container into floating overlay (no grid impact)
            ov.show_for(self)
            # Populate content
            self.detail_container.setVisible(True)
            self.detail_container.setMaximumHeight(16777215)
            has_info = self._render_info_items()
            has_checklist = self._render_checklist_items()
            self.info_widget.setVisible(has_info)
            self.checklist_widget.setVisible(has_checklist)
            # Size overlay to fit content
            self.detail_container.updateGeometry()
            self.detail_container.adjustSize()
            ov.adjustSize()
            ov._reposition()
            # Fade in (no height animation needed; overlay is already full-size)
            self._detail_anim_expanding = True
            self._detail_anim_collapsing = False
            self._info_opacity_fx.setOpacity(0.0)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()
        else:
            self._detail_anim_expanding = False
            self._detail_anim_collapsing = True
            self._fade_anim.setStartValue(float(self._info_opacity_fx.opacity()))
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.start()



    def toggle_expand(self):
        """Toggle detail expansion showing both info and checklist."""
        if self._expanded:
            self._expanded = False
            self.setProperty("expanded", False)
            self._animate_detail(False)
        else:
            self._expanded = True
            self.setProperty("expanded", True)
            self._animate_detail(True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_tag_frame_style()


    def _handle_item_toggled(self, item_id, checked):
        """????? ?? ?? ??"""
        checklist_repo.toggle_checklist_item(item_id)

        progress = checklist_repo.get_task_checklist_progress(self.task_id)
        if progress['total'] > 0:
            base_title = self.raw_text.split(' (')[0]
            new_title = f"{base_title} ({progress['completed']}/{progress['total']})"
            self.title_label.setText(new_title)
            self.raw_text = new_title

        if getattr(self, '_checklist_display_type', 'list') == 'process':
            if not self._render_checklist_items():
                self._expanded = False
                self.checklist_widget.setVisible(False)
                self.setProperty("expanded", False)
                self.style().unpolish(self)
                self.style().polish(self)
                self._animate_detail(False)
                return

            self.checklist_widget.adjustSize()
            target_h = self._expanded_detail_height()
            self.info_widget.setMaximumHeight(target_h)
            self.updateGeometry()
    def contextMenuEvent(self, event):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtGui import QColor

        s = QSettings("kimhyojin", "Dark Calendar")
        theme = get_theme_color(s)
        color = QColor(theme)
        if not color.isValid():
            color = QColor("#4da6ff")

        panel_base = s.value("panel_base_color", "#1c1c1c")
        opacity = get_opacity_factor(s)
        base = QColor(str(panel_base))
        if not base.isValid():
            base = QColor("#1c1c1c")
        menu_bg = f"rgba({base.red()},{base.green()},{base.blue()},{max(210, int(242 * opacity))})"

        from calendar_app.shared.color_utils import derive_text_palette
        text_theme = s.value("text_theme", "dark")
        text_pal = derive_text_palette(text_theme, theme)
        menu_color = text_pal["text_primary"]

        sel_bg_a = f"rgba({color.red()},{color.green()},{color.blue()},0.18)"
        sel_bg_b = f"rgba({color.red()},{color.green()},{color.blue()},0.32)"
        sel_line = f"rgba({color.red()},{color.green()},{color.blue()},0.48)"
        shape = get_ui_shape_tokens()
        menu_radius = int(shape.get("context_menu_radius", 0))
        menu_item_radius = int(shape.get("context_menu_item_radius", 0))
        menu_style = f"""
            QMenu {{ background-color: {menu_bg}; color: {menu_color}; border: 1px solid rgba(255,255,255,18); padding: 5px; border-radius: {menu_radius}px; }}
            QMenu::item {{ padding: 5px 25px; border-radius: {menu_item_radius}px; }}
            QMenu::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {sel_bg_a}, stop:1 {sel_bg_b});
                border: 1px solid {sel_line};
                color: {menu_color};
            }}
            QMenu::separator {{ height: 1px; background: rgba(255,255,255,20); margin: 4px 10px; }}
        """
        menu = QMenu(self)
        menu.setStyleSheet(menu_style)

        edit_act = menu.addAction(t("context_menu.edit_schedule"))
        del_act = menu.addAction(t("context_menu.delete_schedule"))
        menu.addSeparator()

        priority_menu = menu.addMenu(t("context_menu.priority_change"))
        priority_menu.setStyleSheet(menu_style)
        prio_action_map = {}
        for label, value in PRIORITY_MENU_ITEMS:
            prio_action_map[priority_menu.addAction(label)] = value

        status_menu = menu.addMenu(t("context_menu.status_change"))
        status_menu.setStyleSheet(menu_style)
        stat_action_map = {}
        for label, value in STATUS_MENU_ITEMS:
            stat_action_map[status_menu.addAction(label)] = value

        color_menu = menu.addMenu(t("context_menu.color_tag"))
        color_menu.setStyleSheet(menu_style + """
            QMenu::item { padding: 5px 12px 5px 8px; }
        """)

        # ?? ?꾩옱 ?쒖뒪???됱긽 ?쎄린 ??????????????????????????????????????
        from calendar_app.infrastructure.db import task_repo as _tr
        from calendar_app.shared.google_color_palette import get_google_event_palette as _gpal
        _LOCAL_NAMES = {
            "1": t("color.lavender", "Lavender"), "2": t("color.sage", "Sage"), "3": t("color.grape", "Grape"), "4": t("color.flamingo", "Flamingo"),
            "5": t("color.banana", "Banana"), "6": t("color.tangerine", "Tangerine"), "7": t("color.peacock", "Peacock"), "8": t("color.graphite", "Graphite"),
            "9": t("color.blueberry", "Blueberry"), "10": t("color.basil", "Basil"), "11": t("color.tomato", "Tomato"),
        }
        _cur_task = _tr.get_unified_task(self.task_id)
        _cur_color = (_cur_task.get("bg_color") or "").lower().strip() if _cur_task else ""

        def _make_circle_icon(hex_color: str, size: int = 16, checked: bool = False) -> QIcon:
            px = QPixmap(size, size)
            px.fill(QColor(0, 0, 0, 0))
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(hex_color)))
            p.drawEllipse(1, 1, size - 2, size - 2)
            if checked:
                p.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                cx, cy, r = size / 2, size / 2, (size - 2) / 2
                p.drawLine(int(cx - r * 0.45), int(cy + 0.05),
                           int(cx - r * 0.05), int(cy + r * 0.45))
                p.drawLine(int(cx - r * 0.05), int(cy + r * 0.45),
                           int(cx + r * 0.5), int(cy - r * 0.4))
            p.end()
            return QIcon(px)

        color_action_map = {}
        for entry in _gpal():
            name = _LOCAL_NAMES.get(entry["id"], entry["name"])
            is_checked = entry["hex"].lower() == _cur_color
            act = color_menu.addAction(_make_circle_icon(entry["hex"], checked=is_checked), name)
            color_action_map[act] = entry["hex"]

        color_menu.addSeparator()
        color_auto_act = color_menu.addAction(t("context_menu.color_auto"))
        color_clear_act = color_menu.addAction(t("context_menu.color_clear"))

        menu.addSeparator()
        dday_widget_act = menu.addAction(t("context_menu.create_dday_widget", "D-day ?꾩젽"))
        chk_act = menu.addAction(t("context_menu.view_checklist"))
        alarm_clear_act = menu.addAction(t("context_menu.clear_alarm"))

        action = menu.exec(event.globalPos())

        if action == edit_act:
            self.doubleClicked.emit(self.task_id)
        elif action == del_act:
            self.taskDeleted.emit(self.task_id)
        elif action == color_auto_act:
            self.colorAutoAssignRequested.emit(self.task_id)
        elif action == color_clear_act:
            self.colorClearRequested.emit(self.task_id)
        elif action in color_action_map:
            chosen_hex = color_action_map[action]
            from calendar_app.infrastructure.db import task_repo as _tr2
            _tr2.update_unified_task(self.task_id, {"bg_color": chosen_hex})
            from calendar_app.presentation.main_window import action_handlers_tasks as _aht
            # 遺紐??깆뿉 패널 媛깆떊 ?붿껌
            p = self.parent()
            while p and not hasattr(p, "_refresh_all_panels"):
                p = p.parent()
            if p:
                p._refresh_all_panels()
                p.wake_gcal_sync() if hasattr(p, "wake_gcal_sync") else None
                from calendar_app.infrastructure.google_sync.helpers import sync_task_to_google
                import threading
                task_full = _tr2.get_unified_task(self.task_id)
                if task_full:
                    threading.Thread(
                        target=sync_task_to_google, args=(p, task_full), daemon=True
                    ).start()
        elif action == dday_widget_act:
            p = self.parent()
            while p and not hasattr(p, "create_dday_widget_for_task"):
                p = p.parent()
            if p:
                p.create_dday_widget_for_task(self.task_id)
        elif action == chk_act:
            self.checklistRequested.emit(self.task_id)
        elif action == alarm_clear_act:
            self.alarmClearRequested.emit(self.task_id)
        elif action in stat_action_map:
            new_status = stat_action_map[action]
            self.taskStatusChanged.emit(self.task_id, new_status)
        elif action in prio_action_map:
            new_prio = prio_action_map[action]
            from calendar_app.domain.task_constants import priority_icon
            new_ic = priority_icon(new_prio)
            # Apply UI update immediately for responsiveness
            parts = self.raw_text.split(' ', 1)
            if len(parts) > 1:
                self.raw_text = f"{new_ic} {parts[1]}"
                self.title_label.setText(self.raw_text)
            self.taskPriorityChanged.emit(self.task_id, new_prio)

    def _flush_single_click_toggle(self):
        if self._pending_expand_toggle and not self._is_double_click:
            self.toggle_expand()
        self._pending_expand_toggle = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._single_click_timer.stop()
            self._pending_expand_toggle = False
            self._is_double_click = True
            self.doubleClicked.emit(self.task_id)
        event.accept()

    def enterEvent(self, event):
        _set_hover_state(self, True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        _set_hover_state(self, False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._single_click_timer.stop()
            self._pending_expand_toggle = False
            self._is_double_click = False
            self.drag_start_pos = event.globalPosition().toPoint()
            self.clicked_pos = event.pos()
            app_window = self.window()
            if hasattr(app_window, "selected_task_ids"):
                self._drag_selection_snapshot = list(app_window.selected_task_ids)
            else:
                self._drag_selection_snapshot = []

            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and self._selected:
                self._defer_ctrl_toggle = True
            else:
                self._defer_ctrl_toggle = False
                self.taskClicked.emit(self.task_id, event.modifiers())
        elif event.button() == Qt.MouseButton.RightButton:
            self.taskClicked.emit(self.task_id, event.modifiers())
        event.accept()

    def set_selected(self, selected):
        if self._selected != selected:
            self._selected = selected
            self.setProperty("selected", selected)
            self._apply_title_label_style()
            self.style().unpolish(self)
            self.style().polish(self)
            self._apply_tag_frame_style()
            self.selectedChanged.emit(self.task_id, selected)

    def mouseMoveEvent(self, event):
        try:
            super().mouseMoveEvent(event)
            self.setCursor(Qt.CursorShape.PointingHandCursor)

            if (event.buttons() & Qt.MouseButton.LeftButton) and self.drag_start_pos:
                curr_gpos = event.globalPosition().toPoint()
                delta = curr_gpos - self.drag_start_pos

                if delta.manhattanLength() >= QApplication.startDragDistance():
                    if hasattr(self, "setDown"):
                        self.setDown(False)
                    self._defer_ctrl_toggle = False
                    try:
                        ddm.start_task_drag(self, event, self.task_id)
                    except RuntimeError:
                        logger.debug("Drag aborted for deleted task widget task_id=%s", self.task_id)
                    except Exception:
                        logger.exception("Unhandled error while starting drag for task_id=%s", self.task_id)
                    self.drag_start_pos = None
                    self._drag_selection_snapshot = []
        except Exception:
            logger.exception(
                "Unhandled error in DraggableTaskButton.mouseMoveEvent task_id=%s selected=%s drag_start_pos=%s",
                getattr(self, "task_id", None),
                getattr(self, "_selected", False),
                getattr(self, "drag_start_pos", None),
            )
            self.drag_start_pos = None
            self.resizing = False
            if hasattr(self, "setDown"):
                self.setDown(False)
            self._drag_selection_snapshot = []
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if self.drag_start_pos:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            if delta.manhattanLength() < QApplication.startDragDistance():
                if (
                    self._defer_ctrl_toggle
                    and event.button() == Qt.MouseButton.LeftButton
                    and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                ):
                    self.taskClicked.emit(self.task_id, event.modifiers())
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                    and not getattr(self, "_is_double_click", False)
                    and self.title_bar.geometry().contains(getattr(self, "clicked_pos", QPoint(-1, -1)))
                ):
                    self._pending_expand_toggle = True
                    interval = 250
                    app = QApplication.instance()
                    if app is not None:
                        interval = max(200, int(app.doubleClickInterval()))
                    self._single_click_timer.start(interval)

        self._defer_ctrl_toggle = False
        self._drag_selection_snapshot = []
    def event(self, event):
        # Block default tooltip event and use custom immediate tooltip
        from PyQt6.QtCore import QEvent
        if event.type() in (QEvent.Type.ToolTip, QEvent.Type.WhatsThis):
            event.accept()
            return True
        return super().event(event)

        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_title_label_style()
        self._apply_tag_frame_style()
        self._sync_multiday_range_hover(True)
        super().enterEvent(event)

        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_title_label_style()
        self._apply_tag_frame_style()
        self._sync_multiday_range_hover(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().leaveEvent(event)

class ClickableCell(QFrame):
    doubleClicked = pyqtSignal(object)
    shiftClicked = pyqtSignal(object)
    clicked = pyqtSignal(object)
    taskDropped = pyqtSignal(object, object, object, str) # task_id(int or list), date, time, action

    def __init__(self, target_date, target_time=None, parent=None):
        super().__init__(parent)
        self.target_date = target_date
        self.target_time = target_time
        self._pending_click_pack = None
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._flush_single_click)
        self.setAcceptDrops(True)
        self.setProperty("drag_mode", "none")
        self.setProperty("drag_batch", False)
        self.setProperty("drag_pulse", "off")
        self.setProperty("drag_range_preview", False)
        self.setProperty("drag_range_start", False)
        self.setProperty("drag_range_end", False)
        self._drag_pulse_timer = QTimer(self)
        self._drag_pulse_timer.setInterval(520)
        self._drag_pulse_timer.timeout.connect(self._toggle_drag_pulse)
        self._cached_drag_count = None
        self._cached_drag_span_days = None


    def _flush_single_click(self):
        if self._pending_click_pack is not None:
            self.clicked.emit(self._pending_click_pack)
        self._pending_click_pack = None

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self._single_click_timer.stop()
        self._pending_click_pack = None
        if isinstance(self.parent(), TimeGridContainer):
            self.parent().selecting = False
            if hasattr(self.parent(), "overlay"):
                self.parent().overlay.hide()
        self.doubleClicked.emit((self.target_date, self.target_time))
        event.accept()

    def enterEvent(self, event):
        _set_hover_state(self, True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        _set_hover_state(self, False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and isinstance(self.parent(), TimeGridContainer):
            self.parent().start_selection(self.mapToParent(event.pos()))

        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            pack = (self.target_date, self.target_time)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._single_click_timer.stop()
                self._pending_click_pack = None
                self.shiftClicked.emit(pack)
            else:
                self._single_click_timer.stop()
                self._pending_click_pack = pack
                interval = 250
                app = QApplication.instance()
                if app is not None:
                    interval = max(200, int(app.doubleClickInterval()))
                self._single_click_timer.start(interval)

    def mouseMoveEvent(self, event):
        if isinstance(self.parent(), TimeGridContainer) and self.parent().selecting:
            self.parent().mouseMoveEvent(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if isinstance(self.parent(), TimeGridContainer) and self.parent().selecting:
            self.parent().mouseReleaseEvent(event)
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-task-item"):
            # Cache payload parsing during this drag session.
            self._cached_drag_count = self._extract_drag_count(event.mimeData())
            self._cached_drag_span_days = self._extract_drag_span_days(event.mimeData())
            self._update_drag_batch(event.mimeData())
            self._update_drag_style(event.modifiers())
            self._update_drag_range_preview(event.mimeData())
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                event.setDropAction(Qt.DropAction.CopyAction)
            else:
                event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def _update_drag_style(self, modifiers):
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mode = "copy"
        else:
            mode = "move"

        if self.property("drag_mode") != mode:
            self.setProperty("drag_mode", mode)
            self.style().unpolish(self)
            self.style().polish(self)

        if mode == "none":
            self._reset_drag_style()
            return

        if not self._drag_pulse_timer.isActive():
            self.setProperty("drag_pulse", "on")
            self.style().unpolish(self)
            self.style().polish(self)
            self._drag_pulse_timer.start()

    def _update_drag_batch(self, mime_data):
        count = self._cached_drag_count if self._cached_drag_count is not None else self._extract_drag_count(mime_data)
        is_batch = count > 1
        if self.property("drag_batch") != is_batch:
            self.setProperty("drag_batch", is_batch)
            self.style().unpolish(self)
            self.style().polish(self)

    @staticmethod
    def _extract_drag_span_days(mime_data):
        try:
            if not mime_data.hasFormat("application/x-task-span-days"):
                return 1
            span_data = mime_data.data("application/x-task-span-days")
            data_stream = QDataStream(span_data, QIODevice.OpenModeFlag.ReadOnly)
            return max(1, data_stream.readInt32())
        except Exception:
            return 1

    @staticmethod
    def _clear_drag_range_preview_for_app(app):
        if app is None or not hasattr(app, "_drag_range_preview_cells"):
            return
        for cell in list(getattr(app, "_drag_range_preview_cells", []) or []):
            try:
                cell.setProperty("drag_range_preview", False)
                cell.setProperty("drag_range_start", False)
                cell.setProperty("drag_range_end", False)
                cell.style().unpolish(cell)
                cell.style().polish(cell)
            except RuntimeError:
                continue
        app._drag_range_preview_cells = []

    def _update_drag_range_preview(self, mime_data):
        app = self.window()
        if app is None:
            return

        span_days = (
            self._cached_drag_span_days
            if self._cached_drag_span_days is not None
            else self._extract_drag_span_days(mime_data)
        )
        date_map = getattr(app, "_calendar_cells_by_date", None)
        if (
            span_days <= 1
            or date_map is None
            or not hasattr(self.target_date, "toString")
        ):
            self._clear_drag_range_preview_for_app(app)
            return

        preview_cells = []
        for i in range(span_days):
            key = self.target_date.addDays(i).toString("yyyy-MM-dd")
            cell = date_map.get(key) if isinstance(date_map, dict) else None
            if cell is not None:
                preview_cells.append(cell)

        prev_cells = list(getattr(app, "_drag_range_preview_cells", []) or [])
        if prev_cells == preview_cells:
            return

        self._clear_drag_range_preview_for_app(app)

        for idx, cell in enumerate(preview_cells):
            try:
                cell.setProperty("drag_range_preview", True)
                cell.setProperty("drag_range_start", idx == 0)
                cell.setProperty("drag_range_end", idx == (len(preview_cells) - 1))
                cell.style().unpolish(cell)
                cell.style().polish(cell)
            except RuntimeError:
                continue
        app._drag_range_preview_cells = preview_cells

    @staticmethod
    def _extract_drag_count(mime_data):
        try:
            item_data = mime_data.data("application/x-task-item")
            data_stream = QDataStream(item_data, QIODevice.OpenModeFlag.ReadOnly)
            return data_stream.readInt32()
        except Exception:
            return 1

    def _toggle_drag_pulse(self):
        next_state = "off" if self.property("drag_pulse") == "on" else "on"
        self.setProperty("drag_pulse", next_state)
        self.style().unpolish(self)
        self.style().polish(self)

    def _reset_drag_style(self):
        self._cached_drag_count = None
        self._cached_drag_span_days = None
        self._drag_pulse_timer.stop()
        changed = False
        if self.property("drag_mode") != "none":
            self.setProperty("drag_mode", "none")
            changed = True
        if bool(self.property("drag_batch")):
            self.setProperty("drag_batch", False)
            changed = True
        if self.property("drag_pulse") != "off":
            self.setProperty("drag_pulse", "off")
            changed = True
        if changed:
            self.style().unpolish(self)
            self.style().polish(self)
        self._clear_drag_range_preview_for_app(self.window())

    def dragLeaveEvent(self, event):
        self._reset_drag_style()
        super().dragLeaveEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-task-item"):
            self._update_drag_batch(event.mimeData())
            self._update_drag_style(event.modifiers())
            self._update_drag_range_preview(event.mimeData())
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                event.setDropAction(Qt.DropAction.CopyAction)
            else:
                event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        self._reset_drag_style()
        try:
            if event.mimeData().hasFormat("application/x-task-item"):
                item_data = event.mimeData().data("application/x-task-item")
                data_stream = QDataStream(item_data, QIODevice.OpenModeFlag.ReadOnly)
                count = data_stream.readInt32()
                task_ids = []
                for _ in range(count):
                    task_ids.append(data_stream.readInt32())

                modifiers = event.modifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    action = "copy"
                else:
                    action = "move"

                self.taskDropped.emit(task_ids, self.target_date, self.target_time, action)
                event.accept()
            else:
                event.ignore()
        except Exception:
            logger.exception(
                "Unhandled error in ClickableCell.dropEvent target_date=%s target_time=%s",
                self.target_date.toString("yyyy-MM-dd") if hasattr(self.target_date, "toString") else self.target_date,
                self.target_time.toString("HH:mm") if hasattr(self.target_time, "toString") and self.target_time else self.target_time,
            )
            event.ignore()

class SelectionOverlay(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        # Theme-based translucent styling
        theme = get_theme_color()
        self.setStyleSheet(f"background: {theme}33; border: 1px solid {theme}; border-radius: 0px;")

class TimeGridContainer(QWidget):
    taskDropped = pyqtSignal(object, object, object, str)
    def __init__(self, target_date, parent=None):
        super().__init__(parent)
        self.target_date = target_date
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.selecting = False

    def mouseMoveEvent(self, event):
        try:
            if self.selecting:
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                curr_y = local_pos.y()
                y1 = min(self.select_start_y, curr_y)
                y2 = max(self.select_start_y, curr_y)
                self.overlay.setGeometry(0, int(y1), self.width(), int(y2 - y1))
            super().mouseMoveEvent(event)
        except Exception:
            logger.exception(
                "Unhandled error in TimeGridContainer.mouseMoveEvent target_date=%s selecting=%s select_start_y=%s",
                self.target_date.toString("yyyy-MM-dd") if hasattr(self.target_date, "toString") else self.target_date,
                self.selecting,
                getattr(self, "select_start_y", None),
            )
            self.selecting = False
            self.overlay.hide()

    def mouseReleaseEvent(self, event):
        if self.selecting:
            self.selecting = False
            self.overlay.hide()
            y1 = self.overlay.y()
            y2 = y1 + self.overlay.height()
            
            # ??蹂?뜟 ??ｌ뫒亦?(48px = 1??蹂?뜟)
            t1_total = (y1 / 48.0) * 60.0
            t2_total = (y2 / 48.0) * 60.0
            
            # Round to nearest 15-minute unit
            s1 = round(t1_total / 15.0) * 15
            s2 = max(s1 + 15, round(t2_total / 15.0) * 15)
            
            st = QTime(min(23, int(s1/60)), int(s1%60))
            et = QTime(min(23, int(s2/60)), int(s2%60))
            
            # Open create dialog on main window (with period support)
            app = self.window()
            if hasattr(app, "open_task_dialog"):
                # start_date, start_time, end_date, end_time
                # API: open_task_dialog(self, start_date=None, start_time=None, end_date=None, end_time=None)
                app.open_task_dialog(self.target_date, st, self.target_date, et)
            
        super().mouseReleaseEvent(event)
        
    def dropEvent(self, event):
        try:
            y = event.position().y()
            total_minutes = (y / 48.0) * 60.0
            snapped_minutes = round(total_minutes / 15.0) * 15

            hour = min(23, int(snapped_minutes / 60))
            minute = int(snapped_minutes % 60)

            if event.mimeData().hasFormat("application/x-task-item"):
                item_data = event.mimeData().data("application/x-task-item")
                data_stream = QDataStream(item_data, QIODevice.OpenModeFlag.ReadOnly)
                count = data_stream.readInt32()
                task_ids = [data_stream.readInt32() for _ in range(count)]

                modifiers = event.modifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    action = "copy"
                else:
                    action = "move"

                self.taskDropped.emit(task_ids, self.target_date, QTime(hour, minute), action)
                event.accept()
            else:
                event.ignore()
        except Exception:
            logger.exception(
                "Unhandled error in TimeGridContainer.dropEvent target_date=%s drop_y=%s",
                self.target_date.toString("yyyy-MM-dd") if hasattr(self.target_date, "toString") else self.target_date,
                event.position().y() if hasattr(event, "position") else None,
            )
            event.ignore()

