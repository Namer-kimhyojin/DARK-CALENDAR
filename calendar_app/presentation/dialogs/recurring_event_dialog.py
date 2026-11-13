# -*- coding: utf-8 -*-
"""
Dialog to choose the scope for editing or deleting a recurring GCal event.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


class RecurringEventScopeDialog(QDialog):
    """Ask the user whether to modify only this instance, this + following, or all."""

    SCOPE_SINGLE = "single"
    SCOPE_FOLLOWING = "this_and_following"
    SCOPE_ALL = "all"

    def __init__(self, mode: str = "edit", parent=None, *, allow_all: bool = True):
        """
        Parameters
        ----------
        mode : str
            ``"edit"`` or ``"delete"`` — controls label wording.
        """
        super().__init__(parent)
        self._mode = mode
        self._allow_all = bool(allow_all)
        self._scope = self.SCOPE_SINGLE
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        if self._mode == "delete":
            title = t("gcal.recurring.scope_dialog_title_delete", "반복 일정 삭제")
            single_lbl = t("gcal.recurring.delete_single", "이 일정만 삭제")
            following_lbl = t("gcal.recurring.delete_following", "이 일정 이후 모두 삭제")
            all_lbl = t("gcal.recurring.delete_all", "모든 일정 삭제")
        else:
            title = t("gcal.recurring.scope_dialog_title", "반복 일정 수정")
            single_lbl = t("gcal.recurring.edit_single", "이 일정만 수정")
            following_lbl = t("gcal.recurring.edit_following", "이 일정 이후 모두 수정")
            all_lbl = t("gcal.recurring.edit_all", "모든 일정 수정")

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setObjectName("RecurringScopeDialog")
        colors = get_dialog_theme_tokens()
        metrics = get_dialog_metric_tokens(apply_overrides=True)
        radius = int(metrics.get("field_radius", 10))
        apply_common_dialog_style(
            self,
            minimum_width=380,
            size=(440, 360),
            extra_stylesheet=f"""
                QDialog#RecurringScopeDialog QLabel#ScopeTitle {{
                    color: {colors["text_primary"]};
                    font-size: {int(metrics.get("base_font_pt", 14)) + 5}px;
                    font-weight: 700;
                }}
                QDialog#RecurringScopeDialog QLabel#ScopeHint {{
                    color: {colors["text_secondary"]};
                }}
                QDialog#RecurringScopeDialog QRadioButton {{
                    padding: 8px 10px;
                    border-radius: {radius}px;
                }}
                QDialog#RecurringScopeDialog QRadioButton:hover {{
                    background: {colors["surface_hover"]};
                }}
                QDialog#RecurringScopeDialog QRadioButton:checked {{
                    background: {colors["accent_soft_bg"]};
                }}
            """,
        )
        apply_dialog_title(self, title)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 18, 20, 18)

        heading = QLabel(title)
        heading.setObjectName("ScopeTitle")
        layout.addWidget(heading)

        info_label = QLabel(
            t(
                "gcal.recurring.scope_info",
                "이 일정은 반복 일정입니다. 수정/삭제 범위를 선택하세요.",
            )
        )
        info_label.setObjectName("ScopeHint")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self._btn_group = QButtonGroup(self)

        self._rb_single = QRadioButton(single_lbl)
        self._rb_single.setChecked(True)
        self._btn_group.addButton(self._rb_single, 0)
        layout.addWidget(self._rb_single)

        self._rb_following = QRadioButton(following_lbl)
        self._btn_group.addButton(self._rb_following, 1)
        layout.addWidget(self._rb_following)

        self._rb_all = QRadioButton(all_lbl)
        self._btn_group.addButton(self._rb_all, 2)
        self._rb_all.setVisible(self._allow_all)
        layout.addWidget(self._rb_all)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        footer, ok_btn, cancel_btn = build_dialog_footer(
            t("common.delete", "삭제") if self._mode == "delete" else t("common.edit", "수정"),
            t("btn.cancel", "취소"),
            ok_object_name="danger_btn" if self._mode == "delete" else "primary_btn",
        )
        if self._mode == "delete":
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
            cancel_btn.setDefault(True)
            cancel_btn.setAutoDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addLayout(footer)

    # ------------------------------------------------------------------
    def _on_accept(self):
        checked_id = self._btn_group.checkedId()
        if checked_id == 1:
            self._scope = self.SCOPE_FOLLOWING
        elif checked_id == 2:
            self._scope = self.SCOPE_ALL
        else:
            self._scope = self.SCOPE_SINGLE
        self.accept()

    def get_scope(self) -> str:
        """Return the selected scope constant after ``exec()``."""
        return self._scope
