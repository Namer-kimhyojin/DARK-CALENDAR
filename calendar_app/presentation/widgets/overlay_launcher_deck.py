# -*- coding: utf-8 -*-
"""Air KeyDeck overlay — a physically modelled macro pad with transparent keycaps.

The window never takes keyboard focus (like a hardware macro pad), so hotkeys and
text snippets reach the application the user is working in.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import QDialog, QMenu, QMessageBox, QToolTip, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.hotkey_sender import send_hotkey
from calendar_app.infrastructure.runtime.launcher_asset_store import import_launcher_asset
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.keydeck.model import (
    MAX_KEYS_PER_PAGE,
    MAX_PAGES,
    TEMPLATES,
    THEMES,
    apply_template_to_page,
    apply_theme,
    build_template_deck,
    combine_hotkey,
    current_page,
    deck_from_json,
    deck_to_json,
    find_free_slot,
    inherit_style,
    layout_bounds,
    make_key,
    modifier_name,
    new_page,
    normalize_deck,
    resolve_page_target,
)
from calendar_app.presentation.widgets.keydeck.renderer import DeckGeometry
from calendar_app.presentation.widgets.overlay_base import _BaseOverlayWidget, _GripFrame
from calendar_app.shared.app_lifecycle import is_app_exiting
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

logger = logging.getLogger(__name__)

SCRIPT_SUFFIXES = frozenset(
    {".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".scr", ".msc"}
)
_COMMAND_HANDLERS = {
    "new_task": "open_task_dialog",
    "today": "jump_to_today",
    "sync_google": "sync_google_calendar",
    "command_palette": "show_command_palette",
    "focus_mode": "toggle_focus_mode",
    "view_mode": "toggle_view_mode",
    "daily_summary": "open_daily_summary_dialog",
}
_PLACEHOLDER_TARGETS = frozenset({"", "https://", "http://"})
SCALE_STEPS = (75, 90, 100, 115, 130, 150, 175)
_SAVE_DELAY_MS = 400
DATA_KEY = "keydeck_data"
LEGACY_DATA_KEY = "launcher_deck_data"


class OverlayLauncherDeckWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_launcher_deck"
    _DEFAULT_BG_RGBA = "#00000000"
    _DEFAULT_BORDER_RGBA = "#00000000"
    _STYLES = [("default", "KeyDeck")]
    _STYLE_I18N_PREFIX = "widget.launcher"

    def __init__(self, owner):
        self._deck_data: dict | None = None
        self._canvas: KeyDeckCanvas | None = None
        self._studio = None
        super().__init__(owner)
        # 실물 매크로 패드처럼 창이 포커스를 가져가지 않아야 단축키가 작업 중인 앱으로 간다.
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._flush_deck)

    # -- base widget contract ----------------------------------------------------

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 10

    def _build_face(self) -> _GripFrame:
        frame = _GripFrame(self)
        frame.setObjectName("launcherDeckFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        canvas = KeyDeckCanvas(frame)
        layout.addWidget(canvas)
        canvas.keyActivated.connect(self._on_key_activated)
        canvas.editRequested.connect(self._on_edit_requested)
        canvas.closeRequested.connect(self.hide_from_user)
        canvas.pageRequested.connect(self._go_to_page)
        canvas.imageDropped.connect(self._on_image_dropped)
        canvas.targetsDropped.connect(self._on_targets_dropped)
        self._canvas = canvas
        self._deck_data = self._load_deck()
        canvas.set_deck(self._deck_data)
        return frame

    def _apply_appearance(self) -> None:
        self.face.setStyleSheet(
            "QFrame#launcherDeckFace { background: transparent; border: none; }"
        )
        if self.face.layout() is not None:
            self.face.layout().setContentsMargins(0, 0, 0, 0)
        self.setWindowOpacity(self.widget_opacity())
        self._update_grip_color()
        self._update_interaction_surface()

    def _update_grip_color(self) -> None:
        accent = self._deck_data["case"]["accent"] if self._deck_data else "#5ab8ff"
        self.face.setProperty("_grip_color", QColor(accent))
        self.face.update()

    def _update_interaction_surface(self) -> None:
        # 투명한 여백(플로팅 케이스의 키 사이)도 드래그할 수 있게 거의 투명한 채움을 유지한다.
        self.face.setProperty("_interaction_fill_color", QColor(0, 0, 0, 1))
        self.face.update()

    def widget_shape_id(self) -> str:
        return "card"

    def _refresh_face(self) -> None:
        if self._canvas is not None:
            self._canvas.update()

    def _set_runtime_active(self, active: bool) -> None:
        if self._canvas is not None:
            self._canvas.set_runtime_active(active)
        if not active and is_app_exiting():
            self._close_studio_for_exit()

    def closeEvent(self, event) -> None:  # noqa: N802
        # 창이 닫히는 모든 경로(앱 종료의 창 일괄 닫기 포함)에서 저장·정지만 하고 닫기를 거부하지 않는다.
        # 거부하면 Qt 6의 quit()이 취소되어 프로세스가 남는다.
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._flush_deck()
        self._close_studio_for_exit()
        if self._canvas is not None:
            self._canvas.set_runtime_active(False)
        super().closeEvent(event)
        event.accept()

    def _close_studio_for_exit(self) -> None:
        studio = self._studio
        if studio is not None:
            self._studio = None
            studio.force_close()

    def hide_from_user(self) -> None:
        """Close button / menu: hide this deck (it stays registered and can be shown again)."""
        self.set_enabled(False)
        if self._get("hide_hint_shown", False, type_=bool):
            return
        self._set("hide_hint_shown", True)
        notify = getattr(self.owner, "show_toast", None)
        if callable(notify):
            try:
                notify(
                    str(t("widget.launcher.hidden_title", "키덱을 숨겼습니다")),
                    str(
                        t(
                            "widget.launcher.hidden_message",
                            "상단 '위젯' 메뉴나 위젯 관리자에서 다시 켤 수 있습니다.",
                        )
                    ),
                )
            except Exception:
                logger.debug("KeyDeck hide notice could not be shown", exc_info=True)

    def _request_app_exit(self) -> None:
        handler = getattr(self.owner, "request_app_exit", None)
        if callable(handler):
            # 메뉴가 완전히 닫힌 뒤 종료 흐름(확인창 포함)을 시작한다.
            QTimer.singleShot(0, handler)
        else:
            self.hide_from_user()

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def _action_reset_position(self):
        self.center_on_owner()

    def _action_reset_size(self):
        self._set_scale(100)

    def save_position(self):
        super().save_position()
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._flush_deck()

    def apply_initial_settings(self):
        if not self._setting_exists(DATA_KEY):
            self._flush_deck()
        # 줌은 덱 배율로만 표현한다 — 이전 버전의 고정 창 크기는 해제한다.
        self._set("fixed_w", None)
        self._set("fixed_h", None)
        self._apply_and_resize()
        self.restore_position(QPoint(-520, 120))
        if self.is_enabled():
            self._show_with_correct_size()

    # -- resize = zoom ------------------------------------------------------------

    def _fit_font_to_size(self, target_w, target_h, *, live: bool = False):
        canvas = self._canvas
        if canvas is None or self._deck_data is None:
            return
        if live:
            self._release_layout_constraints()
            canvas.set_live_box(QSize(int(target_w), int(target_h)))
            self.resize(int(target_w), int(target_h))
            return
        scale = canvas.fitted_scale(int(target_w), int(target_h))
        canvas.set_live_box(None)
        self._set("fixed_w", None)
        self._set("fixed_h", None)
        self._set_scale(int(round(scale * 100)))

    def _set_scale(self, percent: int) -> None:
        if self._deck_data is None:
            return
        self._deck_data["scale"] = max(60, min(220, int(percent)))
        self._set("fixed_w", None)
        self._set("fixed_h", None)
        self._canvas.refresh()
        self._schedule_save()
        self._fit_window()

    def _fit_window(self) -> None:
        self._release_layout_constraints()
        self._force_resize()
        if self.isVisible():
            self.adjustSize()

    # -- persistence ----------------------------------------------------------------

    def _load_deck(self) -> dict:
        raw = self._get(DATA_KEY, "")
        if raw:
            return deck_from_json(raw)
        legacy = self._get(LEGACY_DATA_KEY, "")
        if legacy:
            # v3 덱은 구 키를 보존한 채 v4로 이관한다 (비파괴).
            deck = deck_from_json(legacy)
            self._set(DATA_KEY, deck_to_json(deck))
            return deck
        return build_template_deck()

    def deck(self) -> dict:
        return self._deck_data

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _flush_deck(self) -> None:
        if self._deck_data is not None:
            self._set(DATA_KEY, deck_to_json(self._deck_data))

    def _fit_scale_to_screen(self, deck: dict) -> None:
        """Shrink the deck scale when a big layout (e.g. a full keyboard) would overflow."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geometry = DeckGeometry(deck)
        factor = min(
            available.width() * 0.96 / max(1, geometry.width),
            available.height() * 0.9 / max(1, geometry.height),
        )
        if factor < 1.0:
            deck["scale"] = max(60, int(deck["scale"] * factor))

    def _apply_deck(self, deck: dict) -> None:
        self._deck_data = normalize_deck(deck)
        self._fit_scale_to_screen(self._deck_data)
        self._save_timer.stop()
        self._flush_deck()
        self._canvas.set_deck(self._deck_data)
        self._apply_appearance()
        self._fit_window()

    # -- input routing ------------------------------------------------------------------

    def eventFilter(self, watched, event):
        canvas = self._canvas
        if canvas is not None and watched is canvas:
            etype = event.type()
            dragging = self._drag_offset is not None or self._resize_origin_global is not None
            if not dragging and etype in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseMove,
            ):
                if canvas.is_pressing():
                    return False
                in_corner = (
                    self._resize_corner_at(
                        self.face.mapFromGlobal(event.globalPosition().toPoint())
                    )
                    is not None
                )
                # 닫기·설정 버튼은 모서리 리사이즈 영역과 겹쳐도 버튼이 우선이다.
                control = canvas.header_control_at(event.position())
                interactive = bool(control) or (
                    not in_corner and canvas.is_interactive_at(event.position())
                )
                if etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
                    if event.button() == Qt.MouseButton.LeftButton and interactive:
                        return False
                elif etype == QEvent.Type.MouseMove and not (
                    event.buttons() & Qt.MouseButton.LeftButton
                ):
                    if interactive:
                        return False
                    canvas.update_hover(QPoint(-10000, -10000))
        return super().eventFilter(watched, event)

    # -- key execution ------------------------------------------------------------------

    def _find_key(self, key_id: str) -> dict | None:
        for page in self._deck_data["pages"]:
            for key in page["keys"]:
                if key["id"] == key_id:
                    return key
        return None

    def _on_key_activated(self, key_id: str, which: str) -> None:
        # 누름 애니메이션이 먼저 시작되도록 실행은 다음 이벤트 루프로 미룬다.
        QTimer.singleShot(0, lambda: self._run_key(key_id, which))

    def _run_key(self, key_id: str, which: str) -> None:
        # 종료 중이거나 숨겨진 뒤 도착한 지연 실행은 버린다 (종료 중 새 창이 뜨는 것 방지).
        if is_app_exiting() or not self.isVisible():
            return
        key = self._find_key(key_id)
        if key is None:
            return
        if which == "tap" and modifier_name(key):
            # 조합키(Shift·Ctrl·Alt·Win)는 바로 보내지 않고 켜 두었다가 다음 키에 붙여 보낸다.
            key["active"] = not key["active"]
            self._canvas.sync_key_state(key_id)
            self._canvas.show_feedback(key_id, True)
            return
        action = key["hold_action"] if which == "hold" else key["action"]
        held = []
        if action.get("type") == "hotkey" and action.get("target"):
            held = [
                item
                for item in current_page(self._deck_data)["keys"]
                if item["id"] != key_id and item["active"] and modifier_name(item)
            ]
            if held:
                action = {
                    **action,
                    "target": combine_hotkey(
                        [modifier_name(item) for item in held], action["target"]
                    ),
                }
        result = self._execute_action(action)
        for item in held:
            # 한 번 쓰인 조합키는 자동으로 풀린다 (고정 키 방식).
            item["active"] = False
            self._canvas.sync_key_state(item["id"])
        if result is None:
            QToolTip.showText(
                QCursor.pos(),
                t(
                    "widget.launcher.unassigned_hint",
                    "아직 동작이 없습니다. 오른쪽 클릭 → 키 편집에서 지정하세요.",
                ),
                self,
            )
            return
        if result and which == "tap" and key["mode"] == "toggle":
            key["active"] = not key["active"]
            self._canvas.sync_key_state(key_id)
            self._schedule_save()
        self._canvas.show_feedback(key_id, bool(result))

    def _execute_action(self, action: dict) -> bool | None:
        """Run an action. ``None`` means the key has nothing to run yet."""
        kind = str(action.get("type", "none"))
        target = str(action.get("target", "") or "")
        if kind == "none":
            return None
        if kind == "command":
            return self._run_command(target)
        if kind == "page":
            self._go_to_page(resolve_page_target(self._deck_data, target))
            return True
        if kind == "text":
            if not target:
                return None
            QGuiApplication.clipboard().setText(target)
            if action.get("paste"):
                QTimer.singleShot(90, lambda: send_hotkey("Ctrl+V"))
            return True
        if kind == "hotkey":
            return bool(send_hotkey(target)) if target else None
        stripped = target.strip()
        if stripped in _PLACEHOLDER_TARGETS:
            return None
        if kind == "url":
            url = QUrl(stripped)
            if url.scheme().lower() not in {"http", "https"} or not url.host():
                return False
            return bool(QDesktopServices.openUrl(url))
        if kind == "app":
            path = Path(stripped)
            if not path.exists() or path.suffix.lower() in SCRIPT_SUFFIXES:
                return False
            return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        return False

    def _run_command(self, command: str) -> bool:
        owner = self.owner
        if command == "widget_manager":
            manager = getattr(owner, "overlay_manager", None)
            handler = getattr(manager, "_open_manager_dialog", None)
        else:
            name = _COMMAND_HANDLERS.get(command)
            handler = getattr(owner, name, None) if name else None
        if not callable(handler):
            return False
        try:
            handler()
        except Exception:
            logger.exception("KeyDeck command %s failed", command)
            return False
        return True

    # -- pages & edits ------------------------------------------------------------------

    def _go_to_page(self, index: int) -> None:
        deck = self._deck_data
        index = max(0, min(int(index), len(deck["pages"]) - 1))
        if index == deck["page"]:
            return
        deck["page"] = index
        self._canvas.set_deck(deck, animate=True)
        self._schedule_save()
        self._fit_window()

    def _add_page(self) -> None:
        deck = self._deck_data
        if len(deck["pages"]) >= MAX_PAGES:
            return
        name = t("widget.launcher.page_default", "페이지 {number}", number=len(deck["pages"]) + 1)
        deck["pages"].append(new_page(str(name)))
        self._go_to_page(len(deck["pages"]) - 1)

    def _on_edit_requested(self, key_id: str) -> None:
        self._open_settings(key_id=key_id)

    def _on_image_dropped(self, key_id: str, path: str) -> None:
        key = self._find_key(key_id)
        if key is None:
            return
        imported = import_launcher_asset(path, "image")
        if not imported:
            QToolTip.showText(
                QCursor.pos(),
                t(
                    "widget.launcher.asset_import_failed",
                    "지원 형식과 25MB 이하의 파일인지 확인해 주세요.",
                ),
                self,
            )
            self._canvas.show_feedback(key_id, False)
            return
        key["insert"].update(
            {"kind": "image", "path": imported, "ox": 0, "oy": 0, "zoom": 100, "rotate": 0}
        )
        self._canvas.refresh({key_id})
        self._schedule_save()
        self._canvas.show_feedback(key_id, True)

    def _on_targets_dropped(self, targets: list) -> None:
        layouts = [
            target
            for kind, target in targets
            if kind == "app" and Path(target).suffix.lower() == ".keydeck"
        ]
        if layouts:
            self._open_layout_library(import_path=layouts[0])
            return
        keys = current_page(self._deck_data)["keys"]
        _min_x, _min_y, max_x, _max_y = layout_bounds(keys)
        columns = max(max_x, 4.0)
        reference = keys[-1] if keys else None
        added = 0
        for kind, target in targets:
            if len(keys) >= MAX_KEYS_PER_PAGE:
                break
            if kind == "app":
                path = Path(target)
                if not path.exists() or path.suffix.lower() in SCRIPT_SUFFIXES:
                    continue
                label = path.stem or path.name
            else:
                label = QUrl(target).host() or "Web"
            key = inherit_style(make_key(label, kind, target), reference)
            key["x"], key["y"] = find_free_slot(keys, 1.0, 1.0, columns=columns)
            keys.append(key)
            added += 1
        if added:
            self._canvas.refresh()
            self._schedule_save()
            self._fit_window()

    def _open_settings(self, initial_tab: int = 0, key_id: str = "") -> None:
        del initial_tab
        from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog

        if is_app_exiting():
            return
        if self._studio is not None:
            self._studio.raise_()
            self._studio.activateWindow()
            return
        self._save_timer.stop()
        self._flush_deck()
        dialog = KeyDeckStudioDialog(
            self._deck_data, self, key_id=key_id, execute_callback=self._execute_action
        )
        self._studio = dialog
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._studio = None
        if accepted and not is_app_exiting():
            self._apply_deck(dialog.result_deck())

    def _apply_template(self, template_id: str) -> None:
        deck = self._deck_data
        page = current_page(deck)
        if page["keys"] and self.isVisible():
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
        apply_template_to_page(deck, int(deck["page"]), template_id)
        self._apply_deck(deck)

    def _open_layout_library(self, import_path: str = "") -> None:
        from calendar_app.presentation.widgets.keydeck.layout_dialog import (
            LayoutLibraryDialog,
            resolve_request,
        )

        if is_app_exiting():
            return
        self._save_timer.stop()
        self._flush_deck()
        dialog = LayoutLibraryDialog(self._deck_data, self, import_path=import_path, can_undo=False)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted and dialog.request is not None and not is_app_exiting():
            self._apply_deck(resolve_request(self._deck_data, dialog.request))

    def _apply_theme(self, theme_id: str) -> None:
        apply_theme(self._deck_data, theme_id)
        self._apply_deck(self._deck_data)

    def _toggle_deck_flag(self, field: str) -> None:
        deck = self._deck_data
        if field == "header":
            deck["case"]["header"] = not deck["case"]["header"]
        else:
            deck[field] = not deck.get(field, True)
        self._apply_deck(deck)

    # -- context menu ---------------------------------------------------------------------

    def _show_context_menu(self, global_pos: QPoint):
        deck = self._deck_data
        style = self._menu_style()
        menu = QMenu(self)
        menu.setStyleSheet(style)
        studio = menu.addAction(
            t("widget.launcher.menu.studio", "KeyDeck 스튜디오 열기..."), self._open_settings
        )
        studio.setIcon(_ic(ICON.EDIT))
        key = self._canvas.key_at(self._canvas.mapFromGlobal(global_pos)) if self._canvas else None
        if key is not None:
            name = key["label"] or t("widget.launcher.unnamed_key", "이름 없는 키")
            menu.addAction(
                t("widget.launcher.menu.edit_key", "'{name}' 키 편집...", name=name),
                lambda *_, kid=key["id"]: self._open_settings(key_id=kid),
            )
        menu.addSeparator()
        pages_menu = menu.addMenu(t("widget.launcher.menu.pages", "페이지"))
        pages_menu.setStyleSheet(style)
        for index, page in enumerate(deck["pages"]):
            action = pages_menu.addAction(page["name"], lambda *_, i=index: self._go_to_page(i))
            action.setCheckable(True)
            action.setChecked(index == deck["page"])
        pages_menu.addSeparator()
        add_page = pages_menu.addAction(
            t("widget.launcher.menu.add_page", "새 페이지 추가"), self._add_page
        )
        add_page.setEnabled(len(deck["pages"]) < MAX_PAGES)
        template_menu = menu.addMenu(t("widget.launcher.menu.templates", "레이아웃"))
        template_menu.setStyleSheet(style)
        gallery = template_menu.addAction(
            t("widget.launcher.menu.layout_gallery", "레이아웃 갤러리 (저장·불러오기·공유)..."),
            self._open_layout_library,
        )
        gallery.setIcon(_ic(ICON.EDIT))
        template_menu.addSeparator()
        for template_id, label_key, fallback, _builder in TEMPLATES:
            template_menu.addAction(
                t(label_key, fallback), lambda *_, tid=template_id: self._apply_template(tid)
            )
        theme_menu = menu.addMenu(t("widget.launcher.menu.themes", "테마"))
        theme_menu.setStyleSheet(style)
        for theme in THEMES:
            action = theme_menu.addAction(
                t(theme.label_key, theme.label_default),
                lambda *_, tid=theme.theme_id: self._apply_theme(tid),
            )
            action.setCheckable(True)
            action.setChecked(deck.get("theme") == theme.theme_id)
        size_menu = menu.addMenu(t("widget.launcher.menu.size", "크기"))
        size_menu.setStyleSheet(style)
        for percent in SCALE_STEPS:
            action = size_menu.addAction(f"{percent}%", lambda *_, p=percent: self._set_scale(p))
            action.setCheckable(True)
            action.setChecked(abs(int(deck["scale"]) - percent) < 3)
        sound = menu.addAction(
            t("widget.launcher.menu.sound", "키 사운드"),
            lambda: self._toggle_deck_flag("sound_enabled"),
        )
        sound.setCheckable(True)
        sound.setChecked(bool(deck.get("sound_enabled", True)))
        header = menu.addAction(
            t("widget.launcher.menu.header", "상단 이름표 표시"),
            lambda: self._toggle_deck_flag("header"),
        )
        header.setCheckable(True)
        header.setChecked(bool(deck["case"]["header"]))
        opacity = menu.addAction(
            t("widget.menu.opacity_settings", "투명도..."), self._action_open_opacity_dialog
        )
        opacity.setIcon(_ic(ICON.OPACITY))
        menu.addSeparator()
        always_on_top = menu.addAction(
            t("widget.menu.always_on_top", "항상 위"), self._toggle_always_on_top
        )
        always_on_top.setIcon(_ic(ICON.ALWAYS_ON_TOP))
        always_on_top.setCheckable(True)
        always_on_top.setChecked(self.always_on_top())
        reset_position = menu.addAction(
            t("widget.menu.reset_position", "위치 초기화"), self._action_reset_position
        )
        reset_position.setIcon(_ic(ICON.RESET_POS))
        reset_size = menu.addAction(
            t("widget.launcher.menu.reset_size", "기본 크기 (100%)"), self._action_reset_size
        )
        reset_size.setIcon(_ic(ICON.RESET_SIZE))
        duplicate_cb = getattr(self, "_overlay_manager_duplicate", None)
        if callable(duplicate_cb):
            duplicate = menu.addAction(t("widget.menu.duplicate", "복제"), duplicate_cb)
            duplicate.setIcon(_ic(ICON.ADD))
        menu.addSeparator()
        hide = menu.addAction(
            t("widget.launcher.menu.hide", "키덱 숨기기 (닫기)"), self.hide_from_user
        )
        hide.setIcon(_ic(ICON.HIDE))
        hide.setToolTip(
            t("widget.launcher.close_tip", "키덱 숨기기 — 상단 '위젯' 메뉴에서 다시 켤 수 있습니다")
        )
        remove_cb = getattr(self, "_overlay_manager_remove", None)
        if callable(remove_cb):
            remove = menu.addAction(t("widget.launcher.menu.delete", "키덱 삭제..."), remove_cb)
            remove.setIcon(_ic(ICON.DELETE))
        if callable(getattr(self.owner, "request_app_exit", None)):
            menu.addSeparator()
            exit_action = menu.addAction(
                t("widget.launcher.menu.exit_app", "Air Calendar 종료..."), self._request_app_exit
            )
            exit_action.setIcon(_ic(ICON.CLOSE))
        menu.setToolTipsVisible(True)
        menu.exec(global_pos)

    def _build_context_menu(self, menu: QMenu):  # pragma: no cover - replaced by _show_context_menu
        del menu


__all__ = ["DATA_KEY", "LEGACY_DATA_KEY", "SCRIPT_SUFFIXES", "OverlayLauncherDeckWidget"]
