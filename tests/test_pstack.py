from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pstack_installer", ROOT / "install.py")
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


def write_upstream(checkout: Path, *relative: str, version: str = "") -> None:
    """Lay out a checkout the way cursor/plugins lays pstack out.

    Skills live one level below `pstack/skills/`, and the manifest that names
    the release sits outside `skills/` — which is the whole reason the byte
    verification covers the plugin directory rather than just its skills.
    """
    plugin = checkout / INSTALLER.PSTACK_SUBDIR
    for path in relative:
        skill_dir = plugin / "skills" / path
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_dir.name}\n---\n", encoding="utf-8"
        )
    manifest = plugin / INSTALLER.PSTACK_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"name": "pstack", "version": version or INSTALLER.PSTACK_VERSION}),
        encoding="utf-8",
    )


def fetch_writes(*relative: str, version: str = ""):
    """A `_run` stand-in that materializes an upstream tree on the fetch step."""

    def fake_run(command: list, cwd: Path, env=None) -> None:
        if command[1] == "fetch":
            write_upstream(cwd, *relative, version=version)

    return fake_run


def verified(head: str = INSTALLER.PSTACK_COMMIT):
    """Patch out the three checks that need a real git, leaving the logic."""
    return (
        mock.patch.object(INSTALLER.shutil, "which", return_value="/tools/git"),
        mock.patch.object(INSTALLER, "checkout_head", return_value=head),
        mock.patch.object(INSTALLER, "checkout_worktree_changes", return_value=""),
        mock.patch.object(INSTALLER, "checkout_content_mismatches", return_value=[]),
    )


class PstackFetchTests(unittest.TestCase):
    def test_fetch_pins_one_revision_of_the_monorepo(self) -> None:
        self.assertEqual(
            [
                ["git", "init", "--quiet", "--template="],
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "--depth",
                    "1",
                    "https://github.com/cursor/plugins.git",
                    "abc123",
                ],
                [
                    "git",
                    "-c",
                    "core.hooksPath=.git/no-hooks",
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "checkout",
                    "--quiet",
                    "--detach",
                    "FETCH_HEAD",
                ],
            ],
            INSTALLER.pstack_fetch_commands("abc123"),
        )

    def test_the_default_ref_is_pinned_rather_than_a_moving_branch(self) -> None:
        self.assertEqual(
            INSTALLER.pstack_fetch_commands()[1][-1], INSTALLER.PSTACK_REF
        )
        self.assertNotEqual(INSTALLER.PSTACK_REF, "main")

    def test_the_pin_is_a_full_commit_because_upstream_publishes_no_tags(self) -> None:
        """cursor/plugins has no tags, so the ref has to be the commit itself.

        `git fetch <url> <ref>` resolves the argument as a refspec and an
        abbreviated SHA is not one, so the constant has to carry all forty.
        """
        self.assertRegex(INSTALLER.PSTACK_REF, r"^[0-9a-f]{40}$")
        self.assertEqual(INSTALLER.PSTACK_REF, INSTALLER.PSTACK_COMMIT)

    def test_the_readable_half_of_the_pin_is_a_plugin_version(self) -> None:
        self.assertRegex(INSTALLER.PSTACK_VERSION, r"^\d+\.\d+\.\d+$")


class PstackSourceTests(unittest.TestCase):
    def test_sources_come_from_the_plugin_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "tdd", "teach")
            self.assertEqual(
                ["tdd", "teach"],
                [source.name for source in INSTALLER.pstack_skill_sources(checkout)],
            )

    def test_a_sibling_plugin_in_the_monorepo_is_not_installed(self) -> None:
        """The monorepo holds many plugins; only the named one is a source."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "tdd")
            other = checkout / "some-other-plugin" / "skills" / "not-ours"
            other.mkdir(parents=True)
            (other / "SKILL.md").write_text("---\nname: not-ours\n---\n", encoding="utf-8")
            self.assertEqual(
                ["tdd"],
                [source.name for source in INSTALLER.pstack_skill_sources(checkout)],
            )

    def test_the_benny_automations_are_outside_the_manifests_skills_pointer(self) -> None:
        """`plugin.json` points at ./skills/, and that is what installs."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "tdd")
            benny = (
                checkout
                / INSTALLER.PSTACK_SUBDIR
                / "automations"
                / "benny"
                / "skills"
                / "setup-benny"
            )
            benny.mkdir(parents=True)
            (benny / "SKILL.md").write_text(
                "---\nname: setup-benny\n---\n", encoding="utf-8"
            )
            self.assertEqual(
                ["tdd"],
                [source.name for source in INSTALLER.pstack_skill_sources(checkout)],
            )

    def test_a_nested_reference_skill_is_not_a_second_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "why", "why/references/sources")
            self.assertEqual(
                ["why"],
                [source.name for source in INSTALLER.pstack_skill_sources(checkout)],
            )

    def test_a_checkout_without_the_plugin_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(INSTALLER.InstallError, "no skills/ directory"):
                INSTALLER.pstack_skill_sources(Path(directory))

    def test_the_declared_version_is_read_from_the_plugin_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            write_upstream(checkout, "tdd", version="9.9.9")
            self.assertEqual(
                "9.9.9",
                INSTALLER.declared_version(
                    checkout, INSTALLER.PSTACK_SUBDIR, INSTALLER.PSTACK_MANIFEST
                ),
            )

    def test_an_unreadable_manifest_reads_as_no_version_rather_than_raising(self) -> None:
        """The caller decides whether a missing version is fatal, not the read."""
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            self.assertEqual(
                "",
                INSTALLER.declared_version(
                    checkout, INSTALLER.PSTACK_SUBDIR, INSTALLER.PSTACK_MANIFEST
                ),
            )
            manifest = checkout / INSTALLER.PSTACK_SUBDIR / INSTALLER.PSTACK_MANIFEST
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{not json", encoding="utf-8")
            self.assertEqual(
                "",
                INSTALLER.declared_version(
                    checkout, INSTALLER.PSTACK_SUBDIR, INSTALLER.PSTACK_MANIFEST
                ),
            )


class PstackInstallTests(unittest.TestCase):
    def test_install_fetches_then_copies_to_exact_resolved_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / ".agents" / "skills"
            patches = verified() + (
                mock.patch.object(
                    INSTALLER, "_run", side_effect=fetch_writes("setup-pstack")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                INSTALLER.install_pstack(
                    ["universal"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=lambda _: None,
                )
            self.assertTrue((destination / "setup-pstack" / "SKILL.md").is_file())

    def test_an_upstream_layout_change_is_reported_not_half_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / ".agents" / "skills"
            patches = verified() + (
                mock.patch.object(INSTALLER, "_run", side_effect=fetch_writes("tdd")),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaisesRegex(INSTALLER.InstallError, "setup-pstack"):
                    INSTALLER.install_pstack(
                        ["universal"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )
            self.assertFalse(destination.exists())

    def test_a_release_the_pin_does_not_name_stops_the_default_install(self) -> None:
        """The commit says where the fetch landed; the version says what it is.

        Upstream publishes no tags, so without this check the only thing
        identifying the installed release is a SHA nobody can read.
        """
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"
            patches = verified() + (
                mock.patch.object(
                    INSTALLER,
                    "_run",
                    side_effect=fetch_writes("setup-pstack", version="0.0.1"),
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaisesRegex(INSTALLER.InstallError, "declares version"):
                    INSTALLER.install_pstack(
                        ["claude"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )
            self.assertFalse(destination.exists())

    def test_a_named_ref_is_not_held_to_the_pinned_version(self) -> None:
        """`--pstack-ref main` asked for upstream, not for the pinned release."""
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"
            emitted: list = []
            patches = verified(head="a" * 40) + (
                mock.patch.object(
                    INSTALLER,
                    "_run",
                    side_effect=fetch_writes("setup-pstack", version="0.99.0"),
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                INSTALLER.install_pstack(
                    ["claude"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=emitted.append,
                    ref="main",
                )
            self.assertTrue((destination / "setup-pstack").is_dir())
            # The version still gets reported, because with a moving ref the
            # ref alone does not say what arrived.
            self.assertIn("plugin 0.99.0", "\n".join(emitted))

    def test_a_fetch_landing_off_the_pin_stops_the_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"
            patches = verified(head="f" * 40) + (
                mock.patch.object(
                    INSTALLER, "_run", side_effect=fetch_writes("setup-pstack")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaisesRegex(INSTALLER.InstallError, "but the checkout is on"):
                    INSTALLER.install_pstack(
                        ["claude"],
                        [destination],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )

    def test_unknown_agents_are_refused_before_anything_is_fetched(self) -> None:
        with mock.patch.object(
            INSTALLER,
            "_run",
            side_effect=AssertionError("an unknown agent must not reach the network"),
        ):
            with self.assertRaisesRegex(INSTALLER.InstallError, "unknown agent"):
                INSTALLER.install_pstack(["nope"], [ROOT], force=False, dry_run=False)

    def test_missing_git_is_actionable_and_names_this_flag(self) -> None:
        with mock.patch.object(INSTALLER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(INSTALLER.InstallError, r"--pstack requires git"):
                INSTALLER.install_pstack([], [ROOT], force=False, dry_run=False)

    def test_dry_run_prints_exact_commands_without_requiring_git(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(
                INSTALLER.shutil,
                "which",
                side_effect=AssertionError("dry run must not inspect installed tools"),
            ),
            contextlib.redirect_stdout(output),
        ):
            INSTALLER.install_pstack(
                ["all"], [ROOT / ".agents" / "skills"], force=False, dry_run=True
            )
        printed = output.getvalue()
        self.assertIn(
            "would run  git fetch --quiet --depth 1 "
            f"https://github.com/cursor/plugins.git {INSTALLER.PSTACK_REF}",
            printed,
        )
        self.assertIn(
            f"would copy all discovered pstack skills -> {ROOT / '.agents' / 'skills'}",
            printed,
        )

    def test_an_empty_ref_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaisesRegex(INSTALLER.InstallError, "empty value"):
            INSTALLER.install_pstack(
                ["claude"], [ROOT], force=False, dry_run=True, ref="  "
            )


class ExternalManifestTests(unittest.TestCase):
    """The record that says which collection put a skill in a root."""

    def test_an_install_records_what_it_placed_and_the_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"
            patches = verified() + (
                mock.patch.object(
                    INSTALLER, "_run", side_effect=fetch_writes("setup-pstack", "tdd")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                INSTALLER.install_pstack(
                    ["claude"],
                    [destination],
                    force=False,
                    dry_run=False,
                    emit=lambda _: None,
                )
            self.assertEqual(
                ["setup-pstack", "tdd"],
                INSTALLER.external_skill_names(destination, "pstack"),
            )
            entry = INSTALLER.read_external_manifest(destination)["pstack"]
            self.assertEqual(INSTALLER.PSTACK_REF, entry["ref"])
            self.assertEqual(INSTALLER.PSTACK_COMMIT, entry["commit"])

    def test_a_root_with_no_record_reads_as_empty_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual({}, INSTALLER.read_external_manifest(root))
            (root / INSTALLER.EXTERNAL_MANIFEST_FILE).write_text(
                "{not json", encoding="utf-8"
            )
            self.assertEqual({}, INSTALLER.read_external_manifest(root))
            self.assertEqual([], INSTALLER.external_skill_names(root, "pstack"))

    def test_another_collections_skill_is_a_conflict_and_its_own_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            INSTALLER.record_external_install(root, "pstack", ["tdd", "why"], "r", "c")
            self.assertEqual([], INSTALLER.external_conflicts(root, "pstack", ["tdd"]))
            self.assertEqual(
                [("tdd", "pstack")],
                INSTALLER.external_conflicts(root, "matt-skills", ["tdd", "implement"]),
            )

    def test_ownership_moves_to_whoever_wrote_the_directory_last(self) -> None:
        """Otherwise the winner's own next update looks like a conflict.

        A forced install replaces the other collection's copy on disk. Leaving
        the loser's claim behind would make every later update of the *winner*
        demand --force against a copy that is no longer there.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            INSTALLER.record_external_install(root, "pstack", ["tdd", "why"], "r", "c")
            INSTALLER.record_external_install(root, "matt-skills", ["tdd"], "r", "c")
            self.assertEqual(
                ["why"], INSTALLER.external_skill_names(root, "pstack")
            )
            self.assertEqual([], INSTALLER.external_conflicts(root, "matt-skills", ["tdd"]))
            # ...and asking to flip it back is still a stop.
            self.assertEqual(
                [("tdd", "matt-skills")],
                INSTALLER.external_conflicts(root, "pstack", ["tdd"]),
            )

    def test_a_bundled_skill_is_protected_from_an_external_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            INSTALLER.write_receipt(root, ["viz-driven-dev"], "copy", False)
            self.assertEqual(
                [("viz-driven-dev", "this collection")],
                INSTALLER.external_conflicts(root, "pstack", ["viz-driven-dev"]),
            )

    def test_a_conflict_stops_the_install_before_any_root_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            roots = [base / "one", base / "two"]
            for root in roots:
                root.mkdir()
            INSTALLER.record_external_install(roots[1], "matt-skills", ["tdd"], "r", "c")
            patches = verified() + (
                mock.patch.object(
                    INSTALLER, "_run", side_effect=fetch_writes("setup-pstack", "tdd")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaisesRegex(INSTALLER.InstallError, "already owns"):
                    INSTALLER.install_pstack(
                        ["claude"],
                        roots,
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )
            # The clean root is checked before the dirty one is written to, so
            # a conflict in the second leaves the first untouched.
            self.assertFalse((roots[0] / "setup-pstack").exists())

    def test_force_accepts_the_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "skills"
            destination.mkdir(parents=True)
            INSTALLER.record_external_install(
                destination, "matt-skills", ["tdd"], "r", "c"
            )
            patches = verified() + (
                mock.patch.object(
                    INSTALLER, "_run", side_effect=fetch_writes("setup-pstack", "tdd")
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                INSTALLER.install_pstack(
                    ["claude"],
                    [destination],
                    force=True,
                    dry_run=False,
                    emit=lambda _: None,
                )
            self.assertEqual(
                ["setup-pstack", "tdd"],
                INSTALLER.external_skill_names(destination, "pstack"),
            )


class LegacyRootTests(unittest.TestCase):
    """Roots installed before `.skills-external.json` existed.

    The commonest starting state by far: matt-skills shipped for releases with
    nothing writing a record, so a check that trusts the record alone fails
    open on exactly the upgrade path it exists for.
    """

    def legacy_matt_root(self, root: Path) -> None:
        """A root as an older release left it: files, marker, no record."""
        for name in ("setup-matt-pocock-skills", "tdd", "teach"):
            (root / name).mkdir(parents=True)
            (root / name / "SKILL.md").write_text(
                f"---\nname: {name}\ndisable-model-invocation: true\n---\n",
                encoding="utf-8",
            )

    def test_a_marker_attributes_a_root_that_predates_the_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.legacy_matt_root(root)
            self.assertEqual({}, INSTALLER.read_external_manifest(root))
            self.assertEqual(
                [("tdd", "matt-skills"), ("teach", "matt-skills")],
                INSTALLER.external_conflicts(root, "pstack", ["tdd", "teach", "why"]),
            )

    def test_a_legacy_root_is_not_half_installed_over(self) -> None:
        """The stop has to happen before the copy loop, not inside it.

        `tdd` sorts late, so without the marker fallback ~40 directories are
        copied before `install_one` refuses on a name it cannot explain.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.legacy_matt_root(root)
            patches = verified() + (
                mock.patch.object(
                    INSTALLER,
                    "_run",
                    side_effect=fetch_writes("architect", "setup-pstack", "tdd"),
                ),
            )
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                with self.assertRaisesRegex(INSTALLER.InstallError, "already owns"):
                    INSTALLER.install_pstack(
                        ["claude"],
                        [root],
                        force=False,
                        dry_run=False,
                        emit=lambda _: None,
                    )
            self.assertFalse((root / "architect").exists())
            self.assertFalse((root / "setup-pstack").exists())

    def test_a_legacy_collection_can_still_update_itself(self) -> None:
        """Its own unrecorded files must not read as somebody else's."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.legacy_matt_root(root)
            self.assertEqual(
                [], INSTALLER.external_conflicts(root, "matt-skills", ["tdd", "teach"])
            )


class UninstallOwnershipTests(unittest.TestCase):
    """The conflict message prescribes --uninstall; it has to actually work."""

    def owned_skills(self, root: Path, tool: str, *names: str) -> None:
        """One install placing several skills, as install_upstream records it.

        Recorded in a single call on purpose: the record is what one install
        put here, so a second call replaces it rather than adding to it.
        """
        for name in names:
            (root / name).mkdir(parents=True)
            (root / name / "SKILL.md").write_text(
                f"---\nname: {name}\n---\n", encoding="utf-8"
            )
        INSTALLER.record_external_install(root, tool, names, "r", "c")

    def test_an_externally_installed_skill_is_ours_to_remove(self) -> None:
        """It is absent from the receipt and matches no bundled skill.

        Without this it reads as a stranger's directory and --uninstall
        refuses, which would make the conflict error's own advice false.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.owned_skills(root, "pstack", "tdd")
            message = INSTALLER.uninstall_one("tdd", root, force=False, dry_run=False)
            self.assertIn("removed", message)
            self.assertFalse((root / "tdd").exists())

    def test_removing_it_clears_the_ownership_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.owned_skills(root, "pstack", "tdd", "why")
            INSTALLER.uninstall_one("tdd", root, force=False, dry_run=False)
            self.assertEqual(["why"], INSTALLER.external_skill_names(root, "pstack"))
            # ...so the install the conflict blocked now goes through.
            self.assertEqual(
                [], INSTALLER.external_conflicts(root, "matt-skills", ["tdd"])
            )

    def test_a_record_claiming_nothing_is_deleted_rather_than_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.owned_skills(root, "pstack", "tdd")
            INSTALLER.uninstall_one("tdd", root, force=False, dry_run=False)
            self.assertFalse((root / INSTALLER.EXTERNAL_MANIFEST_FILE).exists())

    def test_a_dry_run_removes_nothing_from_the_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.owned_skills(root, "pstack", "tdd")
            INSTALLER.uninstall_one("tdd", root, force=False, dry_run=True)
            self.assertEqual(["tdd"], INSTALLER.external_skill_names(root, "pstack"))


class VisibilityHandoverTests(unittest.TestCase):
    def test_a_visibility_choice_does_not_outlive_the_skill_it_was_about(self) -> None:
        """"Show me `tdd`" was said about the collection that just lost it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            INSTALLER.record_external_install(root, "matt-skills", ["tdd", "why"], "r", "c")
            INSTALLER.record_model_decisions([root], {"tdd": "enabled", "why": "enabled"})
            INSTALLER.record_external_install(root, "pstack", ["tdd"], "r", "c")
            self.assertEqual({"why": "enabled"}, INSTALLER.read_model_decisions([root]))


class ConflictSeparateFromForceTests(unittest.TestCase):
    """`--force` and "take another collection's name" are two questions.

    The dashboard says yes to the first so an external row can offer "update",
    and must not thereby say yes to the second.
    """

    def install(self, root: Path, **kwargs) -> None:
        patches = verified() + (
            mock.patch.object(
                INSTALLER, "_run", side_effect=fetch_writes("setup-pstack", "tdd")
            ),
        )
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            INSTALLER.install_pstack(
                ["claude"], [root], dry_run=False, emit=lambda _: None, **kwargs
            )

    def test_force_alone_no_longer_waives_the_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.mkdir(exist_ok=True)
            INSTALLER.record_external_install(root, "matt-skills", ["tdd"], "r", "c")
            with self.assertRaisesRegex(INSTALLER.InstallError, "already owns"):
                self.install(root, force=True, allow_conflicts=False)
            self.assertFalse((root / "setup-pstack").exists())

    def test_it_still_updates_its_own_files_with_conflicts_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.mkdir(exist_ok=True)
            self.install(root, force=True, allow_conflicts=False)
            # Second run replaces its own copies rather than refusing them.
            self.install(root, force=True, allow_conflicts=False)
            self.assertTrue((root / "setup-pstack" / "SKILL.md").is_file())

    def test_the_command_line_still_spells_both_with_one_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.mkdir(exist_ok=True)
            INSTALLER.record_external_install(root, "matt-skills", ["tdd"], "r", "c")
            self.install(root, force=True)
            self.assertEqual(
                ["setup-pstack", "tdd"],
                INSTALLER.external_skill_names(root, "pstack"),
            )


class PstackCommandLineTests(unittest.TestCase):
    def test_the_flag_defaults_to_off_and_is_a_tri_state(self) -> None:
        self.assertIsNone(INSTALLER.parser().parse_args([]).pstack)
        self.assertTrue(INSTALLER.parser().parse_args(["--pstack"]).pstack)
        self.assertFalse(INSTALLER.parser().parse_args(["--no-pstack"]).pstack)

    def test_a_ref_without_the_flag_it_belongs_to_is_refused(self) -> None:
        """Ignoring it would install a revision the command line did not name."""
        self.assertEqual(
            2, INSTALLER.main(["--pstack-ref", "main", "--non-interactive", "--dry-run"])
        )

    def test_the_registry_row_names_the_marker_skill_the_install_requires(self) -> None:
        tool = INSTALLER.external_tool("pstack")
        self.assertEqual("git", tool.requires)
        self.assertEqual(INSTALLER.PSTACK.marker, tool.marker)
        self.assertIn("pstack", INSTALLER.EXTERNAL_NAMES)

    def test_it_is_a_scripted_option_the_dashboard_does_not_carry(self) -> None:
        args = INSTALLER.parser().parse_args(["--pstack", "--interactive"])
        with self.assertRaisesRegex(INSTALLER.InstallError, "--pstack is a scripted"):
            INSTALLER.open_dashboard(args)

    def test_it_does_not_combine_with_uninstall(self) -> None:
        self.assertEqual(
            2, INSTALLER.main(["--uninstall", "--all-skills", "--pstack"])
        )


if __name__ == "__main__":
    unittest.main()
