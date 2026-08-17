from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
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

    def test_uninstall_argv_builds_the_expected_installer_arguments(self) -> None:
        argv = skills_cli.uninstall_argv(
            ["wow-addon-dev"],
            "user",
            Path("/repo"),
            ["claude"],
            global_instructions=True,
            shims=True,
            external=["graphify"],
            unrecorded=True,
            restore=False,
            backup=False,
            dry_run=True,
        )
        self.assertEqual(
            argv,
            [
                "--non-interactive",
                "--uninstall",
                "--scope",
                "user",
                "--project-dir",
                str(Path("/repo")),
                "--agent",
                "claude",
                "--skill",
                "wow-addon-dev",
                "--global-instructions",
                "--setup-path",
                "--graphify",
                "--unrecorded",
                "--no-restore",
                "--no-backup",
                "--dry-run",
            ],
        )

    def test_uninstall_argv_passes_a_named_backup_through(self) -> None:
        argv = skills_cli.uninstall_argv(
            ["a"], "project", Path("/repo"), [], restore_from=Path("/b/a-2020")
        )
        self.assertEqual(argv[argv.index("--restore-from") + 1], str(Path("/b/a-2020")))
        self.assertNotIn("--all", argv)


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

    @unittest.skipUnless(os.name == "nt", "reads the Windows user environment")
    def test_remove_from_windows_path(self) -> None:
        bin_dir = Path.home() / ".local" / "bin"
        message = skills_cli.remove_from_windows_path(bin_dir, dry_run=True)
        self.assertIn(str(bin_dir), message)

    def test_remove_from_posix_path_drops_the_marked_block_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bin_dir = home / ".local" / "bin"
            env = {"SHELL": "/bin/bash"}
            profile = home / ".bashrc"
            profile.write_text("# mine\nexport EDITOR=vi\n", encoding="utf-8")
            skills_cli.add_to_posix_path(bin_dir, env, home=home)
            removed = skills_cli.remove_from_posix_path(bin_dir, env, home=home)
            self.assertIn("removed the PATH line", removed)
            body = profile.read_text(encoding="utf-8")
            self.assertNotIn(skills_cli.PROFILE_MARKER, body)
            self.assertIn("export EDITOR=vi", body)
            # The user's file is theirs: it is copied aside before it is edited,
            # and inside the home rather than beside it.
            backups = list((home / ".skills-backups" / "profile").glob(".bashrc-*"))
            self.assertEqual(1, len(backups))
            self.assertIn(
                skills_cli.PROFILE_MARKER, backups[0].read_text(encoding="utf-8")
            )
            self.assertIn(
                "no PATH line from this collection",
                skills_cli.remove_from_posix_path(bin_dir, env, home=home),
            )

    def test_remove_shims_leaves_a_foreign_shim_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            for path, _content, _newline, _executable in skills_cli.shims(ROOT, bin_dir):
                path.write_text(
                    "#!/usr/bin/env sh\n# Generated by `skills setup-path` "
                    "from /somewhere/else\n",
                    encoding="utf-8",
                )
            results = skills_cli.remove_shims(ROOT, bin_dir)
            self.assertTrue(all(status == "left" for _path, status in results))
            self.assertTrue(all(path.is_file() for path, _status in results))

    def test_remove_shims_takes_back_what_this_checkout_wrote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            skills_cli.write_shims(ROOT, bin_dir)
            preview = skills_cli.remove_shims(ROOT, bin_dir, dry_run=True)
            self.assertTrue(all(status == "would remove" for _p, status in preview))
            self.assertTrue(all(path.is_file() for path, _status in preview))
            results = skills_cli.remove_shims(ROOT, bin_dir)
            self.assertTrue(all(status == "removed" for _p, status in results))
            self.assertTrue(all(not path.exists() for path, _status in results))
            again = skills_cli.remove_shims(ROOT, bin_dir)
            self.assertTrue(all(status == "absent" for _p, status in again))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments: str, expected: int = 0, cwd: Path = ROOT):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr),
        )
        return result

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

    def test_bare_invocation_shows_help(self) -> None:
        self.assertIn("setup-path", self.run_cli(expected=2).stdout)

    def test_uninstall_removes_only_the_named_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            root = project / ".claude" / "skills"
            for name in BUNDLED[:2]:
                self.run_cli(
                    "install", name, "--project-dir", str(project), "--agent", "claude"
                )
            self.run_cli(
                "uninstall", BUNDLED[0], "--project-dir", str(project),
                "--agent", "claude",
            )
            self.assertFalse((root / BUNDLED[0]).exists())
            self.assertTrue((root / BUNDLED[1] / "SKILL.md").is_file())

    def test_status_and_uninstall_work_without_textual(self) -> None:
        """Neither command may reach for the dashboard: the whole point of the
        scripted path is that it needs no dependencies."""
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_cli(
                "install", BUNDLED[0], "--project-dir", str(project), "--agent", "claude"
            )
            for arguments in (
                ["status", "--project-dir", str(project), "--home", str(project)],
                ["uninstall", BUNDLED[0], "--project-dir", str(project),
                 "--agent", "claude"],
            ):
                code = (
                    "import sys; sys.modules['textual'] = None; "
                    "sys.path.insert(0, %r);\n"
                    "import skills_cli\n"
                    "code = skills_cli.main(%r)\n"
                    "print('tui-imported', 'skills_tui' in sys.modules)\n"
                    "raise SystemExit(code)\n" % (str(ROOT), arguments)
                )
                result = subprocess.run(
                    [sys.executable, "-c", code], cwd=str(ROOT), text=True,
                    capture_output=True, check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("tui-imported False", result.stdout)

    def test_uninstall_with_no_names_and_no_tty_explains_the_options(self) -> None:
        result = self.run_cli("uninstall", expected=2)
        for hint in ("--all", "--global-instructions", "--shims", "--external",
                     "skills status", "skills manage"):
            self.assertIn(hint, result.stderr)

    def test_manage_without_a_terminal_points_at_status(self) -> None:
        result = self.run_cli("manage", expected=2)
        self.assertIn("skills status", result.stderr)

    def test_status_lists_what_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_cli(
                "install", BUNDLED[0], "--project-dir", str(project), "--agent", "claude"
            )
            result = self.run_cli(
                "status", "--project-dir", str(project), "--home", str(project)
            )
            self.assertIn(BUNDLED[0], result.stdout)
            self.assertIn("skill", result.stdout)

    def edit_installed(self, project: Path) -> Path:
        """Install one skill into a project and edit it, so the doctor has work."""
        self.run_cli(
            "install", BUNDLED[0], "--project-dir", str(project), "--agent", "claude"
        )
        entrypoint = project / ".claude" / "skills" / BUNDLED[0] / "SKILL.md"
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nEDITED-BY-THE-TEST\n",
            encoding="utf-8",
        )
        return entrypoint

    def test_doctor_lists_findings_and_exits_three(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.edit_installed(project)
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                expected=3,
            )
            self.assertIn("diverged-from-source", result.stdout)
            self.assertIn(BUNDLED[0], result.stdout)

    def test_doctor_exit_zero_suppresses_the_finding_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.edit_installed(project)
            self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                "--exit-zero",
            )

    def test_doctor_json_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.edit_installed(project)
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                "--json", expected=3,
            )
            report = json.loads(result.stdout)
            self.assertEqual(
                ["diverged-from-source"],
                [finding["kind"] for finding in report["findings"]],
            )

    def test_doctor_fix_reinstalls_and_leaves_nothing_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            entrypoint = self.edit_installed(project)
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project), "--fix"
            )
            self.assertIn("nothing inconsistent is left", result.stdout)
            self.assertNotIn("EDITED-BY-THE-TEST", entrypoint.read_text(encoding="utf-8"))

    def test_doctor_fix_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            entrypoint = self.edit_installed(project)
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                "--fix", "--dry-run", expected=3,
            )
            self.assertIn("would", result.stdout)
            self.assertIn("EDITED-BY-THE-TEST", entrypoint.read_text(encoding="utf-8"))

    def test_doctor_fix_rejects_an_unknown_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.edit_installed(project)
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                "--fix", "not-a-kind", expected=2,
            )
            self.assertIn("unknown finding kind", result.stderr)

    def test_doctor_prune_forgets_a_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            gone = project / "gone" / ".claude" / "skills"
            gone.mkdir(parents=True)
            install.record_root(project, gone)
            install.remove_path(project / "gone")
            result = self.run_cli(
                "doctor", "--project-dir", str(project), "--home", str(project),
                "--prune",
            )
            self.assertIn("forgot", result.stdout)
            self.assertEqual([], install.known_roots(project))
            self.assertNotIn(str(gone), install.registry_path(project).read_text())

    def test_doctor_works_without_textual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            code = (
                "import sys; sys.modules['textual'] = None; "
                "sys.path.insert(0, %r);\n"
                "import skills_cli\n"
                "code = skills_cli.main(%r)\n"
                "print('tui-imported', 'skills_tui' in sys.modules)\n"
                "raise SystemExit(code)\n"
                % (
                    str(ROOT),
                    ["doctor", "--project-dir", str(project), "--home", str(project)],
                )
            )
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=str(ROOT), text=True,
                capture_output=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("tui-imported False", result.stdout)


if __name__ == "__main__":
    unittest.main()
