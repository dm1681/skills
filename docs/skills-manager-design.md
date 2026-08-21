# Design: machine-wide manager, uninstall, per-skill versions

Three additions, designed together because they share one dependency chain:
uninstall must exist before the roots index is worth writing (something has to
prune it), and per-skill versions must exist before the TUI can show them.

Status: design only. Nothing here is implemented.

---

## 1. Machine-wide roots index

### The gap

`resolve_roots` (`install.py:303`) answers "which directories does *this*
invocation touch", from `--scope`, `--agent`, and `--project-dir` — the last
defaulting to `Path.cwd()` (`install.py:1655`). Nothing records the roots any
previous invocation touched, so nothing can enumerate them. `--status` is
therefore a question about where you are standing, not about the machine.

### The index

A single file, `~/.dm1681-skills-roots.json`:

```json
{
  "version": 1,
  "roots": [
    {"path": "/Users/d/.claude/skills",           "scope": "user",    "agent": "claude",    "last_seen": "2026-08-20T…"},
    {"path": "/Users/d/.agents/skills",           "scope": "user",    "agent": "universal", "last_seen": "2026-08-20T…"},
    {"path": "/Users/d/projects/foo/.claude/skills", "scope": "project", "agent": "claude", "last_seen": "2026-07-02T…"}
  ]
}
```

**The index is a cache, not a source of truth.** Every root keeps its own
`.dm1681-skills.json` receipt; the index only says *where to look*. This is the
load-bearing property:

- Delete the index and nothing breaks — scoped `--status` behaves exactly as it
  does today, and the next install rebuilds the entry.
- An index entry whose directory is gone (project deleted) is a `VANISHED`
  report and a prune offer, never an error. Same posture as `read_receipt`
  (`install.py:985`) returning `None` rather than raising.
- The index never holds skill names. Duplicating the receipts is how they would
  drift, and drift between two records of the same fact is the exact failure
  `root_status` was written to catch.

### API

```python
def known_roots(home: Path) -> list[RootRecord]
def remember_root(root: Path, scope: str, agent: str, home: Path, dry_run: bool) -> None
def forget_root(root: Path, home: Path) -> None
def machine_status(home: Path) -> MachineReport
```

`remember_root` is called from the same place `write_receipt` is, writes
atomically through the temp-file + `os.replace` pattern (`install.py:981`), and
honours `--home` so tests can redirect it. `--target` installs are recorded too;
an explicit root is still a root you will want to see later.

`machine_status` maps `root_status` — already scope-agnostic, already takes an
arbitrary root — over `known_roots`, plus the shadowing pass below.

### Shadowing

With every root in one view, a new class of finding becomes visible: one skill
name present in more than one root.

**Report the collision, never the winner.** Which copy an agent loads is the
harness's rule, not this installer's, and guessing it would be the kind of
confident wrong answer the receipt reconciliation exists to prevent.

Two states, because they are not equally interesting:

| state | meaning |
|---|---|
| `SHADOWED` | same name in >1 root, **identical contents** — harmless, informational |
| `DIVERGENT` | same name in >1 root, **contents differ** — actionable; the agent's behaviour depends on which one it reads |

Only `DIVERGENT` joins `ACTIONABLE_STATES` and drives the exit-3 code. A
machine-wide install by design puts identical copies in `.agents` and `.claude`;
if that flagged every time, the flag would be worthless.

### CLI

```
skills status --all          # every known root, user and project
install.py --status --all
```

Reuses exit `3` for "something needs updating". `--all` and `--scope` are
mutually exclusive: one asks about the machine, the other about a place.

---

## 2. Uninstaller

### Placement

`install.uninstall_one(name, root, force, dry_run) -> str`, sitting beside
`install_one` in the same module. The rule that every install path goes through
one function is what keeps backups, receipts, and root resolution defined once;
uninstall earns the same treatment or it will grow a second copy of the backup
logic.

Per the repo's interaction split, the CLI stays scripted and the TUI owns the
interactive flow — no prompts inside `uninstall_one`.

### Behaviour

1. Resolve `destination = root / name`. Absent (`exists() or is_symlink()`,
   the same broken-symlink-aware test as `install_one:926`) → `"absent  <path>"`,
   exit 0. Removing nothing is a success, so this is safe in scripts and hooks.
2. **Refuse to remove what this collection did not install**, unless `--force`:
   if the name is missing from the receipt *and* `trees_equal` says the
   directory does not match this checkout, it is someone else's. This is the
   mirror of `install_one`'s refusal to overwrite a differing destination, and
   it is the property that makes the uninstaller safe to point at a shared root.
3. Back up first via `backup_path` (`install.py:900`) → `shutil.move`. Same
   `.skills-backups/` layout, so an accidental removal is recovered the same way
   an accidental overwrite already is.
4. Rewrite the receipt without the name. A receipt that reaches zero skills is
   deleted.
5. **Never `rmdir` the root.** `~/.claude/skills/` is shared with tools this
   collection does not manage.
6. `forget_root` when the root no longer holds anything of ours.

### Surfaces

```
skills uninstall NAME [NAME …]               # the surface people actually use
skills uninstall --all                       # everything in this receipt
skills uninstall --orphans                   # only names the collection dropped

install.py --uninstall --skill NAME [--skill NAME …]
install.py --uninstall --all-skills
install.py --uninstall --orphans
```

Both surfaces, for the same reason `--status --all` has both: `skills` is the
command the docs point people at, and a removal path most people never find is
one they work around by deleting the directory by hand — which leaves the
receipt claiming a skill that is gone. `skills uninstall` naming nothing is an
error rather than a shortcut for everything; the install side can fall back to
the dashboard when given no names, because the cost of guessing wrong there is
an extra directory and here it is a deleted one.

All honour `--scope`, `--agent`, `--target`, `--dry-run`, `--force`.

`--orphans` closes a loop the repo already documents: a skill removed from the
collection sits in a receipt as `ORPHAN` with no command to clear it.

### TUI

An uninstall action on the existing rows rather than a separate screen: `x`
marks a selected installed row for removal, and the review step lists removals
above installs.

**Colour.** The contract reserves red for failure so a healthy run is provably
red-free — an uninstall is not a failure and must not be red. Peach is the
closest existing meaning: "an overwrite; the old copy is backed up first."
Uninstall takes the identical backup-then-mutate path minus the write.

**DECIDED — the valence ramp.** The palette becomes one axis, and every hue
still means exactly one thing:

    grey  ──▶  green  ──▶  peach  ──▶  red
    nothing    a gain     destructive   failure
    happens               (recoverable)

- `green` (`#a6e3a1`) = **install**. A write happens and it succeeds. This is
  what the `✓ N installed` line already used green for, so the completion line
  and the plan now agree.
- `grey` (`MUTE`) = **up to date**. A non-event: nothing will happen to that
  row, and grey is already the dashboard's "context, not consequence" hue.
- `peach` = **replace and remove**. Both take the identical backup-then-mutate
  path, so the contract line becomes "a destructive change; the old copy is
  backed up first."
- `red` stays failure-only, so a healthy run is still provably red-free.

`blue` (`#89b4fa`) retires from the state palette and is reused for the version
column, which needed a hue of its own.

---

## 3. Per-skill versions and upstream freshness

### The blocker

There is no per-skill version anywhere. Every `SKILL.md` in the collection
carries `name` and `description` and nothing else, and the validator
(`scripts/validate_repo.py:102`) requires exactly those two. `VERSION` (10.0.1)
versions the collection, not its members.

So the first question is where a version comes from.

| source | pro | con |
|---|---|---|
| `version:` in frontmatter | explicit; survives into the installed copy, where there is no git | a version nobody bumps lies confidently, so it needs enforcement |
| git log of `skills/<name>/` | free, always accurate, zero discipline | needs a git checkout; a release archive has none |
| collection `VERSION` | free | says nothing per-skill |

### Recommendation: both, layered

They answer different questions, and the second cannot answer the first.

- **`version:` in frontmatter is the identity.** The artifact whose version you
  actually want to read is the *installed* copy at
  `~/.claude/skills/foo/SKILL.md` — which has no git history attached to it.
  Only a field inside the file survives the copy.
- **git is the freshness.** Whether the checkout itself trails origin is
  something no frontmatter field can know.

`frontmatter_value` (`install.py:198`) already reads one key out of a
`SKILL.md` and is deliberately dependency-free. Reading `version:` costs a new
constant and nothing else.

### Three comparisons, three costs

| # | question | how | cost |
|---|---|---|---|
| 1 | installed contents vs. checkout | `trees_equal` → `OUTDATED` | exists today; local |
| 2 | installed **version** vs. checkout version | `frontmatter_value` on both `SKILL.md`s | local, ~free |
| 3 | checkout vs. **origin**, per skill | one fetch, then `git rev-list --count HEAD..origin/<branch> -- skills/<name>/` | **network** |

(1) and (2) are distinct and both worth showing: contents can differ while
versions match — that is unbumped drift, the failure mode the version field
introduces — and it is precisely what you want surfaced.

(3) layers over `checkout_behind_origin` (`install.py:1192`), which already
fetches and already documents *why the fetch is opt-in*: "This costs a fetch, so
it is opt-in rather than part of the default answer." That constraint carries
over intact — **the dashboard must not touch the network at startup.** Bind it
to `u`, run it in a `@work` thread, render `checking…` and fill in. One fetch
serves all N skills; the per-skill `rev-list` calls are local and cheap.

### Display

`SkillRow.redraw` (`skills_tui.py:264`) currently renders

```
◆ skill-name            [ PILL ]  → verb
    one-line summary
```

Add a version between name and pill:

```
◆ tdd                    v1.2.0            [ UP TO DATE ]
◆ diagnose               v1.1.0 → v1.3.0   [ DIFFERS ]     → replace
◆ wow-addon-dev          v1.2.0 ▲          [ DIFFERS ]     → replace  unbumped
◆ research               v2.0.0            [ UP TO DATE ]  ▲ upstream
```

The version column holds only the version and the unbumped marker; the
upstream marker sits after the pill, with the other advisories, because it is
a fact about the checkout rather than about the number.

Colours stay inside the contract — per the DECIDED block above, which is what
the implementation follows:

- matching version → `VERSION` blue. Blue left the state palette precisely so
  a settled version could have a hue that is not a state.
- `installed → checkout` arrow → `REPLACE` peach, matching the row's own
  consequence.
- unknown or vendored → `MUTE`; that is context, not a number.
- unbumped marker (contents differ, version does not) → `ADVISE` yellow.
- upstream-newer marker → `ADVISE` yellow: "allowed, but probably not what you
  want" is exactly "you can install this, but origin has newer."

### The discipline this buys, and its cost

A version field that nobody bumps is worse than no field. The mitigation is to
make it self-enforcing rather than remembered: a validator check that any skill
whose files changed since the last release tag also has a changed `version:`.
Without that check, do not add the field.

`RELEASING.md` needs a matching rule for how a skill's version relates to the
collection's.

---

## Build order

Each step ships working and testable on its own.

1. **`version:` field + validator rules** (incl. the bump check) — foundation,
   no UI.
2. **TUI version column** — comparisons 1 and 2 only. No network.
3. **`uninstall_one` + CLI flags** — with the refuse-what-we-did-not-install
   guard.
4. **TUI uninstall action** — peach `REMOVE`.
5. **Roots index** — `remember_root` from install, `forget_root` from uninstall.
   Comes after (3) so it is never written without a pruner.
6. **`--status --all` + shadowing** — `SHADOWED` / `DIVERGENT`.
7. **TUI upstream check on `u`** — the only networked step, last.

Each step lands with a test alongside the existing suite, and any step touching
a row must prove the row renders, not merely that the validator is green.
