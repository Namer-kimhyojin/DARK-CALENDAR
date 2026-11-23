# -*- coding: utf-8 -*-
"""Transactional widget preferences with a real, isolated widget preview."""

from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_free_layout import (
    FREE_LAYOUT_MODE_KEY,
    read_free_layout,
    write_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    SELECTED_LAYOUT_PRESET_KEY,
    USER_LAYOUT_PRESETS_KEY,
    delete_layout_preset,
    get_layout_preset,
    read_layout_presets,
    rename_layout_preset,
    write_layout_presets,
)
from calendar_app.presentation.widgets.widget_mode_density import (
    DENSITIES,
    DENSITY_KEY,
    read_widget_density,
)
from calendar_app.presentation.widgets.widget_mode_display import (
    CALENDAR_STYLE_PREFIX,
    SEARCH_PINNED_PREFIX,
    SHOW_OVERVIEW_PREFIX,
    display_key,
    read_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_migration import (
    remember_handled_free_layouts,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    read_widget_mode_layout_id,
    widget_mode_layouts,
)
from calendar_app.presentation.widgets.widget_mode_surfaces import (
    SURFACE_SETTING_KEY,
    read_widget_mode_surface,
    widget_mode_surfaces,
)
from calendar_app.presentation.widgets.widget_mode_theme import (
    main_widget_mode_tokens,
)
from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography
from calendar_app.presentation.widgets.widget_mode_visibility import (
    read_widget_calendar_visibility,
    write_widget_calendar_visibility,
)
from calendar_app.presentation.widgets.widget_saved_layouts import (
    SAVED_SETUPS_KEY,
    SELECTED_SETUP_KEY,
    add_setup,
    capture_setup,
    delete_setup,
    find_setup,
    read_saved_setups,
    rename_setup,
    write_saved_setups,
    write_setup_options,
)
from calendar_app.shared.color_utils import composite_color, parse_css_color
from calendar_app.shared.qt_helpers import mnemonic_safe


class _DraftSettings:
    def __init__(self, settings):
        self.source = settings
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, self.source.value(key, default))
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value


class _WrappedTextPage(QWidget):
    """A scroll page whose minimum height follows its word-wrapped labels.

    QTabWidget does not forward height-for-width, so a short dialog sized the
    page from the labels' one-line hints. The box layout then shrank every row
    proportionally and the layout cards painted over each other.
    """

    def _refresh_minimum_height(self, width: int) -> None:
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth() and width > 0:
            needed = layout.totalHeightForWidth(width)
            if needed > 0 and needed != self.minimumHeight():
                self.setMinimumHeight(needed)

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._refresh_minimum_height(event.size().width())

    def event(self, event):
        # Rows are added or revealed (e.g. the saved-layout list) without a resize.
        if event.type() == QEvent.Type.LayoutRequest:
            self._refresh_minimum_height(self.width())
        return super().event(event)


class WidgetCustomizationDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.draft = _DraftSettings(controller.main_window.settings)
        self.draft.setValue("widget_mode_layout", read_widget_mode_layout_id(self.draft))
        self.draft.setValue(SURFACE_SETTING_KEY, read_widget_mode_surface(self.draft))
        self._building = True
        self._layout_changed = False
        self._custom_layout_changed = False
        self.setWindowTitle(t("widget_mode.customize", "꾸미기"))
        self.resize(940, 680)
        apply_common_dialog_style(self)
        root = QVBoxLayout(self)
        intro = QLabel(
            t(
                "widget_mode.customization_intro",
                "배치·모양·표시 항목을 바꾸고 예시 일정에서 확인하세요. "
                "적용하기 전까지 현재 위젯은 바뀌지 않습니다.",
            )
            + " "
            + t(
                "widget_mode.main_theme_note",
                "색과 투명도는 앱의 모양 설정을 따르고, 표면 모양은 모서리와 항목 테두리만 바꿉니다.",
            ),
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        controls = self.controls_scroll = QScrollArea(self)
        controls.setWidgetResizable(True)
        controls.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls.setMinimumWidth(410)
        tabs = self.preferences_tabs = QTabWidget(self)
        tabs.setMinimumWidth(0)
        tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        tabs.tabBar().setUsesScrollButtons(True)
        controls.setWidget(tabs)
        body.addWidget(controls, 1)
        tabs.addTab(self._layout_tab(), t("widget_mode.tab_layout", "배치"))
        tabs.addTab(
            self._appearance_tab(),
            mnemonic_safe(t("widget_workspace.preferences_style", "모양")),
        )
        tabs.addTab(self._visibility_tab(), t("widget_mode.preferences_visibility", "표시 항목"))
        from calendar_app.presentation.widgets.widget_mode_skins import (
            LAYOUT_SELECTION_ENABLED,
        )

        if not LAYOUT_SELECTION_ENABLED:
            # Built (its controls keep the draft consistent) but not offered.
            tabs.setTabVisible(0, False)
            tabs.setCurrentIndex(1)
        tabs.currentChanged.connect(self._scroll_active_surface)

        self.preview_frame = QWidget(self)
        preview_column = QVBoxLayout(self.preview_frame)
        body.addWidget(self.preview_frame, 1)
        preview_column.addWidget(QLabel(t("widget_mode.preview", "미리보기 · 예시 일정"), self))
        self.preview_label = QLabel(self)
        self.preview_label.installEventFilter(self)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_label.setMinimumSize(280, 350)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setAccessibleName(t("widget_mode.preview", "미리보기 · 예시 일정"))
        preview_column.addWidget(self.preview_label, 1)
        note = QLabel(
            t("widget_mode.preview_note", "적용하면 저장됩니다. 취소하면 기존 설정을 유지합니다."),
            self,
        )
        note.setWordWrap(True)
        preview_column.addWidget(note)
        footer, apply_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.apply", "적용"),
            cancel_label=t("common.cancel", "취소"),
        )
        root.addLayout(footer)
        self.apply_btn = apply_btn
        self.cancel_btn = cancel_btn
        self._wheel_controls = []
        for control in (
            self.surface_combo,
            self.font_family,
            self.font_size,
            self.font_weight,
            self.calendar_style_combo,
            self.density_combo,
            self.clock_format_combo,
            self.clock_size_combo,
        ):
            control.installEventFilter(self)
            self._wheel_controls.append(control)
            if isinstance(control, (QComboBox, QSpinBox)) and control.lineEdit() is not None:
                control.lineEdit().installEventFilter(self)
                self._wheel_controls.append(control.lineEdit())
        apply_btn.clicked.connect(self._apply)
        cancel_btn.clicked.connect(self.reject)
        self._build_preview()
        self._building = False
        self._refresh_preview()
        if self.draft.value(SELECTED_LAYOUT_PRESET_KEY, ""):
            QTimer.singleShot(0, self._show_user_layouts)
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            if available.width() < 760:
                body.removeWidget(self.preview_frame)
                tabs.addTab(self.preview_frame, t("widget_mode.preview", "미리보기 · 예시 일정"))
                tabs.tabBar().setUsesScrollButtons(True)
                tabs.currentChanged.connect(self._refresh_preview)
                controls.setMinimumWidth(280)
                self.preview_label.setMinimumSize(220, 220)
            if available.height() < 640:
                self.preview_label.setMinimumHeight(220)
            self.resize(min(940, available.width() - 40), min(680, available.height() - 40))

    @staticmethod
    def _layout_purpose(layout_id):
        return {
            "stacked": t("widget_mode.layout_purpose_stacked", "달력 위 · 목록 아래"),
            "dashboard": t("widget_mode.layout_purpose_dashboard", "달력 왼쪽 · 목록 오른쪽"),
            "work_board": t("widget_mode.layout_purpose_work_board", "일정·업무를 열로 나눔"),
            "minimal": t("widget_mode.layout_purpose_minimal", "목록만 · 가장 작게"),
        }.get(layout_id, "")

    def _layout_tab(self):
        """배치 tab: pick a layout, set that layout's options, save it as 내 배치.

        Hovering a card previews it; clicking selects it. The options right
        under the cards always belong to the selected layout.
        """
        tab = _WrappedTextPage(self)
        layout = QVBoxLayout(tab)
        self.layout_group = QButtonGroup(self)
        self.layout_buttons = {}
        self._hover_restore = None
        current = read_widget_mode_layout_id(self.draft)
        custom_id = str(self.draft.value(SELECTED_LAYOUT_PRESET_KEY, "") or "")
        layout.addWidget(self._section_title(t("widget_mode.preset_builtin", "기본 배치"), tab))
        for index, spec in enumerate(widget_mode_layouts()):
            if spec.layout_id.startswith("user_layout_"):
                continue
            button = QToolButton(tab)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            label = t(spec.label_key, spec.label_default)
            purpose = self._layout_purpose(spec.layout_id)
            button.setText(mnemonic_safe(label) + (f"\n{purpose}" if purpose else ""))
            button.setAccessibleName(label)
            button.setAccessibleDescription(purpose)
            button.setToolTip(
                t(
                    "widget_mode.layout_card_tip", "{name} — {purpose}. 위젯 창에서 Ctrl+{number}"
                ).format(name=label, purpose=purpose, number=index + 1)
            )
            button.setIcon(self._layout_icon(spec))
            button.setIconSize(QSize(90, 42))
            button.setCheckable(True)
            button.ensurePolished()
            text_width = max(
                button.fontMetrics().horizontalAdvance(line) for line in button.text().split("\n")
            )
            minimum_width = max(160, text_width + 28)
            lines = button.text().count("\n") + 1
            minimum_height = max(76, button.fontMetrics().height() * lines + 54)
            # The dialog stylesheet caps every QToolButton at 32px; measure the
            # icon+label card once with that cap lifted, then pin min and max
            # to the same content height. A max below the size hint made grid
            # rows shorter than the painted cards, which overlapped in short dialogs.
            button.setStyleSheet(
                self._layout_card_style(minimum_width, minimum_height, max_height=4096)
            )
            button.ensurePolished()
            frame_extra = max(0, button.minimumHeight() - minimum_height)
            card_height = max(minimum_height, button.sizeHint().height() - frame_extra)
            button.setStyleSheet(self._layout_card_style(minimum_width, card_height))
            button.setChecked(spec.layout_id == current and not custom_id)
            button.clicked.connect(
                lambda _checked=False, key=spec.layout_id: self._pick_layout_card(key)
            )
            button.setProperty("layoutId", spec.layout_id)
            button.installEventFilter(self)
            self.layout_group.addButton(button)
            self.layout_buttons[spec.layout_id] = button
        cards = self._layout_card_grid = QGridLayout()
        layout.addLayout(cards)
        self._reflow_layout_cards()

        layout.addSpacing(8)
        self._build_display_group(tab, layout)

        layout.addSpacing(8)
        layout.addWidget(self._section_title(t("widget_mode.user_layouts", "내 배치"), tab))
        self.user_layout_list = QListWidget(tab)
        self.user_layout_list.setAccessibleName(t("widget_mode.preset_select", "저장한 배치 선택"))
        self.user_layout_list.setIconSize(QSize(72, 48))
        self.user_layout_list.setMinimumHeight(120)
        self.user_layout_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.user_layout_list.currentItemChanged.connect(self._select_user_layout)
        layout.addWidget(self.user_layout_list)
        self.user_layout_empty = QLabel(
            t(
                "widget_mode.user_layouts_empty_hint",
                "자주 쓰는 배치와 옵션을 이름을 붙여 저장하면 위젯 창에서 Ctrl+5~9로 바로 바꿀 수 있습니다.",
            ),
            tab,
        )
        self.user_layout_empty.setWordWrap(True)
        layout.addWidget(self.user_layout_empty)
        actions = QHBoxLayout()
        for attribute, key, text, callback, name in (
            (
                "preset_save_btn",
                "preset_save",
                "현재 설정 저장…",
                self._save_current_setup,
                "ghost_btn",
            ),
            (
                "preset_rename_btn",
                "preset_rename",
                "이름 변경…",
                self._rename_user_layout,
                "ghost_btn",
            ),
            ("preset_delete_btn", "preset_delete", "삭제", self._delete_user_layout, "danger_btn"),
        ):
            button = QPushButton(t(f"widget_mode.{key}", text), tab)
            button.setObjectName(name)
            button.clicked.connect(lambda _checked=False, action=callback: action())
            setattr(self, attribute, button)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._reload_user_layouts()
        layout.addStretch(1)
        return tab

    def _section_title(self, text, parent):
        label = QLabel(text, parent)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _pick_layout_card(self, layout_id):
        # A click ends any hover preview: keep what was clicked.
        self._hover_restore = None
        self._change("widget_mode_layout", layout_id)

    def _preview_hovered_layout(self, layout_id):
        if self._building or getattr(self, "_rendering", False):
            return
        if self._hover_restore is None:
            self._hover_restore = (
                self.draft.value("widget_mode_layout", None),
                self.draft.value(FREE_LAYOUT_MODE_KEY, None),
            )
        self.draft.values["widget_mode_layout"] = layout_id
        self.draft.values[FREE_LAYOUT_MODE_KEY] = "preset"
        self._refresh_preview()

    def _end_layout_hover(self):
        restore = self._hover_restore
        if restore is None:
            return
        self._hover_restore = None
        for key, value in zip(("widget_mode_layout", FREE_LAYOUT_MODE_KEY), restore, strict=True):
            if value is None:
                self.draft.values.pop(key, None)
            else:
                self.draft.values[key] = value
        self._refresh_preview()

    def _user_layout_icon(self, data):
        tokens = main_widget_mode_tokens(self.draft)
        pixmap = QPixmap(72, 48)
        pixmap.fill(QColor(tokens["_main_base_color"]))
        painter = QPainter(pixmap)
        width, height = data["canvas"]
        for block in data["blocks"]:
            if block["enabled"]:
                x, y, w, h = block["rect"]
                painter.fillRect(
                    3 + round(x * 66 / width),
                    3 + round(y * 42 / height),
                    max(2, round(w * 66 / width)),
                    max(2, round(h * 42 / height)),
                    parse_css_color(
                        tokens["accent"] if block["id"] == "agenda" else tokens["text_muted"]
                    ),
                )
        painter.end()
        return QIcon(pixmap)

    def _reload_user_layouts(self):
        """내 배치: saved setups first, then older free-layout presets."""
        selected_setup = str(self.draft.value(SELECTED_SETUP_KEY, "") or "")
        selected = str(self.draft.value(SELECTED_LAYOUT_PRESET_KEY, "") or "")
        setups = read_saved_setups(self.draft)
        library = read_layout_presets(self.draft)
        builtin_count = len(self.layout_buttons)
        self.user_layout_list.blockSignals(True)
        self.user_layout_list.clear()
        for index, setup in enumerate(setups):
            spec = get_widget_mode_layout(setup["layout_id"])
            style = (
                t("widget_mode.month_toggle", "월간")
                if setup["calendar_style"] == "month"
                else t("widget_mode.week_toggle", "주간")
            )
            detail = t(spec.label_key, spec.label_default)
            if setup["layout_id"] != "minimal":
                detail += f" · {style}"
            number = builtin_count + index + 1
            if number <= 9:
                detail += f" · Ctrl+{number}"
            item = QListWidgetItem(self._layout_icon(spec), f"{setup['name']}\n{detail}")
            item.setData(Qt.ItemDataRole.UserRole, setup["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, "setup")
            item.setToolTip(setup["name"])
            self.user_layout_list.addItem(item)
            if setup["id"] == selected_setup and not self._free_active():
                self.user_layout_list.setCurrentItem(item)
        for preset in library:
            width, height = preset["layout"]["canvas"]
            item = QListWidgetItem(
                self._user_layout_icon(preset["layout"]), f"{preset['name']}\n{width} × {height}px"
            )
            item.setData(Qt.ItemDataRole.UserRole, preset["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, "preset")
            item.setToolTip(preset["name"])
            self.user_layout_list.addItem(item)
            if preset["id"] == selected:
                self.user_layout_list.setCurrentItem(item)
        self.user_layout_list.blockSignals(False)
        has_items = bool(setups or library)
        self.user_layout_empty.setVisible(not has_items)
        self.user_layout_list.setVisible(has_items)
        self._update_preset_actions()

    def _show_user_layouts(self):
        self.preferences_tabs.setCurrentIndex(0)
        self.controls_scroll.ensureWidgetVisible(self.user_layout_list, 0, 12)
        self.user_layout_list.setFocus()

    def _selected_user_layout(self):
        item = self.user_layout_list.currentItem()
        if item is None or item.data(Qt.ItemDataRole.UserRole + 1) != "preset":
            return None
        return get_layout_preset(
            read_layout_presets(self.draft), item.data(Qt.ItemDataRole.UserRole)
        )

    def _selected_setup(self):
        item = self.user_layout_list.currentItem()
        if item is None or item.data(Qt.ItemDataRole.UserRole + 1) != "setup":
            return None
        return find_setup(read_saved_setups(self.draft), item.data(Qt.ItemDataRole.UserRole))

    def _update_preset_actions(self):
        selected = self._selected_user_layout() is not None or self._selected_setup() is not None
        has_items = self.user_layout_list.count() > 0
        for button in (self.preset_rename_btn, self.preset_delete_btn):
            button.setEnabled(selected)
            button.setVisible(has_items)
        # A free layout has no built-in options to capture.
        self.preset_save_btn.setEnabled(not self._free_active())

    def _clear_builtin_selection(self):
        self.layout_group.setExclusive(False)
        for button in self.layout_buttons.values():
            button.setChecked(False)
        self.layout_group.setExclusive(True)

    def _select_user_layout(self, _item=None, _previous=None):
        self._update_preset_actions()
        if self._building:
            return
        setup = self._selected_setup()
        if setup is not None:
            write_setup_options(self.draft, setup)
            self.draft.setValue("widget_mode_layout", setup["layout_id"])
            self.draft.setValue(FREE_LAYOUT_MODE_KEY, "preset")
            self.draft.setValue(SELECTED_LAYOUT_PRESET_KEY, "")
            self.draft.setValue(SELECTED_SETUP_KEY, setup["id"])
            self._layout_changed = True
            self._custom_layout_changed = False
            button = self.layout_buttons.get(setup["layout_id"])
            if button is not None:
                button.setChecked(True)
            self._sync_visibility_controls()
            self._update_preset_actions()
            self._refresh_preview()
            return
        preset = self._selected_user_layout()
        if preset is None:
            return
        write_free_layout(self.draft, preset["layout"])
        self.draft.setValue(SELECTED_LAYOUT_PRESET_KEY, preset["id"])
        self.draft.setValue(SELECTED_SETUP_KEY, "")
        self._layout_changed = False
        self._custom_layout_changed = True
        self._clear_builtin_selection()
        self._sync_visibility_controls()
        self._update_preset_actions()
        self._refresh_preview()

    def _save_current_setup(self, name=None):
        if self._free_active():
            return
        layout_id = read_widget_mode_layout_id(self.draft)
        if name is None:
            spec = get_widget_mode_layout(layout_id)
            name = self._prompt_preset_name(
                t(spec.label_key, spec.label_default),
                title=t("widget_mode.preset_save", "현재 설정 저장…"),
            )
            if name is None:
                return
        try:
            setup = capture_setup(self.draft, name, layout_id)
            setups = add_setup(read_saved_setups(self.draft), setup)
        except ValueError:
            self._preset_error(invalid_name=True)
            return
        write_saved_setups(self.draft, setups)
        self.draft.setValue(SELECTED_SETUP_KEY, setup["id"])
        self._reload_user_layouts()

    def _sync_visibility_controls(self):
        self._sync_display_controls()
        for attribute, block_id, default in (
            ("calendar_visibility_checkbox", "calendar", "true"),
            ("clock_visibility_checkbox", "clock", "true"),
        ):
            checkbox = getattr(self, attribute, None)
            if checkbox is None:
                continue
            visible = (
                self._free_block_enabled(block_id)
                if self._free_active()
                else (
                    read_widget_calendar_visibility(
                        self.draft, read_widget_mode_layout_id(self.draft)
                    )
                    if block_id == "calendar"
                    else str(self.draft.value("widget_mode_show_clock", default)).lower() == "true"
                )
            )
            blocked = checkbox.blockSignals(True)
            checkbox.setChecked(visible)
            checkbox.blockSignals(blocked)

    def _prompt_preset_name(self, current, title=None):
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title or t("widget_mode.preset_rename", "이름 변경…"))
        dialog.setLabelText(t("widget_mode.preset_name", "배치 이름"))
        dialog.setTextValue(current)
        apply_common_dialog_style(dialog)
        return dialog.textValue() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _preset_error(self, invalid_name=False):
        message = QMessageBox(
            QMessageBox.Icon.Warning,
            self.windowTitle(),
            t(
                "widget_mode.preset_invalid_name",
                "이름은 1~80자이며 다른 배치와 중복될 수 없습니다.",
            )
            if invalid_name
            else t("widget_mode.preset_error", "배치를 저장하지 못했습니다."),
            QMessageBox.StandardButton.Ok,
            self,
        )
        apply_common_dialog_style(message)
        message.exec()

    def _rename_user_layout(self, name=None):
        setup = self._selected_setup()
        if setup is not None:
            name = self._prompt_preset_name(setup["name"]) if name is None else name
            if name is None:
                return
            try:
                setups = rename_setup(read_saved_setups(self.draft), setup["id"], name)
            except ValueError:
                self._preset_error(invalid_name=True)
                return
            write_saved_setups(self.draft, setups)
            self._reload_user_layouts()
            return
        preset = self._selected_user_layout()
        if preset is None:
            return
        name = self._prompt_preset_name(preset["name"]) if name is None else name
        if name is None:
            return
        try:
            write_layout_presets(
                self.draft,
                rename_layout_preset(read_layout_presets(self.draft), preset["id"], name),
            )
        except ValueError:
            self._preset_error(invalid_name=True)
            return
        self._reload_user_layouts()

    def _delete_user_layout(self, *, confirmed=False):
        setup = self._selected_setup()
        if setup is not None:
            if not confirmed and not self._confirm_delete(setup["name"]):
                return
            write_saved_setups(self.draft, delete_setup(read_saved_setups(self.draft), setup["id"]))
            self.draft.setValue(SELECTED_SETUP_KEY, "")
            self._reload_user_layouts()
            return
        preset = self._selected_user_layout()
        if preset is None:
            return
        if not confirmed:
            message = QMessageBox(
                QMessageBox.Icon.Question,
                self.windowTitle(),
                t(
                    "widget_mode.preset_delete_confirm",
                    "“{name}” 배치를 삭제할까요?",
                    name=preset["name"],
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                self,
            )
            message.setTextFormat(Qt.TextFormat.PlainText)
            message.button(QMessageBox.StandardButton.Yes).setText(
                t("widget_mode.preset_delete", "삭제")
            )
            message.setDefaultButton(QMessageBox.StandardButton.Cancel)
            apply_common_dialog_style(message)
            if message.exec() != QMessageBox.StandardButton.Yes:
                return
        write_layout_presets(
            self.draft, delete_layout_preset(read_layout_presets(self.draft), preset["id"])
        )
        self.draft.setValue(SELECTED_LAYOUT_PRESET_KEY, "")
        self._reload_user_layouts()

    def _confirm_delete(self, name):
        message = QMessageBox(
            QMessageBox.Icon.Question,
            self.windowTitle(),
            t("widget_mode.preset_delete_confirm", "“{name}” 배치를 삭제할까요?", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            self,
        )
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.button(QMessageBox.StandardButton.Yes).setText(
            t("widget_mode.preset_delete", "삭제")
        )
        message.setDefaultButton(QMessageBox.StandardButton.Cancel)
        apply_common_dialog_style(message)
        return message.exec() == QMessageBox.StandardButton.Yes

    def _sync_appearance_controls(self):
        for control, setter, value in (
            (
                self.surface_combo,
                self.surface_combo.setCurrentIndex,
                self.surface_combo.findData(read_widget_mode_surface(self.draft)),
            ),
            (
                self.font_family,
                self.font_family.setCurrentFont,
                QFont(
                    str(
                        self.draft.value(
                            "widget_mode_font_family", self.font_family.currentFont().family()
                        )
                    )
                ),
            ),
            (
                self.font_size,
                self.font_size.setValue,
                read_widget_typography(self.draft).preference,
            ),
            (
                self.font_weight,
                self.font_weight.setCurrentIndex,
                self.font_weight.findData(self._font_weight_preference()),
            ),
        ):
            blocked = control.blockSignals(True)
            setter(value)
            control.blockSignals(blocked)
        self._sync_surface_gallery()

    @staticmethod
    def _layout_card_style(width: int, height: int, *, max_height: int | None = None) -> str:
        return (
            f"QToolButton {{ min-width: {width}px; min-height: {height}px; "
            f"max-height: {max_height if max_height is not None else height}px; "
            "padding: 4px; }"
            "QToolButton:checked { border: 2px solid #65a7ff; border-radius: 6px; }"
        )

    def _reflow_layout_cards(self):
        grid = self._layout_card_grid
        while grid.count():
            grid.takeAt(0)
        columns = (
            1 if any(button.minimumWidth() > 190 for button in self.layout_buttons.values()) else 2
        )
        for index, button in enumerate(self.layout_buttons.values()):
            grid.addWidget(button, index // columns, index % columns)

    def _font_weight_preference(self):
        try:
            weight = int(self.draft.value("widget_mode_font_weight", 500))
        except (TypeError, ValueError, OverflowError):
            weight = 500
        return weight if weight in (400, 500, 600, 700) else 500

    def _layout_icon(self, spec):
        tokens = main_widget_mode_tokens(self.draft)
        pixmap = QPixmap(90, 58)
        pixmap.fill(QColor(tokens["_main_base_color"]))
        painter = QPainter(pixmap)
        rows = max(row + rs for _, row, col, rs, cs in spec.placements)
        cols = max(col + cs for _, row, col, rs, cs in spec.placements)
        for section, row, col, rs, cs in spec.placements:
            painter.fillRect(
                4 + int(col * 82 / cols),
                4 + int(row * 50 / rows),
                max(4, int(cs * 82 / cols) - 3),
                max(4, int(rs * 50 / rows) - 3),
                parse_css_color(tokens["accent"] if section == "agenda" else tokens["text_muted"]),
            )
        painter.end()
        return QIcon(pixmap)

    def _appearance_tab(self):
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.surface_combo = QComboBox(tab)
        for surface in widget_mode_surfaces():
            swatch = QPixmap(20, 20)
            swatch.fill(QColor(main_widget_mode_tokens(self.draft)["accent"]))
            self.surface_combo.addItem(
                QIcon(swatch), t(surface.label_key, surface.label_default), surface.key
            )
        self.surface_combo.setCurrentIndex(
            self.surface_combo.findData(read_widget_mode_surface(self.draft))
        )
        self.surface_combo.setAccessibleName(t("widget_mode.surface_title", "표면 모양"))
        self.surface_combo.currentIndexChanged.connect(
            lambda: self._change(SURFACE_SETTING_KEY, self.surface_combo.currentData())
        )
        self.surface_combo.hide()
        self.surface_gallery = QListWidget(tab)
        self.surface_gallery.setAccessibleName(t("widget_mode.surface_title", "표면 모양"))
        self.surface_gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.surface_gallery.setMovement(QListWidget.Movement.Static)
        self.surface_gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.surface_gallery.setIconSize(QSize(150, 74))
        self.surface_gallery.setGridSize(QSize(172, 112))
        self.surface_gallery.setWordWrap(True)
        self.surface_gallery.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.surface_gallery.installEventFilter(self)
        self.surface_gallery.setMinimumWidth(0)
        self.surface_gallery.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.surface_gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for surface in widget_mode_surfaces():
            item = QListWidgetItem(
                self._surface_icon(surface), t(surface.label_key, surface.label_default)
            )
            item.setData(Qt.ItemDataRole.UserRole, surface.key)
            item.setToolTip(item.text())
            self.surface_gallery.addItem(item)
        self._fit_surface_gallery_height()
        self._sync_surface_gallery()
        self.surface_gallery.currentItemChanged.connect(
            lambda item, _old: (
                self.surface_combo.setCurrentIndex(
                    self.surface_combo.findData(item.data(Qt.ItemDataRole.UserRole))
                )
                if item is not None
                else None
            )
        )
        self.surface_combo.currentIndexChanged.connect(self._sync_surface_gallery)
        form.addRow(t("widget_mode.surface_title", "표면 모양"), self.surface_gallery)
        self.font_family = QFontComboBox(tab)
        self.font_family.setCurrentFont(
            QFont(
                str(
                    self.draft.value(
                        "widget_mode_font_family", self.controller.widget.font().family()
                    )
                )
            )
        )
        self.font_family.setMinimumWidth(0)
        self.font_family.setAccessibleName(t("widget_mode.font_family", "글꼴"))
        self.font_family.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.font_family.currentFontChanged.connect(
            lambda font: self._change("widget_mode_font_family", font.family())
        )
        font_family_row = QHBoxLayout()
        font_family_row.setContentsMargins(0, 0, 0, 0)
        font_family_row.setSpacing(6)
        font_family_row.addWidget(self.font_family, 1)
        self.font_dropdown_btn = QToolButton(tab)
        self.font_dropdown_btn.setObjectName("font_dropdown_btn")
        self.font_dropdown_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.font_dropdown_btn.setFixedSize(38, 36)
        # The dialog's shared QToolButton min-width would widen it (to 48px) once the
        # tab is polished; this tab is now the first one shown.
        self.font_dropdown_btn.setStyleSheet(
            "QToolButton#font_dropdown_btn { min-width: 36px; max-width: 36px; padding: 0; }"
        )
        self.font_dropdown_btn.setToolTip(t("widget_mode.font_dropdown", "글꼴 목록 열기"))
        self.font_dropdown_btn.setAccessibleName(self.font_dropdown_btn.toolTip())
        self.font_dropdown_btn.clicked.connect(self.font_family.showPopup)
        font_family_row.addWidget(self.font_dropdown_btn)
        form.addRow(t("widget_mode.font_family", "글꼴"), font_family_row)
        self.font_size = QSpinBox(tab)
        self.font_size.setRange(10, 18)
        self.font_size.setValue(read_widget_typography(self.draft).preference)
        self.font_size.valueChanged.connect(
            lambda value: self._change("widget_mode_font_size", value)
        )
        font_size_label = QLabel(t("widget_mode.font_size", "전체 글자 크기"), tab)
        font_size_help = t(
            "widget_mode.font_size_help",
            "날짜, 버튼, 캘린더와 목록을 같은 비율로 조절합니다.",
        )
        font_size_label.setToolTip(font_size_help)
        font_size_label.setBuddy(self.font_size)
        self.font_size.setAccessibleName(font_size_label.text())
        self.font_size.setToolTip(font_size_help)
        self.font_size.setAccessibleDescription(font_size_help)
        form.addRow(font_size_label, self.font_size)
        self.font_weight = QComboBox(tab)
        for value, key, label in (
            (400, "regular", "보통"),
            (500, "medium", "중간"),
            (600, "semibold", "약간 굵게"),
            (700, "bold", "굵게"),
        ):
            self.font_weight.addItem(t(f"widget_mode.font_{key}", label), value)
        self.font_weight.setCurrentIndex(self.font_weight.findData(self._font_weight_preference()))
        self.font_weight.setAccessibleName(t("widget_mode.font_weight", "제목 굵기"))
        self.font_weight.currentIndexChanged.connect(
            lambda: self._change("widget_mode_font_weight", self.font_weight.currentData())
        )
        form.addRow(t("widget_mode.font_weight", "제목 굵기"), self.font_weight)
        surface_help = QLabel(
            t("widget_mode.surface_help", "색과 투명도는 모양 설정을 따릅니다."), tab
        )
        surface_help.setWordWrap(True)
        surface_help.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form.addRow(surface_help)
        self.open_appearance_btn = QPushButton(
            t("widget_mode.open_appearance", "모양 설정 열기"), tab
        )
        self.open_appearance_btn.setObjectName("open_appearance_btn")
        opener = getattr(
            getattr(self.controller, "main_window", None),
            "open_panel_background_color_dialog",
            None,
        )
        if callable(opener):
            self.open_appearance_btn.clicked.connect(lambda _checked=False: opener())
        else:
            self.open_appearance_btn.hide()
        form.addRow(self.open_appearance_btn)
        return tab

    def _surface_icon(self, surface):
        from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor

        values = main_widget_mode_tokens(self.draft)
        background, fill, accent = values["panel_bg"], values["section_bg"], values["accent"]
        image = QPixmap(150, 74)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(css_to_qcolor(background))
        radius = surface.radius
        painter.drawRoundedRect(1, 1, 148, 72, radius, radius)
        painter.setBrush(css_to_qcolor(accent))
        painter.drawRoundedRect(10, 10, 35, 5, 2, 2)
        item_radius = surface.item_radius
        outline = css_to_qcolor(accent)
        outline.setAlpha(150)
        soft_outline = css_to_qcolor(accent)
        soft_outline.setAlpha(60)
        for row in range(3):
            top = 23 + row * 14
            if surface.item_background == "card":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(css_to_qcolor(fill))
                painter.drawRoundedRect(10, top, 130, 11, item_radius, item_radius)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if surface.item_border == "full":
                painter.setPen(outline if surface.item_background != "card" else soft_outline)
                painter.drawRoundedRect(10, top, 130, 11, item_radius, item_radius)
            else:
                painter.setPen(outline)
                painter.drawLine(10, top + 12, 140, top + 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(css_to_qcolor(accent))
            painter.drawRoundedRect(14, top + 4, 55 + row * 12, 3, 1, 1)
        painter.end()
        icon = QIcon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            icon.addPixmap(image, mode)
        return icon

    def _fit_surface_gallery_height(self, viewport_width: int | None = None) -> None:
        """Size the gallery to the rows its current width needs so no card is clipped."""
        gallery = self.surface_gallery
        frame = gallery.frameWidth()
        if viewport_width is None:
            viewport_width = gallery.width() - 2 * frame
        grid = gallery.gridSize()
        columns = max(1, viewport_width // max(1, grid.width()))
        rows = -(-gallery.count() // columns)
        height = rows * grid.height() + 2 * frame + 8
        if gallery.height() != height:
            gallery.setFixedHeight(height)

    def _sync_surface_gallery(self, *_):
        if not hasattr(self, "surface_gallery"):
            return
        selected = self.surface_combo.currentData()
        blocked = self.surface_gallery.blockSignals(True)
        for index in range(self.surface_gallery.count()):
            item = self.surface_gallery.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == selected:
                self.surface_gallery.setCurrentItem(item)
                break
        self.surface_gallery.blockSignals(blocked)

    def _scroll_active_surface(self, *_):
        if (
            self.preferences_tabs.currentIndex() == 1
            and self.surface_gallery.currentItem() is not None
        ):
            self.surface_gallery.scrollToItem(
                self.surface_gallery.currentItem(), QListWidget.ScrollHint.PositionAtCenter
            )

    def _build_display_group(self, tab, form):
        self.display_group_title = self._section_title(
            t("widget_mode.display_group", "선택한 배치"), tab
        )
        form.addWidget(self.display_group_title)
        row = QHBoxLayout()
        self.calendar_style_label = QLabel(t("widget_mode.calendar_style", "달력 형태"), tab)
        row.addWidget(self.calendar_style_label)
        self.calendar_style_combo = QComboBox(tab)
        self.calendar_style_combo.addItem(t("widget_mode.week_toggle", "주간"), "week")
        self.calendar_style_combo.addItem(t("widget_mode.month_toggle", "월간"), "month")
        self.calendar_style_combo.setAccessibleName(t("widget_mode.calendar_style", "달력 형태"))
        self.calendar_style_label.setBuddy(self.calendar_style_combo)
        row.addWidget(self.calendar_style_combo, 1)
        form.addLayout(row)
        self.show_overview_checkbox = QCheckBox(t("widget_mode.show_overview", "요약 줄 표시"), tab)
        form.addWidget(self.show_overview_checkbox)
        self.search_pinned_checkbox = QCheckBox(
            t("widget_mode.search_pinned", "검색창 항상 표시"), tab
        )
        form.addWidget(self.search_pinned_checkbox)
        checkbox = QCheckBox(t("widget_mode.show_calendar", "달력 표시"), tab)
        checkbox.setChecked(
            self._free_block_enabled("calendar")
            if self._free_active()
            else read_widget_calendar_visibility(self.draft, read_widget_mode_layout_id(self.draft))
        )
        checkbox.toggled.connect(self._change_calendar_visibility)
        calendar_help = t(
            "widget_mode.calendar_visibility_help",
            "선택한 배치의 달력만 접거나 펼칩니다. 다른 배치의 설정은 유지됩니다.",
        )
        checkbox.setToolTip(calendar_help)
        checkbox.setAccessibleDescription(calendar_help)
        self.calendar_visibility_checkbox = checkbox
        form.addWidget(checkbox)
        scope_help = QLabel(t("widget_mode.display_scope_help", "선택한 배치에만 적용됩니다."), tab)
        scope_help.setWordWrap(True)
        form.addWidget(scope_help)
        self.calendar_style_combo.currentIndexChanged.connect(
            lambda: self._change_display(
                CALENDAR_STYLE_PREFIX, self.calendar_style_combo.currentData()
            )
        )
        self.show_overview_checkbox.toggled.connect(
            lambda value: self._change_display(SHOW_OVERVIEW_PREFIX, value)
        )
        self.search_pinned_checkbox.toggled.connect(
            lambda value: self._change_display(SEARCH_PINNED_PREFIX, value)
        )
        self._sync_display_controls()

    def _change_display(self, prefix, value):
        if self._building:
            return
        self.draft.setValue(display_key(prefix, read_widget_mode_layout_id(self.draft)), value)
        self._refresh_preview()

    def _sync_display_controls(self):
        if not hasattr(self, "calendar_style_combo"):
            return
        layout_id = read_widget_mode_layout_id(self.draft)
        display = read_layout_display(self.draft, get_widget_mode_layout(layout_id))
        for control, setter, value in (
            (
                self.calendar_style_combo,
                self.calendar_style_combo.setCurrentIndex,
                self.calendar_style_combo.findData(display.calendar_style),
            ),
            (
                self.show_overview_checkbox,
                self.show_overview_checkbox.setChecked,
                display.show_overview,
            ),
            (
                self.search_pinned_checkbox,
                self.search_pinned_checkbox.setChecked,
                display.search_pinned,
            ),
        ):
            blocked = control.blockSignals(True)
            setter(value)
            control.blockSignals(blocked)
        if hasattr(self, "display_group_title"):
            spec = get_widget_mode_layout(layout_id)
            self.display_group_title.setText(
                t("widget_mode.free_layout", "자유 구성")
                if self._free_active()
                else t("widget_mode.layout_options", "{name} 옵션").format(
                    name=t(spec.label_key, spec.label_default)
                )
            )
        show_style = layout_id != "minimal" and not self._free_active()
        self.calendar_style_label.setVisible(show_style)
        self.calendar_style_combo.setVisible(show_style)

    def _visibility_tab(self):
        tab = QWidget(self)
        form = QVBoxLayout(tab)
        from calendar_app.presentation.widgets.widget_mode_skins import (
            LAYOUT_SELECTION_ENABLED,
        )

        if not LAYOUT_SELECTION_ENABLED:
            self._build_display_group(tab, form)
        form.addWidget(QLabel(t("widget_mode.density", "목록 밀도"), tab))
        self.density_combo = QComboBox(tab)
        for density in DENSITIES:
            self.density_combo.addItem(
                t(f"widget_mode.density_{density.key}", density.label), density.key
            )
        self.density_combo.setCurrentIndex(
            self.density_combo.findData(read_widget_density(self.draft).key)
        )
        self.density_combo.setAccessibleName(t("widget_mode.density", "목록 밀도"))
        self.density_combo.currentIndexChanged.connect(
            lambda: self._change(DENSITY_KEY, self.density_combo.currentData())
        )
        form.addWidget(self.density_combo)
        help_label = QLabel(
            t("widget_mode.density_help", "글자 크기는 유지하고 행 간격과 시간 배치를 조절합니다."),
            tab,
        )
        help_label.setWordWrap(True)
        form.addWidget(help_label)
        for key, label, default in (
            ("widget_mode_show_clock", t("widget_mode.show_clock", "시계 표시"), "true"),
            ("widget_mode_show_hint", t("widget_mode.show_hint", "보조 설명 표시"), "false"),
            (
                "widget_mode_show_completed",
                t("widget_mode.show_completed", "완료 포함"),
                "false",
            ),
        ):
            checkbox = QCheckBox(label, tab)
            if key == "widget_mode_show_week":
                checkbox.setChecked(
                    self._free_block_enabled("calendar")
                    if self._free_active()
                    else read_widget_calendar_visibility(
                        self.draft, read_widget_mode_layout_id(self.draft)
                    )
                )
                checkbox.toggled.connect(self._change_calendar_visibility)
                self.calendar_visibility_checkbox = checkbox
                calendar_help = t(
                    "widget_mode.calendar_visibility_help",
                    "선택한 배치의 달력만 접거나 펼칩니다. 다른 배치의 설정은 유지됩니다.",
                )
                checkbox.setToolTip(calendar_help)
                checkbox.setAccessibleDescription(calendar_help)
            else:
                checkbox.setChecked(
                    self._free_block_enabled("clock")
                    if key == "widget_mode_show_clock" and self._free_active()
                    else str(self.draft.value(key, default)).lower() == "true"
                )
                checkbox.toggled.connect(lambda value, setting=key: self._change(setting, value))
            if key == "widget_mode_show_completed":
                completed_help = t(
                    "widget_mode.show_completed_help",
                    "완료된 업무와 지시·협조도 목록에 표시합니다.",
                )
                checkbox.setToolTip(completed_help)
                checkbox.setAccessibleDescription(completed_help)
            if key == "widget_mode_show_clock":
                self.clock_visibility_checkbox = checkbox
            form.addWidget(checkbox)
            if key == "widget_mode_show_clock":
                self._build_clock_options(tab, form)
        form.addStretch(1)
        return tab

    def _build_clock_options(self, tab, form) -> None:
        """Clock format, seconds, size and date line, indented under '시계 표시'."""
        from calendar_app.presentation.widgets.widget_mode_clock import (
            CLOCK_DATE_KEY,
            CLOCK_FORMAT_KEY,
            CLOCK_SECONDS_KEY,
            CLOCK_SIZE_KEY,
            read_clock_options,
        )

        options = read_clock_options(self.draft)
        box = QWidget(tab)
        grid = QGridLayout(box)
        grid.setContentsMargins(24, 0, 0, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self.clock_format_combo = QComboBox(box)
        self.clock_format_combo.addItem(t("widget_mode.clock_24h", "24시간 (14:05)"), "24h")
        self.clock_format_combo.addItem(t("widget_mode.clock_12h", "12시간 (오후 2:05)"), "12h")
        self.clock_format_combo.setCurrentIndex(
            self.clock_format_combo.findData(options.hour_format)
        )
        self.clock_format_combo.currentIndexChanged.connect(
            lambda: self._change(CLOCK_FORMAT_KEY, self.clock_format_combo.currentData())
        )
        self.clock_size_combo = QComboBox(box)
        self.clock_size_combo.addItem(t("widget_mode.clock_small", "작게 (아래쪽)"), "small")
        self.clock_size_combo.addItem(t("widget_mode.clock_large", "크게 (위쪽)"), "large")
        self.clock_size_combo.setCurrentIndex(self.clock_size_combo.findData(options.size))
        self.clock_size_combo.currentIndexChanged.connect(
            lambda: self._change(CLOCK_SIZE_KEY, self.clock_size_combo.currentData())
        )
        format_label = QLabel(t("widget_mode.clock_format", "시간 형식"), box)
        size_label = QLabel(t("widget_mode.clock_size", "크기"), box)
        format_label.setBuddy(self.clock_format_combo)
        size_label.setBuddy(self.clock_size_combo)
        self.clock_format_combo.setAccessibleName(format_label.text())
        self.clock_size_combo.setAccessibleName(t("widget_mode.clock_size_name", "시계 크기"))
        self.clock_seconds_checkbox = QCheckBox(t("widget_mode.clock_seconds", "초 표시"), box)
        self.clock_seconds_checkbox.setChecked(options.seconds)
        self.clock_seconds_checkbox.toggled.connect(
            lambda value: self._change(CLOCK_SECONDS_KEY, bool(value))
        )
        self.clock_date_checkbox = QCheckBox(
            t("widget_mode.clock_show_date", "날짜 함께 표시"), box
        )
        self.clock_date_checkbox.setChecked(options.show_date)
        self.clock_date_checkbox.toggled.connect(
            lambda value: self._change(CLOCK_DATE_KEY, bool(value))
        )
        grid.addWidget(format_label, 0, 0)
        grid.addWidget(self.clock_format_combo, 0, 1)
        grid.addWidget(size_label, 1, 0)
        grid.addWidget(self.clock_size_combo, 1, 1)
        grid.addWidget(self.clock_seconds_checkbox, 2, 0, 1, 2)
        grid.addWidget(self.clock_date_checkbox, 3, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        self.clock_options_box = box
        box.setEnabled(self.clock_visibility_checkbox.isChecked())
        self.clock_visibility_checkbox.toggled.connect(box.setEnabled)
        form.addWidget(box)

    def _build_preview(self):
        from calendar_app.presentation.widgets.unified_widget_mode import (
            UnifiedWidgetController,
            UnifiedWidgetWindow,
        )

        self.preview_host = QWidget(self)
        self.preview_host.hide()
        self.preview_host.settings = self.draft
        self.preview_host.current_date = QDate.currentDate()
        self.preview_controller = UnifiedWidgetController(self.preview_host)
        self.preview = UnifiedWidgetWindow(self.preview_controller)
        self.preview_controller.widget = self.preview
        # A hidden top-level preview must not inherit the dialog's control metrics.
        # It is rendered offscreen only and explicitly owned for cleanup.
        self.preview.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        # This is a static two-item sample, not an interactive scrollable window.
        self.preview.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.destroyed.connect(self.preview.deleteLater)
        self.preview.resize(420, 600)

    def _change(self, key, value):
        self.draft.setValue(key, value)
        if key == "widget_mode_layout" and not self._building:
            self.draft.setValue(SELECTED_SETUP_KEY, "")
            self._layout_changed = True
            self._custom_layout_changed = False
            self.draft.setValue(FREE_LAYOUT_MODE_KEY, "preset")
            self.draft.setValue(SELECTED_LAYOUT_PRESET_KEY, "")
            self.user_layout_list.blockSignals(True)
            self.user_layout_list.setCurrentRow(-1)
            self.user_layout_list.blockSignals(False)
            self._update_preset_actions()
            self._sync_visibility_controls()
        if key == "widget_mode_show_clock" and self._free_active():
            self._change_free_block("clock", value)
        if key == "widget_mode_layout" and hasattr(self, "calendar_visibility_checkbox"):
            visible = read_widget_calendar_visibility(self.draft, value)
            self.calendar_visibility_checkbox.blockSignals(True)
            self.calendar_visibility_checkbox.setChecked(visible)
            self.calendar_visibility_checkbox.blockSignals(False)
        if not self._building:
            self._refresh_preview()

    def _change_calendar_visibility(self, visible: bool) -> None:
        if self._free_active():
            self._change_free_block("calendar", visible)
        else:
            write_widget_calendar_visibility(
                self.draft,
                read_widget_mode_layout_id(self.draft),
                visible,
            )
        if not self._building:
            self._refresh_preview()

    def _free_active(self):
        return str(self.draft.value(FREE_LAYOUT_MODE_KEY, "preset")) == "free"

    def _free_block_enabled(self, block_id):
        return next(
            block for block in read_free_layout(self.draft)["blocks"] if block["id"] == block_id
        )["enabled"]

    def _change_free_block(self, block_id, enabled):
        layout = read_free_layout(self.draft)
        next(block for block in layout["blocks"] if block["id"] == block_id)["enabled"] = bool(
            enabled
        )
        write_free_layout(self.draft, layout)

    def _refresh_preview(self):
        if getattr(self, "_rendering", False):
            return
        self._rendering = True
        try:
            self._render_preview()
        finally:
            self._rendering = False

    def _render_preview(self):
        spec = get_widget_mode_layout(read_widget_mode_layout_id(self.draft))
        self.preview.apply_selected_layout(force=True)
        if self._free_active():
            self.preview.resize(*read_free_layout(self.draft)["canvas"])
        else:
            self.preview.resize(max(380, spec.preferred_size[0]), spec.preferred_size[1])
        self.preview._style_signature = None
        self.preview.apply_theme()
        show_completed = (
            str(self.draft.value("widget_mode_show_completed", "false")).lower() == "true"
        )
        self.preview.completed_btn.setChecked(show_completed)
        preview_items = [
            {
                "title": t("widget_mode.preview_schedule", "프로젝트 회의"),
                "time": "14:00",
                "is_task": False,
                "item_kind": "schedule",
                "item_id": 2,
                "source": "task",
            },
            {
                "title": t("widget_mode.preview_work", "회의 자료 정리"),
                "time": "",
                "is_task": True,
                "item_kind": "work",
                "item_id": 1,
                "source": "task",
                "completed": show_completed,
            },
        ]
        if spec.presentation == "board":
            preview_items.append(
                {
                    "title": t("widget_mode.preview_directive", "검토 의견 전달"),
                    "time": "",
                    "is_task": True,
                    "item_kind": "work",
                    "item_id": 3,
                    "source": "directive",
                    "completed": False,
                }
            )
        self.preview.update_agenda(preview_items)
        self.preview.layout().activate()
        # Render the widget's own transparent layers, not the dialog's background.
        self.preview.ensurePolished()
        ratio = self.preview.devicePixelRatioF()
        raw = QPixmap(self.preview.size() * ratio)
        raw.setDevicePixelRatio(ratio)
        raw.fill(Qt.GlobalColor.transparent)
        self.preview.render(raw, flags=QWidget.RenderFlag.DrawChildren)
        self._preview_pixmap = QPixmap(raw.size())
        self._preview_pixmap.setDevicePixelRatio(raw.devicePixelRatio())
        main = main_widget_mode_tokens(self.draft)
        preview_base = QColor(main["_main_base_color"])
        self._preview_pixmap.fill(preview_base)
        painter = QPainter(self._preview_pixmap)
        for y in range(0, self.preview.height(), 24):
            for x in range(0, self.preview.width(), 24):
                if (x // 24 + y // 24) % 2:
                    painter.fillRect(
                        x, y, 24, 24, composite_color(main["surface_alt"], preview_base)
                    )
        painter.drawPixmap(0, 0, raw)
        painter.end()
        self._scale_preview()

    def _scale_preview(self):
        self.preview_label.setPixmap(
            self._preview_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_preview_pixmap") and not self._building:
            self._scale_preview()

    def eventFilter(self, watched, event):
        layout_id = watched.property("layoutId") if isinstance(watched, QToolButton) else None
        if layout_id and watched in getattr(self, "layout_buttons", {}).values():
            if event.type() == QEvent.Type.Enter:
                self._preview_hovered_layout(layout_id)
            elif event.type() == QEvent.Type.Leave:
                self._end_layout_hover()
        if event.type() == QEvent.Type.Wheel and watched in getattr(self, "_wheel_controls", ()):
            # Route scrolling explicitly because the tab container may consume it.
            # Clicks, popup lists and keyboard arrows still change the value normally.
            QCoreApplication.sendEvent(self.controls_scroll.viewport(), event)
            return True
        if watched is getattr(self, "surface_gallery", None) and event.type() == QEvent.Type.Resize:
            self._fit_surface_gallery_height(event.size().width() - 2 * watched.frameWidth())
        if (
            watched is getattr(self, "preview_label", None)
            and event.type() == QEvent.Type.Resize
            and hasattr(self, "_preview_pixmap")
        ):
            self._scale_preview()
        return super().eventFilter(watched, event)

    def _removed_preset_layouts(self, settings):
        """Layouts of stored presets that the draft library no longer contains."""
        if USER_LAYOUT_PRESETS_KEY not in self.draft.values:
            return []
        kept = {preset["id"] for preset in read_layout_presets(self.draft)}
        return [
            preset["layout"] for preset in read_layout_presets(settings) if preset["id"] not in kept
        ]

    def _apply(self):
        allowed = {
            "widget_mode_layout",
            SURFACE_SETTING_KEY,
            "widget_mode_font_size",
            "widget_mode_font_family",
            "widget_mode_font_weight",
            DENSITY_KEY,
            "widget_mode_show_clock",
            "widget_mode_clock_format",
            "widget_mode_clock_seconds",
            "widget_mode_clock_size",
            "widget_mode_clock_show_date",
            "widget_mode_show_week",
            "widget_mode_show_hint",
            "widget_mode_show_completed",
            USER_LAYOUT_PRESETS_KEY,
            SELECTED_LAYOUT_PRESET_KEY,
            SAVED_SETUPS_KEY,
            SELECTED_SETUP_KEY,
        }
        settings = self.controller.main_window.settings
        self.controller._save_geometry()
        removed_layouts = self._removed_preset_layouts(settings)
        for key, value in self.draft.values.items():
            if (
                key in allowed
                or key.startswith(
                    (
                        "widget_mode_calendar_visible_",
                        CALENDAR_STYLE_PREFIX,
                        SHOW_OVERVIEW_PREFIX,
                        SEARCH_PINNED_PREFIX,
                    )
                )
            ) and key != "widget_mode_layout":
                settings.setValue(key, value)
        if removed_layouts:
            # A deleted preset's layout may still be the working free layout; without
            # this the next migration would add it back as "이전 자유 구성".
            remember_handled_free_layouts(settings, removed_layouts)
        if self._free_active():
            if self._custom_layout_changed:
                self.controller.apply_free_layout(read_free_layout(self.draft))
            else:
                write_free_layout(settings, read_free_layout(self.draft))
        if not self._free_active():
            self.controller.set_layout(read_widget_mode_layout_id(self.draft))
        widget = self.controller.widget
        if widget is not None:
            widget.apply_selected_layout(force=True)
            widget._style_signature = None
            widget.apply_theme()
            widget.completed_btn.setChecked(
                str(settings.value("widget_mode_show_completed", "false")).lower() == "true"
            )
        self.controller.force_refresh()
        if hasattr(settings, "sync"):
            settings.sync()
        self.accept()
