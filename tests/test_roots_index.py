"""The roots index and machine-wide status: every place an install touched,
and the shadowing/divergence only visible once more than one root is in view.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent import futures
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
SKILL = "wow-addon-dev"
OTHER = "viz-driven-dev"


class RootsIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_remembering_a_root_dedupes_on_a_second_install(self) -> None:
        root = self.home / "project" / ".claude" / "skills"
        install.remember_root(root, "project", "claude", self.home)
        install.remember_root(root, "project", "claude", self.home)
        recorded = install.known_roots(self.home)
        self.assertEqual(1, len(recorded))
        self.assertEqual(root.expanduser().resolve(), recorded[0].path)

    def test_the_index_file_holds_no_skill_names(self) -> None:
        """The anti-drift invariant: the index only says a root exists.

        Skill names belong to the receipt in that root. A second copy of them
        here would have to be kept true by every install and uninstall, and
        the first one that slipped would leave the index confidently naming
        skills that are not actually there.
        """
        root = self.home / ".claude" / "skills"
        install.remember_root(root, "user", "claude", self.home)
        raw = install.roots_index_path(self.home).read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertTrue(json.loads(raw))  # valid, non-empty JSON
        for entry in payload["roots"]:
            self.assertNotIn("skills", entry)
        # Belt and suspenders: no bundled skill name appears anywhere in the
        # raw text, so a future field addition can't reintroduce the drift
        # under a different key without this test noticing.
        for name in install.available_skills():
            self.assertNotIn(name, raw)

    def test_known_roots_tolerates_a_missing_file(self) -> None:
        self.assertEqual([], install.known_roots(self.home))

    def test_known_roots_tolerates_an_empty_file(self) -> None:
        install.roots_index_path(self.home).write_text("", encoding="utf-8")
        self.assertEqual([], install.known_roots(self.home))

    def test_known_roots_tolerates_a_truncated_file(self) -> None:
        install.roots_index_path(self.home).write_text(
            '{"schema_version": 1, "roots": [{"path": "/x", "scope"',
            encoding="utf-8",
        )
        self.assertEqual([], install.known_roots(self.home))

    def test_known_roots_tolerates_a_well_formed_but_wrong_shape_file(self) -> None:
        """Valid JSON that is not the expected shape must not raise either."""
        install.roots_index_path(self.home).write_text(
            json.dumps({"schema_version": 1, "roots": "not-a-list"}),
            encoding="utf-8",
        )
        self.assertEqual([], install.known_roots(self.home))

    def test_forget_root_removes_an_entry(self) -> None:
        root = self.home / ".claude" / "skills"
        install.remember_root(root, "user", "claude", self.home)
        self.assertEqual(1, len(install.known_roots(self.home)))
        install.forget_root(root, self.home)
        self.assertEqual([], install.known_roots(self.home))

    def test_forgetting_one_root_leaves_another_untouched(self) -> None:
        first = self.home / ".claude" / "skills"
        second = self.home / ".agents" / "skills"
        install.remember_root(first, "user", "claude", self.home)
        install.remember_root(second, "user", "universal", self.home)
        install.forget_root(first, self.home)
        recorded = install.known_roots(self.home)
        self.assertEqual(1, len(recorded))
        self.assertEqual(second.expanduser().resolve(), recorded[0].path)

    def test_dry_run_remember_root_writes_nothing(self) -> None:
        root = self.home / ".claude" / "skills"
        install.remember_root(root, "user", "claude", self.home, dry_run=True)
        self.assertFalse(install.roots_index_path(self.home).is_file())


class MachineStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_a_deleted_indexed_root_is_reported_vanished_without_raising(self) -> None:
        root = self.home / "gone" / ".claude" / "skills"
        install.remember_root(root, "project", "claude", self.home)
        # Nothing was ever written to disk at `root`, so the index names a
        # place that never existed -- the same situation a deleted project
        # leaves behind.
        report = install.machine_status(self.home)
        self.assertEqual((), report.reports)
        self.assertEqual(1, len(report.vanished))
        self.assertEqual(root.expanduser().resolve(), report.vanished[0].path)

    def test_a_shared_skill_installed_identically_in_two_roots_is_shadowed(self) -> None:
        first = self.home / "one" / ".claude" / "skills"
        second = self.home / "two" / ".claude" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, first / SKILL)
        shutil.copytree(install.SOURCE_ROOT / SKILL, second / SKILL)
        install.write_receipt(first, [SKILL], "copy", dry_run=False)
        install.write_receipt(second, [SKILL], "copy", dry_run=False)
        install.remember_root(first, "project", "claude", self.home)
        install.remember_root(second, "project", "claude", self.home)
        report = install.machine_status(self.home)
        shadow = next(item for item in report.shadowed if item.name == SKILL)
        self.assertEqual(install.SHADOWED, shadow.state)
        self.assertEqual([], report.actionable())

    def test_a_shared_skill_that_differs_between_roots_is_divergent(self) -> None:
        first = self.home / "one" / ".claude" / "skills"
        second = self.home / "two" / ".claude" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, first / SKILL)
        shutil.copytree(install.SOURCE_ROOT / SKILL, second / SKILL)
        entrypoint = second / SKILL / "SKILL.md"
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8"
        )
        install.write_receipt(first, [SKILL], "copy", dry_run=False)
        install.write_receipt(second, [SKILL], "copy", dry_run=False)
        install.remember_root(first, "project", "claude", self.home)
        install.remember_root(second, "project", "claude", self.home)
        report = install.machine_status(self.home)
        shadow = next(item for item in report.shadowed if item.name == SKILL)
        self.assertEqual(install.DIVERGENT, shadow.state)
        actionable = report.actionable()
        self.assertEqual(1, len(actionable))
        self.assertEqual(SKILL, actionable[0].name)

    def test_only_divergent_not_shadowed_reaches_the_actionable_exit_code(self) -> None:
        """`shadowed` is what a healthy multi-agent machine looks like.

        `--agent all` deliberately writes identical copies into `.agents` and
        `.claude`, so if `shadowed` alone tripped the actionable exit code,
        every machine-wide install would report work outstanding forever.
        """
        first = self.home / "one" / ".claude" / "skills"
        second = self.home / "two" / ".claude" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, first / SKILL)
        shutil.copytree(install.SOURCE_ROOT / SKILL, second / SKILL)
        install.write_receipt(first, [SKILL], "copy", dry_run=False)
        install.write_receipt(second, [SKILL], "copy", dry_run=False)
        install.remember_root(first, "project", "claude", self.home)
        install.remember_root(second, "project", "claude", self.home)
        machine = install.machine_status(self.home)
        _, pending = install.status_lines([], check_origin=False, machine=machine)
        self.assertFalse(pending)

    def test_divergence_does_reach_the_actionable_exit_code(self) -> None:
        first = self.home / "one" / ".claude" / "skills"
        second = self.home / "two" / ".claude" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, first / SKILL)
        shutil.copytree(install.SOURCE_ROOT / SKILL, second / SKILL)
        entrypoint = second / SKILL / "SKILL.md"
        entrypoint.write_text("replaced\n", encoding="utf-8")
        install.write_receipt(first, [SKILL], "copy", dry_run=False)
        install.write_receipt(second, [SKILL], "copy", dry_run=False)
        install.remember_root(first, "project", "claude", self.home)
        install.remember_root(second, "project", "claude", self.home)
        machine = install.machine_status(self.home)
        _, pending = install.status_lines([], check_origin=False, machine=machine)
        self.assertTrue(pending)


class StatusAllEndToEndTests(unittest.TestCase):
    """The CLI path, exercised through real installs so remember_root, write_receipt,
    and machine_status all have to agree for these to pass.
    """

    def run_installer(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_two_real_installs_are_both_indexed_and_reported_as_shadowed(self) -> None:
        first = self.home / "one" / "skills"
        second = self.home / "two" / "skills"
        self.run_installer(
            "--skill", SKILL, "--target", str(first), "--home", str(self.home),
            "--non-interactive",
        )
        self.run_installer(
            "--skill", SKILL, "--target", str(second), "--home", str(self.home),
            "--non-interactive",
        )
        result = self.run_installer(
            "--status", "--all", "--home", str(self.home),
        )
        self.assertIn(install.SHADOWED, result.stdout)
        self.assertIn(SKILL, result.stdout)

    def test_status_all_combined_with_scope_is_rejected(self) -> None:
        result = self.run_installer(
            "--status", "--all", "--scope", "project", "--home", str(self.home),
            expected=2,
        )
        self.assertIn("--all", result.stdout + result.stderr)

    def test_status_all_combined_with_target_is_rejected(self) -> None:
        result = self.run_installer(
            "--status", "--all", "--target", str(self.home / "x"),
            "--home", str(self.home),
            expected=2,
        )
        self.assertIn("--all", result.stdout + result.stderr)

    def test_all_without_status_is_rejected(self) -> None:
        result = self.run_installer(
            "--all", "--home", str(self.home), expected=2,
        )
        self.assertIn("--status", result.stdout + result.stderr)

    def test_the_index_follows_HOME_when_no_home_flag_is_passed(self) -> None:
        """An install with no `--home` must write the index under $HOME.

        This is the seam the rest of the suite is isolated by, and it is not
        theoretical: because a project-scope install records its root like any
        other, every test that ran the installer without redirecting the home
        appended its own temp path to the developer's real index -- which then
        listed those paths as vanished roots forever, since the temp
        directories were gone by the time anyone looked.

        `skills_cli` has no `--home` of its own, so $HOME is the only lever its
        tests have. Pinning it here means a change that made the index ignore
        $HOME would fail loudly instead of quietly resuming the pollution.
        """
        project = self.home / "project"
        project.mkdir()
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)

        environment = dict(os.environ)
        environment["HOME"] = str(elsewhere)
        environment["USERPROFILE"] = str(elsewhere)
        result = subprocess.run(
            [
                sys.executable, str(INSTALLER), "--non-interactive",
                "--scope", "project", "--project-dir", str(project),
                "--skill", SKILL,
            ],
            cwd=ROOT, text=True, capture_output=True, check=False, env=environment,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        index = install.roots_index_path(elsewhere)
        self.assertTrue(index.is_file(), "the install recorded no root under $HOME")
        recorded = {record.path for record in install.known_roots(elsewhere)}
        self.assertIn((project / ".agents" / "skills").resolve(), recorded)
        # And nothing leaked into the other temp home standing in for the
        # developer's real one.
        self.assertFalse(install.roots_index_path(self.home).exists())


class CacheFailureTests(unittest.TestCase):
    """A cache the docstring says you can delete must also be one you can fail to write.

    The index lives under $HOME; the install may not. A read-only or ephemeral
    home is ordinary in CI and in containers, and letting a failed index write
    escape turned an install whose files all landed into exit 1 -- and, in a
    multi-root run, skipped every root after the first.
    """

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.home = self.directory / "home"
        self.home.mkdir()

    def run_installer(self, *arguments: str, expected: int = 0):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    @unittest.skipIf(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        "needs POSIX permission bits that a non-root user cannot bypass",
    )
    def test_an_unwritable_home_does_not_fail_or_truncate_an_install(self) -> None:
        project = self.directory / "project"
        project.mkdir()
        os.chmod(self.home, 0o555)
        self.addCleanup(os.chmod, self.home, 0o755)

        result = self.run_installer(
            "--non-interactive", "--scope", "project",
            "--project-dir", str(project), "--skill", SKILL,
            "--home", str(self.home),
        )

        # Exit 0, and *both* roots reached: the failure used to escape the
        # per-root loop after the first one was written.
        self.assertTrue((project / ".agents" / "skills" / SKILL).is_dir())
        self.assertTrue((project / ".claude" / "skills" / SKILL).is_dir())
        self.assertIn("note:", result.stdout)

    def test_a_write_failure_in_remember_root_surfaces_as_OSError(self) -> None:
        """The guard in execute_install is what makes it harmless, not a swallow here.

        remember_root still raises, so a caller that genuinely needs the index
        written can tell. Turning the failure into silence at this level would
        hide it from the dashboard too.
        """
        blocked = self.directory / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(OSError):
            install.remember_root(
                self.directory / "root", "user", "claude", blocked
            )


class ConcurrentIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_concurrent_writers_all_land_in_the_index(self) -> None:
        """os.replace makes a reader safe; it does not make two writers safe.

        Each writer read the index, appended its own root, and wrote the whole
        file back, so a write built on a list that predated its neighbour's
        silently dropped a root -- which then never reappeared until someone
        installed into that root again, and nothing reported the gap. Parallel
        writers are ordinary here: agent sessions run concurrently and the
        SessionStart sync hook can fire during a manual install.

        The barrier is what makes this a reproducer rather than a coin flip:
        without it the writers finish in turn and the race never opens.
        """
        count = 12
        roots = [self.home / f"r{index}" for index in range(count)]
        start = threading.Barrier(count)

        def record(root: Path) -> None:
            start.wait()
            install.remember_root(root, "user", "claude", self.home)

        with futures.ThreadPoolExecutor(max_workers=count) as pool:
            for job in [pool.submit(record, root) for root in roots]:
                job.result()

        recorded = {record_.path for record_ in install.known_roots(self.home)}
        missing = [root for root in roots if root.resolve() not in recorded]
        self.assertEqual([], missing, "the index lost a root to a concurrent write")

    def test_no_scratch_file_is_left_beside_the_index(self) -> None:
        """A fixed `.tmp` name is shared by every writer on the machine.

        One process's os.replace would then move another's half-written file
        into place, and the loser's os.replace would raise FileNotFoundError
        at a point where its skills were already installed.
        """
        for index in range(3):
            install.remember_root(
                self.home / f"r{index}", "user", "claude", self.home
            )
        leftovers = sorted(
            path.name for path in self.home.iterdir()
            if path.name.startswith(install.ROOTS_INDEX_NAME)
            and path.name != install.ROOTS_INDEX_NAME
        )
        self.assertEqual([], leftovers)


class UnreadableRootTests(unittest.TestCase):
    """One protected directory costs one line, not the whole machine answer.

    Scoped `--status` asks about one place, so an unreadable directory there
    is the answer. `--all` asks about every place at once, and the first
    permission error used to raise past every healthy root beside it.
    """

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    @unittest.skipIf(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        "needs POSIX permission bits that a non-root user cannot bypass",
    )
    def test_an_unreadable_root_is_one_line_and_the_others_still_report(self) -> None:
        healthy = self.home / "one" / "skills"
        broken = self.home / "two" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, healthy / SKILL)
        shutil.copytree(install.SOURCE_ROOT / SKILL, broken / SKILL)
        install.write_receipt(healthy, [SKILL], "copy", dry_run=False)
        install.write_receipt(broken, [SKILL], "copy", dry_run=False)
        install.remember_root(healthy, "project", "claude", self.home)
        install.remember_root(broken, "project", "claude", self.home)
        os.chmod(broken / SKILL, 0o000)
        self.addCleanup(os.chmod, broken / SKILL, 0o755)

        machine = install.machine_status(self.home)
        lines, pending = install.status_lines([], False, machine)
        rendered = "\n".join(lines)

        self.assertEqual(1, len(machine.unreadable))
        self.assertEqual([healthy.resolve()], [
            report.root for report in machine.reports
        ])
        self.assertIn(str(healthy.resolve()), rendered)
        self.assertIn("could not be read", rendered)
        # Knowingly incomplete is not clean: a hook must not read exit 0 here.
        self.assertTrue(pending)


class AgentContradictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_status_all_with_agent_is_rejected_like_scope_and_target(self) -> None:
        """`--agent` narrows to a place through the same resolve_roots.

        Ignoring it answered "the Claude roots on this machine" with every
        root on the machine, and said nothing about having done so.
        """
        result = subprocess.run(
            [
                sys.executable, str(INSTALLER), "--status", "--all",
                "--agent", "claude", "--home", str(self.home),
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("--agent", result.stdout + result.stderr)


class PruningReachabilityTests(unittest.TestCase):
    """An index entry has to be clearable by some command, or it is forever.

    `uninstall_many` used to `continue` past the prune whenever the selection
    came out empty -- which is exactly what a vanished or hand-emptied root
    produces. So neither `--orphans` nor `--all-skills` could clear the entry
    for a root holding nothing, and `--status --all` listed it under "indexed
    roots that no longer exist" on every run with nothing able to act on it.
    That is the same "entry nothing can clear" loop AGENTS.md records for
    receipts, one level up.
    """

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.home = self.directory / "home"
        self.home.mkdir()

    def test_a_vanished_root_is_pruned_by_an_uninstall_that_removes_nothing(self) -> None:
        gone = self.directory / "deleted-project" / "skills"
        install.remember_root(gone, "project", "claude", self.home)
        self.assertEqual(1, len(install.known_roots(self.home)))

        install.uninstall_many(
            [gone], orphans=True, home=self.home, emit=lambda message: None
        )

        self.assertEqual([], install.known_roots(self.home))

    def test_a_root_emptied_by_hand_is_pruned_too(self) -> None:
        root = self.directory / "project" / "skills"
        root.mkdir(parents=True)
        install.remember_root(root, "project", "claude", self.home)
        self.assertFalse(install.root_holds_collection(root))

        install.uninstall_many(
            [root], all_skills=True, home=self.home, emit=lambda message: None
        )

        self.assertEqual([], install.known_roots(self.home))
        # The directory itself is left exactly as it was: forgetting a root is
        # bookkeeping, not a removal.
        self.assertTrue(root.is_dir())

    def test_a_root_that_still_holds_skills_keeps_its_entry(self) -> None:
        root = self.directory / "project" / "skills"
        shutil.copytree(install.SOURCE_ROOT / SKILL, root / SKILL)
        install.write_receipt(root, [SKILL], "copy", dry_run=False)
        install.remember_root(root, "project", "claude", self.home)

        install.uninstall_many(
            [root], orphans=True, home=self.home, emit=lambda message: None
        )

        self.assertEqual(1, len(install.known_roots(self.home)))


if __name__ == "__main__":
    unittest.main()
