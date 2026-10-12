# Air Calendar 3.8.1 release validation

**Date:** 2026-10-12

Target: x64 / MSIX 3.8.1.0. Existing Store product: 9MXQ08RF22K8.

- [x] Read current run.bat, release rules and existing Store identity.
- [x] Confirm Submission 25 is published in Partner Center and no draft is shown.
- [x] Add Yahoo Calendar, Zoho Calendar and Fastmail with bounded CalDAV URLs, protected credentials and common sync routing.
- [x] Pass 25 new provider cases and the corrected existing service-list case.
- [x] Pass scoped Ruff and encoding guard.
- [ ] Complete app-wide isolated regression suite and resolve failures.
- [ ] Commit complete runtime inputs with matching 3.8.1 metadata.
- [ ] Build with official build-release.bat and locked Python 3.13.15 environment.
- [ ] Verify clean DB, third-party license manifest, frozen input equivalence and MSIX identity/version.
- [ ] Publish corresponding source and matching package artifacts on GitHub.
- [ ] Upload a verified package to the existing Store product and confirm validation.
- [ ] Submit for certification and record the server state.
- [ ] Confirm Store publication and installation separately.

New service real-account authentication and CRUD have not been tested. Same-service multiple simultaneous accounts remain a later account-management expansion; this release uses the existing one-connected-account-per-service policy. Recurring and invitation CalDAV events remain read-only.

Evidence directory: artifacts/global-providers/ and artifacts/deployment/3.8.1/.
