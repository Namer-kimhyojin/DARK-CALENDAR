# Dark Calendar 3.6.9 Deploy Checklist

**Date:** 2026-09-15
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/ARM64 after native validation

## Pre-deploy

- [x] Full automated test suite passes on the release worktree.
- [x] Ruff, encoding guard, release environment checks, and diff checks pass.
- [x] Tray auto-start icon and top/tray state synchronization have regression tests.
- [x] Window layout, widget settings, and individual widget position persistence have round-trip tests.
- [x] The owner requested deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged manifest contains the `DarkCalendarStartup` Windows startup task.
- [x] Packaged payload contains the Python/WinRT runtime and passes the locked-license verifier.
- [x] Packaged executable passes the local smoke launch.

## External release

- [ ] Push the versioned 3.6.9 source and immutable `v3.6.9` tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Confirm GitHub Pages serves `appVersion=3.6.9` and the `v3.6.9` release URL.
- [ ] Run a clean-profile installation and Windows Startup Apps smoke test.
- [ ] Submit the verified x64/ARM64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify login launch, last window position, saved layout, individual widget positions, tray behavior, and calendar rendering.
- [ ] Confirm Store package version and matching corresponding-source link.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.

## Rollback triggers

- Startup registration is missing from the packaged manifest or cannot be disabled.
- Last window position, saved layout, or an individual widget position regresses after relaunch.
- GitHub release does not expose the GPLv3 terms or matching source archive.
- Packaged application cannot launch or exit cleanly.
