"""Helpers for reading theme-related values from QSettings."""

from PyQt6.QtCore import QSettings

from calendar_app.shared.color_utils import derive_panel_palette
from calendar_app.shared.qt_helpers import scaled_pt

OPACITY_STORAGE_UNIT_KEY = "last_opacity_unit"
OPACITY_UNIT_BYTE = "byte"
OPACITY_UNIT_PERCENT = "percent"


def _get_settings(settings=None):
    return settings if settings is not None else QSettings("kimhyojin", "Dark Calendar")


def _settings_has_key(settings, key: str) -> bool:
    try:
        return bool(settings.contains(key))
    except Exception:
        pass
    try:
        return key in set(settings.allKeys())
    except Exception:
        return False


def _clamp_opacity_byte(opacity_raw, default=200):
    try:
        value = int(opacity_raw)
    except Exception:
        value = int(default)
    return max(0, min(255, value))


def opacity_percent_to_byte(percent_raw, default=100):
    """Convert a legacy 0-100 percent opacity to a stored 0-255 byte."""
    try:
        value = int(percent_raw)
    except Exception:
        value = int(default)
    value = max(0, min(100, value))
    return max(0, min(255, int(round(value * 255 / 100.0))))


def opacity_byte_to_percent(opacity_raw, default=255):
    """Convert a stored 0-255 opacity byte to a rounded percent label."""
    return max(0, min(100, int(round(_clamp_opacity_byte(opacity_raw, default) * 100.0 / 255.0))))


def opacity_percent_label(opacity_raw, default=255):
    """Return a user-facing opacity label in percent from a stored 0-255 byte."""
    return f"{opacity_byte_to_percent(opacity_raw, default=default)}%"


def normalize_opacity_byte(opacity_raw, default=200, *, assume_legacy_percent=False):
    """Normalize opacity storage to 0-255 bytes."""
    if assume_legacy_percent:
        return opacity_percent_to_byte(opacity_raw, default=opacity_byte_to_percent(default))
    return _clamp_opacity_byte(opacity_raw, default=default)


def get_opacity_byte(settings=None, default=200, persist_normalized=False):
    """
    Return the stored window/panel opacity as a 0-255 byte.

    Legacy builds stored percent values without a unit marker. When that marker is
    missing, we bias toward byte semantics if theme-dialog-only sibling keys exist;
    otherwise we preserve legacy percent migration.
    """
    cfg = _get_settings(settings)
    raw = cfg.value("last_opacity", default)
    unit = str(cfg.value(OPACITY_STORAGE_UNIT_KEY, "") or "").strip().lower()
    if unit == OPACITY_UNIT_PERCENT:
        normalized = normalize_opacity_byte(raw, default=default, assume_legacy_percent=True)
    elif unit == OPACITY_UNIT_BYTE:
        normalized = normalize_opacity_byte(raw, default=default)
    else:
        clamped = _clamp_opacity_byte(raw, default=default)
        if (
            clamped > 100
            or _settings_has_key(cfg, "last_border_opacity")
            or _settings_has_key(cfg, "last_text_opacity")
        ):
            normalized = clamped
        else:
            normalized = normalize_opacity_byte(raw, default=default, assume_legacy_percent=True)

    if persist_normalized and (
        normalized != _clamp_opacity_byte(raw, default=default) or unit != OPACITY_UNIT_BYTE
    ):
        cfg.setValue("last_opacity", normalized)
        cfg.setValue(OPACITY_STORAGE_UNIT_KEY, OPACITY_UNIT_BYTE)
    return normalized


def set_opacity_byte(settings=None, value=200):
    """Persist the active window/panel opacity as a 0-255 byte value."""
    cfg = _get_settings(settings)
    normalized = normalize_opacity_byte(value, default=200)
    cfg.setValue("last_opacity", normalized)
    cfg.setValue(OPACITY_STORAGE_UNIT_KEY, OPACITY_UNIT_BYTE)
    return normalized


def get_opacity_factor(settings=None, default=200, persist_normalized=False):
    """Return normalized opacity factor in 0.0~1.0 from app settings."""
    normalized = get_opacity_byte(settings, default=default, persist_normalized=persist_normalized)
    return max(0.0, min(1.0, normalized / 255.0))


def get_text_theme_and_panel_base(settings=None):
    """Return (text_theme, panel_base_color) from app settings."""
    cfg = _get_settings(settings)
    return (
        cfg.value("text_theme", "dark"),
        cfg.value("panel_base_color", "#1c1c1c"),
    )


def get_theme_color(settings=None, default="#4da6ff"):
    """Return theme accent color from app settings."""
    cfg = _get_settings(settings)
    return str(cfg.value("theme_color", default) or default)


def get_theme_palette_inputs(settings=None, persist_opacity=False):
    """Return (text_theme, panel_base_color, opacity_factor) for palette builders."""
    cfg = _get_settings(settings)
    text_theme, panel_base = get_text_theme_and_panel_base(cfg)
    opacity_factor = get_opacity_factor(cfg, persist_normalized=persist_opacity)
    return str(text_theme), str(panel_base), opacity_factor


def fpt(delta=0):
    """Return a scaled CSS pt string for UI font sizes (shared across renderers)."""
    return scaled_pt(delta=delta, minimum=6, default=10)


def panel_palette():
    """Return the current panel color palette dict (shared across renderers)."""
    _, panel_base, opacity_factor = get_theme_palette_inputs()
    return derive_panel_palette(panel_base, opacity_factor)


def is_light_mode() -> bool:
    """Return True if the current text theme is 'light' (shared across renderers)."""
    return get_text_theme_and_panel_base()[0] == "light"
