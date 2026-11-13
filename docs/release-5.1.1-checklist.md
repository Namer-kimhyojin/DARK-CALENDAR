# Air Calendar 5.1.1 Release Checklist

**Date:** 2026-11-09

GitHub published at 2026-11-09 03:40 KST. Store draft validated and saved; certification not submitted. The user deferred submission to incorporate further changes. Preserve the draft until the user resumes.

- [x] Reused fixed release reservation release-5.1.1-20261109; no retry version bump.
- [x] Full current run.bat input snapshot: 722 files; user data and unrelated promotion changes excluded.
- [x] Official ValidateOnly passed: private SQLite 3.54.1, 42 runtime and 8 build dependencies.
- [x] Final source integration 747 cases, language 43, packaging/metadata 27, encoding 12; matching payload validation.
- [x] Same CI payload: six native launches/exits on a separate Windows VM; all six screenshots reviewed. 1,877 native files match MSIX, and 722 source inputs match development.
- [x] GitHub release 438437417 published; six draft and public downloads have identical SHA-256. Readback runs 42511003147 and 42511145890 passed.
- [x] Exact MSIXUPLOAD validated and saved to existing product 9MXQ08RF22K8, Submission 34 (1152921505702328889). Fresh listing export: 453 rows, 22 columns, only 18 ReleaseNotes cells changed; other metadata and media preserved.
- [ ] Review submission options and submit for certification after user resumes. Chrome disconnected before this step; user then requested deferral for further changes.
- [ ] Observe certification, publication, official installed update and user-profile acceptance separately.

Actual Store and installed versions remain 5.0.2 / 5.0.2.0; running PID 63508 preserved. Candidate commit: 86b0ba9350ea24d8641d657b628d6d9177607860, build run: 42509937063. Readback QA/main commit: bdd5c15af827da9fb98c805c265b29cc355a59ea. Public files were not rebuilt or retagged. Upload SHA-256: acd0f11643cb511a8b95b4750e99f9f170d486606155b8c08e1a6ccb134f64a2. Evidence: artifacts/deployment/5.1.1/20261109-0322/.

Next: compare all current inputs after the user resumes. Changed product inputs require a new verified candidate without replacing public 5.1.1 assets. Regular daily review remains 8/14 complete, with Nov10 day09 and Nov16 03:00 KST integration unchanged. Windows blocked the check-yaml launcher for the QA-only commit; the block was preserved and equivalent parsing/contract checks passed through approved Python, with only that hook skipped for that commit. Other hooks and 32 readback tests passed.
