"""Layout preset manager for save/load/delete flows."""

from __future__ import annotations

from datetime import datetime
import json

from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.theme_settings import opacity_percent_to_byte


class PresetManager:
    SETTINGS_KEY = "layout_presets_v1"
    DEFAULT_PRESET_KEY = "__default_preset__"
    DOCK_NAMES = ("left_dock", "center_dock", "routine_dock", "directive_dock")

    def __init__(self, app):
        self.app = app

    def update_load_menu(self):
        menu = getattr(self.app, "preset_load_menu", None)
        if menu is None:
            return

        menu.clear()
        menu.addAction(t("layout.default_name"), self.load_default_preset)
        menu.addSeparator()

        presets = self._read_presets()
        history_presets = self._list_history_presets(presets)
        if not history_presets:
            action = menu.addAction(t("layout.none_saved"))
            action.setEnabled(False)
            return

        for name in sorted(history_presets.keys()):
            menu.addAction(name, lambda _checked=False, n=name: self._load_preset(n))

    def update_save_menu(self):
        menu = getattr(self.app, "preset_save_menu", None)
        if menu is None:
            return

        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            LAYOUT_PRESET_DEFS,
        )

        builtin_names = {name for name, _ in LAYOUT_PRESET_DEFS}

        presets = self._read_presets()

        menu.clear()
        menu.addAction(t("layout.save_default"), self.save_default_preset)
        menu.addSeparator()
        menu.addAction(t("layout.save_new"), self._save_with_prompt)

        # ── 단축키 프리셋 슬롯 저장 ──────────────────────────────────
        menu.addSeparator()
        for name, shortcut in LAYOUT_PRESET_DEFS:
            saved_mark = " *" if name in presets else ""
            act = menu.addAction(
                f"{name} ({shortcut}){saved_mark}",
                lambda _checked=False, n=name: self._save_named(n, overwrite=True),
            )
            act.setIcon(_ic(ICON.PRESET))

        # ── 기타 사용자 프리셋 덮어쓰기 ─────────────────────────────
        user_presets = {
            k: v for k, v in self._list_user_presets(presets).items() if k not in builtin_names
        }
        if not user_presets:
            return

        menu.addSeparator()
        for name in sorted(user_presets.keys()):
            menu.addAction(
                t("layout.overwrite", name=name),
                lambda _checked=False, n=name: self._save_named(n, overwrite=True),
            )

    def update_rename_menu(self):
        menu = getattr(self.app, "preset_rename_menu", None)
        if menu is None:
            return

        menu.clear()
        presets = self._read_presets()
        user_presets = self._list_user_presets(presets)

        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            LAYOUT_PRESET_DEFS,
        )

        builtin_names = {row[0] for row in LAYOUT_PRESET_DEFS}

        # ── 단축키 프리셋 (항상 표시) ──────────────────────────────────
        for name, shortcut in LAYOUT_PRESET_DEFS:
            act = menu.addAction(
                f"{name} ({shortcut})", lambda _checked=False, n=name: self._rename_named(n)
            )
            act.setIcon(_ic(ICON.PRESET))

        # ── 기타 사용자 프리셋 ──────────────────────────────────────
        other_presets = {k: v for k, v in user_presets.items() if k not in builtin_names}
        if other_presets:
            menu.addSeparator()
            for name in sorted(other_presets.keys()):
                menu.addAction(name, lambda _checked=False, n=name: self._rename_named(n))

        if not user_presets and not LAYOUT_PRESET_DEFS:
            action = menu.addAction(t("layout.rename_none"))
            action.setEnabled(False)

    def update_delete_menu(self):
        menu = getattr(self.app, "preset_delete_menu", None)
        if menu is None:
            return

        menu.clear()
        presets = self._read_presets()
        user_presets = self._list_user_presets(presets)
        if not user_presets:
            action = menu.addAction(t("layout.delete_none"))
            action.setEnabled(False)
            return

        for name in sorted(user_presets.keys()):
            menu.addAction(name, lambda _checked=False, n=name: self._delete_named(n))

    def load_default_preset(self):
        presets = self._read_presets()
        payload = presets.get(self.DEFAULT_PRESET_KEY)
        if isinstance(payload, dict) and self._apply_payload(payload):
            if hasattr(self.app, "show_toast"):
                self.app.show_toast(t("layout.default_name"), t("layout.default_applied"))
            return
        self._apply_builtin_default_layout()

    def save_default_preset(self):
        presets = self._read_presets()
        presets[self.DEFAULT_PRESET_KEY] = self._capture_current_layout()
        self._write_presets(presets)
        if hasattr(self.app, "show_toast"):
            self.app.show_toast(t("layout.default_name"), t("layout.default_saved"))

    def _save_with_prompt(self):
        name, ok = QInputDialog.getText(self.app, t("layout.save_title"), t("layout.enter_name"))
        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self.app, t("layout.save_title"), t("layout.name_required"))
            return

        self._save_named(name, overwrite=False)

    def _save_named(self, name: str, overwrite: bool):
        presets = self._read_presets()
        if name in presets and not overwrite:
            answer = QMessageBox.question(
                self.app,
                t("layout.save_title"),
                t("layout.exists_overwrite", name=name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        presets[name] = self._capture_current_layout()
        self._write_presets(presets)

        if hasattr(self.app, "show_toast"):
            self.app.show_toast(t("layout.save_title"), t("layout.save_success", name=name))

    def _rename_named(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self.app, t("layout.rename_title"), t("layout.enter_new_name"), text=old_name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self.app, t("layout.rename_title"), t("layout.name_required"))
            return

        if new_name == old_name:
            return

        presets = self._read_presets()

        # Handle built-in slot renaming
        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            LAYOUT_PRESET_DEFS,
            save_custom_preset_names,
        )

        builtin_idx = -1
        for i, row in enumerate(LAYOUT_PRESET_DEFS):
            if row[0] == old_name:
                builtin_idx = i
                break

        if builtin_idx >= 0:
            LAYOUT_PRESET_DEFS[builtin_idx][0] = new_name
            save_custom_preset_names()
            # If there was a custom layout saved under the old name, move it to the new name
            if old_name in presets:
                presets[new_name] = presets.pop(old_name)
                self._write_presets(presets)

            if hasattr(self.app, "refresh_layout_preset_labels"):
                self.app.refresh_layout_preset_labels()
        else:
            # Normal user preset rename
            if old_name not in presets:
                return
            if new_name in presets:
                answer = QMessageBox.question(
                    self.app,
                    t("layout.rename_title"),
                    t("layout.exists_overwrite", name=new_name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            presets[new_name] = presets.pop(old_name)
            self._write_presets(presets)

        if hasattr(self.app, "show_toast"):
            self.app.show_toast(
                t("layout.rename_title"), t("layout.rename_success", old=old_name, new=new_name)
            )

    def _delete_named(self, name: str):
        presets = self._read_presets()
        if name not in presets:
            return

        answer = QMessageBox.question(
            self.app,
            t("layout.delete_title"),
            t("layout.delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        presets.pop(name, None)
        self._write_presets(presets)

        if hasattr(self.app, "show_toast"):
            self.app.show_toast(t("layout.delete_title"), t("layout.delete_success", name=name))

    def _load_preset(self, name: str):
        presets = self._read_presets()
        payload = presets.get(name)
        if not isinstance(payload, dict):
            QMessageBox.warning(self.app, t("layout.load_title"), t("layout.not_found", name=name))
            return

        if not self._apply_payload(payload):
            QMessageBox.warning(
                self.app,
                t("layout.load_title"),
                t("layout.restore_failed", name=name),
            )
            self._apply_builtin_default_layout()
            return

        if hasattr(self.app, "show_toast"):
            self.app.show_toast(t("layout.load_title"), t("layout.save_success", name=name))

    def _apply_builtin_default_layout(self):
        if hasattr(self.app, "set_column_layout"):
            self.app.set_column_layout(4)

        for dock_name in self.DOCK_NAMES:
            dock = getattr(self.app, dock_name, None)
            if dock is not None:
                if dock.isFloating():
                    dock.setFloating(False)
                dock.show()

        if hasattr(self.app, "sync_panel_menu_state"):
            self.app.sync_panel_menu_state()
        if hasattr(self.app, "schedule_panel_refresh"):
            self.app.schedule_panel_refresh(left=True, center=True, right=True)

    def _apply_payload(self, payload: dict) -> bool:
        state_b64 = payload.get("dock_state_b64", "")
        state = self._decode_qbytearray(state_b64)
        restored = bool(state) and bool(self.app.dock_manager.restoreState(state))

        visibility = payload.get("visibility", {})
        if isinstance(visibility, dict):
            for dock_name in self.DOCK_NAMES:
                dock = getattr(self.app, dock_name, None)
                if dock is None:
                    continue
                visible = visibility.get(dock_name)
                if isinstance(visible, bool):
                    dock.setVisible(visible)

        opacity = payload.get("opacity")
        if isinstance(opacity, int) and hasattr(self.app, "slider"):
            opacity_unit = str(payload.get("opacity_unit", "") or "").strip().lower()
            if opacity_unit == "byte" or opacity > 100:
                restored_opacity = max(0, min(255, opacity))
            else:
                restored_opacity = opacity_percent_to_byte(opacity)
            self.app.slider.setValue(restored_opacity)

        view_mode = payload.get("view_mode_state")
        if isinstance(view_mode, str) and view_mode:
            self.app.view_mode_state = view_mode

        if hasattr(self.app, "sync_panel_menu_state"):
            self.app.sync_panel_menu_state()
        if hasattr(self.app, "schedule_panel_refresh"):
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
        if hasattr(self.app, "ensure_window_on_screen"):
            self.app.ensure_window_on_screen()

        return restored

    def _capture_current_layout(self) -> dict:
        state = self.app.dock_manager.saveState()
        geometry = self.app.saveGeometry() if hasattr(self.app, "saveGeometry") else QByteArray()
        visibility = {}
        for dock_name in self.DOCK_NAMES:
            dock = getattr(self.app, dock_name, None)
            visibility[dock_name] = bool(dock and dock.isVisible())

        return {
            "dock_state_b64": self._encode_qbytearray(state),
            "window_geometry_b64": self._encode_qbytearray(geometry),
            "visibility": visibility,
            "opacity": int(self.app.slider.value()) if hasattr(self.app, "slider") else 100,
            "opacity_unit": "byte",
            "view_mode_state": str(getattr(self.app, "view_mode_state", "주간보기")),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _read_presets(self) -> dict:
        raw = self.app.settings.value(self.SETTINGS_KEY, "")
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}

        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                self.app.settings.remove(self.SETTINGS_KEY)
                return {}

        try:
            parsed = json.loads(raw) if isinstance(raw, str) else {}
        except Exception:
            self.app.settings.remove(self.SETTINGS_KEY)
            return {}

        if not isinstance(parsed, dict):
            self.app.settings.remove(self.SETTINGS_KEY)
            return {}
        return parsed

    def _write_presets(self, presets: dict):
        self.app.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, ensure_ascii=False))
        self.app.settings.sync()

    def _list_user_presets(self, presets: dict) -> dict:
        return {k: v for k, v in presets.items() if k != self.DEFAULT_PRESET_KEY}

    def _list_history_presets(self, presets: dict) -> dict:
        builtin_names = self._builtin_slot_names()
        return {k: v for k, v in self._list_user_presets(presets).items() if k not in builtin_names}

    @staticmethod
    def _builtin_slot_names() -> set[str]:
        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            LAYOUT_PRESET_DEFS,
        )

        return {name for name, _shortcut in LAYOUT_PRESET_DEFS}

    @staticmethod
    def _encode_qbytearray(value) -> str:
        if not isinstance(value, QByteArray):
            return ""
        data = bytes(value.toBase64())
        return data.decode("ascii", errors="strict")

    @staticmethod
    def _decode_qbytearray(value) -> QByteArray:
        if not isinstance(value, str) or not value:
            return QByteArray()
        try:
            return QByteArray.fromBase64(value.encode("ascii", errors="strict"))
        except UnicodeEncodeError:
            return QByteArray()
