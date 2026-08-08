"""User-level instructions installed from global/AGENTS.md."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
SYNC = ROOT / "scripts" / "sync-agent-skills.sh"
SOURCE = ROOT / "global" / "AGENTS.md"


def _bash() -> Optional[str]:
    """A bash that can drive the sync script, or None to skip these tests.

    Windows is excluded on purpose, and not because bash is missing there.
    `AGENT_SKILLS_DEST` is colon-separated, so a drive letter cannot survive
    it: `C:\\Users\\x` splits into a root of `C` and a remainder, and the run
    writes a stray `./C` tree into whatever directory it started in — the
    repository, when the suite runs from a checkout. Nothing the test can pass
    avoids that, so this is a real limit of the POSIX script rather than a
    harness detail to work around. `sync-agent-skills.sh` is the POSIX and
    cloud entry point; Windows installs through `install.ps1`, which CI covers
    separately. Which bash also varies: on this developer's box `bash` is
    WSL's, mapping the drive at /mnt/c and unable to open `C:/...` at all.
    """
    if os.name == "nt":
        return None
    return shutil.which("bash")


BASH = _bash()


def run_installer(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(INSTALLER), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return result


class GlobalInstructionSourceTests(unittest.TestCase):
    def test_repository_ships_the_instructions(self) -> None:
        self.assertTrue(SOURCE.is_file(), f"missing {SOURCE}")

    def test_repository_agents_guide_does_not_duplicate_them(self) -> None:
        """The repo guide covers this repo; global/AGENTS.md owns machine-wide rules."""
        guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("Output shaping (ADHD reader)", guide)
        self.assertIn("global/AGENTS.md", guide)


class InstallerGlobalInstructionTests(unittest.TestCase):
    def test_not_installed_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--home", str(home))
            self.assertFalse((home / ".agents" / "AGENTS.md").exists())
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())

    def test_link_mode_chains_home_files_back_to_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--home", str(home), "--global-instructions")
            shared = home / ".agents" / "AGENTS.md"
            claude = home / ".claude" / "CLAUDE.md"
            self.assertIn(f"@{SOURCE.resolve()}", shared.read_text(encoding="utf-8"))
            self.assertIn(f"@{shared}", claude.read_text(encoding="utf-8"))
            # The pointer references the text instead of duplicating it.
            self.assertNotIn("Output shaping", shared.read_text(encoding="utf-8"))

    def test_copy_mode_inlines_the_text_for_agents_without_imports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--home", str(home), "--global-instructions", "copy")
            shared = (home / ".agents" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Output shaping (ADHD reader)", shared)
            claude = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(f"@{home / '.agents' / 'AGENTS.md'}", claude)

    def test_existing_home_instructions_are_backed_up_not_lost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            claude = home / ".claude" / "CLAUDE.md"
            claude.parent.mkdir(parents=True)
            claude.write_text("# hand written\n", encoding="utf-8")
            result = run_installer("--home", str(home), "--global-instructions")
            self.assertIn("backup:", result.stdout)
            backups = list((home / ".skills-backups" / ".claude").iterdir())
            self.assertEqual(1, len(backups))
            self.assertEqual("# hand written\n", backups[0].read_text(encoding="utf-8"))
            self.assertIn("@", claude.read_text(encoding="utf-8"))

    def test_reinstalling_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--home", str(home), "--global-instructions")
            result = run_installer("--home", str(home), "--global-instructions")
            self.assertIn("unchanged", result.stdout)
            self.assertFalse((home / ".skills-backups").exists())

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = run_installer(
                "--home", str(home), "--global-instructions", "--dry-run"
            )
            self.assertIn("would write", result.stdout)
            self.assertFalse((home / ".agents" / "AGENTS.md").exists())

    def test_an_install_that_does_not_ask_writes_no_global_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run_installer("--home", str(home))
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())
            self.assertFalse((home / ".agents" / "AGENTS.md").exists())


class GlobalInstructionStatusTests(unittest.TestCase):
    """The per-file status the dashboard's global-instructions row reads."""

    def paths(self, home: Path) -> tuple[Path, Path]:
        return home / ".agents" / "AGENTS.md", home / ".claude" / "CLAUDE.md"

    def test_a_fresh_home_is_missing_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            status = dict(install.global_instruction_status(home, "link"))
            shared, claude = self.paths(home)
            self.assertEqual(status, {shared: "missing", claude: "missing"})

    def test_an_install_reads_back_as_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            install.install_global_instructions(home, "link", False)
            states = [s for _, s in install.global_instruction_status(home, "link")]
            self.assertEqual(states, ["current", "current"])

    def test_an_edited_file_reads_as_differing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            install.install_global_instructions(home, "link", False)
            shared, _ = self.paths(home)
            shared.write_text("# mine now\n", encoding="utf-8")
            status = dict(install.global_instruction_status(home, "link"))
            self.assertEqual(status[shared], "differs")

    def test_the_status_is_probed_against_the_asked_for_mode(self) -> None:
        """Link-installed files differ from what copy mode would write, and
        saying so is the point: installing in copy mode would replace them."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            install.install_global_instructions(home, "link", False)
            states = [s for _, s in install.global_instruction_status(home, "copy")]
            self.assertEqual(states, ["differs", "current"])


@unittest.skipIf(BASH is None, "needs a POSIX shell and colon-free absolute paths")
class SyncScriptGlobalInstructionTests(unittest.TestCase):
    def _project(self, directory: Path) -> Path:
        project = directory / "checkout"
        (project / "skills" / "demo").mkdir(parents=True)
        (project / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
        )
        (project / "global").mkdir()
        (project / "global" / "AGENTS.md").write_text(
            "# Global agent instructions\n\nBe brief.\n", encoding="utf-8"
        )
        return project

    def _run(self, home: Path, project: Path, **env: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update(
            HOME=str(home),
            AGENT_SKILLS_PROJECT_DIR=str(project),
            AGENT_SKILLS_DEST=str(home / ".agents" / "skills"),
            **env,
        )
        result = subprocess.run(
            [BASH, str(SYNC)],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def test_default_leaves_home_instructions_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            self._run(home, self._project(Path(directory)))
            self.assertFalse((home / ".agents" / "AGENTS.md").exists())
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())

    def test_link_mode_chains_home_files_back_to_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            project = self._project(Path(directory))
            self._run(home, project, AGENT_GLOBAL_INSTRUCTIONS="link")
            shared = home / ".agents" / "AGENTS.md"
            self.assertIn(
                f"@{project / 'global' / 'AGENTS.md'}", shared.read_text(encoding="utf-8")
            )
            self.assertIn(
                f"@{shared}", (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            )

    def test_copy_mode_inlines_the_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            self._run(
                home, self._project(Path(directory)), AGENT_GLOBAL_INSTRUCTIONS="copy"
            )
            self.assertIn(
                "Be brief.", (home / ".agents" / "AGENTS.md").read_text(encoding="utf-8")
            )

    def test_existing_file_is_backed_up_and_rerun_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            (home / ".claude").mkdir(parents=True)
            (home / ".claude" / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
            project = self._project(Path(directory))
            self._run(home, project, AGENT_GLOBAL_INSTRUCTIONS="link")
            backups = list((home / ".skills-backups" / ".claude").iterdir())
            self.assertEqual(["# mine\n"], [b.read_text(encoding="utf-8") for b in backups])
            result = self._run(home, project, AGENT_GLOBAL_INSTRUCTIONS="link")
            self.assertIn("unchanged", result.stderr)


if __name__ == "__main__":
    unittest.main()
