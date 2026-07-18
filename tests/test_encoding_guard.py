from calendar_app.infrastructure.i18n import I18nManager


def test_broken_text_detector_catches_known_encoding_patterns():
    assert I18nManager._looks_broken_text("????")
    assert I18nManager._looks_broken_text("?? Widget Manager")
    assert I18nManager._looks_broken_text("�� 깨짐")


def test_broken_text_detector_allows_normal_strings():
    assert not I18nManager._looks_broken_text("Widget Manager")
    assert not I18nManager._looks_broken_text("위젯 관리자")
    assert not I18nManager._looks_broken_text("최근 색상")
