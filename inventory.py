#!/usr/bin/env python3
"""Find, explain, and plan fixes for inconsistent installs.

`install.py` owns what is on disk: it installs, removes, backs up, and records.
This module only *reads* that picture and reports where it disagrees with
itself — a link whose target moved, one skill installed twice with different
contents, a receipt naming a directory nobody can find. Every mutation it
offers is an `install.*` primitive called through `apply_fix`; nothing here
writes to disk on its own.

Two rules keep it honest:

- `inventory.scan` composes `install.discover` rather than walking roots
  itself, so there is exactly one place in this collection that lists what is
  installed, and a `Placement` is always an `install.Installed` plus the
  comparisons detection needs.
- This module never imports textual. `skills doctor` and `install.py --doctor`
  are scripted paths, and a machine without the dashboard's dependency still
  has to be able to ask what is wrong with it.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional, Sequence, TextIO

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import install  # noqa: E402


SCOPE_USER, SCOPE_PROJECT, SCOPE_TARGET = "user", "project", "target"
SCOPE_ORDER = (SCOPE_USER, SCOPE_PROJECT, SCOPE_TARGET)

BROKEN_LINK = "broken-link"
INCOMPLETE = "incomplete"
DUPLICATE_DIVERGED = "duplicate-diverged"
DIVERGED = "diverged-from-source"
STALE_LINK = "stale-link"
SHAPE_MISMATCH = "shape-mismatch"
ORPHAN_RECEIPT = "orphan-receipt"
CORRUPT_RECEIPT = "corrupt-receipt"

# Worst first: a dangling link breaks the skill outright, a receipt that will
# not parse only misleads a later run.
SEVERITY = {
    BROKEN_LINK: 0,
    INCOMPLETE: 1,
    DUPLICATE_DIVERGED: 2,
    DIVERGED: 3,
    STALE_LINK: 4,
    SHAPE_MISMATCH: 5,
    ORPHAN_RECEIPT: 6,
    CORRUPT_RECEIPT: 6,
}
KINDS = tuple(SEVERITY)

REINSTALL, RELINK, UNINSTALL, FORGET, KEEP = (
    "reinstall",
    "relink",
    "uninstall",
    "forget",
    "keep",
)
# Consequence classes, which are what the dashboard paints: a write is peach,
# a removal pink, and something that changes nothing needs no warning at all.
WRITE, REMOVE, NONE = "write", "remove", "none"

DIFF_LINE_CAP = 400
DIFF_FILE_CAP = 256 * 1024
REPORT_SCHEMA = 1


# -- what a scan produces ----------------------------------------------------


class Placement(NamedTuple):
    """One installed skill, enriched with the comparisons detection needs.

    Wraps an `install.Installed` rather than re-walking the tree, so the row a
    finding talks about is the same row `skills status` prints.
    """

    item: install.Installed
    scope: str  # SCOPE_USER | SCOPE_PROJECT | SCOPE_TARGET
    digest: str  # tree_digest of the content, links resolved
    complete: bool  # SKILL.md present
    link_target: Optional[Path]  # resolved target for a link, else None
    matches_source: Optional[bool]  # None when there is no source to compare to

    # Convenience accessors, so detection never spells `placement.item.x`.
    @property
    def name(self) -> str:
        return self.item.name

    @property
    def root(self) -> Path:
        return self.item.root

    @property
    def path(self) -> Path:
        return self.item.path

    @property
    def shape(self) -> Optional[str]:
        return self.item.shape

    @property
    def bundled(self) -> bool:
        return self.item.bundled

    @property
    def recorded_mode(self) -> Optional[str]:
        return self.item.mode

    @property
    def present(self) -> bool:
        """Whether anything is actually on disk.

        `install.discover_skills` lists a recorded entry whose directory is
        gone, and leaves its shape unset to say so.
        """
        return self.item.shape is not None


class Inventory(NamedTuple):
    roots: tuple  # ((root, scope), …) in scanned order
    placements: tuple  # (Placement, …)
    missing_roots: tuple  # registry entries that no longer exist
    unreadable_receipts: tuple  # roots whose receipt exists but will not parse


class Fix(NamedTuple):
    action: str  # REINSTALL | RELINK | UNINSTALL | FORGET | KEEP
    root: Path
    name: str
    mode: str  # "copy" | "link"; meaningful for REINSTALL only


class Resolution(NamedTuple):
    action: str  # headline action, for colour and label
    label: str  # imperative one-liner shown in the UI
    consequence: str  # WRITE | REMOVE | NONE
    fixes: tuple  # (Fix, …) in application order


class Finding(NamedTuple):
    kind: str
    name: str
    severity: int
    detail: str  # one sentence, no markup
    placements: tuple
    resolutions: tuple  # index 0 is the default
    diff_pair: Optional[tuple]  # (left_path, right_path) or None
    diff_labels: tuple  # (left_label, right_label) or ()


# -- discovery ---------------------------------------------------------------


def _registry_scope(root: Path, home: Path) -> str:
    """Label a recorded root by its shape, since the registry stores no scope."""
    if root.name == "skills" and root.parent.name in (".agents", ".claude"):
        return SCOPE_USER if root.parent.parent == home else SCOPE_PROJECT
    return SCOPE_TARGET


def candidate_roots(
    home: Path,
    project_dirs: Sequence[Path] = (),
    extra_roots: Sequence[Path] = (),
    include_registry: bool = True,
) -> list:
    """Every skills root worth scanning, as (root, scope).

    Fixed order and precedence: the user-scope roots, then each named project
    directory's, then everything an earlier install recorded, then roots named
    outright. Deduped by resolved path with the first scope label winning, so a
    root reached twice is never counted as two placements of one skill.
    """
    home = Path(home).expanduser()
    found: list = []
    seen: set = set()

    def add(root: Path, scope: str) -> None:
        try:
            resolved = Path(root).expanduser().resolve()
        except OSError:  # pragma: no cover - resolve() is non-strict
            resolved = Path(root).expanduser()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append((resolved, scope))

    for root in install.resolve_roots(["all"], "user", home, home, None):
        add(root, SCOPE_USER)
    for project in project_dirs:
        for root in install.resolve_roots(
            ["all"], "project", home, Path(project).expanduser(), None
        ):
            add(root, SCOPE_PROJECT)
    if include_registry:
        for root in install.known_roots(home):
            add(root, _registry_scope(root, home))
    for root in extra_roots:
        add(root, SCOPE_TARGET)
    return found


def _recorded_roots(home: Path) -> list:
    """Every root the registry names, present or not.

    `install.known_roots` drops the missing ones, which is right for a sweep
    and wrong for a report that exists to name them.
    """
    return [Path(item) for item in sorted(set(install._read_registry(home)))]


def tree_digest(path: Path) -> str:
    """sha256 over relative paths and file bytes, links resolved.

    A copy and a link of the same tree hash the same on purpose: shape is
    reported separately, so "these two installs disagree" never fires merely
    because one of them is a symlink.
    """
    try:
        base = Path(path).resolve()
    except (OSError, RuntimeError):
        return "missing"
    if not base.exists():
        return "missing"
    digest = hashlib.sha256()
    for item in sorted(base.rglob("*")):
        try:
            relative = item.relative_to(base).as_posix()
        except ValueError:  # pragma: no cover - rglob stays under base
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if item.is_dir():
            digest.update(b"\0dir")
            continue
        try:
            digest.update(item.read_bytes())
        except OSError:
            # A file that vanished mid-scan, or one this user cannot read: a
            # difference the report can show, not a reason to stop scanning.
            digest.update(b"<unreadable>")
    return digest.hexdigest()


def short_digest(digest: str) -> str:
    return digest if digest == "missing" else digest[:8]


def _link_target(path: Path) -> Optional[Path]:
    try:
        if not path.is_symlink():
            return None
        return path.resolve()
    except OSError:  # pragma: no cover - resolve() is non-strict
        return None


def scan(
    home: Path,
    project_dirs: Sequence[Path] = (),
    extra_roots: Sequence[Path] = (),
    include_registry: bool = True,
) -> Inventory:
    """Everything installed in the candidate roots, ready to be judged."""
    home = Path(home).expanduser()
    roots = candidate_roots(home, project_dirs, extra_roots, include_registry)
    scopes = {root: scope for root, scope in roots}
    placements = []
    for item in install.discover([root for root, _scope in roots], home):
        if item.kind != "skill":
            continue
        present = item.shape is not None
        source = install.SOURCE_ROOT / item.name
        placements.append(
            Placement(
                item=item,
                scope=scopes.get(item.root, SCOPE_TARGET),
                digest=tree_digest(item.path) if present else "missing",
                complete=(item.path / "SKILL.md").is_file(),
                link_target=_link_target(item.path) if item.shape == "link" else None,
                matches_source=(
                    install.trees_equal(item.path, source)
                    if present and item.bundled
                    else None
                ),
            )
        )
    missing = (
        [root for root in _recorded_roots(home) if not root.is_dir()]
        if include_registry
        else []
    )
    unreadable = []
    for root, _scope in roots:
        receipt = install.receipt_path(root)
        if not receipt.is_file() or install.read_receipt(root):
            continue
        try:
            raw = receipt.read_bytes().strip()
        except OSError:  # pragma: no cover - is_file() just said otherwise
            raw = b""
        if raw:
            unreadable.append(root)
    return Inventory(
        roots=tuple(roots),
        placements=tuple(placements),
        missing_roots=tuple(missing),
        unreadable_receipts=tuple(unreadable),
    )


# -- detection ---------------------------------------------------------------


def canonical(placements: Sequence[Placement]) -> Placement:
    """The placement other copies of the same skill are judged against."""
    matching = [item for item in placements if item.matches_source]
    if matching:
        return matching[0]
    return sorted(
        placements,
        key=lambda item: (SCOPE_ORDER.index(item.scope), str(item.root)),
    )[0]


def _strip_model_invocation(text: str) -> str:
    """The same SKILL.md with any `disable-model-invocation:` line dropped."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        return text
    block = [
        line
        for line in lines[1:closing]
        if line.partition(":")[0].strip() != install.MODEL_INVOCATION_KEY
    ]
    return "\n".join(lines[:1] + block + lines[closing:])


def _files_under(base: Path) -> dict:
    found = {}
    for path in base.rglob("*"):
        if path.is_file():
            found[path.relative_to(base).as_posix()] = path
    return found


def _only_model_invocation_differs(placement: Placement) -> bool:
    """Whether hiding the skill from the model is the sole difference.

    A skill the user deliberately hid legitimately differs from the checkout.
    Without this, every hidden bundled skill would be reported forever and the
    report would train its reader to ignore it.
    """
    source = install.SOURCE_ROOT / placement.name
    if not (source / "SKILL.md").is_file() or not placement.complete:
        return False
    try:
        left = _files_under(source)
        right = _files_under(placement.path)
        if set(left) != set(right):
            return False
        for relative, path in left.items():
            if relative == "SKILL.md":
                continue
            if path.read_bytes() != right[relative].read_bytes():
                return False
        return _strip_model_invocation(
            left["SKILL.md"].read_text(encoding="utf-8")
        ) == _strip_model_invocation(
            right["SKILL.md"].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError):
        return False


def _finding(
    kind: str,
    name: str,
    detail: str,
    placements: Sequence[Placement],
    bundled: bool,
    diff_pair: Optional[tuple] = None,
    diff_labels: tuple = (),
) -> Finding:
    return Finding(
        kind=kind,
        name=name,
        severity=SEVERITY[kind],
        detail=detail,
        placements=tuple(placements),
        resolutions=resolutions_for(kind, name, placements, bundled),
        diff_pair=diff_pair,
        diff_labels=diff_labels,
    )


def _source_pair(placement: Placement) -> tuple:
    return (
        (install.SOURCE_ROOT / placement.name, placement.path),
        ("this checkout", str(placement.root)),
    )


def findings(inv: Inventory, include_foreign: bool = False) -> list:
    """Every inconsistency, worst first, then by name, then by root path."""
    by_name: dict = {}
    for placement in inv.placements:
        by_name.setdefault(placement.name, []).append(placement)

    results: list = []
    for name in sorted(by_name):
        every = by_name[name]
        bundled = every[0].bundled
        for placement in every:
            if not placement.present:
                results.append(_orphan(placement, bundled))
        live = [placement for placement in every if placement.present]
        if not live:
            continue
        if not bundled and not include_foreign:
            # A skill with no source here can only be inconsistent with itself,
            # and only across roots. matt-skills' dozen identical directories
            # therefore say nothing.
            if len(live) >= 2 and len({item.digest for item in live}) > 1:
                results.append(_duplicate(name, live, bundled))
            continue
        results.extend(_findings_for_name(name, live, bundled))

    for root in inv.unreadable_receipts:
        receipt = install.receipt_path(root)
        results.append(
            Finding(
                kind=CORRUPT_RECEIPT,
                name=str(receipt),
                severity=SEVERITY[CORRUPT_RECEIPT],
                detail=(
                    "the install receipt in %s exists but cannot be parsed" % root
                ),
                placements=(),
                resolutions=resolutions_for(CORRUPT_RECEIPT, str(receipt), (), False),
                diff_pair=None,
                diff_labels=(),
            )
        )
    return sorted(
        results,
        key=lambda finding: (
            finding.severity,
            finding.name,
            str(finding.placements[0].root) if finding.placements else "",
        ),
    )


def _orphan(placement: Placement, bundled: bool) -> Finding:
    return _finding(
        ORPHAN_RECEIPT,
        placement.name,
        "the receipt in %s records %s, but nothing is installed there"
        % (placement.root, placement.name),
        [placement],
        bundled,
    )


def _duplicate(name: str, live: Sequence[Placement], bundled: bool) -> Finding:
    chosen = canonical(live)
    other = _other_than(chosen, live)
    return _finding(
        DUPLICATE_DIVERGED,
        name,
        "%s is installed in %d roots with %d different contents"
        % (name, len(live), len({item.digest for item in live})),
        live,
        bundled,
        (chosen.path, other.path),
        (str(chosen.root), str(other.root)),
    )


def _other_than(chosen: Placement, placements: Sequence[Placement]) -> Placement:
    for placement in placements:
        if placement.digest != chosen.digest:
            return placement
    return placements[-1]


def _findings_for_name(name: str, live: Sequence[Placement], bundled: bool) -> list:
    """One name's findings, in the suppression order the module documents."""
    results: list = []
    suppressed: set = set()

    broken = [
        placement
        for placement in live
        if placement.shape == "link" and placement.digest == "missing"
    ]
    for placement in broken:
        suppressed.add(placement.path)
        results.append(
            _finding(
                BROKEN_LINK,
                name,
                "%s is a link whose target no longer exists" % placement.path,
                [placement],
                bundled,
            )
        )

    for placement in live:
        if placement.path in suppressed or placement.complete:
            continue
        suppressed.add(placement.path)
        results.append(
            _finding(
                INCOMPLETE,
                name,
                "%s has no SKILL.md, so no agent can load it" % placement.path,
                [placement],
                bundled,
            )
        )

    source_target = (install.SOURCE_ROOT / name).resolve()
    for placement in live:
        if placement.path in suppressed or not bundled:
            continue
        if placement.shape != "link" or placement.link_target is None:
            continue
        if placement.link_target == source_target:
            continue
        # The wrong target is the cause and the content difference the symptom,
        # so this suppresses DIVERGED rather than being reported beside it.
        suppressed.add(placement.path)
        pair, labels = _source_pair(placement)
        results.append(
            _finding(
                STALE_LINK,
                name,
                "%s links to %s, not to this checkout"
                % (placement.path, placement.link_target),
                [placement],
                bundled,
                pair,
                labels,
            )
        )

    remaining = [placement for placement in live if placement.path not in suppressed]

    diverged = [
        placement
        for placement in remaining
        if bundled and placement.matches_source is False
    ]
    if diverged and not all(
        _only_model_invocation_differs(placement) for placement in diverged
    ):
        pair, labels = _source_pair(diverged[0])
        results.append(
            _finding(
                DIVERGED,
                name,
                "%s differs from this checkout in %s"
                % (name, ", ".join(str(item.root) for item in diverged)),
                diverged,
                bundled,
                pair,
                labels,
            )
        )

    digests = {placement.digest for placement in remaining}
    if len(remaining) >= 2 and len(digests) > 1:
        results.append(_duplicate(name, remaining, bundled))
    elif len(remaining) >= 2 and len({placement.shape for placement in remaining}) > 1:
        results.append(
            _finding(
                SHAPE_MISMATCH,
                name,
                "%s holds the same content as both a copy and a link" % name,
                remaining,
                bundled,
            )
        )
    elif len(remaining) == 1:
        only = remaining[0]
        if only.recorded_mode and only.shape != only.recorded_mode:
            results.append(
                _finding(
                    SHAPE_MISMATCH,
                    name,
                    "%s is a %s, but the receipt records a %s"
                    % (only.path, only.shape, only.recorded_mode),
                    remaining,
                    bundled,
                )
            )
    return results


# -- resolutions -------------------------------------------------------------


def _reinstall(root: Path, name: str, mode: str) -> Fix:
    return Fix(REINSTALL, root, name, mode)


def _keep(label: str) -> Resolution:
    return Resolution(KEEP, label, NONE, ())


def _uninstall_each(placements: Sequence[Placement]) -> list:
    """One `uninstall the copy in <root>` resolution per placement."""
    return [
        Resolution(
            UNINSTALL,
            "uninstall the copy in %s" % placement.root,
            REMOVE,
            (Fix(UNINSTALL, placement.root, placement.name, "copy"),),
        )
        for placement in placements
    ]


def resolutions_for(
    kind: str, name: str, placements: Sequence[Placement], bundled: bool
) -> tuple:
    """The offered fixes for one finding, default first.

    A fixed table rather than a judgement call at report time: the same
    inconsistency offers the same choices in the dashboard, in `skills doctor`,
    and in the JSON a script reads.
    """
    placements = list(placements)
    first = placements[0] if placements else None

    if kind == BROKEN_LINK:
        if not bundled:
            return tuple(_uninstall_each(placements) + [_keep("leave the broken link")])
        return (
            Resolution(
                REINSTALL,
                "reinstall the link from this checkout",
                WRITE,
                (_reinstall(first.root, name, "link"),),
            ),
            Resolution(
                REINSTALL,
                "reinstall as a copy",
                WRITE,
                (_reinstall(first.root, name, "copy"),),
            ),
        ) + tuple(_uninstall_each(placements))

    if kind == INCOMPLETE:
        if not bundled:
            return tuple(
                _uninstall_each(placements) + [_keep("leave the partial directory")]
            )
        return (
            Resolution(
                REINSTALL,
                "reinstall from this checkout",
                WRITE,
                (_reinstall(first.root, name, first.recorded_mode or "copy"),),
            ),
        ) + tuple(_uninstall_each(placements))

    if kind == STALE_LINK:
        return (
            Resolution(
                RELINK,
                "relink to this checkout",
                WRITE,
                (Fix(RELINK, first.root, name, "link"),),
            ),
            Resolution(
                REINSTALL,
                "reinstall as a copy",
                WRITE,
                (_reinstall(first.root, name, "copy"),),
            ),
            _keep("keep the link where it points"),
        ) + tuple(_uninstall_each(placements))

    if kind == DIVERGED:
        return (
            Resolution(
                REINSTALL,
                "reinstall every diverged copy from this checkout",
                WRITE,
                tuple(
                    _reinstall(placement.root, name, placement.shape or "copy")
                    for placement in placements
                ),
            ),
            _keep("keep the local edits"),
        ) + tuple(_uninstall_each(placements))

    if kind == DUPLICATE_DIVERGED:
        chosen = canonical(placements)
        others = [item for item in placements if item.path != chosen.path]
        if not bundled:
            return tuple(
                _uninstall_each(others) + [_keep("keep both copies as they are")]
            )
        return (
            Resolution(
                REINSTALL,
                "reinstall all copies from this checkout",
                WRITE,
                tuple(
                    _reinstall(placement.root, name, placement.shape or "copy")
                    for placement in placements
                ),
            ),
            _keep("keep both copies as they are"),
        ) + tuple(_uninstall_each(others))

    if kind == SHAPE_MISMATCH:
        mode = first.recorded_mode or canonical(placements).shape or "copy"
        return (
            Resolution(
                REINSTALL,
                "reinstall all as a %s" % mode,
                WRITE,
                tuple(_reinstall(placement.root, name, mode) for placement in placements),
            ),
            _keep("keep the shapes as they are"),
        )

    if kind == ORPHAN_RECEIPT:
        forget = Resolution(
            FORGET,
            "forget the entry",
            REMOVE,
            (Fix(FORGET, first.root, name, "copy"),),
        )
        if not bundled:
            return (forget,)
        return (
            forget,
            Resolution(
                REINSTALL,
                "reinstall from this checkout",
                WRITE,
                (_reinstall(first.root, name, first.recorded_mode or "copy"),),
            ),
        )

    if kind == CORRUPT_RECEIPT:
        return (_keep("leave it; the next install rewrites it"),)

    raise install.InstallError("unknown finding kind: %s" % kind)


# -- applying ----------------------------------------------------------------


def apply_fix(fix: Fix, dry_run: bool) -> str:
    """Dispatch one atomic fix to its `install.py` primitive, and return its line."""
    if fix.action in (REINSTALL, RELINK):
        source = install.SOURCE_ROOT / fix.name
        if not source.is_dir():
            raise install.InstallError("not a bundled skill: %s" % fix.name)
        if fix.action == RELINK:
            return install.relink_one(fix.root, fix.name, dry_run)
        return install.install_one(source, fix.root, fix.mode, True, dry_run)
    if fix.action == UNINSTALL:
        # Never allow_unrecorded and never keep_backup=False: an unrecorded
        # directory is `--unrecorded`'s business, and a removal offered as a
        # repair is always the recoverable kind.
        return install.uninstall_one(fix.name, fix.root, dry_run)
    if fix.action == FORGET:
        return install.forget_entry(fix.root, fix.name, dry_run)
    if fix.action == KEEP:
        return "unchanged  %s" % (fix.root / fix.name)
    raise install.InstallError("unknown fix action: %s" % fix.action)


def apply_resolution(resolution: Resolution, dry_run: bool) -> list:
    """Every fix in order; the first InstallError stops the rest and propagates."""
    return [apply_fix(fix, dry_run) for fix in resolution.fixes]


# -- diff --------------------------------------------------------------------


def _read_text(path: Path) -> Optional[list]:
    try:
        if path.stat().st_size > DIFF_FILE_CAP:
            return None
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None


def diff_text(
    left: Path,
    right: Path,
    left_label: str,
    right_label: str,
    max_lines: int = DIFF_LINE_CAP,
) -> str:
    """A unified diff of two skill trees as plain text, links resolved.

    No markup: the dashboard colours it by line prefix, and `skills doctor`
    would only have to strip it back out again.
    """
    sides = []
    for path in (left, right):
        base = Path(path).resolve()
        sides.append(_files_under(base) if base.is_dir() else {})
    left_files, right_files = sides
    lines: list = []
    for relative in sorted(set(left_files) | set(right_files)):
        if relative not in right_files:
            lines.append("--- only in %s: %s" % (left_label, relative))
            continue
        if relative not in left_files:
            lines.append("+++ only in %s: %s" % (right_label, relative))
            continue
        first, second = left_files[relative], right_files[relative]
        try:
            if first.read_bytes() == second.read_bytes():
                continue
        except OSError:  # pragma: no cover - both were listed as files
            pass
        before, after = _read_text(first), _read_text(second)
        if before is None or after is None:
            lines.append("binary or oversized file differs: %s" % relative)
            continue
        lines.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile="%s/%s" % (left_label, relative),
                tofile="%s/%s" % (right_label, relative),
                n=2,
                lineterm="",
            )
        )
    if not lines:
        return "no differences"
    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + ["… %d more lines" % hidden]
    return "\n".join(lines)


# -- reporting ---------------------------------------------------------------


def _root_summary(inv: Inventory) -> list:
    """(scope, root, skill count, receipt note) per scanned root."""
    rows = []
    for root, scope in inv.roots:
        count = sum(1 for placement in inv.placements if placement.root == root)
        receipt = install.read_receipt(root)
        if root in inv.unreadable_receipts:
            note = "receipt unreadable"
        elif receipt:
            note = "receipt v%s" % receipt.get("schema_version", install.RECEIPT_SCHEMA)
        else:
            note = "no receipt"
        rows.append((scope, root, count, note))
    return rows


def report_json(inv: Inventory, results: Sequence[Finding]) -> dict:
    """The machine-readable half of `skills doctor`."""
    return {
        "schema_version": REPORT_SCHEMA,
        "collection": "dm1681/skills",
        "version": install.VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": [
            {
                "path": str(root),
                "scope": scope,
                "receipt": note.startswith("receipt v"),
                "skills": count,
            }
            for scope, root, count, note in _root_summary(inv)
        ],
        "missing_roots": [str(root) for root in inv.missing_roots],
        "unreadable_receipts": [str(root) for root in inv.unreadable_receipts],
        "findings": [
            {
                "kind": finding.kind,
                "name": finding.name,
                "severity": finding.severity,
                "detail": finding.detail,
                "paths": [str(placement.path) for placement in finding.placements],
                "resolutions": [
                    {
                        "action": resolution.action,
                        "label": resolution.label,
                        "consequence": resolution.consequence,
                        "fixes": [
                            {
                                "action": fix.action,
                                "root": str(fix.root),
                                "name": fix.name,
                                "mode": fix.mode,
                            }
                            for fix in resolution.fixes
                        ],
                    }
                    for resolution in finding.resolutions
                ],
            }
            for finding in results
        ],
    }


def _plural(count: int, word: str) -> str:
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def _inconsistencies(count: int) -> str:
    return "%d inconsistenc%s" % (count, "y" if count == 1 else "ies")


def render_report(
    inv: Inventory,
    results: Sequence[Finding],
    stream: TextIO = sys.stdout,
    include_foreign: bool = False,
) -> None:
    """The human half: what was scanned, what disagrees, and what to run next."""
    if not inv.placements and not results:
        print("nothing installed yet: scanned %s" % _plural(len(inv.roots), "root"),
              file=stream)
        return
    print(
        "scanned %s · %s · %s"
        % (
            _plural(len(inv.roots), "root"),
            _plural(len(inv.placements), "installed skill"),
            _inconsistencies(len(results)),
        ),
        file=stream,
    )
    print("", file=stream)
    print("roots", file=stream)
    rows = _root_summary(inv)
    width = max([len(str(root)) for _s, root, _c, _n in rows] + [8])
    for scope, root, count, note in rows:
        print(
            "  %-8s %-*s  %-9s  %s"
            % (scope, width, root, _plural(count, "skill"), note),
            file=stream,
        )
    for root in inv.missing_roots:
        print(
            "  %-8s %-*s  %s"
            % ("missing", width, root, "recorded, no longer on disk"),
            file=stream,
        )
    if not results:
        print("", file=stream)
        print("no inconsistencies", file=stream)
        if not include_foreign:
            print(
                "skills with no source in this checkout are not compared; "
                "pass --include-foreign to include them",
                file=stream,
            )
        return
    print("", file=stream)
    print("inconsistencies", file=stream)
    for finding in results:
        print("  %-20s %s" % (finding.kind, finding.name), file=stream)
        print("      %s" % finding.detail, file=stream)
        for placement in finding.placements:
            if not placement.present:
                continue
            print(
                "      %-40s %-5s %-9s %s"
                % (
                    placement.path,
                    placement.shape or "",
                    short_digest(placement.digest),
                    "matches this checkout"
                    if placement.matches_source
                    else "differs"
                    if placement.matches_source is False
                    else "no source to compare",
                ),
                file=stream,
            )
        if finding.resolutions:
            print("      fix: %s" % finding.resolutions[0].label, file=stream)
    print("", file=stream)
    print(
        "run `skills doctor --fix` to apply the first fix for each, or "
        "`skills manage`\nto review the diffs and choose.",
        file=stream,
    )


def command_doctor_from_installer(args: argparse.Namespace) -> int:
    """`install.py --doctor`: the bootstrap path, for a machine with no shim."""
    home = args.home.expanduser()
    inv = scan(
        home,
        [args.project_dir.expanduser()],
        install._status_roots(args),
    )
    results = findings(inv)
    render_report(inv, results)
    return 3 if results else 0
