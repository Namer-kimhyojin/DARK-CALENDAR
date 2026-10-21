# -*- coding: utf-8 -*-
"""Parse untrusted calendars with a timezone cache owned by one parse.

icalendar 7.2.0 exposes parser hooks but its default implementation still uses
the process-wide TZP cache. These two hooks retain the library's parser and
forward-reference handling while preventing one feed from defining another
feed's custom TZID. Keep the exact dependency pin and review these hooks before
upgrading; an unexpected parser version fails closed.
"""

import icalendar
from icalendar.parser.ical.calendar import CalendarIcalParser
from icalendar.timezone.tzp import TZP


class _LocalTimezoneParser(CalendarIcalParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tzp = TZP()

    def handle_end_component(self, vals):
        if vals.upper() != "VTIMEZONE":
            return super().handle_end_component(vals)
        component = self.component
        if component is None or component.name != "VTIMEZONE":
            raise ValueError("Invalid timezone component")
        # The superclass only uses this argument to decide whether to cache a
        # timezone globally; the component keeps its original VTIMEZONE name.
        super().handle_end_component("")
        if "TZID" in component:
            self._tzp.cache_timezone_component(component)

    def parse_and_add_property(self, name, params, val, tzid, line):
        timezone = self._tzp.timezone(tzid) if tzid else None
        # DATE values have no timezone. vDDDTypes' DATE branch expects a name,
        # while its datetime/period branches accept a resolved tzinfo directly.
        if len(val) == 8 and val.isdigit():
            timezone = None
        return super().parse_and_add_property(name, params, val, timezone, line)


class _LocalTimezoneCalendar(icalendar.Calendar):
    @classmethod
    def _get_ical_parser(cls, data):
        return _LocalTimezoneParser(data, cls._get_component_factory(), cls.types_factory)


def parse_calendar(data):
    """Use the existing parser without reading or populating its global TZ cache."""
    if icalendar.__version__ != "7.2.0":
        raise ImportError("Unsupported iCalendar parser API")
    # The library also accepts local filenames as strings. Network response
    # content must always be parsed as content, never probed or opened as a path.
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    if not isinstance(data, bytes):
        raise ValueError("Invalid calendar data type")
    return _LocalTimezoneCalendar.from_ical(data)
