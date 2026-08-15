# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
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
from calendar_app.presentation.dialogs.focus_history_panel import (
    FocusHistoryPanel,
    _focus_history_style_bundle,
)


def _focus_log_style_bundle(tokens=None, metrics=None):
    """Compatibility alias for tests and theme-contract consumers."""
    return _focus_history_style_bundle(tokens=tokens, metrics=metrics)


class FocusLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.focus_log.title"))
        apply_common_dialog_style(self, minimum_width=500, size=(550, 600))
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _focus_log_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        self._load_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 헤더
        header = QLabel(t("dialog.focus_log.header"))
        header.setStyleSheet(self._style_bundle["header"])
        layout.addWidget(header)

        self.history_panel = FocusHistoryPanel(
            self,
            show_heading=False,
            allow_delete=False,
            show_controls=False,
            tokens=self._ui_tokens,
            metrics=self._dialog_metrics,
        )
        self.table = self.history_panel.table
        layout.addWidget(self.history_panel, 1)

        footer, close_btn, _ = build_dialog_footer(
            ok_label=t("dialog.focus_log.close", "닫기"),
            cancel_label=None,
            ok_object_name="ghost_btn",
        )
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(self._style_bundle["button_secondary"])
        close_btn.setDefault(False)
        close_btn.setAutoDefault(False)

        refresh_btn = QPushButton(t("dialog.focus_log.refresh", "새로고침"))
        refresh_btn.setObjectName("ghost_btn")
        refresh_btn.setStyleSheet(self._style_bundle["button_secondary"])
        refresh_btn.setAutoDefault(False)
        refresh_btn.clicked.connect(self._load_logs)
        footer.insertWidget(1, refresh_btn)
        layout.addLayout(footer)

    def _load_logs(self):
        self.history_panel.reload()
