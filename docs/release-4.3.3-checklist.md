# Air Calendar 4.3.3 release validation

**Date:** 2026-10-19

Target: Windows x64 / MSIX 4.3.3.0. Existing Store product: 9MXQ08RF22K8.

- [x] Preserve existing user documents, credentials, databases and settings.
- [x] Apply the user's explicit 4.3.3 version correction and preserve the superseded, unpublished 4.4.0/4.5.0 history.
- [x] Pass the official `build-release.bat -ValidateOnly` environment and identity checks.
- [x] Pass source regression tests and encoding checks, including the DB connection failure regression.
- [x] Build the complete current runtime input and validate frozen modules, resources, licenses and the clean bundled database.
- [ ] Test the packaged KeyDeck sound implementation without source fallback.
- [ ] Commit and push the complete runtime input; verify GitHub build and public package/source checksums.
- [x] Confirm that the previous Store submission, Submission 27 / 4.3.0.0, is published.
- [ ] Upload and validate the verified 4.3.3.0 package in the existing product.
- [ ] Save release notes and submit for certification.
- [ ] Confirm Store publication and installation separately.

Evidence: `artifacts/deployment/4.3.3/20261019-store-keydeck/`.

The locally installed Store package was 4.3.0.0 at the start of this run. Partner Center confirmed that Submission 27 is published. Actual listening, remote-account synchronization and installed 4.3.3 UI behavior remain separate from isolated source and frozen-code tests.

The reported installed-app startup failure was traced to corruption in the Store profile's existing database. Its original DB/WAL/SHM were preserved outside the repository; a verified recovery candidate was applied and the actual installed 4.3.0.0 app started successfully at 15:42 KST. See [DB startup diagnosis and recovery](maintenance/store-db-startup-recovery-20261019.md). Version 4.3.3 also includes the confirmed connection cleanup fix; it does not silently reset corrupted databases.
