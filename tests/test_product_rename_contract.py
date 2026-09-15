# -*- coding: utf-8 -*-
from pathlib import Path
import xml.etree.ElementTree as ET

from calendar_app.app_metadata import (
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


def test_public_product_name_is_air_calendar():
    assert APP_NAME == "Air Calendar"
    assert APP_LEGACY_NAME == "Dark Calendar"


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
    assert visual.attrib["DisplayName"] == APP_NAME
    assert startup.attrib["TaskId"] == "DarkCalendarStartup"
    assert startup.attrib["DisplayName"] == APP_NAME


def test_windows_file_metadata_uses_new_public_name_but_stable_filename():
    metadata = (ROOT / "version_info.txt").read_text(encoding="utf-8", errors="strict")

    assert "StringStruct('FileDescription', 'Air Calendar')" in metadata
    assert "StringStruct('ProductName', 'Air Calendar')" in metadata
    assert "StringStruct('InternalName', 'DarkCalendar')" in metadata
    assert "StringStruct('OriginalFilename', 'DarkCalendar.exe')" in metadata
