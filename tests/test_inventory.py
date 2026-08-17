"""Detection, diff, and resolution: what "inconsistent" means, and what fixes it.

Nothing here imports textual, deliberately: the doctor is a scripted path, and
a machine without the dashboard's dependency still has to be able to ask what
is wrong with it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402
import inventory  # noqa: E402

BUNDLED = sorted(
    path.name
    for path in (ROOT / "skills").iterdir()
    if path.is_dir() and (path / "SKILL.md").is_file()
)
SKILL = BUNDLED[0]
OTHER = BUNDLED[1]


class Fixture(unittest.TestCase):
    """A throwaway home and project, with real installs under them."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.project = self.base / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def user_root(self) -> Path:
        return self.home / ".claude" / "skills"

    def project_root(self) -> Path:
        return self.project / ".claude" / "skills"

    def install_skill(self, root: Path, name: str = SKILL, mode: str = "copy") -> Path:
        install.install_one(install.SOURCE_ROOT / name, root, mode, True, False)
        return root / name

    def edit(self, path: Path) -> None:
        entrypoint = path / "SKILL.md"
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8"
        )

    def scan(self, **kwargs) -> inventory.Inventory:
        kwargs.setdefault("project_dirs", [self.project])
        return inventory.scan(self.home, **kwargs)

    def findings(self, **kwargs) -> list:
        include_foreign = kwargs.pop("include_foreign", False)
        return inventory.findings(self.scan(**kwargs), include_foreign)

    def kinds(self, **kwargs) -> list:
        return [finding.kind for finding in self.findings(**kwargs)]


class DiscoveryTests(Fixture):
    def test_scan_sweeps_both_user_roots(self) -> None:
        roots = [str(root) for root, _scope in self.scan().roots]
        self.assertIn(str(self.home / ".agents" / "skills"), roots)
        self.assertIn(str(self.home / ".claude" / "skills"), roots)

    def test_scan_includes_a_named_project_dir(self) -> None:
        self.install_skill(self.project_root())
        placements = self.scan().placements
        self.assertEqual([SKILL], [placement.name for placement in placements])
        self.assertEqual("project", placements[0].scope)

    def test_registry_roots_are_swept_without_being_named(self) -> None:
        elsewhere = self.base / "elsewhere" / ".claude" / "skills"
        self.install_skill(elsewhere)
        install.record_root(self.home, elsewhere)
        scanned = inventory.scan(self.home)
        self.assertIn(str(elsewhere), [str(root) for root, _scope in scanned.roots])
        self.assertEqual([SKILL], [item.name for item in scanned.placements])
        self.assertEqual(
            [], [item for item in inventory.scan(self.home, include_registry=False).placements]
        )

    def test_a_recorded_root_that_is_gone_is_reported_not_scanned(self) -> None:
        gone = self.base / "gone" / ".claude" / "skills"
        gone.mkdir(parents=True)
        install.record_root(self.home, gone)
        install.remove_path(self.base / "gone")
        scanned = inventory.scan(self.home)
        self.assertEqual([gone], list(scanned.missing_roots))
        self.assertNotIn(str(gone), [str(root) for root, _scope in scanned.roots])
        self.assertEqual([], inventory.findings(scanned))

    def test_scan_reuses_install_discover_rows(self) -> None:
        """A placement wraps the row install.discover produced, untouched."""
        self.install_skill(self.user_root())
        placement = self.scan().placements[0]
        self.assertIsInstance(placement.item, install.Installed)
        self.assertEqual("bundled", placement.item.origin)
        self.assertEqual("copy", placement.item.mode)
        self.assertEqual(placement.item.path, placement.path)

    def test_hidden_files_in_a_root_are_not_placements(self) -> None:
        self.install_skill(self.user_root())
        install.record_model_decisions([self.user_root()], {SKILL: "hidden"})
        names = [placement.name for placement in self.scan().placements]
        self.assertEqual([SKILL], names)

    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_shape_reports_copy_and_link(self) -> None:
        self.install_skill(self.user_root(), SKILL, "copy")
        self.install_skill(self.project_root(), OTHER, "link")
        shapes = {
            placement.name: placement.shape for placement in self.scan().placements
        }
        self.assertEqual({SKILL: "copy", OTHER: "link"}, shapes)


class DigestTests(Fixture):
    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_digest_is_equal_for_a_copy_and_a_link_of_one_tree(self) -> None:
        copied = self.install_skill(self.user_root(), SKILL, "copy")
        linked = self.install_skill(self.project_root(), SKILL, "link")
        self.assertEqual(inventory.tree_digest(copied), inventory.tree_digest(linked))

    def test_digest_changes_when_a_file_changes(self) -> None:
        copied = self.install_skill(self.user_root())
        before = inventory.tree_digest(copied)
        self.edit(copied)
        self.assertNotEqual(before, inventory.tree_digest(copied))

    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_digest_of_a_dangling_link_is_missing(self) -> None:
        root = self.user_root()
        root.mkdir(parents=True)
        (root / SKILL).symlink_to(self.base / "not-here")
        self.assertEqual("missing", inventory.tree_digest(root / SKILL))
        self.assertEqual("missing", inventory.short_digest("missing"))


class DetectionTests(Fixture):
    def test_a_matching_install_produces_no_findings(self) -> None:
        self.install_skill(self.user_root())
        self.assertEqual([], self.findings())

    def test_an_edited_copy_is_diverged_from_source(self) -> None:
        self.edit(self.install_skill(self.user_root()))
        found = self.findings()
        self.assertEqual([inventory.DIVERGED], [finding.kind for finding in found])
        self.assertEqual(SKILL, found[0].name)

    def test_two_roots_with_different_content_is_a_duplicate(self) -> None:
        self.install_skill(self.user_root())
        self.edit(self.install_skill(self.project_root()))
        self.assertIn(inventory.DUPLICATE_DIVERGED, self.kinds())

    def test_two_roots_with_equal_content_is_not_a_duplicate(self) -> None:
        self.install_skill(self.user_root())
        self.install_skill(self.project_root())
        self.assertEqual([], self.findings())

    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_equal_content_in_different_shapes_is_a_shape_mismatch(self) -> None:
        self.install_skill(self.user_root(), SKILL, "copy")
        self.install_skill(self.project_root(), SKILL, "link")
        self.assertEqual([inventory.SHAPE_MISMATCH], self.kinds())

    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_a_broken_link_is_reported_once_and_suppresses_diverged(self) -> None:
        """The checkout it pointed at moved, which is how links really break."""
        moved = self.base / "old-checkout" / SKILL
        shutil.copytree(install.SOURCE_ROOT / SKILL, moved)
        install.install_one(moved, self.user_root(), "link", True, False)
        install.remove_path(self.base / "old-checkout")
        found = self.findings()
        self.assertEqual([inventory.BROKEN_LINK], [finding.kind for finding in found])
        self.assertEqual(
            "reinstall the link from this checkout", found[0].resolutions[0].label
        )

    @unittest.skipIf(os.name == "nt", "symlinks need a privileged Windows session")
    def test_a_link_to_another_checkout_is_stale(self) -> None:
        other_checkout = self.base / "other" / "skills" / SKILL
        other_checkout.mkdir(parents=True)
        (other_checkout / "SKILL.md").write_text("elsewhere\n", encoding="utf-8")
        root = self.user_root()
        root.mkdir(parents=True)
        (root / SKILL).symlink_to(other_checkout)
        found = self.findings()
        self.assertEqual([inventory.STALE_LINK], [finding.kind for finding in found])
        self.assertEqual("relink to this checkout", found[0].resolutions[0].label)

    def test_a_directory_without_skill_md_is_incomplete(self) -> None:
        partial = self.install_skill(self.user_root())
        (partial / "SKILL.md").unlink()
        self.assertEqual([inventory.INCOMPLETE], self.kinds())

    def test_a_receipt_entry_without_a_directory_is_an_orphan(self) -> None:
        self.install_skill(self.user_root())
        install.remove_path(self.user_root() / SKILL)
        found = self.findings()
        self.assertEqual([inventory.ORPHAN_RECEIPT], [f.kind for f in found])
        self.assertEqual("forget the entry", found[0].resolutions[0].label)

    def test_an_unparseable_receipt_is_a_finding_not_a_crash(self) -> None:
        root = self.user_root()
        root.mkdir(parents=True)
        install.receipt_path(root).write_text("{not json", encoding="utf-8")
        scanned = self.scan()
        self.assertEqual([root], list(scanned.unreadable_receipts))
        found = inventory.findings(scanned)
        self.assertEqual([inventory.CORRUPT_RECEIPT], [f.kind for f in found])
        self.assertEqual(inventory.KEEP, found[0].resolutions[0].action)

    def test_a_skill_outside_this_checkout_is_hidden_unless_requested(self) -> None:
        stray = self.user_root() / "not-in-this-checkout"
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("mine\n", encoding="utf-8")
        self.assertEqual([], self.findings())
        self.assertEqual([], self.findings(include_foreign=True))

    def test_an_unbundled_name_diverging_across_roots_is_still_a_duplicate(self) -> None:
        for root, body in ((self.user_root(), "one\n"), (self.project_root(), "two\n")):
            stray = root / "not-in-this-checkout"
            stray.mkdir(parents=True)
            (stray / "SKILL.md").write_text(body, encoding="utf-8")
        found = self.findings()
        self.assertEqual([inventory.DUPLICATE_DIVERGED], [f.kind for f in found])
        # Never offered a reinstall: there is no source here to reinstall from,
        # and never an uninstall either, because no receipt records these two,
        # so apply_fix would refuse them. The offer names --unrecorded instead.
        self.assertEqual(
            {inventory.KEEP},
            {resolution.action for resolution in found[0].resolutions},
        )
        self.assertIn("--unrecorded", found[0].resolutions[0].label)

    def test_every_offered_fix_for_an_unrecorded_duplicate_can_be_applied(self) -> None:
        """The default fix has to be applicable; a suggestion that only raises
        is worse than no suggestion."""
        for root, body in ((self.user_root(), "one\n"), (self.project_root(), "two\n")):
            stray = root / "not-in-this-checkout"
            stray.mkdir(parents=True)
            (stray / "SKILL.md").write_text(body, encoding="utf-8")
        for resolution in self.findings()[0].resolutions:
            self.assertEqual([], inventory.apply_resolution(resolution, False))
        self.assertTrue((self.user_root() / "not-in-this-checkout").is_dir())
        self.assertTrue((self.project_root() / "not-in-this-checkout").is_dir())

    def test_only_a_model_visibility_edit_is_not_a_divergence(self) -> None:
        installed = self.install_skill(self.user_root())
        self.assertTrue(install.set_model_invocation(installed, visible=False))
        self.assertEqual([], self.findings())
        self.edit(installed)
        self.assertEqual([inventory.DIVERGED], self.kinds())

    def test_findings_are_ordered_by_severity_then_name(self) -> None:
        self.edit(self.install_skill(self.user_root(), SKILL))
        partial = self.install_skill(self.user_root(), OTHER)
        (partial / "SKILL.md").unlink()
        self.assertEqual(
            [inventory.INCOMPLETE, inventory.DIVERGED], self.kinds()
        )


class ResolutionTests(Fixture):
    def diverged(self) -> inventory.Finding:
        self.edit(self.install_skill(self.user_root()))
        return self.findings()[0]

    def test_the_default_resolution_for_a_diverged_skill_is_reinstall(self) -> None:
        resolution = self.diverged().resolutions[0]
        self.assertEqual(inventory.REINSTALL, resolution.action)
        self.assertEqual(inventory.WRITE, resolution.consequence)

    def test_applying_reinstall_clears_the_finding(self) -> None:
        inventory.apply_resolution(self.diverged().resolutions[0], False)
        self.assertEqual([], self.findings())
        self.assertTrue(
            install.trees_equal(
                self.user_root() / SKILL, install.SOURCE_ROOT / SKILL
            )
        )

    def test_applying_uninstall_backs_up_before_removing(self) -> None:
        finding = self.diverged()
        removal = next(
            resolution
            for resolution in finding.resolutions
            if resolution.action == inventory.UNINSTALL
        )
        inventory.apply_resolution(removal, False)
        self.assertFalse((self.user_root() / SKILL).exists())
        backups = list((self.home / ".claude" / ".skills-backups").rglob("SKILL.md"))
        self.assertTrue(backups)
        self.assertIn("local edit", backups[0].read_text(encoding="utf-8"))

    def test_applying_uninstall_drops_the_receipt_entry(self) -> None:
        self.install_skill(self.user_root())
        inventory.apply_fix(
            inventory.Fix(inventory.UNINSTALL, self.user_root(), SKILL, "copy"), False
        )
        self.assertEqual({}, install.receipt_entries(self.user_root(), kind="skill"))

    def test_apply_fix_calls_uninstall_one_with_the_installer_argument_order(self) -> None:
        """name first, root second — the mirror of install_one(source, root)."""
        self.install_skill(self.user_root())
        seen = {}
        original = install.uninstall_one

        def spy(name, root, dry_run, **kwargs):
            seen["name"], seen["root"] = name, root
            return original(name, root, dry_run, **kwargs)

        install.uninstall_one = spy
        try:
            inventory.apply_fix(
                inventory.Fix(inventory.UNINSTALL, self.user_root(), SKILL, "copy"),
                False,
            )
        finally:
            install.uninstall_one = original
        self.assertEqual({"name": SKILL, "root": self.user_root()}, seen)

    def test_applying_forget_leaves_the_files_alone(self) -> None:
        installed = self.install_skill(self.user_root())
        message = inventory.apply_fix(
            inventory.Fix(inventory.FORGET, self.user_root(), SKILL, "copy"), False
        )
        self.assertIn("forgot", message)
        self.assertTrue((installed / "SKILL.md").is_file())
        self.assertEqual({}, install.receipt_entries(self.user_root(), kind="skill"))

    def test_reinstalling_a_name_with_no_source_tree_is_refused(self) -> None:
        with self.assertRaises(install.InstallError) as caught:
            inventory.apply_fix(
                inventory.Fix(inventory.REINSTALL, self.user_root(), "no-such", "copy"),
                False,
            )
        self.assertIn("not a bundled skill", str(caught.exception))

    def test_a_placement_removed_before_apply_reports_absent_not_an_error(self) -> None:
        finding = self.diverged()
        removal = next(
            resolution
            for resolution in finding.resolutions
            if resolution.action == inventory.UNINSTALL
        )
        install.remove_path(self.user_root() / SKILL)
        self.assertIn("absent", inventory.apply_resolution(removal, False)[0])

    def test_dry_run_changes_nothing_on_disk(self) -> None:
        finding = self.diverged()
        before = inventory.tree_digest(self.user_root() / SKILL)
        for resolution in finding.resolutions:
            for line in inventory.apply_resolution(resolution, True):
                self.assertTrue(
                    line.startswith("would") or line.startswith("unchanged"), line
                )
        self.assertEqual(before, inventory.tree_digest(self.user_root() / SKILL))

    def test_keeping_a_finding_carries_no_fixes(self) -> None:
        keep = next(
            resolution
            for resolution in self.diverged().resolutions
            if resolution.action == inventory.KEEP
        )
        self.assertEqual((), keep.fixes)
        self.assertEqual(inventory.NONE, keep.consequence)
        self.assertEqual([], inventory.apply_resolution(keep, False))


class DiffTests(Fixture):
    def test_diff_text_shows_the_changed_line(self) -> None:
        installed = self.install_skill(self.user_root())
        self.edit(installed)
        body = inventory.diff_text(
            install.SOURCE_ROOT / SKILL, installed, "checkout", "installed"
        )
        self.assertIn("+local edit", body)
        self.assertIn("@@", body)

    def test_diff_text_names_a_file_present_on_one_side_only(self) -> None:
        installed = self.install_skill(self.user_root())
        (installed / "extra.md").write_text("new\n", encoding="utf-8")
        body = inventory.diff_text(
            install.SOURCE_ROOT / SKILL, installed, "checkout", "installed"
        )
        self.assertIn("+++ only in installed: extra.md", body)

    def test_diff_text_caps_its_output(self) -> None:
        installed = self.install_skill(self.user_root())
        (installed / "SKILL.md").write_text(
            "\n".join("line %d" % index for index in range(500)), encoding="utf-8"
        )
        body = inventory.diff_text(
            install.SOURCE_ROOT / SKILL, installed, "checkout", "installed", max_lines=20
        )
        self.assertEqual(21, len(body.splitlines()))
        self.assertIn("more lines", body.splitlines()[-1])

    def test_diff_text_labels_a_binary_file_without_dumping_it(self) -> None:
        installed = self.install_skill(self.user_root())
        (install.SOURCE_ROOT / SKILL / "SKILL.md").read_bytes()
        (installed / "logo.bin").write_bytes(b"\xff\xfe\x00binary")
        source_copy = self.base / "source-copy"
        shutil.copytree(install.SOURCE_ROOT / SKILL, source_copy)
        (source_copy / "logo.bin").write_bytes(b"\x00\x01different")
        body = inventory.diff_text(source_copy, installed, "checkout", "installed")
        self.assertIn("binary or oversized file differs: logo.bin", body)
        self.assertNotIn("binary", body.replace("binary or oversized", ""))

    def test_identical_trees_have_no_differences(self) -> None:
        installed = self.install_skill(self.user_root())
        self.assertEqual(
            "no differences",
            inventory.diff_text(
                install.SOURCE_ROOT / SKILL, installed, "checkout", "installed"
            ),
        )


class ReportTests(Fixture):
    def test_report_json_is_serialisable_and_keys_are_pinned(self) -> None:
        self.edit(self.install_skill(self.user_root()))
        scanned = self.scan()
        report = json.loads(json.dumps(inventory.report_json(scanned, inventory.findings(scanned))))
        self.assertEqual(
            sorted(
                [
                    "schema_version", "collection", "version", "generated_at",
                    "roots", "missing_roots", "unreadable_receipts", "findings",
                ]
            ),
            sorted(report),
        )
        self.assertNotIn("placements", report)
        finding = report["findings"][0]
        self.assertEqual(
            sorted(["kind", "name", "severity", "detail", "paths", "resolutions"]),
            sorted(finding),
        )
        self.assertEqual(
            sorted(["action", "label", "consequence", "fixes"]),
            sorted(finding["resolutions"][0]),
        )
        self.assertEqual(
            sorted(["action", "root", "name", "mode"]),
            sorted(finding["resolutions"][0]["fixes"][0]),
        )

    def test_render_report_names_every_finding(self) -> None:
        import io

        self.edit(self.install_skill(self.user_root()))
        partial = self.install_skill(self.user_root(), OTHER)
        (partial / "SKILL.md").unlink()
        scanned = self.scan()
        stream = io.StringIO()
        inventory.render_report(scanned, inventory.findings(scanned), stream)
        text = stream.getvalue()
        for expected in (SKILL, OTHER, inventory.DIVERGED, inventory.INCOMPLETE,
                         "roots", "inconsistencies", "fix:"):
            self.assertIn(expected, text)

    def test_an_empty_machine_says_nothing_is_installed(self) -> None:
        import io

        stream = io.StringIO()
        scanned = self.scan()
        inventory.render_report(scanned, inventory.findings(scanned), stream)
        self.assertIn("nothing installed yet", stream.getvalue())

    def test_inventory_imports_without_textual(self) -> None:
        """The doctor is a scripted path: it may not need the dashboard."""
        code = (
            "import sys\n"
            "class Refuse:\n"
            "    def find_module(self, name, path=None):\n"
            "        if name == 'textual' or name.startswith('textual.'):\n"
            "            raise ImportError('textual is not available')\n"
            "        return None\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        return self.find_module(name, path)\n"
            "sys.meta_path.insert(0, Refuse())\n"
            "sys.path.insert(0, %r)\n"
            "import inventory\n"
            "scanned = inventory.scan(%r, [%r])\n"
            "print('placements', len(scanned.placements))\n"
            "print('textual-imported', 'textual' in sys.modules)\n"
            % (str(ROOT), str(self.home), str(self.project))
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=str(ROOT), text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("textual-imported False", result.stdout)


if __name__ == "__main__":
    unittest.main()
