# Store Release Process

## Goal

## Version numbering

Follow [versioning.md](versioning.md): each logical change (including scheduled
fixes) increments patch; a module addition/replacement/contract change or a new
Store release preparation increments minor and resets patch. A carry from minor
increments major. Register events with `scripts/manage_version.py`; reuse the
event ID and package on retries. Build preparation and upload retry are distinct.
Development versions can be newer than the last published website/Store version.

Public versions use one digit per component: `3.8.0`, `3.8.1`, ...,
`3.8.9`, `3.9.0`, ..., `3.9.9`, `4.0.0`. When patch reaches 9,
increment minor and reset patch; when minor reaches 9, increment major
and reset minor and patch. Store and Windows executable metadata retain
the required four-component form, for example `3.8.0.0`. Always increase
the numeric version; never rename an already published package.

## Package goals

Create a Windows Store upload package that:

- ships with a clean bundled database
- excludes local DB files, logs, Google credentials, and Google token files
- supports x64 and arm64 Store submission when both native MSIX packages exist

## Air Calendar Rebrand Compatibility

`Air Calendar` is the public product and package display name. The existing
Microsoft Store product identity remains `Kimhyojin.DarkCalendar`; the packaged
executable remains `DarkCalendar.exe`, and the startup task ID remains
`DarkCalendarStartup`. These are compatibility identifiers, not customer-facing
brand strings. Changing `Package/Identity/Name` requires a separate Store
product and breaks the existing package family, purchase entitlement, and
automatic-update chain.

The app, website, and ordinary author surfaces use the public brand `Zinz-Soft`.
The manifest's technical `PublisherDisplayName` is the exception: it must remain
`Kim,hyojin`, exactly matching the publisher display name registered for this
existing Partner Center product, or package validation will reject the upload.

For the existing Store product, always copy the identity values shown under
Partner Center > Product management > Product identity. Rename the listing by
reserving/selecting `Air Calendar` for every Store language, while keeping the
manifest identity and registered publisher display name unchanged.

## Files

- `build-release.bat` is the only release-build entrypoint.
- `scripts/build_pipeline.ps1` is its internal implementation and must not be run directly in normal use.
- `build_store.py` sanitizes the frozen payload and creates the clean bundled database.

## Native Build Rule

PyInstaller Store builds must stay native to the host architecture.

- x64 host: build `x64`
- arm64 host: build `arm64`

Cross-architecture packaging stays blocked by default because it can produce an
architecture-mismatched desktop executable inside the MSIX.

## One-Command Usage

Run this on the native build machine:

```bat
python -m pip install -r requirements-build.lock
build-release.bat
```

Optional local-state cleanup before release (never runs by default):

```bat
build-release.bat -ResetState
```

`-PurgeLocalData` implies reset and also removes the app's LOCALAPPDATA profile.
Use it only when that destructive cleanup is intentional.

Optional signing for direct sideload distribution:

```bat
build-release.bat -Sign -CertThumbprint <thumbprint>
```

Native payload only, no MSIX/upload:

```bat
build-release.bat -SkipMsix
```

Preflight validation without changing version files or creating build output:

```bat
build-release.bat -ValidateOnly -Version 4.3.3 -PackageVersion 4.3.3.0 -ReleaseDate 2026-10-19 -Channel Stable
```

## Surface Support

For Microsoft Surface users, provide arm64 in the Store submission whenever
possible.

Recommended flow:

1. Run `build-release.bat` on an x64 machine.
2. Run `build-release.bat` on an arm64 machine.
3. Once matching-version MSIX files exist under both `dist\x64` and `dist\arm64`, rerun:

```bat
build-release.bat -UploadOnly
```

That creates:

- `release\store\DarkCalendar-4.3.3.0-arm64_x64.msixupload`

If only one native package is available, the scripts fall back to:

- `release\store\DarkCalendar-4.3.3.0-x64.msixupload`
- `release\store\DarkCalendar-4.3.3.0-arm64.msixupload`

## Open-source compliance gate

Every release build verifies both lock files, copies license texts for every runtime package, removes unapproved Qt/FFmpeg modules, and generates:

- `THIRD_PARTY_MANIFEST.json` and `THIRD_PARTY_LICENSES/` inside the payload
- `release\source\DarkCalendar-4.3.3-corresponding-source.zip`

Do not submit the Store upload unless `scripts/release_compliance.py verify-payload` passes and the corresponding-source ZIP is attached to the matching GitHub release.

## Sanitized Payload Contents

The release payload keeps:

- `_internal\desk_calendar_default.db` with only schema and the default local calendar row

The release payload removes:

- `desk_calendar.db`
- `desk_calendar.db-shm`
- `desk_calendar.db-wal`
- `desk_calendar.log`
- `credentials.json`
- `token.json`


## Current Development Inputs

`run.bat` runs `.venv\Scripts\python.exe main.py` from the development directory.
Local release builds read the current build directory, including uncommitted
runtime changes. GitHub release builds read the pushed commit. Before creating
an isolated build directory, capture all current application code, assets,
translations and runtime entrypoints, including new files and deletions; do not
select only the files changed by the most recent feature task.

The release pipeline compares the frozen Python implementation and bundled
assets/locales with its current source through `verify_release_runtime.py`.
Any missing required module or changed implementation/resource stops packaging.
Corresponding-source collection includes new application modules and resources
even in a local build, while excluding unrelated untracked artifact folders.

For an isolated directory, `-PythonExecutable <absolute-path>` can use the same
verified interpreter as the development `run.bat` without linking `.venv` folders.

## Native startup and SQLite release gates

Before preflight, run the selected build Python with
`scripts/prepare_sqlite_build_runtime.py --arch x64 --directory build/python-sqlite-x64`
(use native arm64 when appropriate). The helper pins the official archive and
DLL hashes, copies the standard Python runtime into a private build cache and
reads locked packages from the selected environment without modifying it.
The pipeline uses that private Python and runs
`scripts/verify_sqlite_runtime.py --runtime`. `-ValidateOnly` validates an existing
prepared cache without creating a new one. After freezing it runs the verifier with
`--payload <DarkCalendar.exe directory>`. Both query the actual SQLite C exports
and native architecture. WAL releases require the official WAL-reset fix:
SQLite 3.51.3 or later, or backports 3.50.7 / 3.44.6 on those branches.
SQLite 3.50.4, withdrawn 3.52.0, unknown versions and failed DLL loads are blocked.
Do not bypass this gate with `-SkipNative` or substitute file-version metadata.
See the [SQLite WAL documentation](https://sqlite.org/wal.html#walreset).

Tag-based GitHub Actions creates a **draft** release candidate. Existing public
release assets must never be replaced; retries download same-name draft assets
and require SHA-256 equality with this build before uploading missing files.
Download failures or mismatches stop without replacing or mixing assets.
Download that exact candidate using existing authenticated
access, record its hashes, then run the native EXE with its bundled Python, Qt
and SQLite before GitHub publication or Store upload.

GitHub-hosted `windows-latest` provides a disposable VM for the native GUI gate;
`scripts/native_release_smoke.py` refuses local execution. CI records actual EXE
startup, normal UI exit/restarts, synthetic data preservation and screenshots.
A release reviewer must inspect those screenshots before promoting the draft.
The previous public baseline is pinned and checked by
`scripts/prepare_native_smoke_baseline.py`. These checks do not establish current
Store package-identity behavior or a real user's DB health.

Otherwise use an isolated VM, Sandbox or existing test account that protects QSettings,
the shared DB and real calendar accounts. Test both a fresh profile and a
consistent previous-version profile copy. For each, verify the main window,
fresh DB/tray/worker logs and two normal exit/restart cycles. Host-Python PYZ
tests and a responsive exception dialog are insufficient. If the required
environment or UI observation is unavailable, retain the draft and report the
gate pending. Publish the same verified candidate without rebuilding, then
download the public assets again and compare hashes. Store installation and
installed startup/restart remain separate checks.

Resolve the actual physical profile used by the packaged process. SQLite main,
WAL and SHM must belong to the same physical DB set. Do not independently merge
sidecars from legacy or virtualized profiles. Back up after normal shutdown or
with SQLite's backup API; keep raw DBs, recovery SQL and personal profiles outside
the repository. A successful private DB recovery does not prove a shipping fix.

Startup diagnostics preserve the original SQLite error and physical DB path.
On corruption, preserve the original instead of replacing it with the bundled
default DB. The deployment skill's read-only `installed-runtime-check.ps1` links
the observed PID, version, startup time and profile; one observation never
completes the full native startup/restart matrix.
