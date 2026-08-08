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


HIDDEN_SKILL = (
    "---\n"
    "name: {name}\n"
    "description: Grill the plan. Use when stress-testing.\n"
    "disable-model-invocation: true\n"
    "---\n"
    "# Body\n"
)


def write_skill(root: Path, name: str, hidden: bool = True) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    text = HIDDEN_SKILL.format(name=name)
    if not hidden:
        text = text.replace("disable-model-invocation: true\n", "")
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


class ModelInvocationTests(unittest.TestCase):
    """Deciding which installed skills the model is allowed to see."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "skills"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_enabling_strips_only_the_flag_line(self) -> None:
        skill_dir = write_skill(self.root, "grill-with-docs")
        self.assertTrue(INSTALLER.set_model_invocation(skill_dir, visible=True))
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("disable-model-invocation", text)
        self.assertIn("description: Grill the plan", text)
        self.assertIn("# Body", text)

    def test_hiding_adds_the_flag_back(self) -> None:
        skill_dir = write_skill(self.root, "grill-with-docs", hidden=False)
        self.assertTrue(INSTALLER.set_model_invocation(skill_dir, visible=False))
        self.assertTrue(INSTALLER.skill_is_model_hidden(skill_dir))

    def test_toggling_to_the_current_state_reports_no_change(self) -> None:
        skill_dir = write_skill(self.root, "grill-with-docs")
        self.assertFalse(INSTALLER.set_model_invocation(skill_dir, visible=False))

    def test_hidden_skills_lists_only_the_flagged_ones(self) -> None:
        write_skill(self.root, "hidden-one")
        write_skill(self.root, "visible-one", hidden=False)
        self.assertEqual(INSTALLER.hidden_skills(self.root), ["hidden-one"])

    def test_a_matt_update_reapplies_a_recorded_enable(self) -> None:
        """The refresh overwrites the frontmatter edit; the record restores it."""
        INSTALLER.record_model_decisions([self.root], {"grill-with-docs": "enabled"})

        def fake_run(command: list, cwd: Path) -> None:
            staged = cwd / ".claude" / "skills"
            write_skill(staged, "setup-matt-pocock-skills")
            write_skill(staged, "grill-with-docs")

        with (
            mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/npx"),
            mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
        ):
            INSTALLER.install_matt_skills(
                ["claude"], [self.root], force=True, dry_run=False,
                emit=lambda _line: None,
            )
        self.assertFalse(
            INSTALLER.skill_is_model_hidden(self.root / "grill-with-docs")
        )
        self.assertTrue(
            INSTALLER.skill_is_model_hidden(self.root / "setup-matt-pocock-skills")
        )

    def test_the_enable_skill_flag_works_end_to_end(self) -> None:
        write_skill(self.root, "grill-with-docs")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = INSTALLER.main(
                ["--enable-skill", "grill-with-docs", "--target", str(self.root)]
            )
        self.assertEqual(status, 0)
        self.assertFalse(
            INSTALLER.skill_is_model_hidden(self.root / "grill-with-docs")
        )
        self.assertIn("visible to the model", output.getvalue())
        self.assertEqual(
            INSTALLER.read_model_decisions([self.root]),
            {"grill-with-docs": "enabled"},
        )

    def test_enabling_a_missing_skill_is_an_error(self) -> None:
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = INSTALLER.main(
                ["--enable-skill", "no-such", "--target", str(self.root)]
            )
        self.assertEqual(status, 2)
        self.assertIn("not installed", errors.getvalue())

    def test_conflicting_enable_and_hide_are_refused(self) -> None:
        write_skill(self.root, "grill-with-docs")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = INSTALLER.main(
                [
                    "--enable-skill", "grill-with-docs",
                    "--hide-skill", "grill-with-docs",
                    "--target", str(self.root),
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("both --enable-skill and --hide-skill", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
