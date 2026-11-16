# Air Calendar Privacy Policy

**Effective date: November 16, 2026**

Air Calendar ("the App") is a Windows desktop calendar application developed and distributed by Zinz-Soft ("the Developer"). This policy explains how the App handles your information. The published version is [privacy.html](https://namer-kimhyojin.github.io/DARK-CALENDAR/privacy.html); this file is a Markdown copy with the same content.

## 1. Summary

- **The Developer does not collect any personal data.** The App has no server, no account system, no analytics, and no advertising.
- All schedules, tasks, and settings you create are **stored on your PC**. Enabling calendar sync also exchanges selected events with the chosen provider.
- Data leaves your device only through features you explicitly enable (Google and Outlook calendar connections, iCloud, Naver, Yahoo, Zoho and Fastmail CalDAV connections, weather and ICS subscriptions), and only to those service providers.
- The microphone is used only when you arm a microphone track in the loop mixer and start recording. Recordings stay on your PC and are never uploaded.

## 2. Data stored locally

The App stores the following on your PC under `%LOCALAPPDATA%\kimhyojin\Dark Calendar`:

| Data | Purpose |
|---|---|
| Schedule/task/checklist data (SQLite database) | Core calendar features |
| App settings (Windows registry `HKCU\Software\kimhyojin\Dark Calendar`) | Preserving theme, language, layout |
| Google auth token (`token.json`, stored encrypted) — only if Google sync is enabled | Keeping sync signed in |
| Outlook authentication cache and CalDAV credential files — when connected | Authentication protected with Windows DPAPI for the current user |
| Selected calendar event caches, link records, conflicts and deletion queues | Provider-specific sync, change comparison and safe retries |
| Loop mixer projects and recorded WAV clips (`loop-mixer` folder, or a location you choose when saving or exporting) | Saving and restoring loop mixer work |
| Diagnostic log files | Troubleshooting |

This data is never transmitted to the Developer, and the Developer has no access to it.

**Microphone**: the Microsoft Store package declares the microphone capability for loop mixer recording. Opening the loop mixer does not open the microphone; the App reads microphone input only after you arm a microphone track and start recording. Recordings are saved on your PC as part of the loop mixer project files above and are not sent to any server. You can block microphone access in the Windows privacy settings.

## 3. Transfers to third-party services (only when you enable them)

### 3.1 Google Calendar sync
- When you sign in with your Google account, the App reads and writes your calendar events via the Google Calendar API.
- Recipient: Google LLC ([Google Privacy Policy](https://policies.google.com/privacy))
- Auth tokens are stored only on your PC, encrypted with Windows DPAPI, and never sent to the Developer.
- When you disconnect, the App requests token revocation from Google and deletes the local token.
- The App's use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), **including the Limited Use requirements.**

### 3.2 Weather widget
- The **city name you type is searched locally** in the GeoNames city dataset bundled with the App and is not sent externally.
- The resulting latitude and longitude (rounded to four decimal places), together with standard web request information such as your IP address, may be sent to MET Norway ([api.met.no](https://api.met.no/)) to retrieve weather data. MET Norway stores API access logs in its own data center in Oslo, Norway.
- Weather data is provided under MET Norway's CC BY 4.0/NLOD 2.0 terms, and city data is provided by GeoNames under CC BY 4.0.
- Device location (GPS, etc.) is never collected or used.

### 3.3 ICS calendar subscriptions
- The App fetches events from ICS URLs you enter yourself. Standard web request information (such as your IP address) may be visible to the operator of that URL.

### 3.4 Outlook and Microsoft 365
- After sign-in and consent, Microsoft Graph reads selected calendar events and basic account details and updates writable events using Calendars.ReadWrite and User.Read.
- The authentication cache is encrypted with Windows DPAPI for the current user. Disconnecting deletes the local cache and deactivates this connection. Revoke server-side app access separately in your Microsoft account or organization's app management.

### 3.5 iCloud, Naver, Yahoo, Zoho and Fastmail CalDAV
- Your account, authentication password and calendar requests are sent over HTTPS directly to the CalDAV server of the selected service (Apple iCloud, Naver, Yahoo, Zoho or Fastmail). iCloud, Yahoo and Fastmail use an app-specific password; Zoho uses one when two-factor authentication is on. Zoho connects to the account data center server you select. Naver is read-only and availability depends on its service policy.
- Credentials are stored in separate files encrypted with Windows DPAPI for the current user, not as plaintext registry settings. Event bodies, ETags and link records are retained in the local sync cache.
- Disconnecting removes the local credential file and deactivates calendars without deleting remote events. You may also revoke app-specific passwords with the provider.

## 4. Retention and deletion

- All data remains on your PC until you delete it.
- **Disconnecting Google sync**: revokes and deletes the token. You can also revoke access anytime at [Google Account permissions](https://myaccount.google.com/permissions).
- **Full deletion**: uninstall the App, then delete the `%LOCALAPPDATA%\kimhyojin\Dark Calendar` folder to remove all data.

## 5. Children's privacy

The App collects no personal data and therefore collects no data from children.

## 6. Changes to this policy

If this policy changes, the updated version and effective date will be posted on this page.

## 7. Contact

Privacy inquiries: **aplus.mylife@gmail.com**
