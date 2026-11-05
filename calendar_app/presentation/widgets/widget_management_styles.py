# -*- coding: utf-8 -*-
"""Semantic styling shared by the widget management hub and add gallery."""


def management_styles(tok):
    return f"""
        QWidget#hubDesktopBody, QScrollArea#hubModeScroll,
        QWidget#hubModeViewport, QWidget#hubModeBody,
        QScrollArea#hubWorkspaceScroll, QWidget#hubWorkspaceViewport,
        QWidget#hubWorkspaceBody, QScrollArea#hubDialogScroll,
        QWidget#hubDialogViewport, QWidget#hubDialogBody {{
            background: {tok["bg_main"]}; color: {tok["text_primary"]}; border: none; }}
        QTabWidget#hubTabs::pane {{ border: none; background: {tok["bg_main"]}; }}
        QScrollArea#hubGalleryScroll, QWidget#hubGalleryBody, QWidget#hubGalleryViewport {{
            background: {tok["bg_main"]}; color: {tok["text_primary"]}; border: none; }}
        QCheckBox#hubSnap {{ color: {tok["text_secondary"]}; background: transparent; }}
        QTabBar::tab {{ padding: 11px 20px; color: {tok["text_muted"]};
            background: {tok["bg_alt"]}; border-bottom: 3px solid transparent; }}
        QTabBar::tab:selected {{ color: {tok["text_primary"]}; font-weight: 700;
            border-bottom-color: {tok["accent"]}; background: {tok["bg_main"]}; }}
        QLabel#hubTitle {{ font-size: {tok["title_px"]}px; font-weight: 700; color: {tok["text_primary"]}; }}
        QLabel#hubBody {{ color: {tok["text_secondary"]}; font-size: {tok["body_px"]}px; }}
        QLabel#hubEyebrow {{ color: {tok["text_muted"]}; font-size: {tok["caption_px"]}px; }}
        QLabel#hubStatus {{ color: {tok["accent"]}; font-weight: 600; }}
        QFrame#hubSummary {{ background: {tok["bg_alt"]}; border: 1px solid {tok["border"]};
            border-radius: {tok["r_card"]}px; }}
        QPushButton#hubTypeCard {{ background: {tok["bg_item"]}; color: {tok["text_primary"]};
            border: 1px solid {tok["border"]}; border-radius: {tok["r_card"]}px;
            min-height: {max(58, 2 * tok["body_px"] + 20)}px;
            text-align: left; padding: 10px; font-size: {tok["body_px"]}px; }}
        QPushButton#hubTypeCard:checked {{ background: {tok["accent_soft"]};
            border: 2px solid {tok["accent"]}; }}
        QPushButton#hubTypeCard:hover {{ border-color: {tok["accent"]}; }}
        QPushButton#hubTypeCard:focus, QPushButton#ghost_btn:focus,
        QPushButton#primary_btn:focus {{ border: 2px solid {tok["accent"]}; }}
        QLineEdit#hubSearch {{ background: {tok["bg_item"]}; color: {tok["text_primary"]};
            border: 1px solid {tok["border"]}; border-radius: {tok["r_md"]}px; padding: 7px 10px; }}
        QComboBox#hubFilter {{ background: {tok["bg_item"]}; color: {tok["text_primary"]};
            border: 1px solid {tok["border"]}; border-radius: {tok["r_md"]}px; padding: 6px 10px; }}
        QFrame#WidgetCard {{ border-radius: {tok["r_card"]}px; border-left: 1px solid {tok["border"]}; }}
        QLineEdit#cardNameEdit:focus {{ border-bottom: 1px solid {tok["accent"]}; }}
        QLabel#cardIdLabel {{ font-size: {tok["caption_px"]}px; color: {tok["text_secondary"]}; }}
        QLabel#emptyLabel {{ padding: 24px; }}
        QComboBox#hubView {{ min-width: 64px; padding: 4px 8px; color: {tok["text_primary"]};
            background: {tok["bg_item"]}; border: 1px solid {tok["border"]}; border-radius: {tok["r_md"]}px; }}
        QListWidget#studioGallery, QListWidget#studioProfiles {{ background: {tok["bg_main"]};
            color: {tok["text_primary"]}; border: 1px solid {tok["border"]}; border-radius: {tok["r_card"]}px; }}
        QListWidget#studioGallery::item, QListWidget#studioProfiles::item {{ padding: 6px;
            background: {tok["bg_item"]}; border: 1px solid {tok["border"]}; border-radius: {tok["r_card"]}px; }}
        QListWidget#studioGallery::item:selected, QListWidget#studioProfiles::item:selected {{
            border: 2px solid {tok["accent"]}; background: {tok["accent_soft"]}; color: {tok["text_primary"]}; }}
        QScrollArea#studioInspector {{ background: {tok["bg_alt"]}; border: 1px solid {tok["border"]}; border-radius: {tok["r_card"]}px; }}
        QWidget#studioInspectorBody, QWidget#studioInspectorViewport {{ background: {tok["bg_alt"]}; }}
        QWidget#studioInspectorBody QLabel, QWidget#studioInspectorBody QCheckBox {{ color: {tok["text_primary"]}; background: transparent; }}
        QWidget#studioInspectorBody QSpinBox {{ min-width: 60px; max-width: 140px;
            color: {tok["text_primary"]}; background: {tok["bg_item"]}; border: 1px solid {tok["border"]}; }}
    """
