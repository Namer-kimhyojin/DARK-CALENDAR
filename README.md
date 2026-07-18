# Dark Calendar

Dark Calendar is a Windows desktop calendar, task workspace, and overlay-widget application.

## License

Dark Calendar is free software distributed under the **GNU General Public License v3.0 only** (`GPL-3.0-only`). See [LICENSE](LICENSE).

The application uses PyQt6, which is distributed by Riverbank Computing under GPLv3 or a commercial license. This repository uses the GPLv3 edition. Third-party components and their licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Corresponding source

- Source repository: <https://github.com/Namer-kimhyojin/DARK-CALENDAR>
- Source for release `3.6.0`: <https://github.com/Namer-kimhyojin/DARK-CALENDAR/tree/v3.6.0>
- Source availability notice: [SOURCE_OFFER.md](SOURCE_OFFER.md)

Each distributed binary must point to the tag matching that binary's version. The tag must contain the complete source and build scripts used for the release.

## Development

Requirements:

- Windows 10 or 11
- Python 3.12 or later

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe main.py
```

Run the test suite:

```powershell
.venv\Scripts\python.exe -m pytest tests
python scripts/run_encoding_guard.py
```

Build the Windows package:

```powershell
build-release.bat -Arch x64
```

The build pipeline and PyInstaller specifications in this repository are part of the Corresponding Source.

## Data and credentials

Google OAuth credentials and tokens are supplied by each user and are not included in the repository or release payload. Do not commit `credentials.json`, `token.json`, local databases, logs, signing certificates, or API keys.

## Warranty

This program is provided without warranty, to the extent permitted by applicable law. See the GPLv3 text for details.
