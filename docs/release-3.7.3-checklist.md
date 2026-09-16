# Air Calendar 3.7.3 Deploy Checklist

**Date:** 2026-09-17
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [x] Focused calendar visibility, database, integration, and UI tests pass.
- [x] Official quality gate, isolated Qt widget tests, Ruff checks, and encoding checks pass.
- [x] Official `build-release.bat -ValidateOnly` preflight passes.
- [x] Existing Store identity and settings namespace remain compatible with current purchasers.
- [x] The owner requested deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged payload passes the locked-license and sensitive-file verifier.
- [x] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.3.0`, architecture `x64`; public display name is `Air Calendar`.
- [x] Packaged calendar-visibility code matches the tagged corresponding source.

## External release

- [ ] Push the versioned 3.7.3 source and immutable `v3.7.3` tag.
- [ ] Publish the matching source ZIP, MSIX, Store upload, and checksums on GitHub.
- [ ] Confirm the GitHub release and public source links resolve.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.3` and the `v3.7.3` release URL.
- [ ] Submit the verified x64 upload through Partner Center.

## Post-deploy

- [ ] Verify the installed package launches and hidden calendars stay excluded from the main and Today views.
- [ ] Monitor GitHub Actions and Microsoft Store certification feedback.

## Rollback triggers

- The packaged application cannot launch or exit cleanly.
- A hidden calendar remains visible in the main calendar or `오늘 일정` panel.
- Changing calendar visibility does not refresh the affected views.
- The release does not expose the GPLv3 terms and matching source archive.
