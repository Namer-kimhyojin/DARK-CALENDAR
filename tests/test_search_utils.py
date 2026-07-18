from unittest import TestCase

from calendar_app.shared.search_utils import (
    clean_calendar_description,
    extract_hashtags,
    matches_search_query,
    parse_search_query,
)


class SearchUtilsTests(TestCase):
    def test_clean_calendar_description_strips_google_holiday_boilerplate(self):
        description = (
            "기념일\n기념일을 숨기려면 Google Calendar 설정 > 대한민국의 휴일 캘린더로 이동하세요."
        )

        cleaned = clean_calendar_description(
            description,
            source_calendar_id="ko.south_korea#holiday@group.v.calendar.google.com",
            sync_mode="remote_mirror",
        )

        self.assertEqual(cleaned, "기념일")

    def test_clean_calendar_description_keeps_regular_text(self):
        description = "팀 회의\n회의실 A"

        cleaned = clean_calendar_description(
            description,
            source_calendar_id="team@example.com",
            sync_mode="remote_mirror",
        )

        self.assertEqual(cleaned, description)

    def test_extract_hashtags_from_texts(self):
        tags = extract_hashtags("회의 #테크 #AI", "메모: #테크, #기획")
        self.assertEqual(tags, {"테크", "ai", "기획"})

    def test_parse_search_query_splits_keywords_and_tags(self):
        keywords, tags = parse_search_query("보고서 #테크 #AI")
        self.assertEqual(keywords, ("보고서",))
        self.assertEqual(tags, frozenset({"테크", "ai"}))

    def test_matches_with_tag_only_query(self):
        self.assertTrue(matches_search_query("#테크", "주간 #테크 회의", "메모"))
        self.assertFalse(matches_search_query("#테크", "주간 회의", "메모"))

    def test_matches_with_keyword_and_tag(self):
        self.assertTrue(matches_search_query("회의 #테크", "주간 #테크 회의", "세부 메모"))
        self.assertFalse(matches_search_query("회의 #테크", "주간 회의", "세부 메모"))

    def test_matches_with_multiple_tags_requires_all(self):
        self.assertTrue(matches_search_query("#테크 #ai", "신규 기능 #테크 #AI"))
        self.assertFalse(matches_search_query("#테크 #ai", "신규 기능 #테크"))
