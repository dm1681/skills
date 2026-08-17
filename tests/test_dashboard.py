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
GLOBAL = skills_tui.GLOBAL


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
        for flag in (
            "--graphify",
            "--matt-skills",
            "--matt-ref",
            "--target",
            "--global-instructions",
        ):
            arguments = [flag, "x"] if flag in ("--target", "--matt-ref") else [flag]
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

    def test_presence_is_probed_by_the_marker_not_the_row_name(self) -> None:
        """matt-skills installs many directories; none is called matt-skills."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                skills_tui.external_state("matt-skills", [root]), skills_tui.AVAILABLE
            )
            (root / "setup-matt-pocock-skills").mkdir()
            self.assertEqual(
                skills_tui.external_state("matt-skills", [root]), skills_tui.INSTALLED
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
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self, guided=False) -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(
            self.project, "project", ["claude"], "copy", guided, home=self.home
        )

    def claude_root(self) -> Path:
        return self.project / ".claude" / "skills"

    async def test_every_bundled_skill_gets_a_row(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(
                [row.skill for row in app.rows()], BUNDLED + EXTERNAL + [GLOBAL]
            )

    async def test_down_moves_focus_even_when_the_list_overflows(self) -> None:
        """The scroll container must not swallow the arrow keys; it did once,
        whenever the list was long enough to scroll."""
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(app.focused, app.rows()[1])

    async def test_space_selects_the_focused_row(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            self.assertEqual(app.selected, {BUNDLED[0]})
            await pilot.press("space")
            self.assertEqual(app.selected, set())

    async def test_the_three_kinds_are_listed_under_separate_headings(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            titles = [title for title, _, _, _ in app.sections()]
            self.assertEqual(
                titles, ["YOUR SKILLS", "EXTERNAL TOOLS", "GLOBAL INSTRUCTIONS"]
            )
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
            self.assertEqual(app.selected, set(BUNDLED + EXTERNAL + [GLOBAL]))
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


class GlobalInstructionRowTests(unittest.IsolatedAsyncioTestCase):
    """The global-instructions row: diffed against what the mode would write,
    installed through install.install_global_instructions, backed up first."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "project"
        self.project.mkdir()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self, mode="copy") -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(
            self.project, "project", ["claude"], mode, False, home=self.home
        )

    def global_row(self, app: skills_tui.SkillsApp) -> skills_tui.SkillRow:
        return next(row for row in app.rows() if row.skill == GLOBAL)

    async def select_global(self, app, pilot) -> None:
        self.global_row(app).focus()
        await pilot.press("space")
        await pilot.pause()

    def test_a_fresh_home_reads_as_available(self) -> None:
        self.assertEqual(
            skills_tui.global_state(self.home, "copy"), skills_tui.AVAILABLE
        )

    def test_an_installed_home_matches_the_mode_that_wrote_it(self) -> None:
        install.install_global_instructions(self.home, "link", False)
        self.assertEqual(
            skills_tui.global_state(self.home, "link"), skills_tui.INSTALLED
        )
        # Probed for the other mode the same files count as differing, because
        # installing in that mode really would replace them.
        self.assertEqual(
            skills_tui.global_state(self.home, "copy"), skills_tui.OUTDATED
        )

    def test_one_edited_file_outranks_a_current_one(self) -> None:
        install.install_global_instructions(self.home, "link", False)
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.write_text(claude.read_text(encoding="utf-8") + "\nedited\n", "utf-8")
        self.assertEqual(
            skills_tui.global_state(self.home, "link"), skills_tui.OUTDATED
        )

    async def test_installing_from_the_dashboard_writes_both_files(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_global(app, pilot)
            await pilot.press("i")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.installed_count, 1)
            self.assertEqual(app.failures, 0)
            self.assertEqual(self.global_row(app).state, skills_tui.INSTALLED)
        for path in (
            self.home / ".agents" / "AGENTS.md",
            self.home / ".claude" / "CLAUDE.md",
        ):
            self.assertIn(
                install.MANAGED_MARKER, path.read_text(encoding="utf-8")
            )

    async def test_replacing_asks_first_and_backs_the_old_files_up(self) -> None:
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.parent.mkdir(parents=True)
        claude.write_text("# hand written\n", encoding="utf-8")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(self.global_row(app).state, skills_tui.OUTDATED)
            await self.select_global(app, pilot)
            await pilot.press("i")
            await pilot.pause()
            self.assertIsInstance(app.screen, skills_tui.ConfirmReplace)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.failures, 0)
        backups = list((self.home / ".skills-backups" / ".claude").iterdir())
        self.assertEqual(
            ["# hand written\n"], [b.read_text(encoding="utf-8") for b in backups]
        )
        self.assertIn("@", claude.read_text(encoding="utf-8"))

    async def test_declining_the_replacement_leaves_the_files_alone(self) -> None:
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.parent.mkdir(parents=True)
        claude.write_text("# hand written\n", encoding="utf-8")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_global(app, pilot)
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(app.installed_count, 0)
        self.assertEqual(claude.read_text(encoding="utf-8"), "# hand written\n")

    async def test_flipping_the_mode_repaints_the_row_in_place(self) -> None:
        install.install_global_instructions(self.home, "link", False)
        app = self.app(mode="copy")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(self.global_row(app).state, skills_tui.OUTDATED)
            focused = app.rows()[3]
            focused.focus()
            await pilot.press("m")
            await pilot.pause()
            self.assertEqual(app.mode, "link")
            self.assertEqual(self.global_row(app).state, skills_tui.INSTALLED)
            # The repaint happened in place, so focus never jumped.
            self.assertEqual(app.focused, focused)

    async def test_the_review_lists_each_target_file_and_its_backup(self) -> None:
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.parent.mkdir(parents=True)
        claude.write_text("# hand written\n", encoding="utf-8")
        app = skills_tui.SkillsApp(
            self.project, "project", ["claude"], "copy", True, home=self.home
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected.add(GLOBAL)
            app.step = 4
            app.render_main()
            await pilot.pause()
            text = " ".join(
                str(widget.content) for widget in app._main.query(Static)
            )
            self.assertIn(str(self.home / ".agents" / "AGENTS.md"), text)
            self.assertIn(str(claude), text)
            self.assertIn(str(self.home / ".skills-backups" / ".claude"), text)

    async def test_enter_previews_the_instructions_text(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.global_row(app).focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, skills_tui.PreviewScreen)
            self.assertIn(
                "Global agent instructions", app.screen.body()
            )


HIDDEN_SKILL = (
    "---\n"
    "name: {name}\n"
    "description: Grill the plan. Use when stress-testing.\n"
    "disable-model-invocation: true\n"
    "---\n"
    "# Body\n"
)


class ReviewHiddenTests(unittest.IsolatedAsyncioTestCase):
    """Hidden skills unfold, collapsible, under the external row that owns them."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "project"
        self.root = self.project / ".claude" / "skills"
        self.root.mkdir(parents=True)
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self) -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(
            self.project, "project", ["claude"], "copy", False, home=self.home
        )

    def write_hidden(self, name: str) -> Path:
        skill_dir = self.root / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            HIDDEN_SKILL.format(name=name), encoding="utf-8"
        )
        return skill_dir

    def sub_rows(self, app: skills_tui.SkillsApp) -> list:
        return list(app._main.query(skills_tui.HiddenSkillRow))

    async def select_matt_row(self, app, pilot) -> None:
        next(row for row in app.rows() if row.skill == "matt-skills").focus()
        await pilot.press("space")
        await pilot.pause()

    async def test_selecting_matt_skills_expands_its_hidden_skills(self) -> None:
        self.write_hidden("grill-with-docs")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(self.sub_rows(app), [])
            await self.select_matt_row(app, pilot)
            rows = self.sub_rows(app)
            self.assertEqual([row.skill for row in rows], ["grill-with-docs"])
            self.assertFalse(rows[0].visible_to_model)
            # The sub-rows sit directly under their parent in the focus order.
            nav = app.nav_rows()
            parent = next(i for i, r in enumerate(nav) if r.skill == "matt-skills")
            self.assertIsInstance(nav[parent + 1], skills_tui.HiddenSkillRow)

    async def test_deselecting_collapses_the_sub_rows(self) -> None:
        self.write_hidden("grill-with-docs")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_matt_row(app, pilot)
            self.assertEqual(len(self.sub_rows(app)), 1)
            await pilot.press("space")  # focus stayed on matt-skills
            await pilot.pause()
            self.assertEqual(self.sub_rows(app), [])

    async def test_space_on_a_sub_row_toggles_the_files_and_records(self) -> None:
        skill_dir = self.write_hidden("grill-with-docs")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_matt_row(app, pilot)
            await pilot.press("down")  # from matt-skills onto its first sub-row
            await pilot.press("space")
            await pilot.pause()
            self.assertFalse(install.skill_is_model_hidden(skill_dir))
            self.assertEqual(
                install.read_model_decisions([self.root]),
                {"grill-with-docs": "enabled"},
            )
            await pilot.press("space")
            await pilot.pause()
            self.assertTrue(install.skill_is_model_hidden(skill_dir))
            self.assertEqual(
                install.read_model_decisions([self.root]),
                {"grill-with-docs": "hidden"},
            )

    async def test_a_decided_skill_stays_reviewable(self) -> None:
        """A recorded choice must be revisitable, or one wrong press is final."""
        skill_dir = self.write_hidden("grill-with-docs")
        install.set_model_invocation(skill_dir, visible=True)
        install.record_model_decisions([self.root], {"grill-with-docs": "enabled"})
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_matt_row(app, pilot)
            rows = self.sub_rows(app)
            self.assertEqual([row.skill for row in rows], ["grill-with-docs"])
            self.assertTrue(rows[0].visible_to_model)

    async def test_selection_without_hidden_skills_adds_no_sub_rows(self) -> None:
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await self.select_matt_row(app, pilot)
            self.assertEqual(self.sub_rows(app), [])

    async def test_the_collapsed_row_advertises_its_hidden_count(self) -> None:
        """Silence would read as "nothing more to decide here"."""
        self.write_hidden("grill-with-docs")
        app = self.app()
        async with app.run_test() as pilot:
            await pilot.pause()
            row = next(row for row in app.rows() if row.skill == "matt-skills")
            self.assertIn("1 hidden from the model", row.note)


class GuidedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "project"
        self.project.mkdir()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def app(self, guided=None) -> skills_tui.SkillsApp:
        return skills_tui.SkillsApp(
            self.project, "project", ["claude"], "copy", guided, home=self.home
        )

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
