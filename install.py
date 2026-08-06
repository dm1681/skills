#!/usr/bin/env python3
"""Install skills from this repository into supported agent directories."""

from __future__ import annotations

import argparse
import atexit
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
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Optional, TextIO


REPO_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = REPO_ROOT / "skills"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

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


class Console:
    """Small dependency-free terminal UI with accessible fallbacks."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

    def __init__(
        self,
        stdin: TextIO = sys.stdin,
        stdout: TextIO = sys.stdout,
        *,
        color: Optional[bool] = None,
        unicode: Optional[bool] = None,
        width: Optional[int] = None,
        key_reader: Optional[Callable[[], str]] = None,
        terminal_restore: Optional[Callable[[], None]] = None,
    ) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self._width = width
        self._written_lines = 0
        tty = _isatty(stdout)
        self.color = (
            color
            if color is not None
            else tty
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM", "") != "dumb"
        )
        encoding = getattr(stdout, "encoding", None) or "utf-8"
        unicode_capable = _can_encode(encoding, "◆✓›")
        self.unicode = unicode if unicode is not None else tty and unicode_capable
        self._key_reader = key_reader
        self._terminal_restore = terminal_restore
        if key_reader is not None:
            self.supports_navigation = True
        elif _isatty(stdin) and tty:
            supported, restore = _prepare_terminal_navigation(stdin, stdout)
            self.supports_navigation = supported
            self._terminal_restore = restore
        else:
            self.supports_navigation = False
        if self._terminal_restore is not None:
            atexit.register(self._terminal_restore)

    @property
    def width(self) -> int:
        if self._width is not None:
            return max(20, self._width)
        columns = shutil.get_terminal_size((88, 24)).columns
        return max(20, min(columns, 100))

    def styled(self, text: str, *styles: str) -> str:
        if not self.color or not styles:
            return text
        return "".join(styles) + text + self.RESET

    def write(self, text: str = "") -> None:
        self._written_lines += text.count("\n") + 1
        self.stdout.write(text + "\n")
        self.stdout.flush()

    def wrap(
        self,
        text: str,
        *,
        indent: int = 0,
        subsequent: Optional[int] = None,
        break_long_words: bool = False,
        right_margin: int = 0,
    ) -> None:
        later = indent if subsequent is None else subsequent
        rendered = textwrap.fill(
            text,
            width=max(10, self.width - right_margin),
            initial_indent=" " * indent,
            subsequent_indent=" " * later,
            break_long_words=break_long_words,
            break_on_hyphens=break_long_words,
        )
        self.write(rendered)

    def header(self) -> None:
        mark = "◆" if self.unicode else "*"
        self.write()
        self.write(self.styled(f"{mark} Skills setup", self.BOLD, self.CYAN))
        self.wrap(
            f"Version {VERSION} · Install portable skills across machines and coding agents.",
            indent=2,
        )

    def section(self, title: str) -> None:
        mark = "◆" if self.unicode else ">"
        self.write()
        self.write(self.styled(f"{mark} {title}", self.BOLD))

    def option(
        self,
        number: int,
        label: str,
        description: str,
        recommended: bool = False,
    ) -> None:
        suffix = " · recommended" if recommended else ""
        self.wrap(f"{number}. {label}{suffix}", indent=2, subsequent=5)
        self.wrap(description, indent=5)

    def ask(self, question: str, default: Optional[str] = None) -> str:
        self.wrap(question, indent=2)
        hint = f" [{default}]" if default is not None else ""
        marker = "›" if self.unicode else ">"
        self.stdout.write(self.styled(f"  {marker}{hint} ", self.CYAN))
        self.stdout.flush()
        value = self.stdin.readline()
        if value == "":
            raise InstallError("input ended before setup was complete")
        self.write()
        value = value.strip()
        return value if value else (default or "")

    def note(self, text: str) -> None:
        mark = "•" if self.unicode else "-"
        self.wrap(
            f"{mark} {text}",
            indent=2,
            subsequent=4,
            break_long_words=True,
        )

    def warning(self, text: str) -> None:
        self.wrap(
            self.styled(f"! {text}", self.YELLOW),
            indent=2,
            subsequent=4,
            break_long_words=True,
        )

    def error(self, text: str) -> None:
        mark = "×" if self.unicode else "x"
        self.wrap(
            self.styled(f"{mark} {text}", self.RED),
            indent=2,
            subsequent=4,
            break_long_words=True,
        )

    def success(self, text: str) -> None:
        mark = "✓" if self.unicode else "ok"
        self.wrap(
            self.styled(f"{mark} {text}", self.GREEN, self.BOLD),
            indent=2,
            subsequent=5,
            break_long_words=True,
        )

    def summary(self, rows: list[tuple[str, str]]) -> None:
        label_width = max(len(label) for label, _ in rows)
        if self.width >= 68:
            for label, value in rows:
                prefix = f"{label:<{label_width}}  "
                self.wrap(
                    prefix + value,
                    indent=2,
                    subsequent=4 + label_width,
                    break_long_words=True,
                )
        else:
            for label, value in rows:
                self.write(self.styled(f"  {label}", self.DIM))
                self.wrap(value, indent=4, break_long_words=True)

    @contextmanager
    def navigation_keys(self) -> Iterator[Callable[[], str]]:
        if self._key_reader is not None:
            yield self._key_reader
            return
        with _terminal_key_reader(self.stdin) as reader:
            yield reader

    def close(self) -> None:
        if self._terminal_restore is None:
            return
        restore = self._terminal_restore
        self._terminal_restore = None
        try:
            restore()
        finally:
            atexit.unregister(restore)


def _isatty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def _can_encode(encoding: str, value: str) -> bool:
    try:
        value.encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def _prepare_terminal_navigation(
    stdin: TextIO, stdout: TextIO
) -> tuple[bool, Optional[Callable[[], None]]]:
    try:
        input_fd = stdin.fileno()
        output_fd = stdout.fileno()
        if not os.isatty(input_fd) or not os.isatty(output_fd):
            return False, None
    except (AttributeError, OSError):
        return False, None
    if os.name != "nt":
        return os.environ.get("TERM", "") != "dumb", None
    restore = _enable_windows_virtual_terminal(stdout)
    return restore is not None, restore


def _enable_windows_virtual_terminal(
    stdout: TextIO,
) -> Optional[Callable[[], None]]:
    if os.name != "nt":
        return None
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(stdout.fileno()))
        mode = wintypes.DWORD()
        kernel32 = ctypes.windll.kernel32
        get_console_mode = kernel32.GetConsoleMode
        get_console_mode.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_console_mode.restype = wintypes.BOOL
        set_console_mode = kernel32.SetConsoleMode
        set_console_mode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        set_console_mode.restype = wintypes.BOOL
        if not get_console_mode(handle, ctypes.byref(mode)):
            return None
        previous = mode.value
        enabled = mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if not set_console_mode(handle, enabled):
            return None

        def restore() -> None:
            set_console_mode(handle, previous)

        return restore
    except (AttributeError, OSError, ValueError):
        return None


def _normalize_posix_key(sequence: bytes) -> str:
    if sequence in {b"\r", b"\n"}:
        return "enter"
    if sequence == b" ":
        return "space"
    if sequence == b"\x03":
        raise KeyboardInterrupt
    if sequence.startswith(b"\x1b") and sequence.endswith(b"A"):
        return "up"
    if sequence.startswith(b"\x1b") and sequence.endswith(b"B"):
        return "down"
    return ""


def _normalize_windows_key(character: str, extended: str = "") -> str:
    if character in {"\x00", "\xe0"}:
        return {"H": "up", "P": "down"}.get(extended, "")
    if character in {"\r", "\n"}:
        return "enter"
    if character == " ":
        return "space"
    if character == "\x03":
        raise KeyboardInterrupt
    return ""


@contextmanager
def _terminal_key_reader(stdin: TextIO) -> Iterator[Callable[[], str]]:
    if os.name == "nt":
        import msvcrt

        def read_windows_key() -> str:
            character = msvcrt.getwch()
            if character in {"\x00", "\xe0"}:
                extended = msvcrt.getwch()
                return _normalize_windows_key(character, extended)
            return _normalize_windows_key(character)

        yield read_windows_key
        return

    import select
    import termios
    import tty

    file_descriptor = stdin.fileno()
    previous = termios.tcgetattr(file_descriptor)
    tty.setcbreak(file_descriptor)

    def read_posix_key() -> str:
        sequence = os.read(file_descriptor, 1)
        if sequence == b"\x1b":
            for _ in range(2):
                readable, _, _ = select.select([file_descriptor], [], [], 0.05)
                if not readable:
                    break
                sequence += os.read(file_descriptor, 1)
        return _normalize_posix_key(sequence)

    try:
        yield read_posix_key
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous)


def _render_navigation(
    console: Console,
    options: list[tuple[str, str, str]],
    current: int,
    selected: set[int],
    multiple: bool,
    warning: Optional[str] = None,
) -> int:
    starting_line = console._written_lines
    for index, (_, label, _) in enumerate(options):
        focused = index == current
        pointer = "›" if console.unicode and focused else ">" if focused else " "
        if console.unicode:
            mark = ("■" if index in selected else "□") if multiple else (
                "●" if index in selected else "○"
            )
        else:
            mark = "[x]" if index in selected else "[ ]"
        style = (console.CYAN, console.BOLD) if focused else ()
        console.wrap(
            console.styled(f"{pointer} {mark} {label}", *style),
            indent=2,
            subsequent=6,
            right_margin=1,
        )
    description = options[current][2]
    if description:
        console.wrap(description, indent=5, right_margin=1)
    action = "toggle" if multiple else "select"
    hint = f"↑/↓ move · Space {action} · Enter confirm" if console.unicode else (
        f"Up/Down move · Space {action} · Enter confirm"
    )
    console.wrap(console.styled(hint, console.DIM), indent=5, right_margin=1)
    if warning:
        console.wrap(
            console.styled(f"! {warning}", console.YELLOW),
            indent=2,
            subsequent=4,
            break_long_words=True,
            right_margin=1,
        )
    return console._written_lines - starting_line


def _erase_navigation(console: Console, rendered_lines: int) -> None:
    if rendered_lines <= 0:
        return
    console.stdout.write(f"\033[{rendered_lines}F\033[J")
    console.stdout.flush()


def _navigate_options(
    console: Console,
    options: list[tuple[str, str, str]],
    defaults: set[int],
    multiple: bool,
) -> set[int]:
    selected = set(defaults)
    current = min(selected) if selected else 0
    warning: Optional[str] = None
    rendered_lines = 0
    console.stdout.write("\033[?25l")
    console.stdout.flush()
    try:
        with console.navigation_keys() as read_key:
            while True:
                _erase_navigation(console, rendered_lines)
                rendered_lines = _render_navigation(
                    console,
                    options,
                    current,
                    selected,
                    multiple,
                    warning,
                )
                warning = None
                key = read_key()
                if key == "up":
                    current = (current - 1) % len(options)
                elif key == "down":
                    current = (current + 1) % len(options)
                elif key == "space":
                    if multiple:
                        if current in selected:
                            selected.remove(current)
                        else:
                            selected.add(current)
                    else:
                        selected = {current}
                elif key == "enter":
                    if not multiple:
                        selected = {current}
                    if selected:
                        break
                    warning = "Select at least one option before continuing."
    finally:
        _erase_navigation(console, rendered_lines)
        _render_navigation(console, options, current, selected, multiple)
        console.stdout.write("\033[?25h")
        console.stdout.flush()
        console.write()
    return selected


def _select_one(
    console: Console,
    title: str,
    options: list[tuple[str, str, str]],
    default_value: str,
) -> str:
    console.section(title)
    if console.supports_navigation:
        default_index = next(
            (
                index
                for index, (value, _, _) in enumerate(options)
                if value == default_value
            ),
            0,
        )
        selected = _navigate_options(console, options, {default_index}, False)
        return options[next(iter(selected))][0]

    default_index = 1
    for index, (value, label, description) in enumerate(options, start=1):
        recommended = value == default_value
        if recommended:
            default_index = index
        console.option(index, label, description, recommended)
    while True:
        answer = console.ask("Choose one", str(default_index))
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        by_name = {value: value for value, _, _ in options}
        if answer.lower() in by_name:
            return by_name[answer.lower()]
        console.warning(f"Enter a number from 1 to {len(options)}.")


def _select_many(
    console: Console,
    title: str,
    options: list[tuple[str, str, str]],
    defaults: list[str],
) -> list[str]:
    console.section(title)
    if console.supports_navigation:
        default_indexes = {
            index
            for index, (value, _, _) in enumerate(options)
            if value in defaults
        }
        selected = _navigate_options(console, options, default_indexes, True)
        return [
            value
            for index, (value, _, _) in enumerate(options)
            if index in selected
        ]

    indexes: list[str] = []
    for index, (value, label, description) in enumerate(options, start=1):
        recommended = value in defaults
        if recommended:
            indexes.append(str(index))
        console.option(index, label, description, recommended)
    default = ",".join(indexes) or "1"
    while True:
        answer = console.ask(
            "Choose one or more numbers, separated by commas",
            default,
        )
        if answer.lower() == "all":
            return [value for value, _, _ in options]
        tokens = [
            token.strip()
            for token in answer.replace(" ", ",").split(",")
            if token.strip()
        ]
        if tokens and all(
            token.isdigit() and 1 <= int(token) <= len(options)
            for token in tokens
        ):
            selected: list[str] = []
            for token in tokens:
                value = options[int(token) - 1][0]
                if value not in selected:
                    selected.append(value)
            return selected
        console.warning(
            f"Enter comma-separated numbers from 1 to {len(options)}, or all."
        )


def _confirm(console: Console, question: str, default: bool) -> bool:
    if console.supports_navigation:
        console.section("Confirm")
        console.wrap(question, indent=2)
        options = [
            ("yes", "Yes", "Continue with this action."),
            ("no", "No", "Leave the current state unchanged."),
        ]
        default_index = 0 if default else 1
        selected = _navigate_options(console, options, {default_index}, False)
        return next(iter(selected)) == 0

    hint = "Y/n" if default else "y/N"
    while True:
        answer = console.ask(
            f"{question} ({hint})",
            "y" if default else "n",
        ).lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        console.warning("Enter y or n.")


def should_use_wizard(
    raw_args: list[str],
    args: argparse.Namespace,
    stdin: TextIO,
    stdout: TextIO,
    env: Mapping[str, str],
) -> bool:
    """Use the wizard by default only when it is safe to prompt."""
    if args.non_interactive:
        return False
    if args.interactive:
        return True
    if raw_args or env.get("CI"):
        return False
    return _isatty(stdin) and _isatty(stdout)


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
    result = subprocess.run(
        [uv, "tool", "dir", "--bin"],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
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
) -> None:
    cwd = project_dir.expanduser().resolve() if scope == "project" else REPO_ROOT
    uv_command = ["uv", "tool", "install", "--upgrade", "graphifyy"]
    if dry_run:
        emit(f"would run  {shlex.join(uv_command)}")
        for command in graphify_install_commands(agents, scope):
            location = f" (in {cwd})" if scope == "project" else ""
            emit(f"would run  {shlex.join(command)}{location}")
        return

    if scope == "project" and not cwd.is_dir():
        raise InstallError(f"Graphify project directory does not exist: {cwd}")
    uv = shutil.which("uv")
    if not uv:
        raise InstallError(
            "--graphify requires uv; install it from https://docs.astral.sh/uv/ and rerun"
        )
    _run([uv, "tool", "install", "--upgrade", "graphifyy"], cwd)
    graphify = _find_graphify(uv, cwd)
    if not graphify:
        raise InstallError(
            "graphifyy was installed but the graphify executable could not be located"
        )
    for command in graphify_install_commands(agents, scope, graphify):
        _run(command, cwd)


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


def _replacement_paths(args: argparse.Namespace, skills: list[str]) -> list[Path]:
    roots = resolve_roots(
        args.agent,
        args.scope,
        args.home,
        args.project_dir,
        args.target,
    )
    paths: list[Path] = []
    for root in roots:
        for skill_name in skills:
            destination = root / skill_name
            exists = destination.exists() or destination.is_symlink()
            if exists and not trees_equal(destination, SOURCE_ROOT / skill_name):
                paths.append(destination)
    return paths


def run_wizard(
    args: argparse.Namespace,
    bundled: list[str],
    console: Console,
) -> bool:
    """Collect installer choices and return whether installation should proceed."""
    console.header()

    if args.target is None:
        args.scope = _select_one(
            console,
            "Installation scope",
            [
                ("user", "This user", "Available from projects on this machine."),
                (
                    "project",
                    "One project",
                    "Stored inside a project so the setup stays local.",
                ),
            ],
            args.scope,
        )
        if args.scope == "project":
            while True:
                entered = console.ask(
                    "Project directory",
                    str(args.project_dir.expanduser().resolve()),
                )
                project_dir = Path(entered).expanduser().resolve()
                if project_dir.is_dir():
                    args.project_dir = project_dir
                    break
                console.warning(f"Directory does not exist: {project_dir}")
    else:
        console.section("Installation target")
        console.note(str(args.target.expanduser().resolve()))

    agent_defaults = args.agent or list(DEFAULT_AGENTS)
    if "all" in agent_defaults:
        agent_defaults = ["universal", "claude"]
    args.agent = _select_many(
        console,
        "Coding agents",
        [
            (
                "universal",
                "Shared .agents directory",
                "Preferred portable location for Codex, Cursor, Copilot, and other agents.",
            ),
            ("codex", "Codex", "Shared skill plus Codex-specific Graphify setup."),
            ("cursor", "Cursor", "Shared skill plus Cursor-specific Graphify setup."),
            (
                "copilot",
                "GitHub Copilot",
                "Shared skill plus Copilot-specific Graphify setup.",
            ),
            ("claude", "Claude Code", "Installs into Claude's dedicated directory."),
        ],
        agent_defaults,
    )

    if len(bundled) == 1:
        args.skill = bundled.copy()
        console.section("Skills")
        console.note(f"Install {bundled[0]}")
    else:
        args.skill = _select_many(
            console,
            "Skills",
            [(name, name, skill_summary(name)) for name in bundled],
            args.skill or bundled,
        )

    args.mode = _select_one(
        console,
        "Install mode",
        [
            (
                "copy",
                "Copy files",
                "Stable across repo moves and best for syncing between machines.",
            ),
            (
                "link",
                "Create links",
                "Changes in this checkout appear immediately in installed skills.",
            ),
        ],
        args.mode,
    )
    # No bundled skill requires mattpocock/skills, so the wizard does not offer
    # to fetch third-party skills. `--matt-skills` still installs them on request.
    args.matt_skills = bool(args.matt_skills)
    args.graphify = _confirm(
        console,
        "Install Graphify and configure it for the selected agents?",
        args.graphify,
    )

    differing = _replacement_paths(args, args.skill)
    if differing and not args.force:
        console.section("Existing installations")
        many = len(differing) != 1
        console.warning(
            f"{len(differing)} installed skill path{'s' if many else ''} "
            f"{'differ' if many else 'differs'} from this release. "
            "Each will be backed up before replacement."
        )
        for path in differing:
            console.note(str(path))
        if not _confirm(console, "Back up and replace these installations?", False):
            console.write()
            console.note("No changes made.")
            return False
        args.force = True

    roots = resolve_roots(
        args.agent,
        args.scope,
        args.home,
        args.project_dir,
        args.target,
    )
    console.section("Review")
    console.summary(
        [
            ("Scope", args.scope if args.target is None else "custom target"),
            ("Agents", ", ".join(args.agent)),
            ("Skills", ", ".join(args.skill)),
            ("Mode", args.mode),
            ("Destination", ", ".join(str(root) for root in roots)),
            (
                "Matt skills",
                "install all" if args.matt_skills else "skip",
            ),
            ("Graphify", "install and configure" if args.graphify else "skip"),
        ]
    )
    if not _confirm(console, "Apply this setup?", True):
        console.write()
        console.note("No changes made.")
        return False
    return True


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
        help="skip Matt Pocock skills in the interactive wizard",
    )
    result.set_defaults(matt_skills=None)
    interaction = result.add_mutually_exclusive_group()
    interaction.add_argument(
        "--interactive",
        action="store_true",
        help="open the guided setup wizard, even when input is not a terminal",
    )
    interaction.add_argument(
        "--non-interactive",
        action="store_true",
        help="use command-line options without opening the setup wizard",
    )
    result.add_argument(
        "--no-color",
        action="store_true",
        help="disable color in the interactive interface",
    )
    result.add_argument("--force", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--list", action="store_true", help="list bundled skills and exit")
    result.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return result


def execute_install(
    args: argparse.Namespace,
    selected: list[str],
    console: Optional[Console],
) -> None:
    roots = resolve_roots(
        args.agent, args.scope, args.home, args.project_dir, args.target
    )
    if console:
        console.section("Installing" if not args.dry_run else "Preview")
    for root in roots:
        for skill_name in selected:
            result = install_one(
                SOURCE_ROOT / skill_name,
                root,
                args.mode,
                args.force,
                args.dry_run,
            )
            if console:
                if result.startswith("installed"):
                    console.success(result)
                else:
                    console.note(result)
            else:
                print(result)
        write_receipt(root, selected, args.mode, args.dry_run)
    if args.matt_skills:
        if console:
            console.section("Matt Pocock skills")
            console.note(
                "Installing the complete engineering skill set, including "
                "setup-matt-pocock-skills."
            )
        install_matt_skills(
            args.agent,
            roots,
            args.force,
            args.dry_run,
            console.note if console else print,
            getattr(args, "matt_npx", None),
        )
    if args.graphify:
        if console:
            console.section("Graphify")
            console.note("Installing graphifyy with uv and registering agent skills.")
        install_graphify(
            args.agent,
            args.scope,
            args.project_dir,
            args.dry_run,
            console.note if console else print,
        )
    if console:
        console.write()
        console.success("Preview complete." if args.dry_run else "Setup complete.")
        if args.matt_skills and not args.dry_run:
            console.note(
                "Next: run /setup-matt-pocock-skills once inside the target "
                "repository to finish configuring the workflows."
            )


def main(argv: Optional[list[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(raw_args)
    console: Optional[Console] = None
    try:
        bundled = available_skills()
        if args.list:
            print("\n".join(bundled))
            return 0
        interactive = should_use_wizard(
            raw_args,
            args,
            sys.stdin,
            sys.stdout,
            os.environ,
        )
        if interactive:
            console = Console(sys.stdin, sys.stdout, color=False if args.no_color else None)
            if not run_wizard(args, bundled, console):
                return 0
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
        execute_install(args, selected, console)
        return 0
    except KeyboardInterrupt:
        if console:
            console.write()
            console.warning("Setup interrupted.")
        else:
            print("error: interrupted", file=sys.stderr)
        return 130
    except InstallError as exc:
        if console:
            console.write()
            console.error(str(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        if console:
            console.write()
            console.error(str(exc))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if console:
            console.close()


if __name__ == "__main__":
    raise SystemExit(main())
