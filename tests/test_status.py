"""Status reconciliation: receipt vs disk vs collection, and upstream drift."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

INSTALLER = ROOT / "install.py"
SKILL = "wow-addon-dev"
OTHER = "viz-driven-dev"


def _receipt(root: Path, skills: list[str], mode: str = "copy", version: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / install.RECEIPT_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "collection": "dm1681/skills",
                "version": install.VERSION if version is None else version,
                "skills": skills,
                "mode": mode,
                "installed_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


class RootStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.root = self.directory / "skills"
        self.root.mkdir(parents=True)

    def state_of(self, name: str) -> str:
        report = install.root_status(self.root)
        return next(item.state for item in report.skills if item.name == name)

    def test_a_matching_install_is_current(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        _receipt(self.root, [SKILL])
        self.assertEqual(install.CURRENT, self.state_of(SKILL))
        self.assertEqual([], install.root_status(self.root).actionable())

    def test_an_edited_install_is_drifted(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        _receipt(self.root, [SKILL])
        entrypoint = self.root / SKILL / "SKILL.md"
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8"
        )
        self.assertEqual(install.DRIFTED, self.state_of(SKILL))

    def test_a_receipt_entry_with_nothing_on_disk_is_missing(self) -> None:
        _receipt(self.root, [SKILL])
        self.assertEqual(install.MISSING, self.state_of(SKILL))

    def test_a_receipt_entry_outside_the_collection_is_an_orphan(self) -> None:
        """The state that went unnoticed for two releases on a real machine."""
        _receipt(self.root, ["orchestrate-olympus"])
        self.assertEqual(install.ORPHAN, self.state_of("orchestrate-olympus"))

    def test_an_install_absent_from_the_receipt_is_untracked(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        _receipt(self.root, [OTHER])
        self.assertEqual(install.UNTRACKED, self.state_of(SKILL))

    def test_drift_outranks_being_absent_from_the_receipt(self) -> None:
        """Bookkeeping must not mask the thing that needs doing.

        An untracked skill that also differs from the checkout has to report
        the difference: that is the state a reinstall would fix.
        """
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        _receipt(self.root, [OTHER])
        entrypoint = self.root / SKILL / "SKILL.md"
        entrypoint.write_text("replaced\n", encoding="utf-8")
        report = next(
            item for item in install.root_status(self.root).skills if item.name == SKILL
        )
        self.assertEqual(install.DRIFTED, report.state)
        self.assertIn("receipt", report.detail)

    def test_a_stale_receipt_version_is_noted(self) -> None:
        _receipt(self.root, [], version="0.0.1")
        report = install.root_status(self.root)
        self.assertTrue(any("0.0.1" in note for note in report.notes))

    def test_a_root_with_no_receipt_still_reports_what_is_installed(self) -> None:
        shutil.copytree(install.SOURCE_ROOT / SKILL, self.root / SKILL)
        report = install.root_status(self.root)
        self.assertFalse(report.managed)
        self.assertEqual(install.CURRENT, self.state_of(SKILL))


class VendoredDriftTests(unittest.TestCase):
    def test_every_vendored_skill_matches_its_recorded_upstream(self) -> None:
        """Guards the copy against being edited here instead of upstream."""
        self.assertEqual([], install.vendored_status())

    def test_the_hash_ignores_platform_line_endings(self) -> None:
        """A CRLF checkout must not read as drift.

        The vendored file is 45,958 bytes on Windows and fewer on Linux for
        identical content, so hashing raw bytes would report drift on one
        platform and nothing on the other.
        """
        entry = install.VENDORED_SKILLS[0]
        entrypoint = install.SOURCE_ROOT / entry.skill / entry.entrypoint
        text = install.vendored_upstream_text(entrypoint)
        self.assertIsNotNone(text)
        self.assertNotIn("\r", text)
        self.assertEqual(
            entry.sha256, hashlib.sha256(text.encode("utf-8")).hexdigest()
        )

    def test_an_edit_to_the_vendored_copy_is_detected(self) -> None:
        entry = install.VENDORED_SKILLS[0]
        entrypoint = install.SOURCE_ROOT / entry.skill / entry.entrypoint
        text = install.vendored_upstream_text(entrypoint)
        edited = text + "\na line that upstream does not have\n"
        self.assertNotEqual(
            entry.sha256, hashlib.sha256(edited.encode("utf-8")).hexdigest()
        )

    def test_removing_the_provenance_note_reads_as_drift(self) -> None:
        """The note is what tells the next reader not to edit this copy."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        noteless = directory / "SKILL.md"
        noteless.write_text("---\nname: x\n---\n\n# body\n", encoding="utf-8")
        self.assertIsNone(install.vendored_upstream_text(noteless))


class OriginStatusTests(unittest.TestCase):
    """Whether the checkout trails its remote, and whether that is knowable."""

    def test_an_unpacked_archive_is_unknown_not_behind(self) -> None:
        """A release archive has no .git, and that is not a finding.

        Reporting it as `behind` made every archive install fail the check
        forever while being perfectly current, which is the one place a
        SessionStart hook or CI job would gate on the exit code.
        """
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        status = install.checkout_behind_origin(directory)
        self.assertEqual(install.ORIGIN_UNKNOWN, status.state)
        self.assertIn("archive", status.detail)

    def test_unknown_does_not_count_as_work(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        with unittest.mock.patch.object(
            install,
            "checkout_behind_origin",
            lambda *a, **k: install.OriginStatus(install.ORIGIN_UNKNOWN, "no idea"),
        ):
            _, pending = install.status_lines([home], check_origin=True)
        self.assertFalse(pending)

    def test_behind_does_count_as_work(self) -> None:
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        with unittest.mock.patch.object(
            install,
            "checkout_behind_origin",
            lambda *a, **k: install.OriginStatus(install.ORIGIN_BEHIND, "3 behind"),
        ):
            _, pending = install.status_lines([home], check_origin=True)
        self.assertTrue(pending)


class StatusCommandTests(unittest.TestCase):
    def run_status(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--status", *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_a_clean_home_exits_zero(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        result = self.run_status("--home", str(directory))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("nothing to update", result.stdout)

    def test_work_to_do_exits_with_its_own_code(self) -> None:
        """Distinct from the error codes so a hook can tell them apart."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        root = directory / ".claude" / "skills"
        _receipt(root, [SKILL])  # recorded, never written to disk
        result = self.run_status("--home", str(directory))
        self.assertEqual(install.STATUS_ACTION_EXIT, result.returncode, result.stdout)
        self.assertIn(install.MISSING, result.stdout)
        self.assertNotIn(install.STATUS_ACTION_EXIT, (0, 1, 2, 130))


if __name__ == "__main__":
    unittest.main()
