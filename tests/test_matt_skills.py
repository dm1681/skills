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


def write_upstream(checkout: Path, *relative: str) -> None:
    """Lay out an upstream checkout the way mattpocock/skills is laid out."""
    for path in relative:
        skill_dir = checkout / "skills" / path
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_dir.name}\n---\n", encoding="utf-8"
        )


class MattSkillsTests(unittest.TestCase):
    def test_fetch_pins_one_revision_of_the_upstream_repository(self) -> None:
        self.assertEqual(
            [
                ["git", "init", "--quiet"],
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "--depth",
                    "1",
                    "https://github.com/mattpocock/skills.git",
                    "v9.9.9",
                ],
                [
                    "git",
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "checkout",
                    "--quiet",
                    "--detach",
                    "FETCH_HEAD",
                ],
            ],
            INSTALLER.matt_skills_fetch_commands("v9.9.9"),
        )

    def test_checkout_keeps_upstream_line_endings(self) -> None:
        """Git for Windows enables core.autocrlf, which would rewrite every file.

        The same commit has to install the same bytes everywhere, and one
        upstream skill ships a shell script whose shebang a CRLF rewrite breaks.
        """
        checkout = INSTALLER.matt_skills_fetch_commands()[-1]
        self.assertIn("core.autocrlf=false", checkout)
        self.assertIn("core.eol=lf", checkout)

    def test_the_default_ref_is_pinned_rather_than_a_moving_branch(self) -> None:
        self.assertEqual(
            INSTALLER.matt_skills_fetch_commands()[1][-1], INSTALLER.MATT_SKILLS_REF
        )
        self.assertNotEqual(INSTALLER.MATT_SKILLS_REF, "main")

    def test_the_pinned_tag_is_backed_by_a_full_commit(self) -> None:
        """A tag can be force-moved; the commit beside it is what actually pins."""
        self.assertRegex(INSTALLER.MATT_SKILLS_COMMIT, r"^[0-9a-f]{40}$")

    def test_sources_are_flattened_across_upstream_categories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/tdd", "productivity/teach")
            self.assertEqual(
                ["tdd", "teach"],
                [source.name for source in INSTALLER.matt_skill_sources(checkout)],
            )

    def test_retired_skills_are_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/tdd", "deprecated/old-one")
            self.assertEqual(
                ["tdd"],
                [source.name for source in INSTALLER.matt_skill_sources(checkout)],
            )

    def test_only_the_top_level_deprecated_category_is_skipped(self) -> None:
        """`skills/deprecated/` is the retirement shelf; deeper names are not."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/deprecated/still-shipped")
            self.assertEqual(
                ["still-shipped"],
                [source.name for source in INSTALLER.matt_skill_sources(checkout)],
            )

    def test_a_nested_reference_skill_is_not_a_second_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/tdd", "engineering/tdd/references/tdd")
            self.assertEqual(
                [checkout / "skills" / "engineering" / "tdd"],
                INSTALLER.matt_skill_sources(checkout),
            )

    def test_a_nested_skill_is_ignored_whatever_the_walk_order(self) -> None:
        """A directory sorting before SKILL.md must not shadow its own skill.

        Path order is not ancestor-first: `Examples/` sorts ahead of `SKILL.md`
        on POSIX, and every nested name does on Windows, where paths compare as
        one case-folded string rather than component by component.
        """
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/tdd", "engineering/tdd/Examples/tdd")
            self.assertEqual(
                [checkout / "skills" / "engineering" / "tdd"],
                INSTALLER.matt_skill_sources(checkout),
            )

    def test_two_categories_claiming_one_name_stop_the_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/tdd", "productivity/tdd")
            with self.assertRaisesRegex(INSTALLER.InstallError, "two skills named tdd"):
                INSTALLER.matt_skill_sources(checkout)

    def test_names_differing_only_in_case_are_one_destination(self) -> None:
        """Windows and stock macOS would resolve both to the same directory."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "engineering/Foo", "productivity/foo")
            with self.assertRaisesRegex(INSTALLER.InstallError, "two skills named"):
                INSTALLER.matt_skill_sources(checkout)

    def test_a_checkout_without_skills_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(INSTALLER.InstallError, "no skills/ directory"):
                INSTALLER.matt_skill_sources(Path(directory))

    def test_install_fetches_then_copies_to_exact_resolved_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / ".agents" / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] != "fetch":
                    return
                write_upstream(cwd, "engineering/setup-matt-pocock-skills")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(
                    INSTALLER, "matt_skills_head", return_value=INSTALLER.MATT_SKILLS_COMMIT
                ),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run) as run,
            ):
                INSTALLER.install_matt_skills(
                    ["universal"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=lambda _: None,
                )
            self.assertEqual(3, run.call_count)
            self.assertTrue(
                (destination / "setup-matt-pocock-skills" / "SKILL.md").is_file()
            )

    def test_every_root_receives_the_same_upstream_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            roots = [base / ".agents" / "skills", base / ".claude" / "skills"]

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] == "fetch":
                    write_upstream(
                        cwd, "engineering/setup-matt-pocock-skills", "productivity/teach"
                    )

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(
                    INSTALLER, "matt_skills_head", return_value=INSTALLER.MATT_SKILLS_COMMIT
                ),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
            ):
                INSTALLER.install_matt_skills(
                    ["all"], roots, force=False, dry_run=False, emit=lambda _: None
                )
            for root in roots:
                self.assertEqual(
                    ["setup-matt-pocock-skills", "teach"],
                    sorted(path.name for path in root.iterdir()),
                )

    def test_an_upstream_layout_change_is_reported_not_half_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / ".agents" / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] == "fetch":
                    write_upstream(cwd, "engineering/tdd")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(
                    INSTALLER,
                    "matt_skills_head",
                    return_value=INSTALLER.MATT_SKILLS_COMMIT,
                ),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
            ):
                with self.assertRaisesRegex(
                    INSTALLER.InstallError, "setup-matt-pocock-skills"
                ):
                    INSTALLER.install_matt_skills(
                        ["universal"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )

    def test_unknown_agents_are_refused_before_anything_is_fetched(self) -> None:
        with mock.patch.object(
            INSTALLER,
            "_run",
            side_effect=AssertionError("an unknown agent must not reach the network"),
        ):
            with self.assertRaisesRegex(INSTALLER.InstallError, "unknown agent"):
                INSTALLER.install_matt_skills(
                    ["nope"], [ROOT], force=False, dry_run=False
                )

    def test_missing_git_is_actionable(self) -> None:
        with mock.patch.object(INSTALLER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(INSTALLER.InstallError, "requires git"):
                INSTALLER.install_matt_skills([], [ROOT], force=False, dry_run=False)

    def test_dry_run_prints_exact_commands_without_requiring_git(self) -> None:
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
                force=False, dry_run=True, ref="v1.0.0",
            )
        self.assertEqual(
            "would run  git init --quiet\n"
            "would run  git fetch --quiet --depth 1 "
            "https://github.com/mattpocock/skills.git v1.0.0\n"
            "would run  git -c core.autocrlf=false -c core.eol=lf "
            "checkout --quiet --detach FETCH_HEAD\n"
            f"would copy all discovered Matt Pocock skills -> {ROOT / '.agents' / 'skills'}\n"
            f"would copy all discovered Matt Pocock skills -> {ROOT / '.claude' / 'skills'}\n",
            output.getvalue(),
        )

    def test_an_unset_ref_falls_back_to_the_pinned_revision(self) -> None:
        self.assertIsNone(INSTALLER.parser().parse_args([]).matt_ref)
        self.assertEqual(
            "main", INSTALLER.parser().parse_args(["--matt-ref", "main"]).matt_ref
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            INSTALLER.install_matt_skills(
                ["claude"], [ROOT], force=False, dry_run=True, ref=None
            )
        self.assertIn(INSTALLER.MATT_SKILLS_REF, output.getvalue())

    def test_an_empty_ref_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaisesRegex(INSTALLER.InstallError, "empty value"):
            INSTALLER.install_matt_skills(
                ["claude"], [ROOT], force=False, dry_run=True, ref="  "
            )

    def test_a_moved_tag_stops_the_default_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] == "fetch":
                    write_upstream(cwd, "engineering/setup-matt-pocock-skills")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(INSTALLER, "matt_skills_head", return_value="f" * 40),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
            ):
                with self.assertRaisesRegex(INSTALLER.InstallError, "tag moved"):
                    INSTALLER.install_matt_skills(
                        ["claude"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )
            self.assertFalse(destination.exists())

    def test_a_named_ref_is_installed_without_the_pin_check(self) -> None:
        """--matt-ref names a revision; there is no second pin to hold it to."""
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] == "fetch":
                    write_upstream(cwd, "engineering/setup-matt-pocock-skills")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(INSTALLER, "matt_skills_head", return_value="f" * 40),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
            ):
                INSTALLER.install_matt_skills(
                    ["claude"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=lambda _: None,
                    ref="main",
                )
            self.assertTrue(
                (destination / "setup-matt-pocock-skills" / "SKILL.md").is_file()
            )

    def test_an_unverifiable_pin_stops_the_default_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"

            def fake_run(command: list[str], cwd: Path) -> None:
                if command[1] == "fetch":
                    write_upstream(cwd, "engineering/setup-matt-pocock-skills")

            with (
                mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
                mock.patch.object(INSTALLER, "matt_skills_head", return_value=""),
                mock.patch.object(INSTALLER, "_run", side_effect=fake_run),
            ):
                with self.assertRaisesRegex(
                    INSTALLER.InstallError, "pin cannot be verified"
                ):
                    INSTALLER.install_matt_skills(
                        ["claude"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )

    def test_a_ref_without_the_opt_in_is_refused(self) -> None:
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = INSTALLER.main(["--matt-ref", "main", "--dry-run"])
        self.assertEqual(status, 2)
        self.assertIn("--matt-ref only applies to --matt-skills", errors.getvalue())

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
            if command[1] != "fetch":
                return
            upstream = cwd / "skills" / "engineering"
            write_skill(upstream, "setup-matt-pocock-skills")
            write_skill(upstream, "grill-with-docs")

        with (
            mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
            mock.patch.object(
                    INSTALLER, "matt_skills_head", return_value=INSTALLER.MATT_SKILLS_COMMIT
                ),
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
