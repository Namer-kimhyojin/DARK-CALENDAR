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
        script = self._read("build-core.ps1")

        self.assertIn('Join-Path $appDir "_internal\\desk_calendar_default.db"', script)
        self.assertIn("Sanitized bundled DB missing from runtime path", script)
        self.assertIn("Stale root default DB remains in payload", script)

    def test_profile_reset_is_opt_in(self):
        script = self._read("build.ps1")

        self.assertIn("[switch]$ResetState", script)
        self.assertIn(
            "$shouldResetState = ($ResetState -or $PurgeLocalData -or $DryRunReset)", script
        )
        self.assertNotIn('if (-not $SkipResetState) { $buildArgs += "-ResetState" }', script)
        self.assertIn("$shouldSign = $Sign -or -not [string]::IsNullOrWhiteSpace", script)

    def test_store_release_wrapper_delegates_to_single_build_pipeline(self):
        script = self._read("build-store-release.ps1")

        self.assertIn('$buildScript = Join-Path $projectRoot "build.ps1"', script)
        self.assertNotIn("DarkCalendar-x64.msix", script)
        self.assertNotIn("-X64Only", script)
        self.assertIn("-CertThumbprint", script)

    def test_project_and_runtime_versions_match(self):
        project = tomllib.loads(self._read("pyproject.toml"))
        metadata = self._read("calendar_app/app_metadata.py")
        match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', metadata, re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(project["project"]["version"], match.group(1))


if __name__ == "__main__":
    unittest.main()
