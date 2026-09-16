# Air Calendar 3.7.2 Deploy Checklist

**Date:** 2026-09-16
**Target:** GitHub GPLv3 release and Windows x64 Store upload package

## Pre-deploy

- [x] Full automated test suite passes on Python 3.13.15.
- [x] Focused schedule information, calendar rendering, panel, theme, Ruff, and encoding checks pass.
- [x] Official `build-release.bat -ValidateOnly` preflight passes.
- [x] Existing Store identity and settings namespace remain compatible with current purchasers.
- [x] The owner requested deployment in this task.

## Build evidence

- [ ] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [ ] Packaged payload passes the locked-license and sensitive-file verifier.
- [ ] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.2.0`, architecture `x64`; public display name is `Air Calendar`.
- [ ] Packaged popup and detail-card code matches the tagged corresponding source.

## External release

- [ ] Push the versioned 3.7.2 source and immutable `v3.7.2` tag.
- [ ] Publish the matching source ZIP, MSIX, Store upload, and checksums on GitHub.
- [ ] Confirm the GitHub release and public source links resolve.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.2` and the `v3.7.2` release URL.
- [ ] Submit the verified x64 upload through Partner Center.

## Post-deploy

- [ ] Verify the installed package launches and the updated schedule popups behave correctly.
- [ ] Monitor GitHub Actions and Microsoft Store certification feedback.

## Rollback triggers

- The packaged application cannot launch or exit cleanly.
- Hover information and click details disagree or overlap.
- The bottom-row detail card is obscured by the taskbar.
- The release does not expose the GPLv3 terms and matching source archive.
