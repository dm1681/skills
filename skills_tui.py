#!/usr/bin/env python3
"""A Textual dashboard for installing this collection's skills.

Layout is one shell in both modes: a header, a sidebar, a main pane, and a key
bar. The sidebar carries filters and destination in dashboard mode, and a step
rail in guided mode; nothing else moves.

COLOUR CONTRACT - every hue means one thing everywhere, and the four hues a
state can take run along one valence ramp:

    grey  ──▶  green  ──▶  peach  ──▶  red
    nothing    a gain     destructive   failure
    happens               (recoverable)

    mauve   you          selection, focus, the active step. Never data.
    grey    nothing      up to date. Selecting it writes nothing, so it is
                         also the hue of plain context: summaries, inert keys,
                         and an upstream check that reached no answer - unknown
                         is marked `? upstream` where a current row is bare,
                         because unknown must never read as up to date. A
                         count of zero is grey too, whatever it counts: a plan
                         with no deletions must not carry a warning colour
                         about deletions.
    green   install      a write that only adds; nothing existing is lost.
                         Also the road to one - a finished guided step - and a
                         skill the model can actually see, which is the gain
                         the install was for. A hidden one is grey, and so is
                         an origin check that found nothing to install. An
                         *aggregate* - the review's write total, the key that
                         commits the plan - is green only when that promise
                         holds of the whole plan; one removal or one
                         replacement in it makes it peach.
    peach   destructive  an overwrite *or* a removal. Both take the same
                         backup-then-mutate path, so the old copy is always
                         recoverable and neither is a failure.
    red     failure      errors only, so a healthy run is provably red-free.
                         An uninstall that is refused is a failure and is red;
                         the uninstall itself never is.
    teal    location     paths, roots, scope. Where things live.
    yellow  advisory     allowed, but probably not what you want: a version
                         nobody bumped, a repo-level skill going machine-wide,
                         a checkout origin has moved past, a removal this
                         collection will refuse because it did not install it.
    blue    version      a version that is not itself the news - it matches,
                         or it is the only one there is. It left the state
                         palette so a settled version cannot read as a state,
                         and it is the only hue a version number wears: the
                         collection version in the header is flat blue beside
                         the gradiented product name, not painted along with
                         it. A version that has *moved* is the news, so it is
                         drawn `old → new` in peach, with the replacement it
                         is describing; an unknown or vendored one is grey,
                         because it is context and not a number.

A skill's state is painted in the colour of the *consequence* of selecting it,
so the same hue carries from the state pill to the action column to the review
step to the progress bar. "Consequence" includes the mode: an identical copy
is grey for a `copy` install and peach for a `link` one, because that is a
backup-and-replace, so pressing `M` can honestly repaint every row.

The install itself runs through `install.install_one` — the
global-instructions row through `install.install_global_instructions` — so
backups, receipts, and root resolution stay defined in one place.
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
# The ramp, in order: nothing happens, a gain, a destructive change, failure.
MUTE = "#7f849c"     # grey  - up to date, and plain context
GAIN = "#a6e3a1"     # green - install: a write that only adds
REPLACE = "#fab387"  # peach - an overwrite, backed up first
FAIL = "#f38ba8"     # red   - failure only
WHERE = "#94e2d5"
ADVISE = "#f9e2af"
# Blue was the install hue until the ramp put green there. It is not retired:
# it is now the version hue, and carries no state meaning at all.
VERSION = "#89b4fa"
BG = "#1e1e2e"
PANEL = "#181825"
HI = "#313244"
FG = "#cdd6f4"

# state -> (colour, pill label, verb once selected)
MEANING = {
    AVAILABLE: (GAIN, "NOT INSTALLED", "install"),
    OUTDATED: (REPLACE, "DIFFERS", "replace"),
    INSTALLED: (MUTE, "UP TO DATE", "skip"),
}
VIEWS = ("all", "differs", "up to date")
VIEW_STATES = {"differs": OUTDATED, "up to date": INSTALLED}
GLOBAL = "global-instructions"
GLOBAL_SUMMARY = (
    "user-level AGENTS.md for every agent: ~/.agents/AGENTS.md + ~/.claude/CLAUDE.md"
)
GLOBAL_STATES = {"missing": AVAILABLE, "current": INSTALLED, "differs": OUTDATED}
# Wide enough for the longest name any row renders. A name that overflows does
# not wrap - it shoves the version column and the pill right, so one long skill
# breaks the alignment of every row beside it. `olympus-report-progress` is 23
# characters and already did. A test pins this against the real collection, so
# a longer name added later fails there rather than silently skewing a column.
NAME_WIDTH = 26

REMOVE_LABEL = "REMOVE"
REMOVE_VERB = "uninstall"
# Answers to "has origin moved past this checkout for this skill". The absent
# third answer is `""` — current, or never asked — which draws no mark at all.
UPSTREAM_BEHIND = "behind"
UPSTREAM_UNKNOWN = "unknown"
UPSTREAM_MARKS = {
    # Yellow: installable, but origin has newer. Grey: nobody could tell, and
    # grey is context rather than a claim — the one thing this must not do is
    # let "could not check" look identical to "up to date".
    UPSTREAM_BEHIND: ("▲ upstream", ADVISE),
    UPSTREAM_UNKNOWN: ("? upstream", MUTE),
}
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

/* Nested under the external row that installed them, so indented and on the
   screen background rather than the panel the parent rows sit on. */
HiddenSkillRow { height: 3; padding: 0 2; margin: 0 0 1 3; background: %(bg)s; }
HiddenSkillRow:focus { background: %(hi)s; }
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


def skill_state(name: str, roots: Sequence[Path], mode: str = "copy") -> str:
    """Worst state across every destination root, for the mode now chosen.

    A skill counts as installed only when every root holds a copy matching this
    checkout; one stale root is enough to call the whole thing outdated,
    because that is the root an agent might read.

    Mode-sensitive for the same reason `global_state` is, and using the same
    test `install_one` itself makes (`destination_matches_mode`): a copy and a
    symlink can hold byte-identical trees, so installing an identical *copy*
    in `link` mode still moves the old directory into `.skills-backups/` and
    writes a symlink over it. Painted from contents alone that row said `UP TO
    DATE → skip`, asked no confirmation, and reported `0 writes  0 backups`
    for a run that backed a directory up -- grey promising exactly what peach
    is for. Flipping `M` now flips the pill, which is the colour contract's
    promise: the colour on a row is what will happen if you pick it.
    """
    source = install.SOURCE_ROOT / name
    states = []
    for root in roots:
        destination = root / name
        if not (destination.exists() or destination.is_symlink()):
            states.append(AVAILABLE)
        elif install.trees_equal(destination, source) and (
            install.destination_matches_mode(destination, mode)
        ):
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
        return (GAIN, "NOT INSTALLED", "install")
    return (REPLACE, "PRESENT", "update")


VERSION_WIDTH = 17
UNKNOWN_VERSION = "—"
VENDORED_VERSION = "vendored"
UNBUMPED = "unbumped"


def version_text(raw: str) -> str:
    """One version string as it is displayed.

    `install.skill_version` returns "" for a skill that states no version, and
    "" means *unknown*, not 0.0.0 — so it renders as a dash rather than as a
    number that would sort below every real one.
    """
    if not raw:
        return UNKNOWN_VERSION
    return raw if raw[:1].lower() == "v" else "v" + raw


def version_column(segments: Sequence[tuple]) -> str:
    """Render (text, colour) pairs into a column of fixed *display* width.

    Padding is measured on the plain text because markup tags occupy no
    columns. Without that, a long version would push the state pill sideways
    on its own row and nothing would line up; with it, an unusually long
    version is truncated instead and the pill never moves.
    """
    rendered = []
    used = 0
    for text, colour in segments:
        room = VERSION_WIDTH - used
        if room <= 0:
            break
        if len(text) > room:
            text = text[: room - 1] + "…"
        rendered.append("[%s]%s[/]" % (colour, text))
        used += len(text)
    return "".join(rendered) + " " * (VERSION_WIDTH - used)


def installed_versions(name: str, roots: Sequence[Path]) -> list:
    """The version each root's installed copy states, roots without one aside.

    Read from the installed `SKILL.md` rather than assumed from the checkout:
    the whole point of the field is that the copy on disk can be older than
    what is here, and only the copy can say so.
    """
    versions = []
    for root in roots:
        destination = root / name
        if destination.exists() or destination.is_symlink():
            versions.append(install.skill_version(destination))
    return versions


def version_field(name: str, state: str, roots: Sequence[Path]) -> tuple:
    """(column markup, unbumped) for one bundled skill's version.

    Four shapes, in the colours the contract already assigns:

    - vendored: the word `vendored` in grey. A vendored skill carries no
      `version:` key by design — its frontmatter is inside the bytes
      `install.vendored_status` hashes — so it is neither missing nor unknown.
    - installed at a different version: `old → new` in peach, the same hue as
      the replacement it is describing.
    - anything else: a single version in blue, the version hue, because a
      version that matches is context rather than a consequence.

    The second return value is the case the field itself introduces: contents
    that differ while versions match, meaning somebody edited a skill without
    bumping it. It is advisory yellow — installable, but probably not what the
    author intended. It asks the disk rather than reading `OUTDATED` off the
    state, because a row is also outdated when the only difference is copy vs
    link, and calling identical bytes "unbumped" would be a warning about
    nothing.
    """
    if install.skill_is_vendored(name):
        return (version_column([(VENDORED_VERSION, MUTE)]), False)
    checkout = install.skill_version(install.SOURCE_ROOT / name)
    stale = [value for value in installed_versions(name, roots) if value != checkout]
    if stale:
        moved = "%s → %s" % (version_text(stale[0]), version_text(checkout))
        return (version_column([(moved, REPLACE)]), False)
    unbumped = state == OUTDATED and any(
        ((root / name).exists() or (root / name).is_symlink())
        and not install.trees_equal(root / name, install.SOURCE_ROOT / name)
        for root in roots
    )
    segments = [(version_text(checkout), VERSION if checkout else MUTE)]
    if unbumped:
        segments.append((" ▲", ADVISE))
    return (version_column(segments), unbumped)


def removable(name: str, roots: Sequence[Path]) -> bool:
    """Whether a bundled row has anything on disk to remove.

    Asks the disk, not the row's state. `skill_state` reports the *worst*
    state across the roots, so a skill installed in `~/.agents/skills` and
    absent from `~/.claude/skills` reads as `AVAILABLE` — and refusing `x`
    there would deny a removal for a live, agent-readable copy, which is the
    half-installed case the uninstaller exists for. `exists() or is_symlink()`
    is the same presence test `install_one` and `uninstall_one` make, so what
    the key offers and what the removal does cannot disagree.
    """
    return any(
        (root / name).exists() or (root / name).is_symlink() for root in roots
    )


def collection_owns(name: str, root: Path) -> bool:
    """Whether `uninstall_one` will remove `root / name` without `--force`.

    The same three-way test `uninstall_one` makes, stated here so the review
    screen can promise a deletion only where one will actually happen. A
    directory of that name that this collection neither recorded nor matches
    is somebody else's — the case the guard exists for on a shared
    `~/.claude/skills` — and planning a `×` and a `↺` for it would describe
    two events that the run then refuses to perform.
    """
    return (
        name in install.receipt_skills(root)
        or name in install.externally_recorded(root)
        or install.trees_equal(root / name, install.SOURCE_ROOT / name)
    )


def upstream_mark(name: str, freshness) -> str:
    """Which upstream marker one row carries, given the last check.

    `install.skills_behind_origin` leaves a name out of `behind` when the
    question could not be answered, so absence is unknown and never zero. That
    distinction is the whole point of the call: a name filled in as 0 would
    paint "up to date" over a machine that never reached the remote.
    """
    if freshness is None:
        return ""
    count = freshness.behind.get(name)
    if count is None:
        return UPSTREAM_UNKNOWN
    return UPSTREAM_BEHIND if count else ""


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
    """One skill: mark, name, version, state pill, advisory, action."""

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
        version: str = "",
        caution: str = "",
        removing: bool = False,
        upstream: str = "",
        failure: str = "",
    ):
        super().__init__()
        self.skill = name
        self.state = state
        self.repo_level = repo_level
        self.selected = selected
        self.external = external
        self.note = note
        # Pre-rendered by `version_field`: a fixed-width column, or "" for a
        # row that has no version to state (an external tool, the global
        # instructions), which then renders no column at all.
        self.version = version
        # Advisory word sitting beside the pill - today only `unbumped`.
        self.caution = caution
        # Marked for removal. A separate axis from `selected` because the two
        # are opposite consequences, and one row cannot carry both.
        self.removing = removing
        # "" until someone presses `u`; then one of UPSTREAM_MARKS' keys, or
        # "" again for a skill origin has not moved past.
        self.upstream = upstream
        # Why the last run could not do what this row asked for. The status
        # line scrolls past; the row is where the person was looking.
        self.failure = failure
        # A row that is not a skill directory (the global-instructions row)
        # supplies its own one-liner; a skill row looks its own up.
        self.blurb = blurb

    def on_mount(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        colour, label, verb = (
            external_meaning(self.state) if self.external else MEANING[self.state]
        )
        if self.removing:
            # Peach, never red. A removal backs the old copy up exactly as a
            # replacement does — same path, same .skills-backups directory —
            # so it is destructive-but-recoverable, which is what peach means.
            # Red here would put a colour reserved for failure on a healthy
            # run the user asked for.
            colour, label, verb = (REPLACE, REMOVE_LABEL, REMOVE_VERB)
        chosen = self.selected or self.removing
        # Left edge answers "what happens to this one", mauve only when it is
        # yours - i.e. picked, whichever way.
        self.styles.border_left = ("thick", YOU if chosen else colour)
        mark = "[%s]◆[/]" % YOU if chosen else "[%s]◇[/]" % MUTE
        action = "[%s]→ %s[/]" % (colour, verb) if chosen else ""
        advisories = [(word, ADVISE) for word in (
            "repo-level only" if self.repo_level else "", self.caution,
        ) if word]
        if self.upstream in UPSTREAM_MARKS:
            advisories.append(UPSTREAM_MARKS[self.upstream])
        advisory = "".join(
            "  [%s]%s[/]" % (hue, word) for word, hue in advisories
        )
        # The column pads itself; the separator is the row's, so a version
        # truncated to the full width still keeps a gap before the pill.
        version = self.version + " " if self.version else ""
        summary = self.blurb or (
            install.external_tool(self.skill).summary
            if self.external
            else install.skill_summary(self.skill)
        )
        note = "  [%s]%s[/]" % (ADVISE, self.note) if self.note else ""
        # The one place red belongs on a row: something was asked for and did
        # not happen.
        failure = "  [%s]× %s[/]" % (FAIL, self.failure) if self.failure else ""
        self.update(
            "%s [b]%-*s[/] %s%s%s  %s\n    [%s]%s[/]%s%s"
            % (mark, NAME_WIDTH, self.skill, version, pill(label, BG, colour),
               advisory, action, MUTE, summary, note, failure)
        )

    def toggle(self) -> None:
        self.selected = not self.selected
        if self.selected:
            # Selecting drops any removal mark: the same name in both groups
            # of one plan would ask for a write and a delete at once.
            self.removing = False
        self.redraw()

    def mark_removal(self) -> bool:
        """Flip the removal mark, and report where it landed."""
        self.removing = not self.removing
        if self.removing:
            self.selected = False
        self.redraw()
        return self.removing


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
    """Asks before backing up and replacing installs that differ.

    Also the last word before a removal, which is why one screen carries both:
    they are the same promise — the old copy is moved aside first — and two
    screens would ask twice for one keypress.
    """

    BINDINGS = [
        Binding("y", "yes", "replace"),
        Binding("n", "no", "cancel"),
        Binding("escape", "no", "cancel"),
    ]

    def __init__(self, names: Sequence[str], removals: Sequence[str] = ()) -> None:
        super().__init__()
        self.names = list(names)
        self.removals = list(removals)

    def blocks(self) -> list:
        """The paragraphs of the prompt, removals first.

        Removals lead because they are the half a reader most needs to catch
        before pressing Y: a replacement leaves a skill of the same name in
        place, a removal leaves nothing there at all.
        """
        parts = []
        if self.removals:
            parts.append(
                "%s [b]%d installed skill%s will be removed[/]\n\n%s"
                % (
                    pill(REMOVE_LABEL, BG, REPLACE),
                    len(self.removals),
                    "" if len(self.removals) == 1 else "s",
                    "\n".join("  [%s]×[/] %s" % (REPLACE, n) for n in self.removals),
                )
            )
        if self.names:
            parts.append(
                "%s [b]%d installed skill%s differ%s from this checkout[/]\n\n%s"
                % (
                    pill("REPLACE", BG, REPLACE),
                    len(self.names),
                    "" if len(self.names) == 1 else "s",
                    "s" if len(self.names) == 1 else "",
                    "\n".join("  [%s]→[/] %s" % (REPLACE, n) for n in self.names),
                )
            )
        parts.append(
            "[%s]Each one is moved into an adjacent .skills-backups directory\n"
            "first, so a replacement and a removal are equally recoverable.[/]"
            % MUTE
        )
        verb = "replace" if self.names else "remove"
        parts.append(
            "%s  %s"
            % (
                chip("Y", "go ahead" if self.names and self.removals else verb, REPLACE),
                chip("N", "cancel", MUTE),
            )
        )
        return parts

    def compose(self) -> ComposeResult:
        yield Container(Static("\n\n".join(self.blocks())), id="confirm")

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
        colour = GAIN if self.visible_to_model else MUTE
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
        Binding("x", "mark_remove", "remove"),
        Binding("u", "check_upstream", "upstream"),
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
        home: Optional[Path] = None,
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
        # Marked for removal. Disjoint from `selected` by construction — the
        # row flips one off when it turns the other on.
        self.marked = set()
        self.view = "all"
        self.installed_count = 0
        self.removed_count = 0
        self.failures = 0
        self.removal_failures = 0
        # name -> why the last run could not do what that row asked for. Kept
        # on the app rather than only on the widget because `finish` rebuilds
        # the list, and a failure that vanishes on the repaint is a failure
        # nobody read.
        self.failed = {}
        # The last answer from `install.skills_behind_origin`, or None while
        # nobody has asked. None is not "up to date": it is "not asked", and
        # the rows draw no upstream mark at all until it stops being None.
        # It starts None because that call fetches, and this constructor runs
        # before the first frame.
        self.freshness = None
        self._checking = False
        self._guided_requested = guided
        self.step = 0
        self._frame = 0
        self._spinning = False

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
        states = {name: skill_state(name, roots, self.mode) for name in self.bundled}
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
            if isinstance(widget, (SkillRow, HiddenSkillRow))
        ]

    def choices(self) -> list:
        return list(self._main.query(ChoiceRow))

    def hidden_note(self, reviewable: list, expanded: bool) -> str:
        """The parent row's one-line pointer at its collapsed sub-rows.

        Silent at zero. `reviewable` deliberately keeps previously-decided
        skills so a choice can be revisited, so a user who has just unhidden
        everything still has entries here and nothing hidden — and the note is
        drawn in advisory yellow, which would then be a warning about the
        state they just finished choosing. `finish()` guards its own version
        of this hint with `if undecided`; this is the same guard.
        """
        if not reviewable:
            return ""
        count = sum(1 for _, visible, _ in reviewable if not visible)
        if not count:
            return ""
        return "%s %d hidden from the model%s" % (
            "▾" if expanded else "▸",
            count,
            "" if expanded else " — select to review",
        )

    def reviewable_under(self, name: str) -> list:
        """Hidden-skill entries shown, collapsed, under one external row.

        Two external tools now install skills carrying
        disable-model-invocation — mattpocock/skills hides 20 of its 35, pstack
        39 of its 44 — and a root scan cannot attribute an installed directory
        to the tool that placed it. So each install records what it placed, and
        a row shows only its own: without that, both rows would list the union
        and each would offer to unhide skills it never installed.

        A root written before that record existed has none, which is why the
        fallback is the old behaviour rather than an empty list: the skills are
        really there and really hidden, and showing them under matt-skills is
        how they were reviewable yesterday.
        """
        if name not in install.EXTERNAL_NAMES:
            return []
        roots = self.roots()
        recorded = {
            skill for root in roots for skill in install.external_skill_names(root, name)
        }
        if recorded:
            return [entry for entry in self.reviewable() if entry[0] in recorded]
        if name not in install.UPSTREAM_TOOL_NAMES:
            # A tool installed by its own CLI never told this installer what it
            # placed, so it can never be credited with an unclaimed skill. The
            # elimination fallback below is for a collection *this* installer
            # copied in before it kept records; crediting graphify by the same
            # rule made its row list mattpocock's hidden skills, and unhiding
            # one there rewrote a file graphify has never touched.
            return []
        marker = install.external_tool(name).marker
        if not any((root / marker).is_dir() for root in roots):
            return []
        # Installed here, but by a release that wrote no record. Everything not
        # claimed by a collection that *did* record is this one's by
        # elimination — which keeps a legacy matt-skills root reviewable after
        # a pstack install rather than silently emptying the row.
        claimed = {
            skill
            for root in roots
            for tool in install.read_external_manifest(root)
            for skill in install.external_skill_names(root, tool)
        }
        # A self-installing tool's own directory is not up for election either.
        # Elimination can only hand this row what no *other* explanation
        # covers, and "graphify placed graphify" is an explanation even though
        # graphify records nothing -- without this, the legacy fallback handed
        # matt-skills a file matt-skills never wrote.
        selfish = {
            install.external_tool(name).marker
            for name in install.EXTERNAL_NAMES
            if name not in install.UPSTREAM_TOOL_NAMES
        }
        return [
            entry
            for entry in self.reviewable()
            if entry[0] not in claimed and entry[0] not in selfish
        ]

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
        return self.step > 0

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

    def removals(self) -> list:
        """Bundled skills marked for removal, in listed order.

        Kept apart from `plan` rather than added to it as another verb: a
        removal runs through `install.uninstall_many` rather than
        `install_one`, counts as a deletion rather than a write, and is
        reviewed in its own group above the installs.

        Filtered by what is on disk *now*: a mark set in one scope survives a
        press of `s`, and carrying it into a scope where the skill was never
        installed would put a peach `REMOVE` on a row with nothing to remove
        and then report it removed.
        """
        roots = self.roots()
        return [
            name
            for name in self.bundled
            if name in self.marked and removable(name, roots)
        ]

    # -- rendering ------------------------------------------------------

    def render_all(self) -> None:
        self.render_head()
        self.render_side()
        self.render_main()
        self.render_foot()
        self.render_status()

    def render_head(self) -> None:
        # The product name gradients into the version hue and the version
        # itself is flat blue: the contract says mauve is never data and blue
        # is a version, and a gradient running across the digits painted a
        # version in six blends of neither.
        self._head.update(
            "%s [%s]%s[/]   [%s]%s[/]   %s"
            % (
                gradient("skills", YOU, VERSION),
                VERSION,
                install.VERSION,
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
            "all": len(self.bundled) + len(self.external),
            "differs": sum(1 for s in states.values() if s == OUTDATED),
            "up to date": sum(1 for s in states.values() if s == INSTALLED),
        }
        colours = {"all": YOU, "differs": REPLACE, "up to date": MUTE}
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
                lines.append("[%s]  ✓ %s[/]" % (GAIN, label))
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

    def section_header(self, title: str, detail: str) -> Static:
        return Static("[b %s]%s[/]\n[%s]%s[/]\n" % (MUTE, title, MUTE, detail))

    def mount_section(self, title: str, detail: str, names: list, external: bool) -> None:
        states = self.states()
        roots = self.roots()
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
            # Only this checkout's own skills carry a version: an external
            # tool's files belong to somebody else's package.
            column, unbumped = ("", False)
            if not external:
                column, unbumped = version_field(name, states[name], roots)
            self._main.mount(
                SkillRow(
                    name,
                    states[name],
                    False if external else not install.skill_global_default(name),
                    name in self.selected,
                    external,
                    self.hidden_note(reviewable, expanded),
                    version=column,
                    caution=UNBUMPED if unbumped else "",
                    # Same filter `removals()` applies: a mark carried into a
                    # scope where this skill is not installed draws nothing.
                    removing=name in self.marked and removable(name, roots),
                    failure=self.failed.get(name, ""),
                    # An external tool's files are its own installer's, and so
                    # is its upstream; neither question is this checkout's to
                    # answer, so those rows carry no mark either way.
                    upstream="" if external else upstream_mark(name, self.freshness),
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
                self.mode == "copy", GAIN,
            )
        )
        self._main.mount(
            ChoiceRow(
                "link", "link to this checkout",
                "edits here appear instantly; breaks if the repo moves",
                self.mode == "link", GAIN,
            )
        )

    def main_review(self) -> None:
        plan = self.plan()
        removals = self.removals()
        if not plan and not removals:
            self._main.mount(
                Static(
                    "[b]Nothing selected.[/]\n\n[%s]Press Escape to go back and "
                    "choose at least one skill.[/]" % MUTE
                )
            )
            return
        roots = self.roots()
        lines = ["[b]Nothing has been written yet. Here is the plan.[/]\n"]
        writes = backups = deletions = 0
        # Removals first, above the installs: they are the half of the plan a
        # reader most needs to catch, and burying them under a list of writes
        # is how one gets approved unread.
        for name in removals:
            lines.append("%s [b]%s[/]" % (pill(REMOVE_LABEL, BG, REPLACE), name))
            for root in roots:
                destination = root / name
                if not (destination.exists() or destination.is_symlink()):
                    lines.append("   [%s]= nothing at %s[/]" % (MUTE, destination))
                    continue
                if not collection_owns(name, root):
                    # Advisory rather than a ×: `uninstall_one` will refuse
                    # this one, so counting a deletion and a backup here would
                    # promise two events that never happen.
                    lines.append(
                        "   [%s]! %s is not installed by this collection — "
                        "the removal will be refused[/]" % (ADVISE, destination)
                    )
                    continue
                deletions += 1
                lines.append("   [%s]×[/] [%s]%s[/]" % (REPLACE, WHERE, destination))
                # One ↺ line per backup actually taken, and the counter
                # follows the lines rather than the names.
                backups += 1
                lines.append(
                    "   [%s]↺ moved to %s[/]"
                    % (REPLACE, root.parent / ".skills-backups" / root.name)
                )
            lines.append("")
        if removals:
            lines.append(
                "[%s]Nothing is deleted outright. Every removal is moved into "
                ".skills-backups/\nfirst, so it comes back the same way a "
                "replacement does.[/]\n" % MUTE
            )
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
            "[%s]%d write%s[/]  [%s]%d backup%s[/]  [%s]%d deletion%s[/]"
            # Each count in the hue of what it actually is, and grey at zero:
            # nothing happening is grey, and a green or peach zero would
            # colour a plan for something it does not contain. Writes are
            # green only when every one of them adds — green's contract is
            # "nothing existing is lost", which a write that took a backup
            # falsifies, so a plan with backups paints its writes peach.
            % (MUTE if not writes else (REPLACE if backups else GAIN),
               writes, "" if writes == 1 else "s",
               REPLACE if backups else MUTE,
               backups, "" if backups == 1 else "s",
               REPLACE if deletions else MUTE,
               deletions, "" if deletions == 1 else "s")
        )
        lines.append(
            "\n[%s]Every replaced or removed file stays recoverable from "
            ".skills-backups/.[/]" % MUTE
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

    def commit_hue(self) -> str:
        """The colour of the key that writes the plan.

        Green is "a write that only adds; nothing existing is lost", so the
        commit key can only be green when that is true of the whole plan. A
        plan holding a removal or a replacement is destructive-but-
        recoverable, which is peach — the same hue its own rows and its own
        totals line already carry.
        """
        if self.removals():
            return REPLACE
        if any(verb in ("replace", "update") for _, _, verb, _ in self.plan()):
            return REPLACE
        return GAIN

    def render_foot(self) -> None:
        if self.guided():
            keys = [("↑↓", "move", MUTE)]
            if self.step in (1, 2, 3):
                keys.append(("SPACE", "choose", YOU))
            if self.step == 2:
                keys.append(("X", "remove", REPLACE))
            if self.step == 4:
                keys.append(("↵", "write it", self.commit_hue()))
            else:
                keys.append(("↵", "next", MUTE))
            if self.step > 1:
                keys.append(("ESC", "back", MUTE))
            keys.append(("Q", "quit", MUTE))
        else:
            keys = [
                ("SPACE", "select", YOU), ("A", "all", YOU), ("↵", "preview", MUTE),
                ("V", "view", MUTE), ("S", "scope", WHERE), ("M", "mode", MUTE),
                ("I", "install", self.commit_hue()), ("X", "remove", REPLACE),
                ("U", "upstream", MUTE), ("G", "guided", MUTE), ("Q", "quit", MUTE),
            ]
        self._foot.update("  ".join(chip(k, v, c) for k, v, c in keys))

    def render_status(self, message: str = "") -> None:
        if message:
            self._status.update(message)
            return
        parts = []
        if self.selected:
            parts.append("[%s]%d selected[/]" % (YOU, len(self.selected)))
        removals = self.removals()
        if removals:
            parts.append("[%s]%d to remove[/]" % (REPLACE, len(removals)))
        self._status.update(
            "  ".join(parts) if parts else "[%s]nothing selected[/]" % MUTE
        )

    def tick(self) -> None:
        # Two workers, two flags: the spinner turns while either is running,
        # and neither may switch the other off. One shared flag let a late
        # origin answer stop the spinner and overwrite the status line while
        # an install was still writing files.
        if not (self._spinning or self._checking):
            return
        self._frame += 1
        glyph = SPINNER[self._frame % len(SPINNER)]
        self.render_status(
            "[%s]%s[/] [%s]%s[/]"
            % (YOU, glyph, MUTE, "checking origin…" if self._checking else "installing…")
        )

    # -- actions --------------------------------------------------------

    def focused_row(self):
        node = self.focused
        return node if isinstance(node, (SkillRow, ChoiceRow, HiddenSkillRow)) else None

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
                GAIN if row.visible_to_model else MUTE,
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
        if isinstance(row, HiddenSkillRow):
            self.toggle_model_visibility(row)
        elif isinstance(row, SkillRow):
            row.toggle()
            if row.selected:
                self.selected.add(row.skill)
                # `SkillRow.toggle` already dropped the widget's mark; this
                # keeps the app's two sets disjoint alongside it.
                self.marked.discard(row.skill)
            else:
                self.selected.discard(row.skill)
            if row.external:
                self.set_expansion(row)
            self.render_status()
            # The commit key is painted from the plan, so it has to be
            # repainted whenever the plan changes.
            self.render_foot()
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
            if value:
                row.removing = False
                self.marked.discard(row.skill)
            row.redraw()
            if value:
                self.selected.add(row.skill)
            else:
                self.selected.discard(row.skill)
        for row in rows:
            if row.external:
                self.set_expansion(row)
        self.render_status()
        self.render_foot()

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
        # Every pill answers "what would this mode write", so every pill can
        # flip with the mode: an identical *copy* is not up to date for a
        # `link` install, it is a backup-and-replace. Repaint the rows in
        # place — a full render_main would steal focus back to the top —
        # unless a filtered view means the flip changes which rows are listed
        # at all.
        if self.view == "all":
            states = self.states()
            roots = self.roots()
            for row in self.rows():
                if row.external:
                    continue
                row.state = states[row.skill]
                if row.skill != GLOBAL:
                    column, unbumped = version_field(row.skill, row.state, roots)
                    row.version = column
                    row.caution = UNBUMPED if unbumped else ""
                row.redraw()
        else:
            self.render_main()

    def action_mark_remove(self) -> None:
        """Mark or unmark the focused row for removal.

        Three rows decline the key rather than promising a removal that cannot
        happen: an external tool, whose files its own CLI placed and which
        `uninstall_one` would rightly refuse as not ours; the
        global-instructions row, which is managed files and not a skill
        directory; and a row with nothing on disk, where a removal would be a
        no-op dressed up as a plan.
        """
        row = self.focused_row()
        if not isinstance(row, SkillRow) or row.external or row.skill == GLOBAL:
            return
        if not removable(row.skill, self.roots()):
            self.render_status(
                "[%s]%s is not installed here — nothing to remove[/]"
                % (ADVISE, row.skill)
            )
            return
        if row.mark_removal():
            self.marked.add(row.skill)
            self.selected.discard(row.skill)
        else:
            self.marked.discard(row.skill)
        self.render_status()
        self.render_foot()

    def action_check_upstream(self) -> None:
        """Ask origin, on purpose and only when asked.

        `install.skills_behind_origin` fetches, and `install.py` documents why
        that must never be part of drawing a frame: a dashboard that reaches
        the network to open would hang on a machine with no route to the
        remote, and would do it before anyone chose anything. So it is a key,
        it runs off the UI thread, and until it answers the rows say nothing
        about upstream at all.
        """
        if self._spinning or self._checking:
            return
        self._checking = True
        self.upstream_worker(list(self.bundled))

    @work(thread=True, exclusive=False)
    def upstream_worker(self, names: list) -> None:
        try:
            freshness = install.skills_behind_origin(names)
        except Exception as exc:  # noqa: BLE001 - see below
            # `skills_behind_origin` documents that every failure degrades to
            # unknown and none raises. This catch is the belt to that braces:
            # an unforeseen one must leave a dashboard saying "could not
            # check", never a traceback over somebody's install.
            freshness = install.SkillFreshness(
                install.ORIGIN_UNKNOWN, "could not check origin: %s" % exc, {}
            )
        self.call_from_thread(self.show_upstream, freshness)

    def show_upstream(self, freshness) -> None:
        """Fill the answer into the rows already on screen.

        In place rather than through `render_main`, so the row someone was
        reading keeps focus while the marks appear under their eye.

        It clears its own flag and never `_spinning`: a thread worker cannot
        be cancelled, so this callback can land after an install has started,
        and switching that install's spinner off would leave a dashboard
        looking idle while it writes.
        """
        self._checking = False
        self.freshness = freshness
        for row in self.rows():
            if row.external or row.skill == GLOBAL:
                continue
            row.upstream = upstream_mark(row.skill, freshness)
            row.redraw()
        colours = {
            install.ORIGIN_BEHIND: ADVISE,
            install.ORIGIN_UNKNOWN: MUTE,
            # Grey, not green: origin having nothing new is the up-to-date
            # answer, and nothing is written. The sentence and the row marks
            # keep it apart from unknown; the hue is not asked to.
            install.ORIGIN_CURRENT: MUTE,
        }
        if self._spinning:
            # An install started after the check did. The marks are in, but
            # the status line belongs to the run that is still going: an
            # origin verdict painted over `installing…`, or over the `✓ N
            # installed` line that follows it, answers a question nobody is
            # asking any more.
            return
        self.render_status(
            "[%s]%s[/]" % (colours.get(freshness.state, MUTE), freshness.detail)
        )

    def action_toggle_guided(self) -> None:
        self.step = 0 if self.guided() else 1
        self.render_all()

    def action_install(self) -> None:
        if self.guided():
            return
        if self._spinning:
            return
        if self._checking:
            # The origin check is bounded and short, and refusing for its
            # duration is what keeps the two workers from sharing a spinner.
            self.render_status(
                "[%s]still checking origin — press I again in a moment[/]" % ADVISE
            )
            return
        if not self.selected and not self.removals():
            self.render_status("[%s]select at least one skill first[/]" % ADVISE)
            return
        states = self.states()
        differing = [n for n in sorted(self.selected) if states[n] == OUTDATED]
        removals = self.removals()
        # A removal always asks, even when no install differs: it is the one
        # thing here that leaves an empty space behind.
        if differing or removals:
            self.push_screen(
                ConfirmReplace(differing, removals), self._after_confirm
            )
            return
        self.start_install()

    def _after_confirm(self, approved: Optional[bool]) -> None:
        if approved:
            self.start_install()
        else:
            self.render_status("[%s]no changes made[/]" % MUTE)

    # -- installing -----------------------------------------------------

    def start_install(self) -> None:
        # Both entrances funnel here — `i` on the dashboard and `↵` on the
        # guided review — so the "one worker at a time" rule is stated here as
        # well as at the key, and neither path can start a write underneath a
        # fetch that is still running.
        if self._spinning or self._checking:
            self.render_status(
                "[%s]still checking origin — try again in a moment[/]" % ADVISE
            )
            return
        names = [name for name in self.bundled if name in self.selected]
        outside = [name for name in self.external if name in self.selected]
        wants_global = GLOBAL in self.selected
        removals = self.removals()
        if not names and not outside and not wants_global and not removals:
            self.render_status("[%s]select at least one skill first[/]" % ADVISE)
            return
        self._spinning = True
        self.installed_count = 0
        self.removed_count = 0
        self.failures = 0
        self.removal_failures = 0
        # Last run's failures are answered by this run: keeping them would
        # leave a red × on a row that just succeeded.
        self.failed = {}
        for row in self.rows():
            if row.failure:
                row.failure = ""
                row.redraw()
        self.install_worker(names, outside, wants_global, self.roots(), removals)

    @work(thread=True, exclusive=True)
    def install_worker(
        self,
        names: list,
        outside: list,
        wants_global: bool,
        roots: list,
        removals: Optional[list] = None,
    ) -> None:
        removed = 0
        # Removals first, so a name being cleared out cannot race a receipt
        # this same run is about to rewrite.
        for name in removals or []:
            try:
                # `uninstall_many` and not `uninstall_one`: the multi-root
                # loop, the receipt pruning and the roots-index cleanup are
                # install.py's to define, exactly as install_one owns the
                # write side. One name at a time so a refusal on one row does
                # not swallow the rows after it.
                messages = install.uninstall_many(
                    roots,
                    skills=[name],
                    home=self.home,
                    emit=lambda _line: None,
                )
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_removal_failure, name, str(exc))
            else:
                # Count what happened, not what was asked. `uninstall_many`
                # answers a directory that is already gone with `absent`,
                # which is a success and not a removal, and a skill installed
                # in two roots is two removals under one name — the same unit
                # the review screen counts as deletions, so the plan's "2
                # deletions" and the result's "2 removed" can no longer
                # disagree.
                removed += sum(
                    1 for line in messages if line.startswith("removed")
                )
        for root in roots:
            for name in names:
                try:
                    install.install_one(
                        install.SOURCE_ROOT / name, root, self.mode, True, False
                    )
                except (install.InstallError, OSError) as exc:
                    self.call_from_thread(self.note_failure, name, str(exc))
            if names:
                self.call_from_thread(self.record_root, root, names)
        done = list(names)
        if wants_global:
            done.append(GLOBAL)
            try:
                install.install_global_instructions(self.home, self.mode, False)
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_failure, GLOBAL, str(exc))
        installed_outside = []
        for name in outside:
            try:
                self.install_external(name)
                installed_outside.append(name)
            except (install.InstallError, OSError) as exc:
                self.call_from_thread(self.note_failure, name, str(exc))
        if installed_outside:
            # An external collection writes real skills into a real root, and a
            # root holding only those has no receipt — so nothing else would
            # ever put it in the index, and `--status --all` stayed blind to a
            # machine whose only install came through this row. Deliberately
            # not by dropping the `if names:` guard above: `record_root` also
            # writes a receipt, and planting an empty one in a root that has
            # none would change what `root_status` reports about it.
            for root in roots:
                self.call_from_thread(self.index_root, root)
        self.call_from_thread(self.finish, done + outside, removed)

    def index_root(self, root: Path) -> None:
        """Record the root in the machine-wide index, and nothing else.

        The half of `record_root` that applies when this collection wrote no
        receipt here because it installed none of its own skills.
        """
        try:
            install.remember_root(
                root, self.scope, install.root_agent(root), self.home, False
            )
        except OSError:
            # A cache whose contract is that losing it costs nothing must not
            # be able to fail an install that already succeeded.
            pass

    def record_root(self, root: Path, names: Sequence[str]) -> None:
        """The bookkeeping half of an install, exactly as `execute_install`
        does it: a receipt saying what is in this root, and an index entry
        saying the root exists at all.

        The receipt is **merged, not replaced**. `write_receipt` rewrites the
        whole `skills` list, so handing it one run's selection dropped every
        skill an earlier run put there — and a name missing from the receipt
        is one `uninstall_one` refuses to remove once it drifts, with no
        `--force` anywhere in this dashboard. Removals run before this in the
        same worker and prune the receipt themselves, so what is read back
        here already excludes them.

        `remember_root` is what `skills status --all` enumerates. Without it
        the dashboard — the default, interactive install path — could only
        ever shrink that index, because the uninstall side does call
        `forget_root`.
        """
        merged = sorted(set(install.receipt_skills(root)) | set(names))
        install.write_receipt(root, merged, self.mode, False)
        try:
            install.remember_root(
                root, self.scope, install.root_agent(root), self.home, False
            )
        except OSError:
            # The index is a cache and its contract is that losing it costs
            # nothing; the skills are installed and the receipt records them.
            # Failing the install over a home that cannot be written — CI, a
            # container, a read-only mount — would report a run that worked as
            # a run that failed.
            pass

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
            # allow_conflicts=False because that offer is to refresh this
            # collection, not to take a name from another one: pstack and
            # matt-skills both ship `tdd`, and a silent swap here would leave
            # the row reading "update" while the skill changed meaning. The
            # refusal surfaces through note_failure, in red, like any failure.
            "matt-skills": lambda: install.install_matt_skills(
                self.agents, self.roots(), True, False, lambda _line: None,
                allow_conflicts=False,
            ),
            "pstack": lambda: install.install_pstack(
                self.agents, self.roots(), True, False, lambda _line: None,
                allow_conflicts=False,
            ),
        }

    def install_external(self, name: str) -> None:
        runner = self.external_installers().get(name)
        if runner is None:
            raise install.InstallError(f"no installer wired for external tool: {name}")
        runner()

    def note_failure(self, name: str, message: str) -> None:
        self.failures += 1
        self.remember_failure(name, message)

    def note_removal_failure(self, name: str, message: str) -> None:
        """A removal that did not happen, in the one colour reserved for it.

        `uninstall_one` refuses to remove a directory absent from the receipt
        that also differs from this checkout — the guard that makes pointing
        this at a shared `~/.claude/skills` safe. A refusal the user cannot
        see is a mark that silently stays marked, so it is red on the row and
        red in the status line, and it is counted apart from the installs so
        that "3 installed" stays true when a fourth row's removal was refused.
        """
        self.removal_failures += 1
        self.remember_failure(name, message)

    def remember_failure(self, name: str, message: str) -> None:
        self.failed[name] = message
        for row in self.rows():
            if row.skill == name:
                row.failure = message
                row.redraw()
        self.render_status("[%s]× %s: %s[/]" % (FAIL, name, message))

    def finish(self, names: Sequence[str], removed: int = 0) -> None:
        self._spinning = False
        # By name, not by attempt: `install_worker` reports a failure once per
        # (root, name), so subtracting that count from a list of names made a
        # skill that failed in both roots of an `--agent all` run read as
        # `-1 installed`.
        self.installed_count = len([n for n in names if n not in self.failed])
        self.removed_count = removed
        self.selected.clear()
        # Only the marks this run answered: a refused removal keeps its mark,
        # so the row still says what it is waiting to do.
        self.marked.intersection_update(self.failed)
        if self.guided():
            self.step = 0
        self.render_all()
        if self.failures or self.removal_failures:
            self.render_status(
                "[%s]× %d failed[/] [%s]· %d installed%s[/]"
                # Names, like the count beside it: one skill refused in two
                # roots is one row with a red × on it, not two failures.
                % (FAIL, len(self.failed), MUTE,
                   self.installed_count,
                   " · %d removed" % removed if removed else "")
            )
        else:
            roots = self.roots()
            undecided = {
                name for root in roots for name in install.hidden_skills(root)
            } - set(install.read_model_decisions(roots))
            # Name the rows that actually hold them. Two collections install
            # hidden skills now, so a hardcoded name sends the reader to a row
            # that unfolds nothing when the other one is what they installed.
            rows = " or ".join(
                tool
                for tool in install.EXTERNAL_NAMES
                if any(entry[0] in undecided for entry in self.reviewable_under(tool))
            )
            hint = (
                " [%s]· %d hidden from the model — select %s to review[/]"
                % (ADVISE, len(undecided), rows or "the collection that installed them")
                if undecided
                else ""
            )
            # A run that only removed things should not open with "0
            # installed": the count that is zero is the one that was never
            # asked for.
            done = []
            if self.installed_count or not removed:
                done.append("[%s]✓ %d installed[/]" % (GAIN, self.installed_count))
            if removed:
                done.append("[%s]✓ %d removed[/]" % (REPLACE, removed))
            self.render_status(
                "%s [%s]· %s[/]%s"
                % (" ".join(done), WHERE,
                   " · ".join(str(root) for root in self.roots()), hint)
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
