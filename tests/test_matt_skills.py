from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("matt_skills_installer", ROOT / "install.py")
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class MattSkillsTests(unittest.TestCase):
    def test_command_installs_all_skills_for_selected_agents(self) -> None:
        self.assertEqual(
            [
                "npx",
                "--yes",
                "skills@latest",
                "add",
                "mattpocock/skills",
                "--skill",
                "*",
                "--agent",
                "codex",
                "--agent",
                "claude-code",
                "--global",
                "--copy",
                "--yes",
            ],
            INSTALLER.matt_skills_install_command(["all"], "user"),
        )

    def test_agent_names_are_mapped_to_skills_cli(self) -> None:
        self.assertEqual(
            ["codex", "cursor", "github-copilot", "claude-code"],
            INSTALLER.matt_skills_agents(
                ["codex", "cursor", "copilot", "claude"]
            ),
        )
        self.assertEqual(["codex"], INSTALLER.matt_skills_agents(["universal"]))

    def test_project_install_runs_in_selected_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/npx"),
                mock.patch.object(INSTALLER, "_run") as run,
            ):
                INSTALLER.install_matt_skills(
                    ["codex"], "project", project, dry_run=False
                )
            run.assert_called_once_with(
                [
                    "/tools/npx",
                    "--yes",
                    "skills@latest",
                    "add",
                    "mattpocock/skills",
                    "--skill",
                    "*",
                    "--agent",
                    "codex",
                    "--copy",
                    "--yes",
                ],
                project,
            )

    def test_missing_npx_is_actionable(self) -> None:
        with mock.patch.object(INSTALLER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(INSTALLER.InstallError, "requires npx"):
                INSTALLER.install_matt_skills([], "user", ROOT, dry_run=False)

    def test_dry_run_prints_exact_command_without_requiring_npx(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(
                INSTALLER.shutil,
                "which",
                side_effect=AssertionError("dry run must not inspect installed tools"),
            ),
            contextlib.redirect_stdout(output),
        ):
            INSTALLER.install_matt_skills(["all"], "user", ROOT, dry_run=True)
        self.assertEqual(
            "would run  npx --yes skills@latest add mattpocock/skills "
            "--skill '*' --agent codex --agent claude-code --global --copy --yes\n",
            output.getvalue(),
        )

    def test_parser_supports_explicit_opt_in_and_opt_out(self) -> None:
        enabled = INSTALLER.parser().parse_args(["--matt-skills"])
        disabled = INSTALLER.parser().parse_args(["--no-matt-skills"])
        unspecified = INSTALLER.parser().parse_args([])
        self.assertTrue(enabled.matt_skills)
        self.assertFalse(disabled.matt_skills)
        self.assertIsNone(unspecified.matt_skills)


if __name__ == "__main__":
    unittest.main()
