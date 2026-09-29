"""The work profile keeps personal skills and global instructions off a machine.

Every install here redirects the home (`--home`, `$HOME`) so no test touches the
developer's real profile marker or skill roots.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"
SYNC = ROOT / "scripts" / "sync-agent-skills.sh"
sys.path.insert(0, str(ROOT))
import install  # noqa: E402

WORK_SAFE = "codebase-onboarding"
PERSONAL = "cloudflare-artifacts"


class WorkProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.env = {**os.environ, "SKILLS_PLUGIN_STATUS": "off"}
        self.env.pop(install.PROFILE_ENV, None)

    def run_installer(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--home", str(self.home), *arguments],
            cwd=ROOT, text=True, capture_output=True, check=False, env=self.env,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def mark_work(self) -> None:
        self.run_installer("--set-profile", "work")
        self.assertEqual((self.home / install.PROFILE_FILE).read_text(encoding="utf-8").strip(), "work")

    def installed(self, name: str) -> bool:
        return (self.home / ".agents" / "skills" / name / "SKILL.md").is_file()

    def test_personal_skills_exist(self) -> None:
        self.assertTrue(install.PERSONAL_SKILLS)
        self.assertLessEqual(install.PERSONAL_SKILLS, set(install.available_skills()))

    def test_unmarked_machine_is_unrestricted(self) -> None:
        self.run_installer("--non-interactive", "--agent", "codex", "--skill", PERSONAL)
        self.assertTrue(self.installed(PERSONAL))

    def test_naming_a_personal_skill_installs_nothing(self) -> None:
        self.mark_work()
        result = self.run_installer("--non-interactive", "--agent", "codex",
                                    "--skill", WORK_SAFE, "--skill", PERSONAL, expected=2)
        self.assertIn("personal skill", result.stderr + result.stdout)
        self.assertFalse(self.installed(PERSONAL))
        self.assertFalse(self.installed(WORK_SAFE), "a refused run must not half-install")

    def test_default_install_skips_personal_skills_and_says_so(self) -> None:
        self.mark_work()
        result = self.run_installer("--non-interactive", "--agent", "codex")
        self.assertIn("work profile: skipping personal skills", result.stdout)
        self.assertTrue(self.installed(WORK_SAFE))
        for name in install.PERSONAL_SKILLS:
            self.assertFalse(self.installed(name), name)

    def test_global_instructions_and_cloud_bootstrap_are_refused(self) -> None:
        self.mark_work()
        for flag in (["--global-instructions"], ["--cloud-bootstrap"]):
            result = self.run_installer(*flag, expected=2)
            self.assertIn("work-profile", result.stderr + result.stdout)
        self.assertFalse((self.home / ".agents" / "AGENTS.md").exists())
        self.assertFalse((self.home / ".claude").exists())

    def test_list_hides_personal_skills(self) -> None:
        self.mark_work()
        listed = self.run_installer("--list").stdout.split()
        self.assertIn(WORK_SAFE, listed)
        self.assertFalse(install.PERSONAL_SKILLS & set(listed))

    def test_environment_can_switch_the_profile_on_but_not_off(self) -> None:
        with mock.patch.dict(os.environ, {install.PROFILE_ENV: "work"}):
            self.assertEqual(install.active_profile(self.home), "work")
        self.mark_work()
        with mock.patch.dict(os.environ, {install.PROFILE_ENV: "personal"}):
            self.assertEqual(install.active_profile(self.home), "work")

    def test_install_one_refuses_for_every_caller(self) -> None:
        """The dashboard and `skills` CLI reach `install_one` directly."""
        root = self.home / "root"
        with mock.patch.dict(os.environ, {install.PROFILE_ENV: "work"}):
            with self.assertRaises(install.InstallError):
                install.install_one(install.SOURCE_ROOT / PERSONAL, root, "copy", False, False)
            with self.assertRaises(install.InstallError):
                install.install_global_instructions(self.home, "link", False)
        self.assertFalse((root / PERSONAL).exists())

    @unittest.skipUnless(shutil.which("bash"), "bash is not installed")
    def test_sync_script_refuses_on_a_work_machine(self) -> None:
        self.mark_work()
        dest = self.home / "dest"
        result = subprocess.run(
            ["bash", str(SYNC)], cwd=ROOT, text=True, capture_output=True, check=False,
            env={**self.env, "HOME": str(self.home), "AGENT_SKILLS_PROJECT_DIR": str(ROOT),
                 "AGENT_SKILLS_DEST": str(dest)},
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("work profile", result.stderr)
        self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
