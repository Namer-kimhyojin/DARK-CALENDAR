# Air Calendar 3.7.4 Deploy Checklist

**Date:** 2026-09-17
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [ ] Full automated test suite passes in the release checkout.
- [ ] Ruff, formatting, locale JSON, encoding guard, release preflight, and diff checks pass.
- [ ] Enhanced help center, guided Windows startup recovery, widget mode, theme, and calendar regressions are covered by focused tests.
- [ ] Existing Store identity, settings namespace, and user database compatibility remain unchanged.
- [x] The owner requested build, local installation, and deployment in this task.

## Build evidence

- [ ] A clean x64 executable payload is rebuilt from source rather than reusing an older payload.
- [ ] x64 MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [ ] Packaged payload passes locked-license, required-DLL, and sensitive-file verification.
- [ ] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.4.0`, architecture `x64`; public display name is `Air Calendar`.
- [ ] The rebuilt executable displays the enhanced help center and guided startup recovery UI.

## External release

- [ ] Push the versioned 3.7.4 source and immutable `v3.7.4` tag.
- [ ] Publish the matching source ZIP, MSIX, Store upload, and checksums on GitHub.
- [ ] Confirm the GitHub release and every public release asset resolve successfully.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.4` and links to `v3.7.4`.
- [ ] Submit the verified Store upload through Partner Center when certification deployment is intended.

## Post-deploy

- [ ] Verify the locally installed or launched 3.7.4 package reports the expected version.
- [ ] Verify F1 opens the enhanced help center and the startup failure dialog exposes the Windows Settings action.
- [ ] Confirm launch, tray lifecycle, window restore, and user settings remain functional.
- [ ] Monitor GitHub Actions and Microsoft Store certification feedback.

## Rollback triggers

- The rebuilt application cannot launch or exit cleanly.
- The packaged help center or startup recovery flow is older than the verified source behavior.
- Existing user settings, layouts, widgets, or calendar data fail to load.
- QtCore or another required packaged DLL fails to load.
- The public release does not expose GPLv3 terms and the matching corresponding-source archive.
