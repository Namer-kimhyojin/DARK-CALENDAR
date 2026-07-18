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
build-release.bat -ValidateOnly -Version 3.6.1 -PackageVersion 3.6.1.0 -ReleaseDate 2026-07-18 -Channel Stable
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

- `release\store\DarkCalendar-3.6.1.0-arm64_x64.msixupload`

If only one native package is available, the scripts fall back to:

- `release\store\DarkCalendar-3.6.1.0-x64.msixupload`
- `release\store\DarkCalendar-3.6.1.0-arm64.msixupload`

## Open-source compliance gate

Every release build verifies both lock files, copies license texts for every runtime package, removes unapproved Qt/FFmpeg modules, and generates:

- `THIRD_PARTY_MANIFEST.json` and `THIRD_PARTY_LICENSES/` inside the payload
- `release\source\DarkCalendar-3.6.1-corresponding-source.zip`

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
