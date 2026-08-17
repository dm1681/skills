#!/usr/bin/env python3
"""A Textual dashboard for installing this collection's skills.

Layout is one shell in both modes: a header, a sidebar, a main pane, and a key
bar. The sidebar carries filters and destination in dashboard mode, and a step
rail in guided mode; nothing else moves.

COLOUR CONTRACT - every hue means one thing everywhere:

    mauve   you        selection, focus, the active step. Never data.
    blue    install    an additive write; nothing existing is lost.
    peach   replace    an overwrite; the old copy is backed up first.
    green   no change  already identical to this checkout.
    teal    location   paths, roots, scope. Where things live.
    yellow  advisory   allowed, but probably not what you want.
    pink    remove     a deletion; the copy is backed up first, and nothing is
                       written in its place. Never used for an error.
    red     failure    errors only, so a healthy run is provably red-free.

A skill's state is painted in the colour of the *consequence* of selecting it,
so the same hue carries from the state pill to the action column to the review
step to the progress bar.

The manage pane paints a removal pink rather than peach: peach promises the
old copy is backed up *and something replaces it*, and a removal only makes
the first half of that promise. Red still means only that an operation failed.

The install itself runs through `install.install_one` — the
global-instructions row through `install.install_global_instructions`, every
removal through `install.uninstall_one` and its siblings — so backups,
receipts, and root resolution stay defined in one place. This module performs
no filesystem removal of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import install  # noqa: E402

from textual import work  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Container, Horizontal, VerticalScroll  # noqa: E402
from textual.screen import ModalScreen  # noqa: E402
from textual.widgets import Markdown, Static  # noqa: E402

AVAILABLE = "available"
INSTALLED = "installed"
OUTDATED = "outdated"

YOU = "#cba6f7"
ADD = "#89b4fa"
REPLACE = "#fab387"
KEEP = "#a6e3a1"
WHERE = "#94e2d5"
ADVISE = "#f9e2af"
REMOVE = "#f5c2e7"
FAIL = "#f38ba8"
MUTE = "#7f849c"
BG = "#1e1e2e"
PANEL = "#181825"
HI = "#313244"
FG = "#cdd6f4"

# state -> (colour, pill label, verb once selected)
MEANING = {
    AVAILABLE: (ADD, "NOT INSTALLED", "install"),
    OUTDATED: (REPLACE, "DIFFERS", "replace"),
    INSTALLED: (KEEP, "UP TO DATE", "skip"),
}
VIEWS = ("all", "differs", "up to date")
VIEW_STATES = {"differs": OUTDATED, "up to date": INSTALLED}
GLOBAL = "global-instructions"
GLOBAL_SUMMARY = (
    "user-level AGENTS.md for every agent: ~/.agents/AGENTS.md + ~/.claude/CLAUDE.md"
)
GLOBAL_STATES = {"missing": AVAILABLE, "current": INSTALLED, "differs": OUTDATED}
STEPS = ("Where to install", "Which skills", "Copy or link", "Review")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
RECEIPT = install.RECEIPT_NAME
# One shell, two panes: choosing what to install, and managing what is already
# installed. The manage pane sweeps every root it knows about, so the view and
# mode filters — which describe an install — have nothing to say in it.
PANES = ("skills", "manage")
MANAGE_TITLES = {
    "skill": ("INSTALLED SKILLS", "removed with a backup; a recorded original is put back"),
    "managed-file": (
        "GLOBAL INSTRUCTIONS",
        "user-level AGENTS.md files; one you have since rewritten is left alone",
    ),
    "shim": ("LAUNCHER SHIMS", "the `skills` command; one from another checkout is left"),
    "external": (
        "EXTERNAL TOOLS",
        "third-party; only what this collection recorded placing can go",
    ),
}

CSS = """
Screen { background: %(bg)s; color: %(fg)s; }
#head { height: 2; padding: 1 2 0 2; }
#body { height: 1fr; }
#side { width: 26; padding: 1 2; background: %(panel)s; }
#main { width: 1fr; padding: 1 3; }
#status { dock: bottom; height: 1; padding: 0 2; }
#foot { dock: bottom; height: 3; padding: 1 2; background: %(panel)s; }

SkillRow { height: 3; padding: 0 2; margin-bottom: 1; background: %(panel)s; }
SkillRow:focus { background: %(hi)s; }
ChoiceRow { height: 4; padding: 0 2; margin-bottom: 1; background: %(panel)s; }
ChoiceRow:focus { background: %(hi)s; }

/* Height is border-box: borders and padding come out of it before content. */
#confirm { width: 62; padding: 1 2; background: %(panel)s; border: thick %(replace)s;
           offset: 0 -3; opacity: 0;
           transition: offset 200ms out_cubic, opacity 180ms out_cubic; }
#confirm.shown { offset: 0 0; opacity: 1; }
ConfirmReplace { align: center middle; }

#preview { width: 70%%; height: 80%%; padding: 1 2; background: %(panel)s;
           border: round %(you)s; }
PreviewScreen { align: center middle; }

/* Nested under the external row that installed them, so indented and on the
   screen background rather than the panel the parent rows sit on. */
HiddenSkillRow { height: 3; padding: 0 2; margin: 0 0 1 3; background: %(bg)s; }
HiddenSkillRow:focus { background: %(hi)s; }

ManageRow { height: 3; padding: 0 2; margin-bottom: 1; background: %(panel)s; }
ManageRow:focus { background: %(hi)s; }

#changes { width: 66; padding: 1 2; background: %(panel)s; border: thick %(remove)s;
           offset: 0 -3; opacity: 0;
           transition: offset 200ms out_cubic, opacity 180ms out_cubic; }
#changes.shown { offset: 0 0; opacity: 1; }
ConfirmChanges { align: center middle; }
""" % {
    "bg": BG, "fg": FG, "panel": PANEL, "hi": HI, "replace": REPLACE, "you": YOU,
    "remove": REMOVE,
}


def pill(label: str, fg: str, bg: str) -> str:
    return "[%s on %s] %s [/]" % (fg, bg, label)


def chip(key: str, label: str, colour: str) -> str:
    return "[%s on %s] %s [/][%s] %s[/]" % (BG, colour, key, MUTE, label)


def blend(start: str, end: str, ratio: float) -> str:
    left = [int(start[i : i + 2], 16) for i in (1, 3, 5)]
    right = [int(end[i : i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(a + (b - a) * ratio) for a, b in zip(left, right)
    )


def gradient(text: str, start: str, end: str) -> str:
    if len(text) < 2:
        return text
    return "".join(
        "[%s]%s[/]" % (blend(start, end, index / (len(text) - 1)), character)
        for index, character in enumerate(text)
    )


def skill_state(name: str, roots: Sequence[Path]) -> str:
    """Worst state across every destination root.

    A skill counts as installed only when every root holds a copy matching this
    checkout; one stale root is enough to call the whole thing outdated,
    because that is the root an agent might read.
    """
    source = install.SOURCE_ROOT / name
    states = []
    for root in roots:
        destination = root / name
        if not (destination.exists() or destination.is_symlink()):
            states.append(AVAILABLE)
        elif install.trees_equal(destination, source):
            states.append(INSTALLED)
        else:
            states.append(OUTDATED)
    if not states:
        return AVAILABLE
    for state in (OUTDATED, AVAILABLE):
        if state in states:
            return state
    return INSTALLED


def external_state(name: str, roots: Sequence[Path]) -> str:
    """Present or absent, and nothing finer.

    An external tool is installed by somebody else's CLI, so there is no source
    tree here to diff it against. Claiming OUTDATED would be a guess, and the
    dashboard's colour contract promises that peach means a replacement it can
    actually describe. Presence is probed by the tool's marker directory, which
    may differ from the row's name (matt-skills installs a dozen directories).
    """
    if not roots:
        return AVAILABLE
    marker = install.external_tool(name).marker
    present = [
        (root / marker).exists() or (root / marker).is_symlink() for root in roots
    ]
    return INSTALLED if all(present) else AVAILABLE


def global_state(home: Path, mode: str) -> str:
    """Worst state across the two managed instruction files.

    Mode-sensitive like the underlying status: the pill answers "what happens
    if you install with the mode currently chosen" — the colour contract's
    promise — so flipping copy/link can honestly flip the pill.
    """
    states = [
        GLOBAL_STATES[state]
        for _, state in install.global_instruction_status(home, mode)
    ]
    for state in (OUTDATED, AVAILABLE):
        if state in states:
            return state
    return INSTALLED


def external_meaning(state: str) -> tuple:
    """(colour, pill label, verb) for an external row.

    Same shape as MEANING, deliberately different words. `UP TO DATE` would
    overclaim — this collection cannot diff somebody else's package — and
    re-running an external installer upgrades rather than no-ops, so a tool
    already present offers `update` in the replacement colour, not `skip`.
    """
    if state == AVAILABLE:
        return (ADD, "NOT INSTALLED", "install")
    return (REPLACE, "PRESENT", "update")


def manage_meaning(item) -> tuple:
    """(colour, pill label, verb) for one discovered install.

    Yellow for something no receipt records: removing it is allowed, but the
    collection cannot say it put it there, which is probably not what you
    want. Pink for a removal. Never FAIL, never YOU — a listed install is not
    an error, and mauve belongs to your selection alone.
    """
    if not item.recorded:
        return (ADVISE, "UNRECORDED", "remove")
    if item.kind == "external":
        empty = not install.external_removal_plan(item.name, [item.root])[0]
        return (ADVISE, "EXTERNAL", "explain") if empty else (REMOVE, "EXTERNAL", "remove")
    return (REMOVE, (item.mode or "PRESENT").upper(), "remove")


def _without_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4 :].lstrip() if end != -1 else text


class RowScroll(VerticalScroll):
    """The main list: arrow keys move row focus instead of scrolling.

    VerticalScroll's own arrow bindings sit closer to the focused row than the
    app's, so they swallow the keys whenever the list overflows — exactly when
    navigation matters most. Rebinding them to the app's move action loses
    nothing: focusing a row scrolls it into view, and the mouse wheel and
    page keys still scroll.
    """

    BINDINGS = [
        Binding("up", "app.move(-1)", "up", show=False),
        Binding("down", "app.move(1)", "down", show=False),
    ]


class SkillRow(Static):
    """One skill: selection mark, name, state pill, advisory, action."""

    can_focus = True

    def __init__(
        self,
        name: str,
        state: str,
        repo_level: bool,
        selected: bool,
        external: bool = False,
        note: str = "",
        blurb: str = "",
    ):
        super().__init__()
        self.skill = name
        self.state = state
        self.repo_level = repo_level
        self.selected = selected
        self.external = external
        self.note = note
        # A row that is not a skill directory (the global-instructions row)
        # supplies its own one-liner; a skill row looks its own up.
        self.blurb = blurb

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        colour, label, verb = (
            external_meaning(self.state) if self.external else MEANING[self.state]
        )
        # Left edge answers "what happens to this one", mauve only when it is
        # yours - i.e. selected.
        self.styles.border_left = ("thick", YOU if self.selected else colour)
        mark = "[%s]◆[/]" % YOU if self.selected else "[%s]◇[/]" % MUTE
        action = "[%s]→ %s[/]" % (colour, verb) if self.selected else ""
        advisory = "  [%s]repo-level only[/]" % ADVISE if self.repo_level else ""
        summary = self.blurb or (
            install.external_tool(self.skill).summary
            if self.external
            else install.skill_summary(self.skill)
        )
        note = "  [%s]%s[/]" % (ADVISE, self.note) if self.note else ""
        self.update(
            "%s [b]%-22s[/] %s%s  %s\n    [%s]%s[/]%s"
            % (mark, self.skill, pill(label, BG, colour), advisory, action,
               MUTE, summary, note)
        )

    def toggle(self) -> None:
        self.selected = not self.selected
        self.redraw()


class ChoiceRow(Static):
    """A guided-step option: title, detail, and whether it is chosen."""

    can_focus = True

    def __init__(self, value: str, title: str, detail: str, chosen: bool, colour: str):
        super().__init__()
        self.value = value
        self.title = title
        self.detail = detail
        self.chosen = chosen
        self.colour = colour

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        self.styles.border_left = ("thick", YOU if self.chosen else HI)
        mark = "[%s]◆[/]" % YOU if self.chosen else "[%s]◇[/]" % MUTE
        self.update(
            "%s [b %s]%s[/]\n    [%s]%s[/]"
            % (mark, self.colour if self.chosen else FG, self.title, MUTE, self.detail)
        )


class ConfirmReplace(ModalScreen):
    """Asks before backing up and replacing installs that differ."""

    BINDINGS = [
        Binding("y", "yes", "replace"),
        Binding("n", "no", "cancel"),
        Binding("escape", "no", "cancel"),
    ]

    def __init__(self, names: Sequence[str]) -> None:
        super().__init__()
        self.names = list(names)

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                "%s [b]%d installed skill%s differ%s from this checkout[/]\n\n%s\n\n"
                "[%s]Each is moved into an adjacent .skills-backups directory before\n"
                "the new version lands, so every replacement is recoverable.[/]\n\n"
                "%s  %s"
                % (
                    pill("REPLACE", BG, REPLACE),
                    len(self.names),
                    "" if len(self.names) == 1 else "s",
                    "s" if len(self.names) == 1 else "",
                    "\n".join("  [%s]→[/] %s" % (REPLACE, n) for n in self.names),
                    MUTE,
                    chip("Y", "replace", REPLACE),
                    chip("N", "cancel", MUTE),
                ),
            ),
            id="confirm",
        )

    def on_mount(self) -> None:
        # The class has to land a frame after mount, or the initial and target
        # styles are applied together and nothing animates.
        self.set_timer(0.02, lambda: self.query_one("#confirm").add_class("shown"))

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class ManageRow(Static):
    """One discovered install: selection mark, name, pill, path, restore line."""

    can_focus = True

    def __init__(self, item, selected: bool) -> None:
        super().__init__()
        self.item = item
        self.selected = selected

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        colour, label, verb = manage_meaning(self.item)
        self.styles.border_left = ("thick", YOU if self.selected else colour)
        mark = "[%s]◆[/]" % YOU if self.selected else "[%s]◇[/]" % MUTE
        action = "[%s]→ %s[/]" % (colour, verb) if self.selected else ""
        name = self.item.name
        if self.item.kind in ("managed-file", "shim"):
            name = Path(self.item.name).name
        self.update(
            "%s [b]%-22s[/] %s  %s\n    [%s]%s[/]  [%s]%s[/]"
            % (mark, name, pill(label, BG, colour), action,
               WHERE, self.item.path, MUTE, self.item.detail)
        )

    def toggle(self) -> None:
        self.selected = not self.selected
        self.redraw()


class ConfirmChanges(ModalScreen):
    """Asks before writing or removing anything in the manage pane.

    Writes and removals are listed under separate headings in their own
    colours, because "12 changes" hides which of them cannot be undone by
    running the installer again.
    """

    BINDINGS = [
        Binding("y", "yes", "apply"),
        Binding("n", "no", "cancel"),
        Binding("escape", "no", "cancel"),
    ]

    def __init__(self, entries: Sequence[tuple]) -> None:
        super().__init__()
        self.entries = list(entries)

    def compose(self) -> ComposeResult:
        writes = [entry for entry in self.entries if entry[1] == "write"]
        removals = [entry for entry in self.entries if entry[1] == "remove"]
        lines = []
        for heading, colour, group in (
            ("WRITE", REPLACE, writes),
            ("REMOVE", REMOVE, removals),
        ):
            if not group:
                continue
            lines.append(
                "%s [b]%d %s[/]"
                % (pill(heading, BG, colour), len(group),
                   "change" if len(group) == 1 else "changes")
            )
            for label, _consequence, paths in group:
                lines.append("  [%s]→[/] %s" % (colour, label))
                for path in paths:
                    lines.append("      [%s]%s[/]" % (WHERE, path))
            lines.append("")
        lines.append(
            "[%s]Nothing is deleted outright: each copy moves into "
            ".skills-backups\nfirst. A link is unlinked; this checkout is "
            "untouched.[/]" % MUTE
        )
        lines.append("")
        lines.append("%s  %s" % (chip("Y", "apply", REMOVE), chip("N", "cancel", MUTE)))
        yield Container(Static("\n".join(lines)), id="changes")

    def on_mount(self) -> None:
        # A frame late, or the initial and target styles land together and
        # nothing animates.
        self.set_timer(0.02, lambda: self.query_one("#changes").add_class("shown"))

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class PreviewScreen(ModalScreen):
    """The focused skill's SKILL.md."""

    BINDINGS = [Binding("escape,enter,q", "close", "close")]

    def __init__(self, skill: str) -> None:
        super().__init__()
        # Not `self.name`: Widget exposes `name` as a read-only property.
        self.skill = skill

    def compose(self) -> ComposeResult:
        yield VerticalScroll(Markdown(self.body()), id="preview")

    def body(self) -> str:
        """The skill's own text, or what can honestly be said about a tool.

        An external tool has no SKILL.md in this checkout — its text ships with
        the package and only exists once installed — so the preview describes
        where it comes from instead of reading a file that is not there. The
        global-instructions row previews global/AGENTS.md, the text the
        managed home files carry or point back to.
        """
        if self.skill == GLOBAL:
            return (
                "# global-instructions\n\n%s\n\nInstalled as managed files — "
                "pointers back to this checkout in `link` mode, the inlined "
                "text in `copy` mode:\n\n- `~/.agents/AGENTS.md`\n"
                "- `~/.claude/CLAUDE.md`\n\n---\n\n%s"
                % (
                    GLOBAL_SUMMARY,
                    install.GLOBAL_SOURCE.read_text(encoding="utf-8"),
                )
            )
        entrypoint = install.SOURCE_ROOT / self.skill / "SKILL.md"
        if entrypoint.is_file():
            return _without_frontmatter(entrypoint.read_text(encoding="utf-8"))
        tool = install.external_tool(self.skill)
        return (
            "# %s\n\n%s\n\n**External tool.** This collection does not carry "
            "its files.\n\n- Source: %s\n- Requires: `%s` on PATH\n\nIts own "
            "documentation ships with the package once installed."
            % (tool.name, tool.summary, tool.origin, tool.requires)
        )

    def action_close(self) -> None:
        self.dismiss(None)


class HiddenSkillRow(Static):
    """One installed skill the model may or may not see, nested under the
    external row whose install placed it."""

    can_focus = True

    def __init__(self, name: str, visible: bool, description: str) -> None:
        super().__init__()
        self.skill = name
        self.visible_to_model = visible
        self.description = description

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        colour = ADD if self.visible_to_model else MUTE
        label = "VISIBLE TO MODEL" if self.visible_to_model else "HIDDEN"
        self.styles.border_left = ("thick", colour)
        self.update(
            "[%s]└[/] [b]%-24s[/] %s\n      [%s]%s[/]"
            % (MUTE, self.skill, pill(label, BG, colour), MUTE, self.description)
        )


class SkillsApp(App):
    """Dashboard and guided setup, sharing one shell."""

    CSS = CSS
    BINDINGS = [
        # Explicit rather than focus_next/focus_previous: the surrounding
        # VerticalScroll binds the arrow keys to scrolling and swallows them
        # before the default focus actions ever run.
        Binding("up", "move(-1)", "up", show=False),
        Binding("down", "move(1)", "down", show=False),
        Binding("space", "toggle", "select"),
        Binding("a", "toggle_all", "all"),
        Binding("enter", "advance", "next"),
        Binding("escape", "back", "back"),
        Binding("v", "cycle_view", "view"),
        Binding("s", "cycle_scope", "scope"),
        Binding("m", "cycle_mode", "mode"),
        Binding("i", "install", "install"),
        Binding("g", "toggle_guided", "guided"),
        Binding("u", "toggle_pane", "manage"),
        Binding("x", "apply", "apply"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(
        self,
        project_dir: Path,
        scope: str = "project",
        agents: Optional[Sequence[str]] = None,
        mode: str = "copy",
        guided: Optional[bool] = None,
        home: Optional[Path] = None,
        pane: str = "skills",
    ) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.scope = scope
        self.agents = list(agents or [])
        self.mode = mode
        # Injectable so tests never probe or write the real home; the
        # global-instructions row reads and installs against this path.
        self.home = (home or Path.home()).expanduser()
        self.bundled = install.available_skills()
        self.external = list(install.EXTERNAL_NAMES)
        self.selected = set()
        self.view = "all"
        self.pane = pane if pane in PANES else "skills"
        self.installed_count = 0
        self.removed_count = 0
        self.failures = 0
        self._guided_requested = guided
        self.step = 0
        self._frame = 0
        self._spinning = False
        self._spin_verb = "installing"

    # -- shell ----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="head")
        yield Horizontal(
            Static(id="side"), RowScroll(id="main"), id="body"
        )
        yield Static(id="foot")
        yield Static(id="status")

    def on_mount(self) -> None:
        # query_one resolves against the top screen, so a modal would hide this
        # chrome from the spinner timer and the install worker.
        self._head = self.query_one("#head", Static)
        self._side = self.query_one("#side", Static)
        self._main = self.query_one("#main", VerticalScroll)
        self._foot = self.query_one("#foot", Static)
        self._status = self.query_one("#status", Static)
        if self._guided_requested is None:
            self.step = 0 if self.has_receipt() else 1
        else:
            self.step = 1 if self._guided_requested else 0
        self.set_interval(0.08, self.tick)
        self.render_all()

    # -- state ----------------------------------------------------------

    def roots(self) -> list:
        return install.resolve_roots(
            self.agents, self.scope, self.home, self.project_dir, None
        )

    def has_receipt(self) -> bool:
        """Whether this destination has been installed into before."""
        return any((root / RECEIPT).is_file() for root in self.roots())

    def target(self) -> Path:
        return self.project_dir if self.scope == "project" else self.home

    def states(self) -> dict:
        roots = self.roots()
        states = {name: skill_state(name, roots) for name in self.bundled}
        states.update({name: external_state(name, roots) for name in self.external})
        states[GLOBAL] = global_state(self.home, self.mode)
        return states

    def visible(self) -> list:
        states = self.states()
        listed = self.bundled + self.external + [GLOBAL]
        if self.view == "all":
            return list(listed)
        wanted = VIEW_STATES[self.view]
        return [name for name in listed if states[name] == wanted]

    def sections(self) -> list:
        """(title, detail, names, external) for each group, empty ones dropped.

        The split is the point: one group is files this checkout owns and can
        diff, the other is somebody else's package that only its own installer
        can place. They install differently, so they are never one list.
        """
        visible = self.visible()
        groups = [
            (
                "YOUR SKILLS",
                "versioned in this checkout; installed as a copy or a link",
                [name for name in self.bundled if name in visible],
                False,
            ),
            (
                "EXTERNAL TOOLS",
                "third-party; each installed and registered by its own CLI",
                [name for name in self.external if name in visible],
                True,
            ),
            (
                "GLOBAL INSTRUCTIONS",
                "user-level AGENTS.md files; diffed and backed up like a skill",
                [name for name in (GLOBAL,) if name in visible],
                False,
            ),
        ]
        return [group for group in groups if group[2]]

    def rows(self) -> list:
        return list(self._main.query(SkillRow))

    def nav_rows(self) -> list:
        """Every focusable row in visual order, expanded sub-rows included."""
        return [
            widget
            for widget in self._main.query(Static)
            if isinstance(widget, (SkillRow, HiddenSkillRow, ManageRow))
        ]

    def choices(self) -> list:
        return list(self._main.query(ChoiceRow))

    def hidden_note(self, reviewable: list, expanded: bool) -> str:
        """The parent row's one-line pointer at its collapsed sub-rows."""
        if not reviewable:
            return ""
        count = sum(1 for _, visible, _ in reviewable if not visible)
        return "%s %d hidden from the model%s" % (
            "▾" if expanded else "▸",
            count,
            "" if expanded else " — select to review",
        )

    def reviewable_under(self, name: str) -> list:
        """Hidden-skill entries shown, collapsed, under one external row.

        Only matt-skills installs skills carrying disable-model-invocation,
        and a root scan cannot attribute an installed directory to the tool
        that placed it, so the association is by name. Revisit if a second
        external tool starts installing hidden skills.
        """
        if name != "matt-skills":
            return []
        return self.reviewable()

    def reviewable(self) -> list:
        """(name, visible, one-line description) for every reviewable skill.

        Hidden skills plus previously decided ones, so a choice can always be
        revisited; a recorded name whose files are gone is dropped rather than
        shown as a ghost row.
        """
        roots = self.roots()
        decisions = install.read_model_decisions(roots)
        names = sorted(
            {name for root in roots for name in install.hidden_skills(root)}
            | set(decisions)
        )
        entries = []
        for name in names:
            dirs = [
                root / name for root in roots if (root / name / "SKILL.md").is_file()
            ]
            if not dirs:
                continue
            visible = not any(install.skill_is_model_hidden(d) for d in dirs)
            description = ""
            for skill_dir in dirs:
                description = install.frontmatter_value(
                    skill_dir / "SKILL.md", "description"
                )
                if description:
                    break
            entries.append((name, visible, install.first_clause(description)))
        return entries

    def guided(self) -> bool:
        # The guided flow walks an install; the manage pane is never part of it.
        return self.pane == "skills" and self.step > 0

    def bin_dir(self) -> Path:
        return self.home / ".local" / "bin"

    def discovered(self) -> list:
        """Everything installed, here and everywhere an install was recorded."""
        roots = self.roots()
        for root in install.known_roots(self.home):
            if root not in roots:
                roots.append(root)
        return install.discover(roots, self.home, self.bin_dir())

    def manage_sections(self) -> list:
        """(title, detail, items) per kind, empty groups dropped."""
        items = self.discovered()
        groups = []
        for kind, (title, detail) in MANAGE_TITLES.items():
            matching = [item for item in items if item.kind == kind]
            if matching:
                groups.append((title, detail, matching))
        return groups

    def plan(self) -> list:
        """(name, state, verb, external) for each selection, in listed order."""
        states = self.states()
        entries = [
            (name, states[name], MEANING[states[name]][2], False)
            for name in self.bundled
            if name in self.selected
        ]
        entries.extend(
            (name, states[name], external_meaning(states[name])[2], True)
            for name in self.external
            if name in self.selected
        )
        if GLOBAL in self.selected:
            entries.append((GLOBAL, states[GLOBAL], MEANING[states[GLOBAL]][2], False))
        return entries

    # -- rendering ------------------------------------------------------

    def render_all(self) -> None:
        self.render_head()
        self.render_side()
        self.render_main()
        self.render_foot()
        self.render_status()

    def render_head(self) -> None:
        self._head.update(
            "%s   [%s]%s[/]   %s%s"
            % (
                gradient("skills %s" % install.VERSION, YOU, ADD),
                WHERE,
                self.target(),
                pill("PROJECT" if self.scope == "project" else "MACHINE-WIDE", BG, WHERE),
                "  " + pill("MANAGE", BG, ADVISE) if self.pane == "manage" else "",
            )
        )

    def render_side(self) -> None:
        if self.pane == "manage":
            self._side.update(self.manage_rail())
            return
        self._side.update(self.step_rail() if self.guided() else self.filters())

    def filters(self) -> str:
        states = self.states()
        counts = {
            "all": len(self.bundled) + len(self.external),
            "differs": sum(1 for s in states.values() if s == OUTDATED),
            "up to date": sum(1 for s in states.values() if s == INSTALLED),
        }
        colours = {"all": YOU, "differs": REPLACE, "up to date": KEEP}
        lines = ["[b %s]VIEW[/]" % MUTE]
        for name in VIEWS:
            label = "%-13s %d" % (name, counts[name])
            lines.append(
                "[b %s on %s] ▸ %s [/]" % (BG, colours[name], label)
                if name == self.view
                else "[%s]   %s[/]" % (MUTE, label)
            )
        lines.append("\n[b %s]INSTALL INTO[/]" % MUTE)
        for value, label in (("project", "this project"), ("user", "machine-wide")):
            lines.append(
                "[b %s on %s] ▸ %-13s[/]" % (BG, WHERE, label)
                if self.scope == value
                else "[%s]   %s[/]" % (MUTE, label)
            )
        lines.append("\n[b %s]MODE[/]" % MUTE)
        for value in ("copy", "link"):
            lines.append(
                "[%s] ▸ %s[/]" % (FG, value)
                if self.mode == value
                else "[%s]   %s[/]" % (MUTE, value)
            )
        return "\n".join(lines)

    def step_rail(self) -> str:
        lines = ["[b %s]GUIDED SETUP[/]\n" % MUTE]
        for index, label in enumerate(STEPS, start=1):
            if index < self.step:
                lines.append("[%s]  ✓ %s[/]" % (KEEP, label))
            elif index == self.step:
                lines.append("[b %s on %s] ▸ %s [/]" % (BG, YOU, label))
            else:
                lines.append("[%s]    %s[/]" % (MUTE, label))
        lines.append("\n[%s]step %d of %d[/]" % (MUTE, self.step, len(STEPS)))
        return "\n".join(lines)

    def manage_rail(self) -> str:
        """What is installed, by kind, and where this pane is looking.

        Not the view/mode filters: those describe an install, and this pane
        sweeps every root it knows about rather than the ones a mode applies to.
        """
        items = self.discovered()
        lines = ["[b %s]INSTALLED[/]" % MUTE]
        for kind, (title, _detail) in MANAGE_TITLES.items():
            count = sum(1 for item in items if item.kind == kind)
            label = "%-13s %d" % (title.lower(), count)
            lines.append(
                "[%s]   %s[/]" % (FG if count else MUTE, label)
            )
        lines.append("\n[b %s]WHERE[/]" % MUTE)
        roots = self.roots()
        for root in install.known_roots(self.home):
            if root not in roots:
                roots.append(root)
        for root in roots:
            lines.append("[%s] ▸ %s[/]" % (WHERE, root))
        lines.append("[%s]   %s[/]" % (WHERE, self.bin_dir()))
        return "\n".join(lines)

    def main_manage(self) -> None:
        groups = self.manage_sections()
        if not groups:
            self._main.mount(
                Static(
                    "[%s]Nothing from this collection is installed in these "
                    "locations.[/]" % MUTE
                )
            )
            return
        for title, detail, items in groups:
            self._main.mount(self.section_header(title, detail))
            for item in items:
                self._main.mount(ManageRow(item, False))

    def manage_rows(self) -> list:
        return list(self._main.query(ManageRow))

    def render_main(self) -> None:
        if self.pane == "manage":
            self._main.remove_children()
            self.main_manage()
            rows = self.manage_rows()
            if rows:
                rows[0].focus()
            return
        self._main.remove_children()
        renderer = {
            0: self.main_dashboard,
            1: self.main_where,
            2: self.main_which,
            3: self.main_mode,
            4: self.main_review,
        }[self.step]
        renderer()
        # `.first()` raises when a query is empty, and a step can legitimately
        # have nothing focusable (the review screen is prose).
        focusable = self.rows() or self.choices()
        if focusable:
            focusable[0].focus()

    def section_header(self, title: str, detail: str) -> Static:
        return Static("[b %s]%s[/]\n[%s]%s[/]\n" % (MUTE, title, MUTE, detail))

    def mount_section(self, title: str, detail: str, names: list, external: bool) -> None:
        states = self.states()
        self._main.mount(self.section_header(title, detail))
        for name in names:
            if name == GLOBAL:
                self._main.mount(
                    SkillRow(
                        GLOBAL,
                        states[name],
                        False,
                        name in self.selected,
                        note="always machine-wide",
                        blurb=GLOBAL_SUMMARY,
                    )
                )
                continue
            reviewable = self.reviewable_under(name) if external else []
            expanded = bool(reviewable) and name in self.selected
            self._main.mount(
                SkillRow(
                    name,
                    states[name],
                    False if external else not install.skill_global_default(name),
                    name in self.selected,
                    external,
                    self.hidden_note(reviewable, expanded),
                )
            )
            if expanded:
                for entry, visible, description in reviewable:
                    self._main.mount(HiddenSkillRow(entry, visible, description))

    def main_dashboard(self) -> None:
        groups = self.sections()
        if not groups:
            self._main.mount(Static("[%s]Nothing matches this view.[/]" % MUTE))
            return
        for title, detail, names, external in groups:
            self.mount_section(title, detail, names, external)

    def main_where(self) -> None:
        self._main.mount(
            Static(
                "[b]Where should these skills go?[/]\n\n"
                "[%s]Skills are folders your coding agent reads. They can live in one\n"
                "project, or on your machine for every project at once.[/]\n"
                % MUTE
            )
        )
        self._main.mount(
            ChoiceRow(
                "project",
                "this project — %s" % self.project_dir,
                "writes ./.claude/skills/ and ./.agents/skills/; only agents "
                "opened here see them",
                self.scope == "project",
                WHERE,
            )
        )
        self._main.mount(
            ChoiceRow(
                "user",
                "machine-wide — %s" % Path.home(),
                "every project sees them, including unrelated ones",
                self.scope == "user",
                WHERE,
            )
        )

    def main_which(self) -> None:
        self._main.mount(
            Static(
                "[b]Which skills does this project need?[/]\n\n"
                "[%s]The colour on each row is what will happen if you pick it.[/]\n"
                % MUTE
            )
        )
        self.mount_section(
            "YOUR SKILLS",
            "versioned in this checkout; installed as a copy or a link",
            list(self.bundled),
            False,
        )
        self.mount_section(
            "EXTERNAL TOOLS",
            "third-party; each installed and registered by its own CLI",
            list(self.external),
            True,
        )
        self.mount_section(
            "GLOBAL INSTRUCTIONS",
            "user-level AGENTS.md files; diffed and backed up like a skill",
            [GLOBAL],
            False,
        )
        narrow = [n for n in self.bundled if not install.skill_global_default(n)]
        if narrow and self.scope == "user":
            self._main.mount(
                Static(
                    "\n[%s]▲ %s is marked repo-level only — narrow enough that "
                    "installing it\n  machine-wide costs you context in every "
                    "unrelated session.[/]" % (ADVISE, ", ".join(narrow))
                )
            )

    def main_mode(self) -> None:
        self._main.mount(
            Static(
                "[b]Copy the files, or link to this checkout?[/]\n\n"
                "[%s]Both are reversible. Linking keeps one source of truth; copying\n"
                "survives moving or deleting this repository.[/]\n" % MUTE
            )
        )
        self._main.mount(
            ChoiceRow(
                "copy", "copy the files",
                "independent of this checkout; the safe default across machines",
                self.mode == "copy", ADD,
            )
        )
        self._main.mount(
            ChoiceRow(
                "link", "link to this checkout",
                "edits here appear instantly; breaks if the repo moves",
                self.mode == "link", ADD,
            )
        )

    def main_review(self) -> None:
        plan = self.plan()
        if not plan:
            self._main.mount(
                Static(
                    "[b]Nothing selected.[/]\n\n[%s]Press Escape to go back and "
                    "choose at least one skill.[/]" % MUTE
                )
            )
            return
        roots = self.roots()
        lines = ["[b]Nothing has been written yet. Here is the plan.[/]\n"]
        writes = backups = 0
        for name, state, verb, external in plan:
            colour, label, _ = external_meaning(state) if external else MEANING[state]
            lines.append("%s [b]%s[/]" % (pill(verb.upper(), BG, colour), name))
            if external:
                tool = install.external_tool(name)
                lines.append("   [%s]%s[/]" % (MUTE, tool.origin))
                lines.append(
                    "   [%s]needs %s on PATH; ignores copy/link — its installer "
                    "decides the shape[/]" % (ADVISE, tool.requires)
                )
                lines.append("")
                continue
            if name == GLOBAL:
                # Per-file, not per-root: the two managed files live in fixed
                # home locations, and each may differ independently.
                for path, file_state in install.global_instruction_status(
                    self.home, self.mode
                ):
                    if file_state == "current":
                        lines.append(
                            "   [%s]= %s already identical[/]" % (MUTE, path)
                        )
                        continue
                    lines.append("   [%s]→[/] [%s]%s[/]" % (colour, WHERE, path))
                    writes += 1
                    if file_state == "differs":
                        backups += 1
                        lines.append(
                            "   [%s]↺ old copy moved to %s[/]"
                            % (REPLACE,
                               path.parent.parent / ".skills-backups" / path.parent.name)
                        )
                lines.append("")
                continue
            if verb == "skip":
                lines.append("   [%s]already identical to this checkout[/]" % MUTE)
            else:
                for root in roots:
                    lines.append("   [%s]→[/] [%s]%s[/]" % (colour, WHERE, root / name))
                    writes += 1
                if verb == "replace":
                    backups += 1
                    lines.append(
                        "   [%s]↺ old copy moved to %s[/]"
                        % (REPLACE, roots[0].parent / ".skills-backups")
                    )
            lines.append("")
        lines.append("[%s]%s[/]" % (HI, "─" * 54))
        lines.append(
            "[%s]%d write%s[/]  [%s]%d backup%s[/]  [%s]0 deletions[/]"
            % (ADD, writes, "" if writes == 1 else "s",
               REPLACE, backups, "" if backups == 1 else "s", KEEP)
        )
        lines.append(
            "\n[%s]Every replaced file stays recoverable from .skills-backups/.[/]" % MUTE
        )
        outside = [name for name, _, _, external in plan if external]
        if outside:
            lines.append(
                "[%s]Counts cover this checkout's own writes only. %s %s its "
                "own installer, so what it writes is neither counted here nor "
                "backed up by this tool.[/]"
                % (MUTE, ", ".join(outside), "runs" if len(outside) == 1 else "run")
            )
        self._main.mount(Static("\n".join(lines)))

    def render_foot(self) -> None:
        if self.pane == "manage":
            keys = [
                ("SPACE", "select", YOU), ("A", "all", YOU), ("X", "apply", REMOVE),
                ("U", "skills", MUTE), ("S", "scope", WHERE), ("Q", "quit", MUTE),
            ]
            self._foot.update("  ".join(chip(k, v, c) for k, v, c in keys))
            return
        if self.guided():
            keys = [("↑↓", "move", MUTE)]
            if self.step in (1, 2, 3):
                keys.append(("SPACE", "choose", YOU))
            if self.step == 4:
                keys.append(("↵", "write it", REPLACE))
            else:
                keys.append(("↵", "next", ADD))
            if self.step > 1:
                keys.append(("ESC", "back", MUTE))
            keys.append(("Q", "quit", MUTE))
        else:
            keys = [
                ("SPACE", "select", YOU), ("A", "all", YOU), ("↵", "preview", MUTE),
                ("V", "view", MUTE), ("S", "scope", WHERE), ("M", "mode", MUTE),
                ("I", "install", REPLACE), ("G", "guided", MUTE), ("Q", "quit", MUTE),
            ]
        self._foot.update("  ".join(chip(k, v, c) for k, v, c in keys))

    def render_status(self, message: str = "") -> None:
        if message:
            self._status.update(message)
            return
        count = (
            sum(1 for row in self.manage_rows() if row.selected)
            if self.pane == "manage"
            else len(self.selected)
        )
        self._status.update(
            "[%s]nothing selected[/]" % MUTE
            if not count
            else "[%s]%d selected[/]" % (YOU, count)
        )

    def tick(self) -> None:
        if not self._spinning:
            return
        self._frame += 1
        glyph = SPINNER[self._frame % len(SPINNER)]
        self.render_status("[%s]%s[/] [%s]%s…[/]" % (YOU, glyph, MUTE, self._spin_verb))

    # -- actions --------------------------------------------------------

    def focused_row(self):
        node = self.focused
        types = (SkillRow, ChoiceRow, HiddenSkillRow, ManageRow)
        return node if isinstance(node, types) else None

    def action_move(self, delta: int) -> None:
        options = self.nav_rows() or self.choices()
        if not options:
            return
        current = self.focused_row()
        index = options.index(current) if current in options else 0
        options[(index + delta) % len(options)].focus()

    def toggle_model_visibility(self, row: HiddenSkillRow) -> None:
        """Flip one nested skill between hidden and model-visible.

        Applies through install.set_model_invocation and records the choice,
        so install_matt_skills re-applies it after an update.
        """
        roots = self.roots()
        row.visible_to_model = not row.visible_to_model
        for root in roots:
            if (root / row.skill / "SKILL.md").is_file():
                install.set_model_invocation(root / row.skill, row.visible_to_model)
        install.record_model_decisions(
            roots, {row.skill: "enabled" if row.visible_to_model else "hidden"}
        )
        row.redraw()
        for parent in self.rows():
            reviewable = (
                self.reviewable_under(parent.skill)
                if parent.external and parent.selected
                else []
            )
            if reviewable:
                parent.note = self.hidden_note(reviewable, expanded=True)
                parent.redraw()
        self.render_status(
            "[%s]%s: %s[/]"
            % (
                ADD if row.visible_to_model else MUTE,
                row.skill,
                "visible to the model" if row.visible_to_model else "hidden",
            )
        )

    def set_expansion(self, row: SkillRow) -> None:
        """Mount or remove the sub-rows under one external row, in place.

        Rebuilding the whole list would drop focus (the new widgets only
        accept it after the next message-pump cycle), so only the sub-rows
        and the parent's note change; every other widget stays put.
        """
        reviewable = self.reviewable_under(row.skill)
        if not reviewable:
            return
        for sub in self._main.query(HiddenSkillRow):
            sub.remove()
        expanded = row.selected
        row.note = self.hidden_note(reviewable, expanded)
        row.redraw()
        if expanded:
            self._main.mount_all(
                [
                    HiddenSkillRow(entry, visible, description)
                    for entry, visible, description in reviewable
                ],
                after=row,
            )

    def action_toggle(self) -> None:
        row = self.focused_row()
        if isinstance(row, ManageRow):
            row.toggle()
            self.render_status()
        elif isinstance(row, HiddenSkillRow):
            self.toggle_model_visibility(row)
        elif isinstance(row, SkillRow):
            row.toggle()
            if row.selected:
                self.selected.add(row.skill)
            else:
                self.selected.discard(row.skill)
            if row.external:
                self.set_expansion(row)
            self.render_status()
        elif isinstance(row, ChoiceRow):
            if self.step == 1:
                self.scope = row.value
                self.render_head()
            else:
                self.mode = row.value
            for other in self.choices():
                other.chosen = other.value == row.value
                other.redraw()

    def action_toggle_all(self) -> None:
        if self.pane == "manage":
            rows = self.manage_rows()
            if not rows:
                return
            value = not all(row.selected for row in rows)
            for row in rows:
                row.selected = value
                row.redraw()
            self.render_status()
            return
        rows = [row for row in self.rows()]
        if not rows:
            return
        value = not all(row.selected for row in rows)
        for row in rows:
            row.selected = value
            row.redraw()
            if value:
                self.selected.add(row.skill)
            else:
                self.selected.discard(row.skill)
        for row in rows:
            if row.external:
                self.set_expansion(row)
        self.render_status()

    def action_advance(self) -> None:
        if not self.guided():
            row = self.focused_row()
            if isinstance(row, SkillRow):
                self.push_screen(PreviewScreen(row.skill))
            return
        if self.step == 4:
            self.start_install()
            return
        self.step += 1
        self.render_all()

    def action_back(self) -> None:
        if self.guided() and self.step > 1:
            self.step -= 1
            self.render_all()

    def inert_here(self, what: str) -> bool:
        """Refuse a key that has no meaning in the manage pane, and say why."""
        if self.pane != "manage":
            return False
        self.render_status("[%s]the %s applies to installing[/]" % (ADVISE, what))
        return True

    def action_cycle_view(self) -> None:
        if self.inert_here("view filter"):
            return
        if self.guided():
            return
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        self.render_side()
        self.render_main()


    def action_cycle_scope(self) -> None:
        if self.guided():
            return
        self.scope = "user" if self.scope == "project" else "project"
        self.render_all()

    def action_cycle_mode(self) -> None:
        if self.inert_here("copy-link mode"):
            return
        if self.guided():
            return
        self.mode = "link" if self.mode == "copy" else "copy"
        self.render_side()
        # The global-instructions pill answers "what would this mode write",
        # so it can flip with the mode. Repaint that row in place — a full
        # render_main would steal focus back to the top — unless a filtered
        # view means the flip changes which rows are listed at all.
        if self.view == "all":
            states = self.states()
            for row in self.rows():
                if row.skill == GLOBAL:
                    row.state = states[GLOBAL]
                    row.redraw()
        else:
            self.render_main()

    def action_toggle_guided(self) -> None:
        if self.inert_here("guided setup"):
            return
        self.step = 0 if self.guided() else 1
        self.render_all()

    def action_toggle_pane(self) -> None:
        self.pane = "manage" if self.pane == "skills" else "skills"
        self.selected.clear()
        self.step = 0
        self.render_all()

    def action_install(self) -> None:
        if self.inert_here("install key"):
            return
        if self.guided():
            return
        if not self.selected:
            self.render_status("[%s]select at least one skill first[/]" % ADVISE)
            return
        states = self.states()
        differing = [n for n in sorted(self.selected) if states[n] == OUTDATED]
        if differing:
            self.push_screen(ConfirmReplace(differing), self._after_confirm)
            return
        self.start_install()

    def _after_confirm(self, approved: Optional[bool]) -> None:
        if not approved:
            self.render_status("[%s]no changes made[/]" % MUTE)
            return
        if self.pane == "manage":
            self.start_apply()
        else:
            self.start_install()

    # -- managing -------------------------------------------------------

    def action_apply(self) -> None:
        if self.pane != "manage":
            return
        entries = self._removal_entries()
        if not entries:
            self.render_status("[%s]select something first[/]" % ADVISE)
            return
        if any(consequence != "none" for _label, consequence, _paths in entries):
            self.push_screen(ConfirmChanges(entries), self._after_confirm)
            return
        self.start_apply()

    def _removal_entries(self) -> list:
        """(label, consequence, paths) for every selected row, for the modal."""
        entries = []
        for row in self.manage_rows():
            if not row.selected:
                continue
            item = row.item
            _colour, _label, verb = manage_meaning(item)
            if verb == "explain":
                entries.append(
                    ("%s: %s" % (item.name, item.detail), "none", [])
                )
                continue
            entries.append(
                ("%s %s" % (verb, item.name), "remove", [str(item.path)])
            )
        return entries

    def start_apply(self) -> None:
        items = [row.item for row in self.manage_rows() if row.selected]
        if not items:
            self.render_status("[%s]select something first[/]" % ADVISE)
            return
        self._spinning = True
        self._spin_verb = "removing"
        self.removed_count = 0
        self.failures = 0
        self.apply_worker(items)

    @work(thread=True, exclusive=True)
    def apply_worker(self, items: list) -> None:
        """Every removal goes through an install.* primitive, never through here."""
        done = []
        roots = []
        for item in items:
            try:
                if item.kind == "skill":
                    install.uninstall_one(
                        item.name, item.root, False, allow_unrecorded=not item.recorded
                    )
                    if item.root not in roots:
                        roots.append(item.root)
                elif item.kind == "managed-file":
                    install.uninstall_managed_file(item.path, False, home=self.home)
                elif item.kind == "shim":
                    install.remove_shims(
                        argparse.Namespace(
                            home=self.home, dry_run=False, add_path=False
                        )
                    )
                elif item.kind == "external":
                    self.uninstall_external(item.name)
                else:  # Defensive: discover() emits no other kind.
                    raise install.InstallError(f"nothing wired to remove a {item.kind}")
                done.append(item.name)
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_failure, item.name, str(exc))
        for root in roots:
            install.prune_root(root, False)
        self.call_from_thread(self.finish_apply, done)

    def external_uninstallers(self) -> dict:
        """name -> a no-argument call removing what this collection recorded.

        A table rather than a branch, exactly like external_installers: a
        registry entry with nothing wired to it is a missing key a test can
        see, not a failure that waits for somebody to press apply.
        """
        return {
            "graphify": lambda: install.uninstall_external(
                "graphify", self.roots(), False
            ),
            "matt-skills": lambda: install.uninstall_external(
                "matt-skills", self.roots(), False
            ),
        }

    def uninstall_external(self, name: str) -> None:
        runner = self.external_uninstallers().get(name)
        if runner is None:
            raise install.InstallError(f"no uninstaller wired for external tool: {name}")
        runner()

    def finish_apply(self, names: Sequence[str]) -> None:
        self._spinning = False
        self._spin_verb = "installing"
        self.removed_count = len(names) - self.failures
        self.render_all()
        if self.failures:
            self.render_status(
                "[%s]× %d failed[/] [%s]· %d removed[/]"
                % (FAIL, self.failures, MUTE, self.removed_count)
            )
        else:
            self.render_status(
                "[%s]✓ %d removed[/]" % (KEEP, self.removed_count)
            )

    # -- installing -----------------------------------------------------

    def start_install(self) -> None:
        names = [name for name in self.bundled if name in self.selected]
        outside = [name for name in self.external if name in self.selected]
        wants_global = GLOBAL in self.selected
        if not names and not outside and not wants_global:
            self.render_status("[%s]select at least one skill first[/]" % ADVISE)
            return
        self._spinning = True
        self.installed_count = 0
        self.failures = 0
        self.install_worker(names, outside, wants_global, self.roots())

    @work(thread=True, exclusive=True)
    def install_worker(
        self, names: list, outside: list, wants_global: bool, roots: list
    ) -> None:
        for root in roots:
            for name in names:
                try:
                    install.install_one(
                        install.SOURCE_ROOT / name, root, self.mode, True, False
                    )
                except (install.InstallError, OSError) as exc:
                    self.call_from_thread(self.note_failure, name, str(exc))
            if names:
                self.call_from_thread(
                    install.write_receipt, root, names, self.mode, False
                )
        done = list(names)
        if wants_global:
            done.append(GLOBAL)
            try:
                install.install_global_instructions(self.home, self.mode, False)
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_failure, GLOBAL, str(exc))
        for name in outside:
            try:
                self.install_external(name)
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_failure, name, str(exc))
        self.call_from_thread(self.finish, done + outside)

    def external_installers(self) -> dict:
        """name -> a no-argument call handing that tool to its own installer.

        A table rather than a branch so a registry entry with nothing wired to
        it is a missing key a test can see, instead of a failure that surfaces
        only when somebody selects the row and presses install.
        """
        return {
            "graphify": lambda: install.install_graphify(
                self.agents, self.scope, self.project_dir, False, lambda _line: None
            ),
            # force=True because an external row already present offers
            # "update", and install_one backs the old copy up before replacing.
            "matt-skills": lambda: install.install_matt_skills(
                self.agents, self.roots(), True, False, lambda _line: None
            ),
        }

    def install_external(self, name: str) -> None:
        runner = self.external_installers().get(name)
        if runner is None:
            raise install.InstallError(f"no installer wired for external tool: {name}")
        runner()

    def note_failure(self, name: str, message: str) -> None:
        self.failures += 1
        self.render_status("[%s]× %s: %s[/]" % (FAIL, name, message))

    def finish(self, names: Sequence[str]) -> None:
        self._spinning = False
        self.installed_count = len(names) - self.failures
        self.selected.clear()
        if self.guided():
            self.step = 0
        self.render_all()
        if self.failures:
            self.render_status(
                "[%s]× %d failed[/] [%s]· %d installed[/]"
                % (FAIL, self.failures, MUTE, self.installed_count)
            )
        else:
            roots = self.roots()
            undecided = {
                name for root in roots for name in install.hidden_skills(root)
            } - set(install.read_model_decisions(roots))
            hint = (
                " [%s]· %d hidden from the model — select matt-skills to review[/]"
                % (ADVISE, len(undecided))
                if undecided
                else ""
            )
            self.render_status(
                "[%s]✓ %d installed[/] [%s]· %s[/]%s"
                % (KEEP, self.installed_count, WHERE,
                   " · ".join(str(root) for root in self.roots()), hint)
            )


def run(
    project_dir: Path,
    scope: str = "project",
    agents: Optional[Sequence[str]] = None,
    mode: str = "copy",
    guided: Optional[bool] = None,
    pane: str = "skills",
    home: Optional[Path] = None,
) -> int:
    app = SkillsApp(project_dir, scope, agents, mode, guided, home, pane)
    app.run()
    return 0
