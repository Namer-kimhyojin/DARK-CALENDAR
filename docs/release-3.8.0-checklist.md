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
- [x] Commit/push the complete runtime inputs and publish v3.8.0 GitHub artifacts (release commit `3c79853414b9eecce51165ae3bf08b246d1a6de6`).
- [x] Verify downloaded public package hashes, identity, PE version and corresponding source (263 modules, 203 resources). Four SVG/Markdown resources differ only by Git CRLF/LF conversion.
- [x] Run independent regressions against the public EXE's extracted code: 117 sync safety cases and 96 KeyDeck cases passed; native preferences preserved.
- [x] Upload verified public package and updated promotional art/screenshots; submit to existing product `9MXQ08RF22K8`. Submission 25 (`1152921505702046260`) was accepted on 2026-10-05 KST; portal phase is PreProcessing.
- [x] Verify saved 3.8.0 release notes, service requirements, two new promotional artworks and three new screenshots/captions across all 18 existing Store listing languages via a fresh portal CSV export. Captions stay associated with their image assets when Partner Center reorders reused images.
- [ ] Confirm Store publication and installed Store update separately.

GitHub release: https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v3.8.0

Public upload package SHA256: `1a04ef1994edc87cfd2ca364d0b577b4ef2caea92e27a539cbdf55c2ffd052eb`.

Public homepage and new media were checked after Pages publication. The currently installed Store version is 3.7.10.0; 3.8.0.0 installation awaits Microsoft certification and publication. Certification is configured to publish automatically after approval. Existing nightly maintenance should resume this submission, then use the official Store update after normal app exit; no duplicate submission is needed.

Evidence: `artifacts/deployment/3.8.0/20261005/public-verification.json`, `store-export-verification.json`, `store-submitted.jpg`, `homepage-public.jpg`, and the frozen sync/KeyDeck test logs.

Live Google/Outlook/iCloud/Naver authentication is not established by fixture-based regression tests. Naver and ICS remain read-only; Outlook needs an administrator-registered client ID.
