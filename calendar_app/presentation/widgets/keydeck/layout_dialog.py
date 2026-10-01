# -*- coding: utf-8 -*-
"""Layout gallery: built-in layouts, the user's saved layouts and ``.keydeck`` sharing.

The dialog never edits a deck itself.  It returns :attr:`LayoutLibraryDialog.request` —
``("template", template_id, mode)`` or ``("layout", document, mode)`` with ``mode`` one of
``"replace"`` (current page), ``"new_page"`` or ``"deck"`` — and the caller applies it with
:func:`resolve_request` (studio: with undo, overlay widget: saved immediately).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.keydeck import layout_library as library
from calendar_app.presentation.widgets.keydeck.model import (
    ACTION_TYPES,
    MAX_PAGES,
    TEMPLATES,
    THEMES,
    apply_template_to_page,
    build_template_deck,
    new_page,
    normalize_deck,
    option_label,
)
from calendar_app.presentation.widgets.keydeck.renderer import render_deck_thumbnail

_THUMB = QSize(168, 104)
_DETAIL = QSize(262, 170)
_TEMPLATE_TAB, _USER_TAB = 0, 1


def _qss(tokens: dict) -> str:
    border = tokens.get("border", "rgba(127,140,160,0.35)")
    muted = tokens.get("text_muted", "#8a96aa")
    accent = tokens.get("accent", "#4da6ff")
    soft_bg = tokens.get("accent_soft_bg", "rgba(77,166,255,0.16)")
    item = tokens.get("surface_item", "rgba(127,140,160,0.10)")
    return f"""
    QLabel#kdTitle {{ font-size: 19px; font-weight: 800; }}
    QLabel#kdSummary {{ font-size: 15px; font-weight: 700; }}
    QLabel#kdHint {{ color: {muted}; font-size: 11px; }}
    QLabel#kdStatus {{ color: {muted}; font-size: 11px; padding: 2px 4px; }}
    QFrame#kdCard {{ background: {item}; border: 1px solid {border}; border-radius: 12px; }}
    QListWidget#kdLayoutGrid {{ border: 1px solid {border}; border-radius: 12px; padding: 6px; }}
    QListWidget#kdLayoutGrid::item {{ border-radius: 10px; padding: 4px; }}
    QListWidget#kdLayoutGrid::item:selected {{ background: {soft_bg}; border: 1px solid {accent}; }}
    """


def error_message(code: str) -> str:
    messages = {
        "unreadable": t(
            "widget.launcher.layouts.error_unreadable",
            "파일을 읽을 수 없습니다. 손상되었거나 KeyDeck 레이아웃 파일이 아닙니다.",
        ),
        "too_large": t(
            "widget.launcher.layouts.error_too_large",
            "파일이 너무 큽니다. 48MB 이하의 레이아웃만 가져올 수 있습니다.",
        ),
        "not_layout": t(
            "widget.launcher.layouts.error_not_layout", "KeyDeck 레이아웃 파일이 아닙니다."
        ),
        "newer_version": t(
            "widget.launcher.layouts.error_newer",
            "더 새로운 버전의 Air Calendar에서 만든 레이아웃입니다. 앱을 업데이트한 뒤 다시 시도하세요.",
        ),
        "empty": t("widget.launcher.layouts.error_empty", "키가 하나도 없는 레이아웃입니다."),
    }
    return str(messages.get(code, messages["unreadable"]))


def resolve_request(deck: dict, request: tuple, *, asset_root: Path | None = None) -> dict:
    """Apply a gallery request to a copy of ``deck`` and return the new deck."""
    source, payload, mode = request
    if source == "template":
        result = normalize_deck(deepcopy(deck))
        if mode == "new_page" and len(result["pages"]) < MAX_PAGES:
            label = next(
                (str(t(key, fallback)) for tid, key, fallback, _b in TEMPLATES if tid == payload),
                str(payload),
            )
            result["pages"].append(new_page(label[:24]))
            result["page"] = len(result["pages"]) - 1
        apply_template_to_page(result, result["page"], str(payload))
        return normalize_deck(result)
    content = library.materialize(payload, asset_root=asset_root)
    return library.apply_content(deck, content, "deck" if content["kind"] == "deck" else mode)


class _ChoiceDialog(QDialog):
    """Small confirmation with full-width stacked buttons (labels never get cut)."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        confirm: str,
        *,
        details: str = "",
        danger: bool = False,
    ):
        super().__init__(parent)
        apply_dialog_title(self, title)
        apply_common_dialog_style(self, minimum_width=420)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        text = QLabel(message, self)
        text.setWordWrap(True)
        root.addWidget(text)
        if details:
            box = QPlainTextEdit(details, self)
            box.setReadOnly(True)
            box.setMaximumHeight(150)
            root.addWidget(box)
        root.addSpacing(4)
        self.confirm_button = QPushButton(confirm, self)
        self.confirm_button.setObjectName("danger_btn" if danger else "primary_btn")
        self.cancel_button = QPushButton(t("common.cancel", "취소"), self)
        self.cancel_button.setObjectName("ghost_btn")
        for button in (self.confirm_button, self.cancel_button):
            button.setAutoDefault(False)
            button.setMinimumHeight(36)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            root.addWidget(button)
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)


class LayoutLibraryDialog(QDialog):
    """Pick a layout to apply, save the current page/deck, and import or export files."""

    def __init__(
        self,
        deck: dict,
        parent=None,
        *,
        library_root: Path | None = None,
        import_path: str = "",
        can_undo: bool = True,
    ):
        super().__init__(parent)
        self.deck = deck
        self.request: tuple | None = None
        self._root = library_root
        self._can_undo = can_undo
        self._documents: dict[str, dict] = {}
        theme_ids = {theme.theme_id for theme in THEMES}
        self._theme_id = deck.get("theme") if deck.get("theme") in theme_ids else "crystal_night"
        apply_dialog_title(self, t("widget.launcher.layouts.title", "레이아웃"))
        apply_common_dialog_style(
            self,
            minimum_width=900,
            size=(1000, 660),
            extra_stylesheet=_qss(get_dialog_theme_tokens()),
        )
        self.setAcceptDrops(True)
        self._build_ui()
        self._show_tab(_TEMPLATE_TAB)
        if import_path:
            QTimer.singleShot(0, lambda: self.import_file(import_path))

    # -- construction ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        title = QLabel(t("widget.launcher.layouts.heading", "레이아웃"), self)
        title.setObjectName("kdTitle")
        hint = QLabel(
            t(
                "widget.launcher.layouts.subheading",
                "기본 레이아웃을 적용하거나, 직접 꾸민 페이지·덱을 저장해 두고 .keydeck 파일로 주고받을 수 있습니다.",
            ),
            self,
        )
        hint.setObjectName("kdHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.tabs = QTabBar(self)
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.addTab(t("widget.launcher.layouts.tab_builtin", "기본 레이아웃"))
        self.tabs.addTab(t("widget.launcher.layouts.tab_mine", "내 레이아웃"))
        self.tabs.currentChanged.connect(self._show_tab)
        bar.addWidget(self.tabs)
        bar.addStretch()
        self.save_page_button = QPushButton(
            t("widget.launcher.layouts.save_page", "현재 페이지 저장…"), self
        )
        self.save_page_button.setToolTip(
            t(
                "widget.launcher.layouts.save_page_tip",
                "지금 페이지의 키 배치·모양·동작을 내 레이아웃에 저장합니다.",
            )
        )
        self.save_page_button.clicked.connect(lambda: self.save_current("page"))
        self.save_deck_button = QPushButton(
            t("widget.launcher.layouts.save_deck", "덱 전체 저장…"), self
        )
        self.save_deck_button.setToolTip(
            t(
                "widget.launcher.layouts.save_deck_tip",
                "모든 페이지와 케이스·크기 설정까지 한 번에 저장합니다.",
            )
        )
        self.save_deck_button.clicked.connect(lambda: self.save_current("deck"))
        self.import_button = QPushButton(
            t("widget.launcher.layouts.import", "파일 가져오기…"), self
        )
        self.import_button.clicked.connect(self._choose_import)
        for button in (self.save_page_button, self.save_deck_button, self.import_button):
            button.setAutoDefault(False)
            bar.addWidget(button)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.stack = QStackedWidget(self)
        self.grid = QListWidget(self)
        self.grid.setObjectName("kdLayoutGrid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setIconSize(_THUMB)
        self.grid.setGridSize(QSize(_THUMB.width() + 28, _THUMB.height() + 58))
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setWordWrap(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(6)
        self.grid.currentItemChanged.connect(lambda *_: self._refresh_detail())
        self.grid.itemDoubleClicked.connect(lambda *_: self._primary())
        self.empty = QLabel(self)
        self.empty.setObjectName("kdHint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setText(
            t(
                "widget.launcher.layouts.empty",
                "아직 저장한 레이아웃이 없습니다.\n'현재 페이지 저장'으로 만들거나, 받은 .keydeck 파일을 가져오거나 여기로 끌어다 놓으세요.",
            )
        )
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, 1)
        body.addWidget(self._build_detail())
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.status = QLabel(self)
        self.status.setObjectName("kdStatus")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        close = QPushButton(t("common.close", "닫기"), self)
        close.setObjectName("ghost_btn")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        root.addLayout(footer)

    def _build_detail(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("kdCard")
        panel.setFixedWidth(_DETAIL.width() + 28)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        self.detail_preview = QLabel(panel)
        self.detail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_preview.setMinimumHeight(_DETAIL.height())
        self.detail_name = QLabel(panel)
        self.detail_name.setObjectName("kdSummary")
        self.detail_name.setWordWrap(True)
        self.detail_meta = QLabel(panel)
        self.detail_meta.setObjectName("kdHint")
        self.detail_meta.setWordWrap(True)
        layout.addWidget(self.detail_preview)
        layout.addWidget(self.detail_name)
        layout.addWidget(self.detail_meta)
        layout.addSpacing(4)
        self.apply_button = self._panel_button(panel, "primary_btn", self._primary)
        self.new_page_button = self._panel_button(
            panel,
            "",
            lambda: self._finish("new_page"),
            t("widget.launcher.layouts.as_new_page", "새 페이지로 추가"),
        )
        layout.addWidget(self.apply_button)
        layout.addWidget(self.new_page_button)
        self.manage_line = QFrame(panel)
        self.manage_line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(self.manage_line)
        self.rename_button = self._panel_button(
            panel, "", self._rename, t("widget.launcher.layouts.rename", "이름 바꾸기")
        )
        self.export_button = self._panel_button(
            panel, "", self._export, t("widget.launcher.layouts.export", "파일로 내보내기…")
        )
        self.delete_button = self._panel_button(
            panel, "danger_btn", self._delete, t("widget.launcher.layouts.delete", "삭제")
        )
        for button in (self.rename_button, self.export_button, self.delete_button):
            layout.addWidget(button)
        layout.addStretch()
        return panel

    @staticmethod
    def _panel_button(parent, object_name: str, slot, text: str = "") -> QPushButton:
        button = QPushButton(text, parent)
        if object_name:
            button.setObjectName(object_name)
        button.setAutoDefault(False)
        button.setMinimumHeight(34)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(slot)
        return button

    # -- listing -----------------------------------------------------------------------

    def _show_tab(self, index: int) -> None:
        if self.tabs.currentIndex() != index:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
        self._reload(select_path="")

    def _reload(self, select_path: str = "") -> None:
        self.grid.clear()
        self._documents.clear()
        user_tab = self.tabs.currentIndex() == _USER_TAB
        if user_tab:
            loaded = library.load_library(self._root)
            for entry, document in loaded:
                self._documents[str(entry.path)] = document
                item = QListWidgetItem(self._thumbnail(library.preview_deck(document)), entry.name)
                item.setData(Qt.ItemDataRole.UserRole, ("user", str(entry.path)))
                item.setToolTip(self._meta_text(document))
                self.grid.addItem(item)
            self.tabs.setTabText(
                _USER_TAB,
                t(
                    "widget.launcher.layouts.tab_mine_count",
                    "내 레이아웃 ({count})",
                    count=len(loaded),
                ),
            )
            self.tabs.updateGeometry()
            self.tabs.adjustSize()
        else:
            folder = library.library_dir(self._root)
            saved = len(list(folder.glob(f"*{library.LAYOUT_SUFFIX}"))) if folder.is_dir() else 0
            self.tabs.setTabText(
                _USER_TAB,
                t("widget.launcher.layouts.tab_mine_count", "내 레이아웃 ({count})", count=saved),
            )
            for template_id, key, fallback, _builder in TEMPLATES:
                preview = build_template_deck(template_id, self._theme_id)
                item = QListWidgetItem(self._thumbnail(preview), str(t(key, fallback)))
                item.setData(Qt.ItemDataRole.UserRole, ("template", template_id))
                self.grid.addItem(item)
        self.stack.setCurrentWidget(self.empty if user_tab and not self.grid.count() else self.grid)
        target = 0
        if select_path:
            for row in range(self.grid.count()):
                if self.grid.item(row).data(Qt.ItemDataRole.UserRole)[1] == select_path:
                    target = row
        if self.grid.count():
            self.grid.setCurrentRow(target)
        self._refresh_detail()

    @staticmethod
    def _thumbnail(deck: dict, size: QSize = _THUMB) -> QIcon:
        pixmap = render_deck_thumbnail(deck, deck.get("page", 0), size.width(), size.height(), 2.0)
        icon = QIcon(pixmap)
        # 선택된 항목도 원래 색 그대로 (목록의 선택 색이 썸네일을 물들이지 않게)
        icon.addPixmap(pixmap, QIcon.Mode.Selected)
        return icon

    def _selection(self) -> tuple[str, str] | None:
        item = self.grid.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected_document(self) -> dict | None:
        selection = self._selection()
        if selection is None or selection[0] != "user":
            return None
        return self._documents.get(selection[1])

    def _meta_text(self, document: dict) -> str:
        keys, pages = library.document_counts(document)
        if document["kind"] == "deck":
            text = t(
                "widget.launcher.layouts.meta_deck",
                "덱 전체 · 페이지 {pages}개 · 키 {keys}개",
                pages=pages,
                keys=keys,
            )
        else:
            text = t(
                "widget.launcher.layouts.meta_page", "페이지 레이아웃 · 키 {keys}개", keys=keys
            )
        created = document.get("created", "")[:10]
        if created:
            text = (
                f"{text} · {t('widget.launcher.layouts.meta_saved', '저장 {date}', date=created)}"
            )
        return str(text)

    def _refresh_detail(self) -> None:
        selection = self._selection()
        has = selection is not None
        user = has and selection[0] == "user"
        document = self._selected_document()
        deck_kind = bool(document and document["kind"] == "deck")
        for widget in (
            self.rename_button,
            self.export_button,
            self.delete_button,
            self.manage_line,
        ):
            widget.setVisible(user)
        self.apply_button.setVisible(has)
        self.new_page_button.setVisible(has and not deck_kind)
        self.new_page_button.setEnabled(len(self.deck["pages"]) < MAX_PAGES)
        if not has:
            self.detail_preview.clear()
            self.detail_name.setText("")
            self.detail_meta.setText(
                t("widget.launcher.layouts.pick_hint", "왼쪽에서 레이아웃을 고르세요.")
            )
            self.apply_button.setText(t("widget.launcher.layouts.apply_page", "현재 페이지에 적용"))
            return
        if user and document is not None:
            preview = library.preview_deck(document)
            name = document["name"]
            meta = self._meta_text(document)
        else:
            template_id = selection[1]
            preview = build_template_deck(template_id, self._theme_id)
            name = self.grid.currentItem().text()
            meta = t(
                "widget.launcher.layouts.meta_builtin",
                "기본 제공 · 키 {keys}개 · 지금 덱의 테마로 꾸며집니다",
                keys=len(preview["pages"][0]["keys"]),
            )
        self.detail_preview.setPixmap(self._thumbnail(preview, _DETAIL).pixmap(_DETAIL))
        self.detail_name.setText(name)
        self.detail_meta.setText(str(meta))
        self.apply_button.setText(
            t("widget.launcher.layouts.apply_deck", "덱 전체를 이 레이아웃으로 바꾸기")
            if deck_kind
            else t("widget.launcher.layouts.apply_page", "현재 페이지에 적용")
        )

    # -- applying ----------------------------------------------------------------------

    def _primary(self) -> None:
        document = self._selected_document()
        self._finish("deck" if document and document["kind"] == "deck" else "replace")

    def _finish(self, mode: str) -> None:
        selection = self._selection()
        if selection is None:
            return
        page_keys = self.deck["pages"][self.deck["page"]]["keys"]
        undo = t(
            "widget.launcher.layouts.undo_hint", " 스튜디오에서는 Ctrl+Z로 되돌릴 수 있습니다."
        )
        if mode == "deck":
            message = t(
                "widget.launcher.layouts.confirm_deck",
                "지금 덱의 모든 페이지가 이 레이아웃으로 바뀝니다. 계속할까요?",
            )
        elif mode == "replace" and page_keys:
            message = t(
                "widget.launcher.layouts.confirm_page",
                "현재 페이지의 키 {count}개가 이 레이아웃으로 바뀝니다. 계속할까요?",
                count=len(page_keys),
            )
        else:
            message = ""
        if message:
            confirm = _ChoiceDialog(
                self,
                t("widget.launcher.layouts.confirm_title", "레이아웃 적용"),
                str(message) + (str(undo) if self._can_undo else ""),
                t("widget.launcher.layouts.confirm_apply", "바꾸기"),
            )
            if confirm.exec() != QDialog.DialogCode.Accepted:
                return
        if selection[0] == "template":
            self.request = (
                "template",
                selection[1],
                "new_page" if mode == "new_page" else "replace",
            )
        else:
            self.request = ("layout", self._documents[selection[1]], mode)
        self.accept()

    # -- saving ------------------------------------------------------------------------

    def save_current(self, kind: str, *, name: str | None = None) -> Path | None:
        """Save the current page (``"page"``) or the whole deck to the user's library."""
        page = self.deck["pages"][self.deck["page"]]
        if kind == "page" and not page["keys"]:
            self._notify(t("widget.launcher.layouts.nothing_to_save", "저장할 키가 없습니다."))
            return None
        if name is None:
            default = page["name"] if kind == "page" else (self.deck["name"] or "KEYDECK")
            name, accepted = QInputDialog.getText(
                self,
                t("widget.launcher.layouts.save_title", "레이아웃 저장"),
                t("widget.launcher.layouts.save_name", "레이아웃 이름"),
                text=default,
            )
            if not accepted:
                return None
        document, skipped = library.build_document(
            self.deck,
            kind=kind,
            name=str(name).strip() or page["name"],
            page_index=self.deck["page"],
        )
        try:
            path = library.save_to_library(document, self._root)
        except OSError:
            QMessageBox.warning(
                self,
                t("widget.launcher.layouts.save_title", "레이아웃 저장"),
                t("widget.launcher.layouts.save_failed", "레이아웃을 저장하지 못했습니다."),
            )
            return None
        self.tabs.setCurrentIndex(_USER_TAB)
        self._reload(select_path=str(path))
        text = t(
            "widget.launcher.layouts.saved",
            "'{name}' 레이아웃을 저장했습니다.",
            name=document["name"],
        )
        if skipped:
            text = f"{text} " + t(
                "widget.launcher.layouts.skipped",
                "파일을 찾을 수 없거나 너무 커서 빠진 그림·소리: {names}",
                names=", ".join(skipped[:4]),
            )
        self._notify(text)
        return path

    # -- import / export ---------------------------------------------------------------

    def _choose_import(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.layouts.import_title", "레이아웃 파일 가져오기"),
            str(Path.home()),
            t("widget.launcher.layouts.file_filter", "KeyDeck 레이아웃 (*.keydeck *.json)"),
        )
        if path:
            self.import_file(path)

    def import_file(self, path: str) -> Path | None:
        """Validate a shared file, show what its keys do, then add it to the library."""
        try:
            document = library.read_layout(path)
        except library.LayoutError as exc:
            QMessageBox.warning(
                self,
                t("widget.launcher.layouts.import_title", "레이아웃 파일 가져오기"),
                error_message(exc.code),
            )
            return None
        if not self._confirm_import(document):
            return None
        try:
            saved = library.save_to_library(document, self._root)
        except OSError:
            QMessageBox.warning(
                self,
                t("widget.launcher.layouts.import_title", "레이아웃 파일 가져오기"),
                t("widget.launcher.layouts.save_failed", "레이아웃을 저장하지 못했습니다."),
            )
            return None
        self.tabs.setCurrentIndex(_USER_TAB)
        self._reload(select_path=str(saved))
        self._notify(
            t(
                "widget.launcher.layouts.imported",
                "'{name}' 레이아웃을 가져왔습니다.",
                name=document["name"],
            )
        )
        return saved

    def _confirm_import(self, document: dict) -> bool:
        summary = library.summarize_actions(document)
        lines = [
            f"• {option_label(ACTION_TYPES, kind)} {count}"
            for kind, count in sorted(summary["counts"].items())
        ]
        details = "\n".join(lines)
        if summary["targets"]:
            details += "\n\n" + str(t("widget.launcher.layouts.targets", "열리는 앱·파일·웹 주소:"))
            details += "\n" + "\n".join(summary["targets"][:12])
            if len(summary["targets"]) > 12:
                details += "\n…"
        message = t(
            "widget.launcher.layouts.import_confirm",
            "'{name}' ({meta})\n\n이 레이아웃의 키를 누르면 아래 동작이 실행됩니다. 믿을 수 있는 곳에서 받은 파일만 가져오세요.",
            name=document["name"],
            meta=self._meta_text(document),
        )
        dialog = _ChoiceDialog(
            self,
            t("widget.launcher.layouts.import_title", "레이아웃 파일 가져오기"),
            str(message),
            t("widget.launcher.layouts.import_go", "가져오기"),
            details=details,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _export(self) -> None:
        document = self._selected_document()
        if document is None:
            return
        suggested = (
            Path.home() / f"{library.safe_file_stem(document['name'])}{library.LAYOUT_SUFFIX}"
        )
        path, _selected = QFileDialog.getSaveFileName(
            self,
            t("widget.launcher.layouts.export_title", "레이아웃 파일로 내보내기"),
            str(suggested),
            t("widget.launcher.layouts.export_filter", "KeyDeck 레이아웃 (*.keydeck)"),
        )
        if not path:
            return
        try:
            written = library.write_layout(document, path)
        except OSError:
            QMessageBox.warning(
                self,
                t("widget.launcher.layouts.export_title", "레이아웃 파일로 내보내기"),
                t("widget.launcher.layouts.export_failed", "파일을 저장하지 못했습니다."),
            )
            return
        self._notify(
            t("widget.launcher.layouts.exported", "내보냈습니다: {path}", path=str(written))
        )

    # -- managing ----------------------------------------------------------------------

    def _rename(self) -> None:
        selection = self._selection()
        document = self._selected_document()
        if selection is None or document is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            t("widget.launcher.layouts.rename", "이름 바꾸기"),
            t("widget.launcher.layouts.save_name", "레이아웃 이름"),
            text=document["name"],
        )
        if not accepted or not str(name).strip():
            return
        try:
            library.rename_layout(selection[1], str(name), self._root)
        except (library.LayoutError, OSError):
            self._notify(
                t("widget.launcher.layouts.save_failed", "레이아웃을 저장하지 못했습니다.")
            )
            return
        self._reload(select_path=selection[1])

    def _delete(self) -> None:
        selection = self._selection()
        document = self._selected_document()
        if selection is None or document is None:
            return
        confirm = _ChoiceDialog(
            self,
            t("widget.launcher.layouts.delete", "삭제"),
            str(
                t(
                    "widget.launcher.layouts.delete_confirm",
                    "'{name}' 레이아웃을 내 레이아웃에서 삭제할까요? 내보낸 파일은 그대로 남습니다.",
                    name=document["name"],
                )
            ),
            t("widget.launcher.layouts.delete", "삭제"),
            danger=True,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return
        library.delete_layout(selection[1], self._root)
        self._reload()

    def _notify(self, text) -> None:
        self.status.setText(str(text))

    # -- drag & drop -------------------------------------------------------------------

    @staticmethod
    def _layout_paths(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [
            url.toLocalFile()
            for url in mime.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in {".keydeck", ".json"}
        ]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._layout_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._layout_paths(event)
        if paths:
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.import_file(paths[0]))


__all__ = ["LayoutLibraryDialog", "error_message", "resolve_request"]
