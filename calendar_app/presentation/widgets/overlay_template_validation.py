# -*- coding: utf-8 -*-
"""Syntax validation for built-in and user-authored overlay templates."""

from __future__ import annotations

from dataclasses import dataclass
import re

_WIDGET_KIND_ALIASES = {
    "date_card": "datecard",
    "overlay_date_card": "datecard",
}

_VARIABLE_RULES = {
    "clock": {
        "plain": {"time", "date", "weekday", "tz_label"},
        "formatted": {"time", "date"},
        "variants": {"weekday": {"short"}},
    },
    "stopwatch": {
        "plain": {
            "elapsed",
            "hours",
            "minutes",
            "seconds",
            "tenths",
            "status",
            "status_icon",
        },
        "formatted": set(),
        "variants": {},
    },
    "countdown": {
        "plain": {"remaining", "days", "hours", "minutes", "seconds", "target"},
        "formatted": {"target"},
        "variants": {},
    },
    "dday": {
        "plain": {"dday", "days", "sign", "label", "date", "date_short"},
        "formatted": {"date"},
        "variants": {},
    },
    "datecard": {
        "plain": {
            "weekday",
            "day",
            "date",
            "month",
            "year",
            "doy",
            "week_num",
            "quarter",
            "days_left_month",
            "days_in_month",
            "yesterday",
            "tomorrow",
        },
        "formatted": {"date"},
        "variants": {"weekday": {"short", "en"}},
    },
    "weather": {
        "plain": {"city", "temp", "unit", "desc", "icon", "humidity", "wind"},
        "formatted": set(),
        "variants": {},
    },
    "text": {
        "plain": {
            "time",
            "date",
            "weekday",
            "day_of_year",
            "dday",
            "countdown",
            "stopwatch",
            "task_count",
            "directive_count",
            "next_event",
            "custom_var",
        },
        "formatted": {"time", "date"},
        "variants": {"weekday": {"short", "en"}},
        "arguments": {"dday", "countdown", "stopwatch", "custom_var"},
    },
}

_CONDITION_VARIABLES = {
    "clock": {"weekday", "date", "tz_label"},
    "stopwatch": set(_VARIABLE_RULES["stopwatch"]["plain"]),
    "countdown": set(_VARIABLE_RULES["countdown"]["plain"]),
    "dday": {"dday", "days", "sign", "label", "date_short"},
    "datecard": set(_VARIABLE_RULES["datecard"]["plain"]),
    "weather": set(_VARIABLE_RULES["weather"]["plain"]),
    "text": {
        "task_count",
        "directive_count",
        "countdown",
        "stopwatch",
        "dday",
        "day_of_year",
    },
}

_TOKEN_RE = re.compile(r"\{([^{}]*)\}")
_CONDITION_RE = re.compile(r"^([\w:.-]+)\s*(==|!=|<=|>=|<|>)\s*(.+)$")
_SIZE_RE = re.compile(r"^(?:base|[+-]\d+|\d+|\d+(?:\.\d+)?x|\d+(?:\.\d+)?%)$")
_LINE_HEIGHT_RE = re.compile(r"^\d+(?:\.\d+)?(?:x|%|pt)?$")
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_COLOR_ALIASES = {
    "text",
    "primary",
    "secondary",
    "muted",
    "faint",
    "accent",
    "info",
    "warning",
    "success",
    "danger",
}


@dataclass(frozen=True)
class TemplateSyntaxIssue:
    """One actionable template grammar problem."""

    code: str
    token: str
    detail: str

    def summary(self) -> str:
        return f"{{{self.token}}}: {self.detail}" if self.token else self.detail


def normalize_widget_template_kind(widget_type: object) -> str:
    """Normalize settings prefixes and registry names to preset schema keys."""

    raw = str(widget_type or "").strip().lower()
    normalized = _WIDGET_KIND_ALIASES.get(raw, raw)
    if normalized.startswith("overlay_"):
        normalized = normalized.removeprefix("overlay_")
    return _WIDGET_KIND_ALIASES.get(normalized, normalized)


def _issue(code: str, token: str, detail: str) -> TemplateSyntaxIssue:
    return TemplateSyntaxIssue(code=code, token=token, detail=detail)


def _validate_style_hints(token: str, hints: list[str]) -> list[TemplateSyntaxIssue]:
    issues: list[TemplateSyntaxIssue] = []
    for raw_hint in hints:
        hint = raw_hint.strip()
        if hint in {"bold", "italic"}:
            continue
        if hint.startswith("size="):
            value = hint[5:].strip()
            if _SIZE_RE.fullmatch(value):
                continue
            issues.append(_issue("invalid_size", token, f"invalid size hint '{hint}'"))
            continue
        if hint.startswith("color="):
            value = hint[6:].strip()
            if value.lower() in _COLOR_ALIASES or _HEX_COLOR_RE.fullmatch(value):
                continue
            issues.append(_issue("invalid_color", token, f"invalid color hint '{hint}'"))
            continue
        if hint.startswith(("line=", "line_height=", "lh=")):
            value = hint.split("=", 1)[1].strip()
            if (
                _LINE_HEIGHT_RE.fullmatch(value)
                and float(value.removesuffix("pt").removesuffix("x").removesuffix("%")) > 0
            ):
                continue
            issues.append(
                _issue("invalid_line_height", token, f"invalid line-height hint '{hint}'")
            )
            continue
        issues.append(_issue("unknown_hint", token, f"unknown style hint '{hint or '<empty>'}'"))
    return issues


def _variable_is_valid(kind: str, expression: str) -> bool:
    rules = _VARIABLE_RULES[kind]
    name, separator, argument = expression.partition(":")
    if not separator:
        return name in rules["plain"]
    if name in rules["formatted"]:
        if kind == "text" and name == "time" and argument.startswith("tz="):
            timezone, separator, fmt = argument[3:].partition(":")
            return bool(timezone and (not separator or fmt))
        return bool(argument)
    variants = rules["variants"].get(name, set())
    if argument in variants:
        return True
    return name in rules.get("arguments", set()) and bool(argument)


def _condition_variable_is_valid(kind: str, expression: str) -> bool:
    if expression in _CONDITION_VARIABLES[kind]:
        return True
    if kind == "text":
        name, separator, argument = expression.partition(":")
        return bool(separator and argument and name in {"countdown", "stopwatch", "dday"})
    return False


def validate_widget_template(
    widget_type: object,
    template: object,
    *,
    allow_default_sentinel: bool = False,
) -> tuple[TemplateSyntaxIssue, ...]:
    """Validate braces, conditionals, widget variables, and style hints."""

    kind = normalize_widget_template_kind(widget_type)
    if kind not in _VARIABLE_RULES:
        return (_issue("unknown_widget", "", f"unknown widget type '{kind}'"),)

    text = str(template or "")
    if allow_default_sentinel and text == "__DEFAULT__":
        return ()

    matches = list(_TOKEN_RE.finditer(text))
    stripped = _TOKEN_RE.sub("", text)
    issues: list[TemplateSyntaxIssue] = []
    if "{" in stripped or "}" in stripped:
        issues.append(_issue("unbalanced_brace", "", "unbalanced or nested braces"))

    conditional_open = False
    else_seen = False
    for match in matches:
        token = match.group(1).strip()
        if token.startswith("if "):
            if conditional_open:
                issues.append(
                    _issue("nested_condition", token, "nested conditions are not supported")
                )
                continue
            condition = token[3:].strip()
            parsed = _CONDITION_RE.fullmatch(condition)
            if parsed is None:
                issues.append(_issue("invalid_condition", token, "invalid condition expression"))
            elif not _condition_variable_is_valid(kind, parsed.group(1)):
                issues.append(
                    _issue(
                        "invalid_condition_variable",
                        token,
                        f"unsupported condition variable '{parsed.group(1)}' for {kind}",
                    )
                )
            conditional_open = True
            else_seen = False
            continue
        if token == "else":
            if not conditional_open or else_seen:
                issues.append(_issue("unexpected_else", token, "unexpected else token"))
            else_seen = True
            continue
        if token == "/if":
            if not conditional_open:
                issues.append(_issue("unexpected_end_if", token, "unexpected condition end"))
            conditional_open = False
            else_seen = False
            continue
        if token.startswith("align="):
            if token.partition("=")[2].strip().lower() not in {"left", "center", "right"}:
                issues.append(
                    _issue("invalid_alignment", token, "alignment must be left, center, or right")
                )
            continue
        if token.startswith(("lh=", "line=", "line_height=")):
            issues.extend(_validate_style_hints(token, [token]))
            continue

        expression, *hints = token.split("|")
        expression = expression.strip()
        if not _variable_is_valid(kind, expression):
            issues.append(
                _issue("unknown_variable", token, f"unsupported variable '{expression}' for {kind}")
            )
        issues.extend(_validate_style_hints(token, hints))

    if conditional_open:
        issues.append(_issue("unclosed_condition", "if", "condition block is not closed"))

    unique = dict.fromkeys(issues)
    return tuple(unique)
