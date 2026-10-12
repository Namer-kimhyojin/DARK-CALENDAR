# Air Calendar 3.8.1 release validation

**Date:** 2026-10-12

Target: x64 / MSIX 3.8.1.0. Existing Store product: 9MXQ08RF22K8.

- [x] Read current run.bat, release rules and existing Store identity.
- [x] Confirm Submission 25 is published in Partner Center and no draft is shown.
- [x] Add Yahoo Calendar, Zoho Calendar and Fastmail with bounded CalDAV URLs, protected credentials and common sync routing.
- [x] Pass 25 new provider cases and the corrected existing service-list case.
- [x] Pass scoped Ruff and encoding guard.
- [x] Complete 219 isolated test files / 3,957 cases, including successful reruns of corrected and timed-out files.
- [x] Commit complete runtime inputs with matching 3.8.1 metadata: d2903bf3583436a7842cbc5707286891dedec970.
- [x] Build with official build-release.bat and locked Python 3.13.15 environment; local payload and GitHub Windows x64 MSIX.
- [x] Verify clean DB, third-party license manifest, 286 frozen modules, 203 resources and MSIX identity/version. Four SVG/Markdown resources differ only by Git CRLF/LF conversion.
- [x] Pass 103 provider regressions against the local packaged implementation and preserve native preferences.
- [x] Publish corresponding source and matching package artifacts on GitHub; redownload and verify all checksums, 305 application source files, PE version and upload-contained MSIX.
- [x] Upload the verified package to Submission 26 and confirm Validated, 3.8.1.0 x64, and Save.
- [ ] Import the prepared 18-language release-notes CSV; browser upload permission remains blocked after the authorized retry.
- [ ] Submit for certification and record the server state.
- [ ] Confirm Store publication and installation separately.

New service real-account authentication and CRUD have not been tested. Same-service multiple simultaneous accounts remain a later account-management expansion; this release uses the existing one-connected-account-per-service policy. Recurring and invitation CalDAV events remain read-only.

Evidence directory: artifacts/global-providers/ and artifacts/deployment/3.8.1/.

GitHub release: https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v3.8.1

Store upload SHA256: 9c95b5ddc164dffa66068a46c0033808054851df8e62c576ce2221a7b3e555f4.

Store checkpoint (2026-10-13 KST): Submission 26, ID 1152921505702105863, was created through the authenticated Partner Center portal. DarkCalendar-3.8.1.0-x64.msixupload is Validated and saved. Publishing is set to occur as soon as certification passes. Pricing, availability, properties and age ratings were preserved.

Store listings remain unchanged. The prepared listing-3.8.1.csv changes only ReleaseNotes in the freshly exported listing, preserving every other cell. Browser security review declined CSV upload, and the rejection persisted after the user explicitly authorized a retry. The next step is normal user file selection under Import listings, followed by verification and certification submission in this existing draft. Do not recreate the draft or reupload the package.

Certification has not been submitted. API credentials remain unavailable. The last checked installed Store package is 3.8.0.0 x64. Draft status, CSV and package-validation screenshot are under artifacts/deployment/3.8.1/store-submission-20261012/.
