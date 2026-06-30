import pytest

from calendar_app.shared.encoding_utils import (
    decode_legacy_bytes,
    read_text_with_legacy_fallback,
)


def test_decode_legacy_bytes_prefers_utf8():
    raw = "다크 캘린더 ✅".encode("utf-8", errors="strict")
    result = decode_legacy_bytes(raw)
    assert result.encoding == "utf-8"
    assert result.text == "다크 캘린더 ✅"


def test_decode_legacy_bytes_falls_back_to_cp949():
    raw = "한글 텍스트".encode("cp949")
    result = decode_legacy_bytes(raw)
    assert result.encoding == "cp949"
    assert result.text == "한글 텍스트"


def test_decode_legacy_bytes_raises_on_unknown_bytes():
    with pytest.raises(UnicodeDecodeError):
        decode_legacy_bytes(b"\x80")


def test_read_text_with_legacy_fallback_reads_cp949_file(tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes("레거시 데이터".encode("cp949"))
    result = read_text_with_legacy_fallback(path)
    assert result.encoding == "cp949"
    assert result.text == "레거시 데이터"
