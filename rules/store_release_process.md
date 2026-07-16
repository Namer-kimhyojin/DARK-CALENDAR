# Store Release Process

## Goal

Create a Windows Store upload package that:

- ships with a clean bundled database
- excludes local DB files, logs, Google credentials, and Google token files
- supports x64 and arm64 Store submission when both native MSIX packages exist

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
build-release.bat
```

Optional cleanup before release:

```bat
build-release.bat -PurgeLocalData
```

Native payload only, no MSIX/upload:

```bat
build-release.bat -SkipMsix
```

Preflight validation without changing version files or creating build output:

```bat
build-release.bat -ValidateOnly -Version 3.5.0 -PackageVersion 3.5.0.0 -ReleaseDate 2026-07-13 -Channel Stable
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

- `release\store\DarkCalendar-3.5.0.0-arm64_x64.msixupload`

If only one native package is available, the scripts fall back to:

- `release\store\DarkCalendar-3.5.0.0-x64.msixupload`
- `release\store\DarkCalendar-3.5.0.0-arm64.msixupload`

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
