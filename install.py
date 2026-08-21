#!/usr/bin/env python3
"""Install skills from this repository into supported agent directories."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
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
MATT_SKILLS_REPO = "https://github.com/mattpocock/skills.git"
# Pinned on purpose. The upstream CLI always took `main`, which made two installs
# a week apart silently different; a ref in the file makes an update a commit
# somebody reviewed, and `git diff` between two refs shows exactly what changed.
# The tag is what a human reads and the commit is what actually pins: a tag can
# be force-moved upstream, so the default install verifies that it still points
# where this repository says it does. Update the two together.
MATT_SKILLS_REF = "v1.2.3"
MATT_SKILLS_COMMIT = "6acc160e4e0cd062dbbbd7a1b26ae92855edf07e"
# Upstream retires skills into `skills/deprecated/` rather than deleting them.
# Nothing lives there today, so skipping it changes no install; it only keeps a
# future retirement from arriving as a fresh install. Matched against the first
# path component only, so a skill that merely has `deprecated` deeper in its
# path still installs.
MATT_SKILLS_SKIP = ("deprecated",)

PSTACK_SOURCE = "cursor/plugins pstack"
PSTACK_REPO = "https://github.com/cursor/plugins.git"
# pstack lives inside a monorepo of Cursor plugins, so the fetch lands the whole
# repository and everything below is relative to this one directory. At depth 1
# that costs about nine megabytes, which is cheaper than teaching the fetch to
# do a partial clone and having the verification below reason about a tree it
# only half has.
PSTACK_SUBDIR = "pstack"
# The same pin as mattpocock/skills, reached the other way round. That
# repository publishes tags, so the tag is what a human reads and the commit
# beside it is what actually pins. cursor/plugins publishes none, so the ref
# *is* a commit and the pair collapses -- which leaves nothing readable saying
# which pstack this is. The plugin states its own version in its manifest, so
# that is what the default install checks: the commit says the fetch landed
# where it was told, and the version says the thing that landed is the release
# this repository documents. Update the three together.
PSTACK_REF = "51a96e0dd838404da19ba83dc70aa21eef71f868"
PSTACK_COMMIT = PSTACK_REF
PSTACK_VERSION = "0.14.1"
PSTACK_MANIFEST = ".cursor-plugin/plugin.json"
# `plugin.json` points its own installer at `./skills/` and nothing else, so
# that is what installs here. `automations/benny/` holds three more skills
# outside that pointer; they drive a Slack-and-tracker pipeline that only works
# once its services are configured, and installing them would place three
# skills upstream's own consumers never get. Named here rather than left
# implicit so the day the manifest grows a second pointer is a decision.
PSTACK_SKIP = ("deprecated",)
# A credential prompt inside an installer waits forever: a scripted or cloud run
# has nobody to answer it, and an askpass helper opens a dialog even where no
# terminal could have asked. A 401 — a proxy in the way, a repository URL
# pointing somewhere private — should fail in a second with a message instead.
UPSTREAM_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
# The same reasoning as UPSTREAM_GIT_ENV, for the reads `--status` makes.
# A status check that blocks on a credential prompt is worse than one that
# cannot reach the network, because the second at least says so and exits.
STATUS_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
# ...and a wall-clock bound, because the env vars only stop a *prompt*. A fetch
# over an ssh remote whose host blackholes packets — a dropped VPN, a captive
# portal — neither prompts nor fails; it waits. That wait lands on a worker
# thread the interpreter joins at exit, so an unbounded one leaves a dashboard
# spinning "checking origin…" and the process alive after quit. Bounded, the
# same case degrades to the honest answer the status side already has a word
# for: unknown.
STATUS_GIT_TIMEOUT = 20.0
RECEIPT_NAME = ".dm1681-skills.json"
# The machine-wide index of every root an install has ever touched, kept in the
# home directory because that is the one place a project-scoped install can
# still write to. It is a cache and never a source of truth: every root carries
# its own receipt, and this file only says where to look. Delete it and nothing
# breaks -- a scoped `--status` answers exactly as before, and the next install
# writes the entry back.
ROOTS_INDEX_NAME = ".dm1681-skills-roots.json"
# The receipt's vocabulary, not the design sketch's `version`: this file has no
# collection version in it, and one key named `version` meaning "schema" here
# while it means "which release installed this" in the receipt beside it is the
# kind of near-miss that gets read wrong once and then trusted.
ROOTS_INDEX_SCHEMA = 1
# How long a writer waits for another writer's lock on the roots index before
# writing anyway. Short because the operation it guards is a few milliseconds
# of JSON, and giving up is deliberately harmless: writing unlocked is exactly
# the behaviour that existed before the lock, whose worst outcome is a lost
# entry the next install rewrites. Blocking an install on a stale lock file
# left by a killed process would be the worse failure.
ROOTS_INDEX_LOCK_SECONDS = 2.0
# The frontmatter key a skill states its own version in. The installed copy at
# ~/.claude/skills/<name>/SKILL.md carries no git history and no VERSION file,
# so a field inside the file is the only version that survives the copy -- and
# comparing an installed version against the checkout's is what tells "you have
# an older release" apart from "somebody edited the installed copy".
SKILL_VERSION_KEY = "version"

# One reconciled answer per skill per root.
CURRENT = "current"
DRIFTED = "drifted"
MISSING = "missing"
ORPHAN = "orphan"
UNTRACKED = "untracked"
MODE_MISMATCH = "mode"

# One name installed in more than one root. Not per-root states: neither root
# is wrong on its own, and the finding only exists once every root is in view,
# which is what the roots index makes possible.
SHADOWED = "shadowed"
DIVERGENT = "divergent"
# An indexed root whose directory is gone -- a deleted project, an unplugged
# volume. A prune offer, never an error, for the same reason `read_receipt`
# returns None instead of raising: the index is allowed to be out of date.
VANISHED = "vanished"

# Every state except `current` wants a human to do something. `shadowed` is
# excluded deliberately: a machine-wide install puts identical copies in
# .agents and .claude *by design*, so a flag that fired on every duplicate
# would fire on every healthy machine and mean nothing. Only `divergent`
# changes what an agent actually reads, so only `divergent` is work.
ACTIONABLE_STATES = (DRIFTED, MISSING, ORPHAN, UNTRACKED, MODE_MISMATCH, DIVERGENT)


class VendoredSkill(NamedTuple):
    """A bundled skill that is a copy of a file this repository does not own.

    A vendored copy drifts silently: someone edits it here instead of upstream,
    and nothing says so. The recorded hash is what makes that detectable with
    no network and no second checkout -- it covers the upstream bytes only, so
    the provenance note this repository splices in does not change it.
    """

    skill: str
    entrypoint: str
    upstream: str
    commit: str
    sha256: str


VENDORED_SKILLS = (
    VendoredSkill(
        skill="olympus-report-progress",
        entrypoint="SKILL.md",
        upstream="dm1681/Olympus .claude/skills/olympus-report-progress/SKILL.md",
        commit="252f467",
        sha256="5a2a30d8056ab340cce4f6006050166cd0d9c99b5d69777264c246e7867d3732",
    ),
)


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
    """

    name: str
    summary: str
    origin: str
    requires: str
    marker: str


EXTERNAL_TOOLS = (
    ExternalTool(
        name="graphify",
        summary="Turn any input into a persistent, queryable knowledge graph",
        origin="graphifyy on PyPI, installed and registered by its own CLI",
        requires="uv",
        marker="graphify",
    ),
    ExternalTool(
        name="matt-skills",
        summary="mattpocock/skills engineering workflows",
        origin="mattpocock/skills on GitHub, cloned at a pinned ref and copied in",
        requires="git",
        marker="setup-matt-pocock-skills",
    ),
    ExternalTool(
        name="pstack",
        summary="pstack rigorous agent workflows and coding principles",
        origin=(
            "the pstack plugin in cursor/plugins on GitHub, cloned at a pinned "
            "ref and copied in"
        ),
        requires="git",
        marker="setup-pstack",
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

    A file that cannot be read is "" -- the same answer as a file with no such
    key -- and not an exception. The paths that ask this walk *installed*
    roots, which are shared with tools this collection does not manage: one
    latin-1 byte or one file mode 000 in `~/.claude/skills` would otherwise
    take down every caller that merely wanted a version, the dashboard's first
    frame included. Same posture as `read_receipt`: unreadable is unknown.
    """
    if not entrypoint.is_file():
        return ""
    try:
        text = entrypoint.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    lines = text.splitlines()
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


def skill_version(skill_dir: Path) -> str:
    """The version a skill declares in its own SKILL.md, or "".

    Takes a directory rather than a name because both copies matter and only
    one of them lives in this checkout: the question worth answering is how the
    *installed* `~/.claude/skills/<name>` compares to `skills/<name>`, and the
    installed copy has neither git history nor a VERSION file beside it.

    Empty is a real answer, not a failure. A skill that predates the field, and
    every vendored copy (see `skill_is_vendored`), has no version to state, and
    a caller that treats "" as 0.0.0 would report those as older than
    everything rather than as unknown.
    """
    return frontmatter_value(skill_dir / "SKILL.md", SKILL_VERSION_KEY)


def skill_is_vendored(name: str) -> bool:
    """Whether a bundled skill is a copy of a file this repository does not own.

    A vendored skill has no local version by design: its frontmatter is inside
    the bytes `vendored_status` hashes, so adding a `version:` key here would
    register as upstream drift and break the one check that makes a silent edit
    to a vendored copy visible. Callers ask this so they can say "vendored" —
    pinned by hash, versioned upstream — instead of reporting a missing version
    as unknown and inviting somebody to fill it in.
    """
    return any(vendored.skill == name for vendored in VENDORED_SKILLS)


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


def root_agent(root: Path) -> str:
    """Which agent convention a resolved root follows, or "".

    `resolve_roots` builds one path per agent and then dedupes them into a flat
    list, so by the time an installer holds a root the agent that produced it
    is gone. Re-deriving it from the path keeps that rule in one place instead
    of threading a second, parallel list of names through every caller for the
    two to fall out of step -- under this convention the directory *is* the
    answer.

    A `--target` root that follows no convention has no agent to name, and ""
    says so. Guessing `claude` there would record a fact nobody established
    into an index whose whole value is that it only says where to look.
    """
    if root.name != "skills":
        return ""
    if root.parent.name == ".claude":
        return "claude"
    if root.parent.name == ".agents":
        return "universal"
    return ""


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


def _run(
    command: list[str], cwd: Path, env: Optional[Mapping[str, str]] = None
) -> None:
    """Run a command, adding `env` on top of the inherited environment."""
    result = subprocess.run(
        command, cwd=cwd, check=False, env={**os.environ, **env} if env else None
    )
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


def upstream_fetch_commands(
    repo: str,
    ref: str,
    executable: str = "git",
) -> list[list[str]]:
    """Shallow-fetch exactly one upstream revision into an empty directory.

    `fetch <url> <ref>` rather than `clone --branch <ref>`, because clone's
    --branch accepts a tag or a branch and refuses a commit SHA. Naming a ref
    exists so an install can be pinned, and a moved tag pins nothing, so the
    one form that takes all three is the form worth having. A commit has to be
    named in full: the remote resolves the positional argument as a refspec,
    and an abbreviated SHA is not one.

    Checkout overrides line-ending conversion because Git for Windows enables
    `core.autocrlf` by default, which would rewrite every checked-out file to
    CRLF — the same commit would then install different bytes on Windows than
    everywhere else, and the shell script one upstream skill ships would land
    with a `#!/bin/bash\r` shebang that no POSIX shell can run.

    It also refuses the user's hooks, by two separate doors: `--template=`
    keeps `init.templateDir` from seeding this throwaway repository with them,
    and an unreadable `core.hooksPath` neutralizes a global setting, which the
    empty template does not cover. A `post-checkout` hook runs before anything
    is copied and can edit the working tree, which the commit check cannot see.
    """
    return [
        [executable, "init", "--quiet", "--template="],
        [executable, "fetch", "--quiet", "--depth", "1", repo, ref],
        [
            executable,
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
    ]


def matt_skills_fetch_commands(
    ref: str = MATT_SKILLS_REF,
    executable: str = "git",
) -> list[list[str]]:
    return upstream_fetch_commands(MATT_SKILLS_REPO, ref, executable)


def pstack_fetch_commands(
    ref: str = PSTACK_REF,
    executable: str = "git",
) -> list[list[str]]:
    return upstream_fetch_commands(PSTACK_REPO, ref, executable)


def require_git(flag: str) -> str:
    executable = shutil.which("git")
    if executable:
        return executable
    raise InstallError(
        f"{flag} requires git; install it from "
        "https://git-scm.com/downloads and rerun"
    )


def checkout_head(checkout: Path, executable: str = "git") -> str:
    """The full commit a checkout landed on, or "" when git cannot say.

    Two jobs: verifying that the pinned tag still points where this repository
    says it does, and provenance for the line printed after an install, since
    with `--matt-ref main` the ref alone does not identify what arrived.
    """
    result = subprocess.run(
        [executable, "rev-parse", "HEAD"],
        cwd=checkout,
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def checkout_worktree_changes(
    checkout: Path, executable: str = "git"
) -> Optional[str]:
    """What the checkout holds beyond the commit it fetched, or None if unknown.

    The commit check proves which revision was asked for, not what landed on
    disk. Anything that runs during checkout — a hook, a smudge filter — can
    edit the working tree afterwards and leave `rev-parse HEAD` still pointing
    at the pinned commit, so the bytes this installs would not be the bytes
    that commit contains. The same overrides as the checkout itself, or a
    global `core.autocrlf` would report every file as modified.
    """
    result = subprocess.run(
        [
            executable,
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.eol=lf",
            "status",
            "--porcelain",
        ],
        cwd=checkout,
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def checkout_content_mismatches(
    checkout: Path, executable: str = "git", prefix: str = "skills/"
) -> Optional[list[str]]:
    """Paths whose bytes on disk differ from the commit, or None if unknown.

    `git status` cannot answer this one. A `.gitattributes` in the fetched
    revision can set `eol`, which outranks the config the checkout passes and
    rewrites files on the way out — and status still calls the result clean,
    because it applies that same attribute on the way back in. Hashing the
    bytes as they actually sit on disk is the one comparison an attribute
    cannot reach, and it catches any other rewrite for free.

    Symlinks are skipped: hashing one reads whatever it points at rather than
    the link, and `git status` already covers a changed link.

    `prefix` narrows the comparison to the part of the revision that will
    actually be copied. It is the whole point for a collection that lives in a
    subdirectory of a monorepo: hashing every blob in cursor/plugins would
    check thousands of files that no install can reach, and an unrelated
    plugin's `.gitattributes` would then be able to stop a pstack install.
    """
    listing = subprocess.run(
        [executable, "ls-tree", "-r", "-z", "FETCH_HEAD", "--", prefix],
        cwd=checkout,
        check=False,
        text=True,
        capture_output=True,
    )
    if listing.returncode != 0:
        return None
    expected: dict[str, str] = {}
    for record in listing.stdout.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if len(fields) != 3 or not path:
            return None
        mode, kind, blob = fields
        if kind != "blob" or mode == "120000":
            continue
        # The batch protocol below is newline-separated, so a newline in a path
        # would silently verify the wrong file. Nothing upstream has one.
        if "\n" in path:
            return None
        expected[path] = blob
    if not expected:
        return None
    hashed = subprocess.run(
        [executable, "hash-object", "--no-filters", "--stdin-paths"],
        cwd=checkout,
        input="\n".join(expected) + "\n",
        check=False,
        text=True,
        capture_output=True,
    )
    actual = hashed.stdout.split()
    if hashed.returncode != 0 or len(actual) != len(expected):
        return None
    return sorted(
        path
        for (path, blob), found in zip(expected.items(), actual)
        if blob != found
    )


def _has_ancestor_skill(skill_dir: Path, root: Path) -> bool:
    """Whether a directory sits inside another skill, up to but excluding root.

    Asked of the filesystem rather than of whatever a caller has collected so
    far, because path order is not ancestor-first: `tdd/SKILL.md` sorts before
    `tdd/references/tdd/SKILL.md` on POSIX and after it on Windows, where paths
    compare as one case-folded string rather than component by component.
    """
    for parent in skill_dir.parents:
        if parent == root:
            break
        if (parent / "SKILL.md").is_file():
            return True
    return False


def collection_skill_sources(
    checkout: Path,
    source: str,
    subdir: str = "",
    skip: tuple = (),
) -> list[Path]:
    """Every skill directory in an upstream checkout, flattened by name.

    Upstream files skills under `skills/<category>/<name>/`, and every consumer
    — its own CLI included — installs them flat as `<name>/`. Discovery walks
    for `SKILL.md` rather than hard-coding those two levels, so a reorganization
    upstream costs nothing here; the price of flattening is that two categories
    could one day claim one name, which is a stop rather than a coin toss. That
    claim is compared case-insensitively, because `Foo` and `foo` are two
    directories in the checkout but one destination on Windows and on a stock
    macOS filesystem — the collision has to be caught before the second copy
    quietly replaces the first.

    `subdir` is the directory inside the checkout that holds the collection,
    empty when the repository *is* the collection. A monorepo plugin sets it,
    and `skills/` is still looked for underneath — the walk is rooted at the
    collection, so a sibling plugin's skills can never be picked up by it.
    """
    base = checkout / subdir if subdir else checkout
    root = base / "skills"
    if not root.is_dir():
        raise InstallError(
            f"{source} checkout has no skills/ directory: {base}"
        )
    sources: dict[str, Path] = {}
    for entrypoint in sorted(root.rglob("SKILL.md")):
        skill_dir = entrypoint.parent
        relative = skill_dir.relative_to(root)
        if relative.parts and relative.parts[0] in skip:
            continue
        # A skill may ship further SKILL.md files under references/; only the
        # outermost one names an installable skill.
        if _has_ancestor_skill(skill_dir, root):
            continue
        claimed = sources.get(skill_dir.name.casefold())
        if claimed is not None:
            raise InstallError(
                f"{source} has two skills named {skill_dir.name}: "
                f"{claimed.relative_to(checkout)} and {relative}"
            )
        sources[skill_dir.name.casefold()] = skill_dir
    return [sources[name] for name in sorted(sources)]


def matt_skill_sources(checkout: Path) -> list[Path]:
    return collection_skill_sources(
        checkout, MATT_SKILLS_SOURCE, "", MATT_SKILLS_SKIP
    )


def pstack_skill_sources(checkout: Path) -> list[Path]:
    return collection_skill_sources(
        checkout, PSTACK_SOURCE, PSTACK_SUBDIR, PSTACK_SKIP
    )


class UpstreamCollection(NamedTuple):
    """A third-party skill collection this installer fetches rather than owns.

    `ExternalTool` describes a row on the dashboard; this describes how to go
    and get one. They are separate because a row exists for graphify too, and
    graphify has its own CLI — there is nothing here to fetch.

    Both collections in this tuple are pinned, verified, and copied by exactly
    the same code. That is deliberate: the verification below is subtle enough
    that a second hand-written copy of it would drift, and a rewriting
    `.gitattributes` that one copy caught and the other did not is precisely
    the failure nobody would notice until it shipped.
    """

    tool: str
    source: str
    repo: str
    ref: str
    commit: str
    marker: str
    noun: str
    flag: str
    ref_flag: str
    pin_constant: str
    verify_prefix: str
    tmp_prefix: str
    subdir: str = ""
    skip: tuple = ()
    manifest: str = ""
    version: str = ""


MATT_SKILLS = UpstreamCollection(
    tool="matt-skills",
    source=MATT_SKILLS_SOURCE,
    repo=MATT_SKILLS_REPO,
    ref=MATT_SKILLS_REF,
    commit=MATT_SKILLS_COMMIT,
    marker="setup-matt-pocock-skills",
    noun="Matt Pocock skills",
    flag="--matt-skills",
    ref_flag="--matt-ref",
    pin_constant="MATT_SKILLS_COMMIT",
    verify_prefix="skills/",
    tmp_prefix="mattpocock-skills-",
    skip=MATT_SKILLS_SKIP,
)

PSTACK = UpstreamCollection(
    tool="pstack",
    source=PSTACK_SOURCE,
    repo=PSTACK_REPO,
    ref=PSTACK_REF,
    commit=PSTACK_COMMIT,
    marker="setup-pstack",
    noun="pstack skills",
    flag="--pstack",
    ref_flag="--pstack-ref",
    pin_constant="PSTACK_REF",
    # The whole plugin, not just its skills/: the manifest checked below sits
    # outside skills/, and a version this install trusts has to be covered by
    # the same hash comparison as the files it describes. Sibling plugins in
    # the monorepo stay outside it, so their churn cannot fail a pstack
    # install.
    verify_prefix=f"{PSTACK_SUBDIR}/",
    tmp_prefix="pstack-skills-",
    subdir=PSTACK_SUBDIR,
    skip=PSTACK_SKIP,
    manifest=PSTACK_MANIFEST,
    version=PSTACK_VERSION,
)

UPSTREAM_COLLECTIONS = (MATT_SKILLS, PSTACK)


def declared_version(checkout: Path, subdir: str, manifest: str) -> str:
    """The version a fetched collection declares for itself, or "".

    The readable half of a pin whose ref is a bare commit. cursor/plugins
    publishes no tags, so `PSTACK_REF` says nothing a human can check against a
    release note; the plugin manifest is where upstream writes the number it
    ships under. Absent, unreadable, or malformed all answer "" rather than
    raising, because the caller decides whether that is fatal — it is for the
    default pin, and it is not for `--pstack-ref main`.
    """
    path = (checkout / subdir if subdir else checkout) / manifest
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return ""
    version = loaded.get("version") if isinstance(loaded, dict) else None
    return version if isinstance(version, str) else ""


EXTERNAL_MANIFEST_FILE = ".skills-external.json"
EXTERNAL_MANIFEST_SCHEMA = 1


def read_external_manifest(root: Path) -> dict:
    """tool -> the skill names that tool last installed into this root.

    A root is one flat directory and nothing in a skill directory records where
    it came from, so without this file the only way to attribute an installed
    skill to the collection that placed it is to guess by name. That guess was
    survivable while one external tool hid skills from the model; pstack hides
    39 of the 44 it ships, so two rows would each claim the other's skills and
    the review screen would offer to unhide skills its row never installed.

    Missing or malformed reads as "nothing recorded" rather than raising: this
    is a record of what happened, and a root written by an older release simply
    has not got one.
    """
    record = root / EXTERNAL_MANIFEST_FILE
    try:
        loaded = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    tools = loaded.get("tools") if isinstance(loaded, dict) else None
    if not isinstance(tools, dict):
        return {}
    return {
        name: entry
        for name, entry in tools.items()
        if isinstance(entry, dict) and isinstance(entry.get("skills"), list)
    }


def external_skill_names(root: Path, tool: str) -> list[str]:
    """The skills one external tool installed into one root, newest record."""
    entry = read_external_manifest(root).get(tool)
    return sorted(str(name) for name in entry["skills"]) if entry else []


def record_external_install(
    root: Path, tool: str, names: Iterable[str], reference: str, head: str
) -> None:
    """Record which skills an external tool just placed in this root.

    Beside the receipt and with the same reasoning: the receipt says what this
    collection put here, and this says what somebody else's collection put here
    on this collection's behalf. Kept as one file per root rather than one per
    tool so a root carries a single answer to "who put this here", and rewritten
    whole for the tool that just ran — an update that drops a skill upstream
    should drop it here too, which is the bug the receipt reconciliation exists
    to catch for bundled skills.
    """
    taken = sorted(names)
    existing = read_external_manifest(root)
    # Ownership moves with the files. A forced install over another
    # collection's copy of `tdd` leaves that copy replaced on disk, so leaving
    # the old owner's claim in place would make its own next *update* look like
    # a conflict with itself and demand --force forever. One name, one owner,
    # and the owner is whoever wrote the directory last.
    surrendered = set()
    for other, entry in existing.items():
        if other == tool:
            continue
        kept = [name for name in entry["skills"] if str(name) not in set(taken)]
        surrendered.update(str(name) for name in entry["skills"] if name not in kept)
        entry["skills"] = kept
    if surrendered:
        # A visibility choice is keyed by name, and the name now means a
        # different skill. "Show me `tdd`" was said about the collection that
        # just lost it, so re-applying it here would silently unhide a skill
        # nobody has looked at -- the exact thing the review screen exists to
        # stop happening by accident.
        forget_model_decisions(root, surrendered)
    existing[tool] = {
        "ref": reference,
        "commit": head,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "skills": taken,
    }
    payload = {"schema": EXTERNAL_MANIFEST_SCHEMA, "tools": existing}
    root.mkdir(parents=True, exist_ok=True)
    (root / EXTERNAL_MANIFEST_FILE).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def external_conflicts(root: Path, tool: str, names: Iterable[str]) -> list[tuple]:
    """(skill, owner) for each name another collection already owns here.

    Two optional collections can claim one name — pstack and mattpocock/skills
    both ship `tdd` and `teach`, and they disagree about what those words mean.
    Installing over the top is not an error a moment later: nothing fails, and
    an agent asked to run `tdd` quietly runs somebody else's workflow instead.

    Owning is by record, not by presence, so re-running a collection over its
    own files is an update rather than a conflict — and this collection's own
    bundled skills, which the receipt records, are protected by the same pass.

    The record is new, though, and the commonest starting state is a machine
    that installed matt-skills with a release that never wrote one. Answering
    "nothing is owned here" for those roots would fail open on exactly the
    upgrade path this check exists for, so a collection with no record falls
    back to its marker: the marker directory is the one attribution that
    survives a root written before the record existed.
    """
    wanted = [str(name) for name in names]
    manifest = read_external_manifest(root)
    owners: dict = {}
    for other, entry in manifest.items():
        if other == tool:
            continue
        for name in entry["skills"]:
            owners[str(name)] = other
    # Only when this collection has never recorded an install here. Without
    # that guard an unrecorded copy of our own would read as somebody else's,
    # and a legacy collection could never update itself again without --force.
    if tool not in manifest and not (root / external_tool(tool).marker).is_dir():
        for other in UPSTREAM_COLLECTIONS:
            if other.tool == tool or other.tool in manifest:
                continue
            if not (root / other.marker).is_dir():
                continue
            for name in wanted:
                if (root / name).is_dir():
                    owners.setdefault(name, other.tool)
    receipt = read_receipt(root)
    if receipt is not None:
        for name in receipt.get("skills", []) or []:
            owners.setdefault(str(name), "this collection")
    return sorted((name, owners[name]) for name in wanted if name in owners)


def prune_external_manifest(root: Path, removed: Iterable[str], dry_run: bool) -> None:
    """Drop names from a root's external record, deleting it when empty.

    The mirror of `prune_receipt`, and needed for the same reason: the conflict
    message tells the reader to remove the other copy with `--uninstall`, and a
    record nothing can clear would make that advice false — the name would stay
    owned by a collection whose files are gone, and the install it was meant to
    unblock would keep being refused.
    """
    if dry_run:
        return
    manifest = read_external_manifest(root)
    if not manifest:
        return
    dropped = {str(name) for name in removed}
    remaining = {}
    changed = False
    for tool, entry in manifest.items():
        kept = [name for name in entry["skills"] if str(name) not in dropped]
        if len(kept) != len(entry["skills"]):
            changed = True
        if kept:
            remaining[tool] = {**entry, "skills": kept}
        else:
            # A record claiming nothing is a claim that nothing can clear.
            changed = True
    if not changed:
        return
    path = root / EXTERNAL_MANIFEST_FILE
    if not remaining:
        remove_path(path)
        return
    path.write_text(
        json.dumps({"schema": EXTERNAL_MANIFEST_SCHEMA, "tools": remaining}, indent=2)
        + "\n",
        encoding="utf-8",
    )


# The external collections this installer copies in itself, and therefore the
# only ones whose skills it can attribute. A tool installed by its own CLI
# (graphify) drops a directory here but never told us what it placed, so it can
# never be credited with an unclaimed skill -- crediting it by elimination let
# the graphify row list mattpocock's hidden skills and rewrite their frontmatter.
UPSTREAM_TOOL_NAMES = frozenset({MATT_SKILLS.tool, PSTACK.tool})


def externally_recorded(root: Path) -> set:
    """Every skill name any external collection recorded in this root."""
    return {
        str(name)
        for entry in read_external_manifest(root).values()
        for name in entry["skills"]
    }


class Ownership(NamedTuple):
    """Who claims `name` in `root`, according to every record that can claim it.

    There are three records now, not two. The receipt lists what this
    collection installed, `.skills-external.json` lists what an external
    collection placed *through* this installer, and the directory itself is
    the third. Before the external manifest existed, "is this ours" was a
    two-source question, and every caller answered it inline. Six of them did,
    each slightly differently, and each one written before the third record
    existed silently began answering about two thirds of the truth -- which is
    how an uninstall could report success while leaving an ownership claim
    behind, and how the machine-wide report went blind to exactly the
    collections whose reason for existing is that they collide.

    So the question is asked once, here. A seventh caller gets the whole
    answer by construction rather than by remembering.
    """

    name: str
    root: Path
    present: bool
    by_receipt: bool
    by_external: Optional[str]
    matches_checkout: bool

    @property
    def recorded(self) -> bool:
        """Whether any record claims it, on disk or not.

        The question the *absent* branch of an uninstall has to ask: a record
        surviving its directory is the thing that needs clearing, and asking
        only the receipt there is what made the conflict message's advertised
        remedy a no-op.
        """
        return self.by_receipt or self.by_external is not None

    @property
    def ours(self) -> bool:
        """Whether this installer may remove it without `--force`.

        A skill an external collection placed through this installer is ours
        to remove -- the conflict message says so -- even though it is in no
        receipt and matches no directory under `skills/`.
        """
        return self.recorded or self.matches_checkout


def ownership(root: Path, name: str) -> Ownership:
    """Reconcile every record that can claim `name` in `root`."""
    destination = root / name
    owners = {
        tool: entry["skills"]
        for tool, entry in read_external_manifest(root).items()
    }
    external = next((tool for tool, names in owners.items() if name in names), None)
    return Ownership(
        name=name,
        root=root,
        present=destination.exists() or destination.is_symlink(),
        by_receipt=name in receipt_skills(root),
        by_external=external,
        matches_checkout=trees_equal(destination, SOURCE_ROOT / name),
    )


def claimed_names(root: Path) -> set:
    """Every name any record in `root` claims, whatever placed it.

    `available_skills()` answers what this collection *could* install; this
    answers what this root actually has a claim on, which is the larger set
    once an external collection has written here.
    """
    return set(receipt_skills(root)) | externally_recorded(root)


def install_upstream(
    collection: UpstreamCollection,
    agents: Iterable[str],
    roots: list[Path],
    force: bool,
    dry_run: bool,
    emit: Callable[[str], None] = print,
    executable: Optional[str] = None,
    ref: Optional[str] = None,
    allow_conflicts: Optional[bool] = None,
) -> None:
    """Fetch one upstream revision, then copy it into the resolved roots.

    Every root gets the same files: the skills are agent-agnostic upstream, and
    the CLI this replaced wrote byte-identical trees to each agent it was given.
    `agents` is still validated so an unknown name fails here rather than
    installing somewhere the caller did not ask for.

    `force` and `allow_conflicts` answer two different questions and default to
    the same answer only because the command line spells them with one flag.
    `force` is `install_one`'s: replace a destination that differs. Taking a
    name from *another collection* is a separate decision, and the dashboard
    needs to say yes to the first and no to the second -- it passes `force=True`
    so an external row can offer "update", and that must not silently hand it
    somebody else's `tdd` as well.
    """
    expand_agents(agents)
    if ref is not None and not ref.strip():
        # `--matt-ref "$REF"` with an unset REF asked for a revision and named
        # none. Falling back to the pin would install something the caller did
        # not choose, which is the failure this flag exists to prevent.
        raise InstallError(
            f"{collection.ref_flag} was given an empty value; name a revision"
        )
    reference = collection.ref if ref is None else ref.strip()
    if dry_run:
        for command in upstream_fetch_commands(collection.repo, reference):
            emit(f"would run  {shlex.join(command)}")
        for root in roots:
            emit(f"would copy all discovered {collection.noun} -> {root}")
        return

    git = executable or require_git(collection.flag)
    with tempfile.TemporaryDirectory(prefix=collection.tmp_prefix) as directory:
        checkout = Path(directory)
        for command in upstream_fetch_commands(collection.repo, reference, git):
            _run(command, checkout, UPSTREAM_GIT_ENV)
        head = checkout_head(checkout, git)
        if reference == collection.ref:
            # A tag is a movable label. Checking it against the commit recorded
            # here is what makes the default install reproducible; without it, a
            # force-moved tag upstream changes what installs with no change in
            # this repository for anyone to review.
            if not head:
                raise InstallError(
                    f"could not read the commit behind {collection.source} "
                    f"{collection.ref}, so the pin cannot be verified"
                )
            if head != collection.commit:
                if collection.ref != collection.commit:
                    raise InstallError(
                        f"{collection.source} {collection.ref} now points at "
                        f"{head[:7]}, not the pinned {collection.commit[:7]}. The "
                        "tag moved upstream: review the difference and update "
                        f"{collection.pin_constant}, or name a revision with "
                        f"{collection.ref_flag}"
                    )
                # The pin is the commit itself, so there is no tag to have
                # moved: the fetch simply did not land where it was sent.
                raise InstallError(
                    f"{collection.source} was fetched at {collection.ref[:7]} "
                    f"but the checkout is on {head[:7]}, so nothing was installed"
                )
        changes = checkout_worktree_changes(checkout, git)
        if changes is None:
            raise InstallError(
                f"could not confirm the {collection.source} checkout matches "
                f"{reference}, so nothing was installed"
            )
        if changes:
            raise InstallError(
                f"the {collection.source} checkout does not match {reference} — "
                "a git hook or filter modified it, so nothing was installed. "
                f"First change: {changes.splitlines()[0].strip()}"
            )
        mismatched = checkout_content_mismatches(
            checkout, git, collection.verify_prefix
        )
        if mismatched is None:
            raise InstallError(
                f"could not confirm the {collection.source} checkout holds the "
                f"bytes of {reference}, so nothing was installed"
            )
        if mismatched:
            raise InstallError(
                f"the {collection.source} checkout does not hold the bytes of "
                f"{reference}: {len(mismatched)} file(s) differ, starting with "
                f"{mismatched[0]}. A .gitattributes in that revision, or a "
                "content filter, rewrote them; nothing was installed"
            )
        # After the byte check, never before: a version read out of a tree that
        # something rewrote on the way to disk is not evidence of anything.
        version = (
            declared_version(checkout, collection.subdir, collection.manifest)
            if collection.manifest
            else ""
        )
        if collection.manifest and reference == collection.ref:
            if version != collection.version:
                raise InstallError(
                    f"{collection.source} at {collection.ref[:7]} declares "
                    f"version {version or 'none'}, not the pinned "
                    f"{collection.version}. The pin and the release it names "
                    "have come apart: review the difference and update "
                    f"{collection.pin_constant} and its version together, or "
                    f"name a revision with {collection.ref_flag}"
                )
        sources = collection_skill_sources(
            checkout, collection.source, collection.subdir, collection.skip
        )
        if not any(source.name == collection.marker for source in sources):
            raise InstallError(
                f"{collection.source} at {reference} did not include "
                f"{collection.marker}"
            )
        names = [source.name for source in sources]
        # Every root is checked before any root is written, so a conflict in
        # the second one does not leave the first half-replaced.
        overwrite_others = force if allow_conflicts is None else allow_conflicts
        for destination_root in roots:
            conflicts = external_conflicts(destination_root, collection.tool, names)
            if conflicts and not overwrite_others:
                listed = ", ".join(
                    f"{name} (owned by {owner})" for name, owner in conflicts
                )
                removal = " ".join(f"--skill {name}" for name, _ in conflicts)
                raise InstallError(
                    f"{collection.source} ships {len(conflicts)} skill(s) that "
                    f"another collection already owns in {destination_root}: "
                    f"{listed}. One name is one directory, so installing would "
                    "replace them and an agent asked for that skill would get "
                    "this collection's version instead. Either rerun with "
                    "--force to replace them, or remove the other copy first "
                    f"with `--uninstall {removal}` — adding --force there too "
                    "if it was installed before this record existed, since "
                    "nothing then proves who put it there. Both back the old "
                    "copy up before touching it"
                )
        detail = ", ".join(
            part
            for part in (f"plugin {version}" if version else "", head[:7] if head else "")
            if part
        )
        emit(
            f"{collection.source} @ {reference}" + (f" ({detail})" if detail else "")
        )
        for destination_root in roots:
            # The record has to survive a copy that dies half way. `install_one`
            # refuses a destination it did not write, and this root is shared --
            # so one hand-placed directory under a name this collection ships
            # raises after earlier skills have already landed. Recording only on
            # the success path left those on disk with nothing claiming them:
            # the uninstaller then refuses to remove what this installer just
            # wrote, and every external row lists the union again, which is the
            # precise failure the manifest was added to prevent. The manifest
            # must never be emptier than the directory.
            copied: list[str] = []
            try:
                for source in sources:
                    emit(install_one(source, destination_root, "copy", force, False))
                    copied.append(source.name)
            except BaseException:
                # An *update* that dies half way must not shrink the record.
                # `record_external_install` rewrites this tool's entry whole, so
                # handing it only what this run managed to copy would un-claim
                # skills from the previous install that are still sitting on
                # disk -- turning a failed update into the same unownable state
                # a failed first install used to cause. The record is therefore
                # the union of what was already claimed and still present with
                # what just landed.
                surviving = {
                    name
                    for name in external_skill_names(destination_root, collection.tool)
                    if (destination_root / name).exists()
                }
                try:
                    record_external_install(
                        destination_root,
                        collection.tool,
                        sorted(surviving | set(copied)),
                        reference,
                        head,
                    )
                except OSError as exc:
                    # Best-effort, like every other write to this cache: losing
                    # the record is bad, but replacing the error that actually
                    # stopped the install is worse -- it hides the cause and
                    # downgrades an InstallError (exit 2) to an OSError (exit 1).
                    emit(f"note: could not record what landed in {destination_root}: {exc}")
                raise
            record_external_install(
                destination_root, collection.tool, copied, reference, head
            )
            # The copies just overwrote any frontmatter edits from an earlier
            # review, so the recorded choices must be re-applied here or an
            # update silently re-hides every skill the user enabled.
            apply_model_decisions(destination_root, emit)


def install_matt_skills(
    agents: Iterable[str],
    roots: list[Path],
    force: bool,
    dry_run: bool,
    emit: Callable[[str], None] = print,
    executable: Optional[str] = None,
    ref: Optional[str] = None,
    allow_conflicts: Optional[bool] = None,
) -> None:
    install_upstream(
        MATT_SKILLS, agents, roots, force, dry_run, emit, executable, ref,
        allow_conflicts,
    )


def install_pstack(
    agents: Iterable[str],
    roots: list[Path],
    force: bool,
    dry_run: bool,
    emit: Callable[[str], None] = print,
    executable: Optional[str] = None,
    ref: Optional[str] = None,
    allow_conflicts: Optional[bool] = None,
) -> None:
    install_upstream(
        PSTACK, agents, roots, force, dry_run, emit, executable, ref,
        allow_conflicts,
    )


MODEL_INVOCATION_KEY = "disable-model-invocation"
MODEL_DECISIONS_FILE = ".skills-model-invocation.json"


def skill_is_model_hidden(skill_dir: Path) -> bool:
    """Whether this skill's frontmatter hides it from the model's skill list.

    Upstream collections (mattpocock/skills hides 20 of the 35 it ships, and
    pstack 39 of its 44) set
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
        (root / MODEL_DECISIONS_FILE).write_text(
            json.dumps(
                {"schema_version": 1, "decisions": decisions},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def forget_model_decisions(root: Path, names: Iterable[str]) -> None:
    """Drop visibility choices for names this root no longer means the same by.

    Called when a name changes hands between collections. The decisions file is
    keyed by name and says nothing about which skill was being decided on, so a
    choice that outlives its skill is not a preference any more — it is an
    instruction aimed at a directory that has been replaced.
    """
    if not root.is_dir():
        return
    decisions = read_model_decisions([root])
    remaining = {
        name: choice
        for name, choice in decisions.items()
        if name not in set(names)
    }
    if remaining == decisions:
        return
    record = root / MODEL_DECISIONS_FILE
    if not remaining:
        remove_path(record)
        return
    record.write_text(
        json.dumps({"schema_version": 1, "decisions": remaining}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


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


def check_skill_name(name: str) -> None:
    """Raise unless `name` is a plain directory name, safe to join onto a root.

    The install side never needed this: `install_one` is only ever handed a
    name that `available_skills` produced. The uninstall side takes whatever
    `--skill` was given — deliberately, because the name most worth removing
    is the orphan that has already left the collection — and joins it onto a
    directory it is about to move away.

    Three values make that dangerous, and all three arrive by accident rather
    than by malice: `""` (a shell expanding an unset `--skill "$SKILL"`), for
    which `root / ""` is the root itself; `..` and anything containing a
    separator, which reach outside the root and land the backup outside the
    documented `.skills-backups/<root>/` layout as well; and `.`, which is the
    root under another spelling. Names also arrive from a receipt, whose JSON
    nothing has ever shape-checked, so the guard belongs at the join and not
    at the CLI.
    """
    if name in ("", ".", "..") or name != Path(name).name:
        raise InstallError(
            f"not a skill name: {name!r} (expected one plain directory name, "
            "with no path separators)"
        )


def uninstall_one(
    name: str,
    root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> str:
    """Remove one installed skill from one root, backing it up first.

    Beside `install_one` on purpose. Backups, receipts, and the refusal to
    touch what this collection did not put there are defined once for both
    directions; an uninstaller written anywhere else grows its own copy of the
    backup logic and then the two disagree about where a recovery lives.

    Four rules carry the risk:

    * `name` must be one plain directory name. `root / name` is a *delete*
      target, and `Path("/a/b") / ""` is `/a/b` itself while `root / "../x"`
      is a sibling of the root — so an empty `--skill "$UNSET_VAR"` moved a
      whole shared `~/.claude/skills` away, receipt and other tools' skills
      included, and reported success. The check runs before the `--force`
      branch on purpose: `--force` means "remove a directory that is not
      ours", never "remove something that is not a skill directory in this
      root", and the refusal message the caller sees invites `--force`.
    * An absent destination is a success. Removing nothing is a no-op, and a
      hook or a script that has to test for presence before every call would
      race with itself. Presence is `exists() or is_symlink()` — the same test
      `install_one` makes — so a broken symlink counts as present rather than
      being silently left behind.
    * A destination that is both absent from the receipt and unequal to
      `skills/<name>` is somebody else's, and is refused without `--force`.
      This is the mirror of `install_one` refusing to overwrite a differing
      destination, and it is what makes the uninstaller safe to point at
      `~/.claude/skills`, which is shared with tools this collection does not
      manage.
    * The root itself is never removed, however empty it gets, for the same
      reason.

    A name the receipt records but the disk no longer holds still leaves the
    receipt: an entry nothing can clear is exactly the `ORPHAN` state that sat
    in a receipt across two releases.
    """
    check_skill_name(name)
    destination = root / name
    if destination.parent.resolve() != root.resolve():
        # Defensive: check_skill_name already rules this out. Stated anyway
        # because the cost of the guard being wrong is a directory outside the
        # root being moved, and the invariant is cheaper to assert than to
        # re-derive from pathlib's join rules at the next edit.
        raise InstallError(f"refusing to remove outside {root}: {destination}")
    owner = ownership(root, name)
    if not owner.present:
        # Asked of every record, not just the receipt. A directory removed by
        # hand leaves its claim behind, and that stale claim is what blocks the
        # next install -- so the remedy the conflict message advertises has to
        # be able to clear it, whatever wrote it.
        if not owner.recorded:
            return f"absent  {destination}"
        if dry_run:
            return f"absent  {destination} (would clear it from the records)"
        forget_records(root, name, dry_run)
        return f"absent  {destination} (cleared from the records)"

    if not owner.ours and not force:
        raise InstallError(
            f"not installed by this collection: {destination} (absent from the "
            "receipt and from every external record, and differs from this "
            "checkout; rerun with --force to back it up and remove it anyway)"
        )

    backup = backup_path(root, name)
    if dry_run:
        return f"would remove {destination}; backup {backup}"

    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(destination), str(backup))
    forget_records(root, name, dry_run)
    return f"removed  {destination} (backup: {backup})"


def forget_records(root: Path, name: str, dry_run: bool) -> None:
    """Drop every record of `name` in `root`: receipt, ownership, visibility.

    All three or none. The visibility record is the one that was missed, and
    it is the one that bites silently: `disable-model-invocation` decisions are
    keyed by bare skill name, so a choice made about one collection's `tdd`
    was re-applied to a different collection's `tdd` the moment it replaced it
    -- unhiding, with no prompt, a skill nobody had looked at. The `--force`
    path of `record_external_install` already drops the decision when ownership
    changes hands; removal is the same event and needs the same rule.
    """
    prune_receipt(root, [name], dry_run)
    prune_external_manifest(root, [name], dry_run)
    if not dry_run:
        forget_model_decisions(root, [name])


def uninstall_names(
    root: Path,
    skills: Iterable[str] = (),
    all_skills: bool = False,
    orphans: bool = False,
) -> list[str]:
    """Which names an uninstall touches in one root.

    Per root, because `--all-skills` and `--orphans` are questions about a
    receipt and two roots rarely hold the same set: resolving them once for
    every root would remove a skill from a root that never recorded it.

    `--orphans` reads its answer from `root_status` rather than re-deriving it,
    so the command that clears an orphan and the report that names one can
    never disagree about which entries qualify.
    """
    if orphans:
        # A record whose directory is gone is an orphan whichever record holds
        # it. Reading only `root_status` answered for the receipt alone, so an
        # externally-owned name left behind by a hand-deleted directory had no
        # bulk command that could clear it -- reopening the very loop
        # `--orphans` exists to close, one record over.
        stale = {
            name
            for name in externally_recorded(root)
            if not (root / name).exists() and not (root / name).is_symlink()
        }
        return sorted(
            {item.name for item in root_status(root).skills if item.state == ORPHAN}
            | stale
        )
    if all_skills:
        # Every name any record claims, not just the receipt's. `uninstall_one`
        # already treats an externally-recorded skill as ours to remove -- the
        # conflict message says so -- and a bulk removal that skipped exactly
        # those left the manifest, and the index entry resting on it, alive
        # after everything had been removed.
        return sorted(claimed_names(root))
    return sorted(set(skills))


def uninstall_many(
    roots: Iterable[Path],
    skills: Iterable[str] = (),
    all_skills: bool = False,
    orphans: bool = False,
    force: bool = False,
    dry_run: bool = False,
    home: Optional[Path] = None,
    emit: Callable[[str], None] = print,
) -> list[str]:
    """Uninstall a selection across several roots, returning what happened.

    One path for the CLI and for a later dashboard, matching the rule that
    every install goes through `install_one`: the selection rules and the
    per-root resolution live here, and a second surface adds a screen rather
    than a second implementation of the same removal.

    Every line is emitted as it happens, not collected and handed back at the
    end. A removal is not reversible from the message alone -- the timestamped
    backup path is in it, and that path is the only way back -- so a refusal
    on the fourth name must not swallow the record of the three directories
    already moved. Returning the list as well keeps it testable.

    `home` is what lets a removal prune the roots index, and it is optional
    because the index is a cache: a caller that does not know which home to
    write to still uninstalls correctly, it just leaves an entry for a root
    that `machine_status` will then find empty and report as holding nothing.
    Getting that wrong costs a stale line in a report; refusing to uninstall
    without it would cost the removal.
    """
    messages: list[str] = []

    def say(message: str) -> str:
        messages.append(message)
        emit(message)
        return message

    for root in roots:
        names = uninstall_names(root, skills, all_skills, orphans)
        if not names:
            say(f"nothing to remove  {root}")
        for name in names:
            say(uninstall_one(name, root, force, dry_run))
        # Reached even when nothing was removed, and that is the whole point:
        # a root the index names but that holds nothing of ours -- deleted
        # project, receipt cleared by hand -- resolves to an empty selection,
        # and skipping the prune for exactly that case left an index entry no
        # command could ever clear. That is the loop `--orphans` was added to
        # close, one level up.
        if home is not None and not dry_run and not root_holds_collection(root):
            try:
                forget_root(root, home)
            except OSError as exc:
                # The skills are already gone; the index is a cache. Failing
                # the command here would report a removal that happened as a
                # run that failed.
                emit(f"note: could not update {roots_index_path(home)}: {exc}")
    return messages


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


def read_receipt(root: Path) -> Optional[dict]:
    """The receipt `root` was installed with, or None when it has none.

    `write_receipt` has recorded one on every install since the first release,
    but nothing read it back, so a receipt could disagree with the directory
    beside it indefinitely. Reading it is what turns "what is on disk" into
    "what was installed, and is it still that".
    """
    path = root / RECEIPT_NAME
    if not path.is_file():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return receipt if isinstance(receipt, dict) else None


def receipt_skills(root: Path) -> list[str]:
    """The names a root's receipt records, or [] when there is no usable one.

    The same shape-tolerant read `root_status` makes, factored out so the
    uninstaller and the reconciliation agree on what "the receipt says" means.
    A missing, unreadable, or malformed receipt answers "nothing recorded"
    rather than raising: that is the state a hand-copied root is already in,
    and refusing to answer would make the uninstaller unusable exactly where
    the receipt is what needs repairing.
    """
    receipt = read_receipt(root)
    if receipt is None:
        return []
    raw = receipt.get("skills", [])
    return [str(item) for item in raw] if isinstance(raw, list) else []


def prune_receipt(root: Path, removed: Iterable[str], dry_run: bool) -> None:
    """Drop names from a root's receipt, deleting it when nothing is left.

    Deliberately not `write_receipt` with a shorter list. That stamps the
    current VERSION and a fresh `installed_at`, so uninstalling one skill would
    silently re-date the others and silence the stale-receipt note
    `root_status` raises on them -- a removal would end up claiming an install
    it never performed. Only the recorded names change here.

    A receipt that reaches zero skills is deleted rather than kept as an empty
    list, because a receipt is the claim "this collection owns something here";
    keeping an empty one leaves the root reported as managed while this
    collection has nothing in it, and nothing would ever clear it.
    """
    if dry_run:
        return
    receipt = read_receipt(root)
    if receipt is None:
        return
    dropped = set(removed)
    raw = receipt.get("skills", [])
    recorded = [str(item) for item in raw] if isinstance(raw, list) else []
    remaining = [name for name in recorded if name not in dropped]
    if remaining == recorded:
        return
    path = root / RECEIPT_NAME
    if not remaining:
        path.unlink()
        return
    receipt["skills"] = remaining
    temporary = root / f"{RECEIPT_NAME}.tmp"
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class RootRecord(NamedTuple):
    """One line of the roots index: a place an install has been, and when.

    Paths and metadata only. It deliberately holds no skill names: the receipt
    in that root already records them, and a second copy of the same fact is
    exactly the drift `root_status` exists to catch -- it would have to be
    rewritten by every install *and* every uninstall to stay true, and the
    first time one of those failed the index would confidently name skills that
    are not there.
    """

    path: Path
    scope: str
    agent: str
    last_seen: str


def roots_index_path(home: Path) -> Path:
    """Where the roots index lives for a given home.

    Taking `home` rather than reading `Path.home()` is what lets `--home`
    redirect it, so a test -- or a cloud run with a throwaway home -- exercises
    the real code against its own file instead of appending to the developer's.
    """
    return home.expanduser() / ROOTS_INDEX_NAME


def known_roots(home: Path) -> list:
    """Every root the index records, or [] when it cannot be read.

    Missing, empty, truncated, malformed, or holding something that is not a
    list of objects all answer the same way: no roots. Mirroring
    `read_receipt`'s posture is the point -- this file is a cache, so the only
    thing worse than losing it would be letting a half-written copy of it break
    a scoped operation that never needed it. A caller that gets [] falls back
    to asking about the place it is standing in, which is what the whole tool
    did before this index existed.

    Entries missing a usable `path` are dropped rather than repaired: an entry
    that cannot name a directory cannot be checked, pruned, or reported on.
    """
    path = roots_index_path(home)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("roots", [])
    if not isinstance(raw, list):
        return []
    records = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        recorded = entry.get("path")
        if not isinstance(recorded, str) or not recorded.strip():
            continue
        records.append(
            RootRecord(
                Path(recorded),
                str(entry.get("scope", "")),
                str(entry.get("agent", "")),
                str(entry.get("last_seen", "")),
            )
        )
    return records


def _write_roots_index(home: Path, records: Iterable) -> None:
    """Replace the index with `records`, atomically, deleting it when empty.

    Same temp-file-and-`os.replace` as `write_receipt`, so a *reader* arriving
    mid-write sees the old file or the new one and never half of either. It
    does not make two writers safe -- that is `_update_roots_index`'s job, and
    conflating the two is why an earlier version of this docstring claimed a
    guarantee the code did not provide.

    The scratch file is uniquely named for the same reason. One index serves
    every root on the machine, so a fixed `.tmp` beside it is shared by every
    writer: one process's `os.replace` would move another's half-written file
    into place, and the loser's `os.replace` would then raise FileNotFoundError
    at a point where its skills are already installed.

    An index with nothing in it is removed rather than left as an empty list,
    matching `prune_receipt`: absent and empty already mean the same thing to
    `known_roots`, and keeping the file would leave a machine that installs
    nothing looking like one that is being tracked.
    """
    path = roots_index_path(home)
    entries = [
        {
            "path": str(record.path),
            "scope": record.scope,
            "agent": record.agent,
            "last_seen": record.last_seen,
        }
        for record in records
    ]
    if not entries:
        if path.is_file():
            path.unlink()
        return
    payload = {"schema_version": ROOTS_INDEX_SCHEMA, "roots": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, scratch = tempfile.mkstemp(
        prefix=f"{ROOTS_INDEX_NAME}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2) + "\n")
        os.replace(scratch, path)
    except Exception:
        remove_path(Path(scratch))
        raise


def _update_roots_index(home: Path, change: Callable[[list], list]) -> None:
    """Read the index, apply `change` to its records, and write the result.

    The read and the write have to be one operation. `os.replace` gives a
    reader an all-or-nothing file, but two installs that each read the index,
    append their own root, and write it back still lose one of the two roots:
    the second write is built on a list that predates the first. Nothing
    reports the gap, and the missing root only reappears if someone installs
    into it again -- so `--status --all` quietly stops describing a machine it
    claims to describe. Parallel installs are ordinary here: agent sessions run
    concurrently and the SessionStart sync hook can fire during a manual run.

    The lock is advisory and best-effort by design. Failing to take it falls
    through to writing anyway, because the cost of losing the race is one
    entry the next install restores, while the cost of honouring a lock file
    left behind by a killed process would be an installer that never finishes.
    """
    path = roots_index_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(f"{ROOTS_INDEX_NAME}.lock")
    handle = None
    deadline = time.monotonic() + ROOTS_INDEX_LOCK_SECONDS
    while handle is None:
        try:
            handle = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
    try:
        _write_roots_index(home, change(list(known_roots(home))))
    finally:
        if handle is not None:
            os.close(handle)
            try:
                lock.unlink()
            except OSError:
                pass


def remember_root(
    root: Path,
    scope: str,
    agent: str,
    home: Path,
    dry_run: bool = False,
) -> None:
    """Record that an install touched `root`, refreshing its `last_seen`.

    Called wherever `write_receipt` is, and honouring `--dry-run` the same way,
    so the index can never claim a root that was only ever described. The two
    together are the whole bookkeeping of an install: the receipt says what is
    in a root, this says the root exists at all.

    Deduped on the resolved path, and every entry is written resolved, so the
    same directory reached as `~/.claude/skills`, as a relative `--target`, or
    through a symlinked home is one entry rather than three that later report
    the same drift three times. An existing entry keeps its position instead of
    moving to the end, so reinstalling does not churn the file for no reason.

    `scope` is the label the invocation used, not a property the path has:
    `--target` names a directory directly and says nothing about whether it
    belongs to a user or a project, so the honest record is what was asked for.
    """
    if dry_run:
        return
    resolved = root.expanduser().resolve()
    entry = RootRecord(
        resolved, scope, agent, datetime.now(timezone.utc).isoformat()
    )

    def change(records: list) -> list:
        for index, record in enumerate(records):
            if record.path == resolved:
                records[index] = entry
                break
        else:
            records.append(entry)
        return records

    _update_roots_index(home, change)


def forget_root(root: Path, home: Path) -> None:
    """Drop `root` from the index.

    The uninstaller's half of the bookkeeping, and the reason the index was
    safe to write in the first place: an index nothing prunes accumulates
    every directory anyone ever pointed this installer at, and a machine-wide
    report made of stale entries is one nobody reads twice.

    Forgetting a root is not removing anything from disk. The directory, and
    whatever another tool put in it, is left exactly as it was -- this only
    stops the index claiming that this collection has business there.
    """
    resolved = root.expanduser().resolve()
    if not any(record.path == resolved for record in known_roots(home)):
        # Nothing to drop, so nothing to lock or rewrite. Checked before the
        # locked update rather than inside it because the common case is an
        # uninstall from a root nobody indexed, and rewriting the file to the
        # bytes it already holds would refresh nothing and race for no reason.
        return

    def change(records: list) -> list:
        return [record for record in records if record.path != resolved]

    _update_roots_index(home, change)


def root_holds_collection(root: Path) -> bool:
    """Whether anything from this collection is still in `root`.

    The condition `forget_root` is gated on. Asked through `root_status` rather
    than by listing the directory, because the directory is shared: another
    tool's skills, or a hand-copied one this collection never installed, are
    not a reason to keep an index entry, and an empty receipt with a stray
    file beside it would otherwise keep the root indexed forever.
    """
    return (
        bool(root_status(root).skills)
        or read_receipt(root) is not None
        or bool(read_external_manifest(root))
    )


class SkillReport(NamedTuple):
    name: str
    state: str
    detail: str


class RootReport(NamedTuple):
    root: Path
    receipt_version: Optional[str]
    receipt_mode: Optional[str]
    skills: tuple
    notes: tuple

    @property
    def managed(self) -> bool:
        return self.receipt_version is not None

    def actionable(self) -> list:
        return [item for item in self.skills if item.state in ACTIONABLE_STATES]


def root_status(root: Path, bundled: Optional[Iterable[str]] = None) -> RootReport:
    """Reconcile one destination root against its receipt and this checkout.

    Three sources have to agree: the receipt (what was installed), the
    directory (what is there now), and the collection (what exists to install).
    Comparing only two of them is what let a skill removed from the collection
    sit in a receipt for two releases without anything noticing.
    """
    names = sorted(bundled) if bundled is not None else available_skills()
    known = set(names)
    receipt = read_receipt(root)
    recorded = []
    mode = None
    version = None
    if receipt is not None:
        version = str(receipt.get("version", ""))
        mode = receipt.get("mode")
        raw = receipt.get("skills", [])
        recorded = [str(item) for item in raw] if isinstance(raw, list) else []

    notes = []
    if receipt is not None and version != VERSION:
        notes.append(
            f"receipt records {version or 'no version'}; this checkout is {VERSION}"
        )

    reports = []
    seen = set()
    for name in recorded:
        seen.add(name)
        destination = root / name
        exists = destination.exists() or destination.is_symlink()
        if name not in known:
            where = "still on disk" if exists else "already gone"
            reports.append(
                SkillReport(name, ORPHAN, f"not in this collection ({where})")
            )
            continue
        if not exists:
            reports.append(
                SkillReport(name, MISSING, "recorded installed but not on disk")
            )
            continue
        reports.append(_installed_report(name, destination, mode))

    # A skill can reach a root without a receipt entry: an older release, a
    # hand copy, or an install that named a different set. It is installed
    # either way, so it is reported either way.
    for name in names:
        if name in seen:
            continue
        destination = root / name
        if not (destination.exists() or destination.is_symlink()):
            continue
        installed = _installed_report(name, destination, mode)
        if receipt is None:
            reports.append(installed)
        elif installed.state == CURRENT:
            reports.append(
                SkillReport(name, UNTRACKED, "on disk but absent from the receipt")
            )
        else:
            # Being absent from the receipt is bookkeeping; differing from the
            # checkout is the thing that needs doing. Report the action, and
            # keep the receipt gap as detail rather than letting it mask this.
            reports.append(
                SkillReport(
                    name,
                    installed.state,
                    f"{installed.detail} (also absent from the receipt)",
                )
            )

    reports.sort(key=lambda item: item.name)
    return RootReport(root, version, mode, tuple(reports), tuple(notes))


def _installed_report(name: str, destination: Path, mode: Optional[str]) -> SkillReport:
    """Compare one installed destination against `skills/<name>`."""
    source = SOURCE_ROOT / name
    if not trees_equal(destination, source):
        return SkillReport(name, DRIFTED, "installed copy differs from this checkout")
    if mode and not destination_matches_mode(destination, mode):
        actual = "link" if destination.is_symlink() else "copy"
        return SkillReport(name, MODE_MISMATCH, f"on disk as a {actual}, receipt says {mode}")
    return SkillReport(name, CURRENT, "matches this checkout")


def collection_status(roots: Iterable[Path]) -> list:
    """One RootReport per root, skipping roots this collection never touched."""
    bundled = available_skills()
    reports = []
    for root in roots:
        if not root.is_dir() and not (root / RECEIPT_NAME).is_file():
            continue
        reports.append(root_status(root, bundled))
    return reports


class ShadowReport(NamedTuple):
    """One skill name found in more than one root, and every root holding it.

    `roots` names all of them and the report never says which one wins.
    Precedence between two skill directories is the harness's rule -- and a
    different rule in each harness -- so naming a winner here would be the
    confident wrong answer the receipt reconciliation exists to prevent. The
    collision is the fact; what to do about it is the reader's call.
    """

    name: str
    state: str
    roots: tuple
    detail: str


class MachineReport(NamedTuple):
    """Every indexed root at once, plus what only that view can see.

    `vanished` is kept apart from `reports` rather than folded in as another
    root with problems: an indexed directory that is gone is a stale cache
    entry, not a broken install, and counting it as work would make a report
    that never comes back clean on any machine where a project was deleted.

    `unreadable` is a root that is there but cannot be opened -- a
    TCC-protected directory on macOS, a root-owned project, a stale network
    mount. Separate from both, and unlike `vanished` it does count as work:
    it is the one case where the report is knowingly incomplete, and a clean
    exit code would tell a hook the machine is fine when nothing looked. One
    line either way, which is the point -- a single unreadable directory used
    to raise past every other root and answer nothing about the machine at all.
    """

    reports: tuple
    vanished: tuple
    shadowed: tuple
    unreadable: tuple = ()

    def actionable(self) -> list:
        return [item for item in self.shadowed if item.state in ACTIONABLE_STATES]


def _copies_agree(left: Path, right: Path) -> bool:
    """Whether two installed copies of one skill hold the same content.

    Both sides are resolved first, deliberately. This collection installs
    either as a copy or as a symlink to the same checkout, so a linked root and
    a copied root read identically while `trees_equal` on the raw paths would
    compare a link's target against a directory and call them different. The
    question shadowing answers is what an agent *reads*; which shape it is
    stored in is `MODE_MISMATCH`'s business, one root at a time.

    A broken link resolves to nothing and so agrees with nothing, which is the
    right answer: a root where the skill reads as empty genuinely differs from
    one where it reads.
    """
    try:
        return trees_equal(left.resolve(), right.resolve())
    except OSError:
        return False


def shadow_reports(roots: Iterable[Path]) -> list:
    """Which skill names appear in more than one of `roots`.

    Two states because they are not equally interesting. Identical copies in
    several roots are what a machine-wide install *produces* -- `--agent all`
    writes the same tree to .agents and to .claude on purpose -- so reporting
    each of those as a finding would bury the one case that matters under the
    normal shape of a healthy machine. Differing copies are the case that
    matters: the agent's behaviour then depends on which root it reads, and
    nothing on disk says which that is.
    """
    bundled = available_skills()
    found: dict = {}
    for root in roots:
        # A name the collection dropped can shadow too, and the root that still
        # holds it is the one nobody is looking at. Taking every claimed name
        # as well as the collection's is what keeps an orphan visible here --
        # and what keeps an *external* skill visible at all. Two collections
        # that ship the same name and disagree about it is the case shadowing
        # exists to catch; enumerating only bundled names looked straight past
        # it and printed "nothing to update".
        for name in sorted(set(bundled) | claimed_names(root)):
            destination = root / name
            if destination.exists() or destination.is_symlink():
                found.setdefault(name, []).append(destination)
    reports = []
    for name in sorted(found):
        copies = found[name]
        if len(copies) < 2:
            continue
        agree = all(_copies_agree(copies[0], other) for other in copies[1:])
        state = SHADOWED if agree else DIVERGENT
        detail = (
            "identical copies in {count} roots"
            if agree
            else "copies differ between {count} roots; which one an agent "
            "reads is its own rule, not this installer's"
        ).format(count=len(copies))
        reports.append(
            ShadowReport(name, state, tuple(copy.parent for copy in copies), detail)
        )
    return reports


def machine_status(home: Path) -> MachineReport:
    """Reconcile every root the index knows about, not just this one place.

    `root_status` was already scope-agnostic and already took an arbitrary
    root; what was missing was a list of them. Mapping the one over the other
    is the whole of the machine-wide answer, plus the shadowing pass that only
    becomes possible once more than one root is in view.

    An indexed root whose directory is gone is skipped and reported as
    `VANISHED` rather than reconciled. Deleting a project is a thing people do,
    and the index promised only to say where to look.

    A root that raises while being read costs one line, not the whole answer.
    Scoped `--status` asks about one place, so an unreadable directory there is
    the answer; `--all` asks about every place at once, and letting the first
    permission error escape meant one protected directory hid the state of
    every healthy root beside it.
    """
    live = []
    vanished = []
    for record in known_roots(home):
        root = record.path.expanduser()
        if root.is_dir() or (root / RECEIPT_NAME).is_file():
            live.append(root)
        else:
            vanished.append(record)
    bundled = available_skills()
    reports = []
    readable = []
    unreadable = []
    for root in live:
        try:
            reports.append(root_status(root, bundled))
        except OSError as exc:
            unreadable.append((root, str(exc)))
        else:
            readable.append(root)
    try:
        shadowed = shadow_reports(readable)
    except OSError as exc:
        # Same reasoning one level up: shadowing is the extra that the
        # machine-wide view makes possible, and losing it must not lose the
        # per-root reports that are the answer people came for.
        shadowed = []
        unreadable.append((home, str(exc)))
    return MachineReport(
        tuple(reports), tuple(vanished), tuple(shadowed), tuple(unreadable)
    )


def _normalized(text: str) -> str:
    """Content with platform line endings removed.

    A vendored file checked out on Windows and the same file on Linux differ by
    every line ending, so hashing raw bytes would report drift on one platform
    and nothing on the other. The hash has to describe content, not checkout.
    """
    return text.replace("\r\n", "\n")


def vendored_upstream_text(entrypoint: Path) -> Optional[str]:
    """The vendored file with its provenance note removed, or None.

    None means the note is gone, which is itself the drift: the note is what
    tells the next reader that editing this copy is the wrong move.
    """
    try:
        content = _normalized(entrypoint.read_text(encoding="utf-8"))
    except OSError:
        return None
    match = re.search(r"\n<!--\n.*?Source of truth.*?\n-->\n", content, re.S)
    if not match:
        return None
    return content[: match.start()] + content[match.end():]


def vendored_status() -> list:
    """One line per vendored skill whose bytes no longer match its upstream."""
    problems = []
    for entry in VENDORED_SKILLS:
        entrypoint = SOURCE_ROOT / entry.skill / entry.entrypoint
        if not entrypoint.is_file():
            problems.append(f"{entry.skill}: {entry.entrypoint} is missing")
            continue
        upstream = vendored_upstream_text(entrypoint)
        if upstream is None:
            problems.append(
                f"{entry.skill}: provenance note is gone, so the copy no longer "
                f"names {entry.upstream}"
            )
            continue
        digest = hashlib.sha256(upstream.encode("utf-8")).hexdigest()
        if digest != entry.sha256:
            problems.append(
                f"{entry.skill}: edited here instead of upstream -- re-sync from "
                f"{entry.upstream} at {entry.commit} (expected {entry.sha256[:12]}, "
                f"found {digest[:12]})"
            )
    return problems


class OriginStatus(NamedTuple):
    """Whether the checkout trails its remote, or whether that is knowable.

    `unknown` is deliberately not `behind`. An unpacked release archive has no
    `.git` at all, and a machine with no route to the remote cannot be asked;
    reporting either as work to do would mean every such install fails a check
    forever while being perfectly current.
    """

    state: str
    detail: str


ORIGIN_CURRENT = "current"
ORIGIN_BEHIND = "behind"
ORIGIN_UNKNOWN = "unknown"


def status_git(
    repo: Path,
    *arguments: str,
    timeout: Optional[float] = STATUS_GIT_TIMEOUT,
) -> Optional[str]:
    """Run one read-only git command in `repo`, or return None if it failed.

    Every freshness question shares this runner so the hardening is stated
    once: `STATUS_GIT_ENV` keeps a credential prompt from parking a status
    check forever, `STATUS_GIT_TIMEOUT` keeps an unreachable remote from doing
    the same without prompting anything, and None covers every way git can
    decline -- not installed, not a checkout, no remote, no route to it, no
    answer inside the budget. Callers turn that None into "unknown", which is
    why this swallows rather than raises: a dashboard asking how fresh it is
    must not die because the network is down, and must not hang because the
    network is merely silent.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **STATUS_GIT_ENV},
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def checkout_behind_origin(repo: Path = REPO_ROOT) -> OriginStatus:
    """How far this checkout trails its remote.

    "Up to date with the checkout" is worth nothing if the checkout itself is
    behind: every skill can match a source that is three commits stale. This
    costs a fetch, so it is opt-in rather than part of the default answer.
    """
    def git(*arguments: str) -> Optional[str]:
        return status_git(repo, *arguments)

    if git("rev-parse", "--is-inside-work-tree") != "true":
        return OriginStatus(
            ORIGIN_UNKNOWN,
            "not a git checkout, so there is no origin to compare "
            "(a release archive has none)",
        )
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return OriginStatus(
            ORIGIN_UNKNOWN, "checkout is not on a branch, so it has no upstream"
        )
    if git("fetch", "--quiet", "origin") is None:
        return OriginStatus(ORIGIN_UNKNOWN, "could not reach origin")
    counts = git("rev-list", "--left-right", "--count", f"{branch}...origin/{branch}")
    if not counts:
        return OriginStatus(ORIGIN_UNKNOWN, f"no origin/{branch} to compare against")
    try:
        ahead, behind = (int(part) for part in counts.split())
    except ValueError:
        return OriginStatus(
            ORIGIN_UNKNOWN, f"could not read how {branch} compares to origin/{branch}"
        )
    if behind:
        return OriginStatus(
            ORIGIN_BEHIND,
            f"{branch} is {behind} commit(s) behind origin/{branch}"
            f"{f' and {ahead} ahead' if ahead else ''}; `git pull` before installing",
        )
    return OriginStatus(ORIGIN_CURRENT, "up to date with origin")


class SkillFreshness(NamedTuple):
    """Per-skill answers to "how far does this checkout trail origin".

    `behind` maps a skill name to the number of commits on `origin/<branch>`
    that touch `skills/<name>/` and are not in HEAD. **A name is present only
    when the question was actually answered.** Absent means unknown, which is
    why this is a mapping rather than a count per requested name: filling an
    unanswerable name in as 0 would let the dashboard paint "up to date" over
    a machine that never reached the remote, and a confident wrong answer is
    the one failure the whole status side is written to avoid.

    `state` is the shared verdict -- `ORIGIN_BEHIND` when some skill trails,
    `ORIGIN_CURRENT` when every asked-about skill was checked and none does,
    `ORIGIN_UNKNOWN` when nothing could be checked -- reusing the vocabulary
    `checkout_behind_origin` already established, because it is the same
    question asked at a smaller grain. `detail` says why, in a sentence fit to
    show a person.
    """

    state: str
    detail: str
    behind: dict


def skills_behind_origin(
    names: Iterable[str],
    repo: Path = REPO_ROOT,
    fetch: bool = True,
) -> SkillFreshness:
    """How far behind origin each named skill in this checkout is.

    `checkout_behind_origin` answers this for the collection; a dashboard
    listing thirty rows wants it per row, so that "up to date with the
    checkout" can stop being mistaken for "up to date". One fetch serves every
    name -- the per-skill work is a local `rev-list` over the paths the remote
    moved, which costs nothing once the objects are here. Pass `fetch=False`
    when something already fetched in this pass, and the whole call stays
    local.

    The fetch is opt-in for the reason `checkout_behind_origin` states, and
    the reason bites harder here: this is the call a TUI is tempted to make
    while drawing its first frame. It must not. Bind it to a key, run it off
    the UI thread, and show "checking..." until it answers.

    Every failure degrades to unknown and none raises. No git, no `.git` (a
    release archive has none), a detached HEAD, no `origin/<branch>`, no route
    to the remote -- each leaves the name out of `behind` rather than claiming
    a number, because a dashboard that crashes when the network drops is worse
    than one that admits it does not know.

    This compares committed history only. A skill edited in the working tree
    and not committed is a different question, which `trees_equal` answers
    locally against the installed copy.
    """
    asked = list(dict.fromkeys(names))
    if status_git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        return SkillFreshness(
            ORIGIN_UNKNOWN,
            "not a git checkout, so there is no origin to compare "
            "(a release archive has none)",
            {},
        )
    branch = status_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return SkillFreshness(
            ORIGIN_UNKNOWN, "checkout is not on a branch, so it has no upstream", {}
        )
    if fetch and status_git(repo, "fetch", "--quiet", "origin") is None:
        return SkillFreshness(ORIGIN_UNKNOWN, "could not reach origin", {})
    remote = f"origin/{branch}"
    if status_git(repo, "rev-parse", "--verify", "--quiet", remote) is None:
        return SkillFreshness(
            ORIGIN_UNKNOWN, f"no {remote} to compare against", {}
        )
    behind = {}
    for name in asked:
        try:
            check_skill_name(name)
        except InstallError:
            continue
        # `:(literal)` because a pathspec is glob-by-default and a name is not
        # a pattern: `check_skill_name` stops separators, not `*`, and a `*`
        # read as a glob would count every skill's commits against one row.
        count = status_git(
            repo,
            "rev-list",
            "--count",
            f"HEAD..{remote}",
            "--",
            f":(literal)skills/{name}",
        )
        if count is None:
            continue
        try:
            behind[name] = int(count)
        except ValueError:
            continue
    if not behind:
        if not asked:
            return SkillFreshness(ORIGIN_CURRENT, f"up to date with {remote}", {})
        return SkillFreshness(
            ORIGIN_UNKNOWN, f"could not read how any skill compares to {remote}", {}
        )
    stale = sorted(name for name, count in behind.items() if count)
    if stale:
        return SkillFreshness(
            ORIGIN_BEHIND,
            f"{len(stale)} skill(s) behind {remote}: {', '.join(stale)}; "
            "`git pull` before installing",
            behind,
        )
    return SkillFreshness(ORIGIN_CURRENT, f"up to date with {remote}", behind)


# `--status` found work to do. Distinct from the error codes above on purpose:
# a hook needs to tell "the check ran and there is drift" apart from "the check
# itself broke", and both being 1 would make that impossible.
STATUS_ACTION_EXIT = 3


def status_lines(
    roots: Iterable[Path],
    check_origin: bool = False,
    machine: Optional[MachineReport] = None,
) -> tuple[list[str], bool]:
    """Rendered status, and whether anything needs a human.

    One function so `install.py --status`, `skills status`, and any hook that
    wants an answer all describe the same reconciliation rather than three that
    drift apart.

    `machine` widens the same report instead of replacing it: `--status --all`
    renders the roots the index knows about in the identical per-root format,
    then the two sections only that view can produce. A second renderer would
    have to be kept in step with this one by hand, and the first line to fall
    out of step would be the one a reader compares across the two.
    """
    lines = [f"collection {VERSION} at {REPO_ROOT}"]
    reports = machine.reports if machine is not None else collection_status(roots)
    pending = 0

    if not reports:
        lines.append("")
        if machine is None:
            lines.append("no destination root holds skills from this collection")
        elif machine.unreadable:
            lines.append("no indexed root could be read; see below")
        elif machine.vanished:
            lines.append("every root the index knows about is gone")
        else:
            lines.append(
                "the roots index records no root yet; it is written by installs, "
                "so a machine that installed before this release has none until "
                "the next one"
            )
    for report in reports:
        lines.append("")
        lines.append(str(report.root))
        if not report.managed:
            lines.append("  (no receipt; reporting what is on disk)")
        for note in report.notes:
            lines.append(f"  ! {note}")
        actionable = report.actionable()
        pending += len(actionable)
        if not report.skills:
            lines.append("  nothing from this collection is installed here")
            continue
        width = max(len(item.name) for item in report.skills)
        for item in report.skills:
            lines.append(f"  {item.state:<9} {item.name:<{width}}  {item.detail}")

    if machine is not None and machine.vanished:
        # Listed, never counted. A directory the index still names is a stale
        # cache entry to offer to prune, and adding it to `pending` would mean
        # a machine where one project was deleted could never report clean.
        lines.append("")
        lines.append("indexed roots that no longer exist")
        width = max(len(record.scope) or 1 for record in machine.vanished)
        for record in machine.vanished:
            lines.append(f"  {VANISHED:<9} {record.scope:<{width}}  {record.path}")

    if machine is not None and machine.unreadable:
        # Counted, unlike `vanished`. A root that is gone is a stale cache
        # entry and answering "nothing to update" about it is true; a root
        # that could not be read is an answer this report does not have, and
        # exiting 0 on it would tell a hook the machine is clean when nobody
        # looked.
        lines.append("")
        lines.append("indexed roots that could not be read")
        pending += len(machine.unreadable)
        for root, detail in machine.unreadable:
            lines.append(f"  unreadable  {root}  {detail}")

    if machine is not None and machine.shadowed:
        lines.append("")
        lines.append("installed in more than one root")
        pending += len(machine.actionable())
        divergent = [item for item in machine.shadowed if item.state == DIVERGENT]
        agreeing = [item for item in machine.shadowed if item.state != DIVERGENT]
        # Identical copies in several roots are what a machine-wide install
        # *produces*, and once external collections are counted there are
        # dozens of them: listing each with its roots buried the divergent
        # case under two hundred lines of healthy machine. So the agreeing
        # half is one count, and the full treatment is spent on the half that
        # actually needs a decision.
        if agreeing:
            lines.append(
                f"  {SHADOWED:<9} {len(agreeing)} name(s) appear identically in "
                "more than one root; nothing to do"
            )
        width = max((len(item.name) for item in divergent), default=1)
        for item in divergent:
            lines.append(f"  {item.state:<9} {item.name:<{width}}  {item.detail}")
            # Every root, every time, and no verdict on which of them wins:
            # the reader knows their harness's precedence rule and this does
            # not, so the useful thing to hand them is the full list.
            for shadow_root in item.roots:
                lines.append(f"            {shadow_root}")

    vendored = vendored_status()
    if vendored:
        pending += len(vendored)
        lines.append("")
        lines.append("vendored copies")
        for problem in vendored:
            lines.append(f"  drifted   {problem}")

    if check_origin:
        origin = checkout_behind_origin()
        lines.append("")
        lines.append("checkout")
        lines.append(f"  {origin.state:<9} {origin.detail}")
        if origin.state == ORIGIN_BEHIND:
            # A stale checkout makes every "current" above meaningless, so it
            # counts as work even when no installed skill differs from it.
            # `unknown` does not: not being able to tell is not a finding, and
            # an archive install would otherwise never report a clean run.
            pending += 1

    lines.append("")
    lines.append(
        "nothing to update"
        if not pending
        else f"{pending} item(s) need attention"
    )
    return lines, bool(pending)


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


def _write_managed_file(path: Path, text: str, dry_run: bool) -> str:
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
        f"  {'matt-skills'.ljust(width)}  external, needs git",
        f"      {external_tool('matt-skills').summary}. Its `code-review` shares",
        "      a name with Claude's built-in and replaces it for the session.",
        f"  {'pstack'.ljust(width)}  external, needs git",
        f"      {external_tool('pstack').summary}. Written for Cursor: several",
        "      of its skills name Cursor-only tools and model slugs.",
        "",
        "Commands:",
        f"  everything suggested   {installer}{suggested}",
        f"  named skills only      {installer} --skill NAME [--skill NAME ...]",
        f"  this repo only         {installer} --skill NAME --scope project",
        f"  global instructions    {installer} --global-instructions",
        f"  graphify               {installer} --graphify",
        f"  matt-skills            {installer} --matt-skills",
        f"  pstack                 {installer} --pstack",
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
        messages.append(_write_managed_file(path, remaining, dry_run))
    return messages


class _RecordScope(argparse.Action):
    """Store `--scope` and remember that it was typed.

    A default and a typed value are the same string once argparse is done, so
    nothing downstream can tell `--all` from `--all --scope user`. One of those
    is a coherent request and the other contradicts itself, and rejecting the
    second means knowing which happened. A second attribute is the cheapest
    way to know without giving `--scope` a sentinel default that every existing
    reader of `args.scope` would then have to resolve.
    """

    def __call__(self, parser_, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, "scope_given", True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Install this collection into shared or agent-specific skill "
            "directories, or uninstall what it installed there."
        )
    )
    result.add_argument(
        "--agent",
        action="append",
        default=[],
        metavar="NAME",
        help="universal, codex, cursor, copilot, claude, or all (repeatable; default all)",
    )
    result.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        action=_RecordScope,
    )
    result.set_defaults(scope_given=False)
    result.add_argument("--project-dir", type=Path, default=Path.cwd())
    result.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    result.add_argument("--target", type=Path, help="override the resolved skills root")
    result.add_argument(
        "--skill",
        action="append",
        default=[],
        metavar="NAME",
        help="a skill to install, or with --uninstall to remove (repeatable)",
    )
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
        "--matt-ref",
        default=None,
        metavar="REF",
        help=(
            "with --matt-skills: the tag, branch, or commit of mattpocock/skills "
            f"to install (default: {MATT_SKILLS_REF}; pass main to track upstream)"
        ),
    )
    pstack = result.add_mutually_exclusive_group()
    pstack.add_argument(
        "--pstack",
        dest="pstack",
        action="store_true",
        help="install all pstack skills for the selected agents",
    )
    pstack.add_argument(
        "--no-pstack",
        dest="pstack",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    result.set_defaults(pstack=None)
    result.add_argument(
        "--pstack-ref",
        default=None,
        metavar="REF",
        help=(
            "with --pstack: the tag, branch, or commit of cursor/plugins to "
            f"install pstack from (default: {PSTACK_REF[:7]}, which ships "
            f"pstack {PSTACK_VERSION}; pass main to track upstream)"
        ),
    )
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
    result.add_argument(
        "--uninstall",
        action="store_true",
        help=(
            "remove skills from the selected roots instead of installing: name "
            "them with --skill, or take a whole receipt with --all-skills or "
            "--orphans. Each removal is backed up first, and a skill this "
            "collection did not install is refused unless you pass --force"
        ),
    )
    result.add_argument(
        "--all-skills",
        action="store_true",
        help="with --uninstall: remove every skill each root's receipt records",
    )
    result.add_argument(
        "--orphans",
        action="store_true",
        help=(
            "with --uninstall: remove only the receipt entries whose skill has "
            "left this collection, the state --status reports as `orphan`"
        ),
    )
    result.add_argument("--force", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--list", action="store_true", help="list bundled skills and exit")
    result.add_argument(
        "--status",
        action="store_true",
        help="report which managed skills need updating, then exit",
    )
    result.add_argument(
        "--all",
        dest="all_roots",
        action="store_true",
        help=(
            "with --status: report every root this installer has recorded "
            "touching, on the whole machine, plus any skill installed in more "
            "than one of them. Cannot be combined with --scope or --target, "
            "which ask about one place"
        ),
    )
    result.add_argument(
        "--check-origin",
        action="store_true",
        help="with --status, also fetch and report whether this checkout is behind",
    )
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
        (args.matt_ref is not None, "--matt-ref"),
        (args.pstack, "--pstack"),
        (args.pstack_ref is not None, "--pstack-ref"),
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
        # Beside the receipt, on purpose and with the same dry-run guard. The
        # receipt says what is in this root; the index says the root exists at
        # all, which is the only reason a later `--status --all` can find a
        # project nobody is standing in. A `--target` install is recorded too:
        # an explicit root is still a root you will want to see later.
        #
        # Wrapped because the index lives in $HOME and the install may not:
        # a read-only or ephemeral home is normal in CI and in containers, and
        # letting a failed cache write escape turned a `--scope project`
        # install that had already written .agents into exit 1 *and* skipped
        # the .claude root entirely. The index's own contract is that deleting
        # it breaks nothing, so failing to write it must break nothing either
        # -- the receipt is the record, and the next install rewrites the entry.
        try:
            remember_root(root, args.scope, root_agent(root), args.home, args.dry_run)
        except OSError as exc:
            print(f"note: could not record {root} in {roots_index_path(args.home)}: {exc}")
    if args.matt_skills:
        install_matt_skills(
            args.agent,
            roots,
            args.force,
            args.dry_run,
            print,
            getattr(args, "matt_git", None),
            getattr(args, "matt_ref", None),
        )
    # After matt-skills, on purpose: the two collections share two skill names,
    # so whichever runs second is the one that finds the conflict and says so.
    # Running pstack second makes that message name the collection the caller
    # is more likely to be adding to an existing machine.
    if args.pstack:
        install_pstack(
            args.agent,
            roots,
            args.force,
            args.dry_run,
            print,
            getattr(args, "pstack_git", None),
            getattr(args, "pstack_ref", None),
        )
    if (args.matt_skills or args.pstack) and not args.dry_run:
        # An external collection writes real skills into a real root, and that
        # root is exactly as worth finding later as one this collection wrote
        # to -- more so, because a root holding only external skills has no
        # receipt, so nothing else in the index would ever name it. Without
        # this, `--status --all` was blind to any machine whose only install
        # was `--pstack`, and the shadowing pass that exists to catch two
        # collections disagreeing about `tdd` never saw either copy.
        for root in roots:
            try:
                remember_root(root, args.scope, root_agent(root), args.home, False)
            except OSError as exc:
                print(
                    f"note: could not record {root} in "
                    f"{roots_index_path(args.home)}: {exc}"
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
    fetched = [
        collection
        for collection, wanted in (
            (MATT_SKILLS, args.matt_skills),
            (PSTACK, args.pstack),
        )
        if wanted
    ]
    if fetched and not args.dry_run:
        for collection in fetched:
            print(
                f"Next: run /{collection.marker} once inside the target "
                "repository to finish configuring the workflows."
            )
        # One message for both, because the count is of a root and not of a
        # collection: a machine with both installed has one list of hidden
        # skills, and two messages counting overlapping halves of it would be
        # arithmetic the reader has to do.
        undecided = {
            name for root in roots for name in hidden_skills(root)
        } - set(read_model_decisions(roots))
        if undecided:
            rows = " or ".join(collection.tool for collection in fetched)
            print(
                f"{len(undecided)} skill(s) installed hidden from the model's "
                f"skill list; select {rows} in the dashboard to review "
                "them, or enable one directly with --enable-skill NAME."
            )
    if not args.dry_run:
        hint = launcher_hint()
        if hint:
            print(hint)


def execute_uninstall(args: argparse.Namespace) -> int:
    """Handle --uninstall and exit.

    Reached before every other dispatch so that a command line asking for a
    removal cannot quietly do something else instead: every flag that would
    have won the dispatch, or that only describes an install, is rejected by
    name rather than ignored. Ignoring one is how `--uninstall --status` would
    print a clean report and leave the skills in place.

    Selecting names is not validated against the collection, on purpose. The
    name most worth removing is the one that has *left* the collection, so a
    bundled-skill check here would reject exactly the orphan the command
    exists to clear.
    """
    for present, flag in (
        (args.list, "--list"),
        (args.status, "--status"),
        # Rejected by name rather than ignored because `--uninstall --all`
        # reads like "remove it everywhere", and it is not: `--all` widens a
        # *report* to the whole machine. Silently doing something narrower
        # than that reading -- or wider -- is the one mistake this flag pair
        # must not make.
        (args.all_roots, "--all"),
        (args.setup_path, "--setup-path"),
        (args.cloud_bootstrap, "--cloud-bootstrap"),
        (args.graphify, "--graphify"),
        (bool(args.matt_skills), "--matt-skills"),
        (args.matt_ref is not None, "--matt-ref"),
        (bool(args.pstack), "--pstack"),
        (args.pstack_ref is not None, "--pstack-ref"),
        (args.global_instructions is not None, "--global-instructions"),
        (bool(args.enable_skill), "--enable-skill"),
        (bool(args.hide_skill), "--hide-skill"),
        (args.interactive, "--interactive"),
    ):
        if present:
            raise InstallError(
                f"--uninstall does not combine with {flag}; run them as two commands"
            )
    if not args.uninstall:
        flag = "--all-skills" if args.all_skills else "--orphans"
        raise InstallError(
            f"{flag} only selects what to remove; add --uninstall to remove it"
        )
    if args.all_skills and args.orphans:
        raise InstallError(
            "--all-skills already covers --orphans; pass one or the other"
        )
    if args.skill and (args.all_skills or args.orphans):
        wider = "--all-skills" if args.all_skills else "--orphans"
        raise InstallError(
            f"--skill names an exact set and {wider} takes a whole receipt; "
            "pass one or the other"
        )
    if not (args.skill or args.all_skills or args.orphans):
        # Defaulting to everything is the one thing an uninstaller must never
        # do: the install default is recoverable, this one deletes work.
        raise InstallError(
            "--uninstall needs to know what to remove: --skill NAME, "
            "--all-skills, or --orphans"
        )
    # `print` rather than a loop over the return value: a refusal or an I/O
    # error partway through has to leave the already-removed skills' backup
    # paths on stdout, and a caller that only reads the returned list sees
    # nothing at all when the call raises.
    uninstall_many(
        stage_roots(args, args.scope),
        args.skill,
        args.all_skills,
        args.orphans,
        args.force,
        args.dry_run,
        args.home,
        print,
    )
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
        if args.uninstall or args.all_skills or args.orphans:
            # Ahead of every other branch so a removal cannot be silently
            # traded for a report or an install; the combinations are rejected
            # inside rather than resolved by dispatch order.
            return execute_uninstall(args)
        if args.all_roots:
            # `--all` asks about the machine; `--scope` and `--target` each
            # name one place. Answering a contradiction by picking whichever
            # the dispatch order happens to favour is how a report ends up
            # describing somewhere the caller did not ask about.
            # `--agent` belongs in this list for the same reason as the other
            # two: it is resolved by the same `resolve_roots`, and narrowing
            # to one agent's convention is narrowing to a place. Ignoring it
            # answered a request for "the Claude roots on this machine" with
            # every root on the machine, silently.
            elsewhere = (
                "--scope"
                if getattr(args, "scope_given", False)
                else "--target" if args.target is not None
                else "--agent" if args.agent
                else ""
            )
            if elsewhere:
                raise InstallError(
                    f"--all asks about the whole machine and {elsewhere} asks "
                    "about one place; pass one or the other"
                )
            if not args.status:
                raise InstallError(
                    "--all widens what --status reports; add --status to see it"
                )
        if args.list:
            print("\n".join(bundled))
            return 0
        if args.status:
            # Read-only, and reachable with no terminal: a hook or a CI job is
            # the caller that most needs this answer.
            machine = machine_status(args.home) if args.all_roots else None
            lines, pending = status_lines(
                [] if machine is not None else stage_roots(args, args.scope),
                args.check_origin,
                machine,
            )
            print("\n".join(lines))
            return STATUS_ACTION_EXIT if pending else 0
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
        if args.matt_ref is not None and not args.matt_skills:
            # Ignoring it would install the pinned revision under a command line
            # that asked for another one, which is the failure this flag exists
            # to prevent.
            raise InstallError(
                "--matt-ref only applies to --matt-skills; add --matt-skills to "
                "install that revision"
            )
        if args.pstack_ref is not None and not args.pstack:
            raise InstallError(
                "--pstack-ref only applies to --pstack; add --pstack to "
                "install that revision"
            )
        if args.graphify and args.target is not None:
            raise InstallError(
                "--graphify cannot be combined with --target; use --scope instead"
            )
        if args.matt_skills and not args.dry_run:
            args.matt_git = require_git("--matt-skills")
        if args.pstack and not args.dry_run:
            args.pstack_git = require_git("--pstack")
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
