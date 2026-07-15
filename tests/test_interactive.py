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
                width=56,
            )
            self.assertTrue(INSTALLER.run_wizard(args, [SKILL], console))
            self.assertEqual("user", args.scope)
            self.assertEqual(["universal"], args.agent)
            self.assertEqual([SKILL], args.skill)
            self.assertEqual("copy", args.mode)
            self.assertTrue(args.graphify)
            self.assertIn("Skills setup", output.getvalue())
            self.assertIn("Review", output.getvalue())
            self.assertLessEqual(max(map(len, output.getvalue().splitlines())), 56)

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

    def test_status_output_wraps_long_paths_at_minimum_width(self) -> None:
        output = TTYBuffer()
        console = INSTALLER.Console(
            TTYBuffer(), output, color=False, unicode=False, width=40
        )
        console.note("installed /a/very/long/path/that/cannot/fit/on/one/line")
        console.success("Setup complete at /another/extremely/long/destination")
        self.assertLessEqual(max(map(len, output.getvalue().splitlines())), 40)

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
