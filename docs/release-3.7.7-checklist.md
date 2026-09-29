# Air Calendar 3.7.7 Deploy Checklist

**Date:** 2026-09-29
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [x] All 121 test files pass in independent processes, excluding only the version-surface check that requires 3.7.7 metadata.
- [x] The official Quality Gate, focused feature tests, Ruff, locale synchronization, encoding guard, and diff checks pass.
- [x] The release preflight validates Python 3.13.15 and all locked runtime/build dependencies.
- [x] The owner requested that the complete current development state be included in this deployment.
- [x] Runtime source and assets are included; local preview images under `artifacts/` are excluded.

## Build evidence

- [x] Rebuild the x64 executable payload from the validated 3.7.7 source.
- [x] Build and inspect the x64 MSIX, Store upload, corresponding-source ZIP, and SHA-256 files.
- [x] Verify package identity `Kimhyojin.DarkCalendar`, version `3.7.7.0`, architecture `x64`, display name `Air Calendar`, and publisher display name `Kim,hyojin`.
- [x] Confirm the Store upload contains the rebuilt x64 MSIX with a matching SHA-256 hash.

## External release

- [ ] Push the versioned 3.7.7 source and immutable `v3.7.7` tag.
- [ ] Confirm Build Release, Quality Gate, Encoding Policy, and Pages workflows succeed.
- [ ] Confirm the GitHub release and every public release asset resolve successfully.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.7` and links to `v3.7.7`.
- [ ] Submit the verified Store upload through Partner Center only when certification submission is explicitly authorized.

## Post-deploy

- [ ] Compare freshly downloaded public asset hashes with the generated release hashes.
- [ ] Verify the public release notes and GPL corresponding-source link.
- [ ] Check the installed Microsoft Store package version separately from the GitHub release.

## Rollback triggers

- The rebuilt application cannot launch or exit cleanly.
- Existing user settings, layouts, widgets, or calendar data fail to load.
- Packaged widget illustration, sound, or launcher assets are missing.
- QtCore or another required packaged DLL fails to load.
- The public release does not expose GPLv3 terms and the matching corresponding-source archive.
