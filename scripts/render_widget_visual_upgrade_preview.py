# -*- coding: utf-8 -*-
"""Render offscreen QA previews for the overlay widget visual upgrade."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QDialog, QTabWidget, QWidget

from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager


def main() -> int:
    app = QApplication.instance() or QApplication([])
    output_dir = Path("artifacts/widget-visual-upgrade")
    output_dir.mkdir(parents=True, exist_ok=True)

    owner = QWidget()
    owner.resize(1200, 800)
    owner.settings = QSettings("codex_qa", "widget_visual_upgrade_preview")
    owner.settings.clear()
    manager = OverlayWidgetManager(owner)

    date_id = manager.add_instance("date_card", "계절 날짜")
    date_widget = manager.get_widget(date_id)
    date_widget._set("datecard_asset_pack", "air_moments")
    date_widget._set_widget_shape("circle")
    date_widget.show()

    dday_id = manager.add_instance("dday", "여행 D-Day")
    dday_widget = manager.get_widget(dday_id)
    dday_widget._set("dd_label", "제주 여행")
    dday_widget._set("dday_moment", "travel")
    dday_widget._set("dday_asset_pack", "paper_seasons")
    dday_widget._set_widget_shape("poster")
    dday_widget.show()
    app.processEvents()

    date_widget.grab().save(str(output_dir / "date-card-circle.png"), "PNG")
    dday_widget.grab().save(str(output_dir / "dday-poster.png"), "PNG")

    def _capture_dialog(dialog: QDialog) -> QDialog.DialogCode:
        tabs = dialog.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentIndex(1)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output_dir / "preset-gallery.png"), "PNG")
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", _capture_dialog):
        date_widget._open_settings()

    manager.remove_all()
    owner.settings.clear()
    owner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
