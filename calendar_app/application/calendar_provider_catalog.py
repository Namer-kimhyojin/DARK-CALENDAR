# -*- coding: utf-8 -*-
"""Service identities shared by connection UI and synchronization routing."""

CALDAV_SERVICES = ("icloud", "naver", "yahoo", "zoho", "fastmail")
PROVIDERS = ("google", "outlook", *CALDAV_SERVICES, "ics")
PROVIDER_NAMES = {
    "google": "Google Calendar",
    "outlook": "Outlook · Microsoft 365",
    "icloud": "iCloud",
    "naver": "네이버",
    "yahoo": "Yahoo Calendar",
    "zoho": "Zoho Calendar",
    "fastmail": "Fastmail",
    "ics": "ICS 구독",
}


def account_provider(account):
    """Unknown CalDAV accounts must never be routed to Outlook."""
    if account.startswith("caldav::"):
        service = account.split("::")[1]
        return service if service in CALDAV_SERVICES else "caldav"
    return "outlook"
