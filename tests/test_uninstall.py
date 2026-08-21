"""uninstall_one / uninstall_many: removal, backups, and receipt bookkeeping."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

SKILL = "wow-addon-dev"
OTHER = "viz-driven-dev"

# uninstall_many emits as it goes -- see its docstring -- so a test that only
# reads the returned list has to say so rather than spraying the suite output.
SILENT = lambda message: None  # noqa: E731


def _receipt(root: Path, skills: list[str], mode: str = "copy") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / install.RECEIPT_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "collection": "dm1681/skills",
                "version": install.VERSION,
                "skills": skills,
                "mode": mode,
                "installed_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


class UninstallOneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"

    def install(self, name: str = SKILL) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(install.SOURCE_ROOT / name, self.root / name)

    def test_removing_an_installed_skill_backs_it_up_and_clears_the_destination(self) -> None:
        self.install()
        _receipt(self.root, [SKILL])
        message = install.uninstall_one(SKILL, self.root)
        self.assertIn("removed", message)
        self.assertFalse((self.root / SKILL).exists())
        backups = list((self.root.parent / ".skills-backups" / self.root.name).glob(f"{SKILL}-*"))
        self.assertEqual(1, len(backups))
        # The backup actually holds the removed skill's content, not an empty
        # marker directory -- a backup nobody could restore from is as bad as
        # no backup at all.
        self.assertTrue((backups[0] / "SKILL.md").is_file())

    def test_the_receipt_loses_exactly_the_removed_name_and_keeps_the_rest(self) -> None:
        self.install(SKILL)
        self.install(OTHER)
        _receipt(self.root, [SKILL, OTHER])
        install.uninstall_one(SKILL, self.root)
        receipt = json.loads((self.root / install.RECEIPT_NAME).read_text())
        self.assertEqual([OTHER], receipt["skills"])

    def test_a_receipt_reaching_zero_skills_is_deleted_not_left_empty(self) -> None:
        self.install()
        _receipt(self.root, [SKILL])
        install.uninstall_one(SKILL, self.root)
        # An empty receipt would still claim this collection owns the root;
        # only deleting it lets a later report call the root clean.
        self.assertFalse((self.root / install.RECEIPT_NAME).exists())

    def test_the_root_directory_itself_is_never_removed(self) -> None:
        self.install()
        _receipt(self.root, [SKILL])
        install.uninstall_one(SKILL, self.root)
        self.assertTrue(self.root.is_dir())

    def test_uninstalling_an_absent_skill_succeeds_without_error(self) -> None:
        self.root.mkdir(parents=True)
        message = install.uninstall_one(SKILL, self.root)
        self.assertIn("absent", message)
        self.assertFalse((self.root / SKILL).exists())

    def test_absent_skill_still_recorded_in_the_receipt_is_cleared_from_it(self) -> None:
        # The disk already lost the skill (hand-deleted, a failed previous
        # uninstall) but the receipt still names it. Nothing else can ever
        # clear that entry, so uninstall_one must, even though there is
        # nothing on disk to remove.
        self.root.mkdir(parents=True)
        _receipt(self.root, [SKILL, OTHER])
        message = install.uninstall_one(SKILL, self.root)
        self.assertIn("absent", message)
        receipt = json.loads((self.root / install.RECEIPT_NAME).read_text())
        self.assertEqual([OTHER], receipt["skills"])

    def test_a_destination_unrecorded_and_unequal_to_the_checkout_is_refused(self) -> None:
        # Nothing in the receipt names this skill, and the on-disk content
        # does not match skills/<name> -- some other tool put it there, and
        # removing it without permission is exactly the mistake install_one's
        # own overwrite refusal exists to avoid on the install side.
        self.root.mkdir(parents=True)
        foreign = self.root / SKILL
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("not the real skill", encoding="utf-8")
        with self.assertRaises(install.InstallError):
            install.uninstall_one(SKILL, self.root)
        # Disk untouched: the refusal is not just an exception message, the
        # foreign content has to still be exactly there.
        self.assertEqual("not the real skill", (foreign / "SKILL.md").read_text())

    def test_the_same_unrecorded_foreign_destination_is_removed_with_force(self) -> None:
        self.root.mkdir(parents=True)
        foreign = self.root / SKILL
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("not the real skill", encoding="utf-8")
        message = install.uninstall_one(SKILL, self.root, force=True)
        self.assertIn("removed", message)
        self.assertFalse(foreign.exists())

    def test_a_symlink_install_is_removed_correctly(self) -> None:
        self.root.mkdir(parents=True)
        link = self.root / SKILL
        link.symlink_to((install.SOURCE_ROOT / SKILL).resolve(), target_is_directory=True)
        _receipt(self.root, [SKILL], mode="link")
        message = install.uninstall_one(SKILL, self.root)
        self.assertIn("removed", message)
        self.assertFalse(link.exists())
        self.assertFalse(link.is_symlink())
        backups = list((self.root.parent / ".skills-backups" / self.root.name).glob(f"{SKILL}-*"))
        self.assertEqual(1, len(backups))
        self.assertTrue(backups[0].is_symlink())

    def test_a_broken_symlink_install_is_removed_correctly(self) -> None:
        # exists() is False for a dangling symlink; uninstall_one has to test
        # is_symlink() too, or a broken link is silently left behind and the
        # receipt entry naming it never clears.
        self.root.mkdir(parents=True)
        link = self.root / SKILL
        link.symlink_to(self.directory / "nowhere", target_is_directory=True)
        self.assertFalse(link.exists())
        self.assertTrue(link.is_symlink())
        _receipt(self.root, [SKILL], mode="link")
        message = install.uninstall_one(SKILL, self.root)
        self.assertIn("removed", message)
        self.assertFalse(link.is_symlink())
        self.assertFalse((self.root / install.RECEIPT_NAME).exists())

    def test_dry_run_writes_nothing_at_all(self) -> None:
        self.install()
        _receipt(self.root, [SKILL])
        before = (self.root / install.RECEIPT_NAME).read_text()
        message = install.uninstall_one(SKILL, self.root, dry_run=True)
        self.assertIn("would remove", message)
        self.assertTrue((self.root / SKILL).is_dir())
        self.assertTrue((self.root / SKILL / "SKILL.md").is_file())
        self.assertEqual(before, (self.root / install.RECEIPT_NAME).read_text())
        # dry_run must not even create the backups directory.
        self.assertFalse((self.root.parent / ".skills-backups").exists())

    def test_dry_run_on_an_absent_recorded_skill_writes_nothing(self) -> None:
        self.root.mkdir(parents=True)
        _receipt(self.root, [SKILL])
        before = (self.root / install.RECEIPT_NAME).read_text()
        message = install.uninstall_one(SKILL, self.root, dry_run=True)
        self.assertIn("would clear it from the records", message)
        self.assertEqual(before, (self.root / install.RECEIPT_NAME).read_text())


class OrphansTests(unittest.TestCase):
    """--orphans removes exactly the receipt entries whose skill left the collection."""

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"
        self.root.mkdir(parents=True)

    def test_orphans_removes_only_names_absent_from_the_collection(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        shutil.copytree(install.SOURCE_ROOT / OTHER, self.root / OTHER)
        retired = self.root / "retired-skill"
        retired.mkdir()
        (retired / "SKILL.md").write_text(
            "---\nname: retired-skill\ndescription: gone\n---\nbody\n", encoding="utf-8"
        )
        _receipt(self.root, [SKILL, OTHER, "retired-skill"])

        removed = install.uninstall_many([self.root], orphans=True, emit=SILENT)

        self.assertTrue(any("retired-skill" in message for message in removed))
        self.assertFalse((self.root / "retired-skill").exists())
        # The two still-bundled skills are untouched on disk and in the receipt.
        self.assertTrue((self.root / SKILL).is_dir())
        self.assertTrue((self.root / OTHER).is_dir())
        receipt = json.loads((self.root / install.RECEIPT_NAME).read_text())
        self.assertEqual(sorted([SKILL, OTHER]), sorted(receipt["skills"]))

    def test_orphans_leaves_a_root_with_no_orphans_completely_alone(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        _receipt(self.root, [SKILL])
        removed = install.uninstall_many([self.root], orphans=True, emit=SILENT)
        self.assertEqual([f"nothing to remove  {self.root}"], removed)
        self.assertTrue((self.root / SKILL).is_dir())

    def test_orphans_agrees_with_root_status_about_which_entries_qualify(self) -> None:
        # uninstall_names reads its answer from root_status rather than
        # re-deriving it; a divergence here means the report and the command
        # disagree about what "orphan" means.
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        stale = self.root / "long-gone"
        stale.mkdir()
        (stale / "SKILL.md").write_text(
            "---\nname: long-gone\ndescription: gone\n---\nbody\n", encoding="utf-8"
        )
        _receipt(self.root, [SKILL, "long-gone"])

        expected = sorted(
            item.name for item in install.root_status(self.root).skills if item.state == install.ORPHAN
        )
        self.assertEqual(["long-gone"], expected)
        install.uninstall_many([self.root], orphans=True, emit=SILENT)
        receipt = json.loads((self.root / install.RECEIPT_NAME).read_text())
        self.assertEqual([SKILL], receipt["skills"])


class SkillNameGuardTests(unittest.TestCase):
    """`root / name` is a delete target, so `name` has to be a skill name.

    Every case here was reachable end to end before the guard: an unset shell
    variable expanding to `--skill ""` moved a whole shared skills root away
    and exited 0, and `--skill ../notes` relocated a sibling directory to a
    path the documented backup layout does not describe.
    """

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"
        self.root.mkdir(parents=True)

    def test_an_empty_name_is_refused_before_it_can_mean_the_root(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        with self.assertRaises(install.InstallError) as caught:
            install.uninstall_one("", self.root)
        self.assertIn("not a skill name", str(caught.exception))
        self.assertTrue(self.root.is_dir())
        self.assertTrue((self.root / SKILL).is_dir())

    def test_force_does_not_unlock_a_traversing_name(self) -> None:
        """--force means "not ours", never "not a skill directory here".

        The refusal message a caller sees invites `--force`, and automation
        passes it as a matter of course, so a guard that `--force` bypassed
        would be no guard at all.
        """
        sibling = self.directory / "notes"
        sibling.mkdir()
        (sibling / "thing.txt").write_text("keep me", encoding="utf-8")
        with self.assertRaises(install.InstallError):
            install.uninstall_one("../notes", self.root, force=True)
        self.assertTrue((sibling / "thing.txt").is_file())

    def test_dot_and_dot_dot_and_separators_are_all_refused(self) -> None:
        for name in ("", ".", "..", "../x", "a/b", "/abs"):
            with self.subTest(name=name):
                with self.assertRaises(install.InstallError):
                    install.uninstall_one(name, self.root, force=True)

    def test_a_corrupt_receipt_cannot_drive_a_removal_outside_the_root(self) -> None:
        """Names reach uninstall_one from receipt JSON too, which nothing shapes."""
        sibling = self.directory / "notes"
        sibling.mkdir()
        _receipt(self.root, ["../notes"])
        with self.assertRaises(install.InstallError):
            install.uninstall_many([self.root], all_skills=True, emit=SILENT)
        self.assertTrue(sibling.is_dir())


class IncrementalReportTests(unittest.TestCase):
    """A removal that fails partway still has to say what it already removed.

    The backup path is in the message and is the only way back, so collecting
    the lines and returning them at the end meant a refusal on the second name
    threw away the record of the first directory being moved.
    """

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"
        self.root.mkdir(parents=True)

    def test_a_refusal_on_the_second_name_still_reports_the_first_removal(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        stranger = self.root / "zz-other"
        stranger.mkdir()
        (stranger / "SKILL.md").write_text(
            "---\nname: zz-other\ndescription: someone else's\n---\nbody\n",
            encoding="utf-8",
        )
        _receipt(self.root, [SKILL])

        said: list[str] = []
        with self.assertRaises(install.InstallError):
            install.uninstall_many(
                [self.root], [SKILL, "zz-other"], emit=said.append
            )

        self.assertTrue(any("removed" in line and SKILL in line for line in said))
        self.assertTrue(any("backup:" in line for line in said))
        self.assertFalse((self.root / SKILL).exists())
        self.assertTrue(stranger.is_dir())


if __name__ == "__main__":
    unittest.main()
