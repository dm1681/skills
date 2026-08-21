"""Where the skills-manager work and the external-collection work meet.

Both landed on one branch, built concurrently, without either knowing what the
other added. Each of these tests pins one place where the newer of the two
records — `.skills-external.json`, and the visibility choices keyed beside it —
has to be visible to code that was written when only the receipt and the
directory existed. Every one of them failed before the `ownership` accessor
gave the six callers a single answer to share.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402


def write_upstream(checkout: Path, *names: str) -> None:
    """Lay out a checkout the way cursor/plugins lays pstack out."""
    plugin = checkout / install.PSTACK_SUBDIR
    for name in names:
        skill = plugin / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: %s\n---\n" % name, encoding="utf-8"
        )
    manifest = plugin / install.PSTACK_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"name": "pstack", "version": install.PSTACK_VERSION}),
        encoding="utf-8",
    )


def fetch_writes(*names: str):
    """A `_run` stand-in that materializes an upstream tree on the fetch step."""

    def fake_run(command: list, cwd: Path, env=None) -> None:
        if command[1] == "fetch":
            write_upstream(cwd, *names)

    return fake_run


def verified(head: str = install.PSTACK_COMMIT):
    """Patch out the three checks that need a real git, leaving the logic.

    Deliberately patches `install` rather than reusing test_pstack's helper:
    that module loads install.py under a second module name, so its patches
    do not reach the instance every other test imports.
    """
    return (
        mock.patch.object(install.shutil, "which", return_value="/tools/git"),
        mock.patch.object(install, "checkout_head", return_value=head),
        mock.patch.object(install, "checkout_worktree_changes", return_value=""),
        mock.patch.object(install, "checkout_content_mismatches", return_value=[]),
    )


def external_root(directory: str, tool: str = "pstack", *names: str) -> Path:
    """A root holding `names` on disk, recorded as placed by `tool`."""
    root = Path(directory) / "skills"
    for name in names:
        skill = root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: %s\ndescription: from %s\n---\nbody\n" % (name, tool),
            encoding="utf-8",
        )
    install.record_external_install(root, tool, list(names), "ref", "head")
    return root


class OwnershipTests(unittest.TestCase):
    """The one accessor the other five callers now share."""

    def test_an_external_skill_is_recorded_and_ours_without_a_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            owner = install.ownership(root, "tdd")
            self.assertTrue(owner.present)
            self.assertFalse(owner.by_receipt)
            self.assertEqual(owner.by_external, "pstack")
            self.assertTrue(owner.recorded)
            self.assertTrue(owner.ours, "the conflict message offers --uninstall")

    def test_a_stranger_is_neither_recorded_nor_ours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            (root / "somebody-elses").mkdir(parents=True)
            owner = install.ownership(root, "somebody-elses")
            self.assertTrue(owner.present)
            self.assertFalse(owner.recorded)
            self.assertFalse(owner.ours)

    def test_a_claim_outlives_the_directory_it_claims(self) -> None:
        """The state the absent branch has to be able to clear."""
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            install.remove_path(root / "tdd")
            owner = install.ownership(root, "tdd")
            self.assertFalse(owner.present)
            self.assertTrue(owner.recorded)


class UninstallClearsEveryRecordTests(unittest.TestCase):
    def test_a_hand_deleted_external_skill_can_still_be_unclaimed(self) -> None:
        """The remedy the conflict error advertises has to actually work.

        Deleting the directory by hand leaves the ownership claim behind, and
        that claim is what refuses the next collection's install. Reporting
        `absent` and clearing nothing left the user with no way out but
        `--force` or hand-editing JSON.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            install.remove_path(root / "tdd")
            self.assertIn("tdd", install.externally_recorded(root))

            message = install.uninstall_one("tdd", root)

            self.assertIn("absent", message)
            self.assertNotIn(
                "tdd",
                install.externally_recorded(root),
                "the stale claim must be gone, or the blocked install stays blocked",
            )
            self.assertEqual(install.external_conflicts(root, "matt-skills", ["tdd"]), [])

    def test_a_dry_run_on_a_stale_claim_clears_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            install.remove_path(root / "tdd")
            install.uninstall_one("tdd", root, dry_run=True)
            self.assertIn("tdd", install.externally_recorded(root))

    def test_removing_a_skill_drops_the_visibility_choice_made_about_it(self) -> None:
        """A decision keyed by bare name must not outlive its owner.

        Both external collections ship `tdd` and disagree about it. A choice to
        unhide one collection's `tdd`, left behind after that `tdd` is removed,
        is re-applied to the next collection's `tdd` on install — silently
        unhiding a skill nobody reviewed. `record_external_install` already
        drops it when ownership changes hands on the --force path; removal is
        the same event.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            install.record_model_decisions([root], {"tdd": "enabled"})
            self.assertEqual(install.read_model_decisions([root]), {"tdd": "enabled"})

            install.uninstall_one("tdd", root)

            self.assertEqual(
                install.read_model_decisions([root]),
                {},
                "a stale 'enabled' would unhide the next collection's tdd",
            )


class ShadowingSeesExternalSkillsTests(unittest.TestCase):
    """Two collections shipping one name is the case shadowing is *for*."""

    def two_roots(self, directory: str, second_body: str) -> list:
        first = external_root(directory + "/a", "pstack", "tdd")
        second = Path(directory + "/b") / "skills"
        (second / "tdd").mkdir(parents=True)
        (second / "tdd" / "SKILL.md").write_text(second_body, encoding="utf-8")
        install.record_external_install(second, "matt-skills", ["tdd"], "ref", "head")
        return [first, second]

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        Path(self._dir.name + "/a").mkdir()
        Path(self._dir.name + "/b").mkdir()

    def test_identical_external_copies_report_shadowed(self) -> None:
        roots = self.two_roots(
            self._dir.name, "---\nname: tdd\ndescription: from pstack\n---\nbody\n"
        )
        reports = install.shadow_reports(roots)
        self.assertEqual([item.name for item in reports], ["tdd"])
        self.assertEqual(reports[0].state, install.SHADOWED)

    def test_disagreeing_external_copies_report_divergent(self) -> None:
        roots = self.two_roots(
            self._dir.name, "---\nname: tdd\ndescription: matt's, different\n---\nx\n"
        )
        reports = install.shadow_reports(roots)
        self.assertEqual([item.name for item in reports], ["tdd"])
        self.assertEqual(
            reports[0].state,
            install.DIVERGENT,
            "which copy an agent reads changes its behaviour; that is the finding",
        )
        self.assertIn(install.DIVERGENT, install.ACTIONABLE_STATES)


class RootMembershipTests(unittest.TestCase):
    def test_a_root_holding_only_external_skills_still_counts_as_held(self) -> None:
        """Otherwise the index forgets a root the installer itself wrote to."""
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd")
            self.assertTrue(install.root_holds_collection(root))


class PartialExternalInstallTests(unittest.TestCase):
    def test_a_copy_that_dies_half_way_still_records_what_landed(self) -> None:
        """The manifest must never be emptier than the directory.

        `install_one` refuses a destination it did not write, and the root is
        shared — so one hand-placed directory under a name the collection ships
        raises after earlier skills have already been copied in. Recorded only
        on success, those skills were unownable: the uninstaller refused to
        remove what the installer had just written.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "skills"
            stranger = root / "tdd"
            stranger.mkdir(parents=True)
            (stranger / "SKILL.md").write_text("hand placed\n", encoding="utf-8")

            patches = verified() + (
                mock.patch.object(
                    install, "_run", side_effect=fetch_writes("setup-pstack", "tdd")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaises(install.InstallError):
                    install.install_pstack(
                        ["claude"], [root], force=False, dry_run=False,
                        emit=lambda _line: None,
                    )

            landed = sorted(
                path.name for path in root.iterdir()
                if path.is_dir() and (path / "SKILL.md").is_file()
            )
            recorded = install.externally_recorded(root)
            self.assertIn("setup-pstack", landed, "it was copied before the failure")
            self.assertIn(
                "setup-pstack",
                recorded,
                "a skill on disk that no record claims cannot be uninstalled",
            )
            self.assertEqual(
                install.uninstall_one("setup-pstack", root).split()[0],
                "removed",
                "the installer must be able to remove what it just wrote",
            )




class VerifyPrefixTests(unittest.TestCase):
    """The one behaviour that distinguishes pstack's verification, run for real.

    Every install test patches `checkout_content_mismatches` out, so the prefix
    that keeps a monorepo verification from hashing thousands of unrelated
    blobs was never executed by the suite and its value was never asserted.
    """

    def test_each_collection_declares_the_prefix_its_layout_needs(self) -> None:
        self.assertEqual(install.MATT_SKILLS.verify_prefix, "skills/")
        self.assertEqual(
            install.PSTACK.verify_prefix,
            f"{install.PSTACK_SUBDIR}/",
            "pstack lives in a subdirectory of a monorepo; verifying from the "
            "repository root would let an unrelated plugin's .gitattributes "
            "stop the install",
        )

    def repo_with(self, directory: str, *paths: str) -> Path:
        checkout = Path(directory) / "checkout"
        checkout.mkdir()
        def run(*arguments: str) -> str:
            return subprocess.run(
                ["git", *arguments], cwd=checkout, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

        run("init", "--quiet")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        for relative in paths:
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("original\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "--quiet", "-m", "seed")
        # FETCH_HEAD is a file git writes, not a ref update-ref will take, and
        # the function under test reads exactly that name because that is what
        # a real fetch leaves behind.
        (checkout / ".git" / "FETCH_HEAD").write_text(
            "%s\t\tbranch 'main' of upstream\n" % run("rev-parse", "HEAD"),
            encoding="utf-8",
        )
        return checkout

    def test_a_rewrite_inside_the_prefix_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.repo_with(directory, "pstack/skills/tdd/SKILL.md")
            (checkout / "pstack/skills/tdd/SKILL.md").write_text(
                "tampered\n", encoding="utf-8"
            )
            mismatches = install.checkout_content_mismatches(
                checkout, "git", install.PSTACK.verify_prefix
            )
            self.assertEqual(mismatches, ["pstack/skills/tdd/SKILL.md"])

    def test_a_rewrite_outside_the_prefix_is_ignored(self) -> None:
        """An unrelated plugin in the same monorepo must not block the install."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.repo_with(
                directory, "pstack/skills/tdd/SKILL.md", "other-plugin/thing.md"
            )
            (checkout / "other-plugin/thing.md").write_text("tampered\n", encoding="utf-8")
            mismatches = install.checkout_content_mismatches(
                checkout, "git", install.PSTACK.verify_prefix
            )
            self.assertEqual(mismatches, [])


class FailedUpdateTests(unittest.TestCase):
    """A record must never end up claiming less than the directory holds."""

    def install_two(self, root: Path) -> None:
        patches = verified() + (
            mock.patch.object(
                install, "_run", side_effect=fetch_writes("setup-pstack", "architect")
            ),
        )
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            install.install_pstack(
                ["claude"], [root], force=False, dry_run=False, emit=lambda _l: None
            )

    def test_an_update_that_dies_half_way_does_not_unclaim_what_is_still_there(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "skills"
            self.install_two(root)
            self.assertEqual(
                install.externally_recorded(root), {"setup-pstack", "architect"}
            )

            real = install.install_one
            calls = {"n": 0}

            def fail_second(source, dest_root, mode, force, dry_run):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise install.InstallError("disk full")
                return real(source, dest_root, mode, force, dry_run)

            patches = verified() + (
                mock.patch.object(
                    install, "_run",
                    side_effect=fetch_writes("setup-pstack", "architect"),
                ),
                mock.patch.object(install, "install_one", side_effect=fail_second),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaises(install.InstallError):
                    install.install_pstack(
                        ["claude"], [root], force=False, dry_run=False,
                        emit=lambda _l: None,
                    )

            on_disk = {
                path.name for path in root.iterdir()
                if path.is_dir() and (path / "SKILL.md").is_file()
            }
            recorded = install.externally_recorded(root)
            self.assertTrue(
                on_disk <= recorded,
                "manifest %s claims less than the disk holds %s" % (recorded, on_disk),
            )

    def test_the_error_that_stopped_the_install_is_the_one_raised(self) -> None:
        """A failure writing the record must not replace the real cause."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "skills"
            patches = verified() + (
                mock.patch.object(
                    install, "_run", side_effect=fetch_writes("setup-pstack")
                ),
                mock.patch.object(
                    install, "install_one",
                    side_effect=install.InstallError("the real cause"),
                ),
                mock.patch.object(
                    install, "record_external_install",
                    side_effect=OSError("record write failed"),
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaises(install.InstallError) as caught:
                    install.install_pstack(
                        ["claude"], [root], force=False, dry_run=False,
                        emit=lambda _l: None,
                    )
            self.assertIn("the real cause", str(caught.exception))


class BulkUninstallCoversEveryRecordTests(unittest.TestCase):
    def test_all_skills_includes_externally_recorded_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd", "teach")
            self.assertEqual(
                install.uninstall_names(root, all_skills=True), ["tdd", "teach"]
            )

    def test_orphans_clears_a_hand_deleted_external_claim(self) -> None:
        """Otherwise the manifest, and the index entry resting on it, live on."""
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd", "teach")
            install.remove_path(root / "tdd")
            self.assertIn("tdd", install.uninstall_names(root, orphans=True))
            install.uninstall_many([root], orphans=True, emit=lambda _l: None)
            self.assertNotIn("tdd", install.externally_recorded(root))

    def test_removing_everything_leaves_no_record_holding_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = external_root(directory, "pstack", "tdd", "teach")
            install.uninstall_many([root], all_skills=True, emit=lambda _l: None)
            self.assertEqual(install.externally_recorded(root), set())
            self.assertFalse(install.root_holds_collection(root))


class ShadowReportingStaysReadableTests(unittest.TestCase):
    def test_the_agreeing_half_collapses_to_one_line(self) -> None:
        """Identical copies in two roots are what a machine-wide install makes."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            roots = []
            for leaf in ("a", "b"):
                base = Path(directory) / leaf
                base.mkdir()
                root = external_root(
                    str(base), "pstack", *["s%d" % n for n in range(12)]
                )
                install.remember_root(root, "user", "claude", home)
                roots.append(root)
            (roots[1] / "s3" / "SKILL.md").write_text(
                "---\nname: s3\n---\nDIFFERENT\n", encoding="utf-8"
            )

            lines, pending = install.status_lines(
                [], False, install.machine_status(home)
            )
            block = "\n".join(lines)
            self.assertIn("divergent", block)
            self.assertIn("s3", block)
            self.assertLess(
                block.count("shadowed"), 3,
                "the agreeing names must collapse, not list one row each",
            )
            self.assertTrue(pending, "a divergence is actionable")


if __name__ == "__main__":
    unittest.main()
