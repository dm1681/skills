from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"
SKILL = "orchestrate-olympus"


class InstallerTests(unittest.TestCase):
    def run_installer(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def test_default_prefers_shared_agents_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home))
            destination = home / ".agents" / "skills" / SKILL
            self.assertTrue((destination / "SKILL.md").is_file())
            receipt = json.loads((destination.parent / ".dm1681-skills.json").read_text())
            self.assertEqual("0.3.0", receipt["version"])

    def test_all_agents_install_once_per_distinct_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home), "--agent", "all")
            self.assertTrue((home / ".agents" / "skills" / SKILL / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / SKILL / "SKILL.md").is_file())

    def test_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_installer("--scope", "project", "--project-dir", str(project))
            self.assertTrue((project / ".agents" / "skills" / SKILL / "SKILL.md").is_file())

    def test_differing_destination_requires_force_and_is_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            destination = home / ".agents" / "skills" / SKILL
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("local change\n", encoding="utf-8")
            result = self.run_installer("--home", str(home), expected=2)
            self.assertIn("destination differs", result.stderr)
            self.run_installer("--home", str(home), "--force")
            backups = list(
                (destination.parent.parent / ".skills-backups" / "skills").glob(f"{SKILL}-*")
            )
            self.assertEqual(1, len(backups))
            self.assertEqual("local change\n", (backups[0] / "SKILL.md").read_text())

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_installer("--home", str(home), "--dry-run")
            self.assertIn("would copy", result.stdout)
            self.assertFalse((home / ".agents").exists())

    def test_graphify_dry_run_shows_external_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_installer(
                "--home", str(home), "--agent", "codex", "--graphify", "--dry-run"
            )
            self.assertIn("uv tool install --upgrade graphifyy", result.stdout)
            self.assertIn("graphify install --platform codex", result.stdout)
            self.assertFalse((home / ".agents").exists())

    def test_graphify_rejects_custom_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(
                "--target", directory, "--graphify", "--dry-run", expected=2
            )
            self.assertIn("cannot be combined with --target", result.stderr)

    @unittest.skipIf(os.name == "nt", "Windows symlinks may require Developer Mode")
    def test_link_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home), "--mode", "link")
            destination = home / ".agents" / "skills" / SKILL
            self.assertTrue(destination.is_symlink())
            self.assertEqual((ROOT / "skills" / SKILL).resolve(), destination.resolve())

    def test_list(self) -> None:
        result = self.run_installer("--list")
        self.assertEqual(f"{SKILL}\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
