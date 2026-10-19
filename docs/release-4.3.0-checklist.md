# Air Calendar 4.3.0 release validation

**Date:** 2026-10-19

Target: Windows x64 / MSIX 4.3.0.0. Existing Store product: 9MXQ08RF22K8.

- [x] Complete the 2026-10-05 review cycle, including the missing homepage/request/image/release review.
- [x] Validate 234 isolated test files / 4,225 JUnit testcases, with no final failures, errors or skips. Replace affected results with 8 rerun files / 327 cases; do not count repeats twice.
- [x] Correct the deferred-layout regression timing and unsupported stopwatch transport-font selection.
- [x] Normalize required commit formatting in 20 files and confirm unchanged Python ASTs across all 49 release Python inputs.
- [x] Confirm authenticated Partner Center shows published Submission 26, matching the existing Store product identity. Preserve pricing, availability, account and user data.
- [x] Reserve final Store preparation event `store-cycle-20261005-final-inputs` as 4.3.0. The earlier 4.2.0 local preparation was superseded before publication or Store upload.
- [x] Complete the final official local payload build, clean bundled DB/license checks and exact match of 286 frozen modules / 203 resources.
- [x] Pass 179 packaged-implementation cases in 9 isolated files, with no source fallback and native preferences preserved.
- [x] Pass post-format source contracts, final registered-version scan and encoding checks.
- [x] Commit/push the complete runtime inputs and verify the matching GitHub Windows build and public package/source/checksums.
- [x] Upload the single verified 4.3.0.0 package to the existing product, validate and submit for certification.
- [ ] Confirm Store publication and installation separately.

The first local 4.2.0 payload build verified 286 compiled modules and 203 resources. Formatting later changed one compiled fingerprint despite equal ASTs; it is not the final submitted artifact. The final build must pass its own complete match. The local PC has no `makeappx.exe`; the Store MSIX and upload will come from the verified GitHub Windows runner.

Evidence: `artifacts/maintenance/20261019-0937/`. Actual remote-calendar writes, physical mixed-DPI operation and updated installed UI are separate from isolated tests and package verification. No Store publication or installation is claimed by this checklist until its corresponding step is completed.

## 2026-10-19 remote deployment checkpoint

Release tag `v4.3.0` points to `73c9c3c01b60c5c8fd5aa11f3a09ac49ec327711`. GitHub Windows Build Release run `39184542848`, Quality Gate, Encoding Policy and Pages deployment succeeded. The public release has all six assets. Downloaded MSIX/upload/source checksums passed; the upload contains the exact public MSIX. Package identity, x64 architecture, PE/MSIX 4.3.0.0 and publisher match the existing product. All 547 current runtime inputs match the corresponding source content; four SVG/Markdown assets differ only in Git checkout CRLF endings. The public package matches all 286 compiled modules and 203 resources of its source. A further 37 isolated widget/DB cases passed against the public frozen code, preserving native preferences.

Public upload SHA-256: `8cb7aa46e55c009967bed4dc31af2dedfda1a62c381a47eecfb903d53075a2be`.

Authenticated Partner Center created **Submission 27 / `1152921505702165197`**. The first normal chooser upload was blocked because the ChatGPT Chrome extension has no file URL access. No new file was uploaded, saved or submitted. The draft still inherits 3.8.1.0. User action is to enable **Allow access to file URLs** or choose the verified upload file manually. Resume this exact draft and file; do not create another submission or increase the version. Published/installed Store version remains 3.8.1.0.

Public release: https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v4.3.0

Evidence: `artifacts/deployment/4.3.0/20261019-1017/` (`public-package-validation.json`, `public-runtime-match.json`, `public-frozen-smoke.xml`, `github-workflows.json`, `store-draft-status.json`). Common state preserves the published Submission 26 checkpoint and the precise upload resume point.

## Certification submitted — 2026-10-19

The user selected the verified 4.3.0.0 upload through the normal Chrome picker. Partner Center recognized x64 / Windows.Desktop minimum 10.0.17763.0 and confirmed that this version supports the same customers as 3.8.1.0. Save completed; the overview shows `DarkCalendar-4.3.0.0-x64.msixupload`, **Validated** and **Updated**. The browser-upload blocker is resolved by the normal user upload; no permission bypass or duplicate package was used.

Release notes for all **18 existing Store listing languages** were updated to 4.3.0 and saved. Existing product descriptions, images, prices, availability and account settings were preserved. The existing option publishes automatically after certification passes.

**Submission 27 / `1152921505702165197` was submitted for certification.** The authenticated portal shows submission complete, preprocessing in progress, certification/publication not yet started. Status: **PreProcessing**, confirmed at approximately **11:07 KST**. Published/installed Store version remains **3.8.1.0**; do not treat submission as publication or installation. Continue status checks on this ID, then use the official Store update after publication. Keep release 4.3.0 and its package/hash on all retries.

Evidence: `store-package-validated.png`, `store-listing-save-evidence.json`, `store-release-notes-4.3.0.json`, `store-publication-options.json`, `store-submitted.json` and `store-submission27-preprocessing.png` in the deployment evidence directory above.
