# -*- coding: utf-8 -*-
"""One internal title/close/drag surface for ordinary application dialogs."""

import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QMargins, QObject, QPoint, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QSizeGrip,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.app_lifecycle import is_app_exiting
from calendar_app.shared.brand_assets import brand_mark_pixmap
from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.icon_map import ICON, icon, strip_leading_emoji

_HEADER_NAMES = ("TaskEditorHeader", "dailySummaryDragHeader", "CommonDialogHeader")
_TITLE_NAMES = {"dialogTitle", "dialog_title", "ScopeTitle", "focusCompletionHeading"}


def _eligible(dialog) -> bool:
    if (
        not isinstance(dialog, QDialog)
        or sip.isdeleted(dialog)
        or not dialog.isWindow()
        or is_app_exiting()
        or dialog.property("dcSkipDialogChrome")
    ):
        return False
    kind = dialog.windowType()
    if kind in (Qt.WindowType.Popup, Qt.WindowType.ToolTip):
        return False
    # Native operating-system file pickers do not expose a Qt client layout.
    # The Qt fallback is styled while preserving its file mode and filters.
    return not (
        (
            isinstance(dialog, QFileDialog)
            and not dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        )
        or (
            isinstance(dialog, QColorDialog)
            and not dialog.testOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        )
    )


def _inherit_message_box_owner_topmost(dialog) -> None:
    """Keep a hidden standard message above its topmost owner, including nested owners."""
    if not isinstance(dialog, QMessageBox) or dialog.isVisible():
        return
    flag = Qt.WindowType.WindowStaysOnTopHint
    owner = dialog.parentWidget()
    owner_topmost = False
    while owner is not None:
        if owner.isWindow() and owner.windowFlags() & flag:
            owner_topmost = True
            break
        owner = owner.parentWidget()
    inherited = bool(dialog.property("_dc_owner_topmost_inherited"))
    current = bool(dialog.windowFlags() & flag)
    if inherited and not owner_topmost:
        dialog.setProperty("_dc_owner_topmost_inherited", False)
        if current:
            dialog.setWindowFlag(flag, False)
    elif owner_topmost and not current:
        dialog.setProperty("_dc_owner_topmost_inherited", True)
        dialog.setWindowFlag(flag, True)


def _restore_tool_dialog_owner(dialog) -> bool:
    """Retain the explicit overlay owner after Qt 6.12 skips Tool ancestors."""
    if not _eligible(dialog) or getattr(dialog, "_dc_native_owner_binding", False):
        return False
    parent = dialog.parentWidget()
    if parent is None or sip.isdeleted(parent):
        return False
    owner = parent.window()
    if owner is dialog or owner.windowType() != Qt.WindowType.Tool:
        return False
    handle, owner_handle = dialog.windowHandle(), owner.windowHandle()
    # Wait for native creation; never create HWNDs early or replace a caller's
    # explicit manager owner (for example the task router's nested modal).
    if handle is None or owner_handle is None or handle.transientParent() is not None:
        return False
    dialog._dc_native_owner_binding = True
    try:
        handle.setTransientParent(owner_handle)
    finally:
        dialog._dc_native_owner_binding = False
    return True


class _MessageBoxOwnerTopmostWatcher(QObject):
    """Reconcile a reused hidden message when its owner's native window changes."""

    def __init__(self, dialog):
        super().__init__(dialog)
        self._dialog_ref = weakref.ref(dialog)
        self._owners = []
        self._syncing = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        dialog.installEventFilter(self)

    def refresh(self):
        reference = getattr(self, "_dialog_ref", None)
        dialog = reference() if reference is not None else None
        if (
            getattr(self, "_syncing", True)
            or dialog is None
            or sip.isdeleted(dialog)
            or is_app_exiting()
        ):
            return
        self._syncing = True
        try:
            owners = []
            owner = dialog.parentWidget()
            while owner is not None:
                if owner.isWindow():
                    owners.append(owner)
                owner = owner.parentWidget()
            for reference in self._owners:
                previous = reference()
                if previous is not None and not sip.isdeleted(previous) and previous not in owners:
                    previous.removeEventFilter(self)
            previous_owners = [reference() for reference in self._owners]
            for owner in owners:
                if owner not in previous_owners:
                    owner.installEventFilter(self)
            self._owners = [weakref.ref(owner) for owner in owners]
            _inherit_message_box_owner_topmost(dialog)
        finally:
            self._syncing = False

    def eventFilter(self, watched, event):
        reference = getattr(self, "_dialog_ref", None)
        dialog = reference() if reference is not None else None
        if (
            getattr(self, "_syncing", True)
            or dialog is None
            or sip.isdeleted(dialog)
            or is_app_exiting()
        ):
            return False
        kind = event.type()
        if watched is not dialog and kind == QEvent.Type.WinIdChange:
            # Qt emits this before updating the owner's widget flags. Invalidate
            # only our derived policy while hidden, then read the final flags later.
            if not dialog.isVisible() and dialog.property("_dc_owner_topmost_inherited"):
                self._syncing = True
                try:
                    dialog.setProperty("_dc_owner_topmost_inherited", False)
                    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
                finally:
                    self._syncing = False
            self._timer.start(0)
        elif kind in (QEvent.Type.ParentChange, QEvent.Type.Hide, QEvent.Type.Show):
            self.refresh()
        return False


def prepare_dialog_chrome(dialog, *, settings=None) -> bool:
    """Set native flags before Show; never hide/recreate an active modal window."""
    if not _eligible(dialog):
        return False
    if settings is not None:
        dialog._dc_chrome_settings = settings
    if isinstance(dialog, QMessageBox):
        watcher = getattr(dialog, "_dc_owner_topmost_watcher", None)
        if watcher is None:
            watcher = _MessageBoxOwnerTopmostWatcher(dialog)
            dialog._dc_owner_topmost_watcher = watcher
        watcher.refresh()
    if not dialog.windowFlags() & Qt.WindowType.FramelessWindowHint:
        if dialog.isVisible():
            return False
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    _restore_tool_dialog_owner(dialog)
    dialog.setProperty("dcCommonChrome", True)
    controller = getattr(dialog, "_dc_dialog_chrome_controller", None)
    if controller is not None:
        controller.refresh_style()
    return True


def _title(dialog) -> str:
    return dialog.windowTitle() or dialog.accessibleName() or "Air Calendar"


def _plain_title(text: str) -> str:
    return " ".join(strip_leading_emoji(str(text)).split())


def _manual_windows_motion(dialog) -> bool:
    return QApplication.platformName() == "windows" and bool(
        dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    )


def _is_close(button) -> bool:
    if not isinstance(button, QAbstractButton):
        return False
    name = button.objectName().lower()
    label = _plain_title(button.accessibleName() or button.text()).casefold()
    close = _plain_title(t("common.close", "닫기")).casefold()
    return bool(
        button.property("dialogChromeClose")
        or "close" in name
        or label in {close, "close", "닫기", "×", "✕", "x"}
    )


def _belongs_to_dialog(widget, dialog) -> bool:
    """Keep an embedded QDialog's controls out of its outer modal's chrome."""
    while widget is not None:
        if isinstance(widget, QDialog):
            return widget is dialog
        widget = widget.parentWidget()
    return False


def _existing_header(dialog):
    candidates = []
    for name in _HEADER_NAMES:
        widget = dialog.findChild(QWidget, name)
        if widget is not None:
            candidates.append(widget)
    candidates.extend(
        widget
        for widget in dialog.findChildren(QWidget)
        if widget.property("role") == "dialogHeader" and widget not in candidates
    )
    for header in candidates:
        if not _belongs_to_dialog(header, dialog):
            continue
        close = next(
            (button for button in header.findChildren(QAbstractButton) if _is_close(button)), None
        )
        labels = header.findChildren(QLabel)
        title = next(
            (
                label
                for label in labels
                if _plain_title(label.text()) == _plain_title(_title(dialog))
            ),
            None,
        )
        return header, title, close, [header, *labels]

    # Some existing translucent dialogs use a header layout within their card.
    # Adopt that row without treating its whole body as a draggable title bar.
    for row in dialog.findChildren(QHBoxLayout):
        if not _belongs_to_dialog(row.parentWidget(), dialog):
            continue
        widgets = [row.itemAt(index).widget() for index in range(row.count())]
        close = next((widget for widget in widgets if _is_close(widget)), None)
        if close is None:
            continue
        labels = [widget for widget in widgets if isinstance(widget, QLabel)]
        title = next(
            (
                label
                for label in labels
                if label.objectName() in _TITLE_NAMES
                or _plain_title(label.text()) == _plain_title(_title(dialog))
            ),
            None,
        )
        if title is not None:
            return row.parentWidget(), title, close, labels
    return None


class _DialogChromeController(QObject):
    def __init__(self, dialog):
        super().__init__(dialog)
        self._dialog_ref = weakref.ref(dialog)
        self._drag_origin = None
        self._resize_origin = None
        self._resize_targets = []
        self._window_origin = QPoint()
        self._updating_geometry = False
        self._icon_color = None
        self._mark_palette = None
        self.mark_label = None
        self._base_margins = QMargins(dialog.contentsMargins())
        self._owns_header = False
        existing = _existing_header(dialog)
        if existing is None:
            self.header = QFrame(dialog)
            self.header.setObjectName("CommonDialogHeader")
            self.header.setProperty("role", "dialogHeader")
            row = QHBoxLayout(self.header)
            row.setContentsMargins(16, 8, 12, 8)
            row.setSpacing(10)
            mark = QLabel(self.header)
            self.mark_label = mark
            row.addWidget(mark)
            self.title_label = QLabel(_title(dialog), self.header)
            self.title_label.setObjectName("CommonDialogTitle")
            self.title_label.setProperty("role", "dialogTitle")
            self.title_label.setTextFormat(Qt.TextFormat.PlainText)
            self.title_label.setWordWrap(True)
            if isinstance(dialog, QColorDialog):
                # Qt's color-selector layout can finish after the shared chrome.
                # A selector caption is a single row, never a narrow text column.
                self.title_label.setWordWrap(False)
                self.title_label.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
                )
                self.title_label.setMinimumWidth(0)
                self.title_label.setToolTip(_title(dialog))
            row.addWidget(self.title_label, 1)
            self.close_button = QToolButton(self.header)
            self.close_button.setObjectName("CommonDialogClose")
            self.close_button.clicked.connect(dialog.close)
            row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
            self._owns_header = True
            self._drag_targets = [self.header, mark, self.title_label]
            self._hide_duplicate_title()
        else:
            self.header, self.title_label, self.close_button, self._drag_targets = existing
            if self.close_button is None:
                self.close_button = QToolButton(self.header)
                self.close_button.setObjectName("CommonDialogClose")
                self.close_button.clicked.connect(dialog.close)
                self._add_close_overlay()

        self.header.setProperty("dialogChromeHeader", True)
        self.close_button.setProperty("dialogChromeClose", True)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setText("")
        self.close_button.setAccessibleName(t("common.close", "닫기"))
        self.close_button.setToolTip(self.close_button.accessibleName())
        for target in self._drag_targets:
            target.installEventFilter(self)
        dialog.installEventFilter(self)
        self.header.installEventFilter(self)
        if not (
            dialog.minimumWidth() == dialog.maximumWidth()
            and dialog.minimumHeight() == dialog.maximumHeight()
        ):
            dialog.setSizeGripEnabled(True)
        self._resize_targets = [
            grip for grip in dialog.findChildren(QSizeGrip) if _belongs_to_dialog(grip, dialog)
        ]
        for grip in self._resize_targets:
            grip.installEventFilter(self)
        self.refresh_style()
        self._update_header_geometry()
        self.header.show()

    @property
    def dialog(self):
        reference = getattr(self, "_dialog_ref", None)
        return reference() if reference is not None else None

    def _hide_duplicate_title(self):
        if isinstance(self.dialog, (QMessageBox, QInputDialog)):
            return
        expected = _plain_title(_title(self.dialog))
        for label in self.dialog.findChildren(QLabel):
            if (
                label is self.title_label
                or self.header.isAncestorOf(label)
                or not _belongs_to_dialog(label, self.dialog)
            ):
                continue
            heading = (
                label.property("role") in {"dialogTitle", "title"}
                or label.objectName() in _TITLE_NAMES
            )
            if heading and _plain_title(label.text()) == expected:
                label.hide()
                label.setProperty("dialogChromeDuplicateTitle", True)

    def _add_close_overlay(self):
        self.header.setProperty("dialogChromeCloseOverlay", True)
        layout = self.header.layout()
        if layout is not None:
            margins = layout.contentsMargins()
            layout.setContentsMargins(
                margins.left(), margins.top(), margins.right() + 40, margins.bottom()
            )

    def refresh_style(self):
        dialog = self.dialog
        header = getattr(self, "header", None)
        close_button = getattr(self, "close_button", None)
        if (
            dialog is None
            or header is None
            or close_button is None
            or sip.isdeleted(dialog)
            or sip.isdeleted(header)
            or sip.isdeleted(close_button)
            or is_app_exiting()
        ):
            return
        # Local import avoids a dialog_styles -> chrome -> dialog_styles cycle.
        from calendar_app.presentation.dialogs.dialog_styles import (
            _dialog_settings,
            get_dialog_theme_tokens,
        )

        settings = getattr(self.dialog, "_dc_chrome_settings", None)
        tokens = get_dialog_theme_tokens(settings=_dialog_settings(self.dialog, settings))
        foreground = parse_css_color(tokens["text_primary"]).name()
        if foreground != self._icon_color:
            self.close_button.setIcon(icon(ICON.CLOSE, color=foreground))
            self._icon_color = foreground
        close_style = (
            "QToolButton, QPushButton { min-width: 32px; max-width: 32px; "
            "min-height: 32px; max-height: 32px; padding: 0; margin: 0; "
            f"background: transparent; color: {tokens['text_primary']}; border: none; border-radius: 8px; }}"
            f"QToolButton:hover, QPushButton:hover {{ background: {tokens['surface_hover']}; }}"
        )
        if self.close_button.styleSheet() != close_style:
            self.close_button.setStyleSheet(close_style)
        if self._owns_header:
            mark_palette = (
                tokens["accent"],
                tokens["floating_bg"],
                tokens["base_hex"],
                dialog.devicePixelRatioF(),
            )
            if self._mark_palette != mark_palette:
                mark = brand_mark_pixmap(
                    tokens["accent"],
                    20,
                    background=tokens["floating_bg"],
                    base=tokens["base_hex"],
                    dpr=dialog.devicePixelRatioF(),
                )
                self.mark_label.setPixmap(mark)
                self.mark_label.setVisible(not mark.isNull())
                self._mark_palette = mark_palette
            header_style = (
                f"QFrame#CommonDialogHeader {{ background: {tokens['floating_bg']}; "
                f"border: none; border-bottom: 1px solid {tokens['border_soft']}; }}"
            )
            if self.header.styleSheet() != header_style:
                self.header.setStyleSheet(header_style)

    def _update_header_geometry(self):
        dialog = self.dialog
        header = getattr(self, "header", None)
        if (
            getattr(self, "_updating_geometry", True)
            or dialog is None
            or header is None
            or sip.isdeleted(dialog)
            or sip.isdeleted(header)
            or is_app_exiting()
        ):
            return
        self._updating_geometry = True
        try:
            if self._owns_header:
                margins = self._base_margins
                width = max(1, self.dialog.width() - margins.left() - margins.right())
                layout = self.header.layout()
                height = max(48, layout.sizeHint().height(), layout.heightForWidth(width))
                if isinstance(dialog, QColorDialog):
                    self.header.setFixedWidth(width)
                self.dialog.setContentsMargins(
                    margins.left(), margins.top() + height, margins.right(), margins.bottom()
                )
                self.header.setGeometry(margins.left(), margins.top(), width, height)
                self.header.raise_()
            elif self.header.property("dialogChromeCloseOverlay"):
                self.close_button.setGeometry(max(0, self.header.width() - 40), 6, 32, 32)
        finally:
            self._updating_geometry = False

    def _resize_from_grip(self, dialog, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._resize_origin = (
                event.globalPosition().toPoint(),
                dialog.geometry(),
                dialog.isRightToLeft(),
            )
            return True
        if (
            kind == QEvent.Type.MouseMove
            and self._resize_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            global_origin, geometry, from_left = self._resize_origin
            delta = event.globalPosition().toPoint() - global_origin
            width = geometry.width() + (-delta.x() if from_left else delta.x())
            height = geometry.height() + delta.y()
            width = max(dialog.minimumWidth(), min(dialog.maximumWidth(), width))
            height = max(dialog.minimumHeight(), min(dialog.maximumHeight(), height))
            left = geometry.x() + geometry.width() - width if from_left else geometry.x()
            dialog.setGeometry(left, geometry.y(), width, height)
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self._resize_origin = None
            return True
        return False

    def eventFilter(self, watched, event):
        # Qt can deliver final events while cyclic GC has already cleared this
        # Python object's dict. A cosmetic filter must never raise into Qt then.
        reference = getattr(self, "_dialog_ref", None)
        header = getattr(self, "header", None)
        if reference is None or header is None or is_app_exiting():
            return False
        dialog = reference()
        if dialog is None or sip.isdeleted(dialog) or sip.isdeleted(header):
            return False
        kind = event.type()
        if watched is dialog and kind in (QEvent.Type.WinIdChange, QEvent.Type.Show):
            _restore_tool_dialog_owner(dialog)
            if kind == QEvent.Type.Show and isinstance(dialog, QColorDialog):
                # Reconcile once Qt has completed the selector's deferred layout.
                QTimer.singleShot(0, self._update_header_geometry)
        if watched is self.dialog and kind == QEvent.Type.WindowTitleChange:
            if self.title_label is not None:
                self.title_label.setText(_title(self.dialog))
            self._update_header_geometry()
        elif kind in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.FontChange):
            self._update_header_geometry()
        if watched in self._resize_targets:
            return (
                self._resize_from_grip(dialog, event) if _manual_windows_motion(dialog) else False
            )
        if watched not in self._drag_targets:
            return False
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            # Keep the press origin even if the platform starts a native move.
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self.dialog.pos()
            # The Windows native move loop can consume the rest of a frameless
            # header gesture without moving the window. Let Qt deliver its normal
            # captured press/move/release sequence for application-owned headers.
            if not _manual_windows_motion(dialog):
                handle = self.dialog.windowHandle()
                if handle is not None:
                    handle.startSystemMove()
            return True
        if (
            kind == QEvent.Type.MouseMove
            and self._drag_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.dialog.move(
                self._window_origin + event.globalPosition().toPoint() - self._drag_origin
            )
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            return True
        return False


def ensure_dialog_chrome(dialog, *, settings=None) -> bool:
    """Attach one reusable header after the dialog has built its controls."""
    if not prepare_dialog_chrome(dialog, settings=settings) or dialog.layout() is None:
        return False
    if getattr(dialog, "_dc_dialog_chrome_installing", False):
        return False
    controller = getattr(dialog, "_dc_dialog_chrome_controller", None)
    if controller is None:
        dialog._dc_dialog_chrome_installing = True
        try:
            controller = _DialogChromeController(dialog)
            dialog._dc_dialog_chrome_controller = controller
        finally:
            dialog._dc_dialog_chrome_installing = False
    else:
        controller.refresh_style()
    from calendar_app.presentation.dialogs.dialog_shadow import ensure_dialog_shadow

    ensure_dialog_shadow(dialog, settings=settings)
    return True
