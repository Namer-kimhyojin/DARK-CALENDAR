from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

import calendar_app.presentation.widgets.panel_widget_style as _pws

_WIDGET_COLOR_THEME_KEY = "widget_mode_color_theme"
_WIDGET_COLOR_DEFAULT = "default"
_WIDGET_COLOR_FOLLOW_MAIN = "follow_main"
_WIDGET_COLOR_PRESET_HEX = {
    "indigo": "#5856d6",
    "ocean": "#22c3ca",
    "sage": "#24b47e",
    "amber": "#f2b84b",
    "rose": "#ff6f91",
    "slate": "#5c6b82",
}


def _css_to_qcolor(value: object, fallback: str = "#000000") -> QColor:
    return _pws.css_to_qcolor(value, fallback)


def _rgba_with_alpha(value: object, alpha: int, fallback: str = "#000000") -> str:
    return _pws.rgba(value, alpha, fallback)


def _blend_qcolor(base: QColor, mix: QColor, ratio: float) -> QColor:
    return _pws.blend(base, mix, ratio)


def _build_widget_mode_theme_tokens(app: QWidget) -> dict[str, str]:
    settings = getattr(app, "settings", None) if app is not None else None
    tokens = _resolve_widget_mode_tokens(app=app)
    raw_theme = ""
    if settings is not None:
        raw_theme = (
            str(settings.value("widget_mode_panel_theme", "light") or "light").strip().lower()
        )
    panel_theme = raw_theme if raw_theme in {"light", "dark"} else "light"
    tokens = _apply_panel_theme_override(tokens, panel_theme)
    return _apply_widget_color_override(
        tokens,
        _read_widget_color_mode_from_settings(settings),
        settings=settings,
    )


def _normalize_widget_color_mode(raw_value: object) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return _WIDGET_COLOR_DEFAULT
    lowered = raw.lower()
    if lowered in {
        _WIDGET_COLOR_DEFAULT,
        _WIDGET_COLOR_FOLLOW_MAIN,
        *_WIDGET_COLOR_PRESET_HEX.keys(),
    }:
        return lowered
    color = QColor(raw)
    if color.isValid():
        return color.name(QColor.NameFormat.HexRgb)
    return _WIDGET_COLOR_DEFAULT


def _read_widget_color_mode_from_settings(settings, *, legacy_key: str | None = None) -> str:
    if settings is None:
        return _WIDGET_COLOR_DEFAULT
    raw = settings.value(_WIDGET_COLOR_THEME_KEY, None)
    normalized = _normalize_widget_color_mode(raw)
    if raw not in (None, ""):
        return normalized
    if legacy_key:
        return _normalize_widget_color_mode(settings.value(legacy_key, None))
    return _WIDGET_COLOR_DEFAULT


def _widget_color_mode_accent(
    mode: str,
    *,
    settings=None,
    palette: dict[str, str] | None = None,
) -> str:
    normalized = _normalize_widget_color_mode(mode)
    if normalized in {_WIDGET_COLOR_DEFAULT, ""}:
        return ""
    if normalized == _WIDGET_COLOR_FOLLOW_MAIN:
        theme_color = QColor(
            str(
                getattr(settings, "value", lambda *_args, **_kwargs: "#4da6ff")(
                    "theme_color", "#4da6ff"
                )
                or "#4da6ff"
            )
        )
        if theme_color.isValid():
            return theme_color.name(QColor.NameFormat.HexRgb)
        if isinstance(palette, dict):
            fallback = QColor(str(palette.get("accent", "")))
            if fallback.isValid():
                return fallback.name(QColor.NameFormat.HexRgb)
        return ""
    if normalized in _WIDGET_COLOR_PRESET_HEX:
        return _WIDGET_COLOR_PRESET_HEX[normalized]
    return normalized if QColor(normalized).isValid() else ""


def _apply_widget_color_override(
    palette: dict[str, str],
    mode: str,
    *,
    settings=None,
) -> dict[str, str]:
    normalized = _normalize_widget_color_mode(mode)
    if normalized in {_WIDGET_COLOR_DEFAULT, _WIDGET_COLOR_FOLLOW_MAIN, ""}:
        return dict(palette)

    accent_override = _widget_color_mode_accent(normalized, settings=settings, palette=palette)
    if not accent_override:
        return dict(palette)

    updated = dict(palette)
    accent_q = _css_to_qcolor(accent_override, updated.get("accent", "#5856d6"))
    panel_bg_q = _css_to_qcolor(updated.get("panel_bg"), "#f3f3f8")
    surface_bg_q = _css_to_qcolor(updated.get("surface_bg"), "#f3f3f8")
    surface_alt_q = _css_to_qcolor(updated.get("surface_alt"), "#ededf2")
    section_bg_q = _css_to_qcolor(updated.get("section_bg"), surface_alt_q.name())
    section_alt_q = _css_to_qcolor(updated.get("section_bg_alt"), section_bg_q.name())
    card_bg_q = _css_to_qcolor(updated.get("card_bg"), section_bg_q.name())
    card_hover_q = _css_to_qcolor(updated.get("card_hover"), section_alt_q.name())
    header_bg_q = _css_to_qcolor(updated.get("header_bg"), surface_alt_q.name())
    header_shell_q = _css_to_qcolor(updated.get("header_shell_bg"), header_bg_q.name())
    button_bg_q = _css_to_qcolor(updated.get("button_bg"), section_bg_q.name())
    button_hover_q = _css_to_qcolor(updated.get("button_hover"), section_alt_q.name())
    chip_bg_q = _css_to_qcolor(updated.get("chip_bg"), section_bg_q.name())
    input_bg_q = _css_to_qcolor(updated.get("input_bg"), section_bg_q.name())
    is_dark = panel_bg_q.lightness() < 128
    accent_deep_q = (
        _blend_qcolor(accent_q, QColor("#ffffff"), 0.10) if is_dark else accent_q.darker(145)
    )
    danger_q = QColor("#ff6f91")

    def _alpha_for(key: str, default: int) -> int:
        return max(0, min(255, int(_css_to_qcolor(updated.get(key), "#000000").alpha() or default)))

    def _mix_with_alpha(base: QColor, ratio: float, *, key: str, default_alpha: int) -> str:
        mixed = _blend_qcolor(base, accent_q, ratio)
        alpha = _alpha_for(key, default_alpha)
        return _rgba_with_alpha(mixed, alpha, mixed.name(QColor.NameFormat.HexRgb))

    shell_start_q = _blend_qcolor(surface_bg_q, accent_q, 0.08 if is_dark else 0.06)
    shell_mid_q = _blend_qcolor(surface_alt_q, accent_q, 0.12 if is_dark else 0.09)
    shell_end_q = _blend_qcolor(panel_bg_q, accent_q, 0.10 if is_dark else 0.07)
    border_q = _blend_qcolor(surface_alt_q, accent_q, 0.26 if is_dark else 0.18)

    updated.update(
        {
            "accent": accent_q.name(QColor.NameFormat.HexRgb),
            "accent_deep": accent_deep_q.name(QColor.NameFormat.HexRgb),
            "accent_soft": _rgba_with_alpha(accent_q, 72, accent_q.name()),
            "accent_mid": _rgba_with_alpha(accent_q, 118, accent_q.name()),
            "accent_strong": accent_q.name(QColor.NameFormat.HexRgb),
            "panel_bg_start": _rgba_with_alpha(
                shell_start_q, _alpha_for("panel_bg_start", 246), shell_start_q.name()
            ),
            "panel_bg_mid": _rgba_with_alpha(
                shell_mid_q, _alpha_for("panel_bg_mid", 240), shell_mid_q.name()
            ),
            "panel_bg_end": _rgba_with_alpha(
                shell_end_q, _alpha_for("panel_bg_end", 246), shell_end_q.name()
            ),
            "panel_bg": _mix_with_alpha(
                panel_bg_q, 0.10 if is_dark else 0.08, key="panel_bg", default_alpha=242
            ),
            "header_bg": _mix_with_alpha(
                header_bg_q, 0.12 if is_dark else 0.07, key="header_bg", default_alpha=236
            ),
            "header_shell_bg": _mix_with_alpha(
                header_shell_q, 0.18 if is_dark else 0.10, key="header_shell_bg", default_alpha=214
            ),
            "header_shell_border": _rgba_with_alpha(
                border_q, _alpha_for("header_shell_border", 118), border_q.name()
            ),
            "surface_bg": _mix_with_alpha(
                surface_bg_q, 0.12 if is_dark else 0.07, key="surface_bg", default_alpha=214
            ),
            "surface_alt": _mix_with_alpha(
                surface_alt_q, 0.16 if is_dark else 0.10, key="surface_alt", default_alpha=196
            ),
            "section_bg": _mix_with_alpha(
                section_bg_q, 0.12 if is_dark else 0.08, key="section_bg", default_alpha=230
            ),
            "section_bg_alt": _mix_with_alpha(
                section_alt_q, 0.20 if is_dark else 0.13, key="section_bg_alt", default_alpha=216
            ),
            "section_border": _rgba_with_alpha(
                border_q, _alpha_for("section_border", 126), border_q.name()
            ),
            "section_border_soft": _rgba_with_alpha(
                border_q, _alpha_for("section_border_soft", 80), border_q.name()
            ),
            "panel_border": _rgba_with_alpha(
                border_q, _alpha_for("panel_border", 122), border_q.name()
            ),
            "panel_border_soft": _rgba_with_alpha(
                border_q, _alpha_for("panel_border_soft", 82), border_q.name()
            ),
            "card_bg": _mix_with_alpha(
                card_bg_q, 0.12 if is_dark else 0.08, key="card_bg", default_alpha=194
            ),
            "card_hover": _mix_with_alpha(
                card_hover_q, 0.22 if is_dark else 0.14, key="card_hover", default_alpha=232
            ),
            "card_pressed": _mix_with_alpha(
                card_hover_q, 0.28 if is_dark else 0.18, key="card_pressed", default_alpha=240
            ),
            "card_border": _rgba_with_alpha(
                border_q, _alpha_for("card_border", 96), border_q.name()
            ),
            "chip_bg": _mix_with_alpha(
                chip_bg_q, 0.24 if is_dark else 0.14, key="chip_bg", default_alpha=160
            ),
            "chip_border": _rgba_with_alpha(
                accent_q, _alpha_for("chip_border", 96), accent_q.name()
            ),
            "input_bg": _mix_with_alpha(
                input_bg_q, 0.14 if is_dark else 0.09, key="input_bg", default_alpha=242
            ),
            "input_border": _rgba_with_alpha(
                border_q, _alpha_for("input_border", 110), border_q.name()
            ),
            "button_bg": _mix_with_alpha(
                button_bg_q, 0.18 if is_dark else 0.10, key="button_bg", default_alpha=172
            ),
            "button_hover": _mix_with_alpha(
                button_hover_q, 0.26 if is_dark else 0.16, key="button_hover", default_alpha=230
            ),
            "button_primary_bg": _rgba_with_alpha(
                accent_q, _alpha_for("button_primary_bg", 42), accent_q.name()
            ),
            "button_primary_border": _rgba_with_alpha(
                accent_q, _alpha_for("button_primary_border", 130), accent_q.name()
            ),
            "button_primary_hover_bg": _rgba_with_alpha(
                accent_q, _alpha_for("button_primary_hover_bg", 62), accent_q.name()
            ),
            "button_primary_hover_border": accent_q.name(QColor.NameFormat.HexRgb),
            "button_primary_text": accent_deep_q.name(QColor.NameFormat.HexRgb),
            "hero_bg": _rgba_with_alpha(accent_q, _alpha_for("hero_bg", 28), accent_q.name()),
            "hero_bg_strong": _rgba_with_alpha(
                accent_q, _alpha_for("hero_bg_strong", 46), accent_q.name()
            ),
            "hero_border": _rgba_with_alpha(
                accent_q, _alpha_for("hero_border", 118), accent_q.name()
            ),
            "shell_gradient_start": _rgba_with_alpha(
                shell_start_q, _alpha_for("shell_gradient_start", 252), shell_start_q.name()
            ),
            "shell_gradient_mid": _rgba_with_alpha(
                shell_mid_q, _alpha_for("shell_gradient_mid", 248), shell_mid_q.name()
            ),
            "shell_gradient_end": _rgba_with_alpha(
                shell_end_q, _alpha_for("shell_gradient_end", 244), shell_end_q.name()
            ),
            "shell_outline": _rgba_with_alpha(
                border_q, _alpha_for("shell_outline", 124), border_q.name()
            ),
            "shell_outline_soft": _rgba_with_alpha(
                border_q, _alpha_for("shell_outline_soft", 78), border_q.name()
            ),
            "scroll_track": _mix_with_alpha(panel_bg_q, 0.08, key="scroll_track", default_alpha=84),
            "scroll_thumb": _rgba_with_alpha(
                accent_q, _alpha_for("scroll_thumb", 76), accent_q.name()
            ),
            "scroll_thumb_hover": _rgba_with_alpha(
                accent_q, _alpha_for("scroll_thumb_hover", 118), accent_q.name()
            ),
            "button_danger_bg": _rgba_with_alpha(danger_q, 34, danger_q.name()),
            "button_danger_border": _rgba_with_alpha(danger_q, 120, danger_q.name()),
            "button_danger_hover_bg": _rgba_with_alpha(danger_q, 56, danger_q.name()),
            "button_danger_hover_border": danger_q.name(QColor.NameFormat.HexRgb),
            "button_danger_text": "#ffffff" if is_dark else "#8f2740",
        }
    )
    return updated


def _apply_widget_background_opacity(
    tokens: dict[str, str], opacity_percent: int
) -> dict[str, str]:
    factor = max(0.30, min(1.0, int(opacity_percent) / 100.0))
    updated = dict(tokens)
    background_keys = {
        "panel_bg_start",
        "panel_bg_mid",
        "panel_bg_end",
        "panel_bg",
        "header_bg",
        "header_shell_bg",
        "surface_bg",
        "surface_alt",
        "section_bg",
        "section_bg_alt",
        "card_bg",
        "card_hover",
        "card_pressed",
        "chip_bg",
        "input_bg",
        "button_bg",
        "button_hover",
        "button_primary_bg",
        "button_primary_hover_bg",
        "button_danger_bg",
        "button_danger_hover_bg",
        "hero_bg",
        "hero_bg_strong",
        "scroll_track",
    }
    for key in background_keys:
        raw = updated.get(key)
        if not raw:
            continue
        qcolor = _css_to_qcolor(raw, "#000000")
        alpha = max(0, min(255, int(round(qcolor.alpha() * factor))))
        updated[key] = _rgba_with_alpha(qcolor, alpha, qcolor.name(QColor.NameFormat.HexRgb))
    return updated


def _resolve_widget_mode_tokens(
    tokens: dict[str, str] | None = None, *, app: QWidget | None = None
) -> dict[str, str]:
    settings = getattr(app, "settings", None) if app is not None else None
    preset_name = None
    if (
        settings is not None
        and _read_widget_color_mode_from_settings(settings) == _WIDGET_COLOR_FOLLOW_MAIN
    ):
        preset_name = ""
    return _pws.resolve_tokens(tokens, settings=settings, preset_name=preset_name)


def _widget_mode_int_token(tokens: dict[str, str], key: str, default: int) -> int:
    return _pws.int_token(tokens, key, default)


def _widget_mode_menu_stylesheet(tokens: dict[str, str] | None = None) -> str:
    return _pws.menu_stylesheet(_resolve_widget_mode_tokens(tokens=tokens))


def _widget_mode_launcher_stylesheet(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> str:
    return _pws.launcher_stylesheet(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)


def _apply_panel_theme_override(tokens: dict[str, str], theme: str) -> dict[str, str]:
    return _pws.apply_dark_theme(tokens) if theme == "dark" else tokens


def _widget_mode_panel_stylesheet(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> str:
    return _pws.panel_stylesheet(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)


def _widget_mode_entry_style_bundle(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> dict[str, str]:
    return _pws.entry_style_bundle(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)


def _widget_mode_quick_add_stylesheet(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> str:
    return _pws.quick_add_stylesheet(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)


def _widget_mode_calendar_stylesheet(tokens: dict[str, str] | None = None) -> str:
    return _pws.calendar_stylesheet(_resolve_widget_mode_tokens(tokens=tokens))


def _widget_mode_calendar_paint_palette(tokens: dict[str, str] | None = None) -> dict[str, QColor]:
    return _pws.calendar_paint_palette(_resolve_widget_mode_tokens(tokens=tokens))


def _widget_mode_chip_stylesheet(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> str:
    return _pws.chip_stylesheet(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)


def _widget_mode_work_summary_stylesheet(
    tokens: dict[str, str] | None = None, *, scale: float = 1.0
) -> str:
    return _pws.work_summary_stylesheet(_resolve_widget_mode_tokens(tokens=tokens), scale=scale)
