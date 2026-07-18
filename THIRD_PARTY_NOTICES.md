# Third-Party Notices

Dark Calendar includes third-party software. `requirements-runtime.lock` is the authoritative runtime version list. Each binary payload also contains:

- `THIRD_PARTY_MANIFEST.json` — exact package versions and license-file hashes
- `THIRD_PARTY_LICENSES/` — license texts copied from every locked distribution
- `SOURCE_OFFER.md` — version-specific corresponding-source instructions

This summary does not replace the bundled license texts.

| Component | Release version | License | Project |
|---|---:|---|---|
| PyQt6 | 6.10.2 | GPL-3.0-only | <https://www.riverbankcomputing.com/software/pyqt/> |
| Qt libraries from PyQt6-Qt6 | 6.10.2 | LGPLv3 and component-specific terms | <https://www.qt.io/> |
| PyQt6-sip | 13.11.1 | BSD-2-Clause | <https://github.com/Python-SIP/sip> |
| QtAwesome | 1.4.2 | MIT; bundled icon fonts use the licenses below | <https://github.com/spyder-ide/qtawesome> |
| Google API Client for Python | 2.191.0 | Apache-2.0 | <https://github.com/googleapis/google-api-python-client> |
| google-auth | 2.48.0 | Apache-2.0 | <https://github.com/googleapis/google-auth-library-python> |
| httplib2 | 0.31.2 | MIT | <https://github.com/httplib2/httplib2> |
| requests-oauthlib | 2.0.0 | ISC | <https://github.com/requests/requests-oauthlib> |
| tzdata | 2026.3 | Apache-2.0; IANA timezone data terms also apply | <https://github.com/python/tzdata> |
| icalendar | 7.2.0 | BSD-family license | <https://github.com/collective/icalendar> |
| pywin32 | 311 | PSF-style licenses | <https://github.com/mhammond/pywin32> |
| MET Norway Locationforecast | API data | CC BY 4.0 / NLOD 2.0 | <https://api.met.no/doc/License> |
| GeoNames cities15000 | 2026-07-18 snapshot | CC BY 4.0 | <https://www.geonames.org/export/> |

All transitive Python packages and their exact versions are recorded in the payload manifest rather than duplicated in this overview.

## Qt and PyQt

The free edition of PyQt6 is GPLv3. Dark Calendar is therefore distributed as a GPLv3-covered work. The complete corresponding-source release asset mirrors the exact PyQt6 source and the applicable QtBase source, along with the application source and the remaining locked Python source distributions.

Dark Calendar 3.6.1 uses the native Windows notification sound API. Qt Multimedia and its FFmpeg runtime, along with unused Qt PDF and SVG image plugins, are intentionally excluded from the release payload.

## QtAwesome bundled fonts

QtAwesome 1.4.2 bundles these font families. The payload's `THIRD_PARTY_LICENSES/common/` directory contains the common MIT, Apache-2.0, SIL OFL-1.1, and CC BY 4.0 license texts.

| Font asset | Bundled version | License |
|---|---:|---|
| Font Awesome 5 Free | 5.15.4 | SIL OFL 1.1 for fonts; CC BY 4.0 for icons; MIT for code |
| Font Awesome 6 Free | 6.7.2 | SIL OFL 1.1 for fonts; CC BY 4.0 for icons; MIT for code |
| Elusive Icons | 2.0 | SIL OFL 1.1 |
| Material Design Icons | 5.9.55 / 6.9.96 | Apache-2.0 |
| Phosphor Icons | 1.3.0 | MIT |
| Remix Icon | 2.5.0 | Apache-2.0 |
| Microsoft Codicons | 0.0.36 | CC BY 4.0 attribution terms described by QtAwesome |

## Weather data

Weather and location provider attribution remains visible in the application. Provider attribution is not replaced by this document.

## Release verification

`scripts/release_compliance.py` must pass both environment and payload verification before an MSIX is packaged. Do not publish a binary if the runtime lock, bundled manifest, corresponding-source archive, or license directory is missing.
