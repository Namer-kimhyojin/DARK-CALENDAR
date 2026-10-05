# Air Calendar 3.8.0 release validation

**Date:** 2026-10-05

Target: x64 / MSIX 3.8.0.0.

- [x] Confirm current `run.bat` entrypoint and full working-tree runtime inputs.
- [x] Confirm previous Store submission 24 is published; no duplicate draft existed.
- [x] Pass release preflight with the development Python and locked dependencies.
- [x] Preserve existing user preferences, account credentials and databases during sync regressions (419 tests passed).
- [x] Validate homepage rendering, new screenshots and image dimensions.
- [x] Build through `build-release.bat`; verify licenses, clean DB and frozen/source equivalence (263 modules, 203 resources).
- [x] Validate KeyDeck editing, rendering and serialization using code extracted from the package. Sync compiled implementations match current source.
- [ ] Commit/push the complete runtime inputs and publish v3.8.0 GitHub artifacts.
- [ ] Verify downloaded public package hashes, identity and corresponding source.
- [ ] Upload package and updated promotional art/screenshots; submit to the existing Store product.
- [ ] Confirm Store publication and installed Store update separately.

Live Google/Outlook/iCloud/Naver authentication is not established by fixture-based regression tests. Naver and ICS remain read-only; Outlook needs an administrator-registered client ID.
