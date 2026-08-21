from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills_cli.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402
import skills_cli  # noqa: E402

BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)


class ArgumentTests(unittest.TestCase):
    def test_project_install_delegates_non_interactively(self) -> None:
        argv = skills_cli.install_argv(
            ["wow-addon-dev"],
            "project",
            Path("/repo"),
            [],
            "copy",
            False,
            False,
        )
        self.assertEqual(
            argv,
            [
                "--non-interactive",
                "--scope",
                "project",
                "--project-dir",
                str(Path("/repo")),
                "--mode",
                "copy",
                "--skill",
                "wow-addon-dev",
            ],
        )

    def test_optional_flags_are_forwarded(self) -> None:
        argv = skills_cli.install_argv(
            ["a", "b"],
            "user",
            Path("/repo"),
            ["claude", "universal"],
            "link",
            True,
            True,
        )
        self.assertEqual(argv[argv.index("--scope") + 1], "user")
        self.assertEqual(argv[argv.index("--mode") + 1], "link")
        self.assertEqual([argv[i + 1] for i, v in enumerate(argv) if v == "--agent"],
                         ["claude", "universal"])
        self.assertEqual([argv[i + 1] for i, v in enumerate(argv) if v == "--skill"],
                         ["a", "b"])
        self.assertIn("--force", argv)
        self.assertIn("--dry-run", argv)


class BareInvocationTests(unittest.TestCase):
    """What `skills` on its own does."""

    def run_bare(self, prompt: bool):
        """Run `skills` with no arguments in-process, capturing what it prints.

        The capture is not incidental. `main([])` prints the parser help
        straight to stdout, and running it in-process dumped that help into the
        middle of the suite's own output on every green run -- the reader then
        has to decide whether a wall of usage text is a failure. Holding it
        here keeps a passing run's output to dots, and hands the text to the
        one test that actually makes a claim about it.
        """
        seen = {}

        def fake_dashboard(project_dir, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return 0

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with unittest.mock.patch.object(skills_cli, "open_dashboard", fake_dashboard):
                with unittest.mock.patch.object(skills_cli, "can_prompt", lambda: prompt):
                    code = skills_cli.main([])
        return code, seen, stdout.getvalue()

    def test_it_opens_the_dashboard_not_the_guided_flow(self) -> None:
        """`skills` asks a question; it must not start an install.

        The guided flow used to open whenever the destination had no receipt,
        so the one case where someone was least likely to want a walkthrough --
        a directory nothing had been installed into -- is exactly the case that
        got one.
        """
        code, seen, _ = self.run_bare(prompt=True)
        self.assertEqual(0, code)
        self.assertIs(False, seen["kwargs"].get("guided"))

    def test_without_a_terminal_it_prints_help(self) -> None:
        code, seen, printed = self.run_bare(prompt=False)
        self.assertEqual(2, code)
        self.assertEqual({}, seen)
        # The test is named for the help, so assert the help: without this it
        # passed on the exit code alone and would have kept passing if the
        # command had started printing nothing at all.
        self.assertIn("usage:", printed)
        self.assertIn("setup-path", printed)


class ShimTests(unittest.TestCase):
    def test_sh_shim_uses_forward_slashes(self) -> None:
        shim = skills_cli.sh_shim(Path(r"C:\Users\dev\skills"))
        self.assertIn("REPO='C:/Users/dev/skills'", shim)
        self.assertNotIn("\\Users", shim)
        self.assertIn('"$CLI" "$@"', shim)

    def test_sh_shim_escapes_a_quote_in_the_path(self) -> None:
        self.assertEqual(skills_cli._sh_quote("a'b"), "'a'\\''b'")

    def test_cmd_shim_branches_with_labels_not_blocks(self) -> None:
        # Inside a parenthesized block batch expands %ERRORLEVEL% at parse time,
        # which would report the code from before the command that just ran.
        shim = skills_cli.cmd_shim(Path(r"C:\repo"))
        self.assertIn("goto run_uv", shim)
        self.assertIn(r'set "REPO=C:\repo"', shim)
        for line in shim.splitlines():
            if "%ERRORLEVEL%" in line:
                self.assertEqual(line.strip(), "exit /b %ERRORLEVEL%")

    def test_write_shims_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            first = skills_cli.write_shims(ROOT, bin_dir)
            self.assertTrue(all(status == "wrote" for _, status in first))
            second = skills_cli.write_shims(ROOT, bin_dir)
            self.assertTrue(all(status == "unchanged" for _, status in second))
            for path, _ in first:
                self.assertTrue(path.is_file())

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            results = skills_cli.write_shims(ROOT, bin_dir, dry_run=True)
            self.assertTrue(all(status == "would write" for _, status in results))
            self.assertFalse(bin_dir.exists())

    def test_windows_gets_a_batch_launcher_too(self) -> None:
        names = {path.name for path, _, _, _ in skills_cli.shims(ROOT, Path("bin"))}
        expected = {"skills", "skills.cmd"} if os.name == "nt" else {"skills"}
        self.assertEqual(names, expected)


class PathTests(unittest.TestCase):
    def test_path_membership_ignores_separator_style(self) -> None:
        bin_dir = Path("/home/dev/.local/bin")
        env = {"PATH": os.pathsep.join(["/usr/bin", str(bin_dir) + os.sep])}
        self.assertTrue(skills_cli.path_contains(bin_dir, env))

    def test_missing_directory_is_reported(self) -> None:
        self.assertFalse(
            skills_cli.path_contains(Path("/opt/bin"), {"PATH": "/usr/bin"})
        )

    def test_blank_entries_are_skipped(self) -> None:
        entries = skills_cli.path_entries({"PATH": os.pathsep.join(["", "/usr/bin", " "])})
        self.assertEqual([str(entry) for entry in entries], [str(Path("/usr/bin"))])

    def test_profile_follows_the_shell(self) -> None:
        home = Path("/home/dev")
        self.assertEqual(
            skills_cli.profile_for({"SHELL": "/bin/zsh"}, home), home / ".zshrc"
        )
        self.assertEqual(
            skills_cli.profile_for({"SHELL": "/bin/bash"}, home), home / ".bashrc"
        )
        self.assertEqual(skills_cli.profile_for({}, home), home / ".profile")

    def test_profile_line_is_written_once_and_uses_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bin_dir = home / ".local" / "bin"
            env = {"SHELL": "/bin/bash"}
            first = skills_cli.add_to_posix_path(bin_dir, env, home=home)
            self.assertIn("appended", first)
            profile = home / ".bashrc"
            body = profile.read_text(encoding="utf-8")
            self.assertIn('export PATH="$HOME/.local/bin:$PATH"', body)
            second = skills_cli.add_to_posix_path(bin_dir, env, home=home)
            self.assertIn("already configured", second)
            self.assertEqual(profile.read_text(encoding="utf-8"), body)

    def test_profile_dry_run_leaves_the_file_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = skills_cli.add_to_posix_path(
                home / ".local" / "bin", {}, dry_run=True, home=home
            )
            self.assertIn("would append", result)
            self.assertFalse((home / ".profile").exists())

    @unittest.skipUnless(os.name == "nt", "reads the Windows user environment")
    def test_windows_path_preview_names_the_directory(self) -> None:
        bin_dir = Path.home() / ".local" / "bin"
        self.assertIn(str(bin_dir), skills_cli.add_to_windows_path(bin_dir, dry_run=True))


class CliInvocation(unittest.TestCase):
    """Shared `skills` invocation harness. Holds no tests of its own.

    Split out from `CommandLineTests` so a new group of CLI tests can inherit
    the throwaway HOME without also inheriting -- and re-running -- every test
    that happens to live in that class.
    """

    def setUp(self) -> None:
        """Give every `skills` invocation a throwaway HOME.

        `skills install` delegates to install.py, which now records the root it
        touched in the machine-wide roots index under the user's home. Without
        this the suite wrote its temp project paths into the developer's real
        ~/.dm1681-skills-roots.json, one dead entry per run, until `--status
        --all` reported nothing but vanished roots. `skills` has no `--home`
        escape hatch the way install.py does, so HOME is the seam -- and doing
        it in the shared helper means a CLI test added later cannot forget.
        """
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)

    def run_cli(self, *arguments: str, expected: int = 0, cwd: Path = ROOT):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "HOME": self._home.name, "USERPROFILE": self._home.name},
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr),
        )
        return result


class CommandLineTests(CliInvocation):
    def test_list_matches_the_bundled_skills(self) -> None:
        result = self.run_cli("list")
        self.assertEqual(result.stdout.split(), BUNDLED)

    def test_where_prints_the_checkout(self) -> None:
        self.assertEqual(self.run_cli("where").stdout.strip(), str(ROOT))

    def test_install_writes_into_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_cli(
                "install", BUNDLED[0], "--project-dir", str(project), "--agent", "claude"
            )
            self.assertTrue((project / ".claude" / "skills" / BUNDLED[0] / "SKILL.md").is_file())
            self.assertFalse((project / ".agents").exists())

    def test_unknown_skill_is_rejected(self) -> None:
        result = self.run_cli("install", "not-a-skill", expected=2)
        self.assertIn("unknown skill", result.stderr)

    def test_names_and_all_are_mutually_exclusive(self) -> None:
        result = self.run_cli("install", BUNDLED[0], "--all", expected=2)
        self.assertIn("not both", result.stderr)

    def test_missing_project_directory_is_reported(self) -> None:
        result = self.run_cli(
            "install", BUNDLED[0], "--project-dir", str(ROOT / "no-such-dir"), expected=2
        )
        self.assertIn("does not exist", result.stderr)

    def test_no_names_without_a_terminal_explains_itself(self) -> None:
        result = self.run_cli("install", expected=2)
        self.assertIn("--all", result.stderr)


    def test_status_all_reports_the_whole_machine(self) -> None:
        """The design names `skills status --all` first, and it did not exist.

        `skills` is the PATH-callable command the docs point people at, so a
        machine-wide report reachable only from `install.py --status --all` is
        one most people never find. Installing into a project and then asking
        without standing in it is the whole point of the flag.
        """
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_cli(
                "install", BUNDLED[0], "--project-dir", str(project),
                "--agent", "claude",
            )
            result = self.run_cli("status", "--all", cwd=ROOT)
            self.assertIn(str((project / ".claude" / "skills").resolve()), result.stdout)

    def test_status_all_with_a_place_flag_is_rejected(self) -> None:
        for flag in (["--user"], ["--agent", "claude"]):
            with self.subTest(flag=flag):
                result = self.run_cli("status", "--all", *flag, expected=2)
                self.assertIn("--all", result.stdout + result.stderr)

    def test_bare_invocation_shows_help(self) -> None:
        self.assertIn("setup-path", self.run_cli(expected=2).stdout)


class UninstallCommandTests(CliInvocation):
    """`skills uninstall` must reach the same rules `install.py` enforces.

    The command exists at all because the uninstaller was otherwise reachable
    only as `python install.py --uninstall`: `skills` is the command the docs
    point people at, and a removal path most people never find is one they
    work around by deleting the directory by hand — which leaves the receipt
    claiming a skill that is gone.
    """

    def project(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_naming_nothing_refuses_rather_than_removing_everything(self) -> None:
        project = self.project()
        self.run_cli("install", BUNDLED[0], "--project-dir", str(project))
        result = self.run_cli("uninstall", "--project-dir", str(project), expected=2)
        self.assertIn("name at least one skill", result.stderr)
        # The refusal has to be a refusal, not a warning before the fact.
        self.assertTrue((project / ".claude" / "skills" / BUNDLED[0]).is_dir())

    def test_names_and_all_together_are_refused(self) -> None:
        project = self.project()
        result = self.run_cli(
            "uninstall", BUNDLED[0], "--all", "--project-dir", str(project), expected=2
        )
        self.assertIn("not both", result.stderr)

    def test_a_dry_run_names_the_backup_and_removes_nothing(self) -> None:
        project = self.project()
        self.run_cli("install", BUNDLED[0], "--project-dir", str(project))
        installed = project / ".claude" / "skills" / BUNDLED[0]
        result = self.run_cli(
            "uninstall", BUNDLED[0], "--project-dir", str(project), "--dry-run"
        )
        self.assertIn("would remove", result.stdout)
        self.assertIn(".skills-backups", result.stdout)
        self.assertTrue(installed.is_dir())

    def test_removal_backs_up_and_clears_the_receipt(self) -> None:
        project = self.project()
        self.run_cli("install", BUNDLED[0], "--project-dir", str(project))
        root = project / ".claude" / "skills"
        self.run_cli("uninstall", BUNDLED[0], "--project-dir", str(project))
        self.assertFalse((root / BUNDLED[0]).exists())
        self.assertTrue(root.is_dir(), "the root itself must survive its last skill")
        backups = list((project / ".claude" / ".skills-backups").rglob("SKILL.md"))
        self.assertTrue(backups, "a removal must stay recoverable")
        receipt = root / install.RECEIPT_NAME
        if receipt.is_file():
            recorded = json.loads(receipt.read_text(encoding="utf-8")).get("skills", [])
            self.assertNotIn(BUNDLED[0], recorded)

    def test_a_directory_this_collection_did_not_install_is_refused(self) -> None:
        project = self.project()
        root = project / ".claude" / "skills" / BUNDLED[0]
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("---\nname: x\n---\nnot ours\n", encoding="utf-8")
        result = self.run_cli(
            "uninstall", BUNDLED[0], "--project-dir", str(project), expected=2
        )
        self.assertIn("not installed by this collection", result.stderr)
        self.assertTrue((root / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()

