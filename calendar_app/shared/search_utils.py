from collections.abc import Iterable
from functools import lru_cache
import re

_TAG_PATTERN = re.compile(r"#([^\s#]+)")
_TRIM_CHARS = ".,!?;:()[]{}<>\"'`"


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _clean_tag(tag: str) -> str:
    cleaned = _norm(tag).strip(_TRIM_CHARS).lstrip("#")
    return cleaned


def strip_hashtags(text: str) -> str:
    """#태그를 제거하고 남은 텍스트를 반환. 표시용으로 사용."""
    if not text:
        return text or ""
    result = _TAG_PATTERN.sub("", text).strip()
    # 연속된 공백 정리
    result = re.sub(r"  +", " ", result)
    return result


def clean_display_text(value) -> str:
    """None-safe wrapper: strip hashtags and whitespace for tooltip/display use."""
    if value is None:
        return ""
    return strip_hashtags(str(value)).strip()


def clean_calendar_description(value, *, source_calendar_id=None, sync_mode=None) -> str:
    """Normalize calendar descriptions for display.

    Google holiday calendars sometimes append a boilerplate hint like
    "Google Calendar 설정 > ... 휴일 캘린더로 이동하세요." which makes compact
    detail cards look like duplicated content. Strip only that hint while
    keeping the human-meaningful first line such as "기념일" or "공휴일".
    """
    text = clean_display_text(value)
    if not text:
        return ""

    source_norm = _norm(source_calendar_id)
    sync_norm = _norm(sync_mode)
    is_google_holiday = (
        "#holiday@" in source_norm or "holiday@group.v.calendar.google.com" in source_norm
    )
    if not is_google_holiday and sync_norm != "remote_mirror":
        return text

    cleaned_lines: list[str] = []
    for raw_line in str(value).splitlines():
        line = clean_display_text(raw_line)
        if not line:
            continue
        line_norm = _norm(line)
        is_holiday_hint = "google calendar" in line_norm and (
            "settings" in line_norm
            or "설정" in line_norm
            or "캘린더로 이동" in line_norm
            or "holiday" in line_norm
            or "휴일" in line_norm
        )
        if is_google_holiday and is_holiday_hint:
            continue
        cleaned_lines.append(line)

    if not cleaned_lines:
        return text

    return "\n".join(cleaned_lines).strip()


def extract_hashtags(*texts) -> set[str]:
    tags: set[str] = set()
    for text in texts:
        if text is None:
            continue
        for raw in _TAG_PATTERN.findall(str(text)):
            tag = _clean_tag(raw)
            if tag:
                tags.add(tag)
    return tags


@lru_cache(maxsize=256)
def parse_search_query(query: str) -> tuple[tuple[str, ...], frozenset[str]]:
    q = _norm(query)
    if not q:
        return (), frozenset()

    tags = frozenset(
        cleaned for cleaned in (_clean_tag(raw) for raw in _TAG_PATTERN.findall(q)) if cleaned
    )
    q_without_tags = _TAG_PATTERN.sub(" ", q)
    keywords = tuple(token for token in re.split(r"\s+", q_without_tags) if token)
    return keywords, tags


def matches_search_query(query: str, *texts, extra_tags: Iterable[str] | None = None) -> bool:
    keywords, required_tags = parse_search_query(_norm(query))
    if not keywords and not required_tags:
        return True

    searchable_blob = " ".join(_norm(text) for text in texts if text).strip()
    if keywords and not all(keyword in searchable_blob for keyword in keywords):
        return False

    if required_tags:
        candidate_tags = extract_hashtags(searchable_blob)
        if extra_tags:
            for raw in extra_tags:
                cleaned = _clean_tag(str(raw))
                if cleaned:
                    candidate_tags.add(cleaned)
        if not required_tags.issubset(candidate_tags):
            return False

    return True
