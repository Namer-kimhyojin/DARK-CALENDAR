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
- [ ] Commit/push the complete runtime inputs and verify the matching GitHub Windows build and public package/source/checksums.
- [ ] Upload the single verified 4.3.0.0 package to the existing product, validate and submit for certification.
- [ ] Confirm Store publication and installation separately.

The first local 4.2.0 payload build verified 286 compiled modules and 203 resources. Formatting later changed one compiled fingerprint despite equal ASTs; it is not the final submitted artifact. The final build must pass its own complete match. The local PC has no `makeappx.exe`; the Store MSIX and upload will come from the verified GitHub Windows runner.

Evidence: `artifacts/maintenance/20261019-0937/`. Actual remote-calendar writes, physical mixed-DPI operation and updated installed UI are separate from isolated tests and package verification. No Store publication or installation is claimed by this checklist until its corresponding step is completed.
