"""REA is installed by its own `rea setup`, pinned, machine-wide and personal.

Every run redirects the home so no test touches the developer's real agent
configuration, and no test reaches the network: the one real invocation runs a
stand-in `npx` that records what it was asked to do.
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
sys.path.insert(0, str(ROOT))
import install  # noqa: E402

PINNED = f"{install.REA_PACKAGE}@{install.REA_VERSION}"


class SetupCommandTests(unittest.TestCase):
    def test_all_configures_only_the_agents_this_machine_has(self) -> None:
        for agents in ([], ["all"], ["codex", "all"]):
            with self.subTest(agents=agents):
                self.assertEqual(
                    ["npx", "-y", PINNED, "setup", "--all-detected", "--yes"],
                    install.rea_setup_command(agents),
                )

    def test_named_agents_map_to_rea_client_ids_once_each(self) -> None:
        self.assertEqual(
            [
                "npx", "-y", PINNED, "setup",
                "--client", "claude_code", "--client", "copilot_cli", "--yes",
            ],
            install.rea_setup_command(["claude", "copilot", "claude"]),
        )

    def test_a_skill_directory_is_not_an_agent(self) -> None:
        for agent in ("universal", "agents"):
            with self.subTest(agent=agent):
                with self.assertRaises(install.InstallError) as caught:
                    install.rea_setup_command([agent])
                self.assertIn("names a skill directory", str(caught.exception))

    def test_hopper_is_never_installed_on_the_users_behalf(self) -> None:
        for agents in (["all"], ["codex"]):
            self.assertNotIn("--install-hopper", install.rea_setup_command(agents))

    def test_every_shared_agent_but_the_generic_ones_has_a_client(self) -> None:
        self.assertEqual(
            install.KNOWN_AGENTS - {"all", "universal", "agents"},
            set(install.REA_CLIENTS),
        )


class InstallReaTests(unittest.TestCase):
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

    def fake_npx(self) -> tuple[Path, Path]:
        """A stand-in npx that writes its working directory and arguments."""
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        log = self.home / "npx.log"
        if os.name == "nt":
            script = bin_dir / "npx.cmd"
            script.write_text(
                f'@echo off\r\ncd > "{log}"\r\necho %* >> "{log}"\r\n',
                encoding="utf-8",
            )
        else:
            script = bin_dir / "npx"
            script.write_text(
                f'#!/bin/sh\npwd > "{log}"\necho "$@" >> "{log}"\n',
                encoding="utf-8",
            )
            script.chmod(0o755)
        return bin_dir, log

    def test_dry_run_prints_the_pinned_setup_and_runs_nothing(self) -> None:
        result = self.run_installer("--agent", "codex", "--rea", "--dry-run")
        self.assertIn(
            f"would run  npx -y {PINNED} setup --client codex --yes", result.stdout
        )
        self.assertFalse((self.home / ".codex").exists())

    def test_setup_runs_from_the_home_with_the_mapped_clients(self) -> None:
        bin_dir, log = self.fake_npx()
        lines: list[str] = []
        with mock.patch.dict(os.environ, {"PATH": str(bin_dir)}):
            install.install_rea(["codex"], "user", False, lines.append, home=self.home)
        cwd, arguments = log.read_text(encoding="utf-8").splitlines()[:2]
        self.assertEqual(Path(cwd.strip()).resolve(), self.home.resolve())
        self.assertEqual(f"-y {PINNED} setup --client codex --yes", arguments.strip())
        self.assertTrue(any("restart" in line for line in lines))

    def test_missing_npx_names_the_node_versions_rea_supports(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": ""}):
            with self.assertRaises(install.InstallError) as caught:
                install.install_rea(["codex"], "user", False, lambda _l: None, home=self.home)
        self.assertIn("requires npx", str(caught.exception))

    def test_project_scope_and_custom_targets_are_refused(self) -> None:
        for flags in (["--scope", "project"], ["--target", str(self.home / "t")]):
            with self.subTest(flags=flags):
                result = self.run_installer("--rea", "--dry-run", *flags, expected=2)
                self.assertIn("--rea", result.stderr)

    def test_the_work_profile_refuses_it_before_installing_anything(self) -> None:
        self.run_installer("--set-profile", "work")
        result = self.run_installer(
            "--non-interactive", "--agent", "codex", "--rea", expected=2
        )
        self.assertIn("rea is a personal skill or tool", result.stderr)
        self.assertFalse((self.home / ".agents" / "skills").exists())

    def test_the_work_profile_refuses_it_for_the_dashboard_too(self) -> None:
        """The dashboard calls install_rea directly, past main's checks."""
        with mock.patch.dict(os.environ, {install.PROFILE_ENV: "work"}):
            with self.assertRaises(install.InstallError):
                install.install_rea(["codex"], "user", True, lambda _l: None, home=self.home)

    def test_it_is_registered_as_a_personal_external_tool(self) -> None:
        tool = install.external_tool("rea")
        self.assertEqual("reverse-engineer-anything", tool.marker)
        self.assertIn("rea", install.PERSONAL_TOOLS)
        self.assertNotIn("rea", install.UPSTREAM_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
