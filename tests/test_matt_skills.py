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
                "--copy",
                "--yes",
            ],
            INSTALLER.matt_skills_install_command(["all"]),
        )

    def test_shared_agents_use_one_staging_target(self) -> None:
        self.assertEqual(
            ["codex"],
            INSTALLER.matt_skills_agents(
                ["codex", "cursor", "copilot"]
            ),
        )
        self.assertEqual(
            ["codex", "claude-code"],
            INSTALLER.matt_skills_agents(["all"]),
        )

    def test_install_stages_then_copies_to_exact_resolved_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / ".agents" / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                source = cwd / ".agents" / "skills" / "setup-matt-pocock-skills"
                source.mkdir(parents=True)
                (source / "SKILL.md").write_text("---\nname: setup-matt-pocock-skills\n---\n")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/npx"),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run) as run,
            ):
                INSTALLER.install_matt_skills(
                    ["universal"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=lambda _: None,
                )
            self.assertEqual(1, run.call_count)
            self.assertTrue(
                (destination / "setup-matt-pocock-skills" / "SKILL.md").is_file()
            )

    def test_missing_npx_is_actionable(self) -> None:
        with mock.patch.object(INSTALLER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(INSTALLER.InstallError, "requires npx"):
                INSTALLER.install_matt_skills([], [ROOT], force=False, dry_run=False)

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
            INSTALLER.install_matt_skills(
                ["all"], [ROOT / ".agents" / "skills", ROOT / ".claude" / "skills"],
                force=False, dry_run=True
            )
        self.assertEqual(
            "would run  npx --yes skills@latest add mattpocock/skills "
            "--skill '*' --agent codex --agent claude-code --copy --yes\n"
            f"would copy all discovered Matt Pocock skills -> {ROOT / '.agents' / 'skills'}\n"
            f"would copy all discovered Matt Pocock skills -> {ROOT / '.claude' / 'skills'}\n",
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
