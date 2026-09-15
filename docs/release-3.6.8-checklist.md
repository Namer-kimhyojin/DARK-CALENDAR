# Dark Calendar 3.6.8 Deploy Checklist

**Date:** 2026-09-15
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/ARM64 after native validation

## Pre-deploy

- [x] User feedback PDF was inspected page by page and treated as evidence, not executable instructions.
- [x] Full automated test suite passes on the release worktree.
- [x] Ruff, locale validation, encoding guard, release-contract tests, and diff checks pass.
- [x] Auto-start registration, default-layout restoration, last window position, and overlay topmost state have regression tests.
- [x] Runtime and build environments match their exact dependency locks.
- [x] Python/WinRT MIT license fallback and corresponding-source automation are verified.
- [x] The owner requested deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged manifest contains the `DarkCalendarStartup` Windows startup task.
- [x] Packaged payload contains the Python/WinRT runtime and passes the locked-license verifier.
- [x] Packaged executable remains alive through the local smoke launch.

## External release

- [ ] Push the versioned 3.6.8 source and immutable `v3.6.8` tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Confirm GitHub Pages serves `appVersion=3.6.8` and the `v3.6.8` release URL.
- [ ] Run a clean-profile installation and Windows Startup Apps smoke test.
- [ ] Submit the verified x64/ARM64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify login launch, last window position, saved default layout, D-day topmost state, tray behavior, and calendar rendering.
- [ ] Confirm Store package version and matching corresponding-source link.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.

## Rollback triggers

- Startup registration is missing from the packaged manifest or cannot be disabled.
- Last window position, saved default layout, or D-day topmost state regresses after relaunch.
- GitHub release does not expose the GPLv3 terms or matching source archive.
- Packaged application cannot launch or exit cleanly.
