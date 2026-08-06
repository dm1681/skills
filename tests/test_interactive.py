from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("interactive_installer", ROOT / "install.py")
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)
SKILL = "wow-addon-dev"
EXPLAINER_SKILL = "semantic-pr-review"


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class InteractiveTests(unittest.TestCase):
    def navigable_console(self, keys: list[str]) -> tuple[object, TTYBuffer]:
        output = TTYBuffer()
        key_stream = iter(keys)
        console = INSTALLER.Console(
            TTYBuffer(),
            output,
            color=False,
            unicode=True,
            width=72,
            key_reader=lambda: next(key_stream),
        )
        return console, output

    def test_auto_interactive_only_for_empty_real_terminal(self) -> None:
        args = INSTALLER.parser().parse_args([])
        tty_in, tty_out = TTYBuffer(), TTYBuffer()
        pipe = io.StringIO()
        self.assertTrue(INSTALLER.should_use_wizard([], args, tty_in, tty_out, {}))
        self.assertFalse(INSTALLER.should_use_wizard([], args, pipe, tty_out, {}))
        self.assertFalse(INSTALLER.should_use_wizard([], args, tty_in, pipe, {}))
        self.assertFalse(INSTALLER.should_use_wizard([], args, tty_in, tty_out, {"CI": "1"}))
        self.assertFalse(INSTALLER.should_use_wizard(["--dry-run"], args, tty_in, tty_out, {}))

    def test_explicit_interactive_and_non_interactive_controls(self) -> None:
        tty_in, tty_out = TTYBuffer(), TTYBuffer()
        interactive = INSTALLER.parser().parse_args(["--interactive"])
        automatic = INSTALLER.parser().parse_args(["--non-interactive"])
        self.assertTrue(
            INSTALLER.should_use_wizard(
                ["--interactive"], interactive, io.StringIO(), io.StringIO(), {}
            )
        )
        self.assertFalse(
            INSTALLER.should_use_wizard([], automatic, tty_in, tty_out, {})
        )

    def test_arrow_keys_space_and_enter_select_one_option(self) -> None:
        console, output = self.navigable_console(["down", "space", "enter"])
        selected = INSTALLER._select_one(
            console,
            "Install mode",
            [
                ("copy", "Copy files", "Stable local copy."),
                ("link", "Create links", "Live checkout changes."),
            ],
            "copy",
        )
        self.assertEqual("link", selected)
        self.assertIn("↑/↓", output.getvalue())
        self.assertIn("Space", output.getvalue())
        self.assertIn("Enter", output.getvalue())

    def test_navigation_redraws_relative_to_rendered_rows(self) -> None:
        console, output = self.navigable_console(["down", "enter"])
        INSTALLER._select_one(
            console,
            "Install mode",
            [
                ("copy", "Copy files", "Stable local copy."),
                ("link", "Create links", "Live checkout changes."),
            ],
            "copy",
        )
        rendered = output.getvalue()
        self.assertNotIn("\033[s", rendered)
        self.assertNotIn("\033[u", rendered)
        self.assertRegex(rendered, r"\033\[\d+F\033\[J")

    def test_space_toggles_multiple_options_before_enter(self) -> None:
        console, _ = self.navigable_console(
            ["space", "down", "space", "down", "space", "enter"]
        )
        selected = INSTALLER._select_many(
            console,
            "Coding agents",
            [
                ("universal", "Shared", "Shared agents directory."),
                ("codex", "Codex", "Codex integration."),
                ("claude", "Claude", "Claude integration."),
            ],
            ["universal"],
        )
        self.assertEqual(["codex", "claude"], selected)

    def test_confirm_uses_keyboard_option_selection(self) -> None:
        console, _ = self.navigable_console(["up", "space", "enter"])
        self.assertTrue(INSTALLER._confirm(console, "Apply this setup?", False))

    def test_full_wizard_can_be_completed_with_navigation_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args(["--home", directory])
            console, _ = self.navigable_console(
                [
                    "enter",  # user scope
                    "enter",  # every skill root
                    "down",
                    "enter",  # link mode
                    "up",
                    "enter",  # Graphify yes
                    "enter",  # apply
                ]
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("user", args.scope)
            self.assertEqual(["universal", "claude"], args.agent)
            self.assertEqual("link", args.mode)
            self.assertFalse(args.matt_skills)
            self.assertTrue(args.graphify)

    def test_multiple_bundled_skills_are_selectable_with_summaries(self) -> None:
        bundled = INSTALLER.available_skills()
        self.assertIn(SKILL, bundled)
        self.assertIn(EXPLAINER_SKILL, bundled)
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args(["--home", directory])
            output = TTYBuffer()
            console = INSTALLER.Console(
                # scope, agents, skills, mode, Graphify, proceed
                TTYBuffer(f"\n\n{bundled.index(EXPLAINER_SKILL) + 1}\n\nn\ny\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertTrue(INSTALLER.run_wizard(args, bundled, console))
            self.assertEqual([EXPLAINER_SKILL], args.skill)
        rendered = output.getvalue()
        for name in bundled:
            with self.subTest(skill=name):
                self.assertIn(name, rendered)
                self.assertIn(INSTALLER.skill_summary(name), rendered)

    def test_wizard_never_offers_to_fetch_third_party_skills(self) -> None:
        """No bundled skill requires mattpocock/skills, so the wizard must not
        offer to download them. `--matt-skills` remains the only way in."""
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args(["--home", directory])
            output = TTYBuffer()
            console = INSTALLER.Console(
                # scope, agents, skills, mode, Graphify, proceed
                TTYBuffer("\n\n2\n\nn\ny\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertTrue(
                INSTALLER.run_wizard(args, [SKILL, EXPLAINER_SKILL], console)
            )
            self.assertEqual([EXPLAINER_SKILL], args.skill)
            self.assertFalse(args.matt_skills)
            self.assertFalse(args.graphify)
        rendered = output.getvalue()
        self.assertNotIn("mattpocock/skills", rendered)

    def test_skill_summaries_come_from_the_bundled_agent_interface(self) -> None:
        self.assertEqual(
            "Build portable, snapshot-verified PR flows",
            INSTALLER.skill_summary(EXPLAINER_SKILL),
        )
        self.assertEqual(
            "Bundled in this collection.",
            INSTALLER.skill_summary("skill-without-an-interface-file"),
        )

    def test_windows_extended_arrow_codes_are_normalized(self) -> None:
        self.assertEqual("up", INSTALLER._normalize_windows_key("\xe0", "H"))
        self.assertEqual("down", INSTALLER._normalize_windows_key("\x00", "P"))
        self.assertEqual("space", INSTALLER._normalize_windows_key(" "))
        self.assertEqual("enter", INSTALLER._normalize_windows_key("\r"))

    def test_terminal_restore_runs_once_when_console_closes(self) -> None:
        restored: list[bool] = []
        console = INSTALLER.Console(
            io.StringIO(),
            io.StringIO(),
            color=False,
            unicode=False,
            terminal_restore=lambda: restored.append(True),
        )
        console.close()
        console.close()
        self.assertEqual([True], restored)

    def test_string_stream_keeps_numbered_prompt_fallback(self) -> None:
        console = INSTALLER.Console(
            TTYBuffer("2\n"), TTYBuffer(), color=False, unicode=False
        )
        self.assertFalse(console.supports_navigation)
        selected = INSTALLER._select_one(
            console,
            "Mode",
            [("copy", "Copy", "Copy files."), ("link", "Link", "Link files.")],
            "copy",
        )
        self.assertEqual("link", selected)

    def test_default_wizard_configures_shared_user_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args(["--home", directory])
            # scope, agents, mode, Graphify=yes, proceed
            output = TTYBuffer()
            console = INSTALLER.Console(
                TTYBuffer("\n\n\ny\ny\n"),
                output,
                color=False,
                unicode=False,
                width=32,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("user", args.scope)
            self.assertEqual(["universal", "claude"], args.agent)
            self.assertEqual([SKILL], args.skill)
            self.assertEqual("copy", args.mode)
            self.assertFalse(args.matt_skills)
            self.assertTrue(args.graphify)
            self.assertIn("Skills setup", output.getvalue())
            self.assertIn("Review", output.getvalue())
            self.assertLessEqual(max(map(len, output.getvalue().splitlines())), 32)

    def test_project_wizard_uses_explicit_agent_and_link_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            args = INSTALLER.parser().parse_args(["--home", str(home)])
            # project, path, Codex, link, no Graphify, proceed
            answers = f"2\n{directory}\n2\n2\nn\ny\n"
            console = INSTALLER.Console(
                TTYBuffer(answers),
                TTYBuffer(),
                color=False,
                unicode=False,
                width=72,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("project", args.scope)
            self.assertEqual(Path(directory).resolve(), args.project_dir)
            self.assertEqual(["codex"], args.agent)
            self.assertEqual("link", args.mode)
            self.assertFalse(args.matt_skills)
            self.assertFalse(args.graphify)

    def test_status_output_wraps_long_paths_in_very_narrow_terminal(self) -> None:
        output = TTYBuffer()
        console = INSTALLER.Console(
            TTYBuffer(), output, color=False, unicode=False, width=24
        )
        console.note("installed /a/very/long/path/that/cannot/fit/on/one/line")
        console.success("Setup complete at /another/extremely/long/destination")
        self.assertLessEqual(max(map(len, output.getvalue().splitlines())), 24)

    def test_cancel_returns_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args(["--home", directory])
            # default scope, agent, mode, no Graphify, cancel at review
            output = TTYBuffer()
            console = INSTALLER.Console(
                TTYBuffer("\n\n\nn\nn\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertFalse(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertIn("No changes made", output.getvalue())

    def stale_home(self, directory: str) -> Path:
        """A home directory holding an installed skill that differs from this release."""
        home = Path(directory)
        destination = home / ".agents" / "skills" / SKILL
        destination.mkdir(parents=True)
        (destination / "SKILL.md").write_text("stale local edit\n", encoding="utf-8")
        return home

    def test_existing_differing_installations_ask_before_replacing(self) -> None:
        """The backup confirmation is an extra prompt, so it must be covered.

        Without it, every wizard test that omits --home silently inherits the
        developer's own skill directories and passes or fails on whether those
        happen to match the repository.
        """
        with tempfile.TemporaryDirectory() as directory:
            home = self.stale_home(directory)
            args = INSTALLER.parser().parse_args(["--home", str(home)])
            output = TTYBuffer()
            # scope, agents, mode, no Graphify, back up, apply
            console = INSTALLER.Console(
                TTYBuffer("\n\n\nn\ny\ny\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertTrue(args.force)
            rendered = output.getvalue()
            self.assertIn("Existing installations", rendered)
            self.assertIn("1 installed skill path differs", rendered)

    def test_backup_warning_agrees_with_the_number_of_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self.stale_home(directory)
            for root in (".claude",):
                destination = home / root / "skills" / SKILL
                destination.mkdir(parents=True)
                (destination / "SKILL.md").write_text("stale\n", encoding="utf-8")
            args = INSTALLER.parser().parse_args(["--home", str(home)])
            output = TTYBuffer()
            console = INSTALLER.Console(
                TTYBuffer("\n\n\nn\ny\ny\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertIn("2 installed skill paths differ from", output.getvalue())

    def test_declining_the_backup_confirmation_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = self.stale_home(directory)
            args = INSTALLER.parser().parse_args(["--home", str(home)])
            output = TTYBuffer()
            console = INSTALLER.Console(
                TTYBuffer("\n\n\nn\nn\n"),
                output,
                color=False,
                unicode=False,
                width=72,
            )
            self.assertFalse(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertFalse(args.force)
            self.assertIn("No changes made", output.getvalue())


if __name__ == "__main__":
    unittest.main()
