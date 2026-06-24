from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE_PARTS = {".venv", "__pycache__"}


def _iter_project_py_files():
    for path in ROOT.rglob("*.py"):
        if any(part in IGNORE_PARTS for part in path.parts):
            continue
        yield path


def _norm_encoding_name(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_ast(path: Path) -> ast.AST:
    source = path.read_bytes().decode("utf-8-sig", errors="strict")
    return ast.parse(source, filename=str(path))


def _kw_str(node: ast.Call, key: str) -> str | None:
    for kw in node.keywords or []:
        if kw.arg != key:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _kw_expr(node: ast.Call, key: str) -> ast.AST | None:
    for kw in node.keywords or []:
        if kw.arg == key:
            return kw.value
    return None


def _kw_bool(node: ast.Call, key: str) -> bool | None:
    expr = _kw_expr(node, key)
    if isinstance(expr, ast.Constant) and isinstance(expr.value, bool):
        return expr.value
    return None


def _open_mode(node: ast.Call) -> str:
    kw_mode = _kw_str(node, "mode")
    if kw_mode is not None:
        return kw_mode
    if (
        len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return node.args[1].value
    return "r"


def test_all_encoding_keyword_usage_is_utf8():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords or []:
                if kw.arg != "encoding":
                    continue
                if not isinstance(kw.value, ast.Constant) or not isinstance(kw.value.value, str):
                    continue
                if _norm_encoding_name(kw.value.value) != "utf-8":
                    violations.append(f"{rel}:{node.lineno}: encoding={kw.value.value!r}")
    assert not violations, "Non-UTF-8 encoding keyword found:\n" + "\n".join(violations)


def test_builtin_open_text_mode_requires_utf8_encoding():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "open":
                continue
            mode = _open_mode(node)
            if "b" in mode:
                continue
            encoding = _kw_str(node, "encoding")
            if encoding is None:
                violations.append(f"{rel}:{node.lineno}: open(...) text mode without encoding")
                continue
            if _norm_encoding_name(encoding) != "utf-8":
                violations.append(f"{rel}:{node.lineno}: open(..., encoding={encoding!r})")
    assert not violations, "Text-mode open() must explicitly use UTF-8:\n" + "\n".join(violations)


def test_path_text_helpers_require_utf8_encoding():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"read_text", "write_text"}:
                continue
            encoding = _kw_str(node, "encoding")
            if encoding is None:
                violations.append(f"{rel}:{node.lineno}: .{node.func.attr}(...) without encoding")
                continue
            if _norm_encoding_name(encoding) != "utf-8":
                violations.append(f"{rel}:{node.lineno}: .{node.func.attr}(encoding={encoding!r})")
    assert not violations, "Path text helpers must explicitly use UTF-8:\n" + "\n".join(violations)


def test_subprocess_text_mode_requires_utf8_encoding():
    violations: list[str] = []
    subprocess_funcs = {"run", "Popen", "check_output", "check_call"}
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in subprocess_funcs:
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
                continue
            text_mode = bool(_kw_bool(node, "text")) or bool(_kw_bool(node, "universal_newlines"))
            if not text_mode:
                continue
            encoding = _kw_str(node, "encoding")
            if encoding is None:
                violations.append(
                    f"{rel}:{node.lineno}: subprocess.{node.func.attr}(text=True) without encoding"
                )
                continue
            if _norm_encoding_name(encoding) != "utf-8":
                violations.append(
                    f"{rel}:{node.lineno}: subprocess.{node.func.attr}(encoding={encoding!r})"
                )
    assert not violations, "subprocess text mode must explicitly use UTF-8:\n" + "\n".join(
        violations
    )


def test_utf8_encoding_keyword_requires_explicit_errors():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            encoding = _kw_str(node, "encoding")
            if encoding is None or _norm_encoding_name(encoding) != "utf-8":
                continue
            errors = _kw_str(node, "errors")
            if errors is None:
                violations.append(f"{rel}:{node.lineno}: encoding='utf-8' missing errors=...")
    assert not violations, "UTF-8 encoding keyword without explicit errors found:\n" + "\n".join(
        violations
    )


def test_errors_ignore_is_not_allowed():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            kw_errors = _kw_str(node, "errors")
            if isinstance(kw_errors, str) and kw_errors.lower() == "ignore":
                violations.append(f"{rel}:{node.lineno}: errors='ignore'")

            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"encode", "decode"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value.lower() == "ignore"
            ):
                violations.append(f"{rel}:{node.lineno}: {node.func.attr}(..., 'ignore')")
    assert not violations, "errors='ignore' usage is forbidden:\n" + "\n".join(violations)


def test_non_utf8_codec_calls_stay_in_whitelisted_locations():
    allowed: set[tuple[str, str]] = {
        ("calendar_app/preset_manager.py", "ascii"),
        ("recovered_source/preset_manager.py", "ascii"),
        ("scripts/fix_encoding.py", "cp949"),
        ("scripts/fix_encoding.py", "utf-8-sig"),
        ("tests/test_encoding_policy.py", "utf-8-sig"),
        ("tests/test_encoding_utils.py", "cp949"),
    }
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"encode", "decode"}:
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            if not isinstance(arg0, ast.Constant) or not isinstance(arg0.value, str):
                continue
            codec = _norm_encoding_name(arg0.value)
            if codec == "utf-8":
                continue
            if (rel, codec) not in allowed:
                violations.append(f"{rel}:{node.lineno}: {node.func.attr}({arg0.value!r})")
    assert not violations, "Unexpected non-UTF-8 codec call found:\n" + "\n".join(violations)


def test_utf8_codec_calls_require_explicit_errors():
    violations: list[str] = []
    for path in _iter_project_py_files():
        tree = _parse_ast(path)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"encode", "decode"}:
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            if not isinstance(arg0, ast.Constant) or not isinstance(arg0.value, str):
                continue
            if _norm_encoding_name(arg0.value) != "utf-8":
                continue
            has_errors_kw = _kw_str(node, "errors") is not None
            has_errors_pos = (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            )
            if not has_errors_kw and not has_errors_pos:
                violations.append(f"{rel}:{node.lineno}: {node.func.attr}('utf-8') missing errors")
    assert not violations, "UTF-8 codec calls must explicitly set errors:\n" + "\n".join(violations)
