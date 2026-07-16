from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UvProjectTests(unittest.TestCase):
    def test_project_metadata_matches_collection_version(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        declared = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        self.assertIsNotNone(declared)
        assert declared is not None
        self.assertEqual(version, declared.group(1))
        self.assertIn('name = "dm1681-skills"', pyproject)
        self.assertIn('requires-python = ">=3.9"', pyproject)
        self.assertIn("[tool.uv]", pyproject)
        self.assertIn("package = false", pyproject)

    def test_launchers_prefer_uv_and_keep_python_fallbacks(self) -> None:
        posix = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertLess(posix.index("command -v uv"), posix.index("command -v python3"))
        self.assertIn('uv run --project "$SCRIPT_DIR"', posix)
        self.assertLess(powershell.index("Get-Command uv"), powershell.index("Get-Command py"))
        self.assertIn("uv run --project $PSScriptRoot", powershell)

    def test_release_archives_include_uv_project_files(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        for filename in ("pyproject.toml", "uv.lock", ".python-version"):
            with self.subTest(filename=filename):
                self.assertIn(filename, workflow)


if __name__ == "__main__":
    unittest.main()
