#!/usr/bin/env python3
"""Validate collection metadata and every bundled skill."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
    """Non-fatal convention nudges: the entrypoint stays a lightweight guide."""
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

    for path in (
        ROOT / "install.py",
        ROOT / "skills_cli.py",
        ROOT / "scripts" / "validate_repo.py",
    ):
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
