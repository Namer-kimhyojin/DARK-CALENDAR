from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import directive_repo, search_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.nlp.nlp_engine import parse_nlp_task
from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    get_key,
    get_shortcut_guide_entries,
)
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_metric_tokens
from calendar_app.shared.color_utils import parse_css_alpha_to_unit
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.ui_tokens import get_ui_tokens

_RGBA_COLOR_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_RECENT_COMMANDS_KEY = "palette_recent_command_ids"
_RESULT_LIMIT = 9
_EMPTY_HEIGHT = 132
_ITEM_HEIGHT = 58
_DEFAULT_COMMAND_IDS = (
    "open_task_dialog",
    "jump_to_today",
    "toggle_focus_mode",
    "open_work_management_dialog",
    "sync_google_calendar",
    "open_widget_manager",
    "show_shortcut_guide",
)


def _normalize(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip()).casefold()


def _split_terms(text: str) -> list[str]:
    return [term for term in re.split(r"\s+", _normalize(text)) if term]


def _palette_qcolor(value, fallback="#101418"):
    raw = str(value or "").strip()
    match = _RGBA_COLOR_RE.match(raw)
    if match:
        r, g, b, alpha_raw = match.groups()
        try:
            alpha = max(0.0, min(1.0, parse_css_alpha_to_unit(alpha_raw)))
        except Exception:
            alpha = 1.0
        color = QColor(int(r), int(g), int(b), int(round(alpha * 255)))
    else:
        color = QColor(raw)
    if color.isValid():
        return color
    fallback_color = QColor(fallback)
    return fallback_color if fallback_color.isValid() else QColor("#101418")


def _command_palette_style_bundle(tokens=None, metrics=None, settings=None):
    resolved_tokens = dict(get_ui_tokens(settings=settings))
    if tokens:
        resolved_tokens.update(tokens)
    resolved_metrics = dict(get_dialog_metric_tokens(settings=settings))
    if metrics:
        resolved_metrics.update(metrics)

    container_radius = max(14, int(resolved_metrics.get("button_radius", 8)) + 8)
    input_radius = max(10, int(resolved_metrics.get("field_radius", 8)) + 6)
    item_radius = max(8, int(resolved_metrics.get("list_item_radius", 4)) + 4)
    hint_radius = max(10, container_radius)
    item_margin = max(8, int(resolved_metrics.get("field_padding_x", 8)) + 4)
    input_padding_y = max(10, int(resolved_metrics.get("field_padding_y", 3)) + 7)
    input_padding_x = max(14, int(resolved_metrics.get("field_padding_x", 8)) + 8)

    shadow = _palette_qcolor(resolved_tokens.get("bg_main"), "#101418")
    shadow.setAlpha(220)

    return {
        "container_radius": container_radius,
        "input_radius": input_radius,
        "item_radius": item_radius,
        "container_bg": resolved_tokens["bg_main"],
        "container_border": resolved_tokens["border"],
        "input_bg": resolved_tokens["bg_item"],
        "input_focus_bg": resolved_tokens["bg_item_hover"],
        "input_border": resolved_tokens.get("border_soft") or resolved_tokens["border"],
        "list_text": resolved_tokens["text_secondary"],
        "item_text": resolved_tokens["text_primary"],
        "item_selected_bg": resolved_tokens["accent_soft"],
        "item_selected_text": resolved_tokens["text_primary"],
        "divider": resolved_tokens.get("divider") or resolved_tokens["border"],
        "hint_bg": resolved_tokens["bg_hover"],
        "hint_text": resolved_tokens["text_muted"],
        "preview_text": resolved_tokens["accent"],
        "focus_border": resolved_tokens["accent"],
        "shadow_color": shadow,
        "input_padding_y": input_padding_y,
        "input_padding_x": input_padding_x,
        "item_margin": item_margin,
        "hint_radius": hint_radius,
    }


def _build_command_palette_stylesheet(bundle: dict) -> str:
    return f"""
            #palette_container {{
                background-color: {bundle["container_bg"]};
                border: 1px solid {bundle["container_border"]};
                border-radius: {bundle["container_radius"]}px;
            }}
            QLineEdit {{
                background: {bundle["input_bg"]};
                border: 1px solid {bundle["input_border"]};
                border-radius: {bundle["input_radius"]}px;
                padding: {bundle["input_padding_y"]}px {bundle["input_padding_x"]}px;
                font-size: 17px;
                color: {bundle["item_text"]};
                font-family: 'Segoe UI', 'Malgun Gothic', 'Inter', sans-serif;
            }}
            QLineEdit:focus {{
                border-color: {bundle["focus_border"]};
                background: {bundle["input_focus_bg"]};
            }}
            QListWidget {{
                background: transparent;
                border: none;
                color: {bundle["list_text"]};
                font-size: 13px;
                outline: none;
                padding-bottom: 4px;
            }}
            QListWidget::item {{
                padding: 10px 16px;
                border-radius: {bundle["item_radius"]}px;
                margin: 2px {bundle["item_margin"]}px;
                color: {bundle["item_text"]};
            }}
            QListWidget::item:selected {{
                background-color: {bundle["item_selected_bg"]};
                color: {bundle["item_selected_text"]};
            }}
            QLabel#palettePreview {{
                color: {bundle["preview_text"]};
                font-size: 11px;
                margin-top: 6px;
                border: none;
                background: transparent;
                font-weight: bold;
            }}
            QFrame#paletteDivider {{
                background-color: {bundle["divider"]};
                max-height: 1px;
                border: none;
            }}
            QFrame#paletteHintBar {{
                background: {bundle["hint_bg"]};
                border-bottom-left-radius: {bundle["hint_radius"]}px;
                border-bottom-right-radius: {bundle["hint_radius"]}px;
            }}
            QLabel#paletteHintLabel {{
                color: {bundle["hint_text"]};
                font-size: 10px;
            }}
        """


def _parse_query_mode(text: str) -> tuple[str, str]:
    raw = str(text or "").lstrip()
    if raw.startswith(">"):
        return "command", raw[1:].strip()
    if raw.startswith("+"):
        return "create", raw[1:].strip()
    if raw.startswith("/"):
        return "record", raw[1:].strip()
    return "default", raw.strip()


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_icon(icon_key: str):
    try:
        return _ic(icon_key)
    except Exception:
        return _ic(ICON.SEARCH)


def _status_text(raw_status: Any) -> str:
    status = _coerce_text(raw_status).replace("_", " ")
    return status.title() if status else ""


def _short_datetime(raw_value: Any, *, include_time: bool = True, all_day: bool = False) -> str:
    text = _coerce_text(raw_value)
    if not text:
        return ""
    parts = text.split()
    date_part = parts[0][:10]
    if not include_time or all_day or len(parts) < 2:
        return date_part
    time_part = parts[1][:5]
    if not time_part:
        return date_part
    return f"{date_part} {time_part}"


def _search_score(
    terms: list[str],
    *,
    title: str,
    shortcut: str = "",
    aliases: str = "",
    keywords: str = "",
    subtitle: str = "",
    group: str = "",
    entry_id: str = "",
) -> int | None:
    title_norm = _normalize(title)
    shortcut_norm = _normalize(shortcut)
    aliases_norm = _normalize(aliases)
    keywords_norm = _normalize(keywords)
    subtitle_norm = _normalize(subtitle)
    group_norm = _normalize(group)
    entry_id_norm = _normalize(entry_id)
    combined = " ".join(
        part
        for part in (
            title_norm,
            shortcut_norm,
            aliases_norm,
            keywords_norm,
            subtitle_norm,
            group_norm,
            entry_id_norm,
        )
        if part
    )
    score = 0
    for term in terms:
        if term not in combined:
            return None
        if term == title_norm:
            score += 180
        elif term in title_norm:
            score += 110
        if term == shortcut_norm:
            score += 120
        elif term and term in shortcut_norm:
            score += 80
        if term and term in aliases_norm:
            score += 65
        if term and term in keywords_norm:
            score += 55
        if term and term in group_norm:
            score += 28
        if term and term in subtitle_norm:
            score += 18
        if term and term in entry_id_norm:
            score += 12
    return score


def _directive_row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)

    data: dict[str, Any] = {}
    keys = list(getattr(row, "keys", lambda: [])())
    if keys:
        for key in keys:
            data[str(key)] = row[key]
        if "receiver_name" not in data and "requester" in data:
            data["receiver_name"] = data.get("requester")
        if "memo" not in data and "details" in data:
            data["memo"] = data.get("details")
        return data

    values = list(row or [])
    while len(values) < 7:
        values.append(None)
    return {
        "id": values[0],
        "content": values[1],
        "status": values[2],
        "receiver_name": values[3],
        "deadline": values[4],
        "memo": values[5],
        "bg_color": values[6],
    }


def _query_mentions_schedule(text: str, parsed: dict[str, Any] | None) -> bool:
    if not text or not parsed:
        return False
    normalized = _normalize(text)
    if _coerce_text(parsed.get("time")):
        return True
    if (
        _coerce_text(parsed.get("date"))
        and _coerce_text(parsed.get("date")) != date.today().isoformat()
    ):
        return True
    explicit_tokens = (
        "today",
        "tomorrow",
        "yesterday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "next",
        "am",
        "pm",
    )
    if any(token in normalized for token in explicit_tokens):
        return True
    return bool(re.search(r"\b\d{1,2}(:\d{2})?\b", normalized))


class CommandPalette(QWidget):
    execute_command = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._style_bundle = _command_palette_style_bundle(
            settings=getattr(parent, "settings", None)
        )
        self._shortcut_meta = {}
        self._commands: list[dict[str, Any]] = []
        self._result_entries: list[dict[str, Any]] = []
        self._last_query_mode = "default"
        self._last_query_text = ""

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame()
        self.container.setObjectName("palette_container")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)

        self.search_frame = QFrame()
        self.search_layout = QVBoxLayout(self.search_frame)
        self.search_layout.setContentsMargins(16, 16, 16, 16)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            t(
                "palette.placeholder",
                "Search commands, schedules, or type + to create... (>, +, /)",
            )
        )
        self.search_bar.addAction(_ic(ICON.SEARCH), QLineEdit.ActionPosition.LeadingPosition)
        self.search_layout.addWidget(self.search_bar)

        self.nlp_preview = QLabel()
        self.nlp_preview.setObjectName("palettePreview")
        self.nlp_preview.setVisible(False)
        self.search_layout.addWidget(self.nlp_preview)

        self.container_layout.addWidget(self.search_frame)

        self.divider = QFrame()
        self.divider.setObjectName("paletteDivider")
        self.divider.setFrameShape(QFrame.Shape.HLine)
        self.divider.setVisible(False)
        self.container_layout.addWidget(self.divider)

        self.result_list = QListWidget()
        self.result_list.setVisible(False)
        self.container_layout.addWidget(self.result_list)

        self.hint_bar = QFrame()
        self.hint_bar.setObjectName("paletteHintBar")
        self.hint_layout = QVBoxLayout(self.hint_bar)
        self.hint_layout.setContentsMargins(16, 8, 16, 8)
        self.hint_label = QLabel(t("palette.no_selection", "Enter opens the selected result"))
        self.hint_label.setObjectName("paletteHintLabel")
        self.hint_layout.addWidget(self.hint_label)
        self.container_layout.addWidget(self.hint_bar)

        self.root_layout.addWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(self._style_bundle["shadow_color"])
        shadow.setOffset(0, 12)
        self.container.setGraphicsEffect(shadow)

        self.search_bar.textChanged.connect(self._on_search_changed)
        self.search_bar.installEventFilter(self)
        self.result_list.itemClicked.connect(self._on_item_clicked)
        self.result_list.currentItemChanged.connect(self._on_current_item_changed)
        self.result_list.installEventFilter(self)

        self._refresh_runtime_data()
        self._apply_style()

    def _settings(self):
        return getattr(self.parent(), "settings", None)

    def _refresh_runtime_data(self):
        self._shortcut_meta = {entry["id"]: entry for entry in get_shortcut_guide_entries()}
        self._commands = self._build_command_entries()

    def _apply_style(self):
        self.setStyleSheet(_build_command_palette_stylesheet(self._style_bundle))

    def _command_entry(
        self,
        command_id: str,
        title: str,
        *,
        subtitle: str = "",
        group: str = "Command",
        icon_key: str = ICON.SEARCH,
        keywords: tuple[str, ...] | list[str] = (),
        shortcut_id: str | None = None,
        shortcut: str = "",
        params: dict[str, Any] | None = None,
        requires: str | None = None,
        extra_method_check: str | None = None,
    ) -> dict[str, Any] | None:
        app = self.parent()
        if app is None:
            return None
        required_name = requires or command_id
        if required_name and not hasattr(app, required_name):
            return None
        if extra_method_check and not hasattr(app, extra_method_check):
            return None

        help_entry = self._shortcut_meta.get(shortcut_id or "", {})
        resolved_shortcut = shortcut or (get_key(shortcut_id, "") if shortcut_id else "")
        description = subtitle or str(help_entry.get("description_ko") or "")
        aliases = list(help_entry.get("aliases", []))
        tags = list(help_entry.get("tags_ko", []))
        menu_path = str(help_entry.get("menu_path_ko") or "")
        search_keywords = [str(value).strip() for value in keywords if str(value).strip()]
        search_keywords.extend(alias for alias in aliases if alias)
        search_keywords.extend(tag for tag in tags if tag)
        return {
            "kind": "command",
            "id": command_id,
            "command_id": command_id,
            "title": title,
            "subtitle": description,
            "group": group,
            "shortcut": resolved_shortcut,
            "menu_path": menu_path,
            "aliases": aliases,
            "keywords": search_keywords,
            "params": dict(params or {}),
            "icon_key": icon_key,
        }

    def _build_command_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []

        def _add(entry: dict[str, Any] | None):
            if entry is not None:
                entries.append(entry)

        command_specs = [
            dict(
                command_id="open_task_dialog",
                title=t("menu.add_schedule", "New Schedule"),
                subtitle="Create a new schedule or calendar item",
                group="Create",
                icon_key=ICON.VIEW_CALENDAR,
                shortcut_id="new_schedule",
                keywords=("schedule", "task", "add", "new"),
            ),
            dict(
                command_id="open_routine_add_dialog",
                title=t("menu.add_routine", "New Routine"),
                subtitle="Create a recurring routine",
                group="Create",
                icon_key=ICON.ROUTINE,
                shortcut_id="new_routine",
                keywords=("routine", "recurring"),
            ),
            dict(
                command_id="open_directive_dialog",
                title=t("menu.add_directive", "New Directive"),
                subtitle="Create a directive or request item",
                group="Create",
                icon_key=ICON.DIRECTIVE,
                shortcut_id="new_directive",
                keywords=("directive", "request"),
            ),
            dict(
                command_id="open_checklist_manager",
                title=t("menu.checklist_mgmt", "Checklist Manager"),
                group="Work",
                icon_key=ICON.CHECKLIST,
                shortcut_id="checklist",
                keywords=("checklist", "template"),
            ),
            dict(
                command_id="open_work_management_dialog",
                title=t("menu.work_management", "Work Management"),
                subtitle="Open the combined work management dialog",
                group="Work",
                icon_key=ICON.ALL_SCHEDULES,
                params={"start_tab": "schedule"},
                keywords=("work", "manage"),
            ),
            dict(
                command_id="open_work_management_dialog",
                title=t("menu.routine_status", "Routine Status"),
                subtitle="Open the routine tab directly",
                group="Work",
                icon_key=ICON.ROUTINE,
                shortcut_id="routine_mgr",
                params={"start_tab": "routine"},
                keywords=("routine", "status"),
            ),
            dict(
                command_id="open_work_management_dialog",
                title=t("menu.directive_status", "Directive Status"),
                subtitle="Open the directive tab directly",
                group="Work",
                icon_key=ICON.DIRECTIVE,
                params={"start_tab": "directive"},
                keywords=("directive", "status"),
            ),
            dict(
                command_id="jump_to_today",
                title="Go To Today",
                group="Navigate",
                icon_key=ICON.STATUS_TODAY,
                shortcut_id="today",
                keywords=("today", "calendar"),
            ),
            dict(
                command_id="prev_day",
                title="Previous Date",
                group="Navigate",
                icon_key=ICON.NAV_PREV,
                shortcut_id="prev_day",
                keywords=("previous", "left"),
            ),
            dict(
                command_id="next_day",
                title="Next Date",
                group="Navigate",
                icon_key=ICON.NAV_NEXT,
                shortcut_id="next_day",
                keywords=("next", "right"),
            ),
            dict(
                command_id="toggle_focus_mode",
                title=t("menu.focus_mode", "Toggle Focus Mode"),
                group="Focus",
                icon_key=ICON.POMODORO,
                shortcut_id="focus_mode",
                keywords=("focus", "pomodoro"),
            ),
            dict(
                command_id="toggle_focus_pause",
                title="Pause Or Resume Focus",
                group="Focus",
                icon_key=ICON.POMODORO,
                shortcut_id="focus_pause",
                keywords=("pause", "resume", "focus"),
            ),
            dict(
                command_id="open_focus_log_dialog",
                title="Focus Session Log",
                group="Focus",
                icon_key=ICON.POMODORO,
                keywords=("focus", "log", "history"),
            ),
            dict(
                command_id="open_pomodoro_settings_dialog",
                title="Pomodoro Settings",
                group="Focus",
                icon_key=ICON.POMODORO,
                keywords=("pomodoro", "timer", "settings"),
            ),
            dict(
                command_id="toggle_top_bar",
                title=t("menu.hide_topbar", "Toggle Top Bar"),
                group="View",
                icon_key=ICON.SCREEN_MGMT,
                shortcut_id="topbar",
                keywords=("top bar", "menu bar"),
            ),
            dict(
                command_id="toggle_calendar_toolbar",
                title=t("menu.hide_calendar_toolbar", "Toggle Calendar Toolbar"),
                group="View",
                icon_key=ICON.TOOLBAR,
                shortcut_id="cal_toolbar",
                keywords=("calendar toolbar", "toolbar"),
            ),
            dict(
                command_id="toggle_fullscreen",
                title=t("menu.fullscreen", "Toggle Fullscreen"),
                group="View",
                icon_key=ICON.FULLSCREEN,
                shortcut_id="fullscreen",
                keywords=("fullscreen", "full screen"),
            ),
            dict(
                command_id="toggle_widget_mode_panel",
                title=t("menu.widget_mode_toggle", "Toggle Widget Mode"),
                group="Widgets",
                icon_key=ICON.WIDGET_MGR,
                shortcut_id="widget_mode",
                keywords=("widget", "panel"),
            ),
            dict(
                command_id="open_widget_manager",
                title="Widget Manager",
                group="Widgets",
                icon_key=ICON.WIDGET_MGR,
                keywords=("widget", "manager", "overlay"),
            ),
            dict(
                command_id="open_schedule_widget_panel",
                title="Open Schedule Widget Panel",
                group="Widgets",
                icon_key=ICON.VIEW_CALENDAR,
                extra_method_check="open_schedule_widget_panel",
                keywords=("schedule widget", "calendar widget"),
            ),
            dict(
                command_id="open_work_widget_panel",
                title="Open Work Widget Panel",
                group="Widgets",
                icon_key=ICON.ALL_SCHEDULES,
                extra_method_check="open_work_widget_panel",
                keywords=("work widget", "routine widget"),
            ),
            dict(
                command_id="open_all_widget_panels",
                title="Open All Widget Panels",
                group="Widgets",
                icon_key=ICON.WIDGET_MGR,
                extra_method_check="open_all_widget_panels",
                keywords=("all widgets",),
            ),
            dict(
                command_id="change_text_theme",
                title=t("palette.theme_dark", "Theme: Change to Dark Mode"),
                group="Settings",
                icon_key=ICON.COLOR_PICKER,
                params={"text_theme": "dark"},
                requires="change_text_theme",
                keywords=("theme", "dark", "appearance"),
            ),
            dict(
                command_id="change_text_theme",
                title=t("palette.theme_light", "Theme: Change to Light Mode"),
                group="Settings",
                icon_key=ICON.COLOR_PICKER,
                params={"text_theme": "light"},
                requires="change_text_theme",
                keywords=("theme", "light", "appearance"),
            ),
            dict(
                command_id="set_system_default_theme",
                title="Theme: Use System Default",
                group="Settings",
                icon_key=ICON.COLOR_PICKER,
                keywords=("theme", "system", "auto"),
            ),
            dict(
                command_id="open_panel_background_color_dialog",
                title=t("menu.ui_theme_open", "Open UI Theme Details"),
                group="Settings",
                icon_key=ICON.COLOR_PICKER,
                keywords=("theme", "ui", "color", "background"),
            ),
            dict(
                command_id="open_label_settings_dialog",
                title=t("menu.label_settings", "Label Settings"),
                group="Settings",
                icon_key=ICON.COLOR_PICKER,
                keywords=("label", "tag", "settings"),
            ),
            dict(
                command_id="open_away_settings_dialog",
                title=t("menu.away_settings", "Away Lock Settings"),
                group="Settings",
                icon_key=ICON.BREAK_LONG,
                keywords=("away", "idle", "lock"),
            ),
            dict(
                command_id="open_font_settings_dialog",
                title="Font Settings",
                group="Settings",
                icon_key=ICON.FONT,
                keywords=("font", "text", "settings"),
            ),
            dict(
                command_id="sync_google_calendar",
                title=t("palette.sync_google", "Sync: Update Google Calendar now"),
                group="Sync",
                icon_key=ICON.GCAL,
                keywords=("google", "calendar", "sync"),
            ),
            dict(
                command_id="open_gcal_settings_dialog",
                title=t("menu.sync_account", "Calendar Sync Settings"),
                group="Sync",
                icon_key=ICON.SYNC_SETTINGS,
                keywords=("google", "calendar", "sync", "settings"),
            ),
            dict(
                command_id="open_gcal_sync_issues_dialog",
                title=t("menu.sync_issues", "Sync Issues"),
                group="Sync",
                icon_key=ICON.WARNING,
                keywords=("sync", "issues", "error"),
            ),
        ]
        for spec in command_specs:
            _add(self._command_entry(**spec))

        _add(
            self._command_entry(
                "save_layout_preset",
                t("menu.save_layout", "Save Current Layout"),
                group="View",
                icon_key=ICON.SAVE,
                shortcut_id="save_layout",
                requires="preset_manager",
                keywords=("layout", "preset", "save"),
            )
        )
        for index in range(5):
            _add(
                self._command_entry(
                    "apply_layout_preset",
                    f"Apply Layout Preset {index + 1}",
                    group="View",
                    icon_key=ICON.DISPLAY_STYLE,
                    shortcut_id=f"layout_{index + 1}",
                    params={"index": index},
                    requires="apply_layout_preset",
                    keywords=("layout", "preset", f"{index + 1}"),
                )
            )

        trailing_specs = [
            dict(
                command_id="toggle_lock_mode",
                title="Toggle Desktop Lock",
                group="Window",
                icon_key=ICON.LOCK,
                shortcut_id="lock_mode",
                requires="toggle_lock_mode",
                keywords=("lock", "desktop"),
            ),
            dict(
                command_id="toggle_magnet_mode",
                title="Toggle Magnet Mode",
                group="Window",
                icon_key=ICON.MAGNET,
                shortcut_id="magnet_mode",
                keywords=("magnet", "dock", "snap"),
            ),
            dict(
                command_id="toggle_idle_lock_manual",
                title=t("menu.instant_away", "Start Away Lock"),
                group="Window",
                icon_key=ICON.LOCK,
                shortcut_id="away_lock",
                requires="toggle_idle_lock",
                keywords=("away", "idle", "lock"),
            ),
            dict(
                command_id="restore_window_to_safe_area",
                title="Restore Window Position",
                group="Window",
                icon_key=ICON.RESET_POS,
                shortcut_id="restore_pos",
                keywords=("restore", "window", "position"),
            ),
            dict(
                command_id="move_to_next_monitor",
                title="Move To Next Monitor",
                group="Window",
                icon_key=ICON.NEXT_MONITOR,
                shortcut_id="monitor_right",
                keywords=("monitor", "display", "screen"),
            ),
            dict(
                command_id="toggle_autostart",
                title=t("menu.autostart", "Toggle Auto Start"),
                group="System",
                icon_key=ICON.SETTINGS,
                keywords=("autostart", "startup"),
            ),
            dict(
                command_id="open_language_settings_dialog",
                title=t("menu.language", "Language Settings"),
                group="System",
                icon_key=ICON.LOCALE_MGMT,
                keywords=("language", "locale"),
            ),
            dict(
                command_id="show_shortcut_guide",
                title=t("menu.shortcuts", "Shortcut Guide"),
                group="System",
                icon_key=ICON.TIP,
                shortcut_id="help",
                keywords=("shortcut", "help", "guide"),
            ),
            dict(
                command_id="request_app_exit",
                title=t("palette.exit_app", "App: Exit"),
                group="System",
                icon_key=ICON.CLOSE,
                keywords=("exit", "quit", "close"),
            ),
        ]
        for spec in trailing_specs:
            _add(self._command_entry(**spec))

        return entries

    def _load_recent_command_ids(self) -> list[str]:
        settings = self._settings()
        if settings is None:
            return []
        raw = settings.value(_RECENT_COMMANDS_KEY, "")
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        text = _coerce_text(raw)
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]

    def _remember_recent_command(self, command_id: str) -> None:
        settings = self._settings()
        if settings is None or not command_id:
            return
        items = [value for value in self._load_recent_command_ids() if value != command_id]
        items.insert(0, command_id)
        settings.setValue(_RECENT_COMMANDS_KEY, json.dumps(items[:8], ensure_ascii=True))

    def _build_default_results(self) -> list[dict[str, Any]]:
        commands_by_id = {entry["id"]: entry for entry in self._commands}
        ordered: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for command_id in self._load_recent_command_ids():
            entry = commands_by_id.get(command_id)
            if not entry:
                continue
            key = (entry["kind"], entry["id"])
            if key in seen:
                continue
            recent_entry = dict(entry)
            if recent_entry.get("subtitle"):
                recent_entry["subtitle"] = f"Recent - {recent_entry['subtitle']}"
            else:
                recent_entry["subtitle"] = "Recent"
            ordered.append(recent_entry)
            seen.add(key)

        for command_id in _DEFAULT_COMMAND_IDS:
            entry = commands_by_id.get(command_id)
            if not entry:
                continue
            key = (entry["kind"], entry["id"])
            if key in seen:
                continue
            ordered.append(entry)
            seen.add(key)

        if not ordered:
            ordered.extend(self._commands[: min(len(self._commands), _RESULT_LIMIT)])
        return ordered[:_RESULT_LIMIT]

    def _search_command_entries(self, query: str) -> list[dict[str, Any]]:
        if not query:
            return self._build_default_results()

        recent_ids = set(self._load_recent_command_ids())
        terms = _split_terms(query)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for entry in self._commands:
            score = _search_score(
                terms,
                title=entry["title"],
                shortcut=entry.get("shortcut", ""),
                aliases=" ".join(entry.get("aliases", [])),
                keywords=" ".join(entry.get("keywords", [])),
                subtitle=" ".join(
                    part for part in (entry.get("subtitle", ""), entry.get("menu_path", "")) if part
                ),
                group=entry.get("group", ""),
                entry_id=entry.get("id", ""),
            )
            if score is None:
                continue
            if entry["id"] in recent_ids:
                score += 12
            ranked.append((score, entry))

        ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
        return [entry for _, entry in ranked[:_RESULT_LIMIT]]

    def _task_record_entry(self, row: dict[str, Any], score: int) -> dict[str, Any]:
        record_type = _coerce_text(row.get("type") or "schedule") or "schedule"
        title = _coerce_text(row.get("name")) or t("panel.common.no_title", "(No Title)")
        when_text = _short_datetime(
            row.get("deadline") or row.get("target_date"),
            include_time=True,
            all_day=bool(row.get("all_day")),
        )
        type_label = "Routine" if record_type == "routine" else "Schedule"
        subtitle_parts = [type_label]
        if when_text:
            subtitle_parts.append(when_text)
        status_text = _status_text(row.get("status"))
        if status_text:
            subtitle_parts.append(status_text)
        jump_date = _coerce_text(row.get("target_date")) or _coerce_text(row.get("deadline"))[:10]
        return {
            "kind": "record",
            "record_kind": "task",
            "record_type": record_type,
            "id": f"task:{row.get('id')}",
            "command_id": "open_task_record",
            "title": title,
            "subtitle": " - ".join(part for part in subtitle_parts if part),
            "group": type_label,
            "shortcut": "",
            "keywords": [
                record_type,
                _coerce_text(row.get("priority")),
                _coerce_text(row.get("status")),
                _coerce_text(row.get("location")),
                _coerce_text(row.get("assignee")),
                _coerce_text(row.get("memo")),
                _coerce_text(row.get("description")),
            ],
            "aliases": [],
            "params": {
                "task_id": int(row.get("id")),
                "record_type": record_type,
                "jump_date": jump_date,
            },
            "icon_key": ICON.ROUTINE if record_type == "routine" else ICON.VIEW_CALENDAR,
            "score": score,
        }

    def _directive_record_entry(self, row: dict[str, Any], score: int) -> dict[str, Any]:
        title = _coerce_text(row.get("content")) or t("panel.common.no_title", "(No Title)")
        when_text = _short_datetime(row.get("deadline"), include_time=True)
        subtitle_parts = ["Directive"]
        receiver = _coerce_text(row.get("receiver_name"))
        if receiver:
            subtitle_parts.append(receiver)
        if when_text:
            subtitle_parts.append(when_text)
        status_text = _status_text(row.get("status"))
        if status_text:
            subtitle_parts.append(status_text)
        jump_date = _coerce_text(row.get("deadline"))[:10]
        return {
            "kind": "record",
            "record_kind": "directive",
            "record_type": "directive",
            "id": f"directive:{row.get('id')}",
            "command_id": "open_directive_record",
            "title": title,
            "subtitle": " - ".join(part for part in subtitle_parts if part),
            "group": "Directive",
            "shortcut": "",
            "keywords": [
                _coerce_text(row.get("receiver_name")),
                _coerce_text(row.get("memo")),
                _coerce_text(row.get("priority")),
                _coerce_text(row.get("status")),
            ],
            "aliases": [],
            "params": {
                "directive_id": int(row.get("id")),
                "jump_date": jump_date,
            },
            "icon_key": ICON.DIRECTIVE,
            "score": score,
        }

    def _search_task_records(self, query: str) -> list[dict[str, Any]]:
        terms = _split_terms(query)
        if not terms:
            return []

        rows_by_id: dict[int, dict[str, Any]] = {}
        for term in terms:
            try:
                rows = search_repo.search_unified_tasks(term)
            except Exception:
                rows = []
            for row in rows or []:
                rows_by_id[int(row.get("id"))] = dict(row)

        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows_by_id.values():
            title = _coerce_text(row.get("name"))
            subtitle = " ".join(
                value
                for value in (
                    _coerce_text(row.get("deadline")),
                    _coerce_text(row.get("target_date")),
                    _coerce_text(row.get("location")),
                    _coerce_text(row.get("assignee")),
                    _coerce_text(row.get("memo")),
                    _coerce_text(row.get("description")),
                    _coerce_text(row.get("type")),
                    _coerce_text(row.get("priority")),
                    _coerce_text(row.get("status")),
                )
                if value
            )
            score = _search_score(
                terms,
                title=title,
                keywords=subtitle,
                subtitle=subtitle,
                group=_coerce_text(row.get("type")),
                entry_id=f"task:{row.get('id')}",
            )
            if score is None:
                continue
            if row.get("type") == "schedule":
                score += 6
            if _coerce_text(row.get("status")) not in {"completed", "canceled"}:
                score += 4
            ranked.append((score, row))

        ranked.sort(key=lambda item: (-item[0], _coerce_text(item[1].get("deadline")) or "9999"))
        return [self._task_record_entry(row, score) for score, row in ranked[:_RESULT_LIMIT]]

    def _search_directive_records(self, query: str) -> list[dict[str, Any]]:
        terms = _split_terms(query)
        if not terms:
            return []

        try:
            rows = directive_repo.get_recent_directives(limit=400)
        except Exception:
            rows = []

        ranked: list[tuple[int, dict[str, Any]]] = []
        for raw_row in rows or []:
            row = _directive_row_to_dict(raw_row)
            title = _coerce_text(row.get("content"))
            subtitle = " ".join(
                value
                for value in (
                    _coerce_text(row.get("receiver_name")),
                    _coerce_text(row.get("deadline")),
                    _coerce_text(row.get("memo")),
                    _coerce_text(row.get("priority")),
                    _coerce_text(row.get("status")),
                )
                if value
            )
            score = _search_score(
                terms,
                title=title,
                keywords=subtitle,
                subtitle=subtitle,
                group="directive",
                entry_id=f"directive:{row.get('id')}",
            )
            if score is None:
                continue
            if _coerce_text(row.get("status")) not in {"completed", "done", "canceled"}:
                score += 4
            ranked.append((score, row))

        ranked.sort(key=lambda item: (-item[0], _coerce_text(item[1].get("deadline")) or "9999"))
        return [self._directive_record_entry(row, score) for score, row in ranked[:_RESULT_LIMIT]]

    def _search_record_entries(self, query: str) -> list[dict[str, Any]]:
        entries = self._search_task_records(query) + self._search_directive_records(query)
        entries.sort(key=lambda entry: (-int(entry.get("score", 0)), entry["title"]))
        return entries[:_RESULT_LIMIT]

    def _build_create_entries(
        self,
        query: str,
        mode: str,
        has_other_results: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        text = _coerce_text(query)
        if len(text) < 2:
            return [], None

        try:
            parsed = parse_nlp_task(text)
        except Exception:
            return [], None

        if not parsed:
            return [], None

        has_signal = _query_mentions_schedule(text, parsed)
        if mode != "create" and not has_signal and has_other_results:
            return [], None

        time_text = _coerce_text(parsed.get("time"))
        if time_text and len(time_text) == 5:
            time_text = f"{time_text}:00"

        title = _coerce_text(parsed.get("title")) or t("dialog.task.untitled", "Untitled")
        preview_time = time_text[:5] if time_text else "09:00 default"
        preview_text = t(
            "palette.nlp_preview",
            "New: [{title}] - {date} {time}",
        ).format(
            title=title,
            date=_coerce_text(parsed.get("date")),
            time=preview_time,
        )
        entry = {
            "kind": "create",
            "id": "create_task_nlp",
            "command_id": "create_task_nlp",
            "title": f"Create Schedule: {title}",
            "subtitle": preview_text,
            "group": "Create",
            "shortcut": "",
            "keywords": ["create", "schedule", "quick add"],
            "aliases": [],
            "params": {
                "title": title,
                "date": _coerce_text(parsed.get("date")),
                "time": time_text,
            },
            "icon_key": ICON.ADD,
        }
        return [entry], entry

    def _combine_results(
        self, mode: str, query: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        command_entries = (
            self._search_command_entries(query) if mode in {"default", "command"} else []
        )
        record_entries = self._search_record_entries(query) if mode in {"default", "record"} else []
        create_entries, preview_entry = self._build_create_entries(
            query,
            mode,
            has_other_results=bool(command_entries or record_entries),
        )

        if mode == "command":
            return command_entries[:_RESULT_LIMIT], None
        if mode == "record":
            return record_entries[:_RESULT_LIMIT], None
        if mode == "create":
            extras = []
            for command_id in (
                "open_task_dialog",
                "open_routine_add_dialog",
                "open_directive_dialog",
            ):
                extras.extend(entry for entry in self._commands if entry["id"] == command_id)
            return (create_entries + extras)[:_RESULT_LIMIT], preview_entry

        results: list[dict[str, Any]] = []
        if create_entries:
            results.extend(create_entries)

        combined_search_entries = [(0, entry) for entry in command_entries] + [
            (1, entry) for entry in record_entries
        ]
        combined_search_entries.sort(
            key=lambda item: (
                -int(item[1].get("score", 999999 if item[1]["kind"] == "command" else 0)),
                item[0],
                item[1]["title"],
            )
        )

        seen: set[tuple[str, str]] = set()
        for _, entry in combined_search_entries:
            key = (entry["kind"], entry["id"])
            if key in seen:
                continue
            seen.add(key)
            results.append(entry)
            if len(results) >= _RESULT_LIMIT:
                break

        return results[:_RESULT_LIMIT], preview_entry

    def _render_results(self, entries: list[dict[str, Any]]):
        self._result_entries = entries
        self.result_list.clear()

        if not entries:
            self.result_list.setVisible(False)
            self.divider.setVisible(False)
            self.setFixedHeight(_EMPTY_HEIGHT if not self.nlp_preview.isVisible() else 154)
            self._update_hint_label(None)
            return

        for entry in entries:
            subtitle = _coerce_text(entry.get("subtitle"))
            shortcut = _coerce_text(entry.get("shortcut"))
            if shortcut:
                subtitle = f"{subtitle} [{shortcut}]" if subtitle else f"[{shortcut}]"
            item = QListWidgetItem(entry["title"] + (f"\n{subtitle}" if subtitle else ""))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(subtitle)
            item.setSizeHint(QSize(0, _ITEM_HEIGHT))
            item.setIcon(_safe_icon(entry.get("icon_key", ICON.SEARCH)))
            self.result_list.addItem(item)

        self.result_list.setVisible(True)
        self.divider.setVisible(True)
        self.result_list.setCurrentRow(0)
        visible_count = min(self.result_list.count(), _RESULT_LIMIT)
        extra_preview_height = 20 if self.nlp_preview.isVisible() else 0
        self.setFixedHeight(min(560, 116 + extra_preview_height + visible_count * _ITEM_HEIGHT))
        self._update_hint_label(self._selected_entry())

    def _selected_entry(self) -> dict[str, Any] | None:
        item = self.result_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _update_hint_label(self, entry: dict[str, Any] | None):
        if entry is None:
            mode_hint = {
                "command": t("palette.hint_command", "명령어를 검색하세요"),
                "create": t("palette.hint_create", "Enter로 일정을 만듭니다"),
                "record": t("palette.hint_record", "일정·루틴·디렉티브를 검색하세요"),
            }.get(self._last_query_mode, t("palette.hint_default", "> 명령어  + 만들기  / 검색"))
            self.hint_label.setText(mode_hint)
            return
        if entry["kind"] == "record" and _coerce_text(entry.get("params", {}).get("jump_date")):
            self.hint_label.setText(
                t("palette.hint_record_jump", "Enter로 항목 열기. Shift+Enter로 날짜 이동.")
            )
            return
        if entry["kind"] == "create":
            self.hint_label.setText(t("palette.hint_create_confirm", "Enter로 일정을 만듭니다"))
            return
        self.hint_label.setText(t("palette.hint_run_command", "Enter로 명령어를 실행합니다"))

    def _move_selection(self, delta: int) -> None:
        if self.result_list.count() <= 0:
            return
        current = self.result_list.currentRow()
        if current < 0:
            current = 0
        self.result_list.setCurrentRow(max(0, min(self.result_list.count() - 1, current + delta)))

    def _dispatch_entry(self, entry: dict[str, Any], *, alternate: bool = False) -> None:
        if alternate and entry["kind"] == "record":
            jump_date = _coerce_text(entry.get("params", {}).get("jump_date"))
            if jump_date:
                self.execute_command.emit("jump_to_date", {"date": jump_date})
                self._close_with_animation()
                return

        self.execute_command.emit(entry["command_id"], dict(entry.get("params") or {}))
        if entry["kind"] == "command":
            self._remember_recent_command(entry["id"])
        self._close_with_animation()

    def _execute_current_selection(self, *, alternate: bool = False) -> bool:
        entry = self._selected_entry()
        if entry is None:
            return False
        self._dispatch_entry(entry, alternate=alternate)
        return True

    def _on_current_item_changed(self, current, _previous):
        if current is None:
            self._update_hint_label(None)
            return
        entry = current.data(Qt.ItemDataRole.UserRole)
        self._update_hint_label(entry if isinstance(entry, dict) else None)

    def _on_item_clicked(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict):
            self._dispatch_entry(entry)

    def _on_search_changed(self, text):
        self._last_query_mode, self._last_query_text = _parse_query_mode(text)

        results, preview_entry = self._combine_results(self._last_query_mode, self._last_query_text)
        if preview_entry:
            self.nlp_preview.setText(preview_entry["subtitle"])
            self.nlp_preview.setVisible(True)
        else:
            self.nlp_preview.setVisible(False)

        self._render_results(results)

    def _handle_key_press(self, event: QKeyEvent) -> bool:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._close_with_animation()
            return True
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._move_selection(1)
            return True
        if key == Qt.Key.Key_Up:
            self._move_selection(-1)
            return True
        return key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._execute_current_selection(
            alternate=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        )

    def eventFilter(self, watched, event):
        if (
            watched in (self.search_bar, self.result_list)
            and event.type() == QEvent.Type.KeyPress
            and self._handle_key_press(event)
        ):
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent):
        if self._handle_key_press(event):
            return
        super().keyPressEvent(event)

    def show_at_center(self, parent_rect):
        self._style_bundle = _command_palette_style_bundle(
            settings=getattr(self.parent(), "settings", None)
        )
        self._refresh_runtime_data()
        self._apply_style()
        self.search_bar.clear()
        self.nlp_preview.hide()
        self.result_list.hide()
        self._render_results(self._build_default_results())

        width = 680
        self.setFixedSize(width, max(_EMPTY_HEIGHT, self.height()))
        x = parent_rect.x() + (parent_rect.width() - width) // 2
        y = parent_rect.y() + 150

        self.setWindowOpacity(0.0)
        self.move(x, y - 24)
        self.show()
        self.raise_()
        self.search_bar.setFocus()

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(280)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(280)
        self.pos_anim.setStartValue(QPoint(x, y - 24))
        self.pos_anim.setEndValue(QPoint(x, y))
        self.pos_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self.anim.start()
        self.pos_anim.start()

    def _close_with_animation(self):
        if not self.isVisible():
            self.hide()
            return
        self.anim_close = QPropertyAnimation(self, b"windowOpacity")
        self.anim_close.setDuration(180)
        self.anim_close.setStartValue(self.windowOpacity())
        self.anim_close.setEndValue(0.0)
        self.anim_close.finished.connect(self.hide)
        self.anim_close.start()
