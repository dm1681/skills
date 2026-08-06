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
    red     failure    errors only, so a healthy run is provably red-free.

A skill's state is painted in the colour of the *consequence* of selecting it,
so the same hue carries from the state pill to the action column to the review
step to the progress bar.

The install itself runs through `install.install_one`, so backups, receipts,
and root resolution stay defined in one place.
"""

from __future__ import annotations

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
STEPS = ("Where to install", "Which skills", "Copy or link", "Review")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
RECEIPT = ".dm1681-skills.json"

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
""" % {
    "bg": BG, "fg": FG, "panel": PANEL, "hi": HI, "replace": REPLACE, "you": YOU,
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


def _without_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4 :].lstrip() if end != -1 else text


class SkillRow(Static):
    """One skill: selection mark, name, state pill, advisory, action."""

    can_focus = True

    def __init__(self, name: str, state: str, repo_level: bool, selected: bool):
        super().__init__()
        self.skill = name
        self.state = state
        self.repo_level = repo_level
        self.selected = selected

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        colour, label, verb = MEANING[self.state]
        # Left edge answers "what happens to this one", mauve only when it is
        # yours - i.e. selected.
        self.styles.border_left = ("thick", YOU if self.selected else colour)
        mark = "[%s]◆[/]" % YOU if self.selected else "[%s]◇[/]" % MUTE
        action = "[%s]→ %s[/]" % (colour, verb) if self.selected else ""
        advisory = "  [%s]repo-level only[/]" % ADVISE if self.repo_level else ""
        summary = install.skill_summary(self.skill)
        self.update(
            "%s [b]%-22s[/] %s%s  %s\n    [%s]%s[/]"
            % (mark, self.skill, pill(label, BG, colour), advisory, action, MUTE, summary)
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


class PreviewScreen(ModalScreen):
    """The focused skill's SKILL.md."""

    BINDINGS = [Binding("escape,enter,q", "close", "close")]

    def __init__(self, skill: str) -> None:
        super().__init__()
        # Not `self.name`: Widget exposes `name` as a read-only property.
        self.skill = skill

    def compose(self) -> ComposeResult:
        body = (install.SOURCE_ROOT / self.skill / "SKILL.md").read_text(encoding="utf-8")
        yield VerticalScroll(Markdown(_without_frontmatter(body)), id="preview")

    def action_close(self) -> None:
        self.dismiss(None)


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
        Binding("q", "quit", "quit"),
    ]

    def __init__(
        self,
        project_dir: Path,
        scope: str = "project",
        agents: Optional[Sequence[str]] = None,
        mode: str = "copy",
        guided: Optional[bool] = None,
    ) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.scope = scope
        self.agents = list(agents or [])
        self.mode = mode
        self.bundled = install.available_skills()
        self.selected = set()
        self.view = "all"
        self.installed_count = 0
        self.failures = 0
        self._guided_requested = guided
        self.step = 0
        self._frame = 0
        self._spinning = False

    # -- shell ----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="head")
        yield Horizontal(
            Static(id="side"), VerticalScroll(id="main"), id="body"
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
            self.agents, self.scope, Path.home(), self.project_dir, None
        )

    def has_receipt(self) -> bool:
        """Whether this destination has been installed into before."""
        return any((root / RECEIPT).is_file() for root in self.roots())

    def target(self) -> Path:
        return self.project_dir if self.scope == "project" else Path.home()

    def states(self) -> dict:
        roots = self.roots()
        return {name: skill_state(name, roots) for name in self.bundled}

    def visible(self) -> list:
        states = self.states()
        if self.view == "all":
            return list(self.bundled)
        wanted = VIEW_STATES[self.view]
        return [name for name in self.bundled if states[name] == wanted]

    def rows(self) -> list:
        return list(self._main.query(SkillRow))

    def choices(self) -> list:
        return list(self._main.query(ChoiceRow))

    def guided(self) -> bool:
        return self.step > 0

    def plan(self) -> list:
        """(name, state, verb) for each selected skill, in listed order."""
        states = self.states()
        return [
            (name, states[name], MEANING[states[name]][2])
            for name in self.bundled
            if name in self.selected
        ]

    # -- rendering ------------------------------------------------------

    def render_all(self) -> None:
        self.render_head()
        self.render_side()
        self.render_main()
        self.render_foot()
        self.render_status()

    def render_head(self) -> None:
        self._head.update(
            "%s   [%s]%s[/]   %s"
            % (
                gradient("skills %s" % install.VERSION, YOU, ADD),
                WHERE,
                self.target(),
                pill("PROJECT" if self.scope == "project" else "MACHINE-WIDE", BG, WHERE),
            )
        )

    def render_side(self) -> None:
        self._side.update(self.step_rail() if self.guided() else self.filters())

    def filters(self) -> str:
        states = self.states()
        counts = {
            "all": len(self.bundled),
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

    def render_main(self) -> None:
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

    def main_dashboard(self) -> None:
        states = self.states()
        names = self.visible()
        if not names:
            self._main.mount(Static("[%s]Nothing matches this view.[/]" % MUTE))
            return
        for name in names:
            self._main.mount(
                SkillRow(
                    name,
                    states[name],
                    not install.skill_global_default(name),
                    name in self.selected,
                )
            )

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
        states = self.states()
        self._main.mount(
            Static(
                "[b]Which skills does this project need?[/]\n\n"
                "[%s]The colour on each row is what will happen if you pick it.[/]\n"
                % MUTE
            )
        )
        for name in self.bundled:
            self._main.mount(
                SkillRow(
                    name,
                    states[name],
                    not install.skill_global_default(name),
                    name in self.selected,
                )
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
        for name, state, verb in plan:
            colour, label, _ = MEANING[state]
            lines.append("%s [b]%s[/]" % (pill(verb.upper(), BG, colour), name))
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
        self._main.mount(Static("\n".join(lines)))

    def render_foot(self) -> None:
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
        count = len(self.selected)
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
        self.render_status("[%s]%s[/] [%s]installing…[/]" % (YOU, glyph, MUTE))

    # -- actions --------------------------------------------------------

    def focused_row(self):
        node = self.focused
        return node if isinstance(node, (SkillRow, ChoiceRow)) else None

    def action_move(self, delta: int) -> None:
        options = self.rows() or self.choices()
        if not options:
            return
        current = self.focused_row()
        index = options.index(current) if current in options else 0
        options[(index + delta) % len(options)].focus()

    def action_toggle(self) -> None:
        row = self.focused_row()
        if isinstance(row, SkillRow):
            row.toggle()
            if row.selected:
                self.selected.add(row.skill)
            else:
                self.selected.discard(row.skill)
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

    def action_cycle_view(self) -> None:
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
        if self.guided():
            return
        self.mode = "link" if self.mode == "copy" else "copy"
        self.render_side()

    def action_toggle_guided(self) -> None:
        self.step = 0 if self.guided() else 1
        self.render_all()

    def action_install(self) -> None:
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
        if approved:
            self.start_install()
        else:
            self.render_status("[%s]no changes made[/]" % MUTE)

    # -- installing -----------------------------------------------------

    def start_install(self) -> None:
        names = [name for name in self.bundled if name in self.selected]
        if not names:
            self.render_status("[%s]select at least one skill first[/]" % ADVISE)
            return
        self._spinning = True
        self.installed_count = 0
        self.failures = 0
        self.install_worker(names, self.roots())

    @work(thread=True, exclusive=True)
    def install_worker(self, names: list, roots: list) -> None:
        for root in roots:
            for name in names:
                try:
                    install.install_one(
                        install.SOURCE_ROOT / name, root, self.mode, True, False
                    )
                except (install.InstallError, OSError) as exc:
                    self.call_from_thread(self.note_failure, name, str(exc))
            self.call_from_thread(install.write_receipt, root, names, self.mode, False)
        self.call_from_thread(self.finish, names)

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
            self.render_status(
                "[%s]✓ %d installed[/] [%s]· %s[/]"
                % (KEEP, self.installed_count, WHERE,
                   " · ".join(str(root) for root in self.roots()))
            )


def run(
    project_dir: Path,
    scope: str = "project",
    agents: Optional[Sequence[str]] = None,
    mode: str = "copy",
    guided: Optional[bool] = None,
) -> int:
    app = SkillsApp(project_dir, scope, agents, mode, guided)
    app.run()
    return 0
