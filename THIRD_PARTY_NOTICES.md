# Third-Party Notices

Dark Calendar includes or depends on third-party software. The release build must preserve the license files shipped by each dependency. This notice is a summary and does not replace those license texts.

| Component | Version policy | License | Project |
|---|---:|---|---|
| PyQt6 | 6.10.2 | GPL-3.0-only | <https://www.riverbankcomputing.com/software/pyqt/> |
| Qt 6 libraries from PyQt6-Qt6 | 6.10.2 package | LGPLv3 and component-specific terms | <https://www.qt.io/> |
| PyQt6-sip | matching installed version | BSD-2-Clause | <https://github.com/Python-SIP/sip> |
| QtAwesome | 1.4.2 or later | MIT; bundled icon fonts have their own licenses | <https://github.com/spyder-ide/qtawesome> |
| Google API Client for Python | 2.191.0 | Apache-2.0 | <https://github.com/googleapis/google-api-python-client> |
| google-auth packages | versions in `requirements.txt` | Apache-2.0 | <https://github.com/googleapis/google-auth-library-python> |
| httplib2 | 0.31.2 | MIT | <https://github.com/httplib2/httplib2> |
| requests-oauthlib | 2.0.0 | ISC | <https://github.com/requests/requests-oauthlib> |
| tzdata | installed release version | Apache-2.0; timezone data has separate terms | <https://github.com/python/tzdata> |
| icalendar | 5.0 or later | BSD-family license | <https://github.com/collective/icalendar> |
| pywin32 | 311 where applicable | PSF | <https://github.com/mhammond/pywin32> |
| MET Norway Locationforecast | API data | CC BY 4.0 / NLOD 2.0 | <https://api.met.no/doc/License> |
| GeoNames cities15000 | 2026-07-18 snapshot | CC BY 4.0 | <https://www.geonames.org/export/> |

## Qt and PyQt

The free edition of PyQt6 is GPLv3. Dark Calendar is therefore distributed as a GPLv3-covered work. Qt libraries included by the PyQt6 wheel are provided separately under their applicable Qt open-source licenses. A release must include the license materials installed with PyQt6, PyQt6-Qt6, PyQt6-sip, and QtAwesome.

## Weather data

Weather and location providers require their own attribution in the user interface. Provider attribution is not replaced by this document.

## Release verification

Before publishing a binary, regenerate the dependency inventory from the clean build environment and verify that this file matches the versions actually packaged.
