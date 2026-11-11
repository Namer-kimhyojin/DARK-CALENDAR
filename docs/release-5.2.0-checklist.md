# Air Calendar 5.2.0 release checklist

**Date:** 2026-11-11

- Release ID: release-5.2.0-20261111; release date 2026-11-11 (Asia/Seoul).
- Build commit: 731bca88a82bec5e200d315dec73321730ad0d96; Actions run 42940491243.
- Complete current runtime input: 726 files. Source integration, encoding guard, pinned SQLite 3.54.1 and official ValidateOnly passed.
- 75 source regression files (1,380 cases), required-flow checks and native font checks completed. Initial test environment failures and corrected evidence are retained.
- All six fresh/upgrade native launches, normal exits and restart/data checks passed on a separate Windows VM. All six screenshots reviewed.
- All 1,877 MSIX payload files match the native-tested payload; package identity and PE version are 5.2.0.0 x64. Store upload contains the identical MSIX.
- GitHub release 441140736 published: https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v5.2.0
- Draft readback run 42941748804 and public readback run 42941926022 verified actual bytes of all six assets and their sidecars.
- Store Submission 34 (1152921505702328889): 5.2.0.0 package validated and saved; certification submitted 2026-11-11. Publish as soon as certification passes.
- All 18 listing languages verified after save. Only release notes changed; descriptions, keywords, image order, captions and other fields preserved.
- Store publication and installation pending. This PC remains on 5.0.2.0; installed 5.2.0 UI/data/restart acceptance has not occurred.
- Original 5.1.1 release/tag and previous submission evidence preserved. Developer source, preferences and personal databases preserved.
- Evidence: artifacts/deployment/5.2.0/20261111-1027.
