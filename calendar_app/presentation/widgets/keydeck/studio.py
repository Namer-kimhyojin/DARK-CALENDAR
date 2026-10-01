# -*- coding: utf-8 -*-
"""KeyDeck Studio — WYSIWYG editor for KeyDeck overlays.

Everything is edited on a private draft; the overlay only changes on 적용.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import time

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.launcher_asset_store import import_launcher_asset
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.keydeck import layout_library
from calendar_app.presentation.widgets.keydeck.canvas import action_summary
from calendar_app.presentation.widgets.keydeck.layout_dialog import (
    LayoutLibraryDialog,
    resolve_request,
)
from calendar_app.presentation.widgets.keydeck.model import (
    CUSTOM_THEME_ID,
    MAX_KEYS_PER_PAGE,
    MAX_PAGES,
    THEMES,
    apply_template_to_page,
    apply_theme,
    copy_key_style,
    default_panorama,
    duplicate_key,
    find_free_slot,
    inherit_style,
    layout_bounds,
    make_key,
    new_id,
    new_page,
    normalize_deck,
    normalize_origin,
    panorama_keys,
    paste_key_style,
    resolve_page_target,
    settle_layout,
    suggest_panorama_fit,
)
from calendar_app.presentation.widgets.keydeck.renderer import render_deck_thumbnail
from calendar_app.presentation.widgets.keydeck.resources import (
    glyph_pixmap,
    has_transparency,
    panorama_image,
)
from calendar_app.presentation.widgets.keydeck.studio_canvas import StudioCanvas
from calendar_app.presentation.widgets.keydeck.studio_inspector import DeckInspector, KeyInspector
from calendar_app.shared.app_lifecycle import is_app_exiting

_UNDO_LIMIT = 80
_CONTENT_FIELDS = frozenset(
    {"label", "sublabel", "action", "hold_action", "mode", "active", "enabled"}
)
_COALESCE_S = 0.9
_SCRIPT_SUFFIXES = frozenset(
    {".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".scr", ".msc"}
)


def _assign(target: dict, path: str, value) -> None:
    parts = path.split(".")
    node = target
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = deepcopy(value)


def _hex_or(value: str, fallback: str) -> str:
    color = QColor(str(value))
    return color.name() if str(value).startswith("#") and color.isValid() else fallback


def _studio_qss(tokens: dict) -> str:
    accent = tokens.get("accent", "#4da6ff")
    border = tokens.get("border", "rgba(127,140,160,0.35)")
    muted = tokens.get("text_muted", "#8a96aa")
    soft_bg = tokens.get("accent_soft_bg", "rgba(77,166,255,0.16)")
    item = tokens.get("surface_item", "rgba(127,140,160,0.10)")
    warning = tokens.get("warning_hex", "#f0a030")
    return f"""
    QLabel#kdTitle {{ font-size: 19px; font-weight: 800; }}
    QLabel#kdSummary {{ font-size: 15px; font-weight: 700; padding: 2px 2px 4px 2px; }}
    QLabel#kdSection {{ font-size: 11px; font-weight: 800; letter-spacing: 0.6px; color: {muted}; padding-top: 10px; }}
    QLabel#kdHint {{ color: {muted}; font-size: 11px; }}
    QLabel#kdWarn {{ color: {warning}; font-size: 11px; }}
    QLabel#kdValue {{ color: {muted}; }}
    QLabel#kdStatus {{ color: {muted}; font-size: 11px; padding: 2px 4px; }}
    QFrame#kdCanvasHost {{
        background: qradialgradient(cx:0.5, cy:0.32, radius:0.95, fx:0.5, fy:0.32,
                                    stop:0 #2b3242, stop:0.7 #161a23, stop:1 #10131a);
        border: 1px solid {border}; border-radius: 16px;
    }}
    QToolButton#kdSeg {{ padding: 6px 8px; border-radius: 8px; border: 1px solid {border}; background: {item}; }}
    QToolButton#kdSeg:hover {{ border: 1px solid {accent}; }}
    QToolButton#kdSeg:checked {{ background: {soft_bg}; border: 1px solid {accent}; font-weight: 700; }}
    QToolButton#kdSeg[tall="true"] {{ min-height: 60px; max-height: 60px; padding: 4px 2px; }}
    QToolButton#kdSwatch {{ border: none; padding: 1px; background: transparent; }}
    QToolButton#kdSwatch:hover {{ background: {soft_bg}; border-radius: 10px; }}
    QToolButton#kdTool {{ padding: 5px 10px; border-radius: 8px; }}
    QToolButton#kdTool:checked {{ background: {soft_bg}; border: 1px solid {accent}; }}
    QTabWidget#kdInspectorTabs QTabBar::tab {{ min-width: 48px; padding: 7px 8px; }}
    QFrame#kdCard {{ background: {item}; border: 1px solid {border}; border-radius: 10px; }}
    QToolButton#kdDisclosure {{ border: none; background: transparent; color: {muted};
                                font-weight: 700; padding: 10px 0 2px 0; }}
    QToolButton#kdTool[preview="true"] {{ background: {accent}; color: #ffffff; font-weight: 700; }}
    QPushButton#kdChoice {{ text-align: left; padding: 9px 14px; min-height: 22px; }}
    QListWidget#kdGallery {{ border: 1px solid {border}; border-radius: 10px; }}
    QListWidget#kdGallery::item:selected {{ background: {soft_bg}; border: 1px solid {accent}; border-radius: 8px; }}
    """


class UnsavedChangesDialog(QDialog):
    """Apply / discard / keep-editing choice with full-width stacked buttons.

    Buttons are stacked vertically so long labels (and longer translations) are never cut.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = "keep"
        apply_dialog_title(
            self, t("widget.launcher.studio.discard_title", "적용하지 않은 변경 사항")
        )
        apply_common_dialog_style(self, minimum_width=380)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        message = QLabel(
            t(
                "widget.launcher.studio.discard",
                "적용하지 않은 변경 사항이 있습니다. 어떻게 할까요?",
            ),
            self,
        )
        message.setWordWrap(True)
        root.addWidget(message)
        root.addSpacing(4)
        self.apply_button = self._choice_button(
            t("widget.launcher.studio.apply_close", "적용하고 닫기"), "primary_btn", "apply"
        )
        self.discard_button = self._choice_button(
            t("widget.launcher.studio.discard_close", "변경 사항 버리기"), "danger_btn", "discard"
        )
        self.keep_button = self._choice_button(
            t("widget.launcher.studio.keep_editing", "계속 편집"), "ghost_btn", "keep"
        )
        for button in (self.apply_button, self.discard_button, self.keep_button):
            root.addWidget(button)
        self.apply_button.setDefault(True)
        self.apply_button.setFocus()

    def _choice_button(self, text: str, object_name: str, choice: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(object_name)
        button.setAutoDefault(False)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setMinimumHeight(36)
        button.clicked.connect(lambda: self._choose(choice))
        return button

    def _choose(self, choice: str) -> None:
        self.choice = choice
        if choice == "keep":
            self.reject()
        else:
            self.accept()

    def reject(self) -> None:  # Esc·창 닫기 = 계속 편집
        self.choice = "keep" if self.choice not in {"apply", "discard"} else self.choice
        super().reject()


class KeyDeckStudioDialog(QDialog):
    """Draft-based KeyDeck editor; call :meth:`result_deck` after acceptance."""

    def __init__(self, deck: dict, parent=None, *, key_id: str = "", execute_callback=None):
        super().__init__(parent)
        self.deck = normalize_deck(deepcopy(deck))
        self._execute_callback = execute_callback
        self._undo: list[tuple[dict, list[str]]] = []
        self._redo: list[tuple[dict, list[str]]] = []
        self._last_tag = ""
        self._last_tag_at = 0.0
        self._dirty = False
        self._preview_toggles: dict[str, bool] = {}
        self._layout_root: Path | None = None  # 테스트에서 라이브러리 위치를 바꿀 때만 사용
        self._style_clipboard: dict | None = None
        self._tokens = get_dialog_theme_tokens()
        self._icon_color = _hex_or(self._tokens.get("text_secondary", ""), "#8a96aa")
        apply_dialog_title(self, t("widget.launcher.studio.title", "KeyDeck 스튜디오"))
        self._base_title = self.windowTitle()
        apply_common_dialog_style(
            self,
            minimum_width=1040,
            size=(1260, 800),
            extra_stylesheet=_studio_qss(self._tokens),
        )
        self._build_ui()
        self._install_shortcuts()
        page_index = self.deck["page"]
        if key_id:
            for index, page in enumerate(self.deck["pages"]):
                if any(key["id"] == key_id for key in page["keys"]):
                    page_index = index
                    break
        self._load_page(page_index, [key_id] if key_id else [])

    # -- construction ------------------------------------------------------------------

    def _glyph_icon(self, glyph: str) -> QIcon:
        pixmap = glyph_pixmap(glyph, self._icon_color, 18, 2.0)
        return QIcon(pixmap) if pixmap is not None else QIcon()

    def _tool(
        self, text: str, glyph: str, slot, tooltip: str = "", checkable: bool = False
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("kdTool")
        button.setText(text)
        button.setIcon(self._glyph_icon(glyph))
        button.setIconSize(QSize(18, 18))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(checkable)
        button.setToolTip(tooltip or text)
        if slot is not None:
            (button.toggled if checkable else button.clicked).connect(slot)
        return button

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(t("widget.launcher.studio.heading", "KeyDeck Studio"), self)
        title.setObjectName("kdTitle")
        subtitle = QLabel(
            t(
                "widget.launcher.studio.subheading",
                "투명 키캡 안에 나만의 아트를 끼우고, 누르는 느낌과 동작까지 설계하세요.",
            ),
            self,
        )
        subtitle.setObjectName("kdHint")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.undo_button = self._tool(
            t("widget.launcher.studio.undo", "실행 취소"), "undo", self.undo, "Ctrl+Z"
        )
        self.redo_button = self._tool(
            t("widget.launcher.studio.redo", "다시 실행"), "redo", self.redo, "Ctrl+Y"
        )
        header.addWidget(self.undo_button)
        header.addWidget(self.redo_button)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.page_tabs = QTabBar(self)
        self.page_tabs.setMovable(True)
        self.page_tabs.setExpanding(False)
        self.page_tabs.setDrawBase(False)
        self.page_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.page_tabs.currentChanged.connect(self._page_tab_changed)
        self.page_tabs.tabMoved.connect(self._page_moved)
        self.page_tabs.tabBarDoubleClicked.connect(self._rename_page)
        self.page_tabs.customContextMenuRequested.connect(self._page_menu)
        self.page_tabs.setUsesScrollButtons(True)
        self.page_tabs.setToolTip(
            t(
                "widget.launcher.studio.page_tabs_tip",
                "더블클릭: 이름 바꾸기 · 오른쪽 클릭: 복제·삭제 · 끌어서 순서 바꾸기",
            )
        )
        toolbar.addWidget(self.page_tabs, 1)
        self.add_page_button = self._tool(
            t("widget.launcher.studio.add_page_short", "새 페이지"),
            "plus",
            self.add_page,
            t(
                "widget.launcher.studio.add_page",
                "페이지 추가 · 탭 더블클릭: 이름 바꾸기 · 탭 오른쪽 클릭: 복제·삭제",
            ),
        )
        toolbar.addWidget(self.add_page_button)
        self.preview_button = self._tool(
            t("widget.launcher.studio.preview_mode", "누르기 체험"),
            "keyboard",
            self._set_preview_mode,
            t(
                "widget.launcher.studio.preview_tip",
                "편집 대신 실제처럼 눌러 보며 소리와 움직임을 확인합니다 (동작은 실행되지 않음).",
            ),
            checkable=True,
        )
        toolbar.addWidget(self.preview_button)
        self.template_button = self._tool(
            t("widget.launcher.studio.templates", "레이아웃"),
            "dashboard",
            lambda: self.open_layout_library(),
            t(
                "widget.launcher.studio.templates_tip",
                "레이아웃 갤러리 (Ctrl+L) · 기본 레이아웃 적용 · 내 레이아웃 저장·불러오기 · 파일로 공유",
            ),
        )
        toolbar.addWidget(self.template_button)
        self.theme_button = self._tool(t("widget.launcher.studio.themes", "테마"), "palette", None)
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        theme_menu = QMenu(self.theme_button)
        theme_menu.aboutToShow.connect(lambda: self._fill_theme_menu(theme_menu))
        self.theme_button.setMenu(theme_menu)
        toolbar.addWidget(self.theme_button)
        self.add_key_button = QPushButton(t("widget.launcher.studio.add_key", "+ 키 추가"), self)
        self.add_key_button.setObjectName("primary_btn")
        self.add_key_button.setAutoDefault(False)
        self.add_key_button.clicked.connect(self.add_key)
        toolbar.addWidget(self.add_key_button)
        self.duplicate_button = self._tool(
            t("widget.launcher.studio.duplicate_short", "복제"),
            "copy",
            self.duplicate_selected,
            t("widget.launcher.studio.duplicate", "복제 (Ctrl+D)"),
        )
        self.delete_button = self._tool(
            t("widget.launcher.studio.delete_short", "삭제"),
            "delete",
            self.delete_selected,
            t("widget.launcher.studio.delete", "삭제 (Delete)"),
        )
        toolbar.addWidget(self.duplicate_button)
        toolbar.addWidget(self.delete_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        host = QFrame(splitter)
        host.setObjectName("kdCanvasHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(8, 8, 8, 8)
        self.canvas = StudioCanvas(host)
        host_layout.addWidget(self.canvas)
        self.canvas.selectionChanged.connect(self._selection_changed)
        self.canvas.editStarted.connect(lambda: self._push_undo(""))
        self.canvas.layoutEdited.connect(self._layout_edited)
        self.canvas.keyDoubleClicked.connect(self._focus_label)
        self.canvas.contextRequested.connect(self._key_menu)
        self.canvas.deleteRequested.connect(self.delete_selected)
        self.canvas.imageDropped.connect(self._image_dropped)
        self.canvas.targetsDropped.connect(self._targets_dropped)
        self.canvas.pageRequested.connect(lambda index: self._load_page(index, []))
        self.canvas.keyActivated.connect(self._preview_key_activated)
        splitter.addWidget(host)
        self.inspector_stack = QStackedWidget(splitter)
        self.inspector_stack.setMinimumWidth(420)
        self.deck_inspector = DeckInspector(self, self.inspector_stack)
        self.key_inspector = KeyInspector(self, self.inspector_stack)
        self.inspector_stack.addWidget(self.deck_inspector)
        self.inspector_stack.addWidget(self.key_inspector)
        splitter.addWidget(self.inspector_stack)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 440])
        root.addWidget(splitter, 1)

        self.status = QLabel(self)
        self.status.setObjectName("kdStatus")
        root.addWidget(self.status)

        footer, self.apply_button, cancel = build_dialog_footer(
            t("common.apply", "적용"), t("common.cancel", "취소")
        )
        self.apply_button.setDefault(False)
        self.apply_button.setToolTip(
            t("widget.launcher.studio.apply_tip", "변경 사항 적용 후 닫기 (Ctrl+S)")
        )
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self.accept)
        if cancel is not None:
            cancel.clicked.connect(self.reject)
        root.addLayout(footer)
        self._update_undo_buttons()

    def _install_shortcuts(self) -> None:
        bindings = (
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
            ("Ctrl+Y", self.redo),
            ("Ctrl+D", self.duplicate_selected),
            (QKeySequence.StandardKey.Copy, self.copy_style),
            (QKeySequence.StandardKey.Paste, self.paste_style),
            ("Ctrl+N", self.add_key),
            ("Ctrl+L", self.open_layout_library),
            ("Ctrl+S", self.accept),
            ("Ctrl+Return", self.accept),
        )
        for sequence, slot in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)

    # -- page handling -----------------------------------------------------------------

    def current_keys(self) -> list[dict]:
        return self.deck["pages"][self.deck["page"]]["keys"]

    def _load_page(self, index: int, selection: list[str] | None = None) -> None:
        self.deck["page"] = max(0, min(int(index), len(self.deck["pages"]) - 1))
        if not self.current_keys():
            # 누를 키가 없는 페이지에서는 체험 모드를 유지할 이유가 없다.
            self._leave_preview()
        self._rebuild_tabs()
        self.canvas.set_deck(self.deck)
        self.canvas.selection = []
        self.canvas.select(selection or [])
        self._selection_changed()

    def _rebuild_tabs(self) -> None:
        self.page_tabs.blockSignals(True)
        while self.page_tabs.count():
            self.page_tabs.removeTab(0)
        for page in self.deck["pages"]:
            self.page_tabs.addTab(page["name"])
        self.page_tabs.setCurrentIndex(self.deck["page"])
        self.page_tabs.blockSignals(False)
        self.add_page_button.setEnabled(len(self.deck["pages"]) < MAX_PAGES)

    def _page_tab_changed(self, index: int) -> None:
        if 0 <= index < len(self.deck["pages"]) and index != self.deck["page"]:
            self._load_page(index, [])

    def _page_moved(self, source: int, target: int) -> None:
        self._push_undo("")
        pages = self.deck["pages"]
        page = pages.pop(source)
        pages.insert(target, page)
        self.deck["page"] = self.page_tabs.currentIndex()
        self._mark_dirty()
        self.canvas.set_deck(self.deck)

    def add_page(self) -> None:
        """Add a page that already holds one key, selected and ready to name."""
        if len(self.deck["pages"]) >= MAX_PAGES:
            return
        self._leave_preview()
        self._push_undo("")
        name = t(
            "widget.launcher.page_default", "페이지 {number}", number=len(self.deck["pages"]) + 1
        )
        page = new_page(str(name))
        current = self.current_keys()
        reference = self.selected_keys()[-1:] or current[:1]
        key = inherit_style(
            make_key(str(t("widget.launcher.new_key", "새 키"))),
            reference[0] if reference else None,
        )
        key["x"], key["y"] = 0.0, 0.0
        page["keys"].append(key)
        self.deck["pages"].append(page)
        self._mark_dirty()
        self._load_page(len(self.deck["pages"]) - 1, [key["id"]])
        self._focus_label(key["id"])

    def _rename_page(self, index: int) -> None:
        if not 0 <= index < len(self.deck["pages"]):
            return
        page = self.deck["pages"][index]
        name, accepted = QInputDialog.getText(
            self,
            t("widget.launcher.studio.rename_page", "페이지 이름"),
            t("widget.launcher.studio.page_name", "이름"),
            text=page["name"],
        )
        name = str(name).strip()[:24]
        if accepted and name and name != page["name"]:
            self._push_undo("")
            page["name"] = name
            self._mark_dirty()
            self._rebuild_tabs()
            self.canvas.refresh()

    def _duplicate_page(self, index: int) -> None:
        if len(self.deck["pages"]) >= MAX_PAGES:
            return
        self._push_undo("")
        source = self.deck["pages"][index]
        copy = deepcopy(source)
        copy["id"] = new_id()
        copy["name"] = str(
            t("widget.launcher.studio.page_copy", "{name} 사본", name=source["name"])
        )[:24]
        copy["keys"] = [duplicate_key(key) for key in source["keys"]]
        self.deck["pages"].insert(index + 1, copy)
        self._mark_dirty()
        self._load_page(index + 1, [])

    def _delete_page(self, index: int) -> None:
        pages = self.deck["pages"]
        if len(pages) <= 1 or not 0 <= index < len(pages):
            return
        if pages[index]["keys"] and self.isVisible():
            answer = QMessageBox.question(
                self,
                t("widget.launcher.studio.delete_page", "페이지 삭제"),
                t(
                    "widget.launcher.studio.delete_page_confirm",
                    "'{name}' 페이지와 키 {count}개를 삭제할까요?",
                    name=pages[index]["name"],
                    count=len(pages[index]["keys"]),
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._push_undo("")
        pages.pop(index)
        self.deck = normalize_deck(self.deck)
        self._mark_dirty()
        self._load_page(max(0, index - 1), [])

    def _page_menu(self, position) -> None:
        index = self.page_tabs.tabAt(position)
        if index < 0:
            return
        menu = QMenu(self)
        menu.addAction(
            t("widget.launcher.studio.rename_page", "페이지 이름"), lambda: self._rename_page(index)
        )
        duplicate = menu.addAction(
            t("widget.launcher.studio.duplicate_page", "페이지 복제"),
            lambda: self._duplicate_page(index),
        )
        duplicate.setEnabled(len(self.deck["pages"]) < MAX_PAGES)
        delete = menu.addAction(
            t("widget.launcher.studio.delete_page", "페이지 삭제"), lambda: self._delete_page(index)
        )
        delete.setEnabled(len(self.deck["pages"]) > 1)
        menu.addSeparator()
        menu.addAction(
            t("widget.launcher.studio.save_page_layout", "내 레이아웃으로 저장…"),
            lambda: self._save_page_layout(index),
        )
        menu.addAction(
            t("widget.launcher.studio.export_page_layout", "레이아웃 파일로 내보내기…"),
            lambda: self._export_page_layout(index),
        )
        menu.exec(self.page_tabs.mapToGlobal(position))

    # -- selection & inspector -----------------------------------------------------------

    def selected_keys(self) -> list[dict]:
        return self.canvas.selected_keys()

    def _selection_changed(self) -> None:
        keys = self.selected_keys()
        if keys:
            self.key_inspector.load(keys)
            self.key_inspector.refresh_material_icons()
            self.inspector_stack.setCurrentWidget(self.key_inspector)
        else:
            self.deck_inspector.load(self.deck)
            self.inspector_stack.setCurrentWidget(self.deck_inspector)
        has_selection = bool(keys)
        self.duplicate_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self._update_status()

    def _reload_inspector(self) -> None:
        keys = self.selected_keys()
        if keys:
            self.key_inspector.load(keys)
        else:
            self.deck_inspector.load(self.deck)
        self._update_status()

    def _update_status(self) -> None:
        keys = self.selected_keys()
        if self.canvas.preview_mode:
            text = t(
                "widget.launcher.studio.status_preview",
                "누르기 체험 중 · 키를 눌러 촉감과 소리를 확인하세요 (동작은 실행되지 않음). "
                "누른 키의 설정이 오른쪽에 열려 바로 바꿔 볼 수 있습니다. 끝내려면 Esc",
            )
        elif not keys:
            text = t(
                "widget.launcher.studio.status_idle",
                "키 {count}개 · 키를 누르면 오른쪽에서 꾸밀 수 있습니다. 앱·파일·링크를 끌어다 놓으면 새 키가 됩니다.",
                count=len(self.current_keys()),
            )
        elif len(keys) == 1:
            key = keys[0]
            text = t(
                "widget.launcher.studio.status_key",
                "'{name}' · {action} · 크기 {size} · 더블클릭: 이름 바꾸기 · 드래그: 옮기기",
                name=key["label"] or t("widget.launcher.unnamed_key", "이름 없는 키"),
                size=f"{key['w']:g}×{key['h']:g}",
                action=action_summary(key["action"], self.deck),
            )
        else:
            text = t(
                "widget.launcher.studio.status_multi",
                "{count}개 키 선택 · 스타일 변경은 선택한 모든 키에 적용됩니다.",
                count=len(keys),
            )
        self.status.setText(str(text))

    def _focus_label(self, key_id: str) -> None:
        self.canvas.select([key_id])
        self.key_inspector.tabs.setCurrentIndex(0)
        self.key_inspector.label_edit.setFocus()
        self.key_inspector.label_edit.selectAll()

    # -- undo / redo ----------------------------------------------------------------------

    def _snapshot(self) -> tuple[dict, list[str]]:
        return (deepcopy(self.deck), list(self.canvas.selection))

    def _push_undo(self, tag: str = "") -> None:
        now = time.monotonic()
        if tag and tag == self._last_tag and now - self._last_tag_at < _COALESCE_S:
            self._last_tag_at = now
            return
        self._undo.append(self._snapshot())
        del self._undo[:-_UNDO_LIMIT]
        self._redo.clear()
        self._last_tag = tag
        self._last_tag_at = now
        self._update_undo_buttons()

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        deck, selection = self._undo.pop()
        self._restore(deck, selection)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        deck, selection = self._redo.pop()
        self._restore(deck, selection)

    def _restore(self, deck: dict, selection: list[str]) -> None:
        self.deck = deck
        self._last_tag = ""
        self._mark_dirty()
        self._load_page(deck["page"], selection)
        self._update_undo_buttons()

    def _update_undo_buttons(self) -> None:
        self.undo_button.setEnabled(bool(self._undo))
        self.redo_button.setEnabled(bool(self._redo))

    def _mark_dirty(self) -> None:
        if not self._dirty:
            unsaved = t("widget.launcher.studio.unsaved", "적용 안 됨")
            self.setWindowTitle(f"{self._base_title} — {unsaved}")
        self._dirty = True

    # -- controller API used by the inspectors ------------------------------------------------

    def set_key_fields(self, values: dict, *, coalesce: str = "") -> None:
        keys = self.selected_keys()
        if not keys:
            return
        self._push_undo(coalesce or ",".join(sorted(values)))
        for key in keys:
            for path, value in values.items():
                _assign(key, path, value)
            if key["mode"] != "toggle":
                key["active"] = False
        if any(path.split(".")[0] not in _CONTENT_FIELDS for path in values):
            self.deck["theme"] = CUSTOM_THEME_ID
        self._mark_dirty()
        self.canvas.refresh({key["id"] for key in keys})
        self.key_inspector.load(keys)
        if any(path.startswith(("cap.", "insert.kind")) for path in values):
            self.key_inspector.refresh_material_icons()
        self._update_status()

    def set_deck_fields(self, values: dict, *, coalesce: str = "") -> None:
        self._push_undo(coalesce or ",".join(sorted(values)))
        for path, value in values.items():
            _assign(self.deck, path, value)
        if any(path.startswith("case.") and path != "case.header" for path in values):
            self.deck["theme"] = CUSTOM_THEME_ID
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()

    def browse_target(self, mode: str) -> str:
        if mode == "folder":
            return QFileDialog.getExistingDirectory(
                self, t("widget.launcher.studio.choose_folder", "폴더 선택")
            )
        path, _selected = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.studio.choose_target", "프로그램 또는 파일 선택"),
            "",
            t(
                "widget.launcher.studio.target_filter",
                "프로그램 및 바로가기 (*.exe *.lnk);;모든 파일 (*.*)",
            ),
        )
        if path and Path(path).suffix.lower() in _SCRIPT_SUFFIXES:
            QMessageBox.warning(
                self,
                t("widget.launcher.studio.script_blocked_title", "실행할 수 없는 파일"),
                t(
                    "widget.launcher.studio.script_blocked",
                    "보안을 위해 스크립트 파일(.bat, .ps1 등)은 키에 연결할 수 없습니다.",
                ),
            )
            return ""
        return path

    def _pick_image_path(self, title: str) -> str:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            t(
                "widget.launcher.studio.image_filter",
                "이미지 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg)",
            ),
        )
        return path

    def _pick_image(self, title: str) -> str:
        path = self._pick_image_path(title)
        return self._import_image(path) if path else ""

    def _import_image(self, path: str) -> str:
        imported = import_launcher_asset(path, "image")
        if not imported:
            QMessageBox.warning(
                self,
                t("widget.launcher.asset_import_failed_title", "파일을 가져올 수 없음"),
                t(
                    "widget.launcher.asset_import_failed",
                    "지원 형식과 25MB 이하의 파일인지 확인해 주세요.",
                ),
            )
        return imported

    def import_image_for_selection(self, path: str = "") -> None:
        if not self.selected_keys():
            self._reload_inspector()
            return
        if path:
            imported = import_launcher_asset(path, "image")
        else:
            imported = self._pick_image(
                t("widget.launcher.studio.choose_image", "이미지 불러오기…")
            )
        if imported:
            self.set_key_fields(
                {
                    "insert.kind": "image",
                    "insert.path": imported,
                    "insert.ox": 0,
                    "insert.oy": 0,
                    "insert.zoom": 100,
                    "insert.rotate": 0,
                }
            )
            self.key_inspector.tabs.setCurrentIndex(1)
        self._reload_inspector()

    def choose_panorama(self, path: str = "") -> bool:
        """Pick (or take a dropped) deck panorama and make it visible right away.

        One undo step covers the new picture and the keys it is applied to: the selected keys,
        or the whole current page when nothing is selected and no key there shows the
        panorama yet (otherwise only the picture is swapped).
        """
        source = path or self._pick_image_path(
            t("widget.launcher.studio.choose_panorama", "파노라마 이미지 선택…")
        )
        imported = self._import_image(source) if source else ""
        image = panorama_image(imported) if imported else None
        if imported and (image is None or image.isNull()):
            QMessageBox.warning(
                self,
                t("widget.launcher.asset_import_failed_title", "파일을 가져올 수 없음"),
                t(
                    "widget.launcher.studio.panorama_unreadable",
                    "이미지를 읽을 수 없습니다. 다른 파일을 선택해 주세요.",
                ),
            )
            imported = ""
        if not imported:
            self._reload_inspector()
            return False
        page = self.deck["page"]
        selected = self.selected_keys()
        if selected:
            targets = selected
        elif panorama_keys(self.deck, page):
            targets = []
        else:
            targets = self.current_keys()
        min_x, min_y, max_x, max_y = layout_bounds(targets or self.current_keys())
        area = (max(max_x - min_x, 1.0), max(max_y - min_y, 1.0))
        self._push_undo("")
        self.deck["panorama"] = {
            **default_panorama(),
            "path": imported,
            "name": Path(source).name,
            "fit": suggest_panorama_fit(
                (image.width(), image.height()), area, transparent=has_transparency(image)
            ),
        }
        for key in targets:
            key["insert"]["kind"] = "panorama"
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()
        if targets:
            self._show_notice(
                t(
                    "widget.launcher.studio.panorama_applied",
                    "파노라마를 키 {count}개에 적용했습니다. 되돌리려면 Ctrl+Z",
                    count=len(targets),
                )
            )
        else:
            self._show_notice(
                t("widget.launcher.studio.panorama_replaced", "파노라마 이미지를 바꿨습니다.")
            )
        return True

    def apply_panorama_to_page(self) -> None:
        keys = self.current_keys()
        if not keys:
            return
        if not self.deck["panorama"]["path"]:
            # 선택 과정에서 이 페이지에 바로 적용된다.
            self.canvas.select([])
            self.choose_panorama("")
            return
        self._push_undo("")
        for key in keys:
            key["insert"]["kind"] = "panorama"
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()
        self._show_notice(
            t(
                "widget.launcher.studio.panorama_applied",
                "파노라마를 키 {count}개에 적용했습니다. 되돌리려면 Ctrl+Z",
                count=len(keys),
            )
        )

    def clear_panorama(self) -> None:
        """Remove the picture; keys that showed it get an empty insert instead of a
        'missing image' placeholder."""
        users = panorama_keys(self.deck)
        if not self.deck["panorama"]["path"] and not users:
            return
        self._push_undo("")
        self.deck["panorama"] = default_panorama()
        for key in users:
            key["insert"]["kind"] = "none"
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()
        self._show_notice(
            t(
                "widget.launcher.studio.panorama_cleared",
                "파노라마를 지웠습니다. 쓰던 키 {count}개의 인서트를 비웠습니다. 되돌리려면 Ctrl+Z",
                count=len(users),
            )
        )

    def _show_notice(self, text: str) -> None:
        """Show a one-off result in the status bar until the next selection change."""
        self.status.setText(str(text))

    def choose_sound(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.studio.choose_sound", "WAV 파일 선택…"),
            "",
            t("widget.launcher.studio.sound_filter", "WAV 오디오 (*.wav)"),
        )
        if path:
            imported = import_launcher_asset(path, "sound")
            if imported:
                self.set_key_fields({"sound": "custom", "sound_path": imported})
            else:
                QMessageBox.warning(
                    self,
                    t("widget.launcher.asset_import_failed_title", "파일을 가져올 수 없음"),
                    t(
                        "widget.launcher.asset_import_failed",
                        "지원 형식과 25MB 이하의 파일인지 확인해 주세요.",
                    ),
                )
        self._reload_inspector()

    def preview_sound(self) -> None:
        """Play one real keystroke (switch sounds follow the physics events)."""
        keys = self.selected_keys()
        if keys:
            self.canvas.press_visual(keys[0]["id"], force_sound=True)

    def test_action(self, which: str) -> None:
        keys = self.selected_keys()
        if len(keys) != 1:
            return
        key = keys[0]
        action = key["hold_action"] if which == "hold_action" else key["action"]
        self.canvas.press_visual(key["id"])
        if action["type"] == "page":
            self._load_page(resolve_page_target(self.deck, action["target"]), [])
            return
        result = self._execute_callback(action) if self._execute_callback is not None else None
        if result is None:
            self.status.setText(
                t("widget.launcher.studio.test_none", "실행할 동작이 아직 없습니다.")
            )
            return
        self.canvas.show_feedback(key["id"], bool(result))
        self.status.setText(
            t(
                "widget.launcher.studio.test_ok",
                "실행했습니다: {action}",
                action=action_summary(action, self.deck),
            )
            if result
            else t(
                "widget.launcher.studio.test_failed",
                "실행하지 못했습니다. 경로나 주소를 확인해 주세요.",
            )
        )

    # -- key operations -------------------------------------------------------------------

    def _columns_hint(self) -> float:
        _min_x, _min_y, max_x, _max_y = layout_bounds(self.current_keys())
        return max(max_x, 4.0)

    def add_key(self) -> None:
        self._leave_preview()
        keys = self.current_keys()
        if len(keys) >= MAX_KEYS_PER_PAGE:
            return
        self._push_undo("")
        selected = self.selected_keys()
        reference = selected[-1] if selected else (keys[-1] if keys else None)
        key = inherit_style(make_key(str(t("widget.launcher.new_key", "새 키"))), reference)
        key["x"], key["y"] = find_free_slot(keys, 1.0, 1.0, columns=self._columns_hint())
        keys.append(key)
        self._mark_dirty()
        self.canvas.refresh()
        self.canvas.select([key["id"]])
        self._focus_label(key["id"])

    def duplicate_selected(self) -> None:
        self._leave_preview()
        keys = self.current_keys()
        selected = self.selected_keys()
        if not selected or len(keys) + len(selected) > MAX_KEYS_PER_PAGE:
            return
        self._push_undo("")
        copies = []
        for source in selected:
            copy = duplicate_key(source)
            copy["x"], copy["y"] = find_free_slot(
                keys,
                copy["w"],
                copy["h"],
                columns=self._columns_hint(),
                near=(source["x"] + source["w"], source["y"]),
            )
            keys.append(copy)
            copies.append(copy["id"])
        self._mark_dirty()
        self.canvas.refresh()
        self.canvas.select(copies)

    def delete_selected(self) -> None:
        self._leave_preview()
        selected = set(self.canvas.selection)
        if not selected:
            return
        self._push_undo("")
        page = self.deck["pages"][self.deck["page"]]
        page["keys"] = [key for key in page["keys"] if key["id"] not in selected]
        self._mark_dirty()
        self.canvas.selection = []
        self.canvas.set_deck(self.deck)
        self._selection_changed()

    def copy_style(self) -> None:
        keys = self.selected_keys()
        if keys:
            self._style_clipboard = copy_key_style(keys[0])
            self.status.setText(
                t(
                    "widget.launcher.studio.style_copied",
                    "스타일을 복사했습니다. 다른 키를 선택하고 Ctrl+V로 붙여넣으세요.",
                )
            )

    def paste_style(self) -> None:
        keys = self.selected_keys()
        if not keys or self._style_clipboard is None:
            return
        self._push_undo("")
        for key in keys:
            paste_key_style(key, self._style_clipboard)
        self._mark_dirty()
        self.canvas.refresh({key["id"] for key in keys})
        self._reload_inspector()
        self.key_inspector.refresh_material_icons()

    def _set_size(self, width: float, height: float) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        self._push_undo("")
        for key in keys:
            key["w"], key["h"] = width, height
        settle_layout(self.current_keys(), {key["id"] for key in keys})
        normalize_origin(self.current_keys())
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()

    def _key_menu(self, key_id: str, global_pos) -> None:
        menu = QMenu(self)
        if key_id:
            menu.addAction(
                t("widget.launcher.studio.duplicate", "복제 (Ctrl+D)"), self.duplicate_selected
            )
            menu.addAction(
                t("widget.launcher.studio.copy_style", "스타일 복사 (Ctrl+C)"), self.copy_style
            )
            paste = menu.addAction(
                t("widget.launcher.studio.paste_style", "스타일 붙여넣기 (Ctrl+V)"),
                self.paste_style,
            )
            paste.setEnabled(self._style_clipboard is not None)
            size_menu = menu.addMenu(t("widget.launcher.studio.key_size", "키 크기"))
            for label, width, height in (
                ("1u", 1.0, 1.0),
                ("1.25u", 1.25, 1.0),
                ("1.5u", 1.5, 1.0),
                ("2u", 2.0, 1.0),
                ("2.25u", 2.25, 1.0),
                ("3u", 3.0, 1.0),
                (t("widget.launcher.studio.tall_2u", "세로 2u"), 1.0, 2.0),
                (t("widget.launcher.studio.big_2x2", "대형 2×2"), 2.0, 2.0),
            ):
                size_menu.addAction(str(label), lambda *_, w=width, h=height: self._set_size(w, h))
            menu.addSeparator()
            menu.addAction(
                t("widget.launcher.studio.delete", "삭제 (Delete)"), self.delete_selected
            )
        else:
            menu.addAction(t("widget.launcher.studio.add_key", "+ 키 추가"), self.add_key)
            paste = menu.addAction(
                t("widget.launcher.studio.paste_style", "스타일 붙여넣기 (Ctrl+V)"),
                self.paste_style,
            )
            paste.setEnabled(False)
        menu.exec(global_pos)

    def _layout_edited(self) -> None:
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()

    def _image_dropped(self, key_id: str, path: str) -> None:
        if key_id not in self.canvas.selection:
            self.canvas.select([key_id])
        self.import_image_for_selection(path)

    def _targets_dropped(self, targets: list) -> None:
        layouts = [
            target
            for kind, target in targets
            if kind == "app" and Path(target).suffix.lower() == layout_library.LAYOUT_SUFFIX
        ]
        if layouts:
            # 레이아웃 파일은 키가 아니라 가져오기 대상이다.
            self.open_layout_library(import_path=layouts[0])
            return
        keys = self.current_keys()
        reference = keys[-1] if keys else None
        added = []
        self._push_undo("")
        for kind, target in targets:
            if len(keys) >= MAX_KEYS_PER_PAGE:
                break
            if kind == "app":
                path = Path(target)
                if not path.exists() or path.suffix.lower() in _SCRIPT_SUFFIXES:
                    continue
                label = path.stem or path.name
            else:
                label = QUrl(target).host() or "Web"
            key = inherit_style(make_key(label, kind, target), reference)
            key["x"], key["y"] = find_free_slot(keys, 1.0, 1.0, columns=self._columns_hint())
            keys.append(key)
            added.append(key["id"])
        if not added:
            self._undo.pop()
            self._update_undo_buttons()
            return
        self._mark_dirty()
        self.canvas.refresh()
        self.canvas.select(added)

    # -- templates & themes -------------------------------------------------------------------

    def open_layout_library(self, import_path: str = "") -> None:
        """Layout gallery: built-in and saved layouts, saving and .keydeck import/export."""
        self._leave_preview()
        dialog = LayoutLibraryDialog(
            self.deck, self, library_root=self._layout_root, import_path=import_path
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.request is not None:
            self._apply_layout_request(dialog.request)

    def _apply_layout_request(self, request: tuple) -> None:
        self._leave_preview()
        deck = resolve_request(self.deck, request)
        self._push_undo("")
        self.deck = deck
        self._mark_dirty()
        self._load_page(self.deck["page"], [])
        self._show_notice(
            t(
                "widget.launcher.layouts.applied",
                "레이아웃을 적용했습니다. 되돌리려면 Ctrl+Z",
            )
        )

    def _save_page_layout(self, index: int) -> None:
        page = self.deck["pages"][index]
        if not page["keys"]:
            self._show_notice(t("widget.launcher.layouts.nothing_to_save", "저장할 키가 없습니다."))
            return
        name, accepted = QInputDialog.getText(
            self,
            t("widget.launcher.layouts.save_title", "레이아웃 저장"),
            t("widget.launcher.layouts.save_name", "레이아웃 이름"),
            text=page["name"],
        )
        if not accepted:
            return
        document, _skipped = layout_library.build_document(
            self.deck, kind="page", name=str(name).strip() or page["name"], page_index=index
        )
        try:
            layout_library.save_to_library(document, self._layout_root)
        except OSError:
            self._show_notice(
                t("widget.launcher.layouts.save_failed", "레이아웃을 저장하지 못했습니다.")
            )
            return
        self._show_notice(
            t(
                "widget.launcher.layouts.saved_hint",
                "'{name}' 레이아웃을 저장했습니다. '레이아웃' 버튼의 내 레이아웃에서 불러올 수 있습니다.",
                name=document["name"],
            )
        )

    def _export_page_layout(self, index: int) -> None:
        page = self.deck["pages"][index]
        if not page["keys"]:
            self._show_notice(t("widget.launcher.layouts.nothing_to_save", "저장할 키가 없습니다."))
            return
        suggested = Path.home() / (
            layout_library.safe_file_stem(page["name"]) + layout_library.LAYOUT_SUFFIX
        )
        path, _selected = QFileDialog.getSaveFileName(
            self,
            t("widget.launcher.layouts.export_title", "레이아웃 파일로 내보내기"),
            str(suggested),
            t("widget.launcher.layouts.export_filter", "KeyDeck 레이아웃 (*.keydeck)"),
        )
        if not path:
            return
        document, _skipped = layout_library.build_document(
            self.deck, kind="page", name=page["name"], page_index=index
        )
        try:
            written = layout_library.write_layout(document, path)
        except OSError:
            self._show_notice(
                t("widget.launcher.layouts.export_failed", "파일을 저장하지 못했습니다.")
            )
            return
        self._show_notice(
            t("widget.launcher.layouts.exported", "내보냈습니다: {path}", path=str(written))
        )

    def _apply_template(self, template_id: str) -> None:
        self._leave_preview()
        if self.current_keys() and self.isVisible():
            answer = QMessageBox.question(
                self,
                t("widget.launcher.template_confirm_title", "레이아웃 바꾸기"),
                t(
                    "widget.launcher.template_confirm",
                    "현재 페이지의 키를 선택한 레이아웃으로 바꿉니다. 계속할까요?",
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._push_undo("")
        apply_template_to_page(self.deck, self.deck["page"], template_id)
        self._mark_dirty()
        self._load_page(self.deck["page"], [])

    def _fill_theme_menu(self, menu: QMenu) -> None:
        menu.clear()
        selection = set(self.canvas.selection)
        for theme in THEMES:
            preview = deepcopy(self.deck)
            apply_theme(preview, theme.theme_id)
            icon = QIcon(render_deck_thumbnail(preview, preview["page"], 88, 56, 2.0))
            action = menu.addAction(
                icon,
                str(t(theme.label_key, theme.label_default)),
                lambda *_, tid=theme.theme_id: self._apply_theme(tid),
            )
            action.setCheckable(True)
            action.setChecked(self.deck["theme"] == theme.theme_id)
        if selection:
            menu.addSeparator()
            scoped = menu.addMenu(t("widget.launcher.studio.theme_selected", "선택한 키에만 적용"))
            for theme in THEMES:
                scoped.addAction(
                    str(t(theme.label_key, theme.label_default)),
                    lambda *_, tid=theme.theme_id: self._apply_theme(tid, selection),
                )
        menu.setStyleSheet("QMenu::item { padding: 6px 18px 6px 8px; } QMenu { icon-size: 88px; }")

    def _apply_theme(self, theme_id: str, key_ids: set[str] | None = None) -> None:
        self._push_undo("")
        if key_ids:
            apply_theme(self.deck, theme_id, page_index=self.deck["page"], key_ids=set(key_ids))
            self.deck["theme"] = "custom"
        else:
            apply_theme(self.deck, theme_id)
        self._mark_dirty()
        self.canvas.refresh()
        self._reload_inspector()
        if self.selected_keys():
            self.key_inspector.refresh_material_icons()

    # -- modes & result -------------------------------------------------------------------------

    def _set_preview_mode(self, enabled: bool) -> None:
        """Try the keys for real without locking the rest of the studio.

        Every tool stays usable: layout edits end the preview first, while style edits (switch,
        sound, material…) apply live to the key that was just pressed so it can be compared
        immediately.  Toggle keys flip while trying and return to their saved state after.
        """
        if enabled and not self.current_keys():
            self.preview_button.blockSignals(True)
            self.preview_button.setChecked(False)
            self.preview_button.blockSignals(False)
            self._show_notice(
                t(
                    "widget.launcher.studio.preview_empty",
                    "이 페이지에는 누를 키가 없습니다. 먼저 키를 추가하세요.",
                )
            )
            return
        if enabled:
            self._preview_toggles = {
                key["id"]: bool(key["active"])
                for page in self.deck["pages"]
                for key in page["keys"]
                if key["mode"] == "toggle"
            }
        else:
            self._restore_preview_toggles()
        self.canvas.set_preview_mode(enabled)
        self.preview_button.setText(
            t("widget.launcher.studio.preview_stop", "체험 끝내기")
            if enabled
            else t("widget.launcher.studio.preview_mode", "누르기 체험")
        )
        self.preview_button.setProperty("preview", "true" if enabled else "false")
        self.preview_button.style().unpolish(self.preview_button)
        self.preview_button.style().polish(self.preview_button)
        self.canvas.select([])
        self._selection_changed()
        self._update_status()

    def _leave_preview(self) -> None:
        if self.canvas.preview_mode:
            self.preview_button.setChecked(False)

    def _restore_preview_toggles(self) -> None:
        saved = self._preview_toggles
        changed = set()
        for page in self.deck["pages"]:
            for key in page["keys"]:
                if key["id"] in saved and key["active"] != saved[key["id"]]:
                    key["active"] = saved[key["id"]]
                    changed.add(key["id"])
        self._preview_toggles = {}
        for key_id in changed:
            self.canvas.sync_key_state(key_id)
        if changed:
            self.canvas.update()

    def _preview_key_activated(self, key_id: str, _which: str) -> None:
        key = next((item for item in self.current_keys() if item["id"] == key_id), None)
        if key is not None and self.canvas.preview_mode and key["mode"] == "toggle":
            # 체험 중 토글은 초안 저장값을 바꾸지 않도록 끝낼 때 되돌린다.
            key["active"] = not key["active"]
            self.canvas.sync_key_state(key_id)
            self.canvas.update()
        self.canvas.show_feedback(key_id, True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self.canvas.preview_mode:
            self._leave_preview()
            event.accept()
            return
        super().keyPressEvent(event)

    def result_deck(self) -> dict:
        return normalize_deck(deepcopy(self.deck))

    def reject(self) -> None:
        # 앱 종료 중에는 묻지 않고 닫는다 — 여기서 닫기를 거부하면 종료가 취소되어 프로세스가 남는다.
        if self._dirty and self.isVisible() and not is_app_exiting():
            choice = self._ask_unsaved_changes()
            if choice == "apply":
                self.accept()
                return
            if choice == "keep":
                return
        super().reject()

    def force_close(self) -> None:
        """Close without prompting (application shutdown)."""
        self._dirty = False
        super().reject()

    def _ask_unsaved_changes(self) -> str:
        dialog = UnsavedChangesDialog(self)
        dialog.exec()
        return dialog.choice


__all__ = ["KeyDeckStudioDialog", "UnsavedChangesDialog"]
