"""The ledger, discovery, and removal: what an uninstall is allowed to undo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)
SKILL = BUNDLED[0]
OTHER = BUNDLED[1]


class Fixture(unittest.TestCase):
    """A throwaway home, and the installer under it."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()
        self.root = self.home / ".claude" / "skills"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def install(self, name: str = SKILL, mode: str = "copy", **kwargs) -> str:
        return install.install_one(
            install.SOURCE_ROOT / name, self.root, mode, True, False, **kwargs
        )

    def receipt(self, root: Path = None) -> dict:
        return json.loads(
            install.receipt_path(root or self.root).read_text(encoding="utf-8")
        )

    def foreign_skill(self, name: str = SKILL, body: str = "not ours\n") -> Path:
        """A skill directory this collection did not put there."""
        directory = self.root / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(body, encoding="utf-8")
        return directory

    def run_installer(self, *arguments: str, expected: int = 0):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result


class LedgerTests(Fixture):
    def test_install_records_an_entry_with_mode_and_origin(self) -> None:
        self.install()
        entry = install.receipt_entries(self.root, kind="skill")[SKILL]
        self.assertEqual("copy", entry["mode"])
        self.assertEqual("bundled", entry["origin"])
        self.assertEqual(install.VERSION, entry["version"])
        self.assertTrue(entry["installed_at"])

    def test_a_v1_receipt_is_upgraded_on_read_without_rewriting_the_file(self) -> None:
        self.root.mkdir(parents=True)
        original = {
            "schema_version": 1,
            "collection": "dm1681/skills",
            "version": "8.0.0",
            "skills": [SKILL],
            "mode": "link",
            "installed_at": "2020-01-01T00:00:00+00:00",
        }
        install.receipt_path(self.root).write_text(
            json.dumps(original), encoding="utf-8"
        )
        entry = install.receipt_entries(self.root, kind="skill")[SKILL]
        self.assertEqual("unknown", entry["origin"])
        self.assertEqual("link", entry["mode"])
        self.assertEqual([], entry["backups"])
        # In memory only: a read is not a write.
        self.assertEqual(original, self.receipt())

    def test_write_receipt_keeps_entries_for_skills_outside_this_run(self) -> None:
        self.install(SKILL)
        install.write_receipt(self.root, [OTHER], "copy", False)
        entries = install.receipt_entries(self.root, kind="skill")
        self.assertEqual([SKILL, OTHER], sorted(entries, key=[SKILL, OTHER].index))
        self.assertEqual([OTHER], self.receipt()["skills"])

    def test_an_entry_for_a_deleted_skill_survives_the_next_write(self) -> None:
        """A stale record is the only evidence that a directory went missing."""
        self.install(SKILL)
        install.remove_path(self.root / SKILL)
        install.write_receipt(self.root, [], "copy", False)
        self.assertIn(SKILL, install.receipt_entries(self.root, kind="skill"))

    def test_a_replaced_foreign_directory_is_recorded_as_foreign(self) -> None:
        self.foreign_skill()
        self.install()
        backups = install.receipt_entries(self.root)[SKILL]["backups"]
        self.assertEqual([True], [record["foreign"] for record in backups])

    def test_replacing_our_own_copy_records_the_backup_as_not_foreign(self) -> None:
        self.install()
        (self.root / SKILL / "SKILL.md").write_text("drifted\n", encoding="utf-8")
        self.install()
        backups = install.receipt_entries(self.root)[SKILL]["backups"]
        self.assertEqual([False], [record["foreign"] for record in backups])

    def test_matt_style_installs_are_recorded_with_their_origin(self) -> None:
        self.install(origin="matt-skills")
        self.assertEqual(
            [SKILL], list(install.receipt_entries(self.root, origin="matt-skills"))
        )
        self.assertEqual({}, install.receipt_entries(self.root, origin="bundled"))

    def test_install_records_the_root_in_the_registry(self) -> None:
        self.run_installer("--home", str(self.home), "--skill", SKILL)
        self.assertIn(
            self.root.resolve(), install.known_roots(self.home)
        )

    def test_known_roots_skips_a_root_that_no_longer_exists(self) -> None:
        gone = self.home / "gone"
        gone.mkdir()
        install.record_root(self.home, gone)
        self.assertEqual([gone], install.known_roots(self.home))
        gone.rmdir()
        self.assertEqual([], install.known_roots(self.home))
        # Read-time pruning only: the record itself is left for --prune.
        self.assertIn(str(gone), install.registry_path(self.home).read_text())

    def test_forget_roots_drops_only_what_it_is_given(self) -> None:
        first, second = self.home / "a", self.home / "b"
        for root in (first, second):
            root.mkdir()
            install.record_root(self.home, root)
        self.assertEqual([first], install.forget_roots(self.home, [first]))
        self.assertEqual([second], install.known_roots(self.home))


class DiscoveryTests(Fixture):
    def test_discover_lists_installed_skills_with_mode_shape_and_root(self) -> None:
        self.install()
        item = install.discover_skills([self.root])[0]
        self.assertEqual(
            ("skill", SKILL, "copy", "copy"),
            (item.kind, item.name, item.mode, item.shape),
        )
        self.assertEqual(self.root, item.root)
        self.assertTrue(item.recorded)
        self.assertTrue(item.bundled)

    def test_a_directory_with_no_receipt_entry_is_unrecorded(self) -> None:
        self.foreign_skill()
        item = install.discover_skills([self.root])[0]
        self.assertFalse(item.recorded)
        self.assertEqual("unknown", item.origin)
        self.assertEqual("UNRECORDED", item.detail)

    def test_discover_marks_a_name_outside_the_checkout_as_not_bundled(self) -> None:
        self.foreign_skill("not-in-this-checkout")
        item = install.discover_skills([self.root])[0]
        self.assertFalse(item.bundled)

    def test_discover_reports_managed_files_and_flags_a_hand_edit(self) -> None:
        self.assertEqual([], install.discover_managed_files(self.home))
        install.install_global_instructions(self.home, "link", False)
        items = install.discover_managed_files(self.home)
        self.assertEqual(
            [self.home / ".agents" / "AGENTS.md", self.home / ".claude" / "CLAUDE.md"],
            [item.path for item in items],
        )
        self.assertTrue(all(item.recorded for item in items))
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.write_text("# mine now\n", encoding="utf-8")
        edited = [
            item for item in install.discover_managed_files(self.home)
            if item.path == claude
        ][0]
        self.assertEqual("hand-edited since install", edited.detail)

    def test_discover_flags_a_shim_written_from_another_checkout(self) -> None:
        import skills_cli

        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        for path, _content, _newline, _executable in skills_cli.shims(ROOT, bin_dir):
            path.write_text(
                "#!/bin/sh\n# Generated by `skills setup-path` from /elsewhere\n",
                encoding="utf-8",
            )
        items = install.discover_shims(bin_dir)
        self.assertTrue(items)
        self.assertTrue(all(not item.recorded for item in items))
        self.assertIn("another checkout", items[0].detail)

    def test_format_status_names_every_kind(self) -> None:
        import skills_cli

        self.install()
        install.install_global_instructions(self.home, "link", False)
        bin_dir = self.home / ".local" / "bin"
        skills_cli.write_shims(ROOT, bin_dir)
        (self.root / install.external_tool("graphify").marker).mkdir()
        text = install.format_status(install.discover([self.root], self.home, bin_dir))
        for kind in ("skill", "managed-file", "shim", "external"):
            self.assertIn(kind, text)
        self.assertIn(SKILL, text)
        self.assertIn("graphify", text)

    def test_format_status_says_so_when_nothing_is_installed(self) -> None:
        self.assertIn("nothing", install.format_status([]))


class RemovalTests(Fixture):
    def test_uninstalling_a_copy_backs_it_up_then_removes_it(self) -> None:
        self.install()
        message = install.uninstall_one(SKILL, self.root, False)
        self.assertTrue(message.startswith("removed"))
        self.assertFalse((self.root / SKILL).exists())
        backups = list(
            (self.home / ".claude" / ".skills-backups" / "skills").glob(f"{SKILL}-*")
        )
        self.assertEqual(1, len(backups))
        self.assertTrue((backups[0] / "SKILL.md").is_file())
        self.assertNotIn(SKILL, install.receipt_entries(self.root))

    def test_uninstalling_restores_the_recorded_pre_install_original(self) -> None:
        self.foreign_skill(body="mine\n")
        self.install()
        install.uninstall_one(SKILL, self.root, False)
        self.assertEqual(
            "mine\n", (self.root / SKILL / "SKILL.md").read_text(encoding="utf-8")
        )

    def test_uninstalling_does_not_restore_a_backup_of_our_own_copy(self) -> None:
        self.install()
        (self.root / SKILL / "SKILL.md").write_text("drifted\n", encoding="utf-8")
        self.install()  # backs our own drifted copy up, foreign=False
        message = install.uninstall_one(SKILL, self.root, False)
        self.assertFalse((self.root / SKILL).exists())
        self.assertIn("no pre-install original", message)

    def test_unrecorded_backups_are_reported_not_restored(self) -> None:
        self.install()
        stray = (
            self.home / ".claude" / ".skills-backups" / "skills"
            / f"{SKILL}-20200101T000000Z"
        )
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("ancient\n", encoding="utf-8")
        message = install.uninstall_one(SKILL, self.root, False)
        self.assertIn("--restore-from", message)
        self.assertFalse((self.root / SKILL).exists())
        self.assertTrue((stray / "SKILL.md").is_file())

    def test_restore_from_names_a_backup_explicitly(self) -> None:
        self.install()
        stray = (
            self.home / ".claude" / ".skills-backups" / "skills"
            / f"{SKILL}-20200101T000000Z"
        )
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("ancient\n", encoding="utf-8")
        install.uninstall_one(SKILL, self.root, False, restore_from=stray)
        self.assertEqual(
            "ancient\n", (self.root / SKILL / "SKILL.md").read_text(encoding="utf-8")
        )

    def test_restore_from_a_path_that_is_not_there_is_refused(self) -> None:
        self.install()
        with self.assertRaises(install.InstallError):
            install.uninstall_one(
                SKILL, self.root, False, restore_from=self.home / "nope"
            )

    @unittest.skipIf(os.name == "nt", "Windows symlinks may require Developer Mode")
    def test_uninstalling_a_link_unlinks_and_leaves_the_checkout_intact(self) -> None:
        self.install(mode="link")
        message = install.uninstall_one(SKILL, self.root, False)
        self.assertIn("link; nothing to back up", message)
        self.assertFalse((self.root / SKILL).is_symlink())
        self.assertTrue((install.SOURCE_ROOT / SKILL / "SKILL.md").is_file())

    @unittest.skipIf(os.name == "nt", "Windows symlinks may require Developer Mode")
    def test_a_broken_link_is_still_removed(self) -> None:
        self.install(mode="link")
        install.record_entry(self.root, SKILL, "skill", mode="link")
        (self.root / SKILL).unlink()
        (self.root / SKILL).symlink_to(self.home / "gone", target_is_directory=True)
        self.assertFalse((self.root / SKILL).exists())
        install.uninstall_one(SKILL, self.root, False)
        self.assertFalse((self.root / SKILL).is_symlink())

    def test_uninstalling_twice_reports_absent(self) -> None:
        self.install()
        install.uninstall_one(SKILL, self.root, False)
        self.assertTrue(
            install.uninstall_one(SKILL, self.root, False).startswith("absent")
        )

    def test_dry_run_writes_nothing(self) -> None:
        self.install()
        before = install.receipt_path(self.root).read_text(encoding="utf-8")
        message = install.uninstall_one(SKILL, self.root, True)
        self.assertTrue(message.startswith("would remove"))
        self.assertTrue((self.root / SKILL / "SKILL.md").is_file())
        self.assertEqual(before, install.receipt_path(self.root).read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".claude" / ".skills-backups").exists())

    def test_the_receipt_and_decisions_go_with_the_last_skill(self) -> None:
        self.install()
        install.record_model_decisions([self.root], {SKILL: "hidden"})
        install.uninstall_one(SKILL, self.root, False)
        self.assertEqual({}, install.read_model_decisions([self.root]))
        install.prune_root(self.root)
        self.assertFalse(self.root.exists())
        self.assertTrue(self.root.parent.is_dir())

    def test_an_unrecorded_directory_is_refused_without_the_flag(self) -> None:
        self.foreign_skill()
        with self.assertRaises(install.InstallError) as caught:
            install.uninstall_one(SKILL, self.root, False)
        self.assertIn("--unrecorded", str(caught.exception))
        self.assertTrue((self.root / SKILL / "SKILL.md").is_file())
        install.uninstall_one(SKILL, self.root, False, allow_unrecorded=True)
        self.assertFalse((self.root / SKILL).exists())

    def test_a_root_that_holds_other_files_is_not_removed(self) -> None:
        self.install()
        install.uninstall_one(SKILL, self.root, False)
        (self.root / "somebody-elses-notes.md").write_text("hi\n", encoding="utf-8")
        install.prune_root(self.root)
        self.assertTrue(self.root.is_dir())

    def test_forget_entry_leaves_the_files_alone(self) -> None:
        self.install()
        message = install.forget_entry(self.root, SKILL)
        self.assertIn("forgot", message)
        self.assertTrue((self.root / SKILL / "SKILL.md").is_file())
        self.assertEqual({}, install.receipt_entries(self.root))
        self.assertIn("unchanged", install.forget_entry(self.root, SKILL))


class GlobalInstructionRemovalTests(Fixture):
    def claude(self) -> Path:
        return self.home / ".claude" / "CLAUDE.md"

    def test_uninstalling_global_instructions_restores_the_hand_written_original(self) -> None:
        self.claude().parent.mkdir(parents=True)
        self.claude().write_text("# hand written\n", encoding="utf-8")
        install.install_global_instructions(self.home, "link", False)
        messages = install.uninstall_global_instructions(self.home, False)
        self.assertTrue(any("restored" in message for message in messages))
        self.assertEqual("# hand written\n", self.claude().read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".agents" / "AGENTS.md").exists())

    def test_a_hand_edited_managed_file_is_left_alone_and_said_so(self) -> None:
        install.install_global_instructions(self.home, "link", False)
        self.claude().write_text("# mine now\n", encoding="utf-8")
        messages = install.uninstall_global_instructions(self.home, False)
        self.assertTrue(any("hand-edited since install" in m for m in messages))
        self.assertEqual("# mine now\n", self.claude().read_text(encoding="utf-8"))

    def test_both_managed_files_go_together(self) -> None:
        install.install_global_instructions(self.home, "link", False)
        install.remove_path(self.home / ".agents" / "AGENTS.md")
        messages = install.uninstall_global_instructions(self.home, False)
        self.assertEqual(2, len(messages))
        self.assertTrue(messages[0].startswith("absent"))
        self.assertTrue(messages[1].startswith("removed"))
        self.assertFalse(self.claude().exists())

    def test_an_unrecorded_managed_backup_without_the_marker_is_restored(self) -> None:
        """An install that predates the ledger left no receipt; the marker is
        the only evidence left of whose file each one is."""
        self.claude().parent.mkdir(parents=True)
        self.claude().write_text(
            install.MANAGED_MARKER + "\n\n# generated\n", encoding="utf-8"
        )
        backup = (
            self.home / ".skills-backups" / ".claude" / "CLAUDE.md-20200101T000000Z"
        )
        backup.parent.mkdir(parents=True)
        backup.write_text("# hand written\n", encoding="utf-8")
        install.uninstall_managed_file(self.claude(), False, home=self.home)
        self.assertEqual("# hand written\n", self.claude().read_text(encoding="utf-8"))


class ExternalRemovalTests(Fixture):
    def test_matt_skills_removal_uses_the_recorded_origin(self) -> None:
        self.install(origin="matt-skills")
        self.install(OTHER)  # bundled: not matt-skills' to remove
        removable, _notes = install.external_removal_plan("matt-skills", [self.root])
        self.assertEqual([(SKILL, self.root)], removable)
        install.uninstall_external("matt-skills", [self.root], False)
        self.assertFalse((self.root / SKILL).exists())
        self.assertTrue((self.root / OTHER / "SKILL.md").is_file())

    def test_matt_skills_without_records_removes_nothing_and_says_why(self) -> None:
        marker = self.root / install.external_tool("matt-skills").marker
        marker.mkdir(parents=True)
        (marker / "SKILL.md").write_text("upstream\n", encoding="utf-8")
        messages = install.uninstall_external("matt-skills", [self.root], False)
        self.assertTrue(any("--unrecorded" in message for message in messages))
        self.assertTrue((marker / "SKILL.md").is_file())

    def test_graphify_removal_prints_the_commands_it_cannot_run(self) -> None:
        (self.root / "graphify").mkdir(parents=True)
        removable, notes = install.external_removal_plan("graphify", [self.root])
        self.assertEqual([], removable)
        self.assertEqual(3, len(notes))
        joined = "\n".join(install.uninstall_external("graphify", [self.root], False))
        self.assertIn("uv tool uninstall graphifyy", joined)
        self.assertTrue((self.root / "graphify").is_dir())

    def test_every_registered_tool_carries_a_removal_line(self) -> None:
        for tool in install.EXTERNAL_TOOLS:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.removal.strip())
                self.assertEqual(tool.removal, tool.removal.strip())


class CommandLineTests(Fixture):
    def test_uninstall_without_a_selector_is_refused(self) -> None:
        result = self.run_installer(
            "--home", str(self.home), "--uninstall", expected=2
        )
        self.assertIn("--uninstall needs to know what to remove", result.stderr)

    def test_uninstall_all_removes_every_recorded_skill(self) -> None:
        self.run_installer("--home", str(self.home), "--agent", "claude")
        self.run_installer("--home", str(self.home), "--agent", "claude", "--uninstall", "--all")
        self.assertFalse(self.root.exists())

    def test_uninstall_names_one_skill_and_leaves_the_rest(self) -> None:
        self.run_installer("--home", str(self.home), "--agent", "claude")
        self.run_installer(
            "--home", str(self.home), "--agent", "claude",
            "--uninstall", "--skill", SKILL,
        )
        self.assertFalse((self.root / SKILL).exists())
        self.assertTrue((self.root / OTHER / "SKILL.md").is_file())

    def test_uninstalling_something_that_was_never_installed_is_refused(self) -> None:
        result = self.run_installer(
            "--home", str(self.home), "--agent", "claude",
            "--uninstall", "--skill", SKILL, expected=2,
        )
        self.assertIn("not installed in", result.stderr)

    def test_the_home_receipt_goes_with_the_last_managed_file(self) -> None:
        """It exists only to describe those files; with none left it is litter."""
        self.run_installer("--home", str(self.home), "--global-instructions")
        self.assertTrue(install.receipt_path(self.home).is_file())
        self.run_installer("--home", str(self.home), "--uninstall", "--global-instructions")
        self.assertFalse(install.receipt_path(self.home).is_file())
        self.assertTrue(self.home.is_dir())

    def test_status_lists_the_installed_skills(self) -> None:
        self.run_installer("--home", str(self.home), "--agent", "claude", "--skill", SKILL)
        result = self.run_installer("--home", str(self.home), "--agent", "claude", "--status")
        self.assertIn(SKILL, result.stdout)
        self.assertIn(str(self.root), result.stdout)

    def test_status_sweeps_a_registry_root_that_was_not_named(self) -> None:
        target = Path(self.directory.name) / "elsewhere"
        self.run_installer(
            "--home", str(self.home), "--target", str(target), "--skill", SKILL
        )
        result = self.run_installer("--home", str(self.home), "--status")
        self.assertIn(str(target.resolve()), result.stdout)

    def test_all_outside_uninstall_is_refused(self) -> None:
        result = self.run_installer("--home", str(self.home), "--all", expected=2)
        self.assertIn("--all only applies to --uninstall", result.stderr)

    def test_restore_from_needs_exactly_one_skill(self) -> None:
        result = self.run_installer(
            "--home", str(self.home), "--uninstall", "--all",
            "--restore-from", str(self.home), expected=2,
        )
        self.assertIn("exactly one --skill", result.stderr)

    def test_uninstall_never_opens_the_dashboard(self) -> None:
        """Removal must work on a machine that has no Textual."""
        self.run_installer("--home", str(self.home), "--agent", "claude", "--skill", SKILL)
        code = (
            "import sys; sys.modules['textual'] = None; sys.path.insert(0, %r);\n"
            "import install\n"
            "code = install.main(['--home', %r, '--agent', 'claude', "
            "'--uninstall', '--all'])\n"
            "print('textual-imported', 'skills_tui' in sys.modules)\n"
            "raise SystemExit(code)\n" % (str(ROOT), str(self.home))
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("textual-imported False", result.stdout)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
