#!/usr/bin/env python3
"""Validate collection metadata and every bundled skill."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# install.py is the one place VENDORED_SKILLS and the git-hardening env are
# already defined; importing it here means a skill added to that tuple is
# exempt from the version check in the same commit, instead of needing a
# second list kept in sync by hand.
sys.path.insert(0, str(ROOT))
import install  # noqa: E402

VENDORED_SKILL_NAMES = frozenset(entry.skill for entry in install.VENDORED_SKILLS)


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


SKILL_LINE_BUDGET = 150


def skill_warnings(skill_name: str, text: str) -> list[str]:
    """Non-fatal convention nudges: the entrypoint stays a lightweight guide.

    Vendored skills are silent here, and the reason is the same trap the
    version check above guards: `vendored_status` pins the upstream bytes by
    SHA256, so the only way to act on a nudge about one is to edit a file we
    do not own -- which registers as vendor drift, exactly the signal the hash
    exists to raise. A warning whose sole remedy is the thing the repo is
    built to detect is not advice, it is a trap, and a permanently-unfixable
    line in a clean run teaches people to skim past the ones that matter.
    Re-sync upstream instead; if the nudge is right, it is right there.
    """
    if skill_name in VENDORED_SKILL_NAMES:
        return []
    warnings: list[str] = []
    lines = len(text.splitlines())
    if lines > SKILL_LINE_BUDGET:
        warnings.append(
            f"skills/{skill_name}/SKILL.md is {lines} lines"
            f" (budget {SKILL_LINE_BUDGET}); move detail into references/ files"
            " the workflow loads on demand"
        )
    description = frontmatter(text).get("description", "")
    if description and "use when" not in description.lower():
        warnings.append(
            f'skills/{skill_name}/SKILL.md description has no "Use when ..." trigger'
            " phrasing; agents judge relevance from the description alone"
        )
    return warnings


def collect_warnings() -> list[str]:
    skills_root = ROOT / "skills"
    if not skills_root.is_dir():
        return []
    warnings: list[str] = []
    for skill in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        entrypoint = skill / "SKILL.md"
        if entrypoint.is_file():
            warnings.extend(
                skill_warnings(skill.name, entrypoint.read_text(encoding="utf-8"))
            )
    return warnings


def _release_git(repo: Path, *arguments: str) -> Optional[str]:
    """Run one git command against `repo`, or return None on any failure.

    Mirrors `checkout_behind_origin`'s closure in install.py: the same
    STATUS_GIT_ENV hardening (no credential prompt can block a validator run),
    and the same collapse of "no git binary", "not a repo", and "command
    failed" into one None so every caller has exactly one thing to check for.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **install.STATUS_GIT_ENV},
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _skills_match_head(repo: Path) -> bool:
    """Whether `skills/` in the working tree is exactly what HEAD committed.

    The one question that separates the release job from a developer: both can
    have HEAD sitting on a release tag, but the job's tree *is* the tagged
    state while the developer's holds the edit they are about to commit. That
    edit is the thing being validated, so it has to be diffed against the tag
    it changes -- not against the release before it, which would compare the
    edit with a state it never claimed to be.

    A failed command answers False, which routes to the ordinary "diff against
    the tag reachable from HEAD" path. Not being able to tell must never turn
    the check into the vacuous tag-against-itself comparison.
    """
    return _release_git(repo, "status", "--porcelain", "--", "skills") == ""


def latest_release_tag(repo: Path) -> Optional[str]:
    """The release tag to diff a skill against, or None to skip the check.

    Normally the newest tag reachable from HEAD. The exception is the run that
    matters most: the release workflow checks out the pushed `v*` tag itself,
    so the reachable tag *is* HEAD, every skill diffs clean against it, and the
    check would have been inert in the one job that gates a release. When HEAD
    carries a release tag and `skills/` is untouched beside it, the comparison
    that means anything is against the tag before it.

    None is the answer for every reason the bump check must go quiet instead
    of failing: no `git` on PATH, a release archive shipped with no `.git` at
    all, a shallow CI clone fetched without tags, or a checkout old enough to
    predate the first tag. Collapsing those into one sentinel keeps the caller
    from having to special-case any of them -- it just skips the check.

    Both probes pass `--tags`, and the first one is useless without it: every
    release tag in this repository is lightweight (`git tag v9.0.0`, and the
    ref the GitHub release API creates), while a bare `git describe
    --exact-match` considers annotated tags only. Without `--tags` the
    "is HEAD tagged" question always answered no, the HEAD^ step never ran,
    and the release job went back to diffing the tag against itself -- the
    exact inertness this function exists to avoid, restored silently.
    """
    if _release_git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        return None
    on_head = _release_git(
        repo, "describe", "--tags", "--exact-match", "--match", "v*", "HEAD"
    )
    start = "HEAD^" if on_head and _skills_match_head(repo) else "HEAD"
    return _release_git(repo, "describe", "--tags", "--abbrev=0", "--match", "v*", start)


def _has_untracked(repo: Path, relative: str) -> bool:
    """Whether `relative` holds a file git has never been told about.

    `git diff` cannot see an untracked file, and adding a `references/` file
    is the most ordinary way to extend a skill. AGENTS.md tells contributors
    to run this validator *before* committing, so without this probe the run
    that is meant to catch a missing version bump is exactly the run that
    cannot see the change that needs one.

    `--exclude-standard` so a gitignored build artefact does not count, and a
    failed command answers False for the same reason the rest of the check
    goes quiet: not being able to tell is not a finding.
    """
    listing = _release_git(repo, "ls-files", "--others", "--exclude-standard", "--", relative)
    return bool(listing)


def bump_errors(repo: Path, skills: list, vendored: frozenset) -> list[str]:
    """Skills whose files changed since the last release tag but whose
    `version:` did not.

    This is what makes the field self-enforcing instead of decorative: a
    version nobody is forced to bump drifts out of truth the first time a
    skill changes underneath it, and a stale-but-plausible-looking version is
    worse than no version, because it is a confident wrong answer instead of
    an honest missing one. Vendored skills are exempt -- they carry no
    version key at all (see the frontmatter check above), so there is nothing
    here for them to have forgotten to bump.
    """
    tag = latest_release_tag(repo)
    if tag is None:
        return []

    errors: list[str] = []
    for skill in skills:
        if skill.name in vendored:
            continue
        entrypoint = skill / "SKILL.md"
        if not entrypoint.is_file():
            continue  # already reported as missing above; nothing to diff
        relative = f"skills/{skill.name}"
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", tag, "--", relative],
            capture_output=True,
            env={**os.environ, **install.STATUS_GIT_ENV},
        )
        if diff.returncode not in (0, 1):
            continue  # git itself failed to answer; stay silent, not wrong
        if diff.returncode == 0 and not _has_untracked(repo, relative):
            continue  # unchanged since the tag
        old_text = _release_git(repo, "show", f"{tag}:{relative}/SKILL.md")
        if old_text is None:
            continue  # the skill did not exist at the tag; nothing to bump from
        old_version = frontmatter(old_text).get("version")
        new_version = frontmatter(entrypoint.read_text(encoding="utf-8")).get("version")
        if old_version == new_version:
            errors.append(
                f"skills/{skill.name} changed since {tag} but its version "
                f"({new_version or 'missing'}) did not -- bump the version key "
                f"in {relative}/SKILL.md"
            )
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        errors.append("VERSION must contain a valid MAJOR.MINOR.PATCH value")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md has no heading for {version}")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(
        r'^version = "([^"]+)"$', pyproject, re.MULTILINE
    )
    if project_version is None:
        errors.append("pyproject.toml has no project version")
    elif project_version.group(1) != version:
        errors.append("pyproject.toml project version must match VERSION")
    if not (ROOT / "uv.lock").is_file():
        errors.append("uv.lock is missing")
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"3\.\d+", python_version):
        errors.append(".python-version must contain a Python 3 minor version")

    skills_root = ROOT / "skills"
    skills = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not skills:
        errors.append("no skills found")
    for skill in skills:
        if not NAME.fullmatch(skill.name):
            errors.append(f"invalid skill directory name: {skill.name}")
        entrypoint = skill / "SKILL.md"
        if not entrypoint.is_file():
            errors.append(f"missing {entrypoint.relative_to(ROOT)}")
            continue
        text = entrypoint.read_text(encoding="utf-8")
        metadata = frontmatter(text)
        if metadata.get("name") != skill.name:
            errors.append(f"{entrypoint.relative_to(ROOT)} name must equal {skill.name}")
        if not metadata.get("description"):
            errors.append(f"{entrypoint.relative_to(ROOT)} requires a description")
        if skill.name in VENDORED_SKILL_NAMES:
            if "version" in metadata:
                errors.append(
                    f"{entrypoint.relative_to(ROOT)} is vendored and must not "
                    "carry a version key -- vendored_status hashes the "
                    "frontmatter against a pinned upstream SHA256, so a local "
                    "version key would register as drift the skill never had"
                )
        else:
            # Deliberately not named `version`: that name already holds the
            # collection's VERSION in this function, and rebinding it here
            # would leave every check added after this loop silently reading
            # the last skill's version instead of the collection's.
            skill_version = metadata.get("version")
            if not skill_version or not SEMVER.fullmatch(skill_version):
                errors.append(
                    f"{entrypoint.relative_to(ROOT)} requires a version key "
                    "matching MAJOR.MINOR.PATCH"
                )
        for path in skill.rglob("*"):
            if path.is_symlink():
                errors.append(f"skill must be self-contained; symlink found: {path.relative_to(ROOT)}")
            if path.is_file() and path.suffix == ".py":
                try:
                    ast.parse(
                        path.read_text(encoding="utf-8"),
                        filename=str(path),
                        feature_version=(3, 9),
                    )
                except SyntaxError as exc:
                    errors.append(f"invalid Python in {path.relative_to(ROOT)}: {exc}")

    errors.extend(bump_errors(ROOT, skills, VENDORED_SKILL_NAMES))

    for path in (ROOT / "install.py", ROOT / "scripts" / "validate_repo.py"):
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                feature_version=(3, 9),
            )
        except SyntaxError as exc:
            errors.append(f"invalid Python in {path.relative_to(ROOT)}: {exc}")
    return errors


def main() -> int:
    errors = validate()
    for warning in collect_warnings():
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    skill_count = sum(1 for path in (ROOT / "skills").iterdir() if path.is_dir())
    print(f"validated {skill_count} skill(s), collection version {(ROOT / 'VERSION').read_text().strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
