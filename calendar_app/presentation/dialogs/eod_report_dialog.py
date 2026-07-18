from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from calendar_app.application import eod_usecases
from calendar_app.infrastructure.db import directive_repo, legacy_report_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)


def _eod_report_style_bundle(tokens=None, settings=None) -> dict[str, str]:
    tokens = tokens or get_dialog_theme_tokens(settings=settings)
    return {
        "title": (f"font-size: 18px; font-weight: 700; color: {tokens.get('accent', '#4da6ff')};"),
        "section": (
            f"font-size: 13px; font-weight: 700; color: {tokens.get('text_secondary', '#c8ccd4')};"
        ),
        "item": (f"font-size: 12px; color: {tokens.get('text_primary', '#ffffff')};"),
        "empty": (f"font-size: 12px; color: {tokens.get('text_muted', '#9aa0ad')};"),
        "scroll": "QScrollArea { border: none; background: transparent; }",
    }


class EODReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("eod.title"))
        apply_common_dialog_style(self, minimum_width=500, size=(620, 620))
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        tokens = get_dialog_theme_tokens()
        styles = _eod_report_style_bundle(tokens=tokens)

        title_lbl = QLabel(t("eod.heading"))
        title_lbl.setStyleSheet(styles["title"])
        layout.addWidget(title_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(styles["scroll"])

        content_widget = QWidget()
        content_lay = QVBoxLayout(content_widget)

        today_str = QDate.currentDate().toString("yyyy-MM-dd")
        summary = eod_usecases.get_eod_summary(legacy_report_repo, directive_repo, today_str)
        events = summary.get("events", [])
        directives = summary.get("directives", [])

        events_lbl = QLabel(t("eod.events"))
        events_lbl.setStyleSheet(styles["section"])
        content_lay.addWidget(events_lbl)
        if not events:
            none_lbl = QLabel(t("eod.none"))
            none_lbl.setStyleSheet(styles["empty"])
            content_lay.addWidget(none_lbl)
        for event in events:
            event_lbl = QLabel(f"   - {event[1]} ({event[2]})")
            event_lbl.setStyleSheet(styles["item"])
            content_lay.addWidget(event_lbl)

        directives_lbl = QLabel(f"\n{t('eod.directives')}")
        directives_lbl.setStyleSheet(styles["section"])
        content_lay.addWidget(directives_lbl)
        if not directives:
            none_lbl = QLabel(t("eod.none"))
            none_lbl.setStyleSheet(styles["empty"])
            content_lay.addWidget(none_lbl)
        for directive in directives:
            directive_lbl = QLabel(f"   - {directive[1]} [{directive[4]}]")
            directive_lbl.setStyleSheet(styles["item"])
            content_lay.addWidget(directive_lbl)

        content_lay.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        footer_layout, close_btn, _ = build_dialog_footer(
            ok_label=t("common.close"),
            cancel_label=None,
            ok_object_name="ghost_btn",
        )
        close_btn.clicked.connect(self.accept)
        layout.addLayout(footer_layout)

        self.setLayout(layout)
