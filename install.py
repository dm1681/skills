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
from typing import Callable, Iterable, Mapping, NamedTuple, Optional, TextIO


REPO_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = REPO_ROOT / "skills"
GLOBAL_SOURCE = REPO_ROOT / "global" / "AGENTS.md"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

# Stamped into every file the installer owns outside a skills root, so a later
# run (or a human) can tell a generated pointer from hand-written guidance.
MANAGED_MARKER = "<!-- dm1681/skills: managed file -->"

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
    about its state is whether a directory by that name is present.
    """

    name: str
    summary: str
    origin: str
    requires: str


EXTERNAL_TOOLS = (
    ExternalTool(
        name="graphify",
        summary="Turn any input into a persistent, queryable knowledge graph",
        origin="graphifyy on PyPI, installed and registered by its own CLI",
        requires="uv",
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


def skill_summary(name: str) -> str:
    """Return one short line describing a bundled skill."""
    interface = SOURCE_ROOT / name / "agents" / "openai.yaml"
    if interface.is_file():
        for line in interface.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition(":")
            if key == "short_description" and separator:
                summary = value.strip().strip('"').strip("'")
                if summary:
                    return summary
    return "Bundled in this collection."


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
                emit(install_one(source, destination_root, "copy", force, False))


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
) -> str:
    destination = root / source.name
    exists = destination.exists() or destination.is_symlink()
    current = exists and destination_matches_mode(destination, mode)
    if current and trees_equal(destination, source):
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
    return f"installed  {destination}" + (f" (backup: {backup})" if backup else "")


def write_receipt(root: Path, skills: list[str], mode: str, dry_run: bool) -> None:
    if dry_run:
        return
    receipt = {
        "schema_version": 1,
        "collection": "dm1681/skills",
        "version": VERSION,
        "skills": skills,
        "mode": mode,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / ".dm1681-skills.json.tmp"
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, root / ".dm1681-skills.json")


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


def _write_managed_file(path: Path, text: str, dry_run: bool) -> str:
    exists = path.exists() or path.is_symlink()
    if exists and not path.is_symlink() and path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return f"unchanged  {path}"
        except UnicodeDecodeError:
            pass
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
    return f"installed  {path}" + (f" (backup: {backup})" if backup else "")


def install_global_instructions(home: Path, mode: str, dry_run: bool) -> list[str]:
    return [
        _write_managed_file(path, text, dry_run)
        for path, text in global_instruction_files(home, mode)
    ]


def setup_path(args: argparse.Namespace) -> int:
    """Write the `skills` launcher shims from the installer.

    `skills setup-path` is what creates the `skills` command, so telling a
    fresh machine to run it is circular: the command does not exist yet. This
    entry point breaks that loop, because `./install.sh` is always available in
    a clone. Imported here rather than at module scope because skills_cli
    imports this module.
    """
    import skills_cli

    return skills_cli.command_setup_path(
        argparse.Namespace(bin=None, dry_run=args.dry_run, add_path=args.add_path)
    )


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
        messages.append(_write_managed_file(path, remaining, dry_run))
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
        "--global-instructions",
        dest="global_instructions",
        nargs="?",
        const="link",
        choices=("link", "copy"),
        default=None,
        help=(
            "install global/AGENTS.md as user-level instructions in "
            "~/.agents/AGENTS.md and ~/.claude/CLAUDE.md; link (default) points "
            "them at this checkout, copy writes the text into ~/.agents/AGENTS.md"
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
    result.add_argument("--force", action="store_true")
    result.add_argument("--dry-run", action="store_true")
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
    if not args.dry_run:
        hint = launcher_hint()
        if hint:
            print(hint)


def main(argv: Optional[list[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(raw_args)
    try:
        bundled = available_skills()
        if args.list:
            print("\n".join(bundled))
            return 0
        if args.setup_path:
            return setup_path(args)
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
