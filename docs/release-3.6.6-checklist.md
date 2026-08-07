# Dark Calendar 3.6.6 Deploy Checklist

**Date:** 2026-08-07
**Target:** GitHub GPLv3 release and Windows x64 package first; Microsoft Store/arm64 after native validation

## Pre-deploy

- [x] Release pipeline environment matches the exact runtime and build dependency locks.
- [x] Full automated test suite passes on the release worktree.
- [x] Ruff, locale structure/placeholder validation, focused compileall, and diff checks pass.
- [x] New application and test files are tracked for the matching corresponding-source archive.
- [x] GPL-3.0-only license, third-party notices, and corresponding-source automation are present.
- [x] GitHub tag workflow uses the unified `build-release.bat` entrypoint.
- [x] The owner requested the deployment in this task.

## Build evidence

- [x] x64 payload, MSIX, Store upload, corresponding-source ZIP, and SHA-256 files build successfully.
- [x] Packaged payload includes `Qt6PrintSupport.dll` and excludes prohibited Qt/FFmpeg modules.
- [x] Corresponding-source archive contains the new calendar printing and first-run source files.
- [x] Packaged executable remains alive through an 8-second local smoke launch.

### Local artifact hashes

- MSIX: `0D677F69F9B8D640A54A0C3D9EACCFD67212858161E45DDE1FBF1E045F012BD1`
- Store upload: `D0B206D4B54AF3F8B77EC81D2F8104BE2728E58B26E2453AB2CAB5C99DB29BD5`

## External release

- [ ] Commit and push the versioned 3.6.6 source.
- [ ] Create and push immutable `v3.6.6` source tag.
- [ ] Confirm GitHub Actions publishes the matching source ZIP, MSIX, Store upload, and checksums.
- [ ] Confirm the GitHub release notes and source links resolve publicly.
- [ ] Publish the 3.6.6 GitHub Pages homepage after the release URL resolves.
- [ ] Run a clean-profile installation smoke test.
- [ ] Configure Partner Center separate terms as GPL-3.0-only.
- [ ] Submit the verified x64/arm64 Store upload after both native packages are available.

## Post-deploy

- [ ] Verify install, launch, tray behavior, printing/PDF, focus fullscreen, source menu, and license menu.
- [ ] Confirm Store package version and matching corresponding-source link.
- [ ] Monitor crash reports, GitHub Actions, and Store certification feedback.
- [ ] Keep the corresponding source available for as long as the binary is offered.

## Rollback triggers

- GitHub release does not expose the GPLv3 terms or matching source archive.
- Corresponding-source archive is missing, corrupt, or version-mismatched.
- Packaged application cannot launch or exit cleanly.
- `Qt6PrintSupport.dll` is missing or calendar printing/PDF generation fails.
- Core calendar, task, Google sync, panel, focus, or overlay-widget flows fail.
