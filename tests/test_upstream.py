"""Per-skill upstream freshness: `install.skills_behind_origin`.

Builds real temporary git repositories (a bare "origin" plus working clones)
and shells out to the real `git` binary, rather than mocking, so these tests
exercise the actual invocations `skills_behind_origin` makes.
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_TERMINAL_PROMPT": "0",
}


class UpstreamHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, **GIT_ENV},
        )

    def _seed_repo(self) -> tuple[Path, Path]:
        """Bare `origin.git` plus a working clone with two committed skills.

        Both skills start identical on both sides of the remote, so a fresh
        clone is trivially "current" until something advances the bare repo.
        """
        bare = self.tmp / "origin.git"
        self._git(self.tmp, "init", "--bare", "-b", "main", str(bare))
        work = self.tmp / "work"
        self._git(self.tmp, "clone", str(bare), str(work))
        for name in ("alpha", "beta"):
            skill_dir = work / "skills" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        self._git(work, "add", ".")
        self._git(work, "commit", "-m", "seed alpha and beta")
        self._git(work, "push", "-u", "origin", "main")
        return work, bare

    def _advance_alpha(self, bare: Path) -> None:
        """Push one more commit to origin that touches only `skills/alpha`."""
        advancer = self.tmp / "advancer"
        self._git(self.tmp, "clone", str(bare), str(advancer))
        (advancer / "skills" / "alpha" / "SKILL.md").write_text(
            "# alpha v2\n", encoding="utf-8"
        )
        self._git(advancer, "commit", "-am", "advance alpha")
        self._git(advancer, "push", "origin", "main")

    # -- not a git checkout at all -----------------------------------------

    def test_a_non_git_directory_is_unknown_for_every_skill(self) -> None:
        directory = self.tmp / "plain"
        directory.mkdir()
        freshness = install.skills_behind_origin(["alpha", "beta"], repo=directory)
        self.assertEqual(install.ORIGIN_UNKNOWN, freshness.state)
        self.assertEqual({}, freshness.behind)

    # -- detached HEAD -------------------------------------------------------

    def test_a_detached_head_is_unknown(self) -> None:
        work, _bare = self._seed_repo()
        sha = self._git(work, "rev-parse", "HEAD").stdout.strip()
        self._git(work, "checkout", sha)
        freshness = install.skills_behind_origin(["alpha", "beta"], repo=work)
        self.assertEqual(install.ORIGIN_UNKNOWN, freshness.state)
        self.assertEqual({}, freshness.behind)

    # -- unreachable origin ---------------------------------------------------

    def test_an_unreachable_origin_is_unknown(self) -> None:
        work, _bare = self._seed_repo()
        bogus = self.tmp / "does-not-exist.git"
        self._git(work, "remote", "set-url", "origin", str(bogus))
        freshness = install.skills_behind_origin(
            ["alpha", "beta"], repo=work, fetch=True
        )
        self.assertEqual(install.ORIGIN_UNKNOWN, freshness.state)
        self.assertEqual({}, freshness.behind)

    # -- unknown vs. zero-commits-behind must never be conflated ------------

    def test_unknown_is_distinguishable_from_zero_commits_behind(self) -> None:
        """Absence from `behind` means unknown; presence with 0 means checked
        and current. Conflating the two is the specific wrong claim the
        design forbids -- a dashboard must not paint "up to date" over a
        machine that never reached the remote.
        """
        work, _bare = self._seed_repo()
        self._git(work, "fetch", "--quiet", "origin")

        checked = install.skills_behind_origin(["beta"], repo=work, fetch=False)
        self.assertEqual(install.ORIGIN_CURRENT, checked.state)
        self.assertEqual(0, checked.behind["beta"])

        bogus = self.tmp / "does-not-exist.git"
        self._git(work, "remote", "set-url", "origin", str(bogus))
        unknown = install.skills_behind_origin(["beta"], repo=work, fetch=True)
        self.assertEqual(install.ORIGIN_UNKNOWN, unknown.state)
        self.assertNotIn("beta", unknown.behind)

        self.assertNotEqual(checked.state, unknown.state)
        self.assertNotEqual(checked.behind, unknown.behind)
        self.assertNotEqual(unknown.behind.get("beta"), checked.behind["beta"])

    # -- a skill touched upstream reports a positive count -------------------

    def test_a_skill_touched_upstream_reports_a_positive_count(self) -> None:
        work, bare = self._seed_repo()
        self._advance_alpha(bare)
        self._git(work, "fetch", "--quiet", "origin")

        freshness = install.skills_behind_origin(
            ["alpha", "beta"], repo=work, fetch=False
        )
        self.assertEqual(install.ORIGIN_BEHIND, freshness.state)
        self.assertEqual(1, freshness.behind["alpha"])
        self.assertEqual(0, freshness.behind["beta"])

    # -- a skill with no new commits reports up to date -----------------------

    def test_a_skill_with_no_new_commits_reports_up_to_date(self) -> None:
        work, bare = self._seed_repo()
        self._advance_alpha(bare)
        self._git(work, "fetch", "--quiet", "origin")

        freshness = install.skills_behind_origin(["beta"], repo=work, fetch=False)
        self.assertEqual(install.ORIGIN_CURRENT, freshness.state)
        self.assertEqual(0, freshness.behind["beta"])

    # -- fetch can be disabled so the check never touches the network --------

    def test_fetch_false_never_touches_the_network(self) -> None:
        """With `fetch=False`, a stale/unreachable `origin` remote must not
        stop the answer -- the function must rely only on refs already on
        disk (from the real fetch this test does itself, locally) and never
        attempt another fetch.
        """
        work, bare = self._seed_repo()
        self._advance_alpha(bare)
        self._git(work, "fetch", "--quiet", "origin")  # only real fetch: local disk

        bogus = self.tmp / "does-not-exist.git"
        self._git(work, "remote", "set-url", "origin", str(bogus))

        freshness = install.skills_behind_origin(
            ["alpha", "beta"], repo=work, fetch=False
        )
        self.assertEqual(install.ORIGIN_BEHIND, freshness.state)
        self.assertEqual(1, freshness.behind["alpha"])
        self.assertEqual(0, freshness.behind["beta"])


class StatusGitDeadlineTests(unittest.TestCase):
    """A silent remote must fail, not wait.

    `STATUS_GIT_ENV` stops git *asking* for something nobody can answer, but a
    host that blackholes packets -- a dropped VPN, a captive portal -- neither
    prompts nor errors. Without a wall-clock bound that fetch runs on a worker
    thread the interpreter joins at exit, so the dashboard spins "checking
    origin..." forever and the process outlives the quit key.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _hanging_git(self) -> Path:
        """A directory holding a `git` that never returns, for $PATH."""
        binary = self.tmp / "bin"
        binary.mkdir()
        fake = binary / "git"
        fake.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
        fake.chmod(0o755)
        return binary

    def test_the_runner_carries_a_deadline_by_default(self) -> None:
        """Pinned as the default, not merely passed at one call site: an
        unbounded call is the failure, and a default is what stops the next
        caller from reintroducing one."""
        default = inspect.signature(install.status_git).parameters["timeout"].default
        self.assertEqual(default, install.STATUS_GIT_TIMEOUT)
        self.assertIsNotNone(install.STATUS_GIT_TIMEOUT)
        self.assertGreater(install.STATUS_GIT_TIMEOUT, 0)

    def test_a_git_that_never_returns_is_cut_off_and_reads_as_unknown(self) -> None:
        binary = self._hanging_git()
        environment = dict(os.environ, PATH=f"{binary}{os.pathsep}{os.environ['PATH']}")
        started = time.monotonic()
        with unittest.mock.patch.dict(os.environ, environment, clear=True):
            answer = install.status_git(self.tmp, "fetch", "--quiet", "origin", timeout=0.5)
        elapsed = time.monotonic() - started
        self.assertIsNone(answer)
        self.assertLess(elapsed, 30)


if __name__ == "__main__":
    unittest.main()
