# Air Calendar 3.7.1 Deploy Checklist

**Date:** 2026-09-15
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [x] Full 746-test automated suite passes on Python 3.13.15.
- [x] Ruff, encoding guard, JSON parsing, release environment, and diff checks pass.
- [x] Print layout, language restart, window layout, widget state, and product rename contracts have regression tests.
- [x] Existing Store identity and settings namespace remain compatible with current purchasers.
- [x] The owner requested deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged payload passes the locked-license and sensitive-file verifier.
- [x] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.1.0`, architecture `x64`; public display name is `Air Calendar`.
- [x] Foreign ICU DLLs from development tools are excluded and rejected by the compliance gate.
- [x] The packaged executable starts without a QtCore DLL import failure.

## External release

- [ ] Push the versioned 3.7.1 source and immutable `v3.7.1` tag.
- [ ] Publish the matching source ZIP, MSIX, Store upload, and checksums on GitHub.
- [ ] Confirm the GitHub release and public source links resolve.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.1` and the `v3.7.1` release URL.
- [ ] Submit the verified x64 upload through Partner Center.

## Post-deploy

- [ ] Verify the installed package launches, prints, exits, and restores its last layout.
- [ ] Verify language restart preserves panels, widgets, settings, and individual widget positions.
- [ ] Monitor GitHub Actions and Microsoft Store certification feedback.

## Rollback triggers

- The packaged application cannot launch or exit cleanly.
- QtCore or another packaged DLL fails to load.
- Printed multi-day events are duplicated or overflow details are missing.
- Language restart loses the last window layout or widget state.
- The release does not expose the GPLv3 terms and matching source archive.
