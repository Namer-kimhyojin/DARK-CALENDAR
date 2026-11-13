# -*- coding: utf-8 -*-
"""GIF gallery with one live preview and an explicit apply/cancel boundary."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.datecard_animations import (
    DATE_ANIMATIONS,
    AnimatedDateSurface,
    date_animation,
)


class DateAnimationDialog(QDialog):
    def __init__(self, widget):
        super().__init__(widget)
        apply_dialog_title(self, t("date_animation.choose", "움직이는 GIF 꾸미기"))
        apply_common_dialog_style(self, minimum_width=600)
        self.animation_id = date_animation(widget._get("datecard_animation", "sakura")).animation_id
        self.motion = widget._get("datecard_animation_motion", True, type_=bool)
        self.resize(650, 565)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        hint = QLabel(
            t(
                "date_animation.hint",
                "그림을 고르고 적용을 누르세요. 날짜는 매일 자동으로 바뀝니다.",
            ),
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        body = QHBoxLayout()
        body.setSpacing(22)
        self.choices = QListWidget(self)
        self.choices.setIconSize(QSize(48, 48))
        self.choices.setMinimumWidth(100)
        self.choices.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.choices.setAccessibleName(t("date_animation.choices", "GIF 디자인 목록"))
        for animation in DATE_ANIMATIONS:
            item = QListWidgetItem(QIcon(QPixmap(animation.filename())), animation.title())
            item.setToolTip(item.text())
            item.setData(Qt.ItemDataRole.UserRole, animation.animation_id)
            item.setSizeHint(QSize(0, 54))
            self.choices.addItem(item)
        body.addWidget(self.choices, 1)
        self.preview = AnimatedDateSurface(self)
        self.preview.setMinimumSize(100, 100)
        self.preview.setMaximumWidth(270)
        self.preview.configure(self.animation_id, family=widget.font_family(), motion=self.motion)
        self.preview.set_runtime_active(True)
        body.addWidget(self.preview, 1)
        root.addLayout(body, 1)
        self.motion_check = QCheckBox(t("date_animation.motion", "애니메이션 재생"), self)
        self.motion_check.setChecked(self.motion)
        root.addWidget(self.motion_check)
        policy_hint = QLabel(
            t(
                "date_animation.policy",
                "숨김·절전·시스템 움직임 끄기에서는 정지 그림으로 표시합니다.",
            ),
            self,
        )
        policy_hint.setWordWrap(True)
        policy_hint.setProperty("role", "dialogSubtitle")
        root.addWidget(policy_hint)
        footer, apply_btn, cancel_btn = build_dialog_footer(
            t("btn.apply", "적용"), t("btn.cancel", "취소")
        )
        root.addLayout(footer)
        apply_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self.choices.currentRowChanged.connect(self._select)
        self.motion_check.toggled.connect(self._motion_changed)
        self.choices.setCurrentRow(
            next(
                index
                for index, item in enumerate(DATE_ANIMATIONS)
                if item.animation_id == self.animation_id
            )
        )

    def _select(self, row):
        if row < 0:
            return
        self.animation_id = DATE_ANIMATIONS[row].animation_id
        self._refresh()

    def _motion_changed(self, enabled):
        self.motion = enabled
        self._refresh()

    def _refresh(self):
        self.preview.configure(self.animation_id, family=self.preview.family, motion=self.motion)

    def hideEvent(self, event):  # noqa: N802
        self.preview.set_runtime_active(False)
        super().hideEvent(event)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.choices.scrollToItem(self.choices.currentItem())
        self.preview.set_runtime_active(True)
