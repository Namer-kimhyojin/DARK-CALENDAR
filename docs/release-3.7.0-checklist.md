# Dark Calendar 3.7.0 Deploy Checklist

**Date:** 2026-09-15
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/ARM64 after native validation

## Pre-deploy

- [x] Full automated test suite passes on the release checkout.
- [x] Ruff, encoding guard, release environment checks, and diff checks pass.
- [x] Widget-mode layout, typography, opacity, visibility, preset, and template validation have regression tests.
- [x] Shutdown, tray, window layout, widget state, and individual widget position persistence have regression tests.
- [x] The owner requested commit and deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged payload passes the locked-license and sensitive-file verifier.
- [x] Package identity is `Kimhyojin.DarkCalendar`, version `3.7.0.0`, architecture `x64`.
- [x] The pipeline rejects release packaging outside the CI-tested Python 3.13.15 ABI.
- [ ] The Python 3.13.15 CI packaged executable passes the launch/exit smoke test.

## External release

- [ ] Push the versioned 3.7.0 source and immutable `v3.7.0` tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Confirm GitHub Pages serves `appVersion=3.7.0` and the `v3.7.0` release URL.
- [ ] Submit the verified x64/ARM64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify widget-only relaunch, layout switching, calendar/list rendering, preset application, and opacity preview.
- [ ] Verify clean exit, language restart, saved window layout, and individual widget positions.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.

## Rollback triggers

- The packaged application cannot launch or exit cleanly.
- Widget-only mode, monthly calendar, schedule list, or preset editor does not render.
- Saved layout, opacity, typography, or individual widget position regresses after relaunch.
- GitHub release does not expose the GPLv3 terms or matching source archive.
