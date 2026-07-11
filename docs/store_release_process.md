# Store Release Process

## Goal

Create a Windows Store upload package that:

- ships with a clean bundled database
- excludes local DB files, logs, Google credentials, and Google token files
- supports x64 and arm64 Store submission when both native MSIX packages exist

## Files

- `build_store.py`
  - creates `desk_calendar_default.db`
  - removes runtime state from a payload directory
  - copies the clean DB into the frozen runtime path `_internal/`
- `build.ps1`
  - builds a native-architecture MSIX payload
  - calls `build_store.py --prepare-only` so every Store build is sanitized
- `build-store-release.ps1`
  - runs the native build for the current host
  - creates a Store `.msixupload`
  - bundles x64 + arm64 automatically when the opposite architecture MSIX is already present
- `make-store-upload.ps1`
  - creates `x64`, `arm64`, or combined `x64 + arm64` Store upload files

## Native Build Rule

PyInstaller Store builds must stay native to the host architecture.

- x64 host: build `x64`
- arm64 host: build `arm64`

Cross-architecture packaging stays blocked by default because it can produce an
architecture-mismatched desktop executable inside the MSIX.

## One-Command Usage

Run this on the native build machine:

```powershell
.\build-store-release.ps1
```

Optional local-state cleanup before release (never runs by default):

```powershell
.\build-store-release.ps1 -ResetState
```

`-PurgeLocalData` implies reset and also removes the app's LOCALAPPDATA profile.
Use it only when that destructive cleanup is intentional.

Optional signing for direct sideload distribution:

```powershell
.\build-store-release.ps1 -Sign -CertThumbprint <thumbprint>
```

Native payload only, no MSIX/upload:

```powershell
.\build-store-release.ps1 -SkipMsix
```

## Surface Support

For Microsoft Surface users, provide arm64 in the Store submission whenever
possible.

Recommended flow:

1. Run `.\build-store-release.ps1` on an x64 machine.
2. Run `.\build-store-release.ps1` on an arm64 machine.
3. Once both `dist\x64\DarkCalendar-x64.msix` and `dist\arm64\DarkCalendar-arm64.msix` exist in the same workspace, rerun:

```powershell
.\make-store-upload.ps1
```

That creates:

- `release\store\DarkCalendar_arm64_x64.msixupload`

If only one native package is available, the scripts fall back to:

- `release\store\DarkCalendar_x64.msixupload`
- `release\store\DarkCalendar_arm64.msixupload`

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
