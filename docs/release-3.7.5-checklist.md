# Air Calendar 3.7.5 Deploy Checklist

**Date:** 2026-09-17
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [x] All 113 test files pass in independent processes.
- [x] The release preflight validates Python 3.13.15 and all locked runtime/build dependencies.
- [x] Ruff, locale synchronization, encoding guard, and diff checks pass for the release scope.
- [x] Existing Store identity, settings namespace, startup task ID, and user database compatibility remain unchanged.
- [x] The owner requested deployment of the integrated fixes.

## Build evidence

- [x] A clean x64 executable payload is rebuilt from source rather than reusing an older payload.
- [x] x64 MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged payload passes locked-license, required-DLL, and sensitive-file verification.
- [x] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.5.0`, architecture `x64`; public display name and publisher are `Air Calendar` and `Zinz-Soft`.
- [x] The Store upload contains exactly the rebuilt x64 MSIX with a matching SHA-256 hash.

## External release

- [ ] Push the versioned 3.7.5 source and immutable `v3.7.5` tag.
- [ ] Publish the matching source ZIP, MSIX, Store upload, and checksums on GitHub.
- [ ] Confirm the GitHub release and every public release asset resolve successfully.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.5` and links to `v3.7.5`.
- [ ] Submit the verified Store upload through Partner Center when certification deployment is intended.

## Post-deploy

- [ ] Confirm Build Release, Quality Gate, Encoding Policy, and Pages workflows succeed.
- [ ] Verify the published asset checksums against freshly downloaded release files.
- [ ] Verify the public release notes and GPL corresponding-source link.
- [ ] Monitor Microsoft Store certification feedback after Partner Center submission.

## Rollback triggers

- The rebuilt application cannot launch or exit cleanly.
- Calendar surfaces or toolbar controls regress to unreadable contrast.
- Existing user settings, layouts, widgets, or calendar data fail to load.
- QtCore or another required packaged DLL fails to load.
- The public release does not expose GPLv3 terms and the matching corresponding-source archive.
