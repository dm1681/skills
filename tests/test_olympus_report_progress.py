from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402

SKILL = "olympus-report-progress"
SKILL_ROOT = ROOT / "skills" / SKILL
UPSTREAM_COMMIT = "252f467"


class OlympusReportProgressPackagingTests(unittest.TestCase):
    """The skill is vendored from another repository, so pin what makes it one
    of this collection's skills rather than a loose copy."""

    def test_the_skill_is_discovered_like_every_other_bundled_skill(self) -> None:
        self.assertIn(SKILL, install.available_skills())

    def test_metadata_matches_its_directory_and_keeps_trigger_phrasing(self) -> None:
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(entrypoint.startswith("---\n"))
        self.assertIn(f"name: {SKILL}", entrypoint)
        description = install.skill_frontmatter_description(SKILL)
        self.assertTrue(description)
        # The validator warns without it and agents match on the description
        # alone, so the trigger phrasing is part of the packaging.
        self.assertIn("use when", description.lower())

    def test_the_vendored_copy_names_its_upstream_and_the_re_sync_rule(self) -> None:
        """A second copy drifts silently; the note is what makes it visible."""
        entrypoint = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(".claude/skills/olympus-report-progress/SKILL.md", entrypoint)
        self.assertIn(UPSTREAM_COMMIT, entrypoint)
        self.assertIn("Re-sync", entrypoint)

    def test_it_stays_out_of_a_machine_wide_default_install(self) -> None:
        """It needs a running Olympus server, so it is opt-in rather than
        pre-selected for every session on the machine."""
        self.assertFalse(install.skill_global_default(SKILL))
        self.assertEqual(
            "Report a checkout and session update to Olympus",
            install.skill_summary(SKILL),
        )

    def test_it_is_self_contained_with_no_pointer_into_the_olympus_checkout(self) -> None:
        """It runs in unrelated repositories, where Olympus's own docs are
        absent, so it must not route the workflow through a repo-local file."""
        self.assertEqual(
            ["SKILL.md"],
            sorted(path.name for path in SKILL_ROOT.iterdir() if path.is_file()),
        )
        self.assertFalse((SKILL_ROOT / "references").exists())


class OlympusReportProgressInstallTests(unittest.TestCase):
    def test_it_installs_through_install_one_and_reruns_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            source = install.SOURCE_ROOT / SKILL
            first = install.install_one(source, root, "copy", False, False)
            self.assertTrue(first.startswith("installed"), first)
            installed = root / SKILL
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "agents" / "openai.yaml").is_file())
            second = install.install_one(source, root, "copy", False, False)
            self.assertTrue(second.startswith("unchanged"), second)

    def test_a_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            line = install.install_one(
                install.SOURCE_ROOT / SKILL, root, "copy", False, True
            )
            self.assertTrue(line.startswith("would copy"), line)
            self.assertFalse((root / SKILL).exists())


if __name__ == "__main__":
    unittest.main()
