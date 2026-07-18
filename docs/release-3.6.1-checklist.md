# Dark Calendar 3.6.1 Deploy Checklist

**Date:** 2026-07-18
**Target:** Microsoft Store, Windows x64 first; arm64 when built natively

## Pre-deploy

- [x] Application and website version surfaces set to 3.6.1.
- [x] Runtime packages pinned in `requirements-runtime.lock`.
- [x] PyQt6 GPLv3 and Qt LGPL source-bundle automation added.
- [x] Third-party license bundle and manifest automation added.
- [x] Qt Multimedia/FFmpeg and unused PDF/SVG plugins removed from release scope.
- [x] Clean locked environment installed and verified.
- [x] Full test suite and encoding guard pass (503 tests, 7 subtests).
- [x] x64 MSIX and `.msixupload` build pass.
- [x] Corresponding-source ZIP generated and verified (34 upstream archives).
- [x] Packaged executable remains healthy through an 8-second local smoke launch.
- [ ] Package smoke test passes on a separate clean Windows profile.
- [ ] Code review/owner approval recorded.

## Build evidence

- MSIX SHA-256: `E031370058B51BEF762EAD74BCAE9B1FDD442CA6E3C4D24D28FAEF8753032048`
- Store upload SHA-256: `0ED0B71EC1047AAD0B8A0F695FB5AD1BB5356F317A6868CD557D2D4B5E42061F`
- Corresponding source SHA-256: `BB8D1FFBA70585579A315D4C244AF53ED78D984D2670D9FFCD8A7A15B9CC8A30`

## External release

- [ ] Create immutable `v3.6.1` source tag.
- [ ] Publish the corresponding-source ZIP on the GitHub release.
- [ ] Configure Partner Center separate terms as GPL-3.0-only.
- [ ] Add the source URL and paid-open-source disclosure to the Store listing.
- [ ] Submit the verified `.msixupload` package.
- [ ] Publish the 3.6.1 homepage only after the GitHub release URL resolves.

## Post-deploy

- [ ] Confirm Store package version and source link.
- [ ] Verify install, launch, notification sound, source menu, and license menu.
- [ ] Monitor crash reports and Store certification feedback.
- [ ] Keep the corresponding source available for as long as the binary is offered.

## Rollback triggers

- Store package does not expose the GPLv3 terms or matching source link.
- Corresponding-source archive is missing, corrupt, or version-mismatched.
- Alarm notifications no longer produce the Windows notification sound.
- Core launch, calendar, task, or widget flow fails in the clean-profile smoke test.
