from __future__ import annotations

import argparse
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textual.widgets import Static  # noqa: E402

import install  # noqa: E402
import skills_tui  # noqa: E402

BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)
FIRST = BUNDLED[0]
EXTERNAL = list(install.EXTERNAL_NAMES)


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def namespace(**overrides) -> argparse.Namespace:
    values = {"non_interactive": False, "interactive": False}
    values.update(overrides)
    return argparse.Namespace(**values)


class EntryPointTests(unittest.TestCase):
    def test_a_bare_run_in_a_real_terminal_opens_the_dashboard(self) -> None:
        self.assertTrue(install.should_open_dashboard([], namespace(), TTY(), TTY(), {}))

    def test_passing_options_keeps_the_run_scripted(self) -> None:
        self.assertFalse(
            install.should_open_dashboard(["--skill", FIRST], namespace(), TTY(), TTY(), {})
        )

    def test_ci_never_takes_the_screen(self) -> None:
        self.assertFalse(
            install.should_open_dashboard([], namespace(), TTY(), TTY(), {"CI": "1"})
        )

    def test_redirected_streams_never_take_the_screen(self) -> None:
        self.assertFalse(
            install.should_open_dashboard([], namespace(), io.StringIO(), io.StringIO(), {})
        )

    def test_explicit_flags_win_over_detection(self) -> None:
        self.assertTrue(
            install.should_open_dashboard(
                ["--skill", FIRST], namespace(interactive=True),
                io.StringIO(), io.StringIO(), {},
            )
        )
        self.assertFalse(
            install.should_open_dashboard(
                [], namespace(non_interactive=True), TTY(), TTY(), {}
            )
        )

    def test_scripted_only_options_are_refused_by_the_dashboard(self) -> None:
        for flag in ("--graphify", "--matt-skills", "--target", "--global-instructions"):
            arguments = [flag, "x"] if flag == "--target" else [flag]
            args = install.parser().parse_args(["--interactive", *arguments])
            with self.assertRaises(install.InstallError) as caught:
                install.open_dashboard(args)
            self.assertIn(flag, str(caught.exception))


class StateTests(unittest.TestCase):
    def test_a_missing_copy_reads_as_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                skills_tui.skill_state(FIRST, [Path(directory)]), skills_tui.AVAILABLE
            )

    def test_a_matching_copy_reads_as_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install.install_one(install.SOURCE_ROOT / FIRST, root, "copy", False, False)
            self.assertEqual(skills_tui.skill_state(FIRST, [root]), skills_tui.INSTALLED)

    def test_a_differing_copy_reads_as_outdated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install.install_one(install.SOURCE_ROOT / FIRST, root, "copy", False, False)
            (root / FIRST / "SKILL.md").write_text("drifted", encoding="utf-8")
            self.assertEqual(skills_tui.skill_state(FIRST, [root]), skills_tui.OUTDATED)

    def test_one_stale_root_outranks_a_current_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current, stale = Path(directory) / "a", Path(directory) / "b"
            for root in (current, stale):
                install.install_one(install.SOURCE_ROOT / FIRST, root, "copy", False, False)
            (stale / FIRST / "SKILL.md").write_text("drifted", encoding="utf-8")
            self.assertEqual(
                skills_tui.skill_state(FIRST, [current, stale]), skills_tui.OUTDATED
            )

    def test_frontmatter_is_stripped_from_the_preview(self) -> None:
        body = skills_tui._without_frontmatter("---\nname: x\n---\n# Title\n\nbody\n")
        self.assertTrue(body.startswith("# Title"))

    def test_a_file_without_frontmatter_is_left_alone(self) -> None:
        self.assertEqual(skills_tui._without_frontmatter("# Title\n"), "# Title\n")


class ExternalToolTests(unittest.TestCase):
    """External tools are installed by their own CLI, so they read differently."""

    def test_an_absent_tool_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                skills_tui.external_state("graphify", [Path(directory)]),
                skills_tui.AVAILABLE,
            )

    def test_a_present_tool_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "graphify").mkdir()
            self.assertEqual(
                skills_tui.external_state("graphify", [root]), skills_tui.INSTALLED
            )

    def test_one_root_missing_it_outranks_a_root_that_has_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            has, lacks = Path(directory) / "a", Path(directory) / "b"
            (has / "graphify").mkdir(parents=True)
            lacks.mkdir()
            self.assertEqual(
                skills_tui.external_state("graphify", [has, lacks]),
                skills_tui.AVAILABLE,
            )

    def test_a_present_tool_offers_update_not_skip(self) -> None:
        """Re-running an external installer upgrades; it is never a no-op."""
        colour, label, verb = skills_tui.external_meaning(skills_tui.INSTALLED)
        self.assertEqual(verb, "update")
        self.assertEqual(colour, skills_tui.REPLACE)
        self.assertNotEqual(label, "UP TO DATE")

    def test_an_absent_tool_reads_as_an_additive_install(self) -> None:
        colour, _, verb = skills_tui.external_meaning(skills_tui.AVAILABLE)
        self.assertEqual((colour, verb), (skills_tui.ADD, "install"))

    def test_every_registered_tool_has_an_installer_wired(self) -> None:
        """A registry entry with nothing wired would fail only at install time."""
        app = skills_tui.SkillsApp(Path.cwd(), "project", ["claude"], "copy", False)
        self.assertEqual(
            sorted(install.EXTERNAL_NAMES), sorted(app.external_installers())
        )

    def test_an_unregistered_tool_is_refused(self) -> None:
        app = skills_tui.SkillsApp(Path.cwd(), "project", ["claude"], "copy", False)
        with self.assertRaises(install.InstallError) as caught:
            app.install_external("not-a-tool")
        self.assertIn("no installer wired", str(caught.exception))

    def test_the_preview_describes_a_tool_this_repo_does_not_carry(self) -> None:
        body = skills_tui.PreviewScreen("graphify").body()
        self.assertIn("External tool", body)
        self.assertIn("graphifyy", body)


class ColourContractTests(unittest.TestCase):
    """Each hue means one thing, so the mapping is worth pinning down."""

    def test_every_state_maps_to_a_colour_and_a_verb(self) -> None:
        self.assertEqual(
            {state: verb for state, (_, _, verb) in skills_tui.MEANING.items()},
            {
                skills_tui.AVAILABLE: "install",
                skills_tui.OUTDATED: "replace",
                skills_tui.INSTALLED: "skip",
            },
        )

    def test_no_two_states_share_a_colour(self) -> None:
        colours = [colour for colour, _, _ in skills_tui.MEANING.values()]
        self.assertEqual(len(colours), len(set(colours)))

    def test_selection_and_failure_never_double_as_state_colours(self) -> None:
        state_colours = {colour for colour, _, _ in skills_tui.MEANING.values()}
        self.assertNotIn(skills_tui.YOU, state_colours)
        self.assertNotIn(skills_tui.FAIL, state_colours)

    def test_a_gradient_interpolates_between_its_endpoints(self) -> None:
        self.assertEqual(skills_tui.blend("#000000", "#ffffff", 0.5), "#808080")
        self.assertIn(skills_tui.YOU, skills_tui.gradient("ab", skills_tui.YOU, skills_tui.ADD))


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self, guided=False) -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(self.project, "project", ["claude"], "copy", guided)

    def claude_root(self) -> Path:
        return self.project / ".claude" / "skills"

    async def test_every_bundled_skill_gets_a_row(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual([row.skill for row in app.rows()], BUNDLED + EXTERNAL)

    async def test_space_selects_the_focused_row(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            self.assertEqual(app.selected, {BUNDLED[0]})
            await pilot.press("space")
            self.assertEqual(app.selected, set())

    async def test_the_two_kinds_are_listed_under_separate_headings(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            titles = [title for title, _, _, _ in app.sections()]
            self.assertEqual(titles, ["YOUR SKILLS", "EXTERNAL TOOLS"])
            yours = next(names for title, _, names, _ in app.sections() if title == "YOUR SKILLS")
            theirs = next(
                names for title, _, names, _ in app.sections() if title == "EXTERNAL TOOLS"
            )
            self.assertEqual(yours, BUNDLED)
            self.assertEqual(theirs, EXTERNAL)

    async def test_an_empty_group_gets_no_heading(self) -> None:
        """A heading over nothing reads as a category that failed to load."""
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.view = "differs"
            self.assertEqual(app.sections(), [])

    async def test_an_external_row_is_marked_external(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            by_name = {row.skill: row for row in app.rows()}
            self.assertTrue(by_name[EXTERNAL[0]].external)
            self.assertFalse(by_name[BUNDLED[0]].external)

    async def test_selecting_an_external_tool_plans_it_as_external(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected.add(EXTERNAL[0])
            entry = next(row for row in app.plan() if row[0] == EXTERNAL[0])
            self.assertTrue(entry[3])
            self.assertEqual(entry[2], "install")

    async def test_a_toggles_everything_then_nothing(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            self.assertEqual(app.selected, set(BUNDLED + EXTERNAL))
            await pilot.press("a")
            self.assertEqual(app.selected, set())

    async def test_scope_and_mode_are_switchable_in_place(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            self.assertEqual(app.scope, "user")
            await pilot.press("s")
            self.assertEqual(app.scope, "project")
            await pilot.press("m")
            self.assertEqual(app.mode, "link")

    async def test_the_view_filter_narrows_the_list(self) -> None:
        install.install_one(
            install.SOURCE_ROOT / BUNDLED[0], self.claude_root(), "copy", False, False
        )
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")  # all -> differs
            self.assertEqual(app.view, "differs")
            self.assertEqual(app.rows(), [])
            await pilot.press("v")  # differs -> up to date
            self.assertEqual([row.skill for row in app.rows()], [BUNDLED[0]])

    async def test_installing_writes_the_skill_and_a_receipt(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.press("i")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.installed_count, 1)
            self.assertEqual(app.failures, 0)
        self.assertTrue((self.claude_root() / BUNDLED[0] / "SKILL.md").is_file())
        self.assertTrue((self.claude_root() / skills_tui.RECEIPT).is_file())

    async def test_rows_report_the_new_state_after_installing(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.press("i")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.rows()[0].state, skills_tui.INSTALLED)
            self.assertEqual(app.selected, set())

    async def test_installing_nothing_is_refused(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            self.assertEqual(app.installed_count, 0)
            self.assertFalse(self.claude_root().exists())

    async def test_a_differing_install_asks_before_it_is_replaced(self) -> None:
        install.install_one(
            install.SOURCE_ROOT / BUNDLED[0], self.claude_root(), "copy", False, False
        )
        (self.claude_root() / BUNDLED[0] / "SKILL.md").write_text("drifted", "utf-8")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(app.rows()[0].state, skills_tui.OUTDATED)
            await pilot.press("space")
            await pilot.press("i")
            await pilot.pause()
            self.assertIsInstance(app.screen, skills_tui.ConfirmReplace)
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(app.installed_count, 0)
        self.assertEqual(
            (self.claude_root() / BUNDLED[0] / "SKILL.md").read_text(encoding="utf-8"),
            "drifted",
        )

    async def test_approving_the_replacement_backs_the_old_copy_up(self) -> None:
        install.install_one(
            install.SOURCE_ROOT / BUNDLED[0], self.claude_root(), "copy", False, False
        )
        (self.claude_root() / BUNDLED[0] / "SKILL.md").write_text("drifted", "utf-8")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.installed_count, 1)
        landed = (self.claude_root() / BUNDLED[0] / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotEqual(landed, "drifted")
        self.assertTrue(list((self.project / ".claude" / ".skills-backups").rglob("SKILL.md")))

    async def test_enter_opens_the_skill_preview(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, skills_tui.PreviewScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, skills_tui.PreviewScreen)


class GuidedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self, guided=None) -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(self.project, "project", ["claude"], "copy", guided)

    async def test_a_first_run_starts_guided(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(app.guided())
            self.assertEqual(app.step, 1)

    async def test_a_destination_with_a_receipt_skips_the_guide(self) -> None:
        root = self.project / ".claude" / "skills"
        install.write_receipt(root, [], "copy", False)
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(app.guided())

    async def test_the_guide_can_be_forced_and_suppressed(self) -> None:
        forced = self.app(guided=True)
        async with forced.run_test() as pilot:
            await pilot.pause()
            self.assertTrue(forced.guided())
        plain = self.app(guided=False)
        async with plain.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(plain.guided())

    async def test_enter_and_escape_walk_the_steps(self) -> None:
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            for expected in (2, 3, 4):
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.step, expected)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.step, 3)

    async def test_step_one_chooses_the_scope(self) -> None:
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual([c.value for c in app.choices()], ["project", "user"])
            await pilot.press("down")
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(app.scope, "user")

    async def test_step_three_chooses_the_mode(self) -> None:
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")  # -> which
            await pilot.press("enter")  # -> mode
            await pilot.pause()
            self.assertEqual([c.value for c in app.choices()], ["copy", "link"])
            await pilot.press("down")
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(app.mode, "link")

    async def test_the_review_step_counts_the_plan(self) -> None:
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")  # which
            await pilot.press("space")  # select the first skill
            await pilot.pause()
            self.assertEqual(
                app.plan(), [(BUNDLED[0], skills_tui.AVAILABLE, "install", False)]
            )

    async def test_the_review_says_what_it_cannot_account_for(self) -> None:
        """Silence here would read as "these counts cover everything"."""
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected.add(EXTERNAL[0])
            app.step = 4
            app.render_main()
            await pilot.pause()
            text = " ".join(
                str(widget.content) for widget in app._main.query(Static)
            )
            self.assertIn("its own installer", text)
            self.assertIn("nor backed up by this tool", text)
            self.assertIn("ignores copy/link", text)

    async def test_finishing_the_guide_installs_and_returns_to_the_dashboard(self) -> None:
        app = self.app(guided=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")  # which
            await pilot.press("space")  # select
            await pilot.press("enter")  # mode
            await pilot.press("enter")  # review
            await pilot.pause()
            self.assertEqual(app.step, 4)
            await pilot.press("enter")  # write it
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.installed_count, 1)
            self.assertFalse(app.guided())
        root = self.project / ".claude" / "skills"
        self.assertTrue((root / BUNDLED[0] / "SKILL.md").is_file())

    async def test_g_switches_between_the_two_modes(self) -> None:
        app = self.app(guided=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()
            self.assertTrue(app.guided())
            await pilot.press("g")
            await pilot.pause()
            self.assertFalse(app.guided())


if __name__ == "__main__":
    unittest.main()
