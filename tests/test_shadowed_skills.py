"""A fork that keeps upstream's name, and the record that keeps it honest.

`skip` drops a path component of the upstream layout; shadowing drops a skill
by name, after discovery has flattened `skills/<category>/<name>/` down to
`<name>/`. The distinction is the whole reason this file exists: upstream files
`implement` under `engineering/`, so a skip entry naming the skill matches
nothing while looking exactly like it works.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("shadow_installer", ROOT / "install.py")
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


UPSTREAM_BODY = "---\nname: implement\n---\n\nUpstream's own text.\n"
UPSTREAM_SHA = hashlib.sha256(UPSTREAM_BODY.encode("utf-8")).hexdigest()


def shadow(**overrides):
    entry = INSTALLER.ShadowedSkill(
        skill="implement",
        tool=INSTALLER.MATT_SKILLS.tool,
        upstream="skills/engineering/implement/SKILL.md",
        ref=INSTALLER.MATT_SKILLS.ref,
        sha256=UPSTREAM_SHA,
    )
    return entry._replace(**overrides)


@contextlib.contextmanager
def upstream(body: str = UPSTREAM_BODY, name: str = "implement"):
    """A fetched checkout holding one skill under a category directory."""
    with tempfile.TemporaryDirectory() as raw:
        checkout = Path(raw)
        skill_dir = checkout / "skills" / "engineering" / name
        skill_dir.mkdir(parents=True)
        # newline="" so the bytes land exactly as written. The default
        # translates line endings on Windows, which would turn the CRLF
        # case below into CR-CR-LF and leave it testing nothing.
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8", newline="")
        yield checkout, [skill_dir]


class SkipCannotNameASkillTests(unittest.TestCase):
    """The defect shadowing exists to avoid, pinned so it cannot come back."""

    def test_a_skip_entry_naming_a_skill_matches_nothing(self) -> None:
        with upstream() as (checkout, _):
            sources = INSTALLER.collection_skill_sources(
                checkout, "test", "", ("implement",)
            )
        self.assertEqual(
            ["implement"],
            [source.name for source in sources],
            "skip matches the first path component, so naming a skill that "
            "lives under a category silently skips nothing",
        )

    def test_a_skip_entry_naming_the_category_does_match(self) -> None:
        with upstream() as (checkout, _):
            sources = INSTALLER.collection_skill_sources(
                checkout, "test", "", ("engineering",)
            )
        self.assertEqual([], sources)


class ApplyShadowsTests(unittest.TestCase):
    def test_a_shadowed_skill_is_dropped_from_what_gets_installed(self) -> None:
        with upstream() as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            kept, notes = INSTALLER.apply_shadows(
                INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
            )
        self.assertEqual([], kept)
        self.assertEqual(1, len(notes))
        self.assertIn("upstream unchanged", notes[0])

    def test_other_skills_are_untouched(self) -> None:
        with upstream(name="tdd") as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            # A named revision, so the missing fork is a note rather than the
            # stop asserted below; the point here is that `tdd` survives.
            kept, _ = INSTALLER.apply_shadows(INSTALLER.MATT_SKILLS, sources, "main")
        self.assertEqual(["tdd"], [source.name for source in kept])

    def test_a_shadow_for_another_collection_is_ignored(self) -> None:
        with upstream() as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(tool="pstack"),)
        ):
            kept, notes = INSTALLER.apply_shadows(
                INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
            )
        self.assertEqual(["implement"], [source.name for source in kept])
        self.assertEqual([], notes)


class UpstreamMovedTests(unittest.TestCase):
    """A pin that moves over a changed upstream is the failure being caught."""

    def test_a_default_install_stops_when_upstream_changed(self) -> None:
        changed = UPSTREAM_BODY + "\nA line upstream added later.\n"
        with upstream(body=changed) as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            with self.assertRaises(INSTALLER.InstallError) as caught:
                INSTALLER.apply_shadows(
                    INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
                )
        message = str(caught.exception)
        self.assertIn("upstream's implement changed", message)
        self.assertIn("skills/engineering/implement/SKILL.md", message)
        self.assertIn("SHADOWED_SKILLS", message)

    def test_a_named_revision_warns_instead_of_stopping(self) -> None:
        """The rule the version pin already follows, for the same reason."""
        changed = UPSTREAM_BODY + "\nA line upstream added later.\n"
        with upstream(body=changed) as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            kept, notes = INSTALLER.apply_shadows(
                INSTALLER.MATT_SKILLS, sources, "main"
            )
        self.assertEqual([], kept)
        self.assertEqual(1, len(notes))
        self.assertTrue(notes[0].startswith("warning:"))
        self.assertIn("diff v1.2.3..main", notes[0])

    def test_line_endings_alone_are_not_a_change(self) -> None:
        with upstream(body=UPSTREAM_BODY.replace("\n", "\r\n")) as (_, sources):
            with mock.patch.object(INSTALLER, "SHADOWED_SKILLS", (shadow(),)):
                kept, notes = INSTALLER.apply_shadows(
                    INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
                )
        self.assertEqual([], kept)
        self.assertIn("upstream unchanged", notes[0])

    def test_upstream_dropping_the_skill_stops_a_default_install(self) -> None:
        with upstream(name="tdd") as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            with self.assertRaises(INSTALLER.InstallError) as caught:
                INSTALLER.apply_shadows(
                    INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
                )
        self.assertIn("no longer ships implement", str(caught.exception))

    def test_an_unreadable_upstream_copy_is_not_read_as_unchanged(self) -> None:
        with upstream() as (_, sources), mock.patch.object(
            INSTALLER, "SHADOWED_SKILLS", (shadow(),)
        ):
            (sources[0] / "SKILL.md").unlink()
            with self.assertRaises(INSTALLER.InstallError) as caught:
                INSTALLER.apply_shadows(
                    INSTALLER.MATT_SKILLS, sources, INSTALLER.MATT_SKILLS.ref
                )
        self.assertIn("could not be read", str(caught.exception))


class RegistryTests(unittest.TestCase):
    def test_every_shadowed_skill_is_shipped_by_this_collection(self) -> None:
        for entry in INSTALLER.SHADOWED_SKILLS:
            with self.subTest(entry.skill):
                self.assertTrue(
                    (INSTALLER.SOURCE_ROOT / entry.skill / "SKILL.md").is_file(),
                    f"{entry.skill} is shadowed but this collection ships no "
                    "fork of it, so the name would simply go missing",
                )

    def test_every_shadowed_skill_names_a_known_collection(self) -> None:
        tools = {item.tool for item in INSTALLER.UPSTREAM_COLLECTIONS}
        for entry in INSTALLER.SHADOWED_SKILLS:
            with self.subTest(entry.skill):
                self.assertIn(entry.tool, tools)

    def test_the_fork_base_does_not_follow_the_pin(self) -> None:
        """The record has to survive the pin moving; that is its whole job.

        Recording the collection's current ref instead of a literal makes the
        two equal by construction, so the diff this prints degenerates to
        `X..X` and names nothing a reader could act on.
        """
        pins = {item.tool: item.ref for item in INSTALLER.UPSTREAM_COLLECTIONS}
        for entry in INSTALLER.SHADOWED_SKILLS:
            with self.subTest(entry.skill):
                moved = INSTALLER.MATT_SKILLS._replace(ref="v99.0.0")
                changed = UPSTREAM_BODY + "\nUpstream moved on.\n"
                with upstream(body=changed) as (_, sources):
                    with mock.patch.object(
                        INSTALLER, "SHADOWED_SKILLS", (shadow(ref=entry.ref),)
                    ):
                        with self.assertRaises(INSTALLER.InstallError) as caught:
                            INSTALLER.apply_shadows(moved, sources, "v99.0.0")
                self.assertIn(
                    f"diff {entry.ref}..v99.0.0", str(caught.exception)
                )
                self.assertNotEqual(
                    entry.ref,
                    "v99.0.0",
                    "the fork base moved with the pin instead of staying put",
                )
                self.assertIsNotNone(pins.get(entry.tool))

    def test_the_recorded_hash_is_a_sha256_digest(self) -> None:
        for entry in INSTALLER.SHADOWED_SKILLS:
            with self.subTest(entry.skill):
                self.assertRegex(entry.sha256, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
