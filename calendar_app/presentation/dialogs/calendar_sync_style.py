# -*- coding: utf-8 -*-
"""Theme-backed hierarchy shared by the calendar and subscription workspace."""

from calendar_app.shared.color_utils import contrast_safe_color


def build_sync_workspace_styles(tokens):
    surface = tokens["surface_alt"]
    primary = tokens["text_primary"]
    secondary = tokens["text_secondary"]
    border = tokens["border"]
    base = tokens["base_hex"]
    busy_text = contrast_safe_color(tokens["accent"], base, minimum=4.5)
    warning_text = contrast_safe_color(tokens["warning_hex"], base, minimum=4.5)
    success_text = contrast_safe_color(tokens["success_hex"], base, minimum=4.5)
    return f"""
    QScrollArea#SyncServices, QWidget#SyncServicesBody, QWidget#SyncServicesViewport,
    QScrollArea#SyncCalendars, QWidget#SyncCalendarsBody, QWidget#SyncCalendarsViewport,
    QScrollArea#SyncLocal, QWidget#SyncLocalBody, QWidget#SyncLocalViewport,
    QScrollArea#SyncIcs, QWidget#SyncIcsBody, QWidget#SyncIcsViewport,
    QScrollArea#SyncIssues, QWidget#SyncIssuesViewport {{
        background: transparent; border: none;
    }}
    QTabBar#SyncManagementTabBar::tab {{
        min-width: 0px; padding: 8px 10px;
    }}
    QFrame#SyncServiceCard, QFrame#SyncCalendarDetails,
    QFrame#SyncAvailableServices, QFrame#SyncCommonSettings {{
        background: {surface}; border: 1px solid {border}; border-radius: 12px;
    }}
    QPushButton[role="syncDisclosure"]:checked {{
        color: {busy_text}; background: {tokens["accent_soft_bg"]}; border-color: {tokens["accent"]};
    }}
    QFrame#SyncCalendarSection, QFrame#SyncSubscriptionSection, QFrame#SyncIssueDetails {{
        background: {tokens["content_bg"]}; border: 1px solid {tokens["border_soft"]}; border-radius: 10px;
    }}
    QLabel[role="syncWorkspaceTitle"] {{ font-size: 24px; font-weight: 700; color: {primary}; }}
    QLabel[role="syncCalendarTitle"] {{ font-size: 20px; font-weight: 700; color: {primary}; }}
    QLabel[role="syncServiceTitle"], QLabel[role="syncSectionTitle"] {{
        font-size: 15px; font-weight: 600; color: {primary};
    }}
    QLabel[role="syncMuted"], QLabel[role="syncStatus"] {{ color: {secondary}; }}
    QLabel[role="syncBadge"] {{
        color: {secondary}; background: {tokens["surface_item"]};
        padding: 4px 9px; border-radius: 6px; font-size: 12px;
    }}
    QLabel[role="syncBadge"][health="attention"] {{
        color: {warning_text}; background: {tokens["warning_soft_bg"]};
    }}
    QLabel[role="syncBadge"][health="busy"] {{
        color: {busy_text}; background: {tokens["accent_soft_bg"]};
    }}
    QLabel[role="syncBadge"][health="ok"] {{
        color: {success_text}; background: {tokens["success_soft_bg"]};
    }}
    QPushButton#primary_btn:disabled, QPushButton#ghost_btn:disabled {{
        color: {tokens["button_disabled_text"]}; background: {tokens["button_disabled_bg"]};
        border-color: {tokens["button_disabled_border"]};
    }}
    QLabel#SyncWorkspaceFeedback {{
        background: {tokens["accent_soft_bg"]}; color: {primary};
        padding: 10px; border-radius: 8px;
    }}
    QListWidget#SyncCalendarList::item {{ padding: 0; min-height: 76px; border: none; background: transparent; }}
    QListWidget#SyncCalendarList::item:selected {{ border: none; background: transparent; }}
    QFrame#SyncCalendarRow {{
        background: {tokens["surface_item"]}; border: 1px solid transparent; border-radius: 8px;
    }}
    QFrame#SyncCalendarRow[selected="true"] {{
        background: {tokens["accent_soft_bg"]}; border-color: {tokens["accent"]};
    }}
    QFrame#SyncCalendarRow QLabel {{ background: transparent; border: none; color: {primary}; }}
    QFrame#SyncCalendarRow QLabel[role="syncCalendarName"] {{ font-size: 14px; font-weight: 600; }}
    QFrame#SyncCalendarRow QLabel[role="syncMuted"] {{ font-size: 12px; color: {secondary}; }}
    QRadioButton#CalendarDefaultRadio {{ background: transparent; color: {secondary}; padding: 6px 0; }}
    QRadioButton#CalendarDefaultRadio:checked {{ color: {busy_text}; font-weight: 600; }}
    QRadioButton#CalendarDefaultRadio:disabled {{ color: {tokens["button_disabled_text"]}; }}
    QListWidget#SyncIssueList::item {{ padding: 12px 10px; min-height: 40px; }}
    """
