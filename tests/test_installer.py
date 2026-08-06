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
SKILL = "wow-addon-dev"
EXPLAINER_SKILL = "semantic-pr-review"
BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)


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

    def test_bare_invocation_without_a_terminal_refuses_to_guess(self) -> None:
        """A bare `install.py` means "ask me". Without a usable terminal there is
        nothing to fall back on, and installing every skill into every root would
        silently make the choices the wizard exists to collect -- including a
        machine-wide install of a skill marked `global_default: false`.

        Reachable in practice: a pty shell such as Git Bash on Windows hides the
        terminal from Python, so the wizard cannot start there.
        """
        result = self.run_installer(expected=2)
        combined = result.stdout + result.stderr
        self.assertIn("nothing was installed", combined)
        self.assertIn("--non-interactive", combined)

    def test_explicit_non_interactive_still_accepts_every_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--non-interactive", "--home", str(home))
            for name in (SKILL, EXPLAINER_SKILL):
                self.assertTrue(
                    (home / ".agents" / "skills" / name / "SKILL.md").is_file()
                )

    def test_default_installs_into_every_skill_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home))
            destination = home / ".agents" / "skills" / SKILL
            self.assertTrue((destination / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / SKILL / "SKILL.md").is_file())
            receipt = json.loads((destination.parent / ".dm1681-skills.json").read_text())
            expected_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
            self.assertEqual(expected_version, receipt["version"])

    def test_default_single_skill_install_reaches_the_claude_root(self) -> None:
        """A bare --skill must be visible to Claude Code, not shared roots only."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home), "--skill", EXPLAINER_SKILL)
            for root in (".agents", ".claude"):
                destination = home / root / "skills" / EXPLAINER_SKILL
                self.assertTrue(
                    (destination / "SKILL.md").is_file(),
                    f"{EXPLAINER_SKILL} missing from {root}/skills",
                )
                self.assertFalse((home / root / "skills" / SKILL).exists())

    def test_explicit_agent_still_narrows_to_one_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home), "--agent", "universal")
            self.assertTrue((home / ".agents" / "skills" / SKILL / "SKILL.md").is_file())
            self.assertFalse((home / ".claude").exists())

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

    def test_mode_change_reinstalls_even_when_contents_match(self) -> None:
        """Switching --mode must convert the destination, not report it current."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            destination = home / ".claude" / "skills" / SKILL
            self.run_installer("--home", str(home), "--agent", "claude", "--skill", SKILL)
            self.assertFalse(destination.is_symlink())

            refused = self.run_installer(
                "--home", str(home), "--agent", "claude", "--skill", SKILL,
                "--mode", "link", expected=2,
            )
            self.assertIn("destination is a copy, not a link", refused.stderr)

            self.run_installer(
                "--home", str(home), "--agent", "claude", "--skill", SKILL,
                "--mode", "link", "--force",
            )
            self.assertTrue(destination.is_symlink())
            self.assertEqual((ROOT / "skills" / SKILL).resolve(), destination.resolve())

    def test_matching_mode_and_contents_are_reported_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            arguments = ("--home", str(home), "--agent", "claude", "--skill", SKILL)
            self.run_installer(*arguments, "--mode", "link")
            repeated = self.run_installer(*arguments, "--mode", "link")
            self.assertIn("unchanged", repeated.stdout)

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

    def test_matt_skills_dry_run_shows_external_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(
                "--home", directory, "--agent", "all", "--matt-skills", "--dry-run"
            )
            self.assertIn("npx --yes skills@latest add mattpocock/skills", result.stdout)
            self.assertIn("--skill '*'", result.stdout)
            self.assertIn("--agent codex --agent claude-code", result.stdout)

    def test_matt_skills_supports_custom_target_via_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(
                "--target", directory, "--matt-skills", "--dry-run"
            )
            self.assertIn(
                f"would copy all discovered Matt Pocock skills -> {Path(directory).resolve()}",
                result.stdout,
            )

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
        self.assertEqual("".join(f"{name}\n" for name in BUNDLED), result.stdout)
        self.assertIn(SKILL, BUNDLED)
        self.assertIn(EXPLAINER_SKILL, BUNDLED)

    def test_default_installs_every_bundled_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home))
            root = home / ".agents" / "skills"
            for name in BUNDLED:
                with self.subTest(skill=name):
                    self.assertTrue((root / name / "SKILL.md").is_file())
            receipt = json.loads((root / ".dm1681-skills.json").read_text())
            self.assertEqual(BUNDLED, receipt["skills"])

    def test_selecting_one_skill_leaves_the_others_uninstalled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_installer("--home", str(home), "--skill", EXPLAINER_SKILL)
            root = home / ".agents" / "skills"
            self.assertTrue((root / EXPLAINER_SKILL / "SKILL.md").is_file())
            self.assertFalse((root / SKILL).exists())
            receipt = json.loads((root / ".dm1681-skills.json").read_text())
            self.assertEqual([EXPLAINER_SKILL], receipt["skills"])


if __name__ == "__main__":
    unittest.main()
