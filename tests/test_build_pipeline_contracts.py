# -*- coding: utf-8 -*-
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildPipelineContractTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8", errors="strict")

    def test_store_spec_defers_default_db_until_sanitized_payload_step(self):
        store_spec = self._read("DarkCalendar.spec")
        standalone_spec = self._read("Standalone.spec")

        self.assertNotIn("('desk_calendar_default.db', '.')", store_spec)
        self.assertIn("('desk_calendar_default.db', '.')", standalone_spec)

    def test_build_pipeline_requires_sanitized_db_in_runtime_path(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn('Join-Path $appDir "_internal\\desk_calendar_default.db"', script)
        self.assertIn("Sanitized bundled DB missing from runtime path", script)
        self.assertIn("Stale root default DB remains in payload", script)

    def test_msix_root_copies_only_manifest_referenced_assets(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn("function Copy-ManifestAssets", script)
        self.assertIn("-ManifestPath $manifestDest", script)
        self.assertNotIn(
            "Copy-Item -Path $assetsSource -Destination $assetsDest -Recurse -Force",
            script,
        )

    def test_bundle_rejects_identity_version_or_architecture_mismatch(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn("function Assert-CompatiblePackages", script)
        self.assertIn('@("Name", "Publisher", "Version")', script)
        self.assertIn('$x64.Architecture -ne "x64"', script)
        self.assertIn('$arm64.Architecture -ne "arm64"', script)

    def test_profile_reset_is_opt_in(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn("[switch]$ResetState", script)
        self.assertIn(
            "$effectiveResetState = ($ResetState -or $PurgeLocalData -or $DryRunReset)",
            script,
        )
        self.assertIn("-not $SkipResetState", script)
        self.assertIn("$effectiveSign = $Sign -or", script)
        self.assertIn("if ($effectiveSign)", script)

    def test_single_batch_entrypoint_delegates_to_unified_pipeline(self):
        batch = self._read("build-release.bat")

        self.assertIn("scripts\\build_pipeline.ps1", batch)
        self.assertIn("%*", batch)
        for legacy in (
            "build.ps1",
            "build-store-release.ps1",
            "build-core.ps1",
            "bundle-msix.ps1",
            "make-store-upload.ps1",
            "prepare-store-release.ps1",
            "prepare-store-release.bat",
            "package_msix.py",
        ):
            self.assertFalse((ROOT / legacy).exists(), legacy)

    def test_unified_pipeline_syncs_all_version_sources(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn("-PyprojectPath", script)
        self.assertIn("-NewPackageVersion", script)
        self.assertIn("[System.Text.UTF8Encoding]::new($false, $true)", script)
        self.assertIn("function New-StoreUpload", script)
        self.assertIn("[switch]$UploadOnly", script)

    def test_store_artifact_names_include_package_version(self):
        script = self._read("scripts/build_pipeline.ps1")

        self.assertIn("$packageVersion = $thisIdentity.Version", script)
        self.assertIn("DarkCalendar-$packageVersion-${ThisArch}.msixupload", script)
        self.assertIn("DarkCalendar-$packageVersion-arm64_x64.msixupload", script)
        self.assertNotIn('"DarkCalendar_arm64_x64.msixupload"', script)

    def test_project_and_runtime_versions_match(self):
        project = tomllib.loads(self._read("pyproject.toml"))
        metadata = self._read("calendar_app/app_metadata.py")
        match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', metadata, re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(project["project"]["version"], match.group(1))


if __name__ == "__main__":
    unittest.main()
