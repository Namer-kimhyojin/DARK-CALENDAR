"""Template/HTML utility helpers extracted from overlay_base."""

from __future__ import annotations

import re as _re

from PyQt6.QtCore import QSize

# Reference font size used for the legacy ``size=N`` (plain integer) form.
# "size=36" means "36 pt when the base font is this many pt".
_TEMPLATE_REF_SIZE: int = 24

_TMPLREF_FS_RE = _re.compile(r"font-size:((?:RATIO|DELTA|REF):[^_]+)_TMPLREF_pt")
_TMPLREF_LH_RE = _re.compile(r"line-height:((?:RATIO|REF):[^_]+)_TMPLREF_lh")

_RE_ALIGN_TAG = _re.compile(r"\{align=(left|center|right)\}", _re.IGNORECASE)
# Sentinel used to protect {align=...} tokens during regex variable substitution
_ALIGN_SENTINEL = "\x00ALIGN:"

_RE_GLOBAL_LH = _re.compile(r"<lh\s+([^>]+)>", _re.IGNORECASE)
_RE_LH_TOKEN = _re.compile(r"\{(?:lh|line|line_height)=([^}]+)\}")


def _scale_template_html(html: str, base_size: int) -> str:
    """Resolve all ``_TMPLREF_`` sentinel markers to actual CSS values.

    Marker forms (font-size):
        REF:<N>     -> round(N * base_size / _TEMPLATE_REF_SIZE)   legacy ratio
        RATIO:<f>   -> round(f * base_size)                        multiplier
        DELTA:<d>   -> base_size + d                               additive

    Marker forms (line-height):
        RATIO:<f>   -> unitless CSS multiplier (kept as-is, e.g. ``line-height:1.4``)
        REF:<N>     -> round(N * base_size / _TEMPLATE_REF_SIZE) pt
    """
    if base_size <= 0:
        base_size = _TEMPLATE_REF_SIZE

    def _fs(m: _re.Match) -> str:
        enc = m.group(1)
        kind, _, val = enc.partition(":")
        try:
            if kind == "REF":
                pt = max(6, round(float(val) * base_size / _TEMPLATE_REF_SIZE))
            elif kind == "RATIO":
                pt = max(6, round(float(val) * base_size))
            elif kind == "DELTA":
                pt = max(6, base_size + int(float(val)))
            else:
                pt = base_size
        except (ValueError, ZeroDivisionError):
            pt = base_size
        return f"font-size:{pt}pt"

    def _lh(m: _re.Match) -> str:
        enc = m.group(1)
        kind, _, val = enc.partition(":")
        try:
            if kind == "RATIO":
                # Unitless line-height multiplier -> keep as float
                return f"line-height:{float(val)}"
            if kind == "REF":
                pt = max(6, round(float(val) * base_size / _TEMPLATE_REF_SIZE))
                return f"line-height:{pt}pt"
        except ValueError:
            pass
        return f"line-height:{val}"

    html = _TMPLREF_FS_RE.sub(_fs, html)
    html = _TMPLREF_LH_RE.sub(_lh, html)
    return html


def _protect_align_tags(template: str) -> str:
    """Replace ``{align=left|center|right}`` with a sentinel before substitution."""
    return _RE_ALIGN_TAG.sub(lambda m: f"{_ALIGN_SENTINEL}{m.group(1).lower()}\x00", template)


def _apply_align_tags(text: str) -> str:
    """Convert newline-separated lines to ``<br>`` and wrap align-tagged lines."""

    def _process_line(line: str) -> str:
        # Sentinel form (from _protect_align_tags)
        if line.startswith(_ALIGN_SENTINEL):
            end = line.index("\x00", len(_ALIGN_SENTINEL))
            align = line[len(_ALIGN_SENTINEL) : end]
            rest = line[end + 1 :]
            return f'<div style="text-align:{align}">{rest}</div>'
        # Raw form (plain text / non-template paths)
        m = _RE_ALIGN_TAG.match(line)
        if m:
            align = m.group(1).lower()
            rest = line[m.end() :]
            return f'<div style="text-align:{align}">{rest}</div>'
        return line

    normalised = text.replace("\\n", "\n")
    lines = normalised.split("\n")
    processed = [_process_line(ln) for ln in lines]
    return "<br>".join(processed)


def _newlines_to_br(text: str) -> str:
    """Convert both literal ``\\n`` and actual newlines to ``<br>``."""
    return text.replace("\\n", "<br>").replace("\n", "<br>")


def _inject_global_lh(template: str) -> str:
    """Convert ``{lh=N}`` standalone tokens in template to ``<lh N>`` markers."""
    return _RE_LH_TOKEN.sub(lambda m: f"<lh {m.group(1).strip()}>", template)


def _extract_global_lh(html: str, base_size: int) -> tuple[str, str]:
    """Strip ``<lh N>`` markers and return (cleaned_html, css_line_height)."""
    css_value = [""]

    def _sub(m: _re.Match) -> str:
        raw = m.group(1).strip()
        if raw.endswith("x"):
            css_value[0] = raw[:-1]
        elif raw.endswith("%"):
            try:
                css_value[0] = str(float(raw[:-1]) / 100.0)
            except ValueError:
                css_value[0] = raw
        elif raw.endswith("pt"):
            # Scale proportionally like font-size REF markers
            try:
                pt = round(float(raw[:-2]) * base_size / _TEMPLATE_REF_SIZE)
                css_value[0] = f"{max(6, pt)}pt"
            except ValueError:
                css_value[0] = raw
        else:
            css_value[0] = raw
        return ""

    cleaned = _RE_GLOBAL_LH.sub(_sub, html)
    return cleaned, css_value[0]


def _empty_preview_html(message: str) -> str:
    return (
        "<div style='color:muted;font-size:10pt;text-align:center;"
        "padding:18px 10px;'>"
        f"{message}"
        "</div>"
    )


def _preview_base_size(size: QSize) -> int:
    width = max(1, size.width())
    height = max(1, size.height())
    width_fit = width // 18
    height_fit = height // 10
    return max(8, min(18, width_fit, height_fit))
