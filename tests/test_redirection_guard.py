"""Links that cannot be followed: Windows Redirection Guard under OpenSSH.

OpenSSH for Windows starts every session under Redirection Guard, where
following a symlink or junction a non-administrator created raises WinError
448. Reading the link itself (`lstat`, `readlink`) still works. The dashboard
crashed on its first render over SSH because `exists()` follows the link.
The guard cannot be switched on from a test, so `following_refused` stands in
for it: every call that follows a link raises, and every call that reads one
does not.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

SKILL = "wow-addon-dev"


def _guarded(error_path: os.PathLike) -> OSError:
    error = OSError(errno.EACCES, "untrusted mount point", str(error_path))
    error.winerror = 448
    return error


@contextlib.contextmanager
def following_refused(link: Path):
    real_stat = os.stat
    real_open = io.open
    real_resolve = pathlib.Path.resolve
    guarded = os.path.normcase(str(link))

    def through(path) -> bool:
        candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
        return candidate == guarded or candidate.startswith(guarded + os.sep)

    def stat(path, *args, follow_symlinks=True, **kwargs):
        if through(path) and (follow_symlinks or os.path.normcase(os.fspath(path)) != guarded):
            raise _guarded(path)
        return real_stat(path, *args, follow_symlinks=follow_symlinks, **kwargs)

    def open_(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and through(path):
            raise _guarded(path)
        return real_open(path, *args, **kwargs)

    def resolve(self, *args, **kwargs):
        if through(self):
            raise _guarded(self)
        return real_resolve(self, *args, **kwargs)

    with mock.patch("os.stat", stat), mock.patch("io.open", open_), mock.patch.object(
        pathlib.Path, "resolve", resolve
    ):
        yield


class RedirectionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"
        self.root.mkdir()
        self.link = self.root / SKILL
        self.link.symlink_to((install.SOURCE_ROOT / SKILL).resolve(), target_is_directory=True)

    def test_the_stand_in_refuses_what_the_guard_refuses(self) -> None:
        with following_refused(self.link):
            with self.assertRaises(OSError):
                self.link.exists()

    def test_a_link_that_cannot_be_followed_is_still_occupied(self) -> None:
        with following_refused(self.link):
            self.assertTrue(install.occupied(self.link))

    def test_a_link_to_the_checkout_still_compares_equal(self) -> None:
        with following_refused(self.link):
            self.assertTrue(install.trees_equal(self.link, install.SOURCE_ROOT / SKILL))
            self.assertFalse(install.trees_equal(self.link, install.SOURCE_ROOT / "viz-driven-dev"))

    def test_a_file_inside_the_link_is_read_at_its_target(self) -> None:
        with following_refused(self.link):
            with self.assertRaises(OSError):
                (self.link / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(
                install.skill_version(install.SOURCE_ROOT / SKILL),
                install.skill_version(self.link),
            )
            self.assertEqual(
                install.skill_is_model_hidden(install.SOURCE_ROOT / SKILL),
                install.skill_is_model_hidden(self.link),
            )

    def test_listing_hidden_skills_reads_through_the_link(self) -> None:
        with following_refused(self.link):
            install.hidden_skills(self.root)

    def test_reinstalling_a_current_link_leaves_it_unchanged(self) -> None:
        with following_refused(self.link):
            message = install.install_one(
                install.SOURCE_ROOT / SKILL, self.root, "link", force=False, dry_run=True
            )
        self.assertTrue(message.startswith("unchanged"), message)


if __name__ == "__main__":
    unittest.main()
