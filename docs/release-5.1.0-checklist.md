# Air Calendar 5.1.0 Release Checklist

**Date:** 2026-11-09

Historical failed candidate: CI 42509340902 stopped before publication because two KeyDeck compatibility modules were absent from the packaged runtime. The original tag is preserved. The packaging fix uses a new 5.1.1 candidate; see release-5.1.1-checklist.md. No 5.1.0 GitHub release or Store package was published/uploaded. The checklist below records the original preparation stage.

- [x] Reused fixed release reservation release-5.1.0-20261109; no retry version bump.
- [x] Full current run.bat input snapshot: 722 files; user data and unrelated promotion changes excluded.
- [x] Official ValidateOnly passed: private SQLite 3.54.1, 42 runtime and 8 build dependencies.
- [ ] Final source integration, encoding, single CI build and matching payload validation.
- [ ] Same CI payload: six native launches/exits on a separate Windows VM; review all six screenshots.
- [ ] Publish verified GitHub draft and independently verify public asset hashes.
- [ ] Submit exact validated MSIXUPLOAD to existing Store product 9MXQ08RF22K8.
- [ ] Observe certification, publication, official installed update and user-profile acceptance separately.

Existing Store 5.0.2 and Submission 34 remain preserved until a verified candidate is ready. Evidence: artifacts/deployment/5.1.0/20261109-0100/.
