# Dark Calendar 3.6.7 Deploy Checklist

**Date:** 2026-08-15
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/ARM64 after native validation

## Pre-deploy

- [x] Release pipeline environment matches the exact runtime and build dependency locks.
- [x] Full automated test suite passes on the release worktree.
- [x] Ruff, locale structure/placeholder validation, encoding guard, formatting, and diff checks pass.
- [x] Database migrations for focus-log indexing and Google delete-queue uniqueness are covered by regression tests.
- [x] New application and test files are tracked for the matching corresponding-source archive.
- [x] GPL-3.0-only license, third-party notices, and corresponding-source automation are present.
- [x] GitHub tag workflow uses the unified `build-release.bat` entrypoint.
- [x] The owner requested the deployment in this task.

## Build evidence

- [ ] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [ ] Packaged payload includes `Qt6PrintSupport.dll` and excludes prohibited Qt/FFmpeg modules.
- [ ] Corresponding-source archive contains the calendar range, focus-history, queue, and regression-test sources.
- [ ] Packaged executable remains alive through the local smoke launch.

## External release

- [ ] Push the versioned 3.6.7 source and immutable `v3.6.7` tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Confirm GitHub Pages serves `appVersion=3.6.7` and the `v3.6.7` release URL.
- [ ] Run a clean-profile installation smoke test.
- [ ] Configure Partner Center separate terms as GPL-3.0-only.
- [ ] Submit the verified x64/ARM64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify install, launch, tray behavior, multi-day creation, repeated-task editing, Google sync, printing/PDF, focus history, source menu, and license menu.
- [ ] Confirm Store package version and matching corresponding-source link.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.
- [ ] Keep the corresponding source available for as long as the binary is offered.

## Rollback triggers

- GitHub release does not expose the GPLv3 terms or matching source archive.
- Corresponding-source archive is missing, corrupt, or version-mismatched.
- Packaged application cannot launch or exit cleanly.
- Multi-day creation, repeat-series editing, Google delete outbox, or core calendar rendering fails.
- `Qt6PrintSupport.dll` is missing or calendar printing/PDF generation fails.
