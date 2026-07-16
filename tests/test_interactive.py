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
SKILL = "orchestrate-olympus"


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
                    "enter",  # shared agents
                    "down",
                    "enter",  # link mode
                    "up",
                    "enter",  # Graphify yes
                    "enter",  # apply
                ]
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("user", args.scope)
            self.assertEqual(["universal"], args.agent)
            self.assertEqual("link", args.mode)
            self.assertTrue(args.graphify)

    def test_windows_extended_arrow_codes_are_normalized(self) -> None:
        self.assertEqual("up", INSTALLER._normalize_windows_key("\xe0", "H"))
        self.assertEqual("down", INSTALLER._normalize_windows_key("\x00", "P"))
        self.assertEqual("space", INSTALLER._normalize_windows_key(" "))
        self.assertEqual("enter", INSTALLER._normalize_windows_key("\r"))

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
            # scope, agents, mode, graphify=yes, proceed
            output = TTYBuffer()
            console = INSTALLER.Console(
                TTYBuffer("\n\n\ny\n\n"),
                output,
                color=False,
                unicode=False,
                width=32,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("user", args.scope)
            self.assertEqual(["universal"], args.agent)
            self.assertEqual([SKILL], args.skill)
            self.assertEqual("copy", args.mode)
            self.assertTrue(args.graphify)
            self.assertIn("Skills setup", output.getvalue())
            self.assertIn("Review", output.getvalue())
            self.assertLessEqual(max(map(len, output.getvalue().splitlines())), 32)

    def test_project_wizard_uses_explicit_agent_and_link_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = INSTALLER.parser().parse_args([])
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
        args = INSTALLER.parser().parse_args([])
        # default scope, agent, mode, no Graphify, cancel at review
        output = TTYBuffer()
        console = INSTALLER.Console(
            TTYBuffer("\n\n\n\nn\n"),
            output,
            color=False,
            unicode=False,
            width=72,
        )
        self.assertFalse(INSTALLER.run_wizard(args, [SKILL], console))
        self.assertIn("No changes made", output.getvalue())


if __name__ == "__main__":
    unittest.main()
