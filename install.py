#!/usr/bin/env python3
"""Install skills from this repository into supported agent directories."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, NamedTuple, Optional, Sequence, TextIO


REPO_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = REPO_ROOT / "skills"
GLOBAL_SOURCE = REPO_ROOT / "global" / "AGENTS.md"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

# Stamped into every file the installer owns outside a skills root, so a later
# run (or a human) can tell a generated pointer from hand-written guidance.
MANAGED_MARKER = "<!-- dm1681/skills: managed file -->"

# The install receipt is the ledger an uninstall reads back: one per skills
# root for the skills in it, one in $HOME for what this collection installed
# outside any root (managed instruction files, launcher shims).
RECEIPT_NAME = ".dm1681-skills.json"
RECEIPT_SCHEMA = 2
# Locations only, never contents. Without it a project or --target root cannot
# be found again short of walking the filesystem.
ROOT_REGISTRY_NAME = ".dm1681-skills-roots.json"

SHARED_AGENTS = {"universal", "agents", "codex", "cursor", "copilot"}
KNOWN_AGENTS = SHARED_AGENTS | {"claude", "all"}
# Install into every known skill root unless the caller narrows it. A shared-only
# default silently produces an install that Claude Code cannot see, because Claude
# reads ~/.claude/skills and never ~/.agents/skills.
DEFAULT_AGENTS = ["all"]
GRAPHIFY_PLATFORMS = {
    "universal": "agents",
    "agents": "agents",
    "codex": "codex",
    "cursor": "cursor",
    "copilot": "copilot",
    "claude": "claude",
}
MATT_SKILLS_SOURCE = "mattpocock/skills"
MATT_SKILLS_AGENTS = {
    "universal": "codex",
    "claude": "claude-code",
}


class InstallError(RuntimeError):
    """A user-actionable installation error."""


class ExternalTool(NamedTuple):
    """A skill this collection can install but does not own.

    Bundled skills are files in this checkout: installing one is a copy or a
    symlink, and its state is a byte comparison against `skills/<name>`. An
    external tool is somebody else's package with its own installer, so it
    honours `--scope` but never `--mode`, and the most this collection can say
    about its state is whether its marker directory is present. The marker is
    a separate field because an install may drop many skill directories under
    names that differ from the row's (matt-skills installs a dozen).

    `removal` is the honest half of the same asymmetry: a tool this collection
    only ever handed to somebody else's installer cannot be uninstalled here,
    and saying so beats a removal that silently misses most of what was placed.
    """

    name: str
    summary: str
    origin: str
    requires: str
    marker: str
    removal: str


EXTERNAL_TOOLS = (
    ExternalTool(
        name="graphify",
        summary="Turn any input into a persistent, queryable knowledge graph",
        origin="graphifyy on PyPI, installed and registered by its own CLI",
        requires="uv",
        marker="graphify",
        removal=(
            "not removable here: its own CLI placed the skill; "
            "uv tool uninstall graphifyy removes the package"
        ),
    ),
    ExternalTool(
        name="matt-skills",
        summary="mattpocock/skills engineering workflows",
        origin="mattpocock/skills on GitHub, staged and copied in by the skills CLI",
        requires="npx",
        marker="setup-matt-pocock-skills",
        removal=(
            "removes the skill directories recorded with origin=matt-skills "
            "in the install receipt"
        ),
    ),
)
EXTERNAL_NAMES = tuple(tool.name for tool in EXTERNAL_TOOLS)


def external_tool(name: str) -> ExternalTool:
    for tool in EXTERNAL_TOOLS:
        if tool.name == name:
            return tool
    raise InstallError(f"unknown external tool: {name}")


def is_terminal(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def should_open_dashboard(
    raw_args: list,
    args: argparse.Namespace,
    stdin: TextIO,
    stdout: TextIO,
    env: Mapping[str, str],
) -> bool:
    """Open the dashboard by default only when it is safe to take the screen.

    Passing any option means the caller has already decided what to install, so
    a scripted run stays on the plain-output path and never clears the screen.
    """
    if args.non_interactive:
        return False
    if args.interactive:
        return True
    if raw_args or env.get("CI"):
        return False
    return is_terminal(stdin) and is_terminal(stdout)


def available_skills() -> list[str]:
    if not SOURCE_ROOT.is_dir():
        raise InstallError(f"skills directory not found: {SOURCE_ROOT}")
    return sorted(
        path.name
        for path in SOURCE_ROOT.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def frontmatter_value(entrypoint: Path, key: str) -> str:
    """The value of one `key:` in a SKILL.md's frontmatter, or "".

    Deliberately naive about YAML: the frontmatter this repo validates is one
    `key: value` per line, and taking a dependency to read three lines would
    cost every scripted path its dependency-free promise.
    """
    if not entrypoint.is_file():
        return ""
    lines = entrypoint.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        candidate, separator, value = line.partition(":")
        if candidate.strip() == key and separator:
            return value.strip().strip('"').strip("'")
    return ""


def skill_frontmatter_description(name: str) -> str:
    """The `description:` from a bundled skill's frontmatter, or "".

    Every skill has one — it is what an agent matches on to decide whether to
    load the skill — so it is the reliable fallback when a skill ships no agent
    interface file.
    """
    return frontmatter_value(SOURCE_ROOT / name / "SKILL.md", "description")


def skill_summary(name: str) -> str:
    """Return one short line describing a bundled skill.

    Prefers the agent interface file's `short_description`, which is written to
    be one line. Falls back to the first sentence of the SKILL.md description,
    because a skill without an interface file is not a skill without a
    description, and "Bundled in this collection." tells a reader nothing they
    could choose on.
    """
    interface = SOURCE_ROOT / name / "agents" / "openai.yaml"
    if interface.is_file():
        for line in interface.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition(":")
            if key == "short_description" and separator:
                summary = value.strip().strip('"').strip("'")
                if summary:
                    return summary
    description = skill_frontmatter_description(name)
    if description:
        return first_clause(description)
    return "Bundled in this collection."


def first_clause(description: str, limit: int = 96) -> str:
    """The opening gist of a trigger description, as one short line.

    A `description:` is written for matching, not for reading: it states the
    gist, then a dash, then everything the gist glossed over, then "Use when"
    and the trigger phrasing. The first *sentence* is therefore not short — for
    one bundled skill it is 250 characters — so cut at the first clause break
    too, whichever comes first, and cap what survives at a word boundary. These
    lines sit in fixed-width UI rows and in the cloud session offer, where one
    long entry buries the next.
    """
    cut = re.search(r"(?<=[.!?])\s|\s[-–—]\s", description)
    clause = (description[: cut.start()] if cut else description).strip()
    if len(clause) <= limit:
        return clause
    return clause[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def skill_global_default(name: str) -> bool:
    """Whether the wizard pre-selects a skill for a machine-wide install.

    A narrow, domain-specific skill opts out with `global_default: false` in its
    agent interface file. It stays listed and selectable; it just is not checked
    by default, because loading it everywhere costs every unrelated session the
    skill's description for no benefit.
    """
    interface = SOURCE_ROOT / name / "agents" / "openai.yaml"
    if interface.is_file():
        for line in interface.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition(":")
            if key == "global_default" and separator:
                setting = value.strip().strip('"').strip("'").lower()
                return setting not in {"false", "no", "0", "off"}
    return True


def expand_agents(values: Iterable[str]) -> list[str]:
    requested = list(values) or list(DEFAULT_AGENTS)
    unknown = sorted(set(requested) - KNOWN_AGENTS)
    if unknown:
        raise InstallError(f"unknown agent: {', '.join(unknown)}")
    if "all" in requested:
        return ["universal", "claude"]
    normalized: list[str] = []
    for value in requested:
        canonical = "universal" if value in SHARED_AGENTS else value
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def resolve_roots(
    agents: Iterable[str],
    scope: str,
    home: Path,
    project_dir: Path,
    target: Optional[Path],
) -> list[Path]:
    if target is not None:
        return [target.expanduser().resolve()]

    base = home.expanduser() if scope == "user" else project_dir.expanduser().resolve()
    roots: list[Path] = []
    for agent in expand_agents(agents):
        if agent == "universal":
            root = base / ".agents" / "skills"
        elif agent == "claude":
            root = base / ".claude" / "skills"
        else:  # Defensive: expand_agents returns only canonical names.
            raise InstallError(f"unsupported canonical agent: {agent}")
        if root not in roots:
            roots.append(root)
    return roots


def graphify_platforms(values: Iterable[str]) -> list[str]:
    requested = list(values) or list(DEFAULT_AGENTS)
    unknown = sorted(set(requested) - KNOWN_AGENTS)
    if unknown:
        raise InstallError(f"unknown agent: {', '.join(unknown)}")
    if "all" in requested:
        return ["agents", "claude"]
    shared = set(requested) & SHARED_AGENTS
    use_generic_shared = bool(shared & {"universal", "agents"}) or len(shared) > 1
    platforms: list[str] = []
    for value in requested:
        platform = (
            "agents"
            if value in SHARED_AGENTS and use_generic_shared
            else GRAPHIFY_PLATFORMS[value]
        )
        if platform not in platforms:
            platforms.append(platform)
    return platforms


def graphify_install_commands(
    agents: Iterable[str], scope: str, executable: str = "graphify"
) -> list[list[str]]:
    commands: list[list[str]] = []
    for platform in graphify_platforms(agents):
        command = [executable, "install"]
        if scope == "project":
            command.append("--project")
        command.extend(("--platform", platform))
        commands.append(command)
    return commands


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise InstallError(
            f"command failed with exit code {result.returncode}: {shlex.join(command)}"
        )


def _find_graphify(uv: str, cwd: Path) -> Optional[str]:
    executable = shutil.which("graphify")
    if executable:
        return executable
    # NO_COLOR, not capture_output alone: uv styles this path even when its
    # output is a pipe, and the escape codes end up inside the Path, so the
    # directory never exists and this fallback silently finds nothing.
    result = subprocess.run(
        [uv, "tool", "dir", "--bin"],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "NO_COLOR": "1"},
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    bin_dir = Path(result.stdout.strip())
    for name in ("graphify.exe", "graphify"):
        candidate = bin_dir / name
        if candidate.is_file():
            return str(candidate)
    return None


def install_graphify(
    agents: Iterable[str],
    scope: str,
    project_dir: Path,
    dry_run: bool,
    emit: Callable[[str], None] = print,
    home: Optional[Path] = None,
) -> None:
    cwd = project_dir.expanduser().resolve() if scope == "project" else REPO_ROOT
    instruction_home = Path.home() if home is None else home
    uv_command = ["uv", "tool", "install", "--upgrade", "graphifyy"]
    if dry_run:
        emit(f"would run  {shlex.join(uv_command)}")
        for command in graphify_install_commands(agents, scope):
            location = f" (in {cwd})" if scope == "project" else ""
            emit(f"would run  {shlex.join(command)}{location}")
        for message in strip_appended_graphify(instruction_home, dry_run=True):
            emit(message)
        return

    if scope == "project" and not cwd.is_dir():
        raise InstallError(f"Graphify project directory does not exist: {cwd}")
    uv = shutil.which("uv")
    if not uv:
        raise InstallError(
            "--graphify requires uv; install it from https://docs.astral.sh/uv/ and rerun"
        )
    _run([uv, "tool", "install", "--upgrade", "graphifyy"], cwd)
    # Graphify's own documented fix for "graphify: command not found" after a
    # fresh install. It edits shell profiles, so it runs only when the tool is
    # genuinely missing from PATH rather than on every install.
    if not shutil.which("graphify"):
        _run([uv, "tool", "update-shell"], cwd)
    graphify = _find_graphify(uv, cwd)
    if not graphify:
        raise InstallError(
            "graphifyy was installed but the graphify executable could not be located. "
            "Run `uv tool update-shell`, open a new terminal, and rerun"
        )
    for command in graphify_install_commands(agents, scope, graphify):
        _run(command, cwd)
    for message in strip_appended_graphify(instruction_home, dry_run=False):
        emit(message)


def matt_skills_agents(agent_names: Iterable[str]) -> list[str]:
    """Map this installer's agent names to the skills CLI agent names."""
    requested = list(agent_names) or list(DEFAULT_AGENTS)
    unknown = sorted(set(requested) - KNOWN_AGENTS)
    if unknown:
        raise InstallError(f"unknown agent: {', '.join(unknown)}")
    if "all" in requested:
        requested = ["universal", "claude"]
    mapped: list[str] = []
    for agent_name in requested:
        canonical = "universal" if agent_name in SHARED_AGENTS else agent_name
        agent = MATT_SKILLS_AGENTS[canonical]
        if agent not in mapped:
            mapped.append(agent)
    return mapped


def matt_skills_install_command(
    agents: Iterable[str],
    executable: str = "npx",
) -> list[str]:
    """Build the official command used inside a temporary staging project."""
    command = [
        executable,
        "--yes",
        "skills@latest",
        "add",
        MATT_SKILLS_SOURCE,
        "--skill",
        "*",
    ]
    for agent in matt_skills_agents(agents):
        command.extend(("--agent", agent))
    command.extend(("--copy", "--yes"))
    return command


def require_npx() -> str:
    executable = shutil.which("npx")
    if executable:
        return executable
    raise InstallError(
        "--matt-skills requires npx (Node.js 18 or newer); install Node.js "
        "from https://nodejs.org/ and rerun"
    )


def _staged_matt_root(staging_dir: Path, canonical_agent: str) -> Path:
    if canonical_agent == "universal":
        return staging_dir / ".agents" / "skills"
    if canonical_agent == "claude":
        return staging_dir / ".claude" / "skills"
    raise InstallError(f"unsupported Matt skills staging agent: {canonical_agent}")


def _matt_source_roots(
    agents: Iterable[str], roots: list[Path], staging_dir: Path
) -> list[Path]:
    canonical_agents = expand_agents(agents)
    if len(canonical_agents) == len(roots):
        return [
            _staged_matt_root(staging_dir, agent) for agent in canonical_agents
        ]
    if len(roots) == 1:
        return [_staged_matt_root(staging_dir, canonical_agents[0])]
    raise InstallError("Matt skills destinations do not match the selected agents")


def install_matt_skills(
    agents: Iterable[str],
    roots: list[Path],
    force: bool,
    dry_run: bool,
    emit: Callable[[str], None] = print,
    executable: Optional[str] = None,
) -> None:
    """Stage upstream skills, then copy them into the exact resolved roots."""
    command = matt_skills_install_command(agents)
    if dry_run:
        emit(f"would run  {shlex.join(command)}")
        for root in roots:
            emit(f"would copy all discovered Matt Pocock skills -> {root}")
        return

    npx = executable or require_npx()
    with tempfile.TemporaryDirectory(prefix="mattpocock-skills-") as directory:
        staging_dir = Path(directory)
        _run(matt_skills_install_command(agents, npx), staging_dir)
        source_roots = _matt_source_roots(agents, roots, staging_dir)
        for source_root, destination_root in zip(source_roots, roots):
            sources = (
                sorted(
                    path
                    for path in source_root.iterdir()
                    if path.is_dir() and (path / "SKILL.md").is_file()
                )
                if source_root.is_dir()
                else []
            )
            if not any(path.name == "setup-matt-pocock-skills" for path in sources):
                raise InstallError(
                    "upstream install did not include setup-matt-pocock-skills"
                )
            for source in sources:
                emit(
                    install_one(
                        source,
                        destination_root,
                        "copy",
                        force,
                        False,
                        origin="matt-skills",
                    )
                )
            # The copies just overwrote any frontmatter edits from an earlier
            # review, so the recorded choices must be re-applied here or an
            # update silently re-hides every skill the user enabled.
            apply_model_decisions(destination_root, emit)


MODEL_INVOCATION_KEY = "disable-model-invocation"
MODEL_DECISIONS_FILE = ".skills-model-invocation.json"


def skill_is_model_hidden(skill_dir: Path) -> bool:
    """Whether this skill's frontmatter hides it from the model's skill list.

    Upstream collections (mattpocock/skills hides 23 of its 51) set
    `disable-model-invocation: true` to keep their descriptions out of every
    session's context. The cost is that a harness which routes slash commands
    through the model gets "that skill is not installed in this session" for
    a skill that is sitting right there on disk.
    """
    value = frontmatter_value(skill_dir / "SKILL.md", MODEL_INVOCATION_KEY)
    return value.lower() in ("true", "yes", "1")


def hidden_skills(root: Path) -> list[str]:
    """Installed skills in one root that are hidden from the model."""
    if not root.is_dir():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and (path / "SKILL.md").is_file()
        and skill_is_model_hidden(path)
    )


def set_model_invocation(skill_dir: Path, visible: bool) -> bool:
    """Toggle `disable-model-invocation` in an installed skill's frontmatter.

    Returns whether the file changed, so a caller can report only real edits.
    """
    entrypoint = skill_dir / "SKILL.md"
    if not entrypoint.is_file():
        raise InstallError(f"not a skill directory: {skill_dir}")
    lines = entrypoint.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise InstallError(f"{entrypoint} has no frontmatter to edit")
    closing = next(
        (i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        raise InstallError(f"{entrypoint} has an unterminated frontmatter block")
    block = [
        line
        for line in lines[1:closing]
        if line.partition(":")[0].strip() != MODEL_INVOCATION_KEY
    ]
    if not visible:
        block.append(f"{MODEL_INVOCATION_KEY}: true")
    updated = lines[:1] + block + lines[closing:]
    if updated == lines:
        return False
    entrypoint.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return True


def read_model_decisions(roots: Iterable[Path]) -> dict:
    """name -> "enabled" | "hidden", merged across the given roots."""
    decisions: dict = {}
    for root in roots:
        record = root / MODEL_DECISIONS_FILE
        if not record.is_file():
            continue
        try:
            loaded = json.loads(record.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(loaded, dict) and isinstance(loaded.get("decisions"), dict):
            decisions.update(loaded["decisions"])
    return decisions


def record_model_decisions(roots: Iterable[Path], updates: Mapping[str, str]) -> None:
    """Persist visibility choices beside each root's receipt.

    A file per root rather than one global record, because a root is the unit
    an external installer refreshes; whoever refreshes it can find the choices
    that apply to it without knowing which other roots exist.
    """
    for root in roots:
        if not root.is_dir():
            continue
        decisions = read_model_decisions([root])
        decisions.update(updates)
        _write_model_decisions(root, decisions)


def _write_model_decisions(root: Path, decisions: dict) -> None:
    """The write half of record_model_decisions, so forgetting can reuse it."""
    (root / MODEL_DECISIONS_FILE).write_text(
        json.dumps(
            {"schema_version": 1, "decisions": decisions},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def forget_model_decisions(
    roots: Iterable[Path], names: Iterable[str], dry_run: bool = False
) -> None:
    """Drop visibility choices for skills being removed.

    A recorded choice outlives the files it applies to otherwise, and would be
    re-applied to a fresh install the user never asked to hide.
    """
    if dry_run:
        return
    dropped = set(names)
    for root in roots:
        if not (root / MODEL_DECISIONS_FILE).is_file():
            continue
        decisions = read_model_decisions([root])
        remaining = {
            name: choice for name, choice in decisions.items() if name not in dropped
        }
        if remaining != decisions:
            _write_model_decisions(root, remaining)


def apply_model_decisions(root: Path, emit: Callable[[str], None] = print) -> None:
    """Re-apply this root's recorded visibility choices to the files on disk."""
    for name, choice in sorted(read_model_decisions([root]).items()):
        skill_dir = root / name
        if not (skill_dir / "SKILL.md").is_file():
            continue
        if set_model_invocation(skill_dir, visible=(choice == "enabled")):
            verb = "re-enabled for the model" if choice == "enabled" else "re-hidden"
            emit(f"{verb}: {skill_dir}")


def _same_file(left: Path, right: Path) -> bool:
    return filecmp.cmp(left, right, shallow=False)


def trees_equal(left: Path, right: Path) -> bool:
    if left.is_symlink():
        try:
            return left.resolve() == right.resolve()
        except OSError:
            return False
    if not left.is_dir() or not right.is_dir():
        return False
    comparison = filecmp.dircmp(left, right)
    if comparison.left_only or comparison.right_only or comparison.funny_files:
        return False
    if any(not _same_file(left / name, right / name) for name in comparison.common_files):
        return False
    return all(trees_equal(left / name, right / name) for name in comparison.common_dirs)


def destination_matches_mode(destination: Path, mode: str) -> bool:
    """Whether an existing destination is already the shape `mode` asks for.

    Equal contents are not enough to call an install current: a copy and a
    symlink can hold identical trees, so switching `--mode` has to reinstall
    even when nothing about the content changed.
    """
    return destination.is_symlink() if mode == "link" else not destination.is_symlink()


def stage_roots(args: argparse.Namespace, scope: str) -> list[Path]:
    return resolve_roots(args.agent, scope, args.home, args.project_dir, args.target)


def backup_path(root: Path, skill_name: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root.parent / ".skills-backups" / root.name
    candidate = backup_root / f"{skill_name}-{timestamp}"
    suffix = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = backup_root / f"{skill_name}-{timestamp}-{suffix}"
        suffix += 1
    return candidate


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def install_one(
    source: Path,
    root: Path,
    mode: str,
    force: bool,
    dry_run: bool,
    *,
    origin: str = "bundled",
    record: bool = True,
) -> str:
    destination = root / source.name
    # Read before anything moves: whether this name was already ours is what
    # decides if the backup taken below is somebody else's original or our own
    # earlier copy, and an uninstall may only restore the former.
    recorded = receipt_entries(root, kind="skill")
    exists = destination.exists() or destination.is_symlink()
    current = exists and destination_matches_mode(destination, mode)
    if current and trees_equal(destination, source):
        if record and source.name not in recorded:
            # Self-heals a v1 receipt and any install that predates the ledger:
            # nothing to write, but the entry has to exist to be removable.
            record_entry(
                root, source.name, "skill", mode=mode, origin=origin, dry_run=dry_run
            )
        return f"unchanged  {destination}"
    if exists and not force:
        actual = "link" if destination.is_symlink() else "copy"
        detail = (
            f"destination is a {actual}, not a {mode}"
            if trees_equal(destination, source)
            else "destination differs"
        )
        raise InstallError(
            f"{detail}: {destination} (rerun with --force to back up and replace it)"
        )

    backup = backup_path(root, source.name) if exists else None
    verb = "link" if mode == "link" else "copy"
    if dry_run:
        detail = f"; backup {backup}" if backup else ""
        return f"would {verb} {source} -> {destination}{detail}"

    root.mkdir(parents=True, exist_ok=True)
    if backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(backup))

    temporary = Path(tempfile.mkdtemp(prefix=f".{source.name}-", dir=root))
    remove_path(temporary)
    try:
        if mode == "link":
            temporary.symlink_to(source.resolve(), target_is_directory=True)
        else:
            shutil.copytree(source, temporary, copy_function=shutil.copy2)
        os.replace(temporary, destination)
    except Exception:
        remove_path(temporary)
        if backup is not None and not destination.exists() and not destination.is_symlink():
            shutil.move(str(backup), str(destination))
        raise
    if record:
        record_entry(
            root,
            source.name,
            "skill",
            mode=mode,
            origin=origin,
            backup=backup,
            foreign=None if backup is None else source.name not in recorded,
        )
    return f"installed  {destination}" + (f" (backup: {backup})" if backup else "")


# -- the ledger -------------------------------------------------------------
#
# One receipt per directory, holding both what the last run selected (`skills`,
# `mode`, `version` — the v1 keys, unchanged) and the durable inventory an
# uninstall reads (`entries`). An entry is keyed by skill name for a skill and
# by absolute path for a managed file or a shim, and remembers who installed it
# and what was moved aside to make room.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def receipt_path(root: Path) -> Path:
    return root / RECEIPT_NAME


def _upgrade_receipt(data: dict) -> dict:
    """v1 -> v2 in memory only; the file is rewritten on the next real write.

    Every name in a v1 `skills` list becomes an entry with kind="skill",
    origin="unknown", the receipt's mode/version, and no backups — provenance
    unknown, which is exactly what a v1 receipt can honestly claim.
    """
    upgraded = dict(data)
    entries = upgraded.get("entries")
    entries = dict(entries) if isinstance(entries, dict) else {}
    for name in upgraded.get("skills") or []:
        if not isinstance(name, str) or name in entries:
            continue
        entries[name] = {
            "kind": "skill",
            "origin": "unknown",
            "mode": upgraded.get("mode"),
            "version": upgraded.get("version"),
            "installed_at": upgraded.get("installed_at"),
            "backups": [],
        }
    upgraded["entries"] = entries
    upgraded["schema_version"] = RECEIPT_SCHEMA
    return upgraded


def read_receipt(root: Path) -> dict:
    """Parsed receipt for one directory, upgraded to the current schema.

    Returns {} when absent, unreadable, or not a JSON object — a corrupt
    receipt is never a reason to refuse to uninstall.
    """
    try:
        loaded = json.loads(receipt_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return _upgrade_receipt(loaded)


def receipt_entries(
    root: Path, kind: Optional[str] = None, origin: Optional[str] = None
) -> dict:
    """entry_id -> entry, filtered. Insertion-ordered."""
    entries = read_receipt(root).get("entries")
    if not isinstance(entries, dict):
        return {}
    return {
        entry_id: entry
        for entry_id, entry in entries.items()
        if isinstance(entry, dict)
        and (kind is None or entry.get("kind") == kind)
        and (origin is None or entry.get("origin") == origin)
    }


def _write_receipt_data(root: Path, data: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / (RECEIPT_NAME + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, receipt_path(root))


def record_entry(
    root: Path,
    entry_id: str,
    kind: str,
    *,
    mode: Optional[str] = None,
    origin: str = "bundled",
    backup: Optional[Path] = None,
    foreign: Optional[bool] = None,
    dry_run: bool = False,
) -> None:
    """Merge one installed thing into this directory's receipt.

    Idempotent per id: re-recording updates mode/version/installed_at and
    *appends* a backup rather than replacing the list — the backup history is
    what tells uninstall which copy predates this collection.
    """
    if dry_run:
        return
    data = read_receipt(root)
    data["schema_version"] = RECEIPT_SCHEMA
    data.setdefault("collection", "dm1681/skills")
    entries = data.get("entries")
    entries = dict(entries) if isinstance(entries, dict) else {}
    entry = entries.get(entry_id)
    entry = dict(entry) if isinstance(entry, dict) else {}
    backups = entry.get("backups")
    backups = list(backups) if isinstance(backups, list) else []
    if backup is not None:
        backups.append({"path": str(backup), "at": _now(), "foreign": foreign})
    entry.update(
        {
            "kind": kind,
            "origin": origin,
            "mode": mode,
            "version": VERSION,
            "installed_at": _now(),
            "backups": backups,
        }
    )
    entries[entry_id] = entry
    data["entries"] = entries
    _write_receipt_data(root, data)


def forget_entry(root: Path, entry_id: str, dry_run: bool = False) -> str:
    """Drop one entry from `entries` and from `skills`, without touching files."""
    data = read_receipt(root)
    entries = data.get("entries")
    entries = dict(entries) if isinstance(entries, dict) else {}
    skills = data.get("skills")
    skills = list(skills) if isinstance(skills, list) else []
    if entry_id not in entries and entry_id not in skills:
        return f"unchanged  {receipt_path(root)}"
    if dry_run:
        return f"would forget {entry_id} in {receipt_path(root)}"
    entries.pop(entry_id, None)
    data["entries"] = entries
    data["skills"] = [name for name in skills if name != entry_id]
    data["schema_version"] = RECEIPT_SCHEMA
    _write_receipt_data(root, data)
    return f"forgot     {entry_id} in {receipt_path(root)}"


def prune_root(root: Path, dry_run: bool = False) -> list:
    """Clean up a root that holds nothing of ours any more.

    A root holding somebody else's files keeps its directory; only this
    collection's bookkeeping is removed, and only once no entry and no skill
    directory is left to describe.
    """
    messages: list = []
    if not root.is_dir() or receipt_entries(root):
        return messages
    if any(
        (path / "SKILL.md").is_file()
        for path in root.iterdir()
        if path.is_dir() or path.is_symlink()
    ):
        return messages
    ours = (RECEIPT_NAME, MODEL_DECISIONS_FILE)
    for name in ours:
        path = root / name
        if not (path.exists() or path.is_symlink()):
            continue
        if dry_run:
            messages.append(f"would remove {path}")
            continue
        remove_path(path)
        messages.append(f"removed    {path}")
    remaining = [path for path in root.iterdir() if path.name not in ours]
    if dry_run:
        if not remaining:
            messages.append(f"would remove {root}")
        return messages
    try:
        root.rmdir()
    except OSError:
        return messages
    messages.append(f"removed    {root}")
    return messages


def write_receipt(root: Path, skills: list, mode: str, dry_run: bool) -> None:
    """Record this run's selection, keeping every entry the ledger already has.

    An entry for a skill outside this run — or one whose directory somebody
    has since deleted — survives on purpose: the ledger is what makes a stale
    record visible, and dropping it silently would erase the only evidence.
    """
    if dry_run:
        return
    data = read_receipt(root)
    entries = data.get("entries")
    entries = dict(entries) if isinstance(entries, dict) else {}
    for name in skills:
        if name in entries:
            continue
        entries[name] = {
            "kind": "skill",
            "origin": "bundled",
            "mode": mode,
            "version": VERSION,
            "installed_at": _now(),
            "backups": [],
        }
    data.update(
        {
            "schema_version": RECEIPT_SCHEMA,
            "collection": "dm1681/skills",
            "version": VERSION,
            "skills": list(skills),
            "mode": mode,
            "installed_at": _now(),
            "entries": entries,
        }
    )
    _write_receipt_data(root, data)


# -- the root registry ------------------------------------------------------


def registry_path(home: Path) -> Path:
    return home.expanduser() / ROOT_REGISTRY_NAME


def _read_registry(home: Path) -> list:
    try:
        loaded = json.loads(registry_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    if not isinstance(loaded, dict):
        return []
    roots = loaded.get("roots")
    if not isinstance(roots, list):
        return []
    return [item for item in roots if isinstance(item, str)]


def _write_registry(home: Path, roots: Sequence[str]) -> None:
    home = home.expanduser()
    home.mkdir(parents=True, exist_ok=True)
    target = registry_path(home)
    temporary = target.with_name(ROOT_REGISTRY_NAME + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "collection": "dm1681/skills",
                "roots": list(roots),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def record_root(home: Path, root: Path, dry_run: bool = False) -> None:
    """Remember one install location, so a later run can find it again."""
    if dry_run:
        return
    entry = str(Path(root).expanduser().resolve())
    known = _read_registry(home)
    if entry in known:
        return
    _write_registry(home, sorted(set(known) | {entry}))


def known_roots(home: Path) -> list:
    """Every recorded root that still exists, sorted and deduped.

    Prunes stale entries at read time only — it rewrites nothing, because a
    root that is missing today may be a mount that comes back tomorrow.
    """
    return [Path(item) for item in sorted(set(_read_registry(home))) if Path(item).is_dir()]


def forget_roots(home: Path, roots: Iterable[Path], dry_run: bool = False) -> list:
    known = _read_registry(home)
    dropping: set = set()
    for root in roots:
        dropping.add(str(root))
        dropping.add(str(Path(root).expanduser().resolve()))
    dropped = [Path(item) for item in known if item in dropping]
    if dropped and not dry_run:
        _write_registry(home, [item for item in known if item not in dropping])
    return dropped


def global_instruction_files(home: Path, mode: str) -> list[tuple[Path, str]]:
    """Return the (path, content) pairs that carry the user-level instructions.

    ``link`` writes pointer files that chain ~/.claude/CLAUDE.md ->
    ~/.agents/AGENTS.md -> this checkout, so the repository stays the only copy
    and edits here apply without reinstalling. ``copy`` inlines the text into
    ~/.agents/AGENTS.md for agents that do not resolve ``@path`` imports, and
    for machines where this checkout is absent.
    """
    if not GLOBAL_SOURCE.is_file():
        raise InstallError(f"missing global instructions: {GLOBAL_SOURCE}")
    source = GLOBAL_SOURCE.resolve()
    root = home.expanduser()
    shared = root / ".agents" / "AGENTS.md"
    claude = root / ".claude" / "CLAUDE.md"
    header = (
        f"{MANAGED_MARKER}\n"
        f"<!-- Generated by dm1681/skills. Edit {source} and reinstall; -->\n"
        f"<!-- edits made here are backed up and replaced on the next run. -->\n\n"
    )
    if mode == "copy":
        shared_body = GLOBAL_SOURCE.read_text(encoding="utf-8")
    else:
        shared_body = textwrap.dedent(
            f"""\
            # Global agent instructions

            Shared by every coding agent on this machine. The instructions are
            version controlled and imported from the checkout that owns them:

            @{source}

            Agents that do not resolve `@path` imports should read that file
            directly, or reinstall with `--global-instructions copy` to write
            the text into this file instead.
            """
        )
    claude_body = textwrap.dedent(
        f"""\
        # Global instructions

        Kept alongside the other agents' guidance so every tool on this machine
        loads the same instructions:

        @{shared}
        """
    )
    return [(shared, header + shared_body), (claude, header + claude_body)]


def _managed_file_state(path: Path, text: str) -> str:
    """'missing', 'current', or 'differs' for one managed instruction file."""
    if not (path.exists() or path.is_symlink()):
        return "missing"
    if path.is_file() and not path.is_symlink():
        try:
            if path.read_text(encoding="utf-8") == text:
                return "current"
        except UnicodeDecodeError:
            pass
    return "differs"


def global_instruction_status(home: Path, mode: str) -> list[tuple[Path, str]]:
    """(path, state) for each managed file, against what `mode` would write.

    Mode-sensitive on purpose: a home holding link-style pointers reads as
    `differs` when probed for copy mode, because installing in copy mode
    really would replace those files. Callers should present the state as
    the consequence of installing with `mode`, not as an absolute.
    """
    return [
        (path, _managed_file_state(path, text))
        for path, text in global_instruction_files(home, mode)
    ]


def _looks_managed(path: Path) -> bool:
    """Whether a file — or a backup of one — carries this collection's marker."""
    try:
        return path.read_text(encoding="utf-8").startswith(MANAGED_MARKER)
    except (OSError, UnicodeDecodeError):
        return False


def _write_managed_file(
    path: Path,
    text: str,
    dry_run: bool,
    *,
    mode: Optional[str] = None,
    home: Optional[Path] = None,
) -> str:
    if _managed_file_state(path, text) == "current":
        return f"unchanged  {path}"
    exists = path.exists() or path.is_symlink()
    backup = backup_path(path.parent, path.name) if exists else None
    if dry_run:
        detail = f"; backup {backup}" if backup else ""
        return f"would write {path}{detail}"

    path.parent.mkdir(parents=True, exist_ok=True)
    if backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup))
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        remove_path(temporary)
        if backup is not None and not path.exists() and not path.is_symlink():
            shutil.move(str(backup), str(path))
        raise
    # These files live outside every skills root, so their ledger is the one in
    # $HOME. `foreign` is decided by the marker: a backup without it is what the
    # user had before this collection ever wrote here.
    record_entry(
        (home or path.parent.parent).expanduser(),
        str(path),
        "managed-file",
        mode=mode,
        backup=backup,
        foreign=None if backup is None else not _looks_managed(backup),
    )
    return f"installed  {path}" + (f" (backup: {backup})" if backup else "")


def install_global_instructions(home: Path, mode: str, dry_run: bool) -> list[str]:
    return [
        _write_managed_file(path, text, dry_run, mode=mode, home=home)
        for path, text in global_instruction_files(home, mode)
    ]


# -- discovery: what is installed, and what a removal would find -----------
#
# Nothing in this section writes. It is the single place that lists what is on
# disk, so `--status`, the manage pane, and anything built on top read one
# description of the world rather than three that can disagree.


class Backup(NamedTuple):
    path: Path
    at: str  # ISO from the receipt, or the stamp parsed out of the directory name
    foreign: Optional[bool]  # None when provenance is unknown


class Installed(NamedTuple):
    """One thing this collection put somewhere, as a removal would see it.

    `mode` is what the receipt recorded and `shape` is what is on disk right
    now; `origin` is who installed it and `bundled` is whether a source tree
    exists here to compare against. Four fields rather than two, because a
    matt-skills copy is not a bundled skill and a link is not a copy, and
    conflating either pair produces a confident wrong answer.
    """

    kind: str  # "skill" | "managed-file" | "shim" | "external"
    name: str
    path: Path  # what a removal would act on
    root: Path  # the receipt-bearing directory
    mode: Optional[str]
    shape: Optional[str]  # "link" | "copy" on disk right now, or None
    origin: str  # bundled | matt-skills | graphify | unknown
    bundled: bool
    recorded: bool
    backups: list  # list[Backup], oldest first
    detail: str  # one honest line, already written for a human


BACKUP_STAMP = "%Y%m%dT%H%M%SZ"
# What that format renders to: 20260817T120000Z. backup_path may append a
# "-1" collision suffix after it, so the stamp is read by width.
BACKUP_STAMP_WIDTH = 16


def known_backups(root: Path, entry_id: str) -> list:
    """Backups this collection recorded for one entry, oldest first, filtered
    to those still on disk."""
    entry = receipt_entries(root).get(entry_id) or {}
    found = []
    for record in entry.get("backups") or []:
        if not isinstance(record, dict) or not record.get("path"):
            continue
        path = Path(str(record["path"]))
        if not (path.exists() or path.is_symlink()):
            continue
        found.append(Backup(path, str(record.get("at") or ""), record.get("foreign")))
    return found


def disk_backups(root: Path, entry_id: str) -> list:
    """Backups found beside `root`, oldest first, with unknown provenance.

    For a managed file, `root` is the file's parent and `entry_id` its name;
    that is where backup_path puts them.
    """
    backup_root = root.parent / ".skills-backups" / root.name
    if not backup_root.is_dir():
        return []
    found = []
    for path in backup_root.glob(f"{entry_id}-*"):
        stamp = path.name[len(entry_id) + 1 :][:BACKUP_STAMP_WIDTH]
        try:
            at = datetime.strptime(stamp, BACKUP_STAMP).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        found.append((at, path))
    return [
        Backup(path, at.isoformat(), None)
        for at, path in sorted(found, key=lambda item: (item[0], str(item[1])))
    ]


def restorable_backup(root: Path, entry_id: str, kind: str = "skill") -> tuple:
    """(chosen, note) — what may legitimately be moved back into place.

    A skill is never auto-restored from an unrecorded candidate: it is just as
    likely an older copy of our own skill, and restoring that would leave our
    files behind after an "uninstall". A managed file can be judged on its
    contents instead, because ours carry MANAGED_MARKER and the user's do not.
    """
    known = known_backups(root, entry_id)
    foreign = [backup for backup in known if backup.foreign is True]
    if foreign:
        return foreign[-1], "recorded pre-install original"
    if kind == "managed-file":
        managed = Path(entry_id)
        candidates = disk_backups(managed.parent, managed.name)
    else:
        candidates = disk_backups(root, entry_id)
    recorded_paths = {backup.path for backup in known}
    extra = [backup for backup in candidates if backup.path not in recorded_paths]
    if kind == "managed-file":
        outside = [backup for backup in extra if not _looks_managed(backup.path)]
        if outside:
            return outside[0], "oldest backup that this collection did not write"
        if extra:
            return None, "every backup here carries this collection's marker"
        return None, "no pre-install original was recorded"
    if extra:
        return None, (
            f"{len(extra)} backup(s) exist but no receipt records which predate "
            "this collection; restore one explicitly with --restore-from PATH"
        )
    return None, "no pre-install original was recorded"


def discover_skills(roots: Sequence[Path]) -> list:
    """Every skill this collection can see in the given roots.

    The union of receipt entries and directories holding a SKILL.md, so a
    directory nobody recorded is still listed (and removable with
    --unrecorded), and an entry whose files are gone is still listed (so the
    stale record can be cleaned).
    """
    bundled = set(available_skills()) if SOURCE_ROOT.is_dir() else set()
    items = []
    for root in roots:
        entries = receipt_entries(root, kind="skill")
        names = set(entries)
        if root.is_dir():
            names.update(
                path.name
                for path in root.iterdir()
                if (path.is_dir() or path.is_symlink()) and (path / "SKILL.md").is_file()
            )
        for name in sorted(names):
            entry = entries.get(name) or {}
            destination = root / name
            present = destination.exists() or destination.is_symlink()
            if not present:
                detail = "recorded, but nothing on disk"
            elif not entry:
                detail = "UNRECORDED"
            else:
                chosen, note = restorable_backup(root, name)
                detail = "original recoverable" if chosen else note
            items.append(
                Installed(
                    kind="skill",
                    name=name,
                    path=destination,
                    root=root,
                    mode=entry.get("mode"),
                    shape=(
                        None
                        if not present
                        else "link"
                        if destination.is_symlink()
                        else "copy"
                    ),
                    origin=str(entry.get("origin") or "unknown"),
                    bundled=name in bundled,
                    recorded=bool(entry),
                    backups=known_backups(root, name),
                    detail=detail,
                )
            )
    return items


def discover_managed_files(home: Path) -> list:
    """The managed instruction files that exist in this home."""
    home = home.expanduser()
    recorded = receipt_entries(home, kind="managed-file")
    items = []
    # Probed with "link" only because the two paths do not depend on the mode.
    for path, _text in global_instruction_files(home, "link"):
        if not (path.exists() or path.is_symlink()):
            continue
        entry = recorded.get(str(path)) or {}
        if not _looks_managed(path):
            detail = "hand-edited since install"
        else:
            chosen, note = restorable_backup(home, str(path), "managed-file")
            detail = "original recoverable" if chosen else note
        items.append(
            Installed(
                kind="managed-file",
                name=str(path),
                path=path,
                root=home,
                mode=entry.get("mode"),
                shape="link" if path.is_symlink() else "copy",
                origin=str(entry.get("origin") or "unknown"),
                bundled=False,
                recorded=bool(entry),
                backups=known_backups(home, str(path)),
                detail=detail,
            )
        )
    return items


def discover_shims(bin_dir: Path) -> list:
    """The launcher shims present in one directory, and whose they are."""
    import skills_cli

    items = []
    for path, content, _newline, _executable in skills_cli.shims(REPO_ROOT, bin_dir):
        if not path.is_file():
            continue
        try:
            ours = path.read_text(encoding="utf-8") == content
        except (OSError, UnicodeDecodeError):
            ours = False
        items.append(
            Installed(
                kind="shim",
                name=str(path),
                path=path,
                root=bin_dir,
                mode=None,
                shape="copy",
                origin="bundled",
                bundled=False,
                recorded=ours,
                detail=(
                    "written by this checkout" if ours else "written from another checkout"
                ),
                backups=[],
            )
        )
    return items


def discover_external(roots: Sequence[Path]) -> list:
    """One row per external tool whose marker directory is present anywhere."""
    items = []
    for tool in EXTERNAL_TOOLS:
        present = [
            root
            for root in roots
            if (root / tool.marker).exists() or (root / tool.marker).is_symlink()
        ]
        if not present:
            continue
        _removable, notes = external_removal_plan(tool.name, present)
        items.append(
            Installed(
                kind="external",
                name=tool.name,
                path=present[0] / tool.marker,
                root=present[0],
                mode=None,
                shape=None,
                origin=tool.name,
                bundled=False,
                # Presence is the marker directory, which is all this collection
                # can honestly claim about somebody else's package; whether any
                # of it is removable here is external_removal_plan's answer.
                recorded=True,
                backups=[],
                detail=notes[0],
            )
        )
    return items


def discover(
    roots: Sequence[Path], home: Path, bin_dir: Optional[Path] = None
) -> list:
    """Everything installed, in reading order. bin_dir=None skips shims."""
    items = list(discover_skills(roots))
    items.extend(discover_managed_files(home))
    if bin_dir is not None:
        items.extend(discover_shims(bin_dir))
    items.extend(discover_external(roots))
    return items


def format_status(items: Sequence[Installed]) -> str:
    """Plain text, grouped by kind, one aligned line per item."""
    if not items:
        return "nothing from this collection was found in the scanned locations"
    # A skill is named; a managed file or a shim *is* a path, and repeating its
    # directory in the root column would say the same thing twice.
    named = ("skill", "external")
    rows = [
        (
            item,
            item.name if item.kind in named else str(item.path),
            str(item.root) if item.kind in named else "",
        )
        for item in items
    ]
    label_width = max(len(label) for _item, label, _root in rows)
    root_width = max(len(root) for _item, _label, root in rows)
    lines = []
    for kind in ("skill", "managed-file", "shim", "external"):
        for item, label, root in rows:
            if item.kind != kind:
                continue
            lines.append(
                (
                    "%-12s %-*s %-6s %-*s %s"
                    % (
                        item.kind,
                        label_width,
                        label,
                        item.shape or "",
                        root_width,
                        root,
                        item.detail,
                    )
                ).rstrip()
            )
    return "\n".join(lines)


# -- removal ----------------------------------------------------------------


def uninstall_one(
    name: str,
    root: Path,
    dry_run: bool,
    *,
    restore: bool = True,
    keep_backup: bool = True,
    allow_unrecorded: bool = False,
    restore_from: Optional[Path] = None,
) -> str:
    """Remove one installed skill, restoring what it replaced when it may.

    Absent is not an error: an idempotent uninstall has to be able to say so,
    and a second run after a manual delete should agree with the first.
    """
    destination = root / name
    exists = destination.exists() or destination.is_symlink()
    recorded = name in receipt_entries(root, kind="skill")
    if exists and not recorded and not allow_unrecorded:
        raise InstallError(
            f"{destination} is not recorded as installed by this collection "
            "(rerun with --unrecorded to remove it anyway)"
        )
    if not exists:
        forget_entry(root, name, dry_run)
        return f"absent     {destination}"

    chosen, note = restorable_backup(root, name)
    if restore_from is not None:
        source = Path(restore_from).expanduser()
        if not (source.exists() or source.is_symlink()):
            raise InstallError(f"backup to restore does not exist: {source}")
        chosen, note = Backup(source, "", None), "restored from --restore-from"
    if not restore:
        chosen, note = None, "left in .skills-backups (--no-restore)"

    is_link = destination.is_symlink()
    backup = backup_path(root, name) if (keep_backup and not is_link) else None
    if dry_run:
        message = f"would remove {destination}"
        if backup is not None:
            message += f"; back up to {backup}"
        message += f"; restore {chosen.path}" if chosen is not None else f"; {note}"
        return message

    # Ordered so a failure never leaves a hole: the destination is vacated
    # exactly once, and only then does anything move back into it.
    if is_link:
        destination.unlink()
    elif backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(backup))
    else:
        remove_path(destination)
    if chosen is not None:
        # Moved, not copied, mirroring install_one, which moved it out.
        shutil.move(str(chosen.path), str(destination))
    forget_entry(root, name, False)
    forget_model_decisions([root], [name])

    parts = [f"removed    {destination}"]
    if is_link:
        parts.append("(link; nothing to back up)")
    elif backup is not None:
        parts.append(f"(backup: {backup})")
    if chosen is not None:
        parts.append(f"(restored: {chosen.path})")
    else:
        parts.append(f"({note})")
    return " ".join(parts)


def relink_one(root: Path, name: str, dry_run: bool) -> str:
    """Point one installed skill back at this checkout."""
    return install_one(SOURCE_ROOT / name, root, "link", True, dry_run)


def uninstall_managed_file(
    path: Path,
    dry_run: bool,
    *,
    home: Optional[Path] = None,
    restore: bool = True,
    keep_backup: bool = True,
) -> str:
    """Remove one managed instruction file, restoring what it replaced.

    A file the user has since rewritten is theirs. Leaving it and saying so is
    the honest answer, and not an error: the run continues and exits 0.
    """
    if not (path.exists() or path.is_symlink()):
        return f"absent     {path}"
    if not _looks_managed(path):
        return f"left       {path} (hand-edited since install; not removed)"

    receipt_root = (home or path.parent.parent).expanduser()
    # Read before the current file is moved aside, or our own fresh backup
    # becomes a restore candidate.
    chosen, note = restorable_backup(receipt_root, str(path), "managed-file")
    if not restore:
        chosen, note = None, "left in .skills-backups (--no-restore)"
    backup = backup_path(path.parent, path.name) if keep_backup else None
    if dry_run:
        message = f"would remove {path}"
        if backup is not None:
            message += f"; back up to {backup}"
        message += f"; restore {chosen.path}" if chosen is not None else f"; {note}"
        return message

    if backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(backup))
    else:
        remove_path(path)
    if chosen is not None:
        shutil.move(str(chosen.path), str(path))
    forget_entry(receipt_root, str(path), False)

    parts = [f"removed    {path}"]
    if backup is not None:
        parts.append(f"(backup: {backup})")
    if chosen is not None:
        parts.append(f"(restored: {chosen.path})")
    else:
        parts.append(f"({note})")
    return " ".join(parts)


def uninstall_global_instructions(
    home: Path, dry_run: bool, *, restore: bool = True, keep_backup: bool = True
) -> list:
    """Both managed files, always together.

    ~/.claude/CLAUDE.md imports ~/.agents/AGENTS.md, so removing one alone
    leaves a dangling @import pointing at a file that is no longer there.
    """
    home = home.expanduser()
    return [
        uninstall_managed_file(
            path, dry_run, home=home, restore=restore, keep_backup=keep_backup
        )
        for path, _text in global_instruction_files(home, "link")
    ]


def external_removal_plan(name: str, roots: Sequence[Path]) -> tuple:
    """(removable, notes) — what this collection recorded placing, and the
    honest lines about everything it cannot touch."""
    tool = external_tool(name)
    notes = [tool.removal]
    removable: list = []
    if name == "matt-skills":
        for root in roots:
            recorded = sorted(
                entry_id
                for entry_id in receipt_entries(root, kind="skill", origin="matt-skills")
                if (root / entry_id).exists() or (root / entry_id).is_symlink()
            )
            removable.extend((entry_id, root) for entry_id in recorded)
            marker = root / tool.marker
            if not recorded and (marker.exists() or marker.is_symlink()):
                notes.append(
                    f"{root}: installed before this version recorded what it "
                    "placed, so nothing is removed. `skills status` lists the "
                    "directories; remove them by name with "
                    "`skills uninstall NAME --unrecorded`."
                )
    elif name == "graphify":
        notes.append("run: uv tool uninstall graphifyy")
        notes.append(
            "its registered skill was placed by graphify itself — check "
            "<root>/graphify in each root and remove it with graphify's own CLI"
        )
    return removable, notes


def uninstall_external(
    name: str,
    roots: Sequence[Path],
    dry_run: bool,
    *,
    restore: bool = True,
    keep_backup: bool = True,
) -> list:
    """Remove what is recorded and print every note; never guess at the rest."""
    removable, notes = external_removal_plan(name, roots)
    messages = list(notes)
    for entry_id, root in removable:
        messages.append(
            uninstall_one(
                entry_id, root, dry_run, restore=restore, keep_backup=keep_backup
            )
        )
    return messages


def remove_shims(args: argparse.Namespace) -> int:
    """Mirror of setup_path(): shim and PATH mechanics belong to skills_cli."""
    import skills_cli

    return skills_cli.command_remove_path(
        argparse.Namespace(
            bin=args.home.expanduser() / ".local" / "bin",
            dry_run=args.dry_run,
            add_path=args.add_path,
        )
    )


def setup_path(args: argparse.Namespace) -> int:
    """Write the `skills` launcher shims from the installer.

    `skills setup-path` is what creates the `skills` command, so telling a
    fresh machine to run it is circular: the command does not exist yet. This
    entry point breaks that loop, because `./install.sh` is always available in
    a clone. Imported here rather than at module scope because skills_cli
    imports this module.
    """
    import skills_cli

    # Derive the shim directory from args.home rather than leaving it to
    # DEFAULT_BIN, which reads the real home at import time. The formula is the
    # same one DEFAULT_BIN uses, so an ordinary run is unaffected; what changes
    # is that --home now isolates this path like it isolates every other, so a
    # test cannot silently report on the machine it happens to run on.
    return skills_cli.command_setup_path(
        argparse.Namespace(
            bin=args.home.expanduser() / ".local" / "bin",
            dry_run=args.dry_run,
            add_path=args.add_path,
        )
    )


CLOUD_DECLINED = Path(".claude") / ".skills-cloud-declined"


def cloud_installed_skills(home: Path) -> list[str]:
    """Bundled skills already present in this home's user-scope roots."""
    roots = resolve_roots(["all"], "user", home, home, None)
    present = {
        name
        for name in available_skills()
        for root in roots
        if (root / name).exists() or (root / name).is_symlink()
    }
    return sorted(present)


def cloud_offer(home: Path, repo: Path = REPO_ROOT) -> Optional[str]:
    """The session-start message that asks the user what to install, or None.

    None means stay silent, and silence is the common case by design: this text
    is prepended to a fresh cloud session before the user has said anything, so
    it has to earn its place in the context window every time. It earns it only
    when the collection is reachable and nothing from it is installed yet.

    The offer deliberately stops at asking. A cloud setup script runs before
    anyone is present to consult, so choosing there means choosing for the user
    and re-choosing on every environment rebuild; handing the catalog to the
    agent instead moves the decision to the one moment the user is actually in
    the room. That is also why declining is a file rather than a flag — it has
    to outlive a session that no longer exists.
    """
    if (home / CLOUD_DECLINED).exists():
        return None
    if cloud_installed_skills(home):
        return None
    # as_posix throughout: these lines are commands the agent will run, and it
    # runs them in the POSIX shell of a cloud container. Mixing separators into
    # something meant to be copied reads as a mistake even where it would work.
    installer = f"{repo.as_posix()}/install.sh"
    names = available_skills()
    width = max(len(name) for name in names)
    # Spell the suggested set out rather than pointing at --non-interactive,
    # which means "every bundled skill" and would machine-wide install exactly
    # the narrow ones global_default marks as not wanting that. A generated
    # list cannot drift from the flag the way a sentence about it would.
    suggested = "".join(
        f" --skill {name}" for name in names if skill_global_default(name)
    )
    lines = [
        f"[skills] dm1681/skills is available at {repo.as_posix()}, and none of",
        "its skills are installed in this session yet.",
        "",
        "Ask the user which they want, then run the matching command below.",
        "Install nothing before they answer.",
        "",
    ]
    for name in names:
        scope = (
            "suggested machine-wide"
            if skill_global_default(name)
            else "narrow; project scope on request"
        )
        lines.append(f"  {name.ljust(width)}  ({scope})")
        lines.append(f"      {skill_summary(name)}")
    lines += [
        "",
        "Also available, neither bundled here nor installed by default:",
        f"  {'graphify'.ljust(width)}  external, needs uv",
        f"      {external_tool('graphify').summary}",
        f"  {'matt-skills'.ljust(width)}  external, needs npx",
        f"      {external_tool('matt-skills').summary}. Its `code-review` shares",
        "      a name with Claude's built-in and replaces it for the session.",
        "",
        "Commands:",
        f"  everything suggested   {installer}{suggested}",
        f"  named skills only      {installer} --skill NAME [--skill NAME ...]",
        f"  this repo only         {installer} --skill NAME --scope project",
        f"  global instructions    {installer} --global-instructions",
        f"  graphify               {installer} --graphify",
        f"  matt-skills            {installer} --matt-skills",
        f"  nothing, stop asking   touch {(home / CLOUD_DECLINED).as_posix()}",
        "",
        "Flags combine, and passing any of them installs without prompting.",
        f"  {installer} --non-interactive  installs EVERY bundled skill,",
        "  the narrow ones included, so prefer naming skills over that.",
    ]
    return "\n".join(lines)


def cloud_bootstrap(home: Path, repo: Path = REPO_ROOT, dry_run: bool = False) -> str:
    """Register the cloud session-start hook in this home's Claude settings.

    Installs no skills, on purpose: this is the whole point of the flag. A cloud
    setup script that installs a fixed set has to be edited every time that set
    should change, and the copy pasted into the environment's setup field drifts
    from the repository the moment anything moves. Registering a hook instead
    means the setup field holds three lines that never change again, and what is
    offered is whatever the checkout says today.
    """
    hook = f"{repo.as_posix()}/scripts/cloud-session-start.sh"
    settings = home / ".claude" / "settings.json"
    existing: dict = {}
    if settings.is_file():
        try:
            loaded = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            # Salvage rather than overwrite: this file is the user's, and a
            # syntax error in it is not permission to discard their hooks.
            return (
                f"{settings} is not valid JSON; left untouched. Add a SessionStart "
                f"hook running {hook} by hand, or move the file aside and re-run."
            )
        if isinstance(loaded, dict):
            existing = loaded
    hooks = existing.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return f"{settings} has a non-object 'hooks' key; left untouched."
    events = hooks.setdefault("SessionStart", [])
    if not isinstance(events, list):
        return f"{settings} has a non-list 'SessionStart' key; left untouched."
    # Compare parsed commands, not serialized JSON: json.dumps escapes a
    # backslash, so testing the raw path against the dump never matches the
    # value this function itself just wrote, and every run appended a duplicate.
    registered = {
        item.get("command")
        for entry in events
        if isinstance(entry, dict)
        for item in entry.get("hooks", [])
        if isinstance(item, dict)
    }
    if hook in registered:
        return f"unchanged    {settings}"
    events.append({"hooks": [{"type": "command", "command": hook}]})
    if dry_run:
        return f"would write  {settings}"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return f"wrote        {settings}"


def launcher_hint(bin_dir: Optional[Path] = None) -> Optional[str]:
    """One line telling the reader how to get the `skills` command, or None.

    Silent when the shim is already there, so a machine that is set up never
    sees it, and a machine that is not gets the exact command instead of
    discovering the gap the next time it types `skills`.
    """
    import skills_cli

    bin_dir = skills_cli.DEFAULT_BIN if bin_dir is None else bin_dir
    if (bin_dir / skills_cli.SHIM_NAME).is_file() and shutil.which(
        skills_cli.SHIM_NAME
    ):
        return None
    return (
        "Next: `./install.sh --setup-path --add-path` writes the `skills` "
        "command so this works from any project."
    )


GRAPHIFY_HEADING = re.compile(r"^#{1,6} graphify\b", re.IGNORECASE | re.MULTILINE)
TRAILING_GRAPHIFY = re.compile(
    r"\n#{1,6} graphify\b(?:(?!\n#).)*\s*\Z", re.IGNORECASE | re.DOTALL
)


def strip_appended_graphify(home: Path, dry_run: bool) -> list[str]:
    """Remove graphify's appended block from pointer files this repo manages.

    graphify's own CLI appends its instructions to ~/.claude/CLAUDE.md and
    ~/.agents/AGENTS.md when it registers. When those are this installer's
    managed pointer files, the chain back to global/AGENTS.md already carries
    the same section, so the appended copy loads twice into every session.
    Only a trailing block is removed, and only while the instructions stay
    reachable; the section ``copy`` mode inlines mid-file is left alone.
    """
    messages: list[str] = []
    root = home.expanduser()
    for path in (root / ".agents" / "AGENTS.md", root / ".claude" / "CLAUDE.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith(MANAGED_MARKER):
            continue
        match = TRAILING_GRAPHIFY.search(text)
        if match is None:
            continue
        remaining = text[: match.start()].rstrip("\n") + "\n"
        source_carries = GLOBAL_SOURCE.is_file() and bool(
            GRAPHIFY_HEADING.search(GLOBAL_SOURCE.read_text(encoding="utf-8"))
        )
        imports_chain = re.search(r"^@", remaining, re.MULTILINE) is not None
        if not (GRAPHIFY_HEADING.search(remaining) or (imports_chain and source_carries)):
            continue
        messages.append(_write_managed_file(path, remaining, dry_run, home=root))
    return messages


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Install this collection into shared or agent-specific skill directories."
    )
    result.add_argument(
        "--agent",
        action="append",
        default=[],
        metavar="NAME",
        help="universal, codex, cursor, copilot, claude, or all (repeatable; default all)",
    )
    result.add_argument("--scope", choices=("user", "project"), default="user")
    result.add_argument("--project-dir", type=Path, default=Path.cwd())
    result.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    result.add_argument("--target", type=Path, help="override the resolved skills root")
    result.add_argument("--skill", action="append", default=[], metavar="NAME")
    result.add_argument("--mode", choices=("copy", "link"), default="copy")
    result.add_argument(
        "--graphify",
        action="store_true",
        help="install or upgrade graphifyy with uv and register its skill for selected agents",
    )
    matt_skills = result.add_mutually_exclusive_group()
    matt_skills.add_argument(
        "--matt-skills",
        dest="matt_skills",
        action="store_true",
        help="install all mattpocock/skills for the selected agents",
    )
    matt_skills.add_argument(
        "--no-matt-skills",
        dest="matt_skills",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    result.set_defaults(matt_skills=None)
    result.add_argument(
        "--enable-skill",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "make an installed skill visible to the model by removing "
            "disable-model-invocation from its frontmatter; recorded and "
            "re-applied when --matt-skills updates the files"
        ),
    )
    result.add_argument(
        "--hide-skill",
        action="append",
        default=[],
        metavar="NAME",
        help="the reverse of --enable-skill: hide an installed skill from the model",
    )
    result.add_argument(
        "--global-instructions",
        dest="global_instructions",
        nargs="?",
        const="link",
        choices=("link", "copy"),
        default=None,
        help=(
            "install global/AGENTS.md as user-level instructions in "
            "~/.agents/AGENTS.md and ~/.claude/CLAUDE.md; link (default) points "
            "them at this checkout, copy writes the text into ~/.agents/AGENTS.md. "
            "With --uninstall the link|copy value is ignored: the paths are fixed"
        ),
    )
    interaction = result.add_mutually_exclusive_group()
    interaction.add_argument(
        "--interactive",
        action="store_true",
        help="open the dashboard, even when input is not a terminal",
    )
    interaction.add_argument(
        "--non-interactive",
        action="store_true",
        help="use command-line options without opening the dashboard",
    )
    result.add_argument(
        "--setup-path",
        action="store_true",
        help=(
            "write the `skills` launcher shims and exit; the only way to get "
            "that command on a machine that does not have it yet"
        ),
    )
    result.add_argument(
        "--add-path",
        action="store_true",
        help="with --setup-path, also add the shim directory to your PATH",
    )
    result.add_argument(
        "--cloud-bootstrap",
        action="store_true",
        help=(
            "register the cloud session-start hook and exit, installing no "
            "skills; for a cloud environment setup script, which runs before "
            "anyone is there to choose"
        ),
    )
    result.add_argument(
        "--cloud-offer",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    result.add_argument("--force", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument(
        "--uninstall",
        action="store_true",
        help=(
            "remove instead of install; --skill/--agent/--scope/--project-dir/"
            "--target/--global-instructions/--matt-skills/--graphify/--setup-path "
            "select what goes"
        ),
    )
    result.add_argument(
        "--all",
        action="store_true",
        help="with --uninstall: every skill recorded in the resolved roots",
    )
    result.add_argument(
        "--unrecorded",
        action="store_true",
        help="with --uninstall: also remove skill directories no receipt records",
    )
    result.add_argument(
        "--no-restore",
        action="store_true",
        help="with --uninstall: leave pre-install originals in .skills-backups",
    )
    result.add_argument(
        "--no-backup",
        action="store_true",
        help="with --uninstall: delete rather than move aside (unrecoverable)",
    )
    result.add_argument(
        "--restore-from",
        type=Path,
        metavar="PATH",
        help="with --uninstall and exactly one --skill: restore this backup",
    )
    result.add_argument(
        "--status",
        action="store_true",
        help="list what this collection installed in the resolved roots, and exit",
    )
    result.add_argument("--list", action="store_true", help="list bundled skills and exit")
    result.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return result


def open_dashboard(args: argparse.Namespace) -> int:
    """Hand the screen to the Textual dashboard.

    Textual is a declared dependency, so `uv run` always has it. A bare-Python
    fallback might not, and that is worth an explanation rather than a
    traceback: naming skills on the command line still needs nothing installed.
    """
    for option, flag in (
        (args.graphify, "--graphify"),
        (args.matt_skills, "--matt-skills"),
        (args.target is not None, "--target"),
        (args.global_instructions is not None, "--global-instructions"),
    ):
        if option:
            raise InstallError(
                f"{flag} is a scripted option and the dashboard does not carry it; "
                "add --non-interactive to run it without opening the dashboard"
            )
    try:
        import skills_tui
    except ImportError as exc:
        raise InstallError(
            f"the dashboard needs Textual ({exc}). Run the installer through uv, "
            "which provisions the locked environment automatically, or install "
            "Textual with pip. A scripted install needs no dependencies at all: "
            "--skill NAME --non-interactive"
        )
    return skills_tui.run(
        args.project_dir.expanduser().resolve(), args.scope, args.agent, args.mode
    )


def execute_install(args: argparse.Namespace, selected: list[str]) -> None:
    roots = stage_roots(args, args.scope)
    for root in roots:
        for skill_name in selected:
            print(
                install_one(
                    SOURCE_ROOT / skill_name,
                    root,
                    args.mode,
                    args.force,
                    args.dry_run,
                )
            )
        write_receipt(root, selected, args.mode, args.dry_run)
        record_root(args.home, root, args.dry_run)
    if args.matt_skills:
        install_matt_skills(
            args.agent,
            roots,
            args.force,
            args.dry_run,
            print,
            getattr(args, "matt_npx", None),
        )
    if args.global_instructions is not None:
        for result in install_global_instructions(
            args.home, args.global_instructions, args.dry_run
        ):
            print(result)
    if args.graphify:
        install_graphify(
            args.agent,
            args.scope,
            args.project_dir,
            args.dry_run,
            print,
            home=args.home,
        )
    if args.matt_skills and not args.dry_run:
        print(
            "Next: run /setup-matt-pocock-skills once inside the target "
            "repository to finish configuring the workflows."
        )
        undecided = {
            name for root in roots for name in hidden_skills(root)
        } - set(read_model_decisions(roots))
        if undecided:
            print(
                f"{len(undecided)} skill(s) installed hidden from the model's "
                "skill list; select matt-skills in the dashboard to review "
                "them, or enable one directly with --enable-skill NAME."
            )
    if not args.dry_run:
        hint = launcher_hint()
        if hint:
            print(hint)


def _status_roots(args: argparse.Namespace) -> list:
    """The roots this run names, plus every root an earlier run recorded."""
    roots = list(stage_roots(args, args.scope))
    for root in known_roots(args.home.expanduser()):
        if root not in roots:
            roots.append(root)
    return roots


def execute_uninstall(args: argparse.Namespace, selected: list) -> None:
    """Mirror of execute_install, in reverse order of installation."""
    roots = stage_roots(args, args.scope)
    restore = not args.no_restore
    keep_backup = not args.no_backup
    for name, wanted in (("graphify", args.graphify), ("matt-skills", args.matt_skills)):
        if not wanted:
            continue
        for message in uninstall_external(
            name, roots, args.dry_run, restore=restore, keep_backup=keep_backup
        ):
            print(message)
    for root in roots:
        for name in selected:
            print(
                uninstall_one(
                    name,
                    root,
                    args.dry_run,
                    restore=restore,
                    keep_backup=keep_backup,
                    allow_unrecorded=args.unrecorded,
                    restore_from=args.restore_from,
                )
            )
        for message in prune_root(root, args.dry_run):
            print(message)
    if args.global_instructions is not None:
        for message in uninstall_global_instructions(
            args.home, args.dry_run, restore=restore, keep_backup=keep_backup
        ):
            print(message)
        # The home receipt exists only to describe those files; with none left
        # it is litter. prune_root leaves the home itself alone — it is never
        # empty, and the rmdir it attempts fails harmlessly.
        for message in prune_root(args.home.expanduser(), args.dry_run):
            print(message)
    if args.setup_path:
        remove_shims(args)


def uninstall_main(args: argparse.Namespace) -> int:
    """Validate an uninstall selection, then carry it out."""
    others = (
        args.global_instructions is not None
        or bool(args.matt_skills)
        or args.graphify
        or args.setup_path
    )
    if not (args.skill or args.all or others):
        raise InstallError(
            "--uninstall needs to know what to remove: --skill NAME, --all, "
            "--global-instructions, --matt-skills, --graphify, or --setup-path"
        )
    if args.skill and args.all:
        raise InstallError("pass --skill or --all, not both")
    if args.restore_from is not None:
        if len(args.skill) != 1:
            raise InstallError(
                "--restore-from restores one backup into one place, so it needs "
                "exactly one --skill"
            )
        if args.no_restore:
            raise InstallError("--restore-from and --no-restore contradict each other")

    roots = stage_roots(args, args.scope)
    if args.all:
        selected = sorted(
            {entry_id for root in roots for entry_id in receipt_entries(root, kind="skill")}
        )
        if not selected:
            print("nothing recorded in: " + ", ".join(str(root) for root in roots))
            if not others:
                return 0
    else:
        # Deliberately not validated against available_skills(): a skill can be
        # removed from the checkout after being installed, and that install
        # still has to be removable.
        selected = list(args.skill)
        for name in selected:
            installed = any(
                name in receipt_entries(root, kind="skill")
                or (root / name).exists()
                or (root / name).is_symlink()
                for root in roots
            )
            if not installed:
                raise InstallError(
                    "not installed in %s: %s"
                    % (", ".join(str(root) for root in roots), name)
                )
    execute_uninstall(args, selected)
    return 0


def manage_model_invocation(args: argparse.Namespace) -> int:
    """Handle --enable-skill / --hide-skill and exit.

    These are the scripted counterparts to the dashboard's review screen. They
    operate on *installed* skills — whatever collection they came from — so
    they skip the bundled-skill validation entirely.
    """
    roots = stage_roots(args, args.scope)
    overlap = sorted(set(args.enable_skill) & set(args.hide_skill))
    if overlap:
        raise InstallError(
            f"both --enable-skill and --hide-skill given for: {', '.join(overlap)}"
        )
    for names, visible in ((args.enable_skill, True), (args.hide_skill, False)):
        for name in names:
            present = [
                root / name for root in roots if (root / name / "SKILL.md").is_file()
            ]
            if not present:
                raise InstallError(
                    f"skill not installed in any selected root: {name}"
                )
            changed = [set_model_invocation(skill_dir, visible) for skill_dir in present]
            record_model_decisions(roots, {name: "enabled" if visible else "hidden"})
            state = "visible to the model" if visible else "hidden from the model"
            already = "" if any(changed) else " (already was)"
            print(f"{name}: {state}{already}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(raw_args)
    try:
        bundled = available_skills()
        if args.list:
            print("\n".join(bundled))
            return 0
        if args.cloud_offer:
            # Ahead of the dashboard check and the bare-invocation guard: this
            # runs from a hook with no terminal, and silence is a valid answer.
            offer = cloud_offer(args.home.expanduser())
            if offer:
                print(offer)
            return 0
        if args.cloud_bootstrap:
            print(cloud_bootstrap(args.home.expanduser(), dry_run=args.dry_run))
            return 0
        if args.status:
            home = args.home.expanduser()
            print(
                format_status(
                    discover(_status_roots(args), home, home / ".local" / "bin")
                )
            )
            return 0
        for flag, flag_name in (
            (args.all, "--all"),
            (args.unrecorded, "--unrecorded"),
            (args.no_backup, "--no-backup"),
            (args.no_restore, "--no-restore"),
            (args.restore_from is not None, "--restore-from"),
        ):
            if flag and not args.uninstall:
                raise InstallError(f"{flag_name} only applies to --uninstall")
        if args.uninstall:
            # Ahead of the --setup-path branch: under --uninstall that flag
            # selects the shims for removal rather than asking for them.
            return uninstall_main(args)
        if args.setup_path:
            return setup_path(args)
        if args.enable_skill or args.hide_skill:
            return manage_model_invocation(args)
        if should_open_dashboard(raw_args, args, sys.stdin, sys.stdout, os.environ):
            return open_dashboard(args)
        if not raw_args:
            # A bare invocation means "ask me". With no terminal to ask in there
            # is nothing to fall back on: installing every skill into every root
            # would silently make the choices the user came here to make.
            raise InstallError(
                "the dashboard needs an interactive terminal, and no options "
                "were given, so nothing was installed. Choose explicitly, for "
                "example `--skill NAME`, or pass --non-interactive to accept "
                "every default. On Windows, a pty shell such as Git Bash hides "
                "the terminal from Python: run install.ps1 in PowerShell or "
                "Windows Terminal for the dashboard."
            )
        selected = args.skill or bundled
        unknown = sorted(set(selected) - set(bundled))
        if unknown:
            raise InstallError(f"unknown skill: {', '.join(unknown)}")
        if len(selected) != len(set(selected)):
            raise InstallError("a skill was selected more than once")
        if args.graphify and args.target is not None:
            raise InstallError(
                "--graphify cannot be combined with --target; use --scope instead"
            )
        if args.matt_skills and not args.dry_run:
            args.matt_npx = require_npx()
        if args.graphify and not args.dry_run:
            graphify_cwd = args.project_dir.expanduser().resolve()
            if args.scope == "project" and not graphify_cwd.is_dir():
                raise InstallError(
                    f"Graphify project directory does not exist: {graphify_cwd}"
                )
            if not shutil.which("uv"):
                raise InstallError(
                    "--graphify requires uv; install it from "
                    "https://docs.astral.sh/uv/ and rerun"
                )
        execute_install(args, selected)
        return 0
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
