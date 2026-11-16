# -*- coding: utf-8 -*-
"""Weekday and month names on screen come from Qt's locale data, not locale keys.

The locale files held word-for-word machine translations of the weekday names
("Sat" became "sat down", "Sun" became "the sun") and scrambled lists for ar and vi.
Each screen now reads QLocale's standalone names; these tests pin that for every
bundled UI language, plus the Russian month case and the Arabic nav chevrons.
"""

from datetime import date, datetime
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QDateTime, QLocale, QSettings, Qt, QTime, QTimer
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget
import pytest

from calendar_app.application.calendar_print_service import (
    CalendarPrintRequest,
    build_calendar_print_document,
)
from calendar_app.infrastructure.i18n import I18nManager
from calendar_app.presentation import locale_names
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    get_weekday_names,
    recurrence_summary,
)
from calendar_app.presentation.dialogs.widget_workspace_options_dialog import weekday_labels
from calendar_app.presentation.main_window.away_lock_actions import _lock_screen_date_text
from calendar_app.presentation.panels import side_panel_renderer
from calendar_app.presentation.printing import calendar_print_renderer
from calendar_app.presentation.widgets import overlay_datecard
from calendar_app.presentation.widgets.unified_widget_mode import _CompactMonthCalendar
from calendar_app.shared.icon_map import ICON
from tests.support import TemporaryDatabaseTestCase
from tests.test_week_planner_integration import CalendarRenderHost

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = sorted(path.stem for path in (ROOT / "locales").glob("*.json"))
FRIDAY = QDate(2026, 11, 13)
SHORT = QLocale.FormatType.ShortFormat
NARROW = QLocale.FormatType.NarrowFormat
LONG = QLocale.FormatType.LongFormat


def _standalone_names(locale: QLocale, fmt: QLocale.FormatType) -> list[str]:
    return [locale.standaloneDayName(day, fmt) for day in range(1, 8)]


def _date_card(tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "datecard.ini"), QSettings.Format.IniFormat)
    return owner, overlay_datecard.OverlayDateCardWidget(owner)


def _close_date_card(owner, card):
    for timer in card.findChildren(QTimer):
        timer.stop()
    card.close()
    owner.close()
    owner.deleteLater()


def _plain(html: str) -> str:
    document = QTextDocument()
    document.setHtml(html)
    return document.toPlainText()


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ui_language(qt_app):
    """Apply the app's own language -> QLocale mapping, then restore the default."""
    original_locale = QLocale()
    original_direction = qt_app.layoutDirection()

    def apply(code: str) -> QLocale:
        I18nManager._apply_qt_locale(code)
        return QLocale()

    yield apply
    QLocale.setDefault(original_locale)
    qt_app.setLayoutDirection(original_direction)


class _RecordingPainter(QPainter):
    texts: list[str] = []

    def drawText(self, *args):  # noqa: N802 - Qt override
        if args and isinstance(args[-1], str):
            _RecordingPainter.texts.append(args[-1])
        return super().drawText(*args)


def _painted_mini_calendar_texts(year: int, month: int) -> list[str]:
    grid = overlay_datecard._CalendarGridWidget(None)
    try:
        grid.resize(240, 190)
        grid.update_date(QDate(year, month, 1), year, month, grid._fg_color, "")
        _RecordingPainter.texts = []
        with patch.object(overlay_datecard, "QPainter", _RecordingPainter):
            grid.render(QImage(240, 190, QImage.Format.Format_ARGB32))
        return list(_RecordingPainter.texts)
    finally:
        grid.deleteLater()


@pytest.mark.parametrize("code", LANGUAGES)
def test_text_sites_use_qt_short_weekday_names(ui_language, code):
    locale = ui_language(code)
    short = _standalone_names(locale, SHORT)

    # Task dialog recurrence weekday picker and its summary line.
    assert get_weekday_names() == short
    assert short[4] in recurrence_summary(FRIDAY, "weekly", "mode=weekly;weekday=4")
    # Widget workspace rules.
    assert weekday_labels() == short
    # Day/week toolbar title and the side-panel week list.
    assert month_renderer._format_toolbar_date(FRIDAY, False) == f"2026.11.13 ({short[4]})"
    assert side_panel_renderer._localized_weekday_short(FRIDAY) == short[4]
    # Printed weekday header.
    assert calendar_print_renderer._weekday_names() == short


@pytest.mark.parametrize("code", LANGUAGES)
def test_compact_grids_use_qt_narrow_weekday_names(ui_language, code, tmp_path):
    locale = ui_language(code)
    narrow = _standalone_names(locale, NARROW)
    # Narrow letters repeat ("T" is Tue and Thu), so screen readers get the full name.
    long_names = _standalone_names(locale, LONG)

    # Widget-mode month header, also after a refresh.
    month = _CompactMonthCalendar()
    try:
        assert [label.text() for label in month.weekday_labels] == narrow
        month.update_month(FRIDAY)
        assert [label.text() for label in month.weekday_labels] == narrow
        assert [label.accessibleName() for label in month.weekday_labels] == long_names
    finally:
        month.deleteLater()

    # Date card: week strip cells and the painted mini calendar.
    owner, card = _date_card(tmp_path)
    try:
        assert [cell.text() for cell in card._ws_cells] == narrow
        assert [cell.accessibleName() for cell in card._ws_cells] == long_names
    finally:
        _close_date_card(owner, card)

    painted = _painted_mini_calendar_texts(2026, 11)
    assert painted[0] == f"2026. 11  {locale.standaloneMonthName(11)}"
    assert painted[1:8] == narrow


def test_korean_output_is_unchanged(ui_language):
    ui_language("ko")
    korean = ["월", "화", "수", "목", "금", "토", "일"]
    assert get_weekday_names() == korean
    assert weekday_labels() == korean
    assert overlay_datecard._weekday_labels_mon_first() == korean
    assert calendar_print_renderer._weekday_names() == korean
    assert month_renderer._format_toolbar_date(FRIDAY, False) == "2026.11.13 (금)"
    assert _lock_screen_date_text(FRIDAY) == "2026.11.13 (금)"


def test_russian_month_titles_use_the_nominative_case(ui_language):
    ui_language("ru")

    def fake_t(key, default=None, **_kwargs):
        return "{month_name} {year}" if key == "calendar.month_title" else default

    with patch.object(month_renderer, "t", side_effect=fake_t):
        assert month_renderer._format_toolbar_date(FRIDAY, True) == "ноябрь 2026"
    assert _painted_mini_calendar_texts(2026, 11)[0] == "2026. 11  ноябрь"


def test_date_card_month_standalone_variant_is_nominative(ui_language, tmp_path):
    ui_language("ru")
    owner, card = _date_card(tmp_path)
    try:
        now = QDateTime(FRIDAY, QTime(12, 0))
        # A month heading on its own line is nominative; "{day} {month}" keeps the
        # genitive that a day number needs ("13 ноября").
        html = card._resolve_dc_template("{month:standalone|size=18}\n{day} {month}", now)
        assert _plain(html).splitlines() == ["ноябрь", "13 ноября"]
    finally:
        _close_date_card(owner, card)


def _arrow_types(month: _CompactMonthCalendar) -> tuple[Qt.ArrowType, Qt.ArrowType]:
    return month.previous_btn.arrowType(), month.next_btn.arrowType()


def test_widget_mode_month_arrows_point_outward_right_to_left(ui_language):
    ui_language("ar")
    month = _CompactMonthCalendar()
    try:
        assert month.isRightToLeft()
        # The mirrored row puts "previous" on the right edge, so it points right.
        assert _arrow_types(month) == (Qt.ArrowType.RightArrow, Qt.ArrowType.LeftArrow)
        ui_language("en")
        assert not month.isRightToLeft()
        assert _arrow_types(month) == (Qt.ArrowType.LeftArrow, Qt.ArrowType.RightArrow)
    finally:
        month.deleteLater()


def test_widget_mode_month_arrows_follow_a_runtime_switch_to_arabic(ui_language):
    ui_language("en")
    month = _CompactMonthCalendar()
    try:
        assert _arrow_types(month) == (Qt.ArrowType.LeftArrow, Qt.ArrowType.RightArrow)
        ui_language("ar")
        assert _arrow_types(month) == (Qt.ArrowType.RightArrow, Qt.ArrowType.LeftArrow)
    finally:
        month.deleteLater()


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "ko"])
def test_lock_screen_date_is_a_real_localized_date(ui_language, code):
    locale = ui_language(code)
    text = _lock_screen_date_text(FRIDAY)
    assert text == locale.toString(FRIDAY, QLocale.FormatType.LongFormat)
    assert locale.dayName(5, QLocale.FormatType.LongFormat) in text


def test_print_header_and_legend_use_locale_names(ui_language, tmp_path):
    locale = ui_language("de")
    request = CalendarPrintRequest(date(2026, 11, 1), date(2026, 11, 30), include_location=True)
    document = build_calendar_print_document(
        request,
        [
            {
                "id": 1,
                "name": "Planung",
                "type": "schedule",
                "deadline": "2026-11-13 09:00:00",
                "end_date": "2026-11-13 10:00:00",
                "target_date": "2026-11-13",
                "calendar_id": locale_names.DEFAULT_LOCAL_CALENDAR_ID,
                "priority": "normal",
                "status": "pending",
            }
        ],
        [
            {
                "id": locale_names.DEFAULT_LOCAL_CALENDAR_ID,
                "name": "기본",
                "color": "#3366cc",
                "type": "local",
                "is_visible": 1,
            }
        ],
        created_at=datetime(2026, 11, 13, 9, 0),
    )
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "locale.pdf"))
    calendar_print_renderer.configure_printer(
        printer, calendar_print_renderer.CalendarPrintRenderOptions(document_title="Test")
    )
    drawn: list[str] = []
    original = calendar_print_renderer._RenderContext.draw_text

    def recording(self, rect, text, *args, **kwargs):
        drawn.append(text)
        return original(self, rect, text, *args, **kwargs)

    with (
        patch.object(calendar_print_renderer._RenderContext, "draw_text", recording),
        patch.object(locale_names, "t", side_effect=lambda key, default=None: "Standard"),
    ):
        calendar_print_renderer.render_calendar_document(printer, document)

    for name in _standalone_names(locale, SHORT):
        assert name in drawn
    assert "Standard" in drawn
    assert "기본" not in drawn


def test_default_local_calendar_name_follows_ui_language_on_render_records():
    calendars = [
        {"id": locale_names.DEFAULT_LOCAL_CALENDAR_ID, "name": "기본", "type": "local"},
        {"id": "local::work", "name": "업무", "type": "local"},
    ]
    tasks = [
        {"id": 1, "name": "a", "calendar_id": locale_names.DEFAULT_LOCAL_CALENDAR_ID},
        {"id": 2, "name": "b", "calendar_id": "local::work"},
    ]
    with patch.object(locale_names, "t", side_effect=lambda key, default=None: "Default"):
        records = month_renderer._prepare_calendar_display_rows(tasks, calendars)
    assert [row["_calendar_name"] for row in records] == ["Default", "업무"]


class NavigationChevronDirectionTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self._original_locale = QLocale()
        self._original_direction = self.qt_app.layoutDirection()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "settings.ini"), QSettings.Format.IniFormat
        )
        self.settings.setFallbacksEnabled(False)
        self.settings.setValue("gcal_enabled", False)
        for target in (
            "calendar_app.shared.theme_settings.QSettings",
            "calendar_app.shared.theme_snapshot.QSettings",
        ):
            self.enterContext(patch(target, return_value=self.settings))
        month_renderer.invalidate_calendar_meta_cache()

    def tearDown(self):
        QLocale.setDefault(self._original_locale)
        self.qt_app.setLayoutDirection(self._original_direction)
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def _nav_icon_keys(self, code):
        I18nManager._apply_qt_locale(code)
        issued = {}

        def fake_icon(key, *_args, **_kwargs):
            icon = QIcon(QPixmap(4, 4))
            issued[icon.cacheKey()] = key
            return icon

        host = CalendarRenderHost(self.settings)
        try:
            with (
                patch.object(month_renderer, "_ic", side_effect=fake_icon),
                patch.object(month_renderer, "_get_subscription_events", return_value=[]),
            ):
                month_renderer.render_calendar(host)
            toolbar = host.calendar_toolbar_widget
            previous = toolbar.findChild(QPushButton, "calendar_previous")
            following = toolbar.findChild(QPushButton, "calendar_next")
            return (
                issued[previous.icon().cacheKey()],
                issued[following.icon().cacheKey()],
                previous.isRightToLeft(),
            )
        finally:
            host.close()
            host.deleteLater()
            self.qt_app.processEvents()

    def test_arabic_previous_points_right_and_next_points_left(self):
        previous, following, right_to_left = self._nav_icon_keys("ar")
        self.assertTrue(right_to_left)
        self.assertEqual((previous, following), (ICON.NAV_NEXT, ICON.NAV_PREV))

    def test_left_to_right_chevrons_are_unchanged(self):
        previous, following, right_to_left = self._nav_icon_keys("en")
        self.assertFalse(right_to_left)
        self.assertEqual((previous, following), (ICON.NAV_PREV, ICON.NAV_NEXT))
