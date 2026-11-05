# -*- coding: utf-8 -*-
"""Widget discovery and workspace controls for the nonmodal management hub."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.overlay_manager import _WIDGET_TYPES, widget_type_label
from calendar_app.shared.icon_map import strip_leading_emoji as _se


def hub_button(text, callback, *, primary=False):
    button = QPushButton(text)
    button.setAutoDefault(False)
    button.setObjectName("primary_btn" if primary else "ghost_btn")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(34)
    button.clicked.connect(callback)
    return button


def hub_label(text, role="hubBody"):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setObjectName(role)
    label.setWordWrap(True)
    return label


def apply_hub_dialog_style(dialog, parent=None, *, minimum_width=500, size=(640, 480)):
    """Keep nested workspace editors on the hub's current semantic palette."""
    from calendar_app.presentation.widgets.overlay_manager_dialog import _load_tokens
    from calendar_app.presentation.widgets.widget_management_styles import management_styles
    from calendar_app.shared.theme_snapshot import _css_to_qcolor

    tokens = getattr(parent, "_tok", None) or _load_tokens()
    dialog._tok = tokens
    apply_common_dialog_style(
        dialog,
        minimum_width=minimum_width,
        size=size,
        theme_color=tokens["accent"],
        text_theme="light" if _css_to_qcolor(tokens["text_primary"]).lightness() < 128 else "dark",
        panel_base_color=_css_to_qcolor(tokens["bg_main"]).name(),
        extra_stylesheet=management_styles(tokens),
    )


_TYPE_HELP = {
    "clock": ("clock", "현재 시간을 크게 확인해요"),
    "stopwatch": ("stopwatch", "작업에 쓴 시간을 측정해요"),
    "date_card": ("date_card", "오늘 날짜와 요일을 확인해요"),
    "countdown": ("countdown", "목표 시간까지 남은 시간을 봐요"),
    "dday": ("dday", "중요한 날까지 남은 날짜를 봐요"),
    "text": ("text", "메모와 정보 템플릿을 표시해요"),
    "weather": ("weather", "현재 날씨와 시간별 예보를 봐요"),
    "launcher_deck": ("launcher_deck", "자주 쓰는 앱과 단축키를 실행해요"),
}


class WidgetAddDialog(QDialog):
    """Selection is a draft; only accepting this dialog creates an instance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("widget_hub.add_title", "어떤 위젯을 추가할까요?"))
        apply_common_dialog_style(self, minimum_width=560, size=(660, 620))
        from calendar_app.presentation.widgets.overlay_manager_dialog import _load_tokens
        from calendar_app.presentation.widgets.widget_management_styles import management_styles

        tokens = getattr(parent, "_tok", None) or _load_tokens()
        self.setStyleSheet(self.styleSheet() + management_styles(tokens))
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.addWidget(hub_label(t("widget_hub.add_title", "어떤 위젯을 추가할까요?"), "hubTitle"))
        root.addWidget(
            hub_label(
                t(
                    "widget_hub.add_hint",
                    "종류를 선택해 추가하세요. 디자인과 세부 옵션은 추가 후 바꿀 수 있어요.",
                )
            )
        )
        scroll = QScrollArea()
        scroll.setObjectName("hubGalleryScroll")
        scroll.viewport().setObjectName("hubGalleryViewport")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("hubGalleryBody")
        grid = QGridLayout(body)
        grid.setSpacing(10)
        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)
        self.kind_buttons = {}
        for index, kind in enumerate(_WIDGET_TYPES):
            key, fallback = _TYPE_HELP[kind]
            button = QPushButton(
                f"{widget_type_label(kind)}\n{t('widget_hub.type_' + key, fallback)}"
            )
            button.setObjectName("hubTypeCard")
            button.setMinimumHeight(82)
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(_se(widget_type_label(kind)))
            self.type_group.addButton(button)
            self.kind_buttons[kind] = button
            grid.addWidget(button, index // 2, index % 2)
        self.kind_buttons["clock"].setChecked(True)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        name_label = hub_label(t("widget_hub.name_optional", "위젯 이름 · 선택"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(
            t("widget_hub.name_hint", "비워 두면 종류 이름으로 추가합니다")
        )
        name_label.setBuddy(self.name_edit)
        self.name_edit.setAccessibleName(name_label.text())
        root.addWidget(name_label)
        root.addWidget(self.name_edit)
        footer, self.add_button, cancel_button = build_dialog_footer(
            ok_label=t("widget_hub.add", "위젯 추가"),
            cancel_label=t("common.cancel", "취소"),
        )
        self.add_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        root.addLayout(footer)

    def selection(self):
        kind = next(kind for kind, button in self.kind_buttons.items() if button.isChecked())
        return kind, self.name_edit.text().strip() or None


class WidgetModeManagementPanel(QWidget):
    """Read-only overview until an explicit lifecycle or editor action is chosen."""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.setObjectName("hubModeBody")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.owner = owner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        self.status = hub_label("", "hubStatus")
        layout.addWidget(self.status)
        layout.addWidget(
            hub_label(t("widget_hub.mode_title", "캘린더와 할 일을 하나의 화면으로"), "hubTitle")
        )
        layout.addWidget(
            hub_label(
                t(
                    "widget_hub.mode_desc",
                    "위젯 전용 모드는 메인 화면을 대신하는 작은 작업 공간입니다. 화면 형태와 스킨을 조합하고 필요한 정보만 표시하세요.",
                )
            )
        )
        summary = QFrame()
        summary.setObjectName("hubSummary")
        details = QVBoxLayout(summary)
        details.setContentsMargins(18, 18, 18, 18)
        details.setSpacing(12)
        details.addWidget(hub_label(t("widget_hub.current_setup", "현재 화면 구성"), "hubEyebrow"))
        self.layout_name = hub_label("", "hubTitle")
        self.skin_name = hub_label("")
        self.catalog = hub_label("")
        details.addWidget(self.layout_name)
        details.addWidget(self.skin_name)
        details.addWidget(self.catalog)
        row = QHBoxLayout()
        self.customize_button = hub_button(
            t("widget_hub.customize_mode", "화면·스킨 꾸미기"), self._customize, primary=True
        )
        self.free_button = hub_button(
            t("widget_hub.free_editor", "자유 구성 편집"), self._edit_free
        )
        row.addWidget(self.customize_button)
        row.addWidget(self.free_button)
        row.addStretch()
        details.addLayout(row)
        layout.addWidget(summary)
        layout.addWidget(
            hub_label(
                t(
                    "widget_hub.mode_edit_hint",
                    "꾸미기는 미리보기에서 적용하거나 취소할 수 있어요. 모드를 실행하지 않고도 설정할 수 있습니다.",
                )
            )
        )
        layout.addStretch()
        actions = QHBoxLayout()
        self.enter_button = hub_button(
            t("widget_hub.enter_mode", "위젯 전용 모드 열기"), self._enter, primary=True
        )
        self.return_button = hub_button(
            t("widget_hub.return_main", "메인 화면으로 돌아가기"), self._return_main
        )
        actions.addWidget(self.enter_button)
        actions.addWidget(self.return_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.refresh()

    def _coordinator(self, *, create=False):
        coordinator = getattr(self.owner, "_widget_mode_coordinator", None)
        ensure = getattr(self.owner, "_ensure_widget_mode_coordinator", None)
        if create and coordinator is None and callable(ensure):
            coordinator = ensure()
        return coordinator

    def refresh(self):
        from calendar_app.presentation.widgets.widget_mode_skins import (
            get_widget_mode_layout,
            get_widget_mode_skin,
            read_widget_mode_layout_id,
            read_widget_mode_skin_id,
            widget_mode_layouts,
            widget_mode_skins,
        )

        settings = getattr(self.owner, "settings", None)
        layout = get_widget_mode_layout(read_widget_mode_layout_id(settings))
        skin = get_widget_mode_skin(read_widget_mode_skin_id(settings))
        free = (
            settings is not None and settings.value("widget_mode_layout_mode", "preset") == "free"
        )
        self.layout_name.setText(
            t("widget_mode.free_layout", "자유 구성")
            if free
            else t(layout.label_key, layout.label_default)
        )
        self.skin_name.setText(
            t("widget_hub.skin_value", "스킨 · {skin}").format(
                skin=t(skin.label_key, skin.label_default)
            )
        )
        self.catalog.setText(
            t(
                "widget_hub.catalog",
                "화면 형태 {layouts}종 · 스킨 {skins}종 · 저장한 자유 구성 지원",
            ).format(layouts=len(widget_mode_layouts()), skins=len(widget_mode_skins()))
        )
        coordinator = self._coordinator()
        active = coordinator is not None and coordinator.is_widget_mode_active()
        visible = active and coordinator.controller.is_visible()
        from calendar_app.presentation.widgets.widget_mode_coordinator import _resume_requested

        resumable = active or (
            coordinator is not None and _resume_requested(settings) and not self.owner.isVisible()
        )
        status = (
            t("widget_hub.mode_running", "실행 중 · 위젯 전용 모드")
            if visible
            else (
                t("widget_hub.mode_tray", "트레이에 숨김 · 다시 열어 이어서 사용하세요")
                if resumable
                else t("widget_hub.mode_closed", "메인 화면 사용 중")
            )
        )
        self.status.setText(status)
        self.enter_button.setText(
            t("widget_hub.reopen_mode", "위젯 전용 모드 다시 보기")
            if resumable
            else t("widget_hub.enter_mode", "위젯 전용 모드 열기")
        )
        self.return_button.setEnabled(bool(resumable))
        available = coordinator is not None or callable(
            getattr(self.owner, "_ensure_widget_mode_coordinator", None)
        )
        for button in (self.enter_button, self.customize_button, self.free_button):
            button.setEnabled(available)

    def _enter(self):
        coordinator = self._coordinator(create=True)
        if coordinator is not None:
            coordinator.enter()
            self.window().show()
            self.window().raise_()
            self.refresh()

    def _return_main(self):
        coordinator = self._coordinator()
        if coordinator is not None:
            coordinator.return_to_main()
            self.refresh()

    def _customize(self):
        from calendar_app.presentation.dialogs.widget_customization_dialog import (
            WidgetCustomizationDialog,
        )

        coordinator = self._coordinator(create=True)
        if coordinator is None:
            return
        controller = coordinator.controller
        controller.ensure_widget()
        dialog = WidgetCustomizationDialog(controller, self.window())
        dialog.exec()
        dialog.deleteLater()
        self.refresh()

    def _edit_free(self):
        from calendar_app.presentation.dialogs.widget_free_layout_editor import (
            WidgetFreeLayoutEditorDialog,
        )

        coordinator = self._coordinator(create=True)
        if coordinator is None:
            return
        controller = coordinator.controller
        controller.ensure_widget()
        dialog = WidgetFreeLayoutEditorDialog(controller, parent=self.window())
        dialog.exec()
        dialog.deleteLater()
        self.refresh()
