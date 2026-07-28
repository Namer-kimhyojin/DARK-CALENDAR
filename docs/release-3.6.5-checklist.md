# Dark Calendar 3.6.5 Deploy Checklist

**Date:** 2026-07-29
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/arm64 after native validation

## Pre-deploy

- [x] Application, package, website, source-offer, and Store guide versions set to 3.6.5.
- [x] Runtime and build environments match the exact dependency locks.
- [x] GPL-3.0-only license, third-party notices, and corresponding-source automation are present.
- [x] GitHub tag workflow uses the unified `build-release.bat` entrypoint.
- [x] Encoding guard and release-compliance tests pass.
- [x] Full automated test suite passes (516 tests, 7 subtests).
- [x] x64 payload, MSIX, Store upload, and corresponding-source ZIP build successfully.
- [x] Packaged executable remains healthy through an 8-second local smoke launch.
- [ ] Code review/owner approval is recorded.

## Build evidence

- MSIX SHA-256: publish `DarkCalendar-3.6.5-x64.msix.sha256`.
- Store upload SHA-256: publish `DarkCalendar-3.6.5.0-x64.msixupload.sha256`.
- Corresponding source SHA-256: publish `DarkCalendar-3.6.5-corresponding-source.zip.sha256`.

## External release

- [ ] Create and push immutable `v3.6.5` source tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Publish the 3.6.5 GitHub Pages homepage after the release URL resolves.
- [ ] Run a clean-profile installation smoke test.
- [ ] Configure Partner Center separate terms as GPL-3.0-only.
- [ ] Submit the verified x64/arm64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify install, launch, tray behavior, notification sound, source menu, and license menu.
- [ ] Confirm Store package version and matching corresponding-source link.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.
- [ ] Keep the corresponding source available for as long as the binary is offered.

## Rollback triggers

- GitHub release does not expose the GPLv3 terms or matching source archive.
- Corresponding-source archive is missing, corrupt, or version-mismatched.
- Packaged application cannot launch or exit cleanly.
- Core calendar, task, Google sync, panel, or overlay-widget flows fail.
