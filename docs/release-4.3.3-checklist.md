# Air Calendar 4.3.3 release validation

**Date:** 2026-10-19

Target: Windows x64 / MSIX 4.3.3.0. Existing Store product: 9MXQ08RF22K8.

- [x] Preserve existing user documents, credentials, databases and settings.
- [x] Apply the user's explicit 4.3.3 version correction and preserve the superseded, unpublished 4.4.0/4.5.0 history.
- [x] Pass the official `build-release.bat -ValidateOnly` environment and identity checks.
- [x] Pass source regression tests and encoding checks, including the DB connection failure regression.
- [x] Build the complete current runtime input and validate frozen modules, resources, licenses and the clean bundled database.
- [x] Test the packaged KeyDeck sound implementation without source fallback.
- [x] Commit and push the complete runtime input; verify GitHub build and public package/source checksums.
- [x] Confirm that the previous Store submission, Submission 27 / 4.3.0.0, is published.
- [x] Upload and validate the verified 4.3.3.0 package in the existing product.
- [x] Save release notes and submit for certification.
- [ ] Confirm Store publication and installation separately.

Evidence: `artifacts/deployment/4.3.3/20261019-store-keydeck/`.

The locally installed Store package was 4.3.0.0 at the start of this run. Partner Center confirmed that Submission 27 is published. Actual listening, remote-account synchronization and installed 4.3.3 UI behavior remain separate from isolated source and frozen-code tests.

The reported installed-app startup failure was traced to corruption in the Store profile's existing database. Its original DB/WAL/SHM were preserved outside the repository; a verified recovery candidate was applied and the actual installed 4.3.0.0 app started successfully at 15:42 KST. See [DB startup diagnosis and recovery](maintenance/store-db-startup-recovery-20261019.md). Version 4.3.3 also includes the confirmed connection cleanup fix; it does not silently reset corrupted databases.

The complete local quality groups passed 191 JUnit cases, with a further 8 i18n structure checks. English/Korean locale ordering was normalized without changing parsed keys or values. A reproducible Windows native crash in stopwatch glyph checking was removed by using QFontMetrics with font merging disabled; real glyph support and all focus tests passed with Windows system fonts supplied to the offscreen tests. The first remote build was cancelled before publication while these checks were resolved; 4.3.3 remains the sole release target.

Final release input: `3d9b5656b7347db2ac238061ed96b35ccf4edf5e`. GitHub Build Release `39213103289` succeeded, and the six public assets were downloaded again. Package identity, PE/MSIX version 4.3.3.0, x64 architecture, publisher, checksums, corresponding source (560 inputs), 287 frozen modules and 215 resources passed verification. The exact public upload SHA-256 is `e5022d329000907d66f5a0a459354a671d9f5cc66554d2d0ae57fb33bd595827`.

The final public PYZ implementation passed 338 KeyDeck and 29 stopwatch/preset cases using isolated host PyQt6 dependencies. Four empty/bundled database worker initializations passed; license, forbidden-file and clean database checks passed. These checks overlap source regressions and are not a separate count of unique application behavior.

A later Windows Photo Viewer edit to `Assets/Square44x44Logo.scale-200.png` was detected after the public package had been verified. That separate edit is preserved in place and excluded from the immutable 4.3.3 release input. Only the automatic scan's temporary version metadata/history changes were undone; a future scan can register that separate icon edit.

Partner Center accepted and saved `DarkCalendar-4.3.3.0-x64.msixupload` as **Validated** in the existing Submission 28 (`1152921505702166970`). It replaces 4.3.0.0 for the same Windows Desktop customers. Release notes were saved in all 18 existing Store languages; the existing Spanish trailer's missing thumbnail/title were completed using the existing Store hero art. Price, availability, device selections and publication timing were preserved.

Certification submission completed on 2026-10-19. The portal shows **PreProcessing** with Submission 28 in certification and automatic publication after certification passes. Submission 27 / 4.3.0.0 remains the published and locally installed release. Publication, official Store installation of 4.3.3 and its installed UI checks are pending; no new draft or version increase is needed to resume this submission.
