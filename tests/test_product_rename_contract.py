# -*- coding: utf-8 -*-
from pathlib import Path
import xml.etree.ElementTree as ET

from calendar_app.app_metadata import (
    APP_AUTHOR,
    APP_EXECUTABLE_NAME,
    APP_LEGACY_NAME,
    APP_NAME,
    APP_PACKAGE_IDENTITY_NAME,
    APP_SETTINGS_NAME,
)

ROOT = Path(__file__).resolve().parents[1]
_FOUNDATION_NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
_UAP_NS = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
_DESKTOP_NS = "http://schemas.microsoft.com/appx/manifest/desktop/windows10"
_PUBLIC_BRANDING_FILES = (
    "pyproject.toml",
    "docs/index.html",
    "docs/promo.html",
    "docs/privacy.html",
    "docs/privacy-policy.ko.md",
    "docs/privacy-policy.en.md",
    "docs/desktop-calendar-widget-windows/index.html",
    "docs/google-calendar-desktop-overlay/index.html",
    "docs/dday-countdown-widget-windows/index.html",
    "docs/pomodoro-calendar-workflow/index.html",
)
_LEGACY_PERSON_NAMES = ("김효진", "Hyojin Kim", "Kim Hyojin", "Kim,hyojin")


def test_public_product_name_is_air_calendar():
    assert APP_NAME == "Air Calendar"
    assert APP_LEGACY_NAME == "Dark Calendar"
    assert APP_AUTHOR == "Zinz-Soft"


def test_public_branding_surfaces_use_zinz_soft_instead_of_a_person_name():
    for relative_path in _PUBLIC_BRANDING_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8", errors="strict")
        assert "Zinz-Soft" in text, relative_path
        for legacy_name in _LEGACY_PERSON_NAMES:
            assert legacy_name not in text, f"{relative_path}: {legacy_name}"


def test_rebrand_keeps_existing_settings_and_store_update_identity():
    root = ET.parse(ROOT / "AppxManifest.xml").getroot()
    identity = root.find(f"{{{_FOUNDATION_NS}}}Identity")
    properties = root.find(f"{{{_FOUNDATION_NS}}}Properties")
    application = root.find(f"{{{_FOUNDATION_NS}}}Applications/{{{_FOUNDATION_NS}}}Application")
    visual = application.find(f"{{{_UAP_NS}}}VisualElements")
    startup = application.find(
        f"{{{_FOUNDATION_NS}}}Extensions/{{{_DESKTOP_NS}}}Extension/{{{_DESKTOP_NS}}}StartupTask"
    )

    assert APP_SETTINGS_NAME == "Dark Calendar"
    assert identity.attrib["Name"] == APP_PACKAGE_IDENTITY_NAME == "Kimhyojin.DarkCalendar"
    assert application.attrib["Executable"] == APP_EXECUTABLE_NAME == "DarkCalendar.exe"
    assert properties.find(f"{{{_FOUNDATION_NS}}}DisplayName").text == APP_NAME
    # Partner Center validates this technical manifest field against the
    # immutable publisher display name registered for the existing product.
    assert properties.find(f"{{{_FOUNDATION_NS}}}PublisherDisplayName").text == "Kim,hyojin"
    assert visual.attrib["DisplayName"] == APP_NAME
    assert startup.attrib["TaskId"] == "DarkCalendarStartup"
    assert startup.attrib["DisplayName"] == APP_NAME


def test_windows_file_metadata_uses_new_public_name_but_stable_filename():
    metadata = (ROOT / "version_info.txt").read_text(encoding="utf-8", errors="strict")

    assert "StringStruct('FileDescription', 'Air Calendar')" in metadata
    assert "StringStruct('ProductName', 'Air Calendar')" in metadata
    assert "StringStruct('InternalName', 'DarkCalendar')" in metadata
    assert "StringStruct('OriginalFilename', 'DarkCalendar.exe')" in metadata
    assert "StringStruct('CompanyName', 'Zinz-Soft')" in metadata
    assert "StringStruct('LegalCopyright', '(c) Zinz-Soft')" in metadata
