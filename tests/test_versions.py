"""Per-skill `version:` frontmatter: the reader, the vendored exemption, and
the validator checks that keep the field from drifting into decoration.

A skill's version lives nowhere but its own SKILL.md -- there is no VERSION
file per skill and the installed copy carries no git history -- so
`skill_version` and `skill_is_vendored` are the only things standing between
"this field means something" and "this field is a string nobody reads."
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
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

SKILL = "wow-addon-dev"

# Mirrors the pattern scripts/validate_repo.py enforces, kept as a separate
# constant so a version-reading test failing here points at install.py's
# `skill_version`, not at whatever scripts/validate_repo.py happens to do.
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

# scripts/validate_repo.py is a script, not a package -- load it the way
# tests/test_validate_repo.py already does, so a version-check test failure
# points at the same module a human would open to fix it.
SPEC = importlib.util.spec_from_file_location(
    "repo_validator", ROOT / "scripts" / "validate_repo.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SkillVersionTests(unittest.TestCase):
    def test_reads_the_version_key_from_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_dir = Path(directory) / "demo"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo\ndescription: x\nversion: 2.3.4\n---\n\nbody\n",
                encoding="utf-8",
            )
            self.assertEqual("2.3.4", install.skill_version(skill_dir))

    def test_a_skill_with_no_version_key_reads_as_empty_not_zero(self) -> None:
        """"" has to mean "unknown", never "0.0.0" -- see skill_version's
        own docstring: a caller that conflated the two would report every
        skill that predates the field as older than everything else."""
        with tempfile.TemporaryDirectory() as directory:
            skill_dir = Path(directory) / "demo"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo\ndescription: x\n---\n\nbody\n", encoding="utf-8"
            )
            self.assertEqual("", install.skill_version(skill_dir))

    def test_a_directory_with_no_skill_md_reads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                "", install.skill_version(Path(directory) / "nonexistent")
            )

    def test_reads_the_installed_copy_not_only_the_checkout(self) -> None:
        """The question that matters is how ~/.claude/skills/<name> compares
        to skills/<name> -- so an installed copy edited after the fact must
        report its own version, not the checkout's."""
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / SKILL
            shutil.copytree(install.SOURCE_ROOT / SKILL, installed)
            entrypoint = installed / "SKILL.md"
            original = entrypoint.read_text(encoding="utf-8")
            edited = original.replace("version: 1.0.0", "version: 9.9.9")
            self.assertNotEqual(original, edited, "fixture assumption broke")
            entrypoint.write_text(edited, encoding="utf-8")
            self.assertEqual("9.9.9", install.skill_version(installed))
            self.assertEqual(
                "1.0.0", install.skill_version(install.SOURCE_ROOT / SKILL)
            )


class SkillIsVendoredTests(unittest.TestCase):
    def test_the_vendored_skill_is_vendored(self) -> None:
        self.assertTrue(install.skill_is_vendored("olympus-report-progress"))

    def test_a_first_party_skill_is_not_vendored(self) -> None:
        self.assertFalse(install.skill_is_vendored(SKILL))

    def test_an_unknown_name_is_not_vendored(self) -> None:
        self.assertFalse(install.skill_is_vendored("does-not-exist"))

    def test_exactly_the_vendored_skills_are_flagged_across_the_collection(self) -> None:
        vendored_names = {entry.skill for entry in install.VENDORED_SKILLS}
        flagged = {
            name for name in install.available_skills() if install.skill_is_vendored(name)
        }
        self.assertEqual(vendored_names, flagged)


class CollectionVersionCoverageTests(unittest.TestCase):
    """Behavioural checks against the real, shipped skills/ tree -- these
    fail the moment a skill loses its version key or the vendored copy
    gains one, which is exactly the regression the design calls out."""

    def test_every_non_vendored_bundled_skill_carries_a_semver_version(self) -> None:
        offenders = [
            name
            for name in install.available_skills()
            if not install.skill_is_vendored(name)
            and not SEMVER.fullmatch(install.skill_version(install.SOURCE_ROOT / name))
        ]
        self.assertEqual([], offenders)

    def test_the_vendored_skill_carries_no_local_version(self) -> None:
        entry = install.VENDORED_SKILLS[0]
        self.assertEqual("", install.skill_version(install.SOURCE_ROOT / entry.skill))

    def test_the_vendored_skill_still_reports_clean_with_no_version_key(self) -> None:
        """The regression test for the hash-covers-frontmatter trap: the
        pinned SHA256 is computed over the frontmatter too, so a vendored
        skill that predates (and must go on lacking) a `version:` key has
        to keep matching its recorded hash -- if this ever fails, either
        the upstream copy drifted for real, or someone added the key the
        install.py comments say never to add."""
        self.assertEqual([], install.vendored_status())

    def test_adding_a_version_key_to_the_vendored_frontmatter_would_register_as_drift(
        self,
    ) -> None:
        """Proves the trap the previous test guards, without touching the
        real file: splice a `version:` line into the same bytes
        `vendored_status` hashes and show the digest no longer matches the
        pinned SHA256. This is *why* constraint 2 (never add `version:` to
        skills/olympus-report-progress/SKILL.md) is load-bearing rather than
        cosmetic."""
        entry = install.VENDORED_SKILLS[0]
        entrypoint = install.SOURCE_ROOT / entry.skill / entry.entrypoint
        upstream = install.vendored_upstream_text(entrypoint)
        self.assertIsNotNone(upstream)
        poisoned = re.sub(r"\n---\n", "\nversion: 9.9.9\n---\n", upstream, count=1)
        self.assertIn("version: 9.9.9", poisoned)
        self.assertNotEqual(upstream, poisoned, "fixture assumption broke")
        digest = hashlib.sha256(poisoned.encode("utf-8")).hexdigest()
        self.assertNotEqual(entry.sha256, digest)


def _scaffold_repo(directory: Path, skills: dict) -> None:
    """A repo tree that satisfies every non-version check `validate()` runs,
    so a version-check test below fails for the version reason and not
    because CHANGELOG.md or uv.lock was missing.

    `skills` maps a skill directory name to the frontmatter line to append
    after `description:` -- typically `"version: X.Y.Z\\n"`, or `""` to
    carry no version key at all.
    """
    (directory / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (directory / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- initial\n", encoding="utf-8"
    )
    (directory / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (directory / "uv.lock").write_text("", encoding="utf-8")
    (directory / ".python-version").write_text("3.12\n", encoding="utf-8")
    (directory / "install.py").write_text("pass\n", encoding="utf-8")
    scripts_dir = directory / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "validate_repo.py").write_text("pass\n", encoding="utf-8")
    skills_dir = directory / "skills"
    skills_dir.mkdir()
    for name, extra in skills.items():
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        text = (
            "---\n"
            f"name: {name}\n"
            "description: Does a thing. Use when testing.\n"
            f"{extra}"
            "---\n\nbody\n"
        )
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")


class ValidatorVersionChecksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        original_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.directory
        self.addCleanup(setattr, VALIDATOR, "ROOT", original_root)

    def test_a_skill_with_no_version_key_is_an_error(self) -> None:
        _scaffold_repo(self.directory, {"demo-skill": ""})
        errors = VALIDATOR.validate()
        self.assertTrue(
            any(
                "demo-skill/SKILL.md requires a version key"
                in error.replace("\\", "/")
                for error in errors
            ),
            errors,
        )

    def test_a_malformed_version_is_an_error(self) -> None:
        _scaffold_repo(self.directory, {"demo-skill": "version: 1.0\n"})
        errors = VALIDATOR.validate()
        self.assertTrue(
            any(
                "demo-skill/SKILL.md requires a version key"
                in error.replace("\\", "/")
                for error in errors
            ),
            errors,
        )

    def test_a_valid_version_on_a_first_party_skill_raises_no_version_error(self) -> None:
        _scaffold_repo(self.directory, {"demo-skill": "version: 1.2.3\n"})
        errors = VALIDATOR.validate()
        self.assertEqual([], [error for error in errors if "demo-skill" in error])

    def test_a_version_key_on_the_vendored_skill_is_an_error(self) -> None:
        vendored_name = next(iter(VALIDATOR.VENDORED_SKILL_NAMES))
        _scaffold_repo(self.directory, {vendored_name: "version: 1.0.0\n"})
        errors = VALIDATOR.validate()
        self.assertTrue(
            any(
                f"{vendored_name}/SKILL.md is vendored and must not carry a "
                "version key" in error
                for error in errors
            ),
            errors,
        )

    def test_the_vendored_skill_with_no_version_key_raises_no_version_error(self) -> None:
        vendored_name = next(iter(VALIDATOR.VENDORED_SKILL_NAMES))
        _scaffold_repo(self.directory, {vendored_name: ""})
        errors = VALIDATOR.validate()
        self.assertEqual(
            [], [error for error in errors if vendored_name in error]
        )


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_all(repo: Path, message: str) -> None:
    """Commit the whole tree with an identity and no signing.

    Spelled out per invocation rather than written into the repo's config so
    the test cannot be steered by whatever the developer's global git config
    says -- a machine with `commit.gpgsign = true` would otherwise hang these
    on a passphrase prompt that no test runner can answer.
    """
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=validator test",
        "-c",
        "user.email=validator@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        message,
    )


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class BumpCheckTests(unittest.TestCase):
    """The check that makes `version:` self-enforcing instead of decorative.

    The design makes this check the precondition for adding the field at all:
    a version nobody is forced to bump is a confident wrong answer, which is
    worse than no field. It is also the check most able to fail silently --
    every way it goes quiet (no tag, no `.git`, a vendored name, a skill that
    did not exist at the tag) is a legitimate skip, so an implementation that
    has stopped firing entirely looks exactly like a clean run. Loosen the
    `git diff` probe by one return code and the whole thing goes dark with
    both gates still green, which is why each firing case is pinned here and
    not only the silent ones.
    """

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.vendored = next(iter(VALIDATOR.VENDORED_SKILL_NAMES))
        _scaffold_repo(
            self.repo,
            {"demo-skill": "version: 1.0.0\n", self.vendored: ""},
        )
        _git(self.repo, "init", "--quiet")
        _commit_all(self.repo, "initial")
        _git(self.repo, "tag", "v1.0.0")

    @property
    def skills(self) -> list:
        return sorted(path for path in (self.repo / "skills").iterdir() if path.is_dir())

    def entrypoint(self, name: str) -> Path:
        return self.repo / "skills" / name / "SKILL.md"

    def errors(self) -> list:
        return VALIDATOR.bump_errors(
            self.repo, self.skills, VALIDATOR.VENDORED_SKILL_NAMES
        )

    def test_an_untouched_collection_reports_nothing(self) -> None:
        self.assertEqual([], self.errors())

    def test_a_changed_skill_whose_version_stayed_put_is_named(self) -> None:
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        _commit_all(self.repo, "edit the body, forget the version")
        errors = self.errors()
        self.assertEqual(1, len(errors), errors)
        self.assertIn("skills/demo-skill", errors[0])
        self.assertIn("v1.0.0", errors[0])
        self.assertIn("1.0.0", errors[0])

    def test_bumping_the_version_clears_the_error(self) -> None:
        entrypoint = self.entrypoint("demo-skill")
        text = entrypoint.read_text(encoding="utf-8").replace(
            "version: 1.0.0", "version: 1.1.0"
        )
        entrypoint.write_text(text + "\nmore body\n", encoding="utf-8")
        _commit_all(self.repo, "edit the body and bump")
        self.assertEqual([], self.errors())

    def test_an_uncommitted_edit_beside_a_tagged_HEAD_is_still_checked(self) -> None:
        """AGENTS.md says to run the validator *before* committing, so the
        working tree is the state being checked -- and this is the case the
        "diff against the tag before HEAD" rule can swallow. Here HEAD sits on
        v1.0.0 (the minute after a release) with an edit on top: stepping back
        to the tag before v1.0.0 would compare that edit against a state it
        never claimed to be, and with no earlier tag to find it would skip the
        skill entirely."""
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        self.assertEqual("v1.0.0", VALIDATOR.latest_release_tag(self.repo))
        self.assertTrue(self.errors())

    def test_a_brand_new_untracked_file_counts_as_a_change(self) -> None:
        """`git diff` cannot see a file git has never been told about, and
        adding a `references/` page is the most ordinary way to extend a
        skill -- so without the untracked probe the commonest change is the
        one that escapes the requirement."""
        references = self.repo / "skills" / "demo-skill" / "references"
        references.mkdir()
        (references / "extra.md").write_text("more\n", encoding="utf-8")
        errors = self.errors()
        self.assertEqual(1, len(errors), errors)
        self.assertIn("skills/demo-skill", errors[0])

    def test_a_gitignored_file_inside_a_skill_is_not_a_change(self) -> None:
        (self.repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
        _commit_all(self.repo, "ignore logs")
        (self.repo / "skills" / "demo-skill" / "build.log").write_text(
            "noise\n", encoding="utf-8"
        )
        self.assertEqual([], self.errors())

    def test_a_release_tag_on_HEAD_diffs_against_the_tag_before_it(self) -> None:
        """The release workflow checks out the pushed tag itself. Diffing
        against the tag HEAD already carries compares a revision with itself,
        so every skill looks unchanged and the check is inert in the one run
        that gates a release."""
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        _commit_all(self.repo, "edit the body, forget the version")
        _git(self.repo, "tag", "v1.1.0")
        # Lightweight, like every release tag this repository has ever pushed
        # and like the ref the GitHub release API creates. A bare `git
        # describe --exact-match` ignores those, so the "is HEAD tagged"
        # question answered no and the step back to v1.0.0 never happened.
        self.assertEqual(
            "commit",
            subprocess.run(
                ["git", "-C", str(self.repo), "cat-file", "-t", "v1.1.0"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
        )
        self.assertEqual("v1.0.0", VALIDATOR.latest_release_tag(self.repo))
        errors = self.errors()
        self.assertEqual(1, len(errors), errors)
        self.assertIn("skills/demo-skill", errors[0])

    def test_the_vendored_skill_is_exempt_however_much_it_changed(self) -> None:
        entrypoint = self.entrypoint(self.vendored)
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nupstream moved on\n",
            encoding="utf-8",
        )
        _commit_all(self.repo, "resync the vendored copy")
        self.assertEqual([], self.errors())

    def test_a_skill_added_since_the_tag_has_no_version_to_bump_from(self) -> None:
        added = self.repo / "skills" / "new-skill"
        added.mkdir()
        (added / "SKILL.md").write_text(
            "---\nname: new-skill\ndescription: Does a thing. Use when testing.\n"
            "version: 1.0.0\n---\n\nbody\n",
            encoding="utf-8",
        )
        _commit_all(self.repo, "add a skill")
        self.assertEqual([], self.errors())

    def test_a_checkout_with_no_release_tag_is_silent(self) -> None:
        _git(self.repo, "tag", "-d", "v1.0.0")
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        self.assertIsNone(VALIDATOR.latest_release_tag(self.repo))
        self.assertEqual([], self.errors())

    def test_a_release_archive_with_no_git_at_all_is_silent(self) -> None:
        """The posture the whole check has to keep: an unpacked release
        tarball has no `.git`, and a validator that failed there would fail
        every install-from-archive for a reason the archive cannot fix."""
        shutil.rmtree(self.repo / ".git")
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        self.assertIsNone(VALIDATOR.latest_release_tag(self.repo))
        self.assertEqual([], self.errors())

    def test_the_check_reaches_validate_and_is_not_merely_defined(self) -> None:
        """A helper nothing calls is a helper that cannot enforce anything;
        this is the wire, not the logic."""
        entrypoint = self.entrypoint("demo-skill")
        entrypoint.write_text(
            entrypoint.read_text(encoding="utf-8") + "\nmore body\n", encoding="utf-8"
        )
        original = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.repo
        self.addCleanup(setattr, VALIDATOR, "ROOT", original)
        self.assertTrue(
            any("changed since v1.0.0" in error for error in VALIDATOR.validate())
        )


if __name__ == "__main__":
    unittest.main()
