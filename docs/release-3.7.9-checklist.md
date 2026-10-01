# Air Calendar 3.7.9 release validation

**Date:** 2026-10-02

- [x] Capture all current application inputs from the development folder used by `run.bat`, including uncommitted and new runtime files, resources, translations and deleted legacy modules.
- [x] Include those application changes in release source control for the GitHub build.
- [x] Validate locked Python, Qt and build dependencies with the official release entrypoint.
- [x] Build native x64 payload, MSIX and Store upload; retain sanitized default DB and exclude user data and credentials.
- [x] Finish isolated module regression tests and release metadata checks: 139 files, 1,499 tests; release documentation checked again after creation.
- [x] Compare frozen Python implementation, images/sounds and translations against development inputs: 239 modules and 114 resources match; 12 extracted-code preset checks pass.
- [ ] Publish the versioned release and verify downloaded public artifacts.

The build source must include current runtime changes across the application, rather than selecting files from only the most recent feature task. Local builds read the working directory; GitHub builds read the pushed commit. Check both inputs before declaring equivalence with `run.bat`.
