"""Preset UI dialog/message helpers extracted from overlay_base."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QInputDialog, QMessageBox

from calendar_app.infrastructure.i18n import t


def warn_preset(parent, message_key: str, fallback: str, **kwargs) -> None:
    QMessageBox.warning(
        parent,
        t("widget.preset.warning_title", "Preset"),
        t(message_key, fallback, **kwargs),
    )


def warn_preset_name_exists(parent) -> None:
    warn_preset(
        parent,
        "widget.preset.name_exists",
        "A user preset with that name already exists.",
    )


def warn_preset_name_builtin(parent) -> None:
    warn_preset(
        parent,
        "widget.preset.name_builtin",
        "That name is reserved for a built-in preset.",
    )


def prompt_preset_name(parent, *, initial: str = "") -> str | None:
    name, ok = QInputDialog.getText(
        parent,
        t("widget.preset.name_title", "Preset Name"),
        t("widget.preset.name_label", "Preset name:"),
        text=initial,
    )
    if not ok:
        return None
    name = str(name or "").strip()
    return name or None


def require_non_empty_template(parent, template_text: str) -> str | None:
    template = str(template_text or "").strip()
    if template:
        return template
    warn_preset(parent, "widget.preset.empty_template", "Enter a template first.")
    return None


def prompt_new_preset_payload(parent, editor_text: str) -> tuple[str, str] | None:
    template = require_non_empty_template(parent, editor_text)
    if template is None:
        return None
    name = prompt_preset_name(parent)
    if not name:
        return None
    return name, template


def confirm_delete_preset(parent, name: str) -> bool:
    reply = QMessageBox.question(
        parent,
        t("widget.preset.delete_title", "Delete Preset"),
        t("widget.preset.delete_confirm", 'Delete preset "{name}"?', name=name),
    )
    return reply == QMessageBox.StandardButton.Yes


def append_row_entries(
    combo: QComboBox,
    entries: list[dict[str, str]],
    *,
    builtin_label: str,
    user_label: str,
) -> None:
    for entry in entries:
        name = entry["name"]
        template = entry["template"]
        kind = entry["kind"]
        kind_label = builtin_label if kind == "builtin" else user_label
        display = f"{name}  [{kind_label}]"
        combo.addItem(display)
        idx = combo.count() - 1
        combo.setItemData(idx, template, Qt.ItemDataRole.UserRole)
        combo.setItemData(idx, kind, Qt.ItemDataRole.UserRole + 1)
        combo.setItemData(idx, name, Qt.ItemDataRole.UserRole + 2)


def add_manager_placeholder(combo: QComboBox, placeholder_text: str) -> None:
    combo.addItem(placeholder_text)
    combo.setItemData(0, "", Qt.ItemDataRole.UserRole + 1)
    combo.setItemData(0, "", Qt.ItemDataRole.UserRole + 2)
    combo.setItemData(0, "placeholder", Qt.ItemDataRole.UserRole + 3)


def append_manager_entries(
    combo: QComboBox,
    entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    combo_entries: list[dict[str, str]] = [{"name": "", "kind": "placeholder"}]
    for entry in entries:
        name = entry["name"]
        template = entry["template"]
        kind = entry["kind"]
        combo_entries.append({"name": name, "kind": kind})
        combo.addItem(name)
        idx = combo.count() - 1
        combo.setItemData(idx, name, Qt.ItemDataRole.UserRole + 1)
        combo.setItemData(idx, template, Qt.ItemDataRole.UserRole + 2)
        combo.setItemData(idx, kind, Qt.ItemDataRole.UserRole + 3)
    return combo_entries


def find_manager_template_index(combo: QComboBox, template: str) -> int:
    for idx in range(combo.count()):
        if str(combo.itemData(idx, Qt.ItemDataRole.UserRole + 2) or "") == template:
            return idx
    return -1
