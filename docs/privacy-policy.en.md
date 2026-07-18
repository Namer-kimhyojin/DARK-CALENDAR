# Dark Calendar Privacy Policy

**Effective date: July 18, 2026**

Dark Calendar ("the App") is a Windows desktop calendar application developed and distributed by Hyojin Kim ("the Developer"). This policy explains how the App handles your information.

## 1. Summary

- **The Developer does not collect any personal data.** The App has no server, no account system, no analytics, and no advertising.
- All schedules, tasks, and settings you create are **stored only on your PC**.
- Data leaves your device only through features you explicitly enable (Google Calendar sync, weather widget, ICS subscriptions), and only to those service providers.

## 2. Data stored locally

The App stores the following on your PC under `%LOCALAPPDATA%\kimhyojin\Dark Calendar`:

| Data | Purpose |
|---|---|
| Schedule/task/checklist data (SQLite database) | Core calendar features |
| App settings (Windows registry `HKCU\Software\kimhyojin\Dark Calendar`) | Preserving theme, language, layout |
| Google auth token (`token.json`) — only if Google sync is enabled | Keeping sync signed in |
| Diagnostic log files | Troubleshooting |

This data is never transmitted to the Developer, and the Developer has no access to it.

## 3. Transfers to third-party services (only when you enable them)

### 3.1 Google Calendar sync
- When you sign in with your Google account, the App reads and writes your calendar events via the Google Calendar API.
- Recipient: Google LLC ([Google Privacy Policy](https://policies.google.com/privacy))
- Auth tokens are stored only on your PC and never sent to the Developer.
- When you disconnect, the App requests token revocation from Google and deletes the local token.
- The App's use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), **including the Limited Use requirements.**

### 3.2 Weather widget
- The **city name you type is searched locally** in the GeoNames city dataset bundled with the App and is not sent externally.
- The resulting latitude and longitude (rounded to four decimal places), together with standard web request information such as your IP address, may be sent to MET Norway ([api.met.no](https://api.met.no/)) to retrieve weather data. MET Norway stores API access logs in its own data center in Oslo, Norway.
- Weather data is provided under MET Norway's CC BY 4.0/NLOD 2.0 terms, and city data is provided by GeoNames under CC BY 4.0.
- Device location (GPS, etc.) is never collected or used.

### 3.3 ICS calendar subscriptions
- The App fetches events from ICS URLs you enter yourself. Standard web request information (such as your IP address) may be visible to the operator of that URL.

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
