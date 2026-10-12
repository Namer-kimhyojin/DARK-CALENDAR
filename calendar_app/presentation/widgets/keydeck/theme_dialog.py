# -*- coding: utf-8 -*-
"""A reversible theme gallery with static KeyDeck renderer previews.

Only ``request`` leaves this dialog.  The studio applies that request to its own
draft, with undo; browsing never modifies the caller's deck or runs a key action.
"""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.keydeck.model import (
    CASE_STYLES,
    CUSTOM_THEME_ID,
    MATERIALS,
    PROFILES,
    THEME_CATEGORIES,
    THEMES,
    apply_theme,
    build_template_deck,
    normalize_deck,
    option_label,
)
from calendar_app.presentation.widgets.keydeck.renderer import render_deck_thumbnail
from calendar_app.presentation.widgets.keydeck.studio_inspector import NoWheelComboBox

_THUMB = QSize(168, 104)
_DETAIL = QSize(264, 164)


def _gallery_styles() -> str:
    """Extend, rather than replace, the common dialog's semantic theme."""
    colors = get_dialog_theme_tokens()
    metrics = get_dialog_metric_tokens()
    return f"""
    QLabel#kdThemeTitle {{ font-size: {metrics["title_font_pt"]}px; font-weight: 700; }}
    QLabel#kdThemeName {{ font-size: {metrics["subtitle_font_pt"]}px; font-weight: 700; }}
    QLabel#kdThemeHint {{ color: {colors["text_muted"]}; }}
    QFrame#kdThemeDetail {{
        background: {colors["surface_item"]}; border: 1px solid {colors["border"]};
        border-radius: {metrics["group_radius"]}px;
    }}
    QListWidget#kdThemeGrid {{
        border: 1px solid {colors["border"]}; border-radius: {metrics["list_radius"]}px;
        padding: 4px;
    }}
    QListWidget#kdThemeGrid::item {{
        border: 1px solid transparent;
        border-radius: {metrics["list_item_radius"]}px; padding: 3px;
    }}
    QListWidget#kdThemeGrid::item:selected {{
        background: {colors["list_selected_bg"]};
        border-color: {colors["list_selected_border"]}; color: {colors["list_selected_text"]};
    }}
    """


class ThemeGalleryDialog(QDialog):
    """Choose a theme and an explicit scope without editing the input deck."""

    def __init__(self, deck: dict, parent=None, *, key_ids: set[str] | None = None):
        super().__init__(parent)
        self.request: tuple[str, str] | None = None
        self._draft = normalize_deck(deepcopy(deck))
        self._themes = {theme.theme_id: theme for theme in THEMES}
        self._opening_theme_id = str(deck.get("theme", ""))
        self._preferred_theme_id = (
            self._opening_theme_id if self._opening_theme_id in self._themes else THEMES[0].theme_id
        )
        page_keys = self._draft["pages"][self._draft["page"]]["keys"]
        self._key_ids = {key["id"] for key in page_keys} & set(key_ids or ())
        self._thumb_cache: dict[str, QIcon] = {}
        self._preview_signature: tuple[str, str] | None = None
        self.preview_deck: dict | None = None
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._render_visible_thumbnail)

        apply_dialog_title(self, t("widget.launcher.themes.title", "테마 갤러리"))
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(1000, available.width() - 32) if available else 1000
        height = min(680, available.height() - 48) if available else 680
        apply_common_dialog_style(
            self,
            minimum_width=min(900, width),
            size=(width, height),
            extra_stylesheet=_gallery_styles(),
        )
        self._build_ui()
        self._reload()
        self.search_edit.setFocus()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        heading = QLabel(t("widget.launcher.themes.heading", "키덱에 어울리는 테마 찾기"), self)
        heading.setObjectName("kdThemeTitle")
        heading.setWordWrap(True)
        root.addWidget(heading)
        hint = QLabel(
            t(
                "widget.launcher.themes.hint",
                "테마를 선택하면 현재 키 배치로 미리 볼 수 있습니다. 적용 전까지 덱은 바뀌지 않습니다.",
            ),
            self,
        )
        hint.setObjectName("kdThemeHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setClearButtonEnabled(True)
        search_label = str(t("widget.launcher.themes.search", "테마 이름·분위기 검색"))
        self.search_edit.setPlaceholderText(search_label)
        self.search_edit.setAccessibleName(search_label)
        self.search_edit.textChanged.connect(self._reload)
        self.search_edit.returnPressed.connect(lambda: self.grid.setFocus())
        filters.addWidget(self.search_edit, 1)
        self.category_combo = NoWheelComboBox(self)
        self.category_combo.setAccessibleName(t("widget.launcher.themes.category", "테마 분류"))
        self.category_combo.addItem(t("widget.launcher.themes.all", "모든 테마"), "")
        for category_id, key, fallback in THEME_CATEGORIES:
            self.category_combo.addItem(str(t(key, fallback)), category_id)
        self.category_combo.currentIndexChanged.connect(self._reload)
        filters.addWidget(self.category_combo)
        root.addLayout(filters)

        context = QHBoxLayout()
        self.current_theme_label = QLabel(self)
        self.current_theme_label.setObjectName("kdThemeHint")
        self.current_theme_label.setWordWrap(True)
        current = self._themes.get(self._opening_theme_id)
        current_name = (
            str(t(current.label_key, current.label_default))
            if current
            else str(t("widget.launcher.themes.custom", "사용자 지정"))
        )
        self.current_theme_label.setText(
            t("widget.launcher.themes.current", "현재 테마: {name}", name=current_name)
        )
        context.addWidget(self.current_theme_label, 1)
        self.result_count = QLabel(self)
        self.result_count.setObjectName("kdThemeHint")
        context.addWidget(self.result_count)
        root.addLayout(context)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.stack = QStackedWidget(self)
        self.grid = QListWidget(self)
        self.grid.setObjectName("kdThemeGrid")
        self.grid.setAccessibleName(t("widget.launcher.themes.list", "테마 목록"))
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setIconSize(_THUMB)
        self.grid.setGridSize(QSize(176, 148))
        self.grid.setSpacing(0)
        self.grid.setWordWrap(False)
        self.grid.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.currentItemChanged.connect(lambda *_: self._refresh_detail())
        # Double-click remains a preview gesture: applying is always explicit.
        self.grid.itemDoubleClicked.connect(lambda *_: self._refresh_detail())
        self.grid.verticalScrollBar().valueChanged.connect(self._schedule_thumbnails)
        self.stack.addWidget(self.grid)
        self.empty = QLabel(
            t(
                "widget.launcher.themes.empty",
                "검색 결과가 없습니다. 검색어를 바꾸거나 모든 테마를 선택하세요.",
            ),
            self,
        )
        self.empty.setObjectName("kdThemeHint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setAccessibleName(self.empty.text())
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, 1)
        body.addWidget(self._build_detail())
        root.addLayout(body, 1)

        preservation = QLabel(
            t(
                "widget.launcher.themes.preserve",
                "키 배치·이름·동작·내 이미지는 유지됩니다. Ctrl+Z로 적용을 되돌릴 수 있습니다.",
            ),
            self,
        )
        preservation.setObjectName("kdThemeHint")
        preservation.setWordWrap(True)
        root.addWidget(preservation)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(separator)
        self.status = QLabel(self)
        self.status.setObjectName("kdThemeHint")
        self.status.setWordWrap(True)
        footer, self.apply_button, cancel = build_dialog_footer(
            t("widget.launcher.themes.apply", "테마 적용"),
            t("common.cancel", "취소"),
            extra_left_widget=self.status,
        )
        # Enter in search changes focus, rather than accepting a theme accidentally.
        self.apply_button.setDefault(False)
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)

    def _build_detail(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("kdThemeDetail")
        panel.setFixedWidth(292)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        preview_heading = QLabel(t("widget.launcher.themes.preview", "현재 페이지 미리보기"), panel)
        preview_heading.setObjectName("kdThemeHint")
        preview_heading.setWordWrap(True)
        layout.addWidget(preview_heading)
        self.detail_preview = QLabel(panel)
        self.detail_preview.setFixedSize(_DETAIL)
        self.detail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_preview.setAccessibleName(preview_heading.text())
        layout.addWidget(self.detail_preview)
        self.detail_name = QLabel(panel)
        self.detail_name.setObjectName("kdThemeName")
        self.detail_name.setWordWrap(True)
        self.detail_name.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.detail_name)
        self.detail_description = QLabel(panel)
        self.detail_description.setWordWrap(True)
        self.detail_description.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.detail_description)
        self.detail_meta = QLabel(panel)
        self.detail_meta.setObjectName("kdThemeHint")
        self.detail_meta.setWordWrap(True)
        layout.addWidget(self.detail_meta)
        layout.addSpacing(2)
        scope_label = QLabel(t("widget.launcher.themes.scope", "적용 범위"), panel)
        layout.addWidget(scope_label)
        self.scope_combo = NoWheelComboBox(panel)
        self.scope_combo.setAccessibleName(scope_label.text())
        self.scope_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scope_combo.addItem(t("widget.launcher.themes.scope_deck", "덱 전체"), "deck")
        self.scope_combo.addItem(t("widget.launcher.themes.scope_page", "현재 페이지"), "page")
        self.scope_combo.addItem(
            t(
                "widget.launcher.themes.scope_selection",
                "선택한 키 ({count}개)",
                count=len(self._key_ids),
            ),
            "selection",
        )
        selection_item = self.scope_combo.model().item(2)
        selection_item.setEnabled(bool(self._key_ids))
        if not self._key_ids:
            selection_item.setToolTip(
                t("widget.launcher.themes.select_keys", "현재 페이지의 키를 먼저 선택하세요.")
            )
        self.scope_combo.currentIndexChanged.connect(self._scope_changed)
        scope_label.setBuddy(self.scope_combo)
        layout.addWidget(self.scope_combo)
        self.preview_note = QLabel(panel)
        self.preview_note.setObjectName("kdThemeHint")
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)
        layout.addStretch()
        return panel

    def selected_theme_id(self) -> str | None:
        item = self.grid.currentItem()
        theme_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return str(theme_id) if theme_id in self._themes else None

    def _reload(self, *_args) -> None:
        self._thumb_timer.stop()
        category = str(self.category_combo.currentData() or "")
        words = self.search_edit.text().strip().casefold().split()
        self.grid.blockSignals(True)
        self.grid.clear()
        target = 0
        for theme in THEMES:
            searchable = " ".join(
                (
                    theme.theme_id,
                    str(t(theme.label_key, theme.label_default)),
                    theme.label_default,
                    theme.category,
                    option_label(THEME_CATEGORIES, theme.category),
                    str(t(theme.description_key, theme.description_default)),
                    theme.description_default,
                )
            ).casefold()
            if category and theme.category != category:
                continue
            if not all(word in searchable for word in words):
                continue
            name = str(t(theme.label_key, theme.label_default))
            if theme.theme_id == self._opening_theme_id:
                name = f"✓ {name}"
            item = QListWidgetItem(self._thumb_cache.get(theme.theme_id, QIcon()), name)
            # Uniform icon views otherwise cache the empty initial icon's text-
            # only height before the deferred thumbnail arrives, clipping cards.
            item.setSizeHint(QSize(176, 148))
            item.setData(Qt.ItemDataRole.UserRole, theme.theme_id)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, name)
            item.setToolTip(f"{name}\n{t(theme.description_key, theme.description_default)}")
            self.grid.addItem(item)
            if theme.theme_id == self._preferred_theme_id:
                target = self.grid.count() - 1
        if self.grid.count():
            self.grid.setCurrentRow(target)
        self.grid.blockSignals(False)
        self.stack.setCurrentWidget(self.grid if self.grid.count() else self.empty)
        self.result_count.setText(
            t(
                "widget.launcher.themes.count",
                "{shown} / {total}개 테마",
                shown=self.grid.count(),
                total=len(THEMES),
            )
        )
        self._refresh_detail()
        self._schedule_thumbnails()

    def _scope_changed(self, *_args) -> None:
        if self.scope_combo.currentData() == "selection" and not self._key_ids:
            self.scope_combo.setCurrentIndex(0)
            return
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        theme_id = self.selected_theme_id()
        self.apply_button.setEnabled(theme_id is not None)
        if theme_id is None:
            self._preview_signature = None
            self.preview_deck = None
            for label in (
                self.detail_preview,
                self.detail_name,
                self.detail_description,
                self.detail_meta,
                self.preview_note,
                self.status,
            ):
                label.clear()
            self.preview_note.setVisible(False)
            return
        self._preferred_theme_id = theme_id
        scope = str(self.scope_combo.currentData())
        if self._preview_signature == (theme_id, scope):
            return
        self._preview_signature = (theme_id, scope)
        theme = self._themes[theme_id]
        self.detail_name.setText(str(t(theme.label_key, theme.label_default)))
        self.detail_description.setText(str(t(theme.description_key, theme.description_default)))
        category = option_label(THEME_CATEGORIES, theme.category)
        material = option_label(MATERIALS, theme.material)
        profile = option_label(PROFILES, theme.profile)
        case_style = option_label(
            CASE_STYLES,
            theme.case_style if scope == "deck" else self._draft["case"]["style"],
        )
        self.detail_meta.setText(f"{category} · {material}\n{profile} · {case_style}")
        preview = deepcopy(self._draft)
        page_index = preview["page"]
        apply_theme(
            preview,
            theme_id,
            page_index=None if scope == "deck" else page_index,
            key_ids=self._key_ids if scope == "selection" else None,
            keep_art=True,
        )
        if scope != "deck":
            preview["theme"] = CUSTOM_THEME_ID
        self.preview_deck = preview
        empty_page = not preview["pages"][page_index]["keys"]
        self.preview_note.setVisible(empty_page)
        if empty_page:
            rendered = build_template_deck("macro_3x3", theme_id)
            rendered["case"] = deepcopy(preview["case"])
            self.preview_note.setText(
                t(
                    "widget.launcher.themes.empty_preview",
                    "현재 페이지가 비어 있어 예시 배치로 표시합니다. 예시 키는 추가되지 않습니다.",
                )
            )
        else:
            rendered = preview
            self.preview_note.clear()
        self.detail_preview.setPixmap(
            render_deck_thumbnail(
                rendered, rendered["page"], _DETAIL.width(), _DETAIL.height(), 2.0
            )
        )
        affected = (
            sum(len(page["keys"]) for page in self._draft["pages"])
            if scope == "deck"
            else len(self._key_ids)
            if scope == "selection"
            else len(self._draft["pages"][page_index]["keys"])
        )
        self.status.setText(
            t("widget.launcher.themes.affected", "키 {count}개에 적용", count=affected)
        )

    def _schedule_thumbnails(self, *_args) -> None:
        if self.isVisible() and not self._thumb_timer.isActive():
            self._thumb_timer.start(0)

    def _render_visible_thumbnail(self) -> None:
        if not self.isVisible():
            return
        viewport = self.grid.viewport().rect()
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            theme_id = str(item.data(Qt.ItemDataRole.UserRole))
            if theme_id in self._thumb_cache:
                continue
            if not self.grid.visualItemRect(item).intersects(viewport):
                continue
            # Small representative keys keep gallery browsing cheap even for a
            # 112-key layout.  The persistent detail uses the real current page.
            sample = build_template_deck("macro_3x3", theme_id)
            pixmap = render_deck_thumbnail(
                sample, sample["page"], _THUMB.width(), _THUMB.height(), 2.0
            )
            icon = QIcon(pixmap)
            icon.addPixmap(pixmap, QIcon.Mode.Selected)
            self._thumb_cache[theme_id] = icon
            item.setIcon(icon)
            # One item per event-loop turn leaves search and cancellation usable.
            self._thumb_timer.start(0)
            return

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_thumbnails()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            self._schedule_thumbnails()

    def done(self, result: int) -> None:
        self._thumb_timer.stop()
        super().done(result)

    def _apply(self) -> None:
        theme_id = self.selected_theme_id()
        scope = str(self.scope_combo.currentData())
        if theme_id is None or (scope == "selection" and not self._key_ids):
            return
        self.request = (theme_id, scope)
        self.accept()


__all__ = ["ThemeGalleryDialog"]
